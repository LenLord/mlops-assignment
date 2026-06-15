# MLOps Assignment — Task Plan

Work through this step by step. Each task has a clear goal, the files to touch, and what "done" looks like.

---

## Phase 0 — Setup (on the H100 VM)

### Task 0.1 — Forward ports and connect to VM
- Forward ports: 3000 (Grafana), 9090 (Prometheus), 3001 (Langfuse), 8000 (vLLM), 8001 (agent)
- Via VSCode Remote-SSH or plain SSH: `ssh -L 3000:localhost:3000 -L 9090:localhost:9090 -L 3001:localhost:3001 -L 8000:localhost:8000 -L 8001:localhost:8001 <user>@<vm>`
- **Done when:** you can reach `http://localhost:9090` in your local browser

### Task 0.2 — Clone repo and install dependencies
```bash
git clone <repo-url>
cd <repo-folder>
uv sync
cp .env.example .env   # fill in HF_TOKEN at minimum
```
- **Done when:** `uv run python -c "import langgraph; print('ok')"` prints `ok`

### Task 0.3 — Load BIRD data
```bash
uv run python scripts/load_data.py
```
- Downloads BIRD dev set (~500 MB), extracts SQLite databases, creates `evals/eval_set.jsonl` (30 questions) and `load_test/perf_pool.jsonl`
- **Done when:** `data/bird/` exists with `.sqlite` files and `evals/eval_set.jsonl` has 30 lines

### Task 0.4 — Start the observability stack
```bash
docker compose up -d
```
- **Done when:** Grafana (`localhost:3000`), Prometheus (`localhost:9090`), Langfuse (`localhost:3001`) all load in browser

---

## Phase 1 — vLLM Serving Config

### Task 1.1 — Start vLLM with initial config
- File: `scripts/start_vllm.sh`
- Add optimization flags to the launch command. Start with:
  - `--enable-prefix-caching` — schema prompts are repeated; cache hits save TTFT
  - `--kv-cache-dtype fp8` — halves KV memory, more concurrency headroom
  - `--max-num-seqs 64` — cap concurrent sequences to bound latency
  - `--gpu-memory-utilization 0.92`
- Run: `bash scripts/start_vllm.sh`
- **Done when:** `curl http://localhost:8000/v1/models` returns the model name

### Task 1.2 — Test manually with eval questions
- Pick 3-5 lines from `evals/eval_set.jsonl` and fire them at vLLM directly
- Take screenshot: `screenshots/vllm_manual_query.png`
- **Done when:** SQL-looking output comes back for a natural language question

### Task 1.3 — Document config in REPORT.md
- Create `REPORT.md`, add section "Serving Configuration"
- One row per flag: `flag | justification`
- **Done when:** REPORT.md exists with the config table

---

## Phase 2 — Grafana Dashboard

### Task 2.1 — Add latency panels
- File: `infra/grafana/provisioning/dashboards/serving.json` (or edit in Grafana UI and export)
- Add panels:
  - P95 E2E latency: `histogram_quantile(0.95, rate(vllm:e2e_request_latency_seconds_bucket[1m]))`
  - P50 E2E latency: same with 0.50
  - TTFT P95: `histogram_quantile(0.95, rate(vllm:time_to_first_token_seconds_bucket[1m]))`

### Task 2.2 — Add throughput panels
- Panels to add:
  - Request queue depth: `vllm:num_requests_waiting`
  - Generation tokens/s: `rate(vllm:generation_tokens_total[1m])` (already in starter)
  - Successful requests/s: `rate(vllm:request_success_total[1m])`

### Task 2.3 — Add KV cache panel
- Panel: `vllm:gpu_cache_usage_perc` — % of GPU KV cache used
- This is the most important single metric for diagnosing overload
- **Done when:** All panels visibly react when you fire a burst of requests
- Take screenshot: `screenshots/grafana_serving.png`
- Commit the updated dashboard JSON

---

## Phase 3 — Agent Implementation

### Task 3.1 — Write SQL generation prompts (`agent/prompts.py`)
- Fill in `GENERATE_SQL_SYSTEM` and `GENERATE_SQL_USER`
- System: role ("expert SQL assistant"), output format ("return only SQL, no explanation")
- User template: uses `{schema}` and `{question}` placeholders
- **Done when:** `generate_sql_node` (already wired) produces valid SQL

### Task 3.2 — Write verification prompts (`agent/prompts.py`)
- Fill in `VERIFY_SYSTEM` and `VERIFY_USER`
- System: role ("SQL result verifier"), output must be JSON `{"ok": bool, "issue": str}`
- User template: uses `{question}`, `{sql}`, `{result}` placeholders
- Goal: catch SQL errors, zero rows when rows expected, wrong columns

### Task 3.3 — Write revision prompts (`agent/prompts.py`)
- Fill in `REVISE_SYSTEM` and `REVISE_USER`
- User template: includes schema, question, previous SQL, issue description, previous result
- Include prior attempt history so model doesn't repeat the same mistake

### Task 3.4 — Implement `verify_node` (`agent/graph.py`)
- Call LLM with VERIFY prompts (formatted with `state.question`, `state.sql`, `state.execution_result.render()`)
- Parse JSON response: `json.loads(response)`
- Return `{"verify_ok": bool, "verify_issue": str}`
- Fallback if JSON parse fails: `{"verify_ok": False, "verify_issue": "unparseable response"}`

### Task 3.5 — Implement `revise_node` (`agent/graph.py`)
- Follow the same pattern as `generate_sql_node` (the worked example in the file)
- Call LLM with REVISE prompts
- Extract SQL with `_extract_sql()`
- Return `{"sql": new_sql, "iteration": state.iteration + 1}`

### Task 3.6 — Implement `route_after_verify` (`agent/graph.py`)
- If `state.verify_ok` → return `"end"`
- If `state.iteration >= MAX_ITERATIONS` → return `"end"`
- Otherwise → return `"revise"`

### Task 3.7 — Start agent server and test
```bash
uv run uvicorn agent.server:app --host 0.0.0.0 --port 8001
```
- Test with: `curl -X POST http://localhost:8001/answer -H 'Content-Type: application/json' -d '{"question": "...", "db": "..."}'`
- **Done when:** At least one question returns `"iterations": 1` or higher (revise triggered)

---

## Phase 4 — Langfuse Tracing

### Task 4.1 — Set up Langfuse project
- Go to `http://localhost:3001`, sign up, create a project
- Copy public key and secret key

### Task 4.2 — Add keys to `.env`
```
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=http://localhost:3001
```
- The callback handler is already wired in `agent/server.py` — env vars are all that's needed

### Task 4.3 — Fire 10 questions and inspect traces
- Send 10 POST requests to `/answer`
- In Langfuse UI: find a trace, confirm waterfall shows `generate_sql → verify → (revise)` spans with latency + token counts
- Take screenshots: `screenshots/langfuse_trace.png`, `screenshots/langfuse_tags.png`

---

## Phase 5 — Eval Runner

### Task 5.1 — Implement `eval_one` (`evals/run_eval.py`)
```python
def eval_one(question, db_id, gold_sql, agent_url):
    # 1. POST {"question": question, "db": db_id} to agent_url
    # 2. Extract agent sql and iteration count from response
    # 3. run_sql(db_id, agent_sql) and run_sql(db_id, gold_sql)
    # 4. matches(gold_rows, pred_rows) → correct bool
    # 5. Return dict: {question, db_id, gold_sql, agent_sql, iterations, correct, error}
```

### Task 5.2 — Implement `summarize` (`evals/run_eval.py`)
```python
def summarize(results):
    # Overall pass rate: sum(correct) / len(results)
    # Per-iteration: for k in [0,1,2,3]:
    #   count questions where correct AND iterations <= k
    #   (carry-forward: correct at iter 1 = correct at iters 2, 3 too)
    # Return {"overall": float, "per_iteration": {0: float, ...}, "n": int}
```
- Helper functions `run_sql`, `canonicalize`, `matches`, and the main loop are already complete

### Task 5.3 — Run baseline eval
```bash
uv run python evals/run_eval.py
```
- Watch Grafana while it runs (~60 LLM calls)
- **Done when:** `results/eval_baseline.json` written with per-iteration pass rates
- Take screenshot: `screenshots/grafana_eval_run.png`
- Check: if `per_iteration[3] > per_iteration[0]`, the revise loop is earning its keep

---

## Phase 6 — SLO Tuning

### Task 6.1 — Baseline load test
```bash
uv run python load_test/driver.py --rps 10 --duration 300
```
- Note P95 latency and achieved RPS from output
- Watch Grafana: which metric moves first as load ramps?

### Task 6.2 — Diagnose bottleneck
- Look at: KV cache usage, queue depth, TTFT vs TPOT breakdown
- Form a hypothesis before changing anything
- Write in REPORT.md: `"saw X → hypothesized Y → changed Z → result was W"`

### Task 6.3 — Change one thing and re-run
- Common levers: `--max-num-seqs`, `--kv-cache-dtype fp8`, prefix caching, `--max-num-batched-tokens`
- Take before/after Grafana screenshots: `screenshots/grafana_before.png`, `screenshots/grafana_after.png`
- Repeat until P95 <5s at 10 RPS (or document the gap)

### Task 6.4 — Post-tuning eval
```bash
uv run python evals/run_eval.py --out results/eval_after_tuning.json
```
- **Done when:** `results/eval_after_tuning.json` saved; compare pass rates vs baseline

---

## Phase 7 — Report

### Task 7.1 — Complete `REPORT.md`
Sections (target 2-3 pages total):
1. **Serving configuration** — table of vLLM flags + one-line justification each
2. **Baseline eval results** — overall pass rate, per-iteration table, commentary on loop value
3. **SLO iteration log** — baseline numbers → each change → final numbers
4. **Agent value** — did verify→revise improve accuracy? cite the per-iteration stats
5. **What I'd do with more time** — specific ideas (e.g., few-shot examples, schema compression, prefix caching tuning)

---

## Deliverables Checklist

| File | Phase |
|------|-------|
| `REPORT.md` | 1, 6, 7 |
| `scripts/start_vllm.sh` (tuned) | 1 |
| `infra/grafana/provisioning/dashboards/serving.json` | 2 |
| `agent/prompts.py` | 3 |
| `agent/graph.py` (verify/revise/router) | 3 |
| `evals/run_eval.py` | 5 |
| `results/eval_baseline.json` | 5 |
| `results/eval_after_tuning.json` | 6 |
| `screenshots/vllm_manual_query.png` | 1 |
| `screenshots/grafana_serving.png` | 2 |
| `screenshots/langfuse_trace.png` | 4 |
| `screenshots/langfuse_tags.png` | 4 |
| `screenshots/grafana_eval_run.png` | 5 |
| `screenshots/grafana_before.png` | 6 |
| `screenshots/grafana_after.png` | 6 |
