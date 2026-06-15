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

Eval set: 30 questions from BIRD-bench dev, run against `Qwen/Qwen3-30B-A3B-Instruct-2507`.

| Metric | Value |
|--------|-------|
| Overall pass rate | 23.3% (7 / 30) |
| Pass rate at iteration 0 | 26.7% (8 / 30) |
| Pass rate at iteration 1 | 23.3% (7 / 30) |
| Pass rate at iteration 2 | 23.3% (7 / 30) |

**Commentary:** The verify→revise loop did not improve quality — it slightly degraded it (26.7% → 23.3%). One question that was correct on the first attempt (card_games/Coldsnap) was incorrectly flagged by the verifier and revised into a wrong answer. Zero questions improved through revision. The loop is not earning its keep on this eval set with the current prompts.

Root cause: the verifier prompt is slightly over-aggressive — it flags single-row results as incomplete when the question uses the word "cards" (plural). This causes the revise node to drop a correct `LIMIT 1` and return multiple rows, breaking the match against gold SQL.

---

## 3. SLO Tuning (Phase 6)

*To be filled in after load testing on the H100.*

---

## 4. Agent Value

*To be filled in after Phase 6 with final per-iteration pass rates.*

---

## 5. What I'd Do With More Time

- **Few-shot examples in `GENERATE_SQL_SYSTEM`:** Include 2-3 examples of schema + question → SQL pairs. The model's first-attempt accuracy on hard BIRD questions (multi-table joins, date filters) would improve significantly.
- **Schema compression:** Current prompts include full `CREATE TABLE` statements. Stripping column comments and unused tables would reduce prompt tokens by ~30%, cutting TTFT and cost.
- **Smarter verify prompt:** Add explicit guidance that `ORDER BY ... LIMIT 1` is a valid "highest X" pattern, preventing the verifier from flagging correct single-row results as incomplete.
- **Per-database prefix caching tuning:** Different databases have different schema sizes. Profiling cache hit rates per database would reveal which schemas benefit most from prefix caching.
