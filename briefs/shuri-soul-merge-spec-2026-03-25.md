---
from: shuri
to: team-lead (CEO)
date: 2026-03-25
type: architecture-spec
status: READY FOR CEO REVIEW
---

# Soul v1/v2 Merge — Architecture Spec

## TL;DR

- **Keep**: v2 backend unchanged (46 packages, 13 servers, tested)
- **Replace**: v2's router-based SPA with v1's AppShell panel layout
- **Rename**: module path + directory to ~/soul/
- **Chat decision**: INVEST (crashes are titan-pi reboots, not chat bugs)
- **Timeline**: 3 phases, 2 weeks aggressive

---

## 1. Chat Decision: INVEST

**What Pepper reported:** 0 sessions / 4 days, 31% of alerts, 6 crashes.

**What the logs actually show:**

```
-- Boot cb5fe5a... --    # titan-pi reboot
-- Boot 482db59... --    # titan-pi reboot
-- Boot baf12b2... --    # titan-pi reboot (3 reboots just today)
-- Boot cc7fb8c... --    # titan-pi reboot
```

The "6 crashes" are **system-level watchdog reboots** (GNOME + agent CPU contention on
titan-pi — documented root cause). Chat starts cleanly after every reboot with no panics,
no fatals, no application-level errors. Service is healthy.

"0 sessions in 4 days" = the web UI at :3002 is not being accessed, not that chat is
broken. Probable reason: CEO is using soul (v1) at :3000, not soul-v2 at :3002. After the
merge, there is only one interface — this metric disappears.

**Decision: INVEST.** No chat code needs fixing. The 31% of alerts are system restart
noise (the pane noise reduction spec already deploys fixes for this). Chat is the
interaction layer for all 21 products in v2 — hibernating it would require rearchitecting
the entire product.

---

## 2. Merge Approach: Frontend-Only Swap

Two options considered:

| Option | Scope | Risk | Timeline |
|--------|-------|------|----------|
| A: Frontend-only swap | Replace web/src/ with v1 UI, keep all of internal/ | Low | 2 weeks |
| B: Full backend merge | Rewrite 13 Go servers into one v1-style binary | High | 6-8 weeks |

**Recommendation: Option A.**

v2's backend is proven (46 packages, 0 failures). v1's UI is purely frontend — it can run
on top of v2's REST + WebSocket API with adapter hooks where needed. Option B introduces
risk without benefit; the CEO keeps v1's UI either way.

### What stays (v2 backend — do not touch):

```
~/soul/
  cmd/                    All 13 server entrypoints (unchanged)
  internal/               All Go packages (unchanged, ~40k lines)
    chat/                 Server, session, stream, ws, metrics, context
    tasks/                Server, store, executor, hooks, phases, gates
    tutor/                Server, store, modules, eval
    scout/                Server, store, ai, sweep, runner, pipelines
    observe/              Server (stubs → real data, separate sprint)
    projects/, infra/, quality/, dataprod/, docsprod/
    sentinel/, mesh/, bench/, mcp/
  tests/                  All test suites (unchanged)
  go.mod → module github.com/rishav1305/soul  (renamed)
  Makefile                (unchanged except module reference)
```

### What changes (v1 UI replaces v2 UI):

```
~/soul/web/src/
  REMOVED:  pages/           (router-based: ChatPage, TutorPage, etc.)
  REMOVED:  router.tsx        (React Router — v1 doesn't use routing)
  KEPT:     hooks/            (all API hooks work as-is — call same endpoints)
  KEPT:     lib/types.ts      (generated from specs)
  KEPT:     lib/api.ts, ws.ts (endpoint callers — unchanged)

  NEW (ported from v1):
    components/layout/
      AppShell.tsx            Main layout (ProductRail + HorizontalRail + ProductView)
      ProductRail.tsx         Left sidebar — product navigation
      HorizontalRail.tsx      Chat + Tasks panel (configurable top/bottom/right)
      RightPanel.tsx          Right panel variant
      ProductView.tsx         Main content area (routes to product-specific views)
      SessionsDrawer.tsx      Chat sessions slide-out
      SplashScreen.tsx        Connection loading state
      ToastStack.tsx          Notifications
    components/chat/
      ChatPanel.tsx           Chat interface (uses existing useChat hook)
      ChatView.tsx            Message list + input
      Message.tsx, ToolCall.tsx, CodeBlock.tsx, etc.
    components/planner/
      KanbanBoard.tsx         Tasks kanban (uses existing useTasks hook)
      TaskCard.tsx, TaskDetail.tsx, TaskPanel.tsx
    hooks/
      useLayoutStore.ts       Panel layout state (v1's flexible panel positions)
      useProductContext.ts    Product context injection for chat
      useChatSessions.tsx     Multi-session management
      useNotifications.ts     Toast notifications from task events
```

### What gets dropped (v2 UI that doesn't exist in v1):

v2 has product-specific pages: ScoutPage, TutorPage, ObservePage, SentinelPage, etc.
In the merged product, each product becomes a **ProductView panel** within AppShell,
not a separate route. This matches how v1 worked. The product content still exists —
it just renders inside ProductView instead of a routed page.

---

## 3. Module Rename

**Current:** `github.com/rishav1305/soul-v2`
**Target:** `github.com/rishav1305/soul`

Impact: every `.go` file with an import path. Mechanical change.

```bash
# Rename procedure (Stark runs this):
go mod edit -module github.com/rishav1305/soul
find . -name '*.go' -exec sed -i 's|github.com/rishav1305/soul-v2|github.com/rishav1305/soul|g' {} +
go build ./...
go test -race ./...
```

Zero architecture changes. Pure search-and-replace.

---

## 4. Directory Setup

```bash
# Create ~/soul/ from ~/soul-v2/ (Shuri, Phase 1):
cp -r ~/soul-v2/ ~/soul/
cd ~/soul/

# Rename module
go mod edit -module github.com/rishav1305/soul
find . -name '*.go' -exec sed -i 's|github.com/rishav1305/soul-v2|github.com/rishav1305/soul|g' {} +

# Update binary names in Makefile
sed -i 's/soul-v2/soul/g' Makefile

# Verify
go build ./...
go test -race ./...
```

The existing ~/soul/ on titan-pi (v1) moves to ~/soul-v1-archive/ first.

---

## 5. Public Repo Prep (No Secrets)

Before publishing to GitHub:

```
REMOVE from repo:
  - Any .env files or examples with real keys
  - soul-v2.env, ~/.soul-v2/ data directory references in docs
  - Internal IP addresses in READMEs
  - Any hardcoded API keys, tokens, bearer strings

KEEP private (gitignore):
  ~/.soul/          Data directory (planner.db, tutor.db, scout.db — all user data)
  Any *.env files
  credentials.json

SAFE to publish:
  All Go source (no secrets — env vars only)
  All React/TypeScript (no secrets)
  CLAUDE.md, docs/, specs/
  Makefile, go.mod, go.sum
  README (write clean version)
```

Banner runs the data audit. Shuri reviews and signs off.

---

## 6. Sprint Plan

### Phase 1: Foundation (3 days)

| Task | Owner | Effort | Dependencies |
|------|-------|--------|--------------|
| Archive ~/soul/ to ~/soul-v1-archive/ | Shuri | 30 min | — |
| Create ~/soul/ from ~/soul-v2/ | Shuri | 1 hr | ^ |
| Module rename + verify 46 packages | Stark | 2-3 hrs | ^ |
| Data audit — scan for secrets/private data | Banner | 2-3 hrs | ^ |
| Chat crash investigation | Shuri | 1 hr | — (done: it's system reboots, not chat) |
| Update Makefile + binary names | Shuri | 30 min | module rename |
| Push ~/soul/ to Gitea (private) | Shuri | 30 min | P1 complete |

**Phase 1 exit criteria:** `go test -race ./...` passes in ~/soul/, no secrets found.

### Phase 2: UI Migration (7 days)

| Task | Owner | Effort | Dependencies |
|------|-------|--------|--------------|
| Port AppShell + ProductRail layout | Happy | 2 days | P1 complete |
| Port HorizontalRail (chat + tasks panels) | Happy | 2 days | AppShell done |
| Port ChatPanel + all chat components | Happy | 1 day | HorizontalRail done |
| Port KanbanBoard + TaskCard + TaskDetail | Happy | 1 day | HorizontalRail done |
| Wire v1 layout hooks (useLayoutStore) | Happy | 1 day | components done |
| Review all Happy PRs, fix integration | Shuri | 2 days | continuous |
| Adapt product views to ProductView panel | Shuri | 1 day | P2 complete |

**Phase 2 exit criteria:** `cd web && npx vite build` passes, AppShell renders all products, chat and tasks panels work.

### Phase 3: Polish & Publish (3 days)

| Task | Owner | Effort | Dependencies |
|------|-------|--------|--------------|
| Write README for public GitHub | Shuri | 2 hrs | P2 complete |
| Apply Banner's data audit fixes | Shuri | 1 hr | Banner's audit |
| Cleanup gitignore for public repo | Shuri | 30 min | audit |
| E2E smoke test (all 21 products) | Shuri + Happy | 1 day | P3 started |
| Create GitHub repo + push | Shuri | 30 min | E2E green |
| Update systemd service paths | Shuri | 30 min | published |

**Phase 3 exit criteria:** ~/soul/ live on GitHub, all services running under new paths.

---

## 7. Final ~/soul/ Repo Structure

```
~/soul/                         GitHub: rishav1305/soul (public)
├── cmd/                        13 server binaries
│   ├── chat/main.go            :3002
│   ├── tasks/main.go           :3004
│   ├── tutor/main.go           :3006
│   ├── scout/main.go           :3020
│   └── ...                     (all 13 unchanged)
├── internal/                   All backend logic (unchanged)
├── web/                        Frontend
│   └── src/
│       ├── components/
│       │   ├── layout/         AppShell, ProductRail, HorizontalRail (v1 UI)
│       │   ├── chat/           ChatPanel, Message, ToolCall (v1 UI)
│       │   └── planner/        KanbanBoard, TaskCard, TaskDetail (v1 UI)
│       ├── hooks/              All API hooks (v2 — unchanged)
│       └── lib/                types.ts (generated), api.ts, ws.ts
├── tests/                      46 test packages (unchanged)
├── docs/                       Architecture docs, specs, decisions
├── Makefile
├── go.mod                      module github.com/rishav1305/soul
├── CLAUDE.md
└── README.md                   Public-facing docs
```

---

## 8. Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| v1 UI hooks incompatible with v2 API | Medium | Audit API contracts before Phase 2; write adapters if needed |
| Module rename breaks something subtle | Low | `go test -race ./...` is the gate; Stark catches it |
| Missing data-testid after UI port | High | Happy's brief mandates it; Shuri review catches gaps |
| titan-pi reboots during Phase 1-2 | High (known) | Gitea push after each phase; work is checkpointed |
| Private Scout data in repo | Low | Banner's audit catches it; gitignore data dir |

---

## 9. What Stays Private

Even after ~/soul/ goes public:

- `~/.soul/` data directory (all user databases — never committed)
- TheirStack API key (env var only)
- Claude OAuth credentials (`~/.claude/.credentials.json`)
- All lead/contact data in scout.db
- Personal email/calendar data

Pepper/Loki/Fury are deciding product positioning. That's separate from this technical scope.

---

## Summary for CEO

| Question | Answer |
|----------|--------|
| Chat: invest or hibernate? | **Invest** — crashes are system reboots, not chat bugs. Service is healthy. |
| Backend changes? | **None** — v2's 46 test packages stay intact |
| UI changes? | **v1's AppShell replaces v2's router SPA** — same products, better layout |
| Timeline | **2 weeks** (3 phases): Foundation → UI Migration → Publish |
| Who does what? | Shuri: architecture + review. Happy: UI port. Stark: module rename. Banner: data audit |
| GitHub name | `rishav1305/soul` |

Ready to start Phase 1 on your approval.

— Shuri
