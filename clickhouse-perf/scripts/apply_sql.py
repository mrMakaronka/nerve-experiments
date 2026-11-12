"""apply_sql.py FILE [--user U]: strip -- comments, fill {{NAME}} from ~/nerve-demo-private/v4/.env (CH_<NAME>_PASSWORD),
run statement by statement via scripts/ch.sh. Prints only the first words of each statement (never secrets)."""
import os, re, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
env = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/nerve-demo-private/v4/.env")) if "=" in l)
src = open(sys.argv[1]).read()
src = re.sub(r"--[^\n]*", "", src)
src = re.sub(r"\{\{(\w+)\}\}", lambda m: env[f"CH_{m.group(1)}_PASSWORD"], src)
extra = sys.argv[2:]
ok = True
for st in [s.strip() for s in src.split(";") if s.strip()]:
    r = subprocess.run([os.path.join(here, "ch.sh"), *extra, st], capture_output=True, text=True)
    head = " ".join(st.split()[:6])
    print(("OK  " if r.returncode == 0 else "ERR ") + head, (r.stdout.strip()[:300] if r.returncode else ""))
    ok &= r.returncode == 0
sys.exit(0 if ok else 1)
