"""Tee SREGym's central OTel collector (namespace `observe`) into ClickStack.

Adds an `otlphttp/clickstack` exporter to the otel-collector-config ConfigMap and
appends it to the `traces` and `traces/otlp` pipelines. Jaeger / Prometheus
exporters are left untouched. Idempotent. Restarts the collector.

    uv run --project vendor/SREGym python sre-clickstack/scripts/tee-collector.py [--endpoint URL]

Endpoint default: http://host.docker.internal:4318 (Docker Desktop). On Linux use
the kind network gateway, e.g. `docker network inspect kind` -> IPAM gateway.
The ClickStack ingestion key is read from sre-clickstack/.env.
"""

import argparse
import json
import subprocess
from pathlib import Path

import yaml

DEMO = Path(__file__).resolve().parent.parent
NS, CM, KEY = "observe", "otel-collector-config", "config.yaml"
EXPORTER = "otlphttp/clickstack"


def env_file() -> dict:
    out = {}
    for line in (DEMO / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://host.docker.internal:4318")
    args = ap.parse_args()
    ingest_key = env_file()["CLICKSTACK_INGESTION_API_KEY"]

    cm = json.loads(subprocess.check_output(["kubectl", "get", "cm", CM, "-n", NS, "-o", "json"]))
    cfg = yaml.safe_load(cm["data"][KEY])
    cfg["exporters"][EXPORTER] = {
        "endpoint": args.endpoint,
        "tls": {"insecure": True},
        "headers": {"authorization": ingest_key},
        "compression": "gzip",
        "sending_queue": {"enabled": True, "queue_size": 5000},
        "retry_on_failure": {"enabled": True},
    }
    for pipeline in ("traces", "traces/otlp"):
        exporters = cfg["service"]["pipelines"][pipeline]["exporters"]
        if EXPORTER not in exporters:
            exporters.append(EXPORTER)

    patch = {"data": {KEY: yaml.safe_dump(cfg, sort_keys=False)}}
    subprocess.check_call(["kubectl", "patch", "cm", CM, "-n", NS, "--type=merge", "-p", json.dumps(patch)])
    subprocess.check_call(["kubectl", "rollout", "restart", "deployment/otel-collector", "-n", NS])
    subprocess.check_call(["kubectl", "rollout", "status", "deployment/otel-collector", "-n", NS, "--timeout=120s"])
    print(f"collector now tees traces to {args.endpoint}")


if __name__ == "__main__":
    main()
