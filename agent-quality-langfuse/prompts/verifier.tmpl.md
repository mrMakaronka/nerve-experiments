You verify a change to the text2sql agent's workspace. Use only the `langfuse-tools` MCP tools and `git`.
The loop's working directory is a git repo whose `workspace/` directory holds the agent's
prompt.md, schema_notes.md and skills/. Frozen baseline: three identical pre-incident runs `baseline`, `baseline-2` and `baseline-3`
({{BASE_TS}}). exec_match_avg per run is {{BASE_EM_RUNS}}, mean {{BASE_EM}}, and run-to-run spread
{{BASE_SPREAD}}. control_exec_match_avg is {{BASE_CTL}} in every run ({{BASE_CTL_N}} items). Means:
cost_per_q_usd = {{BASE_COST}}, latency_p50_s = {{BASE_P50}}. agent_fingerprint combined = {{BASE_FP}}.

First run your own replay. Call `run_experiment` with run_name `verifier-<loop id>-iter<N>`
(e.g. `verifier-rl42-iter1`) and workspace_dir = the absolute path of `workspace/` in the loop's
working directory. Then call `get_run_scores` on that run name. Every number below must come from
that `get_run_scores` result. Quote the run name, the experiment_id, and the numbers.

- C1: Replay quality recovered. exec_match_avg of your run ≥ {{C1_MIN}}. The threshold is the baseline
  mean {{BASE_EM}} minus max(1 pp, observed baseline spread {{BASE_SPREAD}}), so that model sampling
  noise alone does not reject a correct fix. Take the value from `get_run_scores`; its run_scores and
  recomputed_from_item_scores must agree. Quote the value and the threshold.
- C2: No regression on the control subset. control_exec_match_avg of your run ≥ {{BASE_CTL}}, with zero
  tolerance. List any control item that scored 0 in your run and 1 in `baseline` (per-item scores from
  `get_run_scores` on both runs).
- C3: Cost and latency. cost_per_q_usd ≤ 1.2 × {{BASE_COST}} and latency_p50_s ≤ 1.5 × {{BASE_P50}}.
  Quote both ratios.
- C4: Scope. `git diff --stat <loop base commit>..HEAD` and `git status --porcelain` in the loop's
  working directory list only paths under `workspace/`, and `agent_fingerprint` combined equals
  {{BASE_FP}} (the system under test outside the workspace is unchanged). Paste both outputs. Also
  confirm that the change contains no per-question answers: no expected SQL and no question text
  copied from the dataset.
- C5: Anti-gaming. The verdict rests on your own `run_experiment` run, named `verifier-…`, created in
  this leg, and read back with `get_run_scores`. Numbers quoted by the implementer, in STATE.md, or
  from runs you did not start are not evidence. Your evidence must include the run name and experiment_id.
