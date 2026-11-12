## Context and anomalies (hand-written; read with the numbers above)

- **Clean baseline 16 min, not 10.** The frozen C1/C2 baseline is the 15 min before `inject_done`. A 10-min wait would have put
  the previous incident's tail inside the baseline and inflated the baseline error rate.
- **rep2-B disagreement: environmental, verifier correct per the criteria.** SREGym's in-memory Jaeger all-in-one
  (`observe/jaeger-agent`, 1 GiB limit) filled up around 04:24, the minute of injection. It thrashed at ~9.5 cores until it was
  OOMKilled at 04:45:43, slowing every service. The fix itself held: 0 % errors, oracle success. But synthetic-user
  p95 was 1.41–1.55× baseline against the 1.2× limit in all three verifier legs.
  - The implementer diagnosed Jaeger as the cause and declined to touch `observe` (out of scope). It asked for an operator decision.
  - Nobody intervened. The run used 3 iterations and $5.33.
  - This is the same class as demo-v1 Run B's host-memory spell: fixed latency thresholds cannot tell cluster-wide noise from a bad fix.
- **rep3-C was re-run once.** The first attempt (`rep3-C-authfail/`) failed 7 s into the implementer leg with "OAuth token revoked".
  - Claude Code had rotated the Keychain token after `refresh_claude_token.sh` copied it, 16 min earlier, before the baseline wait.
  - The leg never ran (cost $0, no verdict). It is excluded from `results.csv`.
  - Fix: `repeat.sh` now refreshes the token right before each loop. Re-run with `RUN_ONLY=rep3-C:C`.
- **Accounting's OOM was fixed once and stayed fixed.** In rep1-B the implementer again raised `accounting`'s memory limit
  (120 → 300 Mi) because C3 forced it to, as in demo-v1. The cluster isn't reset between runs, so later runs did not see that OOM cycle.
- **Mitigation latency** (loop start → first fix): Run B 57 s; rep1-B ~52 s (T_mit 7 min because of the accounting change);
  rep2-B 50 s; rep3-B 36 s.
- **Host stayed awake:** the whole run was under `caffeinate -is`, added after Run C2's idle sleep.
