---
name: Agent tuning playbook (text2sql quality regressions)
description: >
  Procedure for diagnosing and fixing a quality regression of the text2sql agent using
  Langfuse scores and traces: confirm the drop, classify failures, find the cause, make the
  smallest workspace change, replay, and prove no regression on the control subset.
version: 1.0.0
context: procedure
---

# Agent tuning playbook

1. **Confirm the drop with numbers.** Call `get_run_scores` for `baseline` and for the latest run.
   Write down exec_match_avg, control_exec_match_avg, cost_per_q_usd and latency_p50_s for both.
2. **Classify the failures** with `get_failed_traces` on the degraded run. Sort each failure into
   one of these:
   - SQL error (`no such column`, `no such table`, syntax);
   - wrong rows (wrong join, filter, aggregation or column);
   - empty result.
   A sudden cluster of the same error usually means an environment change, not a model change.
3. **Find the cause** before editing anything.
   - For schema errors, compare `describe_live_db()` with the names the agent used, and with the
     names in the question evidence.
   - Find out which items fail now but passed at `baseline`. Those are the regression; failures
     present in both runs are not.
4. **Make the smallest change that removes the cause**, only in the workspace (`prompt.md`,
   `schema_notes.md`, `skills/`).
   - Schema facts belong in `schema_notes.md`.
   - Fix the cause, not individual questions. Do not paste per-question answers or expected SQL
     into the workspace. The change is also judged on questions you cannot see, so a fix that only
     memorises `replay` will be caught.
   - Keep the prompt short. Extra tokens cost money on every call, and the budget is ≤ 1.2× the
     baseline cost per question.
5. **Replay.** Call `run_experiment` with a new descriptive run name (e.g. `impl-schema-notes-1`)
   and the absolute path of your workspace directory. Then read the results back with
   `get_run_scores`. Check four things:
   - exec_match_avg is back to ≥ baseline − 1 pp;
   - control_exec_match_avg is ≥ baseline;
   - cost is ≤ 1.2× baseline;
   - latency_p50 is ≤ 1.5× baseline.
   If any check fails, go back to step 2 on the new run.
6. **Record** in STATE.md: the cause (with the evidence), the diff, your run name, and its numbers,
   marked as your own unverified claim. Commit the workspace change to git.
