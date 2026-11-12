"""Tiny Nerve REST client for the demo (stdlib only).

    python3 sre-clickstack/scripts/nerve_api.py chat  --title T --message-file prompt.md --out evidence/x.md
    python3 sre-clickstack/scripts/nerve_api.py loop  --goal-file goal.md --verifier-file criteria.md --budget 8 --out evidence/dir
    python3 sre-clickstack/scripts/nerve_api.py loop ... --wait [--abandon-on-park]   # block, then collect evidence
    python3 sre-clickstack/scripts/nerve_api.py collect --loop-id ID --out dir --cwd loopdir
    python3 sre-clickstack/scripts/nerve_api.py loop-status --loop-id ID
    python3 sre-clickstack/scripts/nerve_api.py messages --session-id ID --out file.md

Token: NERVE_TOKEN in sre-clickstack/.env (obtained via POST /api/auth/login on a passwordless install).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8900"


def env() -> dict:
    out = {}
    for line in (DEMO / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def call(method: str, path: str, body: dict | None = None, timeout: int = 1800):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {env()['NERVE_TOKEN']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def render_messages(session_id: str) -> str:
    msgs = call("GET", f"/api/sessions/{session_id}/messages?limit=1000")
    items = msgs.get("messages", msgs) if isinstance(msgs, dict) else msgs
    lines = []
    for m in items:
        blocks = m.get("blocks")
        if isinstance(blocks, str):
            blocks = json.loads(blocks)
        lines.append(f"### {m.get('role', '?')} — {m.get('created_at', '')}\n")
        if not blocks:
            lines.append(f"{m.get('content', '')}\n")
            continue
        for b in blocks:
            t = b.get("type")
            if t == "text":
                lines.append(b.get("content") or b.get("text") or "")
            elif t == "tool_call":
                res = b.get("result") or ""
                try:
                    parsed = json.loads(res)
                    if isinstance(parsed, list):
                        res = "\n".join(x.get("text", "") for x in parsed if isinstance(x, dict))
                except Exception:
                    pass
                lines.append(
                    f"**tool `{b.get('tool')}`**\n```json\n{json.dumps(b.get('input'), indent=2)[:3000]}\n```\n"
                    f"<details><summary>result{' (error)' if b.get('is_error') else ''}</summary>\n\n```\n{str(res)[:3000]}\n```\n</details>\n"
                )
        lines.append("")
    return "\n".join(lines)


def cmd_chat(a):
    msg = Path(a.message_file).read_text() if a.message_file else a.message
    sid = call("POST", "/api/sessions", {"title": a.title})["id"]
    t0 = time.time()
    print(f"[{utc()}] session {sid} started")
    resp = call("POST", "/api/chat", {"session_id": sid, "message": msg}, timeout=3600)
    dur = time.time() - t0
    print(f"[{utc()}] done in {dur:.0f}s")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"# {a.title}\n\n- session: `{sid}`\n- wall time: {dur:.0f} s\n- finished: {utc()} UTC\n\n"
        f"## Prompt\n\n{msg}\n\n## Final answer\n\n{resp.get('response')}\n\n## Full transcript\n\n{render_messages(sid)}"
    )
    print(resp.get("response", "")[:3000])


def cmd_loop(a):
    body = {
        "title": a.title,
        **({"cwd": a.cwd} if a.cwd else {}),
        "review_loop": {
            "goal": Path(a.goal_file).read_text(),
            "verifier": Path(a.verifier_file).read_text(),
            "budget_usd": a.budget,
            **({"max_iterations": a.max_iterations} if a.max_iterations else {}),
            "implementer": {"engine": "claude-workflow"},
            "verifier_leg": {"engine": a.verifier_engine},
        },
    }
    resp = call("POST", "/api/sessions", body)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "create-response.json").write_text(json.dumps(resp, indent=2))
    print(json.dumps(resp, indent=2)[:2000])
    if a.wait:
        collect(resp["review_loop_id"], out, a.cwd, abandon_on_park=a.abandon_on_park)


TERMINAL = {"passed", "failed", "awaiting_user", "abandoned", "killed", "cancelled", "budget_exhausted", "error"}


def collect(
    loop_id: str, out: Path, cwd: str | None, poll: int = 30, abandon_on_park: bool = False, max_wait_s: int = 2 * 3600
) -> dict:
    """Block until the loop settles (or max_wait_s), then save loop-final.json, verdicts, STATE.md, transcripts."""
    out.mkdir(parents=True, exist_ok=True)
    last = None
    deadline = time.time() + max_wait_s
    while True:
        if time.time() > deadline:
            print(f"[{utc()}] {loop_id}: gave up waiting after {max_wait_s}s")
            st = call("GET", f"/api/review-loops/{loop_id}")
            status = st["loop"]["status"]
            break
        try:
            st = call("GET", f"/api/review-loops/{loop_id}")
        except Exception as e:  # daemon reload / transient
            print(f"[{utc()}] status error: {e}")
            time.sleep(poll)
            continue
        status = st["loop"]["status"]
        if status != last:
            print(
                f"[{utc()}] {loop_id}: {status} (iteration {st['loop'].get('iteration')}, ${st['loop'].get('spent_usd')})",
                flush=True,
            )
            last = status
        if status in TERMINAL or st["loop"].get("ended_at"):
            break
        time.sleep(poll)
    if status == "awaiting_user" and abandon_on_park:
        (out / "loop-parked.json").write_text(json.dumps(st, indent=2))
        call("POST", f"/api/review-loops/{loop_id}/decision", {"decision": "abandon"})
        print(f"[{utc()}] {loop_id}: abandoned (parked at max_iterations)")
    (out / "loop-final.json").write_text(json.dumps(st, indent=2))
    for att in st.get("attempts", []):
        role, it, run = att["role"], att["iteration"], att.get("run_id")
        if role == "verifier" and att.get("verdict") is not None:
            v = att["verdict"]
            v = json.loads(v) if isinstance(v, str) else v
            (out / f"verdict-iter{it}.json").write_text(json.dumps(v, indent=2))
        if run:
            try:
                (out / f"{role}-leg-{it}.md").write_text(render_messages(f"workflow:{run}"))
            except Exception as e:
                print(f"transcript {run}: {e}")
    try:
        (out / "observer.md").write_text(render_messages(st["loop"]["session_id"]))
    except Exception as e:
        print(f"observer transcript: {e}")
    if cwd:
        for f in Path(cwd).glob(f".nerve-review/{loop_id}/STATE.md"):
            (out / "STATE.md").write_text(f.read_text())
        for f in Path(cwd).glob(".nerve-review/*/STATE.md"):
            if not (out / "STATE.md").exists():
                (out / "STATE.md").write_text(f.read_text())
    print(f"[{utc()}] collected into {out}")
    return st


def cmd_collect(a):
    collect(a.loop_id, Path(a.out), a.cwd, abandon_on_park=a.abandon_on_park)


def cmd_loop_status(a):
    print(json.dumps(call("GET", f"/api/review-loops/{a.loop_id}"), indent=2))


def cmd_messages(a):
    Path(a.out).write_text(render_messages(a.session_id))
    print(f"wrote {a.out}")


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    c = s.add_parser("chat")
    c.add_argument("--title", required=True)
    c.add_argument("--message")
    c.add_argument("--message-file")
    c.add_argument("--out", required=True)
    c.set_defaults(fn=cmd_chat)
    l = s.add_parser("loop")
    l.add_argument("--title", default="review loop")
    l.add_argument("--goal-file", required=True)
    l.add_argument("--verifier-file", required=True)
    l.add_argument("--budget", type=float, default=8.0)
    l.add_argument("--max-iterations", type=int)
    l.add_argument("--cwd")
    l.add_argument("--verifier-engine", default="codex-ultracode")
    l.add_argument("--out", required=True)
    l.add_argument("--wait", action="store_true")
    l.add_argument("--abandon-on-park", action="store_true")
    l.set_defaults(fn=cmd_loop)
    co = s.add_parser("collect")
    co.add_argument("--loop-id", required=True)
    co.add_argument("--out", required=True)
    co.add_argument("--cwd")
    co.add_argument("--abandon-on-park", action="store_true")
    co.set_defaults(fn=cmd_collect)
    st = s.add_parser("loop-status")
    st.add_argument("--loop-id", required=True)
    st.set_defaults(fn=cmd_loop_status)
    m = s.add_parser("messages")
    m.add_argument("--session-id", required=True)
    m.add_argument("--out", required=True)
    m.set_defaults(fn=cmd_messages)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
