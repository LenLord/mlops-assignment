# MLOps Assignment Report

## 1. Serving Configuration (Phase 1)

Model: `Qwen/Qwen3-30B-A3B-Instruct-2507` on 1× H100 80GB HBM3

| Flag | Value | Justification |
|------|-------|---------------|
| `--gpu-memory-utilization` | `0.92` | Leaves 8% headroom for CUDA kernels and driver overhead while maximising KV cache budget. |
| `--max-model-len` | `4096` | Workload prompts are 1.5–3K tokens with short SQL outputs; default 128K wastes ~30× more KV cache memory per slot than needed. |
| `--max-num-seqs` | `128` | Caps concurrent sequences to bound worst-case KV pressure; prevents cache evictions under burst load. |
| `--enable-prefix-caching` | — | Every request carries the same DB schema in the system prompt; prefix caching reuses those KV blocks across requests, cutting TTFT significantly after the first request. |
| `--kv-cache-dtype` | `fp8` | Halves KV cache memory footprint on H100 (which has native fp8 support), doubling the number of concurrent sequences that fit before eviction. |

---

## 2. Baseline Eval Results (Phase 5)

Eval set: 30 questions from BIRD-bench dev, run against `Qwen/Qwen3-30B-A3B-Instruct-2507` on H100.

| Metric | Value |
|--------|-------|
| Overall pass rate | 16.7% (5 / 30) |
| Pass rate at iteration 0 | 20.0% (6 / 30) |
| Pass rate at iteration 1 | 16.7% (5 / 30) |
| Pass rate at iteration 2 | 16.7% (5 / 30) |

**Commentary:** The verify→revise loop is net-negative: the first-attempt pass rate (20%) degrades to 16.7% after revision and never recovers. The reviser breaks one question that was originally correct and fails to fix any others. The loop is costing one correct answer per 30 questions.

Root cause: the verifier is too aggressive — it flags valid results where row count seems "low" given a plural noun in the question. The reviser then introduces SQL syntax errors (extra closing parentheses, wrong table aliases) that weren't in the original query. The model's revision pass is producing syntactically broken SQL more often than it produces fixes.

---

## 3. SLO Tuning (Phase 6)

SLO target: P95 agent latency < 5s at 10 RPS over a 5-minute window.

**Baseline (10 RPS, 300s, default uvicorn — 1 worker):**
- P50: 45.8s | P95: 113.8s | OK: 11% (332/3000) | client_errors: 869 | timeouts: 1631

**Iteration 1:**
Saw P95=113s with 869 client errors and only 11% success → hypothesized uvicorn's default single-worker thread pool (~12 threads) was saturated: at 10 RPS × ~45s/request the backlog was ~450 concurrent requests, far beyond capacity. Changed to `--workers 4` (~48 threads). Result: client errors dropped to 45, success rate jumped to 79%, P50 halved to 18.9s — but P95 only moved to 95.7s. The congestion loop partially broke but per-call vLLM latency rose from ~2s to ~6s, indicating vLLM is now also under load.

**Iteration 2:**
Saw Grafana queue depth spike to 25-30 and requests_running near 100 (approaching max-num-seqs=128), with vLLM per-call latency rising from 2s to 4-7s → hypothesized too many concurrent sequences competing for GPU memory bandwidth. Changed `--max-num-seqs 128 → 32`. Result: invalid — Grafana showed an abrupt cliff in requests_running and generation tokens/sec mid-run (crash signature, not graceful completion). vLLM crashed during the test, causing all subsequent requests to fail with connection errors. The 2708 client_errors and 7% success rate reflect the crash, not the config change. Reverted to max-num-seqs=128.

**Iteration 3:**
Saw P95 drop with each worker increase (1→4→8 workers: 113s→95s→55s) → hypothesized agent server thread pool still the binding constraint. Changed to `--workers 8` (~96 threads). Result: P50 improved to 12.9s, P95 to 55.2s, success rate 84%, Grafana queue depth near 0 (agent server no longer queuing). vLLM per-call P50 stabilised at ~4-5s. Worker scaling is working but hitting diminishing returns — further doubling would yield ~27s P95, not 5s.

**Final verdict — SLO MISSED:**
Best P95 = 55.2s at 10 RPS; gap = 11× over the 5s target. Root cause is structural: 3 sequential LLM calls × ~4-5s each under load = ~12-15s minimum pipeline. The 5s SLO requires each call to complete in < 1.67s, which is only achievable at very low concurrency (< 5 RPS). Closing the gap would require: (a) removing the verify→revise loop (1 LLM call instead of 3), or (b) a smaller/faster model, or (c) parallelising the verify and revise calls.

---

## 4. Agent Value

*To be filled in after Phase 6 with final per-iteration pass rates.*

---

## 5. What I'd Do With More Time

- **Few-shot examples in `GENERATE_SQL_SYSTEM`:** Include 2-3 examples of schema + question → SQL pairs. The model's first-attempt accuracy on hard BIRD questions (multi-table joins, date filters) would improve significantly.
- **Schema compression:** Current prompts include full `CREATE TABLE` statements. Stripping column comments and unused tables would reduce prompt tokens by ~30%, cutting TTFT and cost.
- **Smarter verify prompt:** Add explicit guidance that `ORDER BY ... LIMIT 1` is a valid "highest X" pattern, preventing the verifier from flagging correct single-row results as incomplete.
- **Per-database prefix caching tuning:** Different databases have different schema sizes. Profiling cache hit rates per database would reveal which schemas benefit most from prefix caching.
