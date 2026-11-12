"""Shared paths/clients for the demo-v3 text-to-SQL agent (demo code; not visible to the Nerve implementer)."""
import os
from pathlib import Path

V3 = Path(__file__).resolve().parent.parent
DB = V3 / "data/superhero.sqlite"
FAULT = V3 / "data/fault.json"
ORACLE = Path.home() / "nerve-demo-private/v3/oracle.jsonl"
MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10e-6, 0.50e-6   # USD/token, Haiku 5.5 list price (<=100K prompt)


def load_env():
    """demo-v3/.env (Langfuse) first; ANTHROPIC_API_KEY may also live in demo/.env. Both gitignored."""
    for f, only in ((V3 / ".env", None), (V3.parent / ".env", {"ANTHROPIC_API_KEY"})):
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                k = k.strip().removeprefix("export ").strip()
                if only is None or k in only:
                    os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def langfuse_client():
    load_env()
    from langfuse import Langfuse
    return Langfuse(public_key=os.environ["LANGFUSE_PUBLIC_KEY"], secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                    host=os.environ["LANGFUSE_HOST"])
