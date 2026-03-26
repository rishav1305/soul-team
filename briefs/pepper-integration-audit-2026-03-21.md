# Cross-Product Integration Audit — 2026-03-21

## Architecture Overview

Soul v2 operates a **hub-spoke model**:
- **Hub:** Chat server (port 3002) — routes tool calls to product REST APIs via `context/dispatch.go`
- **Spokes:** 13 independent product servers, each with their own port and binary

When Soul v2 is down, **ALL chat-based product access is blocked** — not just chat.

## Product Server Status Matrix

| Product | Port | Binary | Status | Tool Count | Notes |
|---------|------|--------|--------|------------|-------|
| Chat (hub) | 3002 | soul-chat | ⛔ DOWN | 8 built-in | P0 blocker |
| Tasks | 3004 | soul-tasks | ❓ Unknown | 6 | Task management |
| Tutor | 3006 | soul-tutor | ✅ LIVE | 7 | 137 topics, 0% usage |
| Projects | 3008 | soul-projects | ❓ Unknown | 6 | Skill-building |
| Observe | 3010 | soul-observe | ❓ Unknown | 4 | Pillar metrics |
| Infra | 3012 | soul-infra | ❓ Unknown | 6 | DevOps/DBA/Migrate |
| Quality | 3014 | soul-quality | ❓ Unknown | 8 | Compliance engine |
| Data | 3016 | soul-data | ❓ Unknown | 6 | DataEng/Viz |
| Docs | 3018 | soul-docs | ❓ Unknown | 4 | Documentation |
| Scout | 3020 | soul-scout | ⛔ DOWN | 55 | Pipeline CRM |
| Sentinel | 3022 | soul-sentinel | ❓ Unknown | 7 | CTF platform |
| Mesh | 3024 | soul-mesh | ❓ Unknown | 4 | Distributed compute |
| Bench | 3026 | soul-bench | ❓ Unknown | 4 | LLM benchmarking |

**Total product tools: 127** (119 product + 8 built-in)

## Cross-Product Wiring Status

### Verified Integrations
1. **Chat → Tutor:** Wired via `context/tutor.go` → `dispatch.go`. Tutor tools (7) dispatch to port 3006 REST API. **Would work if chat was up.**
2. **Chat → Scout:** Wired via `context/scout.go` → `dispatch.go`. Scout tools (55) dispatch to port 3020 REST API. **Blocked — both down.**
3. **Chat → Tasks:** Wired via `dispatch.go`. Task tools dispatch to port 3004.

### Missing Integrations
1. **Xavier ↔ Scout:** No code-level integration. Xavier operates Tutor independently; Hawkeye operates Scout independently. They communicate via inboxes only.
2. **Loki ↔ Scout:** No automated content→pipeline feedback loop. Loki generates content; Scout tracks leads. No data flows between them.
3. **Banner ↔ Any Product:** No analytics ingestion pipeline. Banner would need to manually query each product's API.

### Architecture Notes
- Products use **env-var-based service discovery** (e.g., `SOUL_SCOUT_URL=http://127.0.0.1:3020`)
- Each product has its own SQLite database (tutor.db, scout.db, etc.)
- No shared auth between product servers — auth is on the chat hub only
- No service mesh — direct HTTP calls between processes

## Product Gaps Identified

1. **No cross-product data flow** — each product is an island. Xavier can't see Scout leads; Hawkeye can't see Tutor readiness.
2. **No shared health endpoint** — `make serve` starts all 13 servers but no central health check aggregates their status.
3. **No systemd units for product servers** — Tutor runs from /tmp, fragile. Scout has no running process.
4. **Hub dependency is absolute** — if chat goes down, no product is accessible via the primary UI. Products should have standalone UIs too.

## Recommendations

### Immediate (This Sprint)
- Restore Soul v2 chat server (P0)
- Verify all product servers needed for current sprint can start

### Next Sprint
- Create systemd units for Tutor, Scout, Tasks at minimum
- Add health check aggregation endpoint to chat server
- Add `/` root handler to Tutor (returns info instead of 404)

### Backlog
- Evaluate cross-product data APIs (e.g., Scout lead data available to Tutor for interview context)
- Consider standalone product UIs for critical products
- Propose product health dashboard to Banner

— Pepper (CPO)
