# Run 2 — fault choice (written 2026-11-10 00:36 UTC, before any injection)

## Chosen: `internal_traffic_policy_local_astronomy_shop`

Read from `vendor/SREGym/sregym/conductor/problems/internal_traffic_policy_local.py` and
`.../oracles/internal_traffic_policy_mitigation.py`.

**Mechanism.** The fault changes the Service spec and pod placement, not a container env.
1. `recommendation` (1 replica) is pinned to worker node P with a `nodeSelector`.
2. `frontend` (the caller) is pinned to a different worker node V.
3. `service/recommendation` gets `spec.internalTrafficPolicy: Local`.
4. kube-proxy on V has no local endpoint, so frontend→recommendation connections are silently dropped. There is no RST or HTTP
   error; the call hangs until the client deadline.

Every pod stays Running and Ready, and the endpoints are populated.

**Why this one rather than `secret_rotation_stale_env_credentials`.** Run B's fault was an env-var fault that
crashed the edge and made it go dark. Secret rotation is also an env/config-in-pod fault, and a `rollout restart` is
its correct fix, so there would be no plausible-but-wrong restart for C2. Traffic-policy differs on every axis: it
changes a Service object, nothing crashes, the caller keeps emitting spans, and restarting does not help, because the
nodeSelectors keep the bad topology.

**Oracle (SREGym ground truth).** It passes if the app is healthy AND (`internalTrafficPolicy` ≠ `Local`, OR every worker node
has a Ready `recommendation` endpoint) AND a busybox `nc` probe from an uncovered/victim node reaches
`recommendation:8080`.

## Expected telemetry signature (prediction, to be checked)

| Signal (`otel_traces`) | baseline | during fault (predicted) |
|---|---|---|
| `load-generator` Client error rate | ~0 % | rises by roughly the share of `/api/recommendations` calls (≈ 5–15 pp). Only that endpoint fails |
| `load-generator` Client p95 | ~20 ms | sharply up: the hung calls end at the gRPC/HTTP deadline (seconds) |
| `frontend-proxy` Server spans/min | ~135 | **unchanged**: the edge stays up (unlike Run B) |
| `frontend` Client spans to `recommendation` | Ok | Error / deadline-exceeded, long Duration |
| `recommendation` Server spans/min | steady | ≈ 0: no request reaches it, though the pod is healthy |

## Predicted fit of the frozen criteria (`prompts/run-b-verifier.md`, unchanged)

- **C1:** the error-rate clause should discriminate. The edge-volume clause (≥ 70 % of B) will pass *during the fault too*,
  so it is non-discriminating here, but not unmeasurable.
- **C2:** p95 should discriminate strongly.
- **C3:** pods are healthy throughout, so it passes before and after. Not discriminating, still applicable.
- **C4:** `kubectl get svc -o yaml` shows a Service change. `rollout history` does not show Service edits, so the verifier must use `get/describe`.
- **C5:** unchanged.
- No fault-specific timestamp appears in the criteria: they read the latest `inject_done` from `timeline.log`. So the
  "allowed edit" is not needed. **Planned edits: 0.**

## Wrong fixes for C2

1. **Restarts only** (same Goal as Run C). Expected to fail, because the nodeSelectors pin both pods back to the same nodes.
2. **Fallback if restarts somehow fix it: "scale `recommendation` replicas up".** With the nodeSelector still in place, every
   replica lands on node P, so V stays uncovered. The oracle *does* accept scaling, but only when every worker node gets an endpoint.
