---
name: Langfuse text2sql project (scores, runs, datasets)
description: >
  What the self-hosted Langfuse project `text2sql` contains and how to read it with the
  `langfuse-tools` MCP tools: the `replay` dataset and its `control` subset, the score names
  and their meaning, experiment runs, failed-trace inspection, live DB schema. Use before
  reading or comparing any agent-quality numbers.
version: 1.0.0
context: domain
---

# Langfuse `text2sql` project

**System under test.** A single-shot text-to-SQL agent (Claude Haiku) answers questions over the
SQLite database `superhero` (BIRD benchmark). For each question it sends one prompt and gets back
one SQL query. It does not retry, and it cannot look at the live schema. The prompt is assembled
from the files of a **workspace directory**:

| file | role |
|---|---|
| `prompt.md` | system instructions |
| `schema_notes.md` | notes on the live schema; the prompt says they override the frozen schema reference |
| `skills/*.md` | extra guidance, appended as `# Skill: <name>` |

The frozen schema reference and the agent code live outside the workspace. You cannot see or change them.

**Dataset `replay`.** It has 60 questions. Each item has:
- input `{question, evidence}`, where `evidence` is a hint written by an analyst;
- expected output `{sql}`;
- metadata `{question_id, difficulty, control}`.

The 20 items with `control = true` are the **regression gate**: a change must not make any of them worse.

**Scores.** Every experiment run writes these.

| score | level | meaning |
|---|---|---|
| `exec_match` | item | 1 if the generated SQL returns the same set of rows as the expected SQL on the live DB; else 0 (SQL errors are 0) |
| `cost_usd` | item | model cost of the call (input + output tokens at list price) |
| `latency_s` | item | wall time: model call + SQL execution |
| `exec_match_avg` | run | mean exec_match over the 60 items |
| `control_exec_match_avg` | run | mean exec_match over the 20 control items |
| `cost_per_q_usd`, `latency_avg_s`, `latency_p50_s` | run | cost and latency aggregates |

**Tools (`langfuse-tools` MCP).**
- `list_runs(limit)`: recent runs, newest first, with run-level scores. Named runs: `baseline`, `baseline-2`, `baseline-3` are three identical
  pre-incident runs (their spread is the noise floor); `post-fault` is right after the incident started.
- `get_run_scores(run_name)`: run scores, plus per-item scores and aggregates recomputed from the
  item scores, all read back from Langfuse. This is the authoritative way to read a run.
- `get_failed_traces(run_name, limit)`: the exec_match = 0 items, with question, evidence,
  generated SQL, SQLite error, expected SQL and trace id.
- `run_experiment(run_name, workspace_dir)`: replays all 60 items with the files in
  `workspace_dir`, which is an absolute path to the directory that holds `prompt.md`. It takes
  1–3 minutes and costs about $0.05. Run names must be new.
- `describe_live_db()`: the current columns of every table.
- `agent_fingerprint()`: a hash of the agent code and frozen reference. It is unchanged unless
  someone modified the system under test.

**Pitfalls.**
- exec_match is noisy by ±1–3 items between identical runs, because the model is sampled. Compare
  runs on the same dataset, and look at which items flipped, not only the averages.
- `evidence` strings are written by analysts against the schema *as it was when the question was
  written*. They can name columns that no longer exist.
