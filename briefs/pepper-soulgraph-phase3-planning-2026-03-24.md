---
author: pepper
date: 2026-03-24
type: product-planning
priority: P1
for: shuri, team-lead
---

# SoulGraph Phase 3 Planning Brief — Full POC

**Context:** Phase 2 is CONFIRMED COMPLETE (11/11 tasks, 53 tests, 79% coverage, ~10 days early). Phase 3 due Apr 11. With 18 days of runway, we have buffer — but several Phase 3 deliverables are meaty. Planning NOW prevents the bottleneck pattern we saw in Week 1.

---

## Phase 3 Scope (from PRD v1.0)

| # | Deliverable | Description | Estimated Effort | Risk |
|---|-------------|-------------|-----------------|------|
| T1 | Fine-tuning pipeline | HuggingFace PEFT + MLflow + eval-to-training feedback loop | 3-5 days | HIGH — largest single task, needs GPU access |
| T2 | NeMo Guardrails | Safety layer on all agent I/O. Adversarial input must trigger block. | 2-3 days | MEDIUM — NeMo integration can be finicky |
| T3 | Colab notebook | One-click demo, no local setup, runs on Colab free tier | 1-2 days | LOW — mostly packaging |
| T4 | pgvector integration | Hybrid search (structured + vector) alongside ChromaDB | 2-3 days | MEDIUM — new data store + dual retrieval logic |
| T5 | vLLM integration | Production serving behind LiteLLM proxy, 16x throughput | 1-2 days | LOW — LiteLLM already proxies; vLLM is a backend swap |
| T6 | Eval report formatting | Structured scored output (JSON/HTML report, not just metrics in logs) | 1 day | LOW |

**Total estimated effort: 10-16 days.** Available runway: 18 days (Mar 25 → Apr 11). Buffer: 2-8 days.

---

## Acceptance Criteria Assessment (6 criteria from conference decision)

| # | Criterion | Status After Phase 2 | Phase 3 Gap |
|---|-----------|---------------------|-------------|
| 1 | Supervisor delegates to 3+ sub-agents | LIKELY MET — Supervisor routes to RAG + Tool + Eval | Verify; may just need a test |
| 2 | End-to-end structured evaluation report | PARTIALLY MET — RAGAS metrics exist but output format unclear | T6: format as structured JSON/HTML report |
| 3 | Streaming token output visible | LIKELY MET — Phase 2 T8 added WebSocket streaming | Verify in Colab context |
| 4 | Guardrail triggers on adversarial input | NOT MET — NeMo not integrated | T2: Full Phase 3 task |
| 5 | Latency under 90 seconds | UNTESTED — need benchmark on standard dataset | Test after T1/T5; may need optimization |
| 6 | Colab notebook included | NOT MET | T3: Full Phase 3 task |

**3 of 6 criteria likely already met by Phase 2.** Phase 3 work is primarily T1 (fine-tuning), T2 (guardrails), T3 (Colab), and verification of the others.

---

## Recommended Task Sequencing

**Wave 1 (Mar 25-28): Foundation + Quick Wins**
- T6: Eval report formatting (1 day) — quick win, satisfies criterion #2 definitively
- T5: vLLM integration (1-2 days) — backend swap behind existing LiteLLM proxy
- Verify criteria #1, #3 via tests — confirm Phase 2 already satisfies these
- Add GitHub topics to repo (5 min): langgraph, multi-agent, rag, evaluation, python, redis

**Wave 2 (Mar 29 - Apr 2): Core New Features**
- T2: NeMo Guardrails (2-3 days) — satisfies criterion #4 (the one blocker)
- T4: pgvector integration (2-3 days) — can run parallel with T2 if modular

**Wave 3 (Apr 3-7): The Big One**
- T1: Fine-tuning pipeline (3-5 days) — PEFT + MLflow + eval-to-training loop
- GPU access needed: Kaggle T4 (30 hrs/week free) or Colab Pro ($10/mo backup)

**Wave 4 (Apr 8-10): Polish + Ship**
- T3: Colab notebook (1-2 days) — depends on all other tasks being done
- Run all 6 acceptance criteria as an integration test
- DECISIONS.md (per Fury S2 recommendation — architectural tradeoff documentation)

**Buffer (Apr 10-11): Emergency time**

---

## Cross-Agent Dependencies

| Dependency | From | Impact | Action |
|------------|------|--------|--------|
| Fine-tuning GPU access | CEO | T1 blocked if Kaggle access not set up | CEO: verify Kaggle account can access T4 GPUs |
| DECISIONS.md content | Fury + Shuri | Xavier needs this for system design interview prep | Fury drafts architecture tradeoffs, Shuri adds implementation details |
| Colab testing | Banner | Can Banner help test Colab notebook on multiple accounts? | Low priority but useful for QA |
| Portfolio integration | Loki | SoulGraph Phase 3 features should be reflected in portfolio | After Phase 3 ships |
| Outreach claim accuracy | Hawkeye | 3 outreach templates claim fine-tuning. Must ship T1 before credibility gap matters. | CEO: decide whether to reframe or wait |

---

## Key Decisions Needed

| # | Decision | Who | Impact | Recommendation |
|---|----------|-----|--------|----------------|
| 1 | When should Shuri start Phase 3? | CEO/Pepper | Phase 2 just closed; Shuri also has portfolio mobile fix | Start Wave 1 immediately (quick wins), defer heavy tasks until portfolio mobile fix ships |
| 2 | Fine-tuning claim in outreach templates | CEO | Credibility risk if HM clicks SoulGraph and finds no fine-tuning | Remove "integrates fine-tuning" from templates now; add back when T1 ships. Or reframe as "fine-tuning pipeline designed/planned." |
| 3 | Kaggle vs Colab Pro for GPU access | CEO | T1 depends on GPU. Kaggle = free but 30hr/week cap. Colab Pro = $10/mo, more flexible. | Start with Kaggle. Upgrade to Colab Pro only if 30hr/week is insufficient. |
| 4 | pgvector priority | Pepper | pgvector adds architectural depth but isn't in acceptance criteria | Keep in scope but de-prioritize to Wave 2. If behind schedule, cut it. |

---

## Portfolio Mobile Fix vs Phase 3 Capacity

**Shuri's current queue:**
1. Portfolio mobile fix (P0 for Mar 28 outreach) — Loki spec pending, Shuri implements
2. SoulGraph Phase 3 (P1 for Apr 11) — 18-day runway

**Recommendation:** Shuri starts Phase 3 Wave 1 (quick wins) NOW while waiting for Loki's spec. When spec arrives, switch to portfolio mobile fix (1-2 days). Then resume Phase 3 Wave 2+. This maximizes throughput.

---

## Phase 3 Health Monitoring

| Checkpoint | Date | Expected |
|------------|------|----------|
| Wave 1 complete | Mar 28 | T5, T6 done. Criteria 1-3 verified. |
| Wave 2 complete | Apr 2 | T2, T4 done. Criterion 4 met. |
| Wave 3 complete | Apr 7 | T1 done. Fine-tuning loop working. |
| All criteria pass | Apr 10 | T3 done. Integration test green. |
| Phase 3 ship | Apr 11 | README updated. Announcement ready. |

If any checkpoint misses by >2 days, escalate to Pepper for scope negotiation.

---

## DECISIONS.md Recommendation (from Fury S2)

Fury recommends SoulGraph include a `DECISIONS.md` documenting architectural tradeoffs. This document becomes Xavier's system design interview answer. Key entries:

| Decision | Why | Alternative | Tradeoff |
|----------|-----|-------------|----------|
| LangGraph over CrewAI | State machine rigor, 400 companies in production | CrewAI simpler for POCs | LangGraph more robust at production scale |
| ChromaDB + pgvector over single store | Hybrid retrieval: semantic + structured | Single store simpler | Precision improvement justifies complexity |
| RAGAS + DeepEval over LangSmith-only | Vendor-neutral eval, data ownership | LangSmith faster setup | Dual approach demonstrates production maturity |
| Redis state bus over in-memory | Cross-agent state sharing, crash recovery | In-memory faster for single-process | Multi-agent coordination requires shared state |
| vLLM over API-only | Self-hosted inference, no vendor lock-in | API simpler | Sovereignty + latency justify GPU investment |
| NeMo Guardrails over manual checks | Named framework for regulated industries | Manual cheaper | Enterprise trust requires named frameworks |

Shuri should create this file during Phase 3 implementation as decisions are being made.

---

*Filed by Pepper. For Shuri (implementation), CEO (decisions), Fury (DECISIONS.md content). Next review: Mar 28 checkpoint.*
