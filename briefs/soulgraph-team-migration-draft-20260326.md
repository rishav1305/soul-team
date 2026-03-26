# SoulGraph Team Migration — Draft (PARKED)

**Status:** Parked — awaiting SoulGraph maturity + deeper discussion
**Date:** March 26, 2026
**Participants:** CEO, Pepper, Fury, Shuri

---

## Problem

Agent context overflow across 10-agent team. Xavier at 251KB memory, Shuri crashed. Memory budgets are wrong answer — architecture must scale.

## CEO Decision

- **Full replacement** — SoulGraph replaces tmux + courier + filesystem entirely
- **No hybrid** — gaps in SoulGraph get filled, making it stronger
- **Convergent Runtime (Approach C)** — start process-orchestrated, converge to API-native per agent

## Agreed Architecture Direction

- `AgentNode` abstraction with two backends: `CLIAgent` (wraps Claude Code) and `APIAgent` (Anthropic API direct)
- Shared services: ChromaDB (memory), Redis (state), LangGraph (routing), FastAPI (API)
- Migration order: Banner first (simplest) → Xavier last (most complex)
- Each agent migrates independently when tool coverage reaches parity

## Phased Approach (Consensus)

| Phase | What | Timeline | Status |
|-------|------|----------|--------|
| Phase 0 | ChromaDB vector memory | TBD | Not started |
| Phase 1 | Redis state management | TBD | Not started |
| Phase 2 | LangGraph routing (replaces courier) | TBD | Not started |
| Phase 3 | Eval + fine-tuning | TBD | Not started |

## Team Assessments (Archived)

- **Pepper**: SoulGraph readiness 4/10, MVP as shared memory layer first
- **Fury**: Phase 0 alone buys 90% relief, dogfooding value is highest demo
- **Shuri**: 40% ready, 7 new components needed, 3-4 weeks estimate

## Open Questions (For Deeper Discussion)

- Agent-SoulGraph communication protocol design
- Tool handler coverage matrix per agent
- Process management layer (replaces tmux)
- Multi-machine orchestration (titan-pi + titan-pc)
- Other complexities CEO wants to explore when SoulGraph is more mature

---

*Parked by CEO on March 26, 2026. Resume when SoulGraph has matured.*
