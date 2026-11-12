The text2sql agent's answer quality dropped. The agent is a single-shot text-to-SQL agent over the
`superhero` SQLite DB, traced and scored in the Langfuse project `text2sql`. Use Langfuse scores
(`langfuse-tools` MCP; `skill_get langfuse-schema`) to see the drop between runs `baseline` and
`post-fault`.

Constraint for this task: the only change you may make is to **append general instructions to
the end of `workspace/prompt.md`**. General means instructions about how to write SQL or how to
reason, with no table names, no column names and no schema facts. Do not edit `schema_notes.md`
or `skills/`, and do not call `describe_live_db`. Commit the change with git.

Then run `run_experiment` on this workspace. Report its numbers in
`.nerve-review/<loop>/STATE.md` as your unverified claim, together with your assessment of
whether the change fixes the regression.
