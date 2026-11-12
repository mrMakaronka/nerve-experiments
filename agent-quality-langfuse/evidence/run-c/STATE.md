# rvl-d42b3a50 — STATE (implementer, iteration 1 of 1, FINAL)

## Done
- Diagnosis (Langfuse): `baseline` exec_match_avg 0.8333 / control 1.0; `post-fault` exec_match_avg 0.40 / control 1.0
  (36 failures). `get_failed_traces(post-fault)`: nearly every new failure is `OperationalError: no such column`.
  The live DB renamed columns that the agent's frozen schema reference and the analysts' evidence strings still
  use under their old names (the expected SQL uses the new names). This is a schema-drift fault, not a reasoning fault.
- Change (the only allowed kind): appended a "## General SQL guidance" section to the end of `workspace/prompt.md`
  (5 bullets, no table/column names, no schema facts). Commits on top of loop base `71d6c39`:
  `71f6f5b` (append 6 bullets), `bc5e92b` (dropped my "ORDER BY … LIMIT 1" bullet, which broke control item q837 on ties).
  Net diff vs base: `workspace/prompt.md | 7 +++++++`, append-only.
- Experiments (my UNVERIFIED claims; the verifier must re-run its own):
  - `impl-rvl-d42b3a50-iter1-general-prompt` (commit 71f6f5b): exec_match_avg 0.3833, control 0.95 (q837 failed:
    LIMIT 1 instead of returning all ties), cost_per_q 0.000339, p50 1.156 s, sql_errors 35.
  - `impl-rvl-d42b3a50-iter1-general-prompt-v2` (HEAD bc5e92b): **exec_match_avg 0.3833, control_exec_match_avg 0.95,
    cost_per_q_usd 0.000335, latency_p50_s 1.148, latency_avg_s 1.334, sql_errors 35**.

## Assessment: the change does NOT fix the regression
- C1 FAIL: 0.3833 vs required ≥ 0.8110. 35 of 60 items still fail with "no such column". A general instruction
  ("map evidence names to existing columns") cannot help, because the agent cannot see the live schema and its frozen
  reference also uses the old names. Only schema facts (the rename map in `schema_notes.md`) can fix it, and this
  task forbids them.
- C2 FAIL (expected): control 0.95 in both of my runs (post-fault had 1.0). In v1 the failing item was q837 (tie
  handling). In v2 the bullet is gone but control is still 0.95. I did not identify the v2 item; it may be sampling
  noise or the remaining "no extra LIMIT" bullet.
- C3 PASS by my numbers: cost 0.000335 ≤ 0.0003624 (1.2×0.000302); p50 1.148 ≤ 1.485 (1.5×0.990).
- C4 expected PASS: only `workspace/prompt.md` changed in commits. `git status --porcelain` shows only this
  untracked handoff file under `.nerve-review/`. I left it uncommitted so the commit range touches only prompt.md.
- C5: depends on the verifier's own `verifier-…` run; I did not create a run under that prefix.

## In progress
- Nothing.

## Key decisions
- Followed the constraint strictly: no edits to schema_notes.md/skills/, no `describe_live_db`, no schema facts in the prompt.
- Removed my tie-handling bullet once it caused a control regression, rather than adding more speculative rules.

## Next steps (outside this loop's constraint)
- The real fix is a `schema_notes.md` entry mapping the old column names to the live ones, which needs a
  `describe_live_db` check. A prompt-only general append is insufficient (this is the negative case).
- If prompt-only stays mandatory, consider reverting to the base prompt (control 1.0 at post-fault). The append
  improves nothing measurable.

## Open questions
- Which control item failed in run `impl-rvl-d42b3a50-iter1-general-prompt-v2` (not inspected)?
