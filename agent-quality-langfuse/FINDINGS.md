# FINDINGS: agent quality in Langfuse

**Setup.**
- System under test: a single-shot text-to-SQL agent, Claude Haiku 5.5 at low effort, on the BIRD `superhero` database (10 tables).
- It is traced and scored in self-hosted Langfuse v4. Scores: `exec_match`, `cost_usd`, `latency_s`.
- Questions: 120 BIRD dev questions.
  - 60 are in the Langfuse dataset `replay`. 20 of these are `control`: the fault touches none of their gold SQL, question or evidence.
  - 60 are in a hidden `oracle` file, scored locally.
- Fault: a schema change that renames 4 columns. The agent's schema reference is frozen, so it keeps using the old names.
- Nerve: Claude implementer and Codex verifier, connected to Langfuse through a 6-tool MCP (`langfuse-tools`).
- `nerve/` was not changed.

| | replay exec_match | control | oracle exec_match | verdict |
|---|---|---|---|---|
| baseline (3 identical runs) | 83 / 83 / 87 % | 20/20 ×3 | 85 % | — |
| post-fault | **40 %** (35 SQL errors) | 20/20 | **40 %** | — |
| **Run B** (fix workspace) | **93 %** (verifier's own replay) | 20/20 | **90 %** (85 % with schema_notes only) | **pass**, iteration 3, 21 min, ~$4 |
| **Run C** (prompt-only append) | **38 %** (verifier's own replay) | 19/20 | **38 %** | **fail** (C1, C2), 7 min, ~$1.2 |

Verifier runs: `verifier-rvl-87f3dbe9-iter3` ([run-b/verdict-iter3.json](evidence/run-b/verdict-iter3.json)) and `verifier-rvl-d42b3a50-iter1` ([run-c/verdict-iter1.json](evidence/run-c/verdict-iter1.json)); every run's scores are in [scores_table.md](evidence/scores_table.md). Loop costs are Nerve's API-equivalent figures; the loops ran on subscriptions.

**What transferred from the SRE case unchanged.** The loop shape and the evidence discipline:
- the verifier runs its own `run_experiment` (`verifier-<loop>-iter<N>`) and reads the scores back with `get_run_scores`;
- every verdict quotes the run name, the experiment_id and the numbers;
- `gamed=false` in all 4 verdicts.

Only the signal adapter changed: an MCP over the Langfuse experiments API in place of ClickHouse SQL.

**Findings.**
1. **The regression gate caught a real side effect, not noise.**
   - The implementer found all 4 renames on its first pass. A run with only `schema_notes.md` changed already scored 83 % with control 20/20, which would have passed.
   - It kept tuning `prompt.md` (a superlative rule, a casing rule, a no-extra-filters rule).
   - Iterations 1 and 2 were rejected on C2 because control item q837 flipped. In all 3 baselines the agent wrote `= (SELECT MIN …)`; after the new rule it wrote `ORDER BY … LIMIT 1`.
   - Iteration 3 narrowed the rule and passed.
   - Cost of over-reaching: 2 extra iterations (more than half of the loop's cost) and +16 % cost per question (still within the 1.2× budget).
2. **The hidden oracle agrees with the verifier, and the extra tuning did not overfit.**
   - Oracle scores: B-final 90 %, B with schema notes only 85 %, Run C 38 %.
   - The +5 pp from tuning shows on both splits but is 3 items, within replay's measured run-to-run noise (3.3 pp).
3. **The C1 threshold has to come from measured noise.**
   - Three identical baselines differed by 3.3 pp; 3 items flip from run to run.
   - On 60 questions, the initially planned C1 of "≥ baseline − 1 pp" would reject a correct fix after a single unlucky flip.
   - So C1 is the baseline mean − max(1 pp, spread) = 0.811 (≥ 49/60). This deliberate deviation from the initial plan was made from the baselines, before the fault and before any run, and is recorded in `prompts/verifier.md`.
   - C2 keeps zero tolerance, because control was 20/20 in every baseline.
4. **Control must be clean in text, not only in gold SQL.** As first built, q724 was in control: its gold SQL avoided the renamed columns, but its evidence said "refers to power_name". I replaced it before the baseline.
5. **Criterion wording bug (C4).** "`git status` lists only `workspace/`" fails on Nerve's own untracked `.nerve-review/`. This happened in Run B iteration 1 (the implementer then added it to `.git/info/exclude`) and in Run C. Run C would have been rejected anyway on C1 and C2. Fix: exclude `.nerve-review/` in the criterion, or in `make_loop_repo.sh`.
6. **Run C is a clean negative.** The general instructions, including "map evidence names to existing columns", cannot recover names that are absent from the agent's schema reference: SQL errors stayed at 35/60. The verifier rejected it with its own run. Nerve parked the loop at max_iterations, and the driver abandoned it.

**Gaps / caveats.**
- Isolation is by instruction plus C4 plus the oracle. The legs have a shell, so `agent/` and the oracle file are readable on disk.
- The replay dataset exposes expected SQL, as real Langfuse datasets do. A workspace that memorised it would pass C1 and be caught only by the oracle.
- Each run happened once (n = 1 for B and C). No LLM-as-judge score: skipped to stay within the time-box, since exec_match alone was discriminating.
- Langfuse v4 ("events_only") turns off the legacy read APIs (`/datasets/*/runs`, `/scores`). The MCP uses `/api/public/experiments` and `/experiment-items`.

Evidence: `evidence/` contains:
- `run-b/` and `run-c/`: leg transcripts, `verdict-iter*.json`, STATE.md, `workspace.diff`;
- `scores_timeline.png`, `summary.png` and `scores_table.md`;
- `baseline.json` and `post-fault.json`;
- `oracle-scores.json`: summaries only, no per-item SQL.
