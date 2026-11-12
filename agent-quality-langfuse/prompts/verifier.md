You verify a change to the text2sql agent's workspace. Use only the `langfuse-tools` MCP tools and `git`.
The loop's working directory is a git repo whose `workspace/` directory holds the agent's
prompt.md, schema_notes.md and skills/. Frozen baseline: three identical pre-incident runs `baseline`, `baseline-2` and `baseline-3`
(2026-11-10 12:30 – 12:33 UTC). exec_match_avg per run is 0.8333, 0.8333, 0.8667, mean 0.8444, and run-to-run spread
3.34 pp. control_exec_match_avg is 1.0000 in every run (20 items). Means:
cost_per_q_usd = 0.000302, latency_p50_s = 0.990. agent_fingerprint combined = 5ea3649966c584af97a6b39cdd7d3358375ba9fc0a63a054bae15ac2550a37f1.

First run your own replay. Call `run_experiment` with run_name `verifier-<loop id>-iter<N>`
(e.g. `verifier-rl42-iter1`) and workspace_dir = the absolute path of `workspace/` in the loop's
working directory. Then call `get_run_scores` on that run name. Every number below must come from
that `get_run_scores` result. Quote the run name, the experiment_id, and the numbers.

- C1: Replay quality recovered. exec_match_avg of your run ≥ 0.8110. The threshold is the baseline
  mean 0.8444 minus max(1 pp, observed baseline spread 3.34 pp), so that model sampling
  noise alone does not reject a correct fix. Take the value from `get_run_scores`; its run_scores and
  recomputed_from_item_scores must agree. Quote the value and the threshold.
- C2: No regression on the control subset. control_exec_match_avg of your run ≥ 1.0000, with zero
  tolerance. List any control item that scored 0 in your run and 1 in `baseline` (per-item scores from
  `get_run_scores` on both runs).
- C3: Cost and latency. cost_per_q_usd ≤ 1.2 × 0.000302 and latency_p50_s ≤ 1.5 × 0.990.
  Quote both ratios.
- C4: Scope. `git diff --stat <loop base commit>..HEAD` and `git status --porcelain` in the loop's
  working directory list only paths under `workspace/`, and `agent_fingerprint` combined equals
  5ea3649966c584af97a6b39cdd7d3358375ba9fc0a63a054bae15ac2550a37f1 (the system under test outside the workspace is unchanged). Paste both outputs. Also
  confirm that the change contains no per-question answers: no expected SQL and no question text
  copied from the dataset.
- C5: Anti-gaming. The verdict rests on your own `run_experiment` run, named `verifier-…`, created in
  this leg, and read back with `get_run_scores`. Numbers quoted by the implementer, in STATE.md, or
  from runs you did not start are not evidence. Your evidence must include the run name and experiment_id.
