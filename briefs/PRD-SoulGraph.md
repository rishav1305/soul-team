# PRD: SoulGraph — Enterprise Multi-Agent System

**Author:** Pepper (CPO) | **Version:** 1.0 | **Date:** 2026-03-23
**Status:** DRAFT — Pending CEO review
**Decision source:** `~/soul-roles/shared/decisions/2026-03-22-soulgraph-meta-agent.md`

---

## 1. Summary

SoulGraph is a batteries-included, open-source multi-agent system built on LangGraph that unifies four deep AI/ML capabilities — RAG, Agent Orchestration, Model Evaluation, and Fine-tuning — into a single architecture with shared state via Redis and ChromaDB. It serves as both a public portfolio piece proving enterprise-grade AI architecture skills and a reusable starter service for AI engineers building production agent systems.

This PRD defines what SoulGraph is, who it serves, how we measure success, and what ships in each phase. SoulGraph is the centerpiece of the 90-day salary targeting plan — it closes the public proof gap that currently limits pipeline conversion and comp negotiation leverage.

---

## 2. Contacts

| Name | Role | Responsibility |
|------|------|---------------|
| Rishav (CEO) | Product Owner | Final approval on scope, timeline, public positioning |
| Pepper | CPO | PRD, health scorecard, graduation criteria, product oversight |
| Shuri | Engineering Lead | Implementation, CI/CD, Docker infrastructure, code quality |
| Fury | Strategy Advisor | Competitive positioning, market alignment, domain mapping |
| Loki | Content Lead | GitHub README copy, LinkedIn content series, SEO optimization |
| Hawkeye | Pipeline Operator | Outreach messaging alignment, lead-to-pillar mapping |
| Xavier | Interview Prep | System design interview answers based on SoulGraph architecture |

---

## 3. Background

### Context

Building production AI agent systems today requires stitching together 5+ separate tools — an orchestration framework, a RAG pipeline, an evaluation suite, a fine-tuning workflow, and a state management layer — none of which share state or feedback loops. AI engineers spend weeks wiring these together for every project.

Meanwhile, hiring managers evaluating senior AI engineer candidates see the same pattern: "I built a chatbot with LangChain" or "I used CrewAI to make agents talk to each other." These shallow portfolio pieces don't demonstrate the system design depth that $150K-$300K roles require.

### Why now?

Three converging forces make this the right time:

1. **Market timing:** Gartner predicts 40% of enterprise apps will embed AI agents by 2028 (up from <5% in 2025). The agentic AI market is $10.9B with 45% CAGR. Job postings for agentic AI roles grew 986% from 2023 to 2024.

2. **Competitive gap:** Fury's competitive scan (Mar 23, 2026) found that no existing open-source project combines all four pillars in a single integrated system. Frameworks (LangGraph, CrewAI) give you tools but not the system. Platforms (Dify, RAGFlow) are low-code and shallow. Tutorials are educational but not production-grade. The "enterprise reference architecture" niche is empty.

3. **Pipeline urgency:** 71% of Rishav's 40 active pipeline leads require RAG experience. 33% of T1-T2 leads need agentic orchestration. All 5 active T1 leads (Glean, Wissen, Movius, JAGGAER, Welldoc) explicitly seek orchestration experience. Without a public proof artifact, outreach messages lack credibility. SoulGraph closes this gap by March 27 (Phase 1).

### What recently became possible?

- **LangGraph maturity:** 34.5M monthly downloads, 400+ companies in production. The framework is stable enough to build on.
- **Free GPU access:** Kaggle offers 30 hrs/week of T4/P100 GPU time. Fine-tuning is no longer cost-prohibitive for a portfolio POC.
- **Dual observability:** LangSmith (managed) + LangFuse (self-hosted) can run simultaneously at zero cost, providing enterprise-grade tracing.
- **soul-team production experience:** Rishav has been running a 9-agent production system (soul-team) for months. SoulGraph formalizes these patterns into an open-source framework — this isn't theoretical, it's battle-tested.

---

## 4. Objective

### What is the objective?

Build and ship an open-source, enterprise-grade multi-agent reference architecture that proves Rishav can design production AI systems — not just call APIs.

### Why does it matter?

| Stakeholder | Value |
|------------|-------|
| **Rishav (career)** | Closes the public proof gap. Enables comp negotiations at Rs 50-80L / $100-160K. Differentiates from 99% of AI engineer candidates. |
| **Pipeline leads** | Gives hiring managers a verifiable, deep technical artifact to evaluate. |
| **AI community** | Provides a free, complete reference architecture that doesn't exist today. |
| **Content strategy** | 4 pillars generate 45-54 derivative content pieces over 3 months. |

### How does it align with strategy?

SoulGraph is pillar #1 of the salary targeting plan's four-channel strategy:
1. **SoulGraph** = public proof (credibility) <-- THIS PRODUCT
2. Scout pipeline = application volume
3. Content/LinkedIn = inbound visibility
4. Expert networks = immediate revenue + rate anchoring

### Key Results (SMART OKRs)

| KR | Metric | Target | Timeline | Measurement |
|----|--------|--------|----------|-------------|
| KR1 | Phase 1 shipped to GitHub | Supervisor + RAG + Eval agents working | Mar 27 | Repo exists, README complete, demo runs |
| KR2 | Full POC acceptance criteria met | All 6 criteria pass | Apr 11 | Test suite + manual verification |
| KR3 | GitHub stars | 25-50 | Apr 27 (Month 1) | GitHub API |
| KR4 | Pipeline conversion signal | 1+ interview attributed to SoulGraph | May 9 (Week 7) | Hawkeye tracking |
| KR5 | Content derivatives published | 10+ pieces (LinkedIn, blog, carousel) | Apr 27 | Loki metrics |
| KR6 | Colab notebook usage | 50+ opens | Apr 27 | Colab analytics |

### Graduation Criteria (Portfolio to Product)

SoulGraph starts as a portfolio piece. It graduates to "product" status only if:

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| External users | 5+ non-Rishav users running it | GitHub issues, Colab opens |
| GitHub stars | 200+ | GitHub API |
| Community contributions | 3+ external PRs merged | GitHub PR history |
| Repeat usage | Evidence of users building on it (forks with commits) | GitHub fork analysis |

Until graduation, SoulGraph is classified as **BUILD (portfolio)**, not **LIVE (product)**.

---

## 5. Market Segments

### Primary: AI engineers at startups and scaleups

**Who they are:** Mid-to-senior AI/ML engineers (3-8 years experience) at Series A-C startups who need to build multi-agent systems but don't have time to wire together 5 separate tools from scratch.

**Their problem:** "My CTO wants an AI agent system for our product. I know the pieces — RAG, orchestration, evaluation — but connecting them with shared state takes weeks. I wish there was a reference architecture I could fork and customize."

**Constraints:** Must run on modest hardware (no A100 clusters). Must be self-hosted (data sovereignty). Must be Python-native (LangGraph ecosystem). Prefer open-source with permissive license.

### Secondary: Enterprise AI platform teams

**Who they are:** Platform engineering teams at mid-to-large companies (500+ employees) evaluating multi-agent frameworks for internal tooling.

**Their problem:** "We're comparing CrewAI, AutoGen, and LangGraph. We need a production reference implementation — not a tutorial — to evaluate architecture patterns before committing."

**Constraints:** Need evaluation and guardrails (regulated industries). Need observability (LangSmith/LangFuse integration). Must demonstrate production signals (error recovery, state management, retry logic).

### Tertiary: Advanced students and career transitioners

**Who they are:** MS/PhD students or engineers pivoting into AI who want a deep project for their portfolio.

**Their problem:** "I've done the tutorials. I need something that shows I can architect systems, not just call APIs."

**Constraints:** Must be Colab-compatible (no local GPU required). Must have clear documentation. Must be followable as a learning path.

### Non-target (explicitly excluded)

- **Low-code builders** — Dify serves them. SoulGraph is code-first by design.
- **Researchers** — SoulGraph is engineering, not research. No novel algorithms.
- **Non-Python developers** — LangGraph is Python-native. No Go/Rust/JS port planned.

---

## 6. Value Propositions

### What customer jobs are we addressing?

| Customer Job | Current Solution | SoulGraph Solution | Improvement |
|-------------|-----------------|-------------------|------------|
| "Build a multi-agent system" | Wire together LangGraph + RAG + eval manually (2-4 weeks) | Fork SoulGraph, customize agents (2-3 days) | 5-10x faster time-to-prototype |
| "Evaluate my AI agent outputs" | LangSmith (paid) or nothing | Built-in RAGAS + DeepEval scoring on every output | Free, automatic, integrated |
| "Fine-tune models from agent feedback" | Separate pipeline, manual data curation | Eval agent auto-logs (input, output, score) triples for training | Closed feedback loop |
| "Prove I can build production AI systems" | Tutorial repos, toy chatbots | Enterprise reference architecture with 4 deep pillars | Portfolio differentiation |
| "Evaluate multi-agent frameworks" | Read docs, build toy apps | Working reference implementation with production signals | Faster, evidence-based evaluation |

### Value Curve: SoulGraph vs Competitors

| Dimension | CrewAI | AutoGen | LangGraph (raw) | Dify | SoulGraph |
|-----------|--------|---------|----------------|------|-----------|
| Ease of starting | HIGH | MEDIUM | LOW | HIGH | MEDIUM |
| Agent orchestration depth | MEDIUM | MEDIUM | HIGH | LOW | HIGH |
| Built-in RAG | NONE | NONE | NONE | HIGH | HIGH |
| Built-in evaluation | NONE | NONE | NONE (paid) | NONE | HIGH |
| Fine-tuning integration | NONE | NONE | NONE | NONE | HIGH |
| Production signals | LOW | LOW | MEDIUM | LOW | HIGH |
| Self-hosted | YES | YES | YES | YES | YES |
| Code-first | YES | YES | YES | NO | YES |
| Community size | LARGE | LARGE | LARGE | LARGE | NEW |

**SoulGraph's unique value:** The only open-source project that integrates all four pillars (RAG + Orchestration + Evaluation + Fine-tuning) with shared state and a feedback loop. Competitors are either frameworks (BYO everything), platforms (low-code, shallow), or single-pillar solutions.

### Which problems do we solve better than competitors?

1. **The integration problem.** Nobody else connects evaluation output to fine-tuning input automatically. The eval-to-training feedback loop is SoulGraph's core differentiator.

2. **The "prove it" problem.** Most portfolio projects show API calls. SoulGraph shows system design: state management, error recovery, retry logic, evaluation pipelines, model lifecycle management.

3. **The vendor lock-in problem.** SoulGraph is model-agnostic (LiteLLM proxy), infrastructure-agnostic (Docker), and observability-agnostic (LangSmith + LangFuse). No vendor lock-in at any layer.

---

## 7. Solution

### 7.1 Architecture

SoulGraph uses a **supervisor-swarm hybrid** pattern built on LangGraph StateGraph:

```
User Query
    |
    v
[FastAPI + WebSocket] ---- Streaming layer
    |
    v
[Supervisor Agent] ---- Task decomposition + routing
    |
    +---> [RAG Agent] ---- ChromaDB + pgvector retrieval
    |         |
    |         v
    |    [Context Assembly]
    |
    +---> [Tool Agent] ---- Function calling via ToolNode
    |
    +---> [Eval Agent] ---- RAGAS + DeepEval + NeMo Guardrails
    |         |
    |         +--> Score >= threshold --> Return to Supervisor
    |         +--> Score < threshold --> Retry + log to training data
    |         +--> Safety violation --> Block + sanitize
    |
    v
[Redis State Bus] ---- Shared state, checkpointing, pub/sub
    |
    v
[Fine-tune Pipeline] ---- HuggingFace PEFT, MLflow, vLLM
    |
    v
[Observability] ---- LangSmith + LangFuse + MLflow
```

**The loop:** Decompose -> Retrieve -> Execute -> Evaluate -> Learn

### 7.2 Key Features

#### Feature 1: Supervisor Agent (Pillar 2 — Agentic/Orchestration)

**What it does:** Receives user queries, decomposes them into subtasks, routes each subtask to the appropriate specialist agent, aggregates results, and decides when to retry.

**Why it matters:** Demonstrates the system design skill that senior AI roles require — not just "call one LLM" but "coordinate multiple agents with state and routing logic."

**Key capabilities:**
- Task decomposition using structured output
- Conditional routing via LangGraph StateGraph edges
- Iteration budget control (prevents infinite retry loops)
- Model routing via LiteLLM proxy (Claude for reasoning, Haiku for summarization)
- Redis checkpoint persistence via RedisSaver

#### Feature 2: RAG Agent (Pillar 1 — RAG Pipeline)

**What it does:** Retrieves relevant context from document stores using hybrid search (vector + structured), assembles context, and supports multi-hop retrieval.

**Why it matters:** RAG appears in 71% of pipeline leads. Every T1 lead requires RAG experience.

**Key capabilities:**
- Dual-store retrieval: ChromaDB (unstructured) + pgvector (structured/hybrid)
- Cross-encoder reranking for precision
- Multi-hop retrieval (query -> retrieve -> re-query)
- RAGAS quality scores logged per retrieval (faithfulness, relevance, precision)
- Dataset: HotpotQA (multi-hop QA, standardized benchmarks)

#### Feature 3: Evaluation Agent (Pillar 3 — Model Evaluation)

**What it does:** Scores every agent output before it reaches the user. Triggers retries on low scores. Blocks safety violations. Logs all scores for training data.

**Why it matters:** Blue ocean differentiator. No competitor has built-in evaluation. This is the feature that closes the eval-to-training feedback loop.

**Key capabilities:**
- RAGAS metrics: faithfulness, answer relevance, context precision, context recall
- DeepEval metrics: hallucination, toxicity, coherence, task accuracy (14+ metrics)
- NeMo Guardrails: PII detection, prompt injection blocking, content moderation
- Automatic (input, output, score) triple logging for fine-tuning dataset
- Structured evaluation reports (per-query and aggregate)

#### Feature 4: Fine-tuning Pipeline (Pillar 4 — Fine-tuning)

**What it does:** Curates training data from evaluation logs, runs LoRA/QLoRA fine-tuning, tracks experiments with MLflow, and hot-swaps improved models into the serving layer.

**Why it matters:** 47% salary premium for fine-tuning skills. No competitor integrates fine-tuning with evaluation feedback. This makes SoulGraph a "system that gets smarter over time."

**Key capabilities:**
- Automatic training data curation from eval agent logs
- LoRA/QLoRA fine-tuning via HuggingFace PEFT/TRL
- MLflow experiment tracking (hyperparams, loss curves, eval metrics)
- Model registry with version management
- Hot-swap into vLLM serving layer
- Runs on free GPU: Kaggle T4 (30 hrs/week), Colab Pro ($10/mo) backup

#### Feature 5: Cross-Cutting Infrastructure

| Layer | Implementation | Purpose |
|-------|---------------|---------|
| **Streaming** | FastAPI WebSocket + LangGraph async callbacks | Real-time token streaming visible during execution |
| **Serving** | vLLM behind LiteLLM proxy | 16x throughput over Ollama, production inference |
| **Observability** | LangSmith (managed) + LangFuse (self-hosted) + MLflow | Dual tracing + experiment tracking at $0 |
| **State** | Redis (pub/sub + checkpoint) | Shared state bus across all agents |
| **Guardrails** | NeMo on all agent I/O | Safety layer for regulated use cases |

### 7.3 Technology Stack

| Component | Technology | Why This Choice |
|-----------|-----------|-----------------|
| Orchestration | LangGraph (Python) | 34.5M downloads/mo, 400+ production users, graph-based state machines |
| State management | Redis | Persistent checkpointing, pub/sub, proven at scale |
| Vector store | ChromaDB | Simple, self-hosted, good for POC. Production path: pgvector |
| Structured search | pgvector | SQL + vector hybrid search for structured data |
| Evaluation | RAGAS + DeepEval | Open-source, comprehensive metrics, Python-native |
| Guardrails | NeMo Guardrails | NVIDIA-backed, enterprise-grade safety |
| Fine-tuning | HuggingFace PEFT/TRL | Industry standard LoRA/QLoRA, massive model support |
| Experiment tracking | MLflow | Open-source, self-hosted, model registry |
| Serving | vLLM | Fastest open-source inference engine |
| Model routing | LiteLLM | Model-agnostic proxy (Claude, GPT, Llama, Mistral) |
| API | FastAPI | Async, WebSocket support, Python-native |
| Datasets | HotpotQA, MMLU subset | Standardized benchmarks, reproducible results |
| Deployment | Docker Compose | Redis + ChromaDB + API in one command |
| GPU | Kaggle (free 30hr/wk T4), Colab Pro ($10/mo backup) | $0 fine-tuning |
| CI | GitHub Actions | Green-main policy, broken builds rolled back |
| Repo | github.com/rishav1305/soulgraph | Public monorepo, MIT license |

### 7.4 Assumptions

| # | Assumption | Risk if Wrong | Validation Plan |
|---|-----------|---------------|-----------------|
| 1 | LangGraph's supervisor pattern is stable enough for production reference architecture | Architecture needs rework | LangGraph has 400+ production users — validated |
| 2 | Free Kaggle GPU (30hr/week T4) is sufficient for fine-tuning demos | Need to pay for compute | T4 handles 7B models with QLoRA. Test in Phase 3. |
| 3 | HotpotQA is a good benchmark dataset for multi-hop RAG | Reviewers question dataset choice | HotpotQA is standard in RAG literature — validated |
| 4 | Portfolio value (proving skills) is guaranteed even without product traction | Effort wasted | Portfolio value is intrinsic to building it. Reversibility: 100%. |
| 5 | AI engineers want code-first reference architectures, not low-code platforms | Wrong audience | LangGraph's 34.5M downloads validate code-first demand |
| 6 | Hiring managers will evaluate the GitHub repo during interview process | Nobody looks at it | Mitigated by content strategy driving awareness |
| 7 | Shuri can deliver Phase 1 by Mar 27 alongside Claude API auth fix | Timeline slips | Skeleton is intentionally minimal. Fallback: delay outreach 1 day. |

---

## 8. Release

### Phase 1: Skeleton (Target: March 27 — 4 days from now)

**Scope:** Minimum viable architecture that demonstrates the core loop.

| Deliverable | Description | Acceptance |
|------------|-------------|------------|
| Supervisor agent | LangGraph StateGraph with task routing | Routes queries to 2+ agents |
| RAG agent | ChromaDB retrieval with HotpotQA dataset | Returns relevant context with RAGAS scores |
| Eval agent | Basic scoring (faithfulness, relevance) | Scores every output, triggers retry on low score |
| Docker Compose | Redis + ChromaDB + API | `docker compose up` starts everything |
| README | Architecture diagram, quickstart, one-liner | Visitors understand what SoulGraph is in 30 seconds |
| GitHub repo | Public, MIT license | github.com/rishav1305/soulgraph exists |

**NOT in Phase 1:** Fine-tuning, streaming, vLLM, NeMo guardrails, Colab notebook, pgvector.

**Success metric:** "Give it a question, get a grounded answer with an evaluation score."

### Phase 2: State + Routing (Target: April 3 — +1 week)

**Scope:** Production infrastructure layers.

| Deliverable | Description |
|------------|-------------|
| Model router | LiteLLM proxy for multi-model support |
| Redis state bus | Full checkpoint persistence, pub/sub wired |
| Streaming | FastAPI WebSocket, tokens visible during execution |
| Observability | LangSmith + LangFuse dual tracing |
| Tool agent | LangGraph ToolNode with function schemas |

**Success metric:** "Watch agents work in real-time. Switch models without code changes. Trace every step."

### Phase 3: Full POC (Target: April 11 — +2 weeks)

**Scope:** Complete system meeting all 6 acceptance criteria.

| Deliverable | Description |
|------------|-------------|
| Fine-tuning pipeline | HuggingFace PEFT + MLflow + eval-to-training loop |
| Guardrails | NeMo on all agent I/O, adversarial input triggers block |
| Colab notebook | One-click demo, no local setup required |
| Eval report | Structured scored output (not just logs) |
| pgvector | Hybrid search (structured + vector) |
| vLLM integration | Production serving with 16x throughput |

**Acceptance criteria (from conference decision):**
1. Supervisor delegates to 3+ sub-agents without human intervention
2. End-to-end processing returns structured evaluation report (scored)
3. Streaming token output visible during execution
4. At least one guardrail triggers on adversarial input
5. Total latency under 90 seconds for standard dataset
6. Colab-compatible notebook included

**Success metric:** All 6 criteria pass. Portfolio-ready. Content derivatives begin.

### Phase 4+: Ongoing Depth (April 11 onward)

| Deliverable | Timeline |
|------------|----------|
| One domain agent per week | Ongoing |
| Advanced RAG (reranking, hybrid, multi-hop) | Apr 18 |
| Production fine-tuning results (before/after metrics) | Apr 25 |
| Community contributions (good first issues) | May 1 |
| Conference talk material | Jun 1 |

### What is explicitly NOT in scope

| Item | Reason |
|------|--------|
| Multimodal AI | 0 pipeline leads need it. Doesn't integrate naturally. |
| Knowledge Graphs | 1 pipeline lead mentions it (Varahi — already SKIP). |
| Go/Rust/JS ports | LangGraph is Python-native. Wrapping adds 3 weeks for zero gain. |
| SaaS product | Portfolio first. Product traction is upside, not requirement. |
| Mobile/desktop app | Web API only. |
| Custom UI | API-first. Colab notebook is the "UI." |

---

## Health Scorecard

Once SoulGraph enters BUILD phase, track these metrics weekly:

| Metric | Source | Target (Month 1) | Target (Month 3) |
|--------|--------|------------------|------------------|
| Phases shipped on time | Shuri reports | 3/3 | — |
| Acceptance criteria met | Test suite | 6/6 | 6/6 |
| GitHub stars | GitHub API | 25-50 | 100-200 |
| Colab notebook opens | Colab analytics | 50+ | 200+ |
| Content pieces published | Loki tracking | 10+ | 45+ |
| Pipeline interviews attributed | Hawkeye tracking | 1+ | 3+ |
| Build stability | CI green rate | 95%+ | 98%+ |
| Community issues/PRs | GitHub | Any | 3+ PRs |

### Health Score Formula

```
Health = (0.3 * timeline_adherence) + (0.3 * acceptance_criteria_met)
       + (0.2 * content_velocity) + (0.2 * pipeline_attribution)

timeline_adherence: phases shipped on time / total phases (0-1)
acceptance_criteria_met: criteria passing / 6 (0-1)
content_velocity: pieces published / target (0-1, capped at 1)
pipeline_attribution: interviews attributed > 0 ? 1 : 0
```

Scale to 1-10. Below 6 triggers review. Below 4 triggers escalation.

---

## Risks

| Risk | Probability | Impact | Mitigation | Owner |
|------|-------------|--------|------------|-------|
| Phase 1 slips past Mar 27 | 25% | HIGH | Skeleton is minimal viable. Shuri dedicated sprint. | Shuri |
| Shuri overloaded (Claude API auth + SoulGraph) | 40% | HIGH | Prioritize auth fix first (unblocks Hawkeye). SoulGraph second. | CEO |
| "Yet another LangGraph demo" perception | 20% | HIGH | Differentiate with eval + fine-tuning loop. No demo has this. | Loki |
| Low star count weakens portfolio claim | 30% | MEDIUM | Content strategy drives initial stars. Quality > quantity for hiring. | Loki |
| Kaggle GPU insufficient for fine-tuning | 15% | LOW | Colab Pro backup ($10/mo). QLoRA reduces memory needs. | Shuri |
| Someone else ships equivalent first | 15% | MEDIUM | First-mover advantage. Ship fast, publish content immediately. | All |
| Microsoft Agent Framework dominates narrative | 40% | LOW | SoulGraph is vendor-neutral, open-source, self-hosted. Different audience. | Fury |

---

## Appendix A: Pipeline Lead Alignment

From Hawkeye's pillar mapping (Mar 23):

| Pillar | T1 Leads | T2 Leads | % of Top Leads |
|--------|----------|----------|---------------|
| RAG | 5/5 active T1 | 4/13 T2 | 50% |
| Agentic | 3/5 active T1 | 3/13 T2 | 33% |
| Eval | 1/5 (partial) | 2/13 T2 | 17% |
| Fine-tuning | 1/5 | 2/13 T2 | 17% |

**Golden lead:** Deutsche Bank #26 — aligns on ALL FOUR pillars. Despite being T2 (match 77), deserves T1-level outreach quality.

## Appendix B: Competitive Positioning

From Fury's competitive scan (Mar 23):

**SoulGraph's niche:** No existing open-source project combines all four pillars in a single integrated system with shared state. The "code-first enterprise reference architecture" niche is empty.

**What to say:** "Most AI portfolios show you can call an API. SoulGraph proves you can architect a system."

**What NOT to say:**
- Don't say "better than CrewAI/AutoGen" — we build ON frameworks, not against them
- Don't say "enterprise-ready" until there's production usage
- Don't claim "the first" — hedge with "one of the first"

## Appendix C: Content Strategy Tie-In

4 pillars = 4 pillar articles = 45-54 derivative content pieces over 3 months.

| Phase | Content Milestone |
|-------|------------------|
| Phase 1 (Mar 27) | "Building a Multi-Agent RAG System from Scratch" (LinkedIn carousel) |
| Phase 2 (Apr 3) | "Production State Management for AI Agents" (LinkedIn deep-dive) |
| Phase 3 (Apr 11) | "The Complete Enterprise AI Agent Architecture" (anchor article) |
| Ongoing | Build-in-public series, eval reports, $0 GPU diaries |

Full content strategy: `~/soul-roles/shared/briefs/soulgraph-content-strategy.md`

---

*This PRD will be updated as phases ship and market feedback arrives. Next review: March 28 (post-Phase 1).*
