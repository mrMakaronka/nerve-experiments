# Pinned upstreams

Upstream sources are **not** vendored or included as submodules. Each case clones them into `vendor/` (gitignored) at the commits below. `sre-clickstack/scripts/up.sh` and `agent-quality-langfuse/scripts/langfuse-up.sh` do this automatically. These are the commits that the recorded runs used.

| Upstream | Repository | Pin | Used by |
|---|---|---|---|
| Nerve | https://github.com/ClickHouse/nerve | `4173725dc2723ee9e3b41c05522f695ba72e6b1d` | all cases (review loop, gateway on 127.0.0.1:8900) |
| SREGym | https://github.com/SREGym/SREGym | `ef444ee65f763154c29d0b95f89a4f1e4c2ac2e0` (submodule `SREGym-applications` at `7d00a9773d93f94d9612512dfa2a25fb0abdbe6d`) | sre-clickstack |
| Langfuse (docker compose) | https://github.com/langfuse/langfuse | `4fe6ebf6a04191f90e89cdff646535cce2a9c46d`; images `langfuse:4` / `langfuse-worker:4`, web reported v4.77.0 | agent-quality-langfuse |
| mcp-clickhouse | PyPI `mcp-clickhouse` | `0.7.0` (resolved by `uv run --with mcp-clickhouse`; clickhouse-perf pins `mcp-clickhouse==0.7.0`) | sre-clickstack, clickhouse-perf (and listed in the agent-quality Nerve config) |
| ClickStack all-in-one | Docker Hub `clickhouse/clickstack-all-in-one` | `sha256:6804421d79acea32cf42c93171df0e82df081a0c96af3f3743e91d6185d26a54` (pulled as `latest`; `clickstack-up.sh` now uses the digest) | sre-clickstack |
| ClickHouse server | Docker Hub `clickhouse/clickhouse-server` | `26.8.36.3@sha256:d426d2f612e1e189c90f9a3f8dcd85a03c6851273833817a296bb327e63aa7a7` | clickhouse-perf |
| ClickBench | https://github.com/ClickHouse/ClickBench | `3e064d9` (official `hits` DDL and the 43 queries); data: the 100 partitioned `hits_*.parquet` files, 14,737,666,736 bytes in total | clickhouse-perf |
| Codex CLI | npm `@openai/codex` | `0.164.0` | verifier, all cases |
| BIRD dev | https://bird-bench.github.io (dev set, `dev_20240627`) | `superhero` database | agent-quality-langfuse |

Manual equivalent:

```bash
git clone https://github.com/ClickHouse/nerve.git vendor/nerve && git -C vendor/nerve checkout 4173725dc2723ee9e3b41c05522f695ba72e6b1d
git clone https://github.com/SREGym/SREGym.git vendor/SREGym && git -C vendor/SREGym checkout ef444ee65f763154c29d0b95f89a4f1e4c2ac2e0 \
  && git -C vendor/SREGym submodule update --init --recursive
git clone https://github.com/langfuse/langfuse vendor/langfuse && git -C vendor/langfuse checkout 4fe6ebf6a04191f90e89cdff646535cce2a9c46d
# BIRD: unpack the dev set so that vendor/bird/dev_20240627/dev_databases/superhero/superhero.sqlite exists
```
