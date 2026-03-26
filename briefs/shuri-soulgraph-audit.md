# SoulGraph Full Codebase Audit — Shuri

**Date:** 2026-03-26
**Auditor:** Shuri (Technical PM)
**Requested by:** CEO
**Scope:** Full architecture, features, tests, quality, frontend assessment

---

## 1. Executive Summary

SoulGraph is a well-architected LangGraph multi-agent RAG service at **Phase 3 Wave 1 complete**. The codebase is clean, well-tested (91% coverage, 113 tests), fully linted (ruff + mypy strict), and follows solid Python conventions. **No frontend exists** — only CLI + REST API + WebSocket streaming. A frontend is the obvious next step.

**Health: GREEN** — all CI checks pass, no tech debt worth flagging.

---

## 2. Architecture Assessment

### Graph Topology
```
User -> Supervisor (intent classify) -> RAG Agent -> Evaluator -> END
                                     -> Tool Agent -> END
```

- **4 nodes:** supervisor, rag, evaluator, tool
- **Routing:** LLM-based intent classification (question_answering vs tool_use)
- **State:** TypedDict (AgentState) — immutable semantics, add_messages accumulator
- **Checkpointing:** Redis (optional, graceful None fallback)

### Module Sizes (957 lines total, excluding tests)
| Module | Lines | Role |
|--------|-------|------|
| report.py | 225 | Report formatter (JSON + HTML) |
| api.py | 166 | FastAPI REST + WebSocket |
| supervisor.py | 135 | LangGraph StateGraph + routing |
| tool_agent.py | 114 | AST calculator + word count |
| evaluator.py | 106 | RAGAS metrics |
| router.py | 103 | LiteLLM model routing |
| config.py | 88 | Environment settings |
| tracing.py | 85 | LangSmith + LangFuse dual tracing |
| cli.py | 69 | CLI entrypoint |
| rag.py | 67 | ChromaDB retrieval |
| checkpoint.py | 43 | Redis checkpoint factory |
| state.py | 39 | Shared state schema |

**Assessment:** Small, focused modules. Good separation of concerns. No module exceeds 225 lines. Clean import structure with lazy imports where appropriate.

### 6 Pillars Assessment

| Pillar | Score | Notes |
|--------|-------|-------|
| **Performant** | 7/10 | 16s test suite. WS streaming is word-by-word (not true async). vLLM for self-hosted inference. |
| **Robust** | 8/10 | 91% coverage, strict mypy, 8 ADRs. Graceful fallbacks (Redis None, tracing no-op, ChromaDB empty). |
| **Resilient** | 7/10 | Redis/ChromaDB failures handled gracefully. No circuit breaker or retry logic. API returns 503 on graph errors. |
| **Secure** | 7/10 | No secrets in code. Safe AST arithmetic (no raw code execution). Missing: NeMo Guardrails (planned Wave 2), input sanitization, rate limiting. |
| **Sovereign** | 8/10 | Self-hostable via Docker Compose. vLLM for local inference. LangFuse for self-hosted tracing. All data stays local. |
| **Transparent** | 9/10 | 8 ADRs documenting every major decision. Structured reports (JSON + HTML). Dual tracing. Clean logging throughout. |

---

## 3. Feature Completeness

### Working (Phase 0-3 Wave 1)
- LangGraph supervisor with intent-based routing
- RAG Agent with ChromaDB vector retrieval
- Evaluator Agent with RAGAS metrics (faithfulness, relevancy, precision, recall)
- Tool Agent with safe AST calculator + word count
- Redis checkpointing with graceful fallback
- LiteLLM model router (cloud + vLLM backends)
- FastAPI REST (/query) + WebSocket streaming (/ws/query)
- Health endpoint (/health)
- Dual tracing (LangSmith + LangFuse)
- EvalReport formatter (JSON + HTML output)
- CLI entrypoint (soulgraph "question")
- Docker Compose (Redis + ChromaDB + LangFuse)
- HotpotQA seed script (referenced but not in main source)

### Missing / Planned (Phase 3 Wave 2 — deadline Apr 11)
- NeMo Guardrails (T2) — adversarial input protection
- Colab/Jupyter notebook demo (T3)
- pgvector migration from ChromaDB (T4) — for production persistence
- Feedback store — user feedback loop
- Batch evaluation pipeline
- API enhancements — pagination, filtering, batch queries
- **Frontend** — no web UI exists at all

### Acceptance Criteria Status
| Criterion | Status | Notes |
|-----------|--------|-------|
| 1. Supervisor delegates to 3+ agents | MET | 4 agent nodes in graph |
| 2. Structured report | MET | EvalReport with JSON + HTML |
| 3. Streaming token output | PARTIAL | Word-by-word simulation, not true async streaming |
| 4. Guardrail triggers | NOT MET | Planned Wave 2 |
| 5. Latency < 90s | UNTESTED | Requires live benchmark |
| 6. Colab notebook | NOT MET | Planned Wave 2 |

---

## 4. Test Quality

**Total: 113 passed, 1 skipped, 91% coverage**

| Test File | Tests | Coverage Target |
|-----------|-------|-----------------|
| test_report.py | ~30 | EvalReport JSON/HTML/save |
| test_acceptance_criteria.py | ~15 | Phase 3 acceptance criteria |
| test_api.py | ~12 | REST + WebSocket endpoints |
| test_router.py | ~10 | LiteLLM cloud + vLLM routing |
| test_tracing.py | ~10 | LangSmith + LangFuse callbacks |
| test_supervisor.py | ~8 | Intent classify + graph routing |
| test_cli.py | ~7 | CLI arg parsing + config validation |
| test_tool_agent.py | ~7 | AST calculator + tool dispatch |
| test_evaluator.py | ~6 | RAGAS metrics evaluation |
| test_rag_agent.py | ~5 | ChromaDB retrieval |
| test_config.py | ~4 | Settings env var loading |
| test_checkpoint.py | ~3 | Redis connect + None fallback |

**Coverage Gaps (minor):**
- cli.py at 58% — main execution path not tested (requires live infra)
- tracing.py at 88% — LangFuse import error path
- tool_agent.py at 84% — some edge case paths (unary ops, error formatting)

**Test Quality Assessment:** GOOD. Mocks are clean (MockRAGAgent, MockRouter). No tests hit live APIs. conftest.py is minimal and focused. Test names are descriptive.

---

## 5. Code Quality

### Strengths
1. **Type safety:** mypy --strict passes. All public functions have type annotations.
2. **No bare excepts:** Every catch block specifies exception type.
3. **Lazy initialization:** ChromaDB, Redis, Router all use lazy singletons — fast startup.
4. **Clean ADRs:** 8 decision records covering every architectural choice.
5. **Consistent patterns:** All agents follow __call__(state) -> dict convention.
6. **Import discipline:** Heavy imports (chromadb, litellm, ragas) are lazily imported.
7. **Clean git history:** 19 meaningful commits, each with proper conventional commit messages.

### Minor Issues (non-blocking)
1. **WebSocket streaming is simulated:** answer.split() word-by-word isn't true streaming — it runs the full graph synchronously then splits. Real astream() streaming planned for Wave 2.
2. **asyncio.get_event_loop() deprecation:** Used in api.py lines 80 and 129. Should use asyncio.get_running_loop() or asyncio.to_thread().
3. **Singleton pattern:** Module-level _router, _graph, _settings are not thread-safe. Fine for uvicorn workers but could cause issues in multi-threaded tests.
4. **RAGAS deprecation warning:** aevaluate() deprecated, should migrate to @experiment decorator (110 warnings in test output).
5. **Version mismatch:** pyproject.toml says 0.1.0, api.py says 0.2.0. Should be consistent.
6. **Missing seed script:** scripts/seed_hotpotqa.py referenced in CLAUDE.md but scripts/ dir only contains superpowers/.

---

## 6. Frontend Assessment

### Current State: NO FRONTEND EXISTS

SoulGraph has:
- CLI: python -m soulgraph.cli "question" — text output
- REST API: POST /query -> JSON response
- WebSocket: /ws/query -> JSON stream
- HTML Report: EvalReport.to_html() — static file, not served

There is **no web UI, dashboard, or interactive frontend**.

### Recommended Frontend

**Purpose:** Operational dashboard for SoulGraph agent coordination and evaluation results.

**Views:**
1. **Query Playground** — Chat-like interface. Type a question, see agent routing in real-time (supervisor -> rag/tool -> evaluator), stream answer tokens via WebSocket.
2. **Eval Dashboard** — Historical evaluation scores across queries. Table + charts showing faithfulness/relevancy/precision/recall trends. Pass/fail rate over time.
3. **Agent Monitor** — Real-time view of agent status (idle/running), current question, processing time. Shows graph execution path for each query.
4. **RAG Inspector** — Browse ChromaDB collections, view retrieved documents for a query, see relevance scores. Test retrieval without running full graph.
5. **Model Router Config** — View current model assignments (reasoning vs fast), vLLM status, switch models. Show cost/latency comparison if LangFuse data available.
6. **Trace Viewer** — Pull LangFuse traces and display inline (or link to LangFuse UI).

**Stack recommendation:**
- Next.js (consistent with portfolio/soul UI)
- WebSocket client for live streaming
- Recharts for score visualization
- Tailwind + zinc theme (consistent with portfolio brand)
- Can be a separate soulgraph-web/ directory or embedded in web/ subfolder

**Complexity:** Medium. WebSocket integration is the hard part. Query playground + eval dashboard should be MVP (2 views).

---

## 7. Recommendations

### Immediate (before Wave 2)
1. Fix version mismatch (0.1.0 vs 0.2.0)
2. Replace asyncio.get_event_loop() with asyncio.get_running_loop() or asyncio.to_thread()
3. Suppress or fix RAGAS deprecation warnings

### Wave 2 Priorities (by Apr 11)
1. NeMo Guardrails — adversarial input protection
2. True async streaming via graph.astream() — replace word-by-word simulation
3. pgvector migration for production persistence
4. Colab notebook demo
5. Frontend MVP (Query Playground + Eval Dashboard)

### Post Wave 2
1. Feedback store — user thumbs up/down on answers
2. Batch evaluation pipeline — run assessments across dataset
3. Rate limiting + auth on API
4. Multi-tenant session management
5. Full frontend with all 6 views

---

## 8. Conclusion

SoulGraph is a solid, well-documented, production-path multi-agent RAG system. The codebase is clean, tests are comprehensive, and architecture decisions are well-reasoned. The main gap is the **complete absence of a frontend** — currently only accessible via CLI or raw API calls. A frontend is the highest-impact next deliverable after completing the Wave 2 backlog items.

**Audit verdict: HEALTHY** — ready for continued development.
