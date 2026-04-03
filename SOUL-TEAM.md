# Soul Team — Multi-Agent Operating System

A distributed team of 9 AI agents coordinated across two machines, communicating via file-based messaging, managed by background daemons, and protected by resource guardians. Each agent has a distinct persona, domain expertise, and autonomous daily routine.

---

## Quickstart

### Launch the team

```bash
soul-team
```

This opens a tmux session with 10 panes (CEO + 9 agents) in a 4-column layout:

```
┌──────────────┬──────────┬──────────┬──────────┐
│              │ Friday   │ Pepper   │ Shuri*   │
│              ├──────────┼──────────┼──────────┤
│   CEO (You)  │ Xavier   │ Fury     │ Stark*   │
│              ├──────────┼──────────┼──────────┤
│              │ Hawkeye  │ Loki     │ Banner*  │
└──────────────┴──────────┴──────────┴──────────┘

* = runs on worker machine via SSH
```

Launch takes ~2 minutes. Agents start sequentially with 10s stagger to avoid CPU spikes.

### Send a message to an agent

```bash
soul-msg send fury "Review the Q2 product strategy and identify gaps"
```

Or from within any Claude Code session:

```
clawteam inbox send soul-team fury "Your message" --from team-lead
```

### Check agent status

```bash
soul-monitor        # Full dashboard (both machines)
soul-monitor --bar  # One-line status bar
```

### Shut everything down

```bash
soul-shutdown "end of day"
```

Gracefully saves state, kills agents, shuts down worker machine, then primary.

---

## Architecture

### Machines

| Machine | Host | Specs | Role |
|---------|------|-------|------|
| **primary** | (your primary IP) | Always-on machine (e.g. RPi, home server) | Primary -- runs 6 agents, CEO, all daemons |
| **worker** | (your worker IP) | High-compute machine (e.g. desktop, workstation) | Compute -- runs 3 heavy agents (Shuri, Stark, Banner) |

The primary machine is the **source of truth**. Agent definitions, skills, and shared state live here. The worker accesses them via sshfs mounts (`soul-mounts.service`).

### The Team

| Agent | Model | Machine | Domain | Key Products |
|-------|-------|---------|--------|-------------|
| **Friday** | Sonnet | primary | Personal Assistant | Schedule, tasks, journal, meetings, people directory |
| **Shuri** | Sonnet | worker | Technical PM | Builds soul-v2, ships code, sprint execution |
| **Loki** | Opus | primary | Brand & Growth | SEO, content strategy, Scout content pipeline |
| **Fury** | Opus | primary | Strategy Advisor | Market analysis, positioning, competitive intel |
| **Xavier** | Opus | primary | Interview Coach | DSA drilling, mock interviews, Tutor product (`:3006`) |
| **Hawkeye** | Opus | primary | Pipeline Ops | Lead management, Scout product (`:3020`) |
| **Stark** | Opus | worker | Financial Analyst | Stock trading, portfolio management |
| **Banner** | Opus | worker | Data Scientist | EDA, ML, visualization, statistical analysis |
| **Pepper** | Opus | primary | Program Manager | Product oversight, roadmaps, gap analysis |

### Shared Filesystem

The worker machine mounts these from the primary via sshfs:

```
~/.claude/agents/     → agent persona definitions
~/.claude/skills/     → 65+ skill plugins
~/soul-roles/         → shared inboxes, briefs, decisions
~/soul-v2/            → codebase (for Shuri)
```

**Rule:** Edit agents/skills ONLY on the primary machine. The worker sees changes instantly via sshfs.

---

## Communication System

Three layers handle different communication patterns:

### Layer 1: Inbox Files (Action Items)

Direct, persistent messages between agents or from CEO.

**Location:** `~/soul-roles/shared/inbox/{agent}/`

```bash
# CEO sends action item to Fury
soul-msg send fury "Evaluate competitor X's new pricing tier" --priority P1

# Agent checks their inbox
clawteam inbox receive soul-team --agent fury

# Peek without consuming
clawteam inbox peek soul-team --agent fury
```

**Format:** Markdown with YAML frontmatter:
```yaml
---
from: team-lead
to: fury
date: 2026-03-22
priority: P1
type: direct
status: new
---
Evaluate competitor X's new pricing tier and report back with positioning implications.
```

### Layer 2: Broadcast & Group Discussions (Router)

Multi-agent conversations coordinated by the `soul-router` daemon.

```bash
# Broadcast to all agents
clawteam inbox broadcast soul-team "Sprint review at 4pm — prepare status updates" --from team-lead

# Group discussions happen automatically when agents need multi-party input
# Router manages thread state, fan-out, and auto-close at 20 messages
```

**Discussion threads:** `~/.clawteam/teams/soul-team/discussions/{thread_id}/`
- Each response is a timestamped JSON file: `{timestamp}-{agent}.json`
- Max 20 messages per thread (auto-closes)
- Max 3 concurrent discussions

### Layer 3: Sidecar Injection (Real-time)

Per-agent watchers that detect idle state and inject messages via tmux.

Each agent has a background sidecar that:
1. Monitors the agent's inbox for new messages
2. Detects agent state (idle / busy / crashed / crunched)
3. Injects messages into the agent's tmux pane when idle
4. Builds thread summaries for context-compressed agents

**State detection:**
- **Idle:** Agent shows `❯` prompt — safe to inject
- **Busy:** Pane output is changing — wait
- **Crashed:** Shows `$` bash prompt — needs auto-heal
- **Crunched:** Context window compressed — send summaries instead of full messages

---

## Task Management

Agents coordinate work through the ClawTeam task system:

```bash
# List your tasks
clawteam task list soul-team --owner shuri

# Create a task
clawteam task create soul-team "Implement delta sync endpoint" --owner shuri

# Create with dependency
clawteam task create soul-team "Write frontend hook" --blocked-by TASK-42

# Mark complete
clawteam task update soul-team TASK-42 --status completed

# List all team tasks
clawteam task list soul-team
```

### Cross-Collaboration Routing

When an agent needs expertise outside their domain:

| Need | Ask |
|------|-----|
| Design/UI/Brand | Loki |
| Code/Build | Shuri |
| Strategy | Fury |
| Pipeline/Outreach | Hawkeye |
| Schedule/People | Friday |
| Data/Analysis | Banner |
| Trading/Finance | Stark |
| Interviews/Learning | Xavier |
| Product/Roadmap | Pepper |

---

## Background Daemons

Launched automatically by `soul-team`:

| Daemon | Type | Purpose |
|--------|------|---------|
| **soul-router** | Python | Fan-out broadcasts, coordinate group discussions |
| **soul-sidecars** (x10) | Bash | Per-agent inbox watchers, message injection |
| **soul-bridge** | Python | Sync between native Teams inboxes and ClawTeam inboxes |
| **soul-heartbeat** | Bash | Keep agents alive (prevent idle timeout) |
| **soul-guardian** | Python (systemd) | CPU/memory/temp monitoring, auto-heal, token tracking |

### Soul Guardian

The watchdog that keeps the system healthy:

**Thresholds:**
| Metric | Threshold | Action |
|--------|-----------|--------|
| Temperature | > 80 C | Kill newest agent |
| Free RAM | < 1.5 GB | Kill heaviest agent |
| CPU | > 95% | Log warning |
| Daily spend | > $48 (80% of $60 cap) | Alert |
| Daily spend | > $60 | Pause non-critical agents |

**Auto-healing:**
- Detects crashed agents (bash prompt instead of Claude TUI)
- Relaunches via tmux
- Auto-continues safe prompts (`[Y/n]`, `Press Enter`)
- NEVER auto-continues dangerous prompts (password, delete, force push)
- **Critical agents** (Friday, Shuri) are never paused, even under resource pressure

**Token tracking:** SQLite database at `~/.soul/guardian.db`
- Tracks input/output tokens per agent
- Daily spend totals
- Cost rates: Opus ($15/$75 per M tokens), Sonnet ($3/$15 per M tokens)

---

## Resource Protection

### cgroup Slice

All local agents run under `soul-agents.slice`:
- **CPU cap:** 300% (3 of 4 cores)
- **RAM cap:** 12 GB
- Prevents single agent from crashing the system

### CPU Governor

The primary machine can run a conservative CPU governor (e.g., max 1.8 GHz). Persisted via `/etc/default/cpufrequtils`.

### Power Budget

Low-power primary machines have limited PSU. **Never run all 9 agents on the primary alone** -- always distribute heavy agents (Shuri, Stark, Banner) to the worker.

---

## Agent Lifecycle

### Daily Routine (Every Agent)

Each agent follows this cycle on every session start:

1. **Check inbox** — `clawteam inbox receive soul-team --agent {name}`
2. **Process new items** — Handle messages with `status: new`
3. **Check assigned tasks** — Pick highest-priority open task
4. **Check peer requests** — Respond to pending inter-agent queries
5. **Idle check** — If nothing pending, enter **Proactive Mode**
   - Work on domain-specific improvements
   - Timebox to 15-20 minutes per item
   - Log work to `~/soul-roles/shared/briefs/{agent}-improvements.md`
   - Loop back to step 1

### Escalation Chain

1. **Can I solve this myself?** — Check skills, knowledge, WebSearch
2. **Does a peer know?** — Route to appropriate agent (see routing matrix)
3. **Still blocked?** — Escalate to CEO via Friday's inbox
4. **Is this a pattern?** — If escalated 3+ times, propose a new skill

### Status Notifications

Agents report state changes to CEO:

```json
{"from": "shuri", "type": "status", "action": "started", "task": "sync endpoint", "detail": "ETA: 30min"}
{"from": "shuri", "type": "status", "action": "completed", "task": "sync endpoint", "summary": "10 tests pass"}
{"from": "shuri", "type": "status", "action": "blocked", "task": "...", "blocker": "need API key"}
{"from": "shuri", "type": "status", "action": "idle", "last_completed": "..."}
```

---

## Skills System

65+ skills available across agents. Each agent has access to relevant skills for their domain.

**Skill categories:**
- **Superpowers:** Plan writing, TDD, code review, parallel dispatch, debugging, git worktrees
- **Marketing:** SEO, content strategy, cold email, pricing, CRO, ad creative, referral programs
- **Product:** PRDs, roadmaps, health diagnostics, feature reviews, strategy sessions
- **Finance:** Technical analysis, fundamental analysis, portfolio review, sector rotation
- **Data:** EDA, ML pipelines, statistical analysis, visualization, data collection
- **Interview:** DSA drills, mock interviews, study plans, system design
- **Pipeline:** Sweeps, outreach, gate reviews, lead research, negotiation prep
- **UI/UX:** Design intelligence (50+ styles, 161 palettes, 57 font pairings)

Skills are invoked via the `Skill` tool in Claude Code sessions.

---

## Configuration

### soul-team.toml

```toml
# ~/.claude/config/soul-team.toml
boot_prompt = "Begin your daily routine."
stagger_seconds = 10

[[agents]]
name = "friday"
model = "sonnet"
machine = "local"

[[agents]]
name = "shuri"
model = "sonnet"
machine = "remote"

# ... (9 agents total)
```

### Agent Persona Files

Each agent is defined in `~/.claude/agents/{agent}.md` with:

- **Identity:** Personality, philosophy, boundaries
- **Mandate:** DO/DO NOT lists
- **KPIs:** Measurable daily/weekly/sprint targets
- **Skills:** Whitelisted skill plugins
- **Memory Charter:** What to store/ignore/read
- **Daily Routine:** Startup sequence
- **Cross-Collaboration:** Routing matrix
- **Proactive Focus:** What to work on when idle

---

## Key Directories

| Path | Purpose |
|------|---------|
| `~/.claude/agents/` | Agent persona definitions (9 files) |
| `~/.claude/skills/` | 65+ skill plugins |
| `~/.claude/config/soul-team.toml` | Launcher configuration |
| `~/.claude/scripts/` | All soul-* scripts |
| `~/.claude/teams/soul-team/` | Native Teams config + inboxes |
| `~/.clawteam/teams/soul-team/` | ClawTeam inboxes, queues, discussions |
| `~/soul-roles/` | Persona CLAUDE.md files, shared resources |
| `~/soul-roles/shared/inbox/` | Per-agent action item inboxes |
| `~/soul-roles/shared/briefs/` | Reports, logs, improvement notes |
| `~/soul-roles/shared/decisions/` | Documented team decisions |
| `~/.soul/guardian.db` | Guardian SQLite (token tracking, health) |

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `soul-team` | Launch all 9 agents in tmux |
| `soul-monitor` | Full resource dashboard (both machines) |
| `soul-monitor --bar` | One-line status bar |
| `soul-shutdown [reason]` | Graceful shutdown (save → kill → poweroff) |
| `soul-msg send {agent} "msg"` | Send message to agent |
| `soul-msg send {agent} "msg" --priority P1` | Priority message |
| `clawteam inbox receive soul-team --agent {name}` | Check inbox |
| `clawteam inbox peek soul-team --agent {name}` | Peek without consuming |
| `clawteam inbox broadcast soul-team "msg" --from {name}` | Broadcast to all |
| `clawteam task list soul-team` | List all tasks |
| `clawteam task list soul-team --owner {name}` | List agent's tasks |
| `clawteam task create soul-team "title" --owner {name}` | Create task |
| `clawteam task update soul-team {id} --status completed` | Complete task |
| `clawteam lifecycle idle soul-team` | Signal idle state |

---

## Shutdown Protocol

`soul-shutdown` executes 6 steps:

1. **Log event** — Appends to `~/soul-roles/shared/briefs/sentinel-power-log.md`
2. **Save state** — Dumps tmux sessions, claude processes, service status
3. **Stop daemons** — Kills sidecars, router, bridge, heartbeat
4. **Kill tmux** — `tmux kill-session -t soul-team`
5. **Shutdown worker** -- SSH `sudo shutdown now`
6. **Shutdown primary** -- `sudo shutdown now` (5s grace, Ctrl+C to abort)

---

## Adding a New Agent

See `~/soul-roles/GUIDE.md` for the full checklist. Summary:

1. Create persona at `~/.claude/agents/{name}.md`
2. Create role directory at `~/soul-roles/{name}/CLAUDE.md`
3. Create inbox at `~/soul-roles/shared/inbox/{name}/`
4. Add to `~/.claude/config/soul-team.toml`
5. Add to team config in `~/.claude/teams/soul-team/config.json`
6. Update routing matrix in all agent personas
7. Create bash alias for solo sessions
8. Restart `soul-team`

---

## Design Principles

1. **Personas live outside the codebase** — Agent definitions are in `~/.claude/agents/`, not in soul-v2. This allows team composition changes without code changes.

2. **File-based IPC** — All communication uses the filesystem (markdown files, JSON). No databases, no network protocols, no message brokers. Simple, debuggable, grep-able.

3. **Primary is source of truth** -- All agent definitions, skills, and shared state originate here. Worker reads via sshfs.

4. **Graceful degradation** -- If the worker goes down, 6 agents continue on the primary. If an agent crashes, guardian auto-heals. If context fills, sidecars send summaries.

5. **Cost containment** — $60/day spend cap, token tracking per agent, non-critical agents paused under pressure, sonnet for routine work, opus for judgment.

6. **No unsupervised danger** — Guardian never auto-approves destructive operations. Agents escalate to CEO for architecture changes, external comms, and business decisions.
