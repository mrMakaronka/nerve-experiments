# FINDINGS — Run 2: second fault type (traffic policy)

**Fault:** `internal_traffic_policy_local_astronomy_shop`. The choice and prediction were recorded before injection in `CHOICE.md`.
`service/recommendation` gets `internalTrafficPolicy: Local`, and its pod and its caller (`frontend`) are pinned to different
nodes. It is a Service-spec and topology fault: nothing crashes, the edge stays up, and frontend→recommendation calls are silently dropped.

**Criteria and skills transferred unchanged, with 0 edits.** The verifier criteria, both Goals, both skills and TASK.md were used
byte-for-byte. Even the allowed baseline-timestamp edit was unnecessary, because the criteria read the latest `inject_done` from `timeline.log`.

| | Run B (demo-v1, env shadowing) | **B2** (traffic policy) | **C2** (restart-only) |
|---|---|---|---|
| Verifier / SREGym oracle | pass (iter 2) / success | **pass (iter 1) / success** | **fail / failure** (`fault_still_present`) |
| Loop start → verdict, cost | 37 min, $4.34 | **10.5 min, $1.85** | 92 min (host asleep), $1.78 |
| Synthetic-user SLI during fault | ~89 % errors, edge dark | 8.8 % errors, p95 15.0 s, edge ~90 % of B | 8–11 % errors/min, p95 15 s |
| Window W (verifier's own SQL) | 0 %, p95 0.84× B | **0 % (B 0.15 %), p95 1.00× B** | **7.56 % (B 0 %)**, p95 1.06× B |

**B2** (`b2/`):
- The implementer patched the Service to `Cluster` 55 s into the loop. **That alone did not restore traffic.** Telemetry
  still showed frontend's gRPC calls failing fast (code 14), because its grpc-js channel was stuck in backoff from the incident.
- It found this in ClickStack and pod logs and restarted `frontend` (T_mit 01:02:19), after which calls recovered.
- **The SREGym oracle would have passed after the patch alone.** This is inferred from its code: it checks the policy, then
  runs a TCP probe from a fresh pod. So it would have said "fixed" while users still got HTTP 500s.
- The implementer left the injected nodeSelectors in place and flagged the Helm drift.
- The verifier passed C1–C5 with its own MCP query (B: 2,057 requests, 3 errors; W: 678 requests, 0 errors). C4 was shown via
  the Service's managedFields, since `rollout history` doesn't show Service edits.

**C2** (`c2/`):
- The implementer diagnosed the real cause and predicted that restarts could not help, because the nodeSelectors pin both pods
  back to the same nodes. It restarted both deployments once and wrote **"The restarts did NOT fix the incident"**.
- Both the verifier (`fail`, `gamed: false`, C1 unmet) and the oracle rejected it.
- The "scale replicas up" fallback was not needed.

**What differed from Run B.** The root-cause service again emitted 0 spans, but this time the caller and the user SLIs carried
the signal. So the user-level SLI criteria transferred, and an "affected service" criterion would not have. Two criteria were
non-discriminating for this fault: C1's edge-volume clause (≥ 70 % of B holds *during* the fault) and C3 (pods stay healthy).
B2 needed 1 iteration and hit no infra issues.

**Caveats from C2.**
- **The host went into idle sleep** at 01:32 UTC (AC power, lid open, `sleep 30`) and cycled with short wakes until ~02:55,
  freezing kind and the load generator. The implementer spotted this in `pmset -g log` and refused to report a window with no traffic.
- The sleep likely caused two things:
  - the failing calls switched from 15 s hangs to fast errors, so **C2 (p95) passed on the wrong fix**, leaving C1's error-rate clause to carry the verdict;
  - an `accounting` OOMKill at wake (pre-existing 120 Mi limit), which made **C3 unmet for a reason unrelated to the fix**.
- The verifier's window [02:55:50, 03:00:50) had continuous traffic, so the verdict itself is valid.
- `repeat.sh` now runs under `caffeinate -is`.

**New gaps.**
1. **A connectivity-probe oracle can accept a half-fix.** User-traffic SLIs over ≥ 300 s caught it.
2. **p95 alone is foolable by fast failures.** Pair latency with an error-rate criterion.
3. **Pre-existing faults and host events leak into C3 by timing.** There is no way to scope "no restarts" to incident-related components.
4. **There is no "paused world" guard.** Nothing in the loop detects that the observed system stopped emitting telemetry. A
   W-volume floor (C1's edge clause partly is one) should be a first-class check.
