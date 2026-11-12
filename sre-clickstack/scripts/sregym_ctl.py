"""Drive one SREGym problem without an agent: deploy / inject / oracle / recover.

Uses SREGym as a library (no changes to the sregym package). Run from the repo:

    cd vendor/SREGym
    SREGYM_PROFILE=svelte uv run python ../../sre-clickstack/scripts/sregym_ctl.py deploy
    uv run python ../../sre-clickstack/scripts/sregym_ctl.py inject
    uv run python ../../sre-clickstack/scripts/sregym_ctl.py oracle      # mitigation oracle -> JSON
    uv run python ../../sre-clickstack/scripts/sregym_ctl.py recover     # undo the fault (demo reset)

Every subcommand appends a timestamped line to sre-clickstack/runs/timeline.log (gitignored) so the
injection / mitigation times used as telemetry baselines are recorded. The recorded runs' events are in
evidence/timeline.log, which is not written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

PROBLEM_ID = os.environ.get("DEMO_PROBLEM", "env_variable_shadowing_astronomy_shop")
NAMESPACE = "astronomy-shop"
DEMO_DIR = Path(__file__).resolve().parent.parent
TIMELINE = DEMO_DIR / "runs" / "timeline.log"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def mark(event: str, **extra) -> None:
    TIMELINE.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts_utc": now(), "event": event, "problem": PROBLEM_ID, **extra})
    with TIMELINE.open("a") as fh:
        fh.write(line + "\n")
    print(f"[timeline] {line}")


def problem_instance():
    from sregym.conductor.problems.registry import ProblemRegistry

    return ProblemRegistry().get_problem_instance(PROBLEM_ID)


def cmd_deploy(_args) -> None:
    from sregym.conductor.conductor import Conductor, ConductorConfig

    mark("deploy_start")
    conductor = Conductor(ConductorConfig(deploy_loki=False))
    problem = problem_instance()
    conductor.problem = problem
    conductor.app = problem.app
    conductor.deploy_app()
    mark("deploy_done")


def cmd_inject(_args) -> None:
    problem = problem_instance()
    mark("inject_start")
    problem.inject_fault()
    mark("inject_done")


def cmd_oracle(_args) -> None:
    problem = problem_instance()
    result = problem.mitigation_oracle.evaluate()
    mark("oracle", result=result)
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("success") else 1)


def _kubectl_json(*args: str) -> dict:
    return json.loads(subprocess.check_output(["kubectl", *args, "-o", "json"]))


def cmd_recover(_args) -> None:
    """Demo reset.

    env_variable_shadowing: drop the shadowing FRONTEND_HOST entries directly (SREGym's own
    recover_fault needs the in-memory baseline captured by the injecting process).
    Other problems (e.g. internal_traffic_policy_local): their recover_fault is stateless
    (restore the Service policy, clear the nodeSelectors), so call it.
    """
    if PROBLEM_ID != "env_variable_shadowing_astronomy_shop":
        problem_instance().recover_fault()
        mark("recover_done")
        return
    dep = _kubectl_json("get", "deployment", "frontend-proxy", "-n", NAMESPACE)
    containers = dep["spec"]["template"]["spec"]["containers"]
    idx = next(i for i, c in enumerate(containers) if c["name"] == "frontend-proxy")
    env = containers[idx].get("env", [])
    ops = [
        {"op": "remove", "path": f"/spec/template/spec/containers/{idx}/env/{i}"}
        for i in reversed(range(len(env)))
        if env[i].get("name") == "FRONTEND_HOST" and env[i].get("value") == "localhost"
    ]
    if not ops:
        print("nothing to recover")
        return
    subprocess.check_call(
        ["kubectl", "patch", "deployment", "frontend-proxy", "-n", NAMESPACE, "--type=json", "-p", json.dumps(ops)]
    )
    subprocess.check_call(
        ["kubectl", "rollout", "status", "deployment/frontend-proxy", "-n", NAMESPACE, "--timeout=180s"]
    )
    mark("recover_done")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in [("deploy", cmd_deploy), ("inject", cmd_inject), ("oracle", cmd_oracle), ("recover", cmd_recover)]:
        sub.add_parser(name).set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
