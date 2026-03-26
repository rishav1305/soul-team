# Portfolio Enhancement Content Spec
**Author:** Loki | **Date:** March 26, 2026 | **Status:** PENDING PEPPER REVIEW
**Triggered by:** CEO P1 directive — add SoulGraph, soul-bench, soul-team; grow blog; deepen all projects
**Implements for:** Shuri + Happy (code), Pepper (decisions), CEO (final approval)

---

## Executive Summary

The portfolio at rishavchatterjee.com currently positions Rishav as a **data engineering** professional. The site subtitle reads "data engineering, analytics, and visualization." This directly contradicts the locked-in brand: **Senior AI Architect** specializing in LLM evaluation, agentic system design, and multi-agent orchestration.

**What's wrong:**
- 0 of 3 flagship AI projects (SoulGraph, soul-bench/CARS, soul-team) appear on the site
- Projects page subtitle says "data engineering, analytics, and visualization"
- personalInfo.title says "AI Engineer | AI Consultant | AI Researcher" (should be "Senior AI Architect")
- domainExpertise list is pharma/retail/supply-chain heavy — no mention of LLM evaluation, agent orchestration, or AI research
- 11 current projects skew heavily toward Polestar/Novartis data work (2018-2022)
- Only 1 blog post exists (2-model CARS comparison) — but 3+ articles are in pipeline
- GitHub links missing from all project pages (SoulGraph and soul-bench are public MIT repos)

**What this spec delivers:**
- 2 new custom project pages (SoulGraph, soul-bench/CARS) modeled on the GOAT reference template
- 1 Pepper decision on soul-team page (include or skip)
- Updated projects page copy and ordering
- Updated personalInfo and domainExpertise
- Blog growth roadmap with 3 articles in pipeline
- Supabase data entries for all new projects
- Implementation brief for Shuri/Happy with exact component specs

---

## TIER 1: New Custom Project Pages

### 1A. SoulGraph — Multi-Agent AI System

**Route:** `/projects/soulgraph`
**Template:** Custom dedicated page (like goat-agentic-ai, ~350-400 lines)
**GitHub:** https://github.com/rishav1305/soulgraph (MIT license)

#### Hero Section
- **Badge:** `Open Source Research`
- **Title:** SoulGraph / Multi-Agent AI System
- **Subtitle:** "Production-grade multi-agent orchestration on LangGraph — supervisor routing, RAG retrieval, tool execution, and automated quality evaluation. 91 tests, 91% coverage."
- **Date:** March 2026 - Present

#### Metrics Cards (4)
| Value | Label | Sub |
|-------|-------|-----|
| 91 | Tests Passing | full CI pipeline |
| 91% | Code Coverage | across all modules |
| 4 | Agent Types | supervisor + 3 specialists |
| <200ms | First Token | streaming WebSocket |

#### Executive Summary
> A batteries-included LangGraph multi-agent service. Feed it documents and a question — it returns a grounded, multi-agent answer with automated quality evaluation using RAGAS metrics. Built as a public reference implementation for production multi-agent systems.

#### Problem & Solution (2-column)
**Problem:** Most multi-agent demos are toy examples — single-file scripts, no state management, no evaluation, no production path. Engineers evaluating agent frameworks have no reference for what "production-grade" looks like.

**Solution:** A fully-tested, observable, production-ready multi-agent system with real infrastructure: Redis state bus, ChromaDB vector store, LiteLLM model routing, dual tracing (LangSmith + LangFuse), FastAPI REST + WebSocket streaming.

#### Capabilities (3 items)
1. **RAG-Grounded Answers** — ChromaDB vector retrieval over HotpotQA dataset. Context-window-aware chunking. Answers grounded in retrieved documents, not model hallucination. (gold border)
2. **Automated Quality Evaluation** — RAGAS metrics (faithfulness, relevance, context precision) computed on every response. Structured EvalReport with JSON + HTML output. Quality scores travel with the answer. (blue border)
3. **Tool Execution with Safety** — AST-based calculator agent with safe evaluation (no eval/exec). Tool dispatch pattern extensible to any function. Sandboxed execution prevents code injection. (green border)

#### Architecture Section — "Why LangGraph?"
4 cards:
1. **State Graph Routing** — Supervisor routes by intent. Each agent is a node. State flows through typed edges. No spaghetti chains — the graph IS the control flow.
2. **Streaming First** — `astream()` delivers tokens as they generate. WebSocket endpoint pushes to clients in real-time. No blocking on full response.
3. **Observable by Default** — LangSmith + LangFuse dual tracing. Every agent call, every retrieval, every evaluation logged with latency and token counts.
4. **Self-Hosted Everything** — Redis + ChromaDB + LangFuse all run via Docker Compose. Zero cloud dependencies at runtime. Sovereign by design.

#### Architecture Diagram (text-based, styled)
```
User Query → Supervisor (intent routing)
                ├→ RAG Agent (ChromaDB + HotpotQA) → answer
                ├→ Tool Agent (AST calculator) → computation
                └→ Evaluator Agent (RAGAS metrics) → quality report
                        ↓
                Redis State Bus (pub/sub + checkpoints)
```

#### Module Structure (6-item grid, like DATA_MODEL in GOAT)
| Module | Description | Color |
|--------|-------------|-------|
| supervisor.py | StateGraph supervisor with intent routing | gold |
| agents/rag.py | ChromaDB retrieval + answer generation | blue |
| agents/evaluator.py | RAGAS metrics, structured EvalReport | green |
| agents/tool_agent.py | Safe AST calculator + tool dispatch | purple |
| router.py | LiteLLM model router (cloud + vLLM) | amber |
| checkpoint.py | Redis checkpointer with graceful fallback | pink |

#### Workflow Steps (5)
1. **Document Ingestion** — Seed ChromaDB with HotpotQA dataset via embedding pipeline
2. **Query Submission** — REST API or WebSocket. Query enters the supervisor node
3. **Intent Routing** — Supervisor classifies intent: retrieval, calculation, or mixed
4. **Agent Execution** — Specialist agent(s) execute. RAG retrieves, Tool computes, results aggregate
5. **Quality Evaluation** — Evaluator agent scores the response. RAGAS metrics + EvalReport returned alongside the answer

#### Tech Stack Pills
`Python` `LangGraph` `LangChain` `ChromaDB` `Redis` `FastAPI` `LiteLLM` `RAGAS` `LangSmith` `LangFuse` `Docker` `pytest` `WebSocket` `vLLM`

#### Learnings Section — "What This Proves"
- **Supervisor-pattern scales to real workloads** — Same pattern used in GOAT (5,000+ users) works for research and production. Decompose → route → aggregate is the canonical multi-agent pattern.
- **Evaluation must be first-class, not afterthought** — Building RAGAS evaluation INTO the response pipeline (not as a separate tool) catches quality issues before they reach users.
- **Infrastructure matters more than model choice** — Redis checkpoints, LiteLLM routing, and dual tracing solve 80% of "why doesn't my agent work in production?" complaints. The model is the easy part.

#### CTA
"Need a multi-agent system built for production?" → Book AI Consultation | View on GitHub

#### Schema Markup (JSON-LD)
```json
{
  "@type": "SoftwareApplication",
  "name": "SoulGraph",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Linux",
  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" },
  "author": { "@type": "Person", "name": "Rishav Chatterjee" },
  "codeRepository": "https://github.com/rishav1305/soulgraph"
}
```

---

### 1B. soul-bench / CARS Benchmark Framework

**Route:** `/projects/soul-bench`
**Template:** Custom dedicated page (~350-400 lines)
**GitHub:** TBD — currently in Gitea under soul-old. **PEPPER DECISION: Does soul-bench get its own public GitHub repo?** If yes, Shuri creates. If no, link to soulgraph or omit GitHub link.

#### Hero Section
- **Badge:** `AI Research`
- **Title:** soul-bench / CARS Benchmark
- **Subtitle:** "LLM evaluation framework with the CARS efficiency metric — 52 models, 7 providers, 10 task categories, 7 scoring methods. Because a model that's 95% as good at 10% the cost is often the right choice."
- **Date:** February 2026 - Present

#### Metrics Cards (4)
| Value | Label | Sub |
|-------|-------|-----|
| 52 | Models Benchmarked | across 7 providers |
| 10 | Task Categories | from production workloads |
| 39 | Tests Passing | framework validation |
| 160x | Efficiency Gap | between best and worst CARS |

#### Executive Summary
> Most LLM benchmarks test accuracy in isolation. CARS (Cost-Adjusted Relative Score) asks the harder question: which model gives the best answer per dollar of compute? 52 models, 7 providers, 30 prompts across 10 real-world task categories. The results challenge conventional model rankings.

#### Problem & Solution
**Problem:** Accuracy-only benchmarks mislead. A 3B model that scores 79% in 1.4 seconds costs radically less than a frontier model scoring 85% in 4.7 seconds. Current evaluation frameworks (MMLU, HumanEval, LMSYS) ignore resource cost entirely.

**Solution:** CARS normalizes accuracy against resource consumption. Three variants for different deployment targets: CARS_Size (any hardware), CARS_VRAM (GPU), CARS_RAM (CPU). Higher = better value. One number that captures "is this model worth it?"

#### CARS Formula (styled code block)
```
CARS_Size = Accuracy / (Model_Size_GB x Latency_s)
CARS_VRAM = Accuracy / (Peak_VRAM_GB x Latency_s)
CARS_RAM  = Accuracy / (Peak_RAM_GB x Latency_s)
```

#### Key Findings (4 cards, pull from Banner data)
1. **o3 Takes #1** — 85% strict accuracy, 0pp format tax, 4.72s latency. The only frontier model where what it knows and how it formats are perfectly aligned. (gold)
2. **20B Open-Source Beats GPT-4o** — GPT-OSS 20B scores 79.4% strict vs GPT-4o's 77.8%. Open-source models are not just catching up — they've passed the previous generation. (blue)
3. **The Format Tax Is Real** — Average 14pp gap between strict and relaxed scoring across 52 models. Claude Haiku 4.5 loses 23.3pp to formatting alone — the most capable model that can't follow instructions. (green)
4. **Progress Isn't Monotonic** — GPT-5 regressed to 56.7% (below GPT-3.5). GPT-5.2 recovered to 78.2% but introduced 13.3pp format tax. Upgrading models blindly breaks things. (red/amber)

#### 10 Task Categories (grid, like DATA_MODEL)
| Category | What It Tests |
|----------|--------------|
| System Health | JSON diagnosis from system snapshots |
| Code Generation | Python functions that compile and run |
| Email Drafting | Structured email from template + contact data |
| Contact Research | Enrichment JSON from name + company |
| Knowledge QA | Factual extraction from provided context |
| Task Planning | Task assignment from agent roster |
| Classification | Single-label content classification |
| Campaign Planning | Correct CLI pipeline step ordering |
| Reply Classification | Email reply intent (incl. adversarial injection) |
| Infra Management | Infrastructure diagnosis with required terms |

#### 7 Scoring Methods (compact list)
`json_schema` `contains_keywords` `code_executes` `ordered_steps` `exact_match_label` `exact_match_number` `contains_function`

All return fractional scores (0.0-1.0). Partial credit, not binary pass/fail.

#### Top 10 Leaderboard (styled table)
| # | Model | Strict | Relaxed | Format Tax | Latency |
|---|-------|--------|---------|------------|---------|
| 1 | o3 | 85.0% | 85.0% | 0pp | 4.72s |
| 2 | GPT-OSS 20B | 79.4% | 85.7% | 6.3pp | 1.61s |
| 3 | Nova Micro (3B) | 79.0% | 79.4% | 0.4pp | 1.42s |
| 4 | GPT-5.2 | 78.2% | -- | -- | -- |
| 5 | GPT-4o | 77.8% | 82.7% | 4.9pp | 1.35s |
| 6 | GPT-3.5 Turbo | 75.7% | 75.7% | 0pp | 0.79s |
| 7 | Claude 3.5 Sonnet | 71.2% | 85.0% | 13.8pp | 2.18s |
| 8 | Gemini 3 Flash | 69.7% | 82.3% | 12.6pp | 1.89s |
| 9 | GPT-4.1-nano (8B) | 67.0% | 83.0% | 16.0pp | 1.54s |
| 10 | Claude Haiku 4.5 (8B) | 62.1% | 85.4% | 23.3pp | 2.12s |

#### Workflow Steps (4)
1. **Define Prompts** — 30 task prompts across 10 categories, each with expected output schema
2. **Run Benchmark** — `benchmark.py` executes each prompt, captures accuracy, latency, resource consumption
3. **Score Responses** — 7 scoring methods evaluate output quality with fractional partial credit
4. **Compute CARS** — Normalize accuracy against resource cost. Rank models by efficiency, not just accuracy.

#### Tech Stack Pills
`Python` `llama.cpp` `llama-cpp-python` `Google Colab` `pytest` `JSON Schema` `GGUF` `vLLM`

#### Learnings
- **Accuracy alone is a lie** — CARS reveals a 160x efficiency gap between the best and worst models. Rankings change completely when you factor in cost.
- **Format compliance is a separate capability** — Some models know the answer but can't format it. The 14pp average format tax means strict production use cases must evaluate differently.
- **Adversarial testing catches real failures** — The prompt injection test in reply classification found models that score 100% on normal inputs but fail on adversarial ones.

#### CTA
"Want to evaluate LLMs for your use case?" → Book AI Consultation | Read the CARS Article

#### Schema Markup
```json
{
  "@type": "SoftwareApplication",
  "name": "soul-bench",
  "applicationCategory": "DeveloperApplication",
  "description": "LLM evaluation framework with CARS efficiency metric"
}
```

---

### 1C. Soul Team — Multi-Agent Coordination System

**PEPPER DECISION REQUIRED — 3 OPTIONS:**

**Option A: Full Architecture Page (RECOMMENDED)**
- Focus on ARCHITECTURE and COORDINATION patterns (per guardrail)
- 9 specialized agents, distributed across 2 machines, real-time messaging, task routing
- Frame as: "How I architect and operate production multi-agent teams"
- DO NOT reveal: personal use cases (job search, trading, outreach specifics)
- DO NOT name: Scout, Stark trading details, lead pipeline data
- DO show: agent roles (brand, strategy, data science, engineering, PM), coordination patterns, infrastructure (tmux, inbox, heartbeat)
- Route: `/projects/soul-team`

**Option B: Combined with SoulGraph**
- Add a "From Research to Production" section on the SoulGraph page
- Brief mention that the same patterns power a 9-agent production system
- Less disclosure, less separate content

**Option C: Skip**
- soul-team is private infrastructure, not a product
- Focus portfolio on SoulGraph (open source) and soul-bench (research)
- soul-team mentioned in passing on about/bio page only

**Loki's recommendation:** Option A. This is the strongest signal for "Senior AI Architect" positioning. No competitor has a live 9-agent coordination system they can point to. The architecture alone — without revealing personal use cases — is a portfolio piece that outweighs most candidates' entire project sections. Guardrails are enforceable: talk about HOW agents coordinate, not WHAT they coordinate on.

If Pepper selects Option A, I will write the full content spec with the same depth as SoulGraph/soul-bench above.

---

## TIER 2: Projects Page & Global Updates

### 2A. Projects Page Copy Update

**Current subtitle:** "data engineering, analytics, and visualization"
**Proposed subtitle:** "AI systems architecture, LLM evaluation, and multi-agent orchestration"

**Current description (from page.tsx):**
> "Explore my portfolio of data engineering, analytics, and visualization projects..."

**Proposed description:**
> "Production AI systems — from multi-agent orchestration to LLM evaluation frameworks. Enterprise deployments serving thousands of users alongside open-source research tools."

### 2B. Project Ordering

**Current:** Appears to use Supabase `order` or insertion order. GOAT is first.

**Proposed ordering (AI-forward, recency-weighted):**

| Position | Project | Rationale |
|----------|---------|-----------|
| 1 | GOAT Agentic AI Platform | Flagship enterprise, 5K+ users, Fortune 500 |
| 2 | SoulGraph | Open source, public proof anchor, active |
| 3 | soul-bench / CARS Benchmark | Research credibility, 52-model data |
| 4 | Soul Team* | (If Pepper approves Option A) |
| 5 | Enterprise Data Quality Framework | IBM-TWC, ongoing |
| 6 | AI-Powered Portfolio Website | Meta-project, demonstrates AI tooling |
| 7 | Profile Builder with Local LLM | AI/LLM project |
| 8-11 | Remaining projects | Chronological within category |

### 2C. Category Updates

**Current categories in data:** "Ongoing", "Completed"

**Proposed categories:**
- **AI & Agents** — GOAT, SoulGraph, soul-bench, Soul Team, Profile Builder
- **Data Engineering** — Data Quality Framework, Data Integration Pipeline, Production Pipelines
- **Analytics** — Forecasting Dashboards, Process Automation, Data Wrangling
- **Tools** — Portfolio App, DSA Tracker

### 2D. personalInfo Updates

**title:** `"AI Engineer | AI Consultant | AI Researcher"` → `"Senior AI Architect"`
(CEO decision #8, locked Mar 22)

**shortBio:** Update to align with current positioning:
> "I architect production AI systems — multi-agent orchestration, LLM evaluation, RAG pipelines — for enterprises and open-source. GOAT platform (5,000+ users, Fortune 500), SoulGraph (open-source multi-agent framework), CARS benchmark (52-model evaluation). 8+ years of Python and data platform engineering."

**domainExpertise:** Replace current list with:
```
[
  "Multi-Agent Orchestration",
  "LLM Evaluation & Benchmarking",
  "RAG Pipeline Architecture",
  "Agentic AI Systems",
  "Production AI Infrastructure",
  "Enterprise AI Consulting",
  "Healthcare AI",
  "Cloud Infrastructure (AWS)",
  "Data Platform Engineering",
  "Conversational AI"
]
```

---

## TIER 3: Blog Growth Plan

### Current State
- 1 published blog post: `/blog/cars-benchmark` (2-model CARS comparison)
- Blog system: Markdown in `content/blog/`, parsed by `src/lib/markdown.ts`
- BlogPosting + FAQPage JSON-LD schema already deployed

### Pipeline (in priority order)

| # | Article | Status | Target Publish | Slug |
|---|---------|--------|---------------|------|
| 1 | Anchor Article: Enterprise Multi-Agent | CEO REVIEW SUBMITTED | Mar 28-30 | `enterprise-multi-agent-systems` |
| 2 | CARS 52-Model Benchmark | DRAFT v2 COMPLETE | Apr 1-2 (hard deadline Apr 3) | `cars-52-model-benchmark` |
| 3 | The Format Tax | OUTLINE READY | Week 3 (Apr 7+) | `format-tax-llm-evaluation` |
| 4 | MCP in Multi-Agent Production | CEO GATE (P2) | Apr 2-3 | `mcp-multi-agent-production` |
| 5 | The Hidden Cost of Upgrading LLMs | CEO GATE (P3) | Apr 8 | `hidden-cost-upgrading-llms` |

### Blog Section Enhancements Needed
- Blog listing page currently shows minimal metadata — add reading time, category tags
- Add "Featured" badge for anchor/CARS articles
- Internal linking between blog posts and project pages (e.g., CARS article links to soul-bench project page)
- Blog RSS feed for syndication
- OG image generation for social sharing

---

## TIER 4: Implementation Brief for Shuri/Happy

### What to Build

#### Phase 1: Data Layer (Happy — Supabase entries)
1. Add 2-3 new rows to `projects` table in Supabase:
   - SoulGraph (category: "AI & Agents", link: "projects/soulgraph")
   - soul-bench (category: "AI & Agents", link: "projects/soul-bench")
   - Soul Team (category: "AI & Agents", link: "projects/soul-team") — IF Pepper approves
2. Update `site_config` table: title field → "Senior AI Architect"
3. Update `projects` table: reorder existing projects per 2B
4. Update category values on existing project rows per 2C

#### Phase 2: Custom Pages (Shuri — Next.js code)
1. **`/src/app/projects/soulgraph/page.tsx`** (~350-400 lines)
   - Clone GOAT template structure: Hero → Metrics → Executive Summary → Problem/Solution → Capabilities → Architecture → Module Grid → Workflow → Tech Stack → Learnings → CTA
   - All content provided in this spec (Section 1A above)
   - Add GitHub external link button in hero (opens in new tab)
   - Add JSON-LD SoftwareApplication schema in head

2. **`/src/app/projects/soul-bench/page.tsx`** (~350-400 lines)
   - Same template structure
   - All content provided in this spec (Section 1B above)
   - Special component: CARS Formula styled code block
   - Special component: Leaderboard table (styled, sortable would be bonus)
   - Add JSON-LD schema in head

3. **`/src/app/projects/soul-team/page.tsx`** — CONDITIONAL on Pepper decision

#### Phase 3: Global Updates (Happy)
1. Update `portfolioData.ts`:
   - `personalInfo.title` → "Senior AI Architect"
   - `personalInfo.shortBio` → new copy from 2D
   - `personalInfo.domainExpertise` → new list from 2D
   - Add SoulGraph and soul-bench to `projects` array (needed for slug matching on custom pages)
2. Update projects page subtitle in `/src/app/projects/page.tsx`

#### Phase 4: Blog Enhancements (Happy)
1. Add reading time estimation to blog listing
2. Add category tags to blog posts
3. Ensure internal links work between project pages and blog posts

### Design Patterns (from GOAT reference)
- **Background:** `bg-[#020617]` (deepest navy)
- **Cards:** `bg-[#0F172A]` with `border-[#1E293B]`
- **Gold accent:** `#CA8A04` for badges, metrics, section labels
- **Blue accent:** `#3B82F6` for secondary highlights
- **Green accent:** `#22C55E` for third color
- **Font:** Fraunces for headings (`var(--font-fraunces)`), system for body
- **Sections:** uppercase tracking-widest gold labels above serif headings
- **Grid:** `max-w-5xl mx-auto px-6` container

### Branch Strategy
- `feat/portfolio-soulgraph-page`
- `feat/portfolio-soul-bench-page`
- `feat/portfolio-global-updates`
- Merge order: global updates → soulgraph → soul-bench (each independently testable)

---

## PEPPER DECISION POINTS

| # | Question | Options | Loki's Rec | Deadline |
|---|----------|---------|------------|----------|
| P1 | Soul Team project page? | A: Full arch page / B: Combined w/ SoulGraph / C: Skip | A | Before impl starts |
| P2 | soul-bench GitHub repo? | Create public repo / Link to Gitea / Omit link | Create public repo | Before soul-bench page |
| P3 | Project ordering on /projects? | AI-forward (proposed) / Keep current / Other | AI-forward | With global updates |
| P4 | De-emphasize old projects? | Archive Polestar projects / Keep all / Move to "legacy" | Keep all, just reorder | With global updates |
| P5 | Blog enhancements scope? | Full (reading time, tags, RSS, OG) / Minimal / Defer | Full | Week 2 |

---

## GUARDRAIL COMPLIANCE CHECK

| Guardrail | Status | How Enforced |
|-----------|--------|-------------|
| No Scout pipeline details | CLEAN | soul-team page (if built) focuses on architecture only |
| No specific lead data | CLEAN | No company names or pipeline data in any project page |
| No trading details | CLEAN | Stark agent described as "financial analysis" only |
| No Gartner name | CLEAN | GOAT page already uses "Fortune 500 analytics company" |
| Agent content = architecture focus | ENFORCED | soul-team page focuses on coordination patterns, not use cases |
| soul-bench not "open source" | STALE — Pepper confirmed MIT/public | Will say "MIT license, public on GitHub" |
| Check CEO before Gartner details | ENFORCED | GOAT page content unchanged from current approved version |

---

## TIMELINE

| Phase | What | Who | Target |
|-------|------|-----|--------|
| Review | Pepper reviews this spec, makes P1-P5 decisions | Pepper | Mar 27 |
| Phase 1 | Supabase data entries | Happy | Mar 28 |
| Phase 2a | SoulGraph custom page | Shuri | Mar 29-30 |
| Phase 2b | soul-bench custom page | Shuri | Mar 30-31 |
| Phase 3 | Global updates (title, bio, ordering) | Happy | Mar 31 |
| Phase 4 | Blog enhancements | Happy | Apr 1-3 |
| QA | CEO reviews live site | CEO | Apr 3-4 |

**Dependencies:**
- Phase 2 blocked on Pepper P1-P5 decisions
- soul-bench page blocked on P2 (GitHub repo decision)
- soul-team page blocked on P1 (disclosure decision)
- Blog content blocked on CEO article reviews (anchor article, CARS article)

---

## SUPABASE DATA ENTRIES

### SoulGraph Project Row
```json
{
  "title": "SoulGraph — Multi-Agent AI System",
  "short_description": "Production-grade multi-agent orchestration on LangGraph with RAG retrieval, tool execution, and automated quality evaluation.",
  "description": "Open-source LangGraph multi-agent service with supervisor routing, ChromaDB RAG, RAGAS evaluation, Redis state bus, and FastAPI streaming. 91 tests, 91% code coverage. Built as a reference implementation for production multi-agent systems.",
  "image": "/images/projects/thumbnail/soulgraph.png",
  "tech_stack": ["Python", "LangGraph", "LangChain", "ChromaDB", "Redis", "FastAPI", "LiteLLM", "RAGAS", "Docker", "pytest", "WebSocket"],
  "category": "AI & Agents",
  "company": "Personal Project",
  "link": "projects/soulgraph",
  "start_date": "2026-03-01",
  "end_date": null,
  "github_url": "https://github.com/rishav1305/soulgraph",
  "order": 2
}
```

### soul-bench Project Row
```json
{
  "title": "soul-bench / CARS Benchmark",
  "short_description": "LLM evaluation framework with the CARS efficiency metric — 52 models, 7 providers, 10 task categories.",
  "description": "Benchmark framework evaluating LLMs across 10 production-derived task categories using the CARS (Cost-Adjusted Relative Score) metric. 52 models benchmarked, 7 scoring methods, adversarial testing. Reveals a 160x efficiency gap between best and worst models.",
  "image": "/images/projects/thumbnail/soul-bench.png",
  "tech_stack": ["Python", "llama.cpp", "Google Colab", "pytest", "JSON Schema", "GGUF", "vLLM"],
  "category": "AI & Agents",
  "company": "Personal Project",
  "link": "projects/soul-bench",
  "start_date": "2026-02-01",
  "end_date": null,
  "order": 3
}
```

### Thumbnail Images Needed
- `/public/images/projects/thumbnail/soulgraph.png` — Architecture diagram or agent graph visualization
- `/public/images/projects/thumbnail/soul-bench.png` — CARS leaderboard visualization or metric formula graphic

**NOTE:** These can be generated from the existing Banner charts at `~/soul-roles/shared/briefs/banner-analyses/` or created new by Shuri using the carousel pipeline.

---

*End of spec. Route to Pepper for P1-P5 decisions, then to Shuri/Happy for implementation.*
