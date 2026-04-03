# Architecture Decision Records

This document records the key architectural decisions made in soul-team,
following the ADR format. Each entry captures the context, the decision,
and the trade-offs accepted.

---

## ADR-001: File-Based Messaging Over Redis/RabbitMQ

**Status:** Active

**Context:**
Nine AI agents need to communicate: direct messages, broadcasts, group discussions,
and task assignments. Traditional options include Redis pub/sub, RabbitMQ, or a
custom TCP protocol. However, the system runs on low-power hardware (Raspberry Pi)
and must remain fully debuggable without specialized tooling.

**Decision:**
All inter-agent communication uses the filesystem -- markdown files with YAML
frontmatter for direct messages, JSON files for discussion threads, and a
flat-file task board. Messages are delivered by writing files to per-agent
inbox directories (`~/.clawteam/teams/{team}/inboxes/{agent}/`).

**Consequences:**
- (+) Zero infrastructure dependencies -- no broker to install, configure, or crash
- (+) Fully debuggable with `ls`, `cat`, `grep` -- any operator can inspect message state
- (+) Survives machine restarts -- messages are persistent by default
- (+) Cross-machine sync via sshfs is trivial (mount the directory)
- (-) No real-time push -- relies on polling (500ms interval) or filesystem watchers
- (-) Higher latency than in-memory brokers (~500ms vs ~1ms)
- (-) Manual cleanup required for old messages (mitigated by auto-archive)

---

## ADR-002: tmux Over Docker

**Status:** Active

**Context:**
Each AI agent runs as an interactive Claude Code CLI session. The system needs
process isolation, visibility into agent activity, and the ability to inject
messages into running sessions. Docker containers, systemd services, and tmux
panes were all considered.

**Decision:**
Agents run as Claude Code processes inside named tmux panes within a shared
tmux session. The CEO (human operator) sees all agents in a tiled layout and
can switch to any pane to observe or intervene.

**Consequences:**
- (+) Direct visibility -- switch to any pane and see exactly what an agent is doing
- (+) Human intervention is instant -- type into a pane to override an agent
- (+) tmux send-keys enables programmatic message injection by sidecars
- (+) No container overhead on resource-constrained hardware
- (-) No filesystem isolation between agents (mitigated by convention)
- (-) tmux is a single point of failure for the session (mitigated by guardian auto-restart)
- (-) Limited to one machine per tmux session (mitigated by SSH-launched remote agents)

---

## ADR-003: Guardian as Monolith

**Status:** Active (refactor proposed)

**Context:**
The guardian daemon handles 10+ responsibilities: CPU/memory/temperature monitoring,
agent crash detection, auto-restart, token tracking, cost enforcement, idle detection,
auto-compact, auto-continue, context budget monitoring, and bridge watchdog. Over
time, it grew to 2,274 lines in a single file.

**Decision:**
Initially built as a single `guardian.py` file for rapid iteration. All health
monitoring, restart logic, and cost tracking live in one daemon with one event loop.

**Consequences:**
- (+) Single process to manage -- one systemd service, one log stream
- (+) All state in one place -- no coordination between microservices
- (+) Fast iteration during early development -- no package structure overhead
- (-) Hard to test subsystems in isolation (mitigated by 110+ unit tests)
- (-) Merge conflicts when multiple developers touch the file
- (-) Cognitive load when reading -- 2,274 lines is too much for one file

**Note:** A detailed refactor plan exists in `guardian/REFACTOR-PLAN.md` that
decomposes the monolith into 22 focused modules while preserving all 110 tests.

---

## ADR-004: CARS/ACRS for Model Assignment

**Status:** Active

**Context:**
Running all 9 agents on the most capable (and expensive) model would cost
$150+/day. Different agents have different cognitive requirements -- a personal
assistant needs less reasoning power than a strategy advisor. We needed a
systematic way to assign models.

**Decision:**
Agents are assigned models (Opus vs Sonnet) based on their cognitive requirements:
- **Opus** (high reasoning): Strategy, competitive intel, interviews, pipeline ops,
  data science, financial analysis, product management
- **Sonnet** (fast execution): Personal assistant, code builder

The assignment is declared in `soul-team.toml` and enforced by the launcher.
Guardian tracks per-agent token spend to validate cost assumptions.

**Consequences:**
- (+) 60-70% cost reduction vs all-Opus
- (+) Sonnet agents respond faster (lower latency for routine tasks)
- (+) Cost tracking per agent enables data-driven rebalancing
- (-) Model capability mismatches require manual reassignment
- (-) Cost rates change with provider pricing updates (tracked in guardian constants)

---

## ADR-005: Courier Replacing Sidecars

**Status:** Active

**Context:**
Originally, each agent had its own bash sidecar script -- 10 independent processes
watching inboxes, detecting idle states, and injecting messages via tmux. This
caused race conditions (multiple sidecars injecting simultaneously), zombie processes,
and debugging nightmares (10 log streams to check).

**Decision:**
Replace 10 bash sidecars with a single Python daemon (`soul-courier`) that
manages all agents. Courier uses watchdog filesystem events instead of polling,
has proper locking per agent pane, and runs as one systemd user service.

**Consequences:**
- (+) Single process, single log stream, single PID to manage
- (+) Proper mutex locks prevent concurrent injection into the same pane
- (+) Filesystem watcher (inotify) instead of polling -- lower CPU usage
- (+) Structured Python code is testable (vs bash scripts)
- (-) Single point of failure for message delivery (mitigated by systemd auto-restart)
- (-) More complex codebase than individual bash scripts

---

## ADR-006: SSHFS for Multi-Machine Sync

**Status:** Active

**Context:**
Agent definitions, skills, inboxes, and shared state must be accessible from both
the primary machine and the worker. Options considered: NFS, rsync (cron or inotify),
shared database, and SSHFS.

**Decision:**
The worker mounts shared directories from the primary via SSHFS. Seven mount points
cover agents, skills, roles, comms, scripts, memory, and assistant data. A systemd
service (`soul-mounts.service`) manages the mounts with auto-reconnect.

**Consequences:**
- (+) Zero additional infrastructure -- uses existing SSH keys
- (+) Changes on primary are visible on worker immediately (no sync delay)
- (+) Bidirectional -- worker writes (e.g., inbox messages) appear on primary
- (+) Encrypted in transit by default (SSH)
- (-) Network latency affects file operations on mounted paths
- (-) If SSH connection drops, mounted paths become stale (mitigated by `reconnect` option)
- (-) Not suitable for high-throughput file I/O (acceptable for config/messaging)

---

## ADR-007: SQLite for Guardian State

**Status:** Active

**Context:**
Guardian needs persistent storage for heal logs, token usage tracking, and daily
spend totals. Options: PostgreSQL, Redis, flat files (JSON/CSV), SQLite.

**Decision:**
Use SQLite with a single database file (`~/.soul/guardian.db`). All writes go through
a threading lock to handle concurrent access safely.

**Consequences:**
- (+) Zero infrastructure -- no server process to manage
- (+) Single file backup -- copy `guardian.db` and you have everything
- (+) SQL queries for cost analysis (e.g., "total spend by agent this week")
- (+) ACID transactions for atomic token usage updates
- (-) Single-writer bottleneck (acceptable at guardian's write frequency)
- (-) No remote access without copying the file (acceptable for single-daemon use)

---

## ADR-008: Lazy Memory Loading

**Status:** Active

**Context:**
Each agent has a growing memory directory with potentially hundreds of files.
Loading all memories into context on every session start would waste tokens
and slow down agent boot time.

**Decision:**
Agents load only their `MEMORY.md` index file at startup (a lightweight table of
contents). Individual memory files are read on-demand when the index entry is
relevant to the current task. Guardian enforces periodic memory re-reads after
restarts and context compaction.

**Consequences:**
- (+) Fast agent startup -- only ~200 lines of index loaded
- (+) Token-efficient -- irrelevant memories never enter context
- (+) Index serves as a navigable summary for human operators
- (-) Agents may miss relevant context if the index description is too vague
- (-) Memory files can go stale without agents noticing (mitigated by guardian audits)

---

## ADR-009: Shared Protocol Extraction

**Status:** Active

**Context:**
All 9 agents share common behaviors: inbox checking, status notifications, escalation
chains, task execution flow, and heartbeat reporting. Initially, each agent's persona
file contained duplicate copies of these protocols, leading to drift and inconsistency.

**Decision:**
Extract shared behaviors into `protocols/team-protocol-v2.md`. Each agent's persona
file references the shared protocol via `See ~/soul-roles/shared/protocols/team-protocol-v2.md`.
Agent-specific behaviors remain in individual persona files.

**Consequences:**
- (+) Single source of truth for shared behaviors
- (+) Protocol changes propagate to all agents automatically
- (+) Smaller persona files -- easier to review and maintain
- (-) Agents must load an additional file at startup (mitigated by sshfs mount)
- (-) Risk of agents ignoring shared protocol if persona file contradicts it

---

## ADR-010: systemd User Services

**Status:** Active

**Context:**
Background daemons (guardian, courier, router) need to run persistently, restart on
failure, and start on login. Options: root systemd services, supervisor, pm2, cron
with watchdog scripts, or systemd user services.

**Decision:**
All daemons run as systemd user services (`--user` scope) under the operator's
account. Service files use `%h` for home directory expansion and include security
hardening directives (NoNewPrivileges, PrivateTmp, ProtectSystem).

**Consequences:**
- (+) No root access required -- user services run in user scope
- (+) Standard systemd tooling: `systemctl --user status`, `journalctl --user-unit`
- (+) Auto-restart on failure with configurable backoff
- (+) Security hardening via systemd directives (read-only filesystem, no privilege escalation)
- (-) User services only run when the user is logged in (mitigated by `loginctl enable-linger`)
- (-) `%h` expansion doesn't work in all directive types (mitigated by consistent use)
- (-) Debugging requires `--user` flag on all systemctl commands (easy to forget)
