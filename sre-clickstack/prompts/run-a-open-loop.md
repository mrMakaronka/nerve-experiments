There is an incident in astronomy-shop. Diagnose the root cause using telemetry.

This is a DIAGNOSIS-ONLY request: do not run any mutating command (no kubectl
set/patch/apply/edit/rollout/scale/delete). Read-only kubectl and ClickHouse
SELECT queries only.

Report: the faulty component, the mechanism, and the exact SQL queries + returned
numbers that support it. Distinguish the root-cause component from symptom
services. Finish with the fix you would apply (but do not apply it).
