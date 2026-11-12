# STATE — review loop rvl-87f3dbe9 (implementer, iteration 3 of 3, final)

Loop base commit: `71d6c39` (baseline workspace). HEAD: **`b4db62e`**. Iteration 3 adds one commit.
Agent fingerprint (combined), read in this leg: `5ea3649966c584af97a6b39cdd7d3358375ba9fc0a63a054bae15ac2550a37f1`. It is unchanged; I did not touch the system under test.

## Done

### Root cause (found in iteration 1; still holds)
**A live schema change, not a model change.** Four columns in the live `superhero` DB were renamed. The agent kept using the old names, taken from the frozen schema reference and from the analysts' `evidence` strings. Its queries then failed with `OperationalError: no such column`.

| old name (frozen ref / evidence) | live name (`describe_live_db`) |
|---|---|
| `superhero.full_name` | `superhero.civilian_name` |
| `superhero.height_cm` | `superhero.stature_cm` |
| `publisher.publisher_name` | `publisher.imprint` |
| `superpower.power_name` | `superpower.ability` |

Evidence (from `get_failed_traces`, iteration 1):
- `post-fault` had 36 failures. In 35 of them the error was `no such column` on one of the four names. Examples:
  - trace `38683c222182de3419e1ef3d0ecb8708` (q717): `T3.power_name`;
  - trace `9b2467b33b7c166762f64adb1fa81b65` (q731): `p.publisher_name`.
- `baseline` had 10 failures and 0 SQL errors.

### C2 fix in iteration 3 (q837 flakiness)
`get_failed_traces` on `verifier-rvl-87f3dbe9-iter2` and on `impl-rvl87f3-iter2-ties-1` showed two cases:
- The expected SQL uses `ORDER BY … LIMIT 1` when the question asks **who/which entity** (by name):
  - q794 "Which hero was the fastest?" (control);
  - q802 "Who is the tallest superhero?";
  - q741 "name of the superhero that has the most powers".
- The expected SQL uses `WHERE col = (SELECT MIN(col) …)`, which returns every tied row, when the question asks for **IDs of rows in a per-measurement table**:
  - q837 "hero ID … lowest attribute value" (control), on `hero_attribute`.

Without guidance the agent picked either form at random, so both q837 and q802 flipped between runs. The superlative rule I added makes the form follow the output the question asks for. The rule is generic: it contains no per-question answers or expected SQL.

### Diff (`git diff 71d6c39..HEAD`)
```diff
--- a/workspace/prompt.md
+++ b/workspace/prompt.md
@@ -4,4 +4,8 @@
 - Use only tables and columns that exist in the schema.
 - Return only the columns the question asks for, in the order asked.
+- Do not add filters the question or evidence does not ask for (e.g. do not exclude NULL or 0 values).
+- Superlatives (highest, lowest, most, tallest, fastest, ...):
+  - asking who/which entity (a name): `ORDER BY <measure> DESC|ASC LIMIT 1`;
+  - asking for IDs of rows in a per-measurement table (e.g. `hero_attribute`) at the minimum/maximum value: return every such row with `WHERE <col> = (SELECT MIN|MAX(<col>) FROM ...)`.
 - Put the final query in a single ```sql code block. No explanation is needed.
--- a/workspace/schema_notes.md
+++ b/workspace/schema_notes.md
@@ -1 +1,14 @@
-<!-- Notes about the live schema that the frozen schema reference does not reflect yet. Empty at baseline. -->
+# Live schema renames (override the frozen schema reference and the evidence)
+
+Four columns were renamed. The old names no longer exist; analyst evidence may still use them. Always write the new name:
+
+| old name (do not use) | live name |
+|---|---|
+| `superhero.full_name` | `superhero.civilian_name` |
+| `superhero.height_cm` | `superhero.stature_cm` |
+| `publisher.publisher_name` | `publisher.imprint` |
+| `superpower.power_name` | `superpower.ability` |
+
+Values and meaning are unchanged (e.g. "full name" = `civilian_name`, "height" = `stature_cm`, "publisher name" = `imprint`, "power/superpower" = `ability`).
+
+Names in `superpower.ability` and `attribute.attribute_name` are stored in Title Case (e.g. 'Super Strength', 'Speed'); evidence sometimes quotes them in lower case, so write them in Title Case.
```

### My runs (UNVERIFIED IMPLEMENTER CLAIM; values returned by `run_experiment` in this leg, on workspace = HEAD `b4db62e`)
Thresholds:
- C1: exec ≥ 0.8110
- C2: control ≥ 1.0
- C3: cost ≤ 0.000362 (1.2 × 0.000302) and p50 ≤ 1.485 s (1.5 × 0.990)

| run | exec | control | cost/q | p50 s | sql_errors |
|---|---|---|---|---|---|
| `impl-rvl87f3-iter3-superl-1` | 0.9333 | 1.0 (20/20) | 0.000346 | 1.080 | 0 |
| `impl-rvl87f3-iter3-superl-2` | 0.9333 | 1.0 (20/20) | 0.000349 | 1.022 | 0 |

In superl-1 four items failed, none of them control: q741, q798, q805, q835. All four also fail at baseline. q837 and q802 now pass.

Scope, checked after the commit:
- `git diff --stat 71d6c39..HEAD` shows only `workspace/prompt.md` and `workspace/schema_notes.md`.
- `git status --porcelain` is empty. `.nerve-review/` is listed in `.git/info/exclude`, which is local repo config and is not tracked.

## In progress
- Nothing.

## Key decisions
- I chose a superlative rule keyed on the output the question asks for (an entity name or row IDs), not a global "always return ties" rule. The iteration-2 global tie rule fixed q837 but broke q794 and q802.
- The rule is phrased as a generic SQL convention. It contains no per-question SQL.

## Next steps
- Verifier: replay `verifier-…` on `$HOME/nerve-v3-loops/run-b/workspace` at HEAD `b4db62e`.

## Open questions / known gaps
- Cost headroom is small: 0.000346–0.000349 against a limit of 0.000362, about 4% margin. The longer prompt adds roughly 5% per question.
- The agent is still stochastic. In 2 runs out of 2, control was 20/20, but a single unlucky sample cannot be ruled out.
- On held-out data, a "who/which" superlative whose expected SQL returns all tied rows would be steered to LIMIT 1. In the replay set the expected SQL follows the convention in the rule.
