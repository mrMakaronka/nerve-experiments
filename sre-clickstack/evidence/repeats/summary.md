# Repeats: env_variable_shadowing, Run B and Run C × N

Source: `results.csv` (one row per loop, written by `scripts/repeat_row.py`). Median (min–max).
`c1_value` / `c2_value` are recomputed by the harness over the 300 s before the verdict (synthetic-user error % / p95 ms); the verifier's own numbers are in each run's `verdict-iter*.json`.

| kind | runs | loop minutes | cost USD | iterations | c1 err % | c2 p95 ms | verifier queries |
|---|---|---|---|---|---|---|---|
| B | 3 | 17.6 (9.9–23.5) | 2.4 (1.63–5.33) | 1 (1–3) | 0 (0–0) | 21.5 (20.7–26.1) | 1 (1–7) |
| C | 3 | 9.4 (9–10.9) | 1.25 (1.23–1.43) | 1 (1–1) | 87.76 (87.57–91.64) | 19380.6 (16855.9–19452.1) | 1 (1–5) |

## Verdict vs SREGym oracle

- **B:** 2/3 runs where verifier `pass` and oracle `success` agree.
  - disagreement in `rep2-B`: verdict `needs_improvement`, oracle `success` (status=awaiting_user reason=max_iterations; C1:met C2:unmet C3:met C4:met C5:met; iter1 verdict=needs_improvement: C1, C3, C4, and C5 are met, but C2 is unmet. The final verifier-owned 300-second wind)
- **C:** 3/3 runs where verifier rejected (`fail`/`needs_improvement`) and oracle `failure` agree.

## Runs needing more than one iteration

- `rep2-B` (B): 3 iterations — status=awaiting_user reason=max_iterations; C1:met C2:unmet C3:met C4:met C5:met; iter1 verdict=needs_improvement: C1, C3, C4, and C5 are met, but C2 is unmet. The final verifier-owned 300-second window had zero user-facing errors and 1.381× baseline edge volume, while load-

## All runs

| run | kind | verdict | oracle | iter | loop min | $ | c1 | c2 | notes |
|---|---|---|---|---|---|---|---|---|---|
| rep1-B | B | pass | success | 1 | 17.6 | 2.4 | 0 | 21.5 | status=passed; C1:met C2:met C3:met C4:met C5:met |
| rep1-C | C | fail | failure | 1 | 10.9 | 1.43 | 87.57 | 19452.1 | status=awaiting_user reason=max_iterations; C1:unmet C2:unmet C3:unmet C4:met C5:met |
| rep2-B | B | needs_improvement | success | 3 | 23.5 | 5.33 | 0 | 26.1 | status=awaiting_user reason=max_iterations; C1:met C2:unmet C3:met C4:met C5:met; iter1 verdict=needs_improvement: C1, C |
| rep2-C | C | fail | failure | 1 | 9.0 | 1.23 | 91.64 | 16855.9 | status=awaiting_user reason=max_iterations; C1:unmet C2:unmet C3:unmet C4:met C5:met |
| rep3-B | B | pass | success | 1 | 9.9 | 1.63 | 0 | 20.7 | status=passed; C1:met C2:met C3:met C4:met C5:met |
| rep3-C | C | fail | failure | 1 | 9.4 | 1.25 | 87.76 | 19380.6 | status=awaiting_user reason=max_iterations; C1:unmet C2:unmet C3:unmet C4:met C5:met |

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

