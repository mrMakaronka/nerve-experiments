"""Schema-change fault for demo-v3 (EvoSchema-style column renames, hand-rolled).

    .venv/bin/python scripts/inject.py --kind rename    # rename 4 columns in data/superhero.sqlite, regenerate gold SQL
    .venv/bin/python scripts/inject.py --kind recover   # restore pristine DB + original gold

The agent keeps prompting with the frozen agent/schema_snapshot.md, so it keeps writing the old names.
Gold SQL is regenerated for the new schema and checked to return exactly the pre-fault result set.
Replay gold is upserted into the Langfuse dataset `replay`; oracle gold goes into data/fault.json (local only).
"""

import argparse
import datetime
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

V3 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V3 / "agent"))
from common import DB, FAULT, ORACLE, langfuse_client

RENAMES = [  # (table, old, new)
    ("superhero", "full_name", "civilian_name"),
    ("superhero", "height_cm", "stature_cm"),
    ("publisher", "publisher_name", "imprint"),
    ("superpower", "power_name", "ability"),
]
PRISTINE = V3 / "data/superhero.pristine.sqlite"
ORIG = json.loads((V3 / "data/gold_original.json").read_text())


def rewrite(sql, renames):
    for _, old, new in renames:
        sql = re.sub(rf"\b{old}\b", new, sql, flags=re.IGNORECASE)
    return sql


def rows(db, sql):
    c = sqlite3.connect(db)
    try:
        return set(map(tuple, c.execute(sql).fetchall()))
    finally:
        c.close()


def upsert_replay(gold):
    lf = langfuse_client()
    for l in (V3 / "data/replay.jsonl").read_text().splitlines():
        it = json.loads(l)
        lf.create_dataset_item(
            dataset_name="replay",
            id=it["id"],
            input=it["input"],
            expected_output={"sql": gold[it["id"]]},
            metadata=it["metadata"],
        )
    lf.flush()


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--kind", choices=["rename", "recover"], required=True)
    kind = a.parse_args().kind
    if kind == "recover":
        shutil.copy(PRISTINE, DB)
        FAULT.unlink(missing_ok=True)
        upsert_replay(ORIG)
        print("recovered: pristine DB, original gold")
        return
    shutil.copy(PRISTINE, DB)
    c = sqlite3.connect(DB)
    for t, old, new in RENAMES:
        c.execute(f'ALTER TABLE "{t}" RENAME COLUMN "{old}" TO "{new}"')
    c.commit()
    c.close()
    gold, changed = {}, 0
    for qid, sql in ORIG.items():
        g = rewrite(sql, RENAMES)
        changed += g != sql
        assert rows(DB, g) == rows(PRISTINE, sql), f"gold mismatch after rewrite: {qid}"
        gold[qid] = g
    ids_oracle = [json.loads(l)["id"] for l in ORACLE.read_text().splitlines()]
    FAULT.write_text(
        json.dumps(
            {
                "kind": "rename",
                "renames": RENAMES,
                "injected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "oracle_gold": {k: gold[k] for k in ids_oracle},
            },
            indent=1,
        )
    )
    upsert_replay(gold)
    print(f"renamed {len(RENAMES)} columns; {changed}/{len(ORIG)} gold queries rewritten and verified equal")


main()
