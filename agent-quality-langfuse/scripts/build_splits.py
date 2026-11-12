"""One-off build step (run BEFORE any fault): pick 120 BIRD `superhero` questions, split them, write the
agent's schema snapshot, upload `replay` to Langfuse, keep `oracle` outside the repo.

    agent-quality-langfuse/.venv/bin/python agent-quality-langfuse/scripts/build_splits.py [--check] [--no-langfuse]

Safe to re-run. The split is deterministic (seed 20261110), so every output is recomputed and then:
  - tracked files (data/replay.jsonl, agent/schema_snapshot.md) are compared, never overwritten. A difference
    means a different BIRD copy or code; the script stops. schema_snapshot.md is part of the agent fingerprint
    quoted in the verifier criteria, so it must stay byte-identical;
  - local files are written only if missing. data/superhero.sqlite is never reset here, because inject.py mutates
    it; use `scripts/inject.py --kind recover` for that;
  - the Langfuse dataset `replay` is created and filled only if it does not exist yet. If it exists with all 60
    items, it is left alone (inject.py rewrites the items' expected SQL after the fault).
--check compares and reports without writing anything; --no-langfuse skips the Langfuse step.

Outputs
  data/superhero.sqlite          live DB the agent queries (inject.py mutates it)
  data/superhero.pristine.sqlite untouched copy (recover)
  data/replay.jsonl              60 items, 20 with control=true   (also Langfuse dataset `replay`)
  data/gold_original.json        qid -> original gold SQL (inject.py regenerates gold from this)
  agent/schema_snapshot.md       schema doc the agent is prompted with (frozen at build time)
  ~/nerve-demo-private/v3/oracle.jsonl  60 hidden items (never uploaded, never in the repo)
"""

import argparse
import csv
import json
import random
import re
import shutil
import sqlite3
import sys
from pathlib import Path

V3 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V3 / "agent"))
from common import ORACLE, langfuse_client

BIRD = V3.parent / "vendor/bird/dev_20240627"
SRC = BIRD / "dev_databases/superhero"
# Columns the schema-change fault will rename (fixed before the split so `control` can be chosen).
FAULT_COLS = ["full_name", "height_cm", "publisher_name", "power_name"]

ap = argparse.ArgumentParser()
ap.add_argument("--check", action="store_true", help="compare outputs with what exists; write nothing")
ap.add_argument("--no-langfuse", action="store_true", help="skip creating/filling the Langfuse dataset")
args = ap.parse_args()
if not (BIRD / "dev.json").exists() or not (SRC / "superhero.sqlite").exists():
    sys.exit(f"BIRD dev not found under {BIRD} (see README.md, Prerequisites)")

qs = [q for q in json.load(open(BIRD / "dev.json")) if q["db_id"] == "superhero"]
rnd = random.Random(20261110)
rnd.shuffle(qs)
qs = qs[:120]
aff = lambda q: any(re.search(rf"\b{c}\b", q["SQL"], re.IGNORECASE) for c in FAULT_COLS)
A, U = [q for q in qs if aff(q)], [q for q in qs if not aff(q)]
# stratified halves: same affected/unaffected mix in replay and oracle
ka, ku = (len(A) + 1) // 2, len(U) // 2  # odd counts: the extra affected item goes to replay
replay = A[:ka] + U[:ku]
oracle = A[ka:] + U[ku:]
assert len(replay) == 60 and len(oracle) == 60, (len(replay), len(oracle))
# control = the regression gate: untouched by the fault in gold SQL *and* in question/evidence text
# (q724's evidence says "refers to power_name": the agent would follow it into the renamed column)
mentions = lambda q: any(re.search(rf"\b{c}\b", q["question"] + " " + q["evidence"], re.IGNORECASE) for c in FAULT_COLS)
control_ids = {q["question_id"] for q in [q for q in U[:ku] if not mentions(q)][:20]}
assert len(control_ids) == 20
print(f"affected {len(A)} / unaffected {len(U)}; replay affected {sum(map(aff, replay))}, control {len(control_ids)}")

problems = []


def tracked(path, text):
    """Recorded artifact: compare, never overwrite."""
    if not path.exists():
        problems.append(f"MISSING tracked file {path.relative_to(V3)}; restore it from git, do not regenerate it")
    elif path.read_text() != text:
        problems.append(f"DIFFERS {path.relative_to(V3)}: recomputed content does not match the recorded file")
    else:
        print(f"ok        {path.relative_to(V3)} (matches the recorded file)")


def local(path, write, same=None, mode=None):
    """Local derived file: create if missing; if present, keep it (and compare when a check is given)."""
    if path.exists():
        if same is not None and not same(path):
            problems.append(f"DIFFERS {path}: existing local file does not match the recomputed content")
        else:
            print(f"keep      {path}")
        return
    if args.check:
        print(f"would write {path}")
        return
    write(path)
    if mode is not None:
        path.chmod(mode)
    print(f"wrote     {path}")


local(V3 / "data/superhero.pristine.sqlite", lambda p: shutil.copy(SRC / "superhero.sqlite", p))
local(V3 / "data/superhero.sqlite", lambda p: shutil.copy(SRC / "superhero.sqlite", p))


def item(q):
    return {
        "id": f"q{q['question_id']}",
        "input": {"question": q["question"], "evidence": q["evidence"]},
        "expected_output": {"sql": q["SQL"]},
        "metadata": {
            "question_id": q["question_id"],
            "difficulty": q["difficulty"],
            "control": q["question_id"] in control_ids,
        },
    }


replay_text = "".join(json.dumps(item(q)) + "\n" for q in replay)
oracle_text = "".join(json.dumps(item(q)) + "\n" for q in oracle)
gold_text = json.dumps({f"q{q['question_id']}": q["SQL"] for q in qs}, indent=1)
tracked(V3 / "data/replay.jsonl", replay_text)
if not args.check:
    ORACLE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)  # outside the repo, operator-only
    ORACLE.parent.chmod(0o700)
local(ORACLE, lambda p: p.write_text(oracle_text), same=lambda p: p.read_text() == oracle_text, mode=0o600)
local(V3 / "data/gold_original.json", lambda p: p.write_text(gold_text), same=lambda p: p.read_text() == gold_text)

# Schema snapshot: DDL + BIRD column descriptions, as a data team would publish it.
con = sqlite3.connect(SRC / "superhero.sqlite")
out = ["# superhero database: schema reference", "", "SQLite. Generated from the warehouse on 2026-11-10.", ""]
for t, ddl in con.execute("select name, sql from sqlite_master where type='table' order by name"):
    out += [f"## {t}", "", "```sql", ddl.strip(), "```", ""]
    p = SRC / "database_description" / f"{t}.csv"
    if p.exists():
        rows = list(csv.DictReader(p.open(encoding="utf-8-sig", errors="replace")))
        for r in rows:
            desc = " ".join((r.get("column_description") or "").split())
            vd = " ".join((r.get("value_description") or "").split())
            out.append(f"- `{r['original_column_name'].strip()}`: {desc}" + (f" ({vd[:160]})" if vd else ""))
        out.append("")
tracked(V3 / "agent/schema_snapshot.md", "\n".join(out))

if problems:
    print("\n".join(problems), file=sys.stderr)
    sys.exit(2)
if args.check or args.no_langfuse:
    print("Langfuse step skipped (--check / --no-langfuse)")
    sys.exit(0)

from langfuse.api import NotFoundError

lf = langfuse_client()
want = {f"q{q['question_id']}" for q in replay}
try:
    have = {i.id for i in lf.get_dataset("replay").items}
except NotFoundError:
    have = None
    print("Langfuse dataset `replay` not found; creating it")
if have is not None and want <= have:
    print(f"Langfuse dataset `replay` already initialized ({len(have)} items); left unchanged")
    sys.exit(0)
if have is not None:
    print(f"Langfuse dataset `replay` is incomplete ({len(want & have)}/60); adding the missing items")
else:
    lf.create_dataset(
        name="replay",
        description="60 BIRD superhero questions; metadata.control marks the 20-item regression gate",
        metadata={"source": "BIRD dev 20240627", "db": "superhero"},
    )
for q in replay:
    it = item(q)
    if have is not None and it["id"] in have:
        continue
    lf.create_dataset_item(
        dataset_name="replay",
        id=it["id"],
        input=it["input"],
        expected_output=it["expected_output"],
        metadata=it["metadata"],
    )
lf.flush()
print("Langfuse dataset `replay`:", len(want - (have or set())), "items added | oracle at", ORACLE)
