---
author: pepper
date: 2026-03-24
type: infrastructure-strategy
priority: P1
for: team-lead, fury, shuri
status: DRAFT — Pepper operational view. Awaiting Fury strategic merge.
---

# Infrastructure Expansion Plan — 3-Machine Fleet

**Trigger:** CEO adding a 3rd machine. Migrating base of operations from titan-pi to new PC due to corruption risk from frequent crashes.

---

## 1. Current State Assessment

### Machine Inventory

| Machine | CPU | RAM | Role | Agents | Services | Health |
|---------|-----|-----|------|--------|----------|--------|
| **titan-pi** (192.168.0.128) | ARM 4-core (RPi) | 15GB (5.7GB used, 9.9GB free) | Primary / Source of Truth | Friday, Xavier, Hawkeye + team-lead | soul-v2, Scout, Tutor, soul-router, soul-guardian | UNSTABLE — frequent crashes, corruption risk |
| **titan-pc** (192.168.0.196) | i5-8400 6-core x86 | 7.6GB (3.5GB used, 4.1GB avail) | Compute Node | Pepper, Banner, Shuri, Stark | None (accesses titan-pi via sshfs) | STABLE but RAM-constrained under peak load |

### Current Architecture

```
titan-pi (SOURCE OF TRUTH)
  ├── ~/.claude/agents/          (agent definitions)
  ├── ~/.claude/skills/          (skill definitions)
  ├── ~/soul-v2/                 (primary codebase)
  ├── ~/soulgraph/               (SoulGraph codebase)
  ├── ~/portfolio_app/           (portfolio codebase)
  ├── ~/soul-roles/              (shared briefs, inboxes, decisions)
  ├── soul-router.py             (message routing)
  ├── soul-guardian.py           (health monitoring)
  ├── soul-team.sh               (agent lifecycle)
  └── Services: soul-v2 (:3002), Scout (:3020), Tutor (:3006)

titan-pc (COMPUTE NODE)
  ├── sshfs mounts → titan-pi    (read-only agents, skills; read-write soul-roles, soul-v2)
  └── 4 agent processes           (Pepper, Banner, Shuri, Stark)
```

### Current Problems

1. **titan-pi is a single point of failure.** It hosts ALL source of truth data, ALL services, AND 4 agent processes. When it crashes, everything goes down.
2. **titan-pi has corruption risk.** Frequent crashes (4+ in the last week) risk filesystem corruption on the SD card.
3. **titan-pc is RAM-constrained.** 7.6GB for 4 agents + sshfs. Adding Happy would push to ~5GB used.
4. **No redundancy.** If either machine dies, half the team is offline.
5. **sshfs latency.** Shuri's code editing on titan-pc goes through sshfs to titan-pi — adds latency to every file operation.

---

## 2. Target State — 3-Machine Fleet

### Proposed Architecture

```
NEW PC ("titan-prime") — PRIMARY / SOURCE OF TRUTH
  ├── ~/.claude/agents/          (agent definitions — source of truth)
  ├── ~/.claude/skills/          (skill definitions — source of truth)
  ├── ~/soul-v2/                 (primary codebase — git origin)
  ├── ~/soulgraph/               (SoulGraph codebase)
  ├── ~/portfolio_app/           (portfolio codebase)
  ├── ~/soul-roles/              (shared briefs, inboxes, decisions)
  ├── soul-router.py             (message routing)
  ├── soul-guardian.py           (health monitoring — watches all 3 machines)
  ├── soul-team.sh               (agent lifecycle — orchestrates all machines)
  ├── Services: soul-v2 (:3002), Scout (:3020), Tutor (:3006)
  └── Agents: Shuri, Happy, Hawkeye, Xavier, Friday (5 agents — build + operations)

titan-pc (192.168.0.196) — STRATEGY & ANALYSIS NODE
  ├── sshfs mounts → titan-prime  (agents, skills, codebases)
  └── Agents: Pepper, Fury, Banner, Stark, Loki (5 agents — strategy + analytics)

titan-pi (192.168.0.128) — REDUCED ROLE: BACKUP & MONITORING
  ├── rsync mirror of titan-prime  (hourly backup of source of truth)
  ├── Secondary soul-guardian      (watchdog — can alert if titan-prime goes down)
  └── Agents: None (or 1 lightweight agent for monitoring if needed)
```

### Why This Distribution

**titan-prime (new PC) — Build & Operations cluster:**
- **Shuri + Happy** need LOCAL codebase access (no sshfs latency). They write code to ~/soul-v2/, ~/soulgraph/, ~/portfolio_app/. Local disk = fastest possible I/O.
- **Hawkeye** needs Scout service on the same machine (no network hop for API calls).
- **Xavier** needs Tutor service on the same machine.
- **Friday** manages scheduling, routing, and operational coordination — should be on the primary machine.
- **Services** (soul-v2, Scout, Tutor) run here — co-located with their operator agents.

**titan-pc — Strategy & Analysis cluster:**
- **Pepper, Fury, Loki, Banner, Stark** don't write code to the primary codebase (or rarely do).
- They primarily read briefs, write briefs, do analysis, and coordinate.
- sshfs latency is acceptable for reading files and writing to ~/soul-roles/.
- 6 cores + 7.6GB RAM is sufficient for 5 strategy/analytics agents (no heavy builds).

**titan-pi — Backup & Monitoring:**
- Demoted from primary to backup. No agents running = no crash risk from agent load.
- Hourly rsync from titan-prime preserves all data.
- Secondary soul-guardian watches titan-prime health — if titan-prime goes down, titan-pi can alert (or even failover for critical services).
- 15GB RAM is wasted in this role — but the machine is unreliable, so we don't trust it with primary workloads.

---

## 3. Agent Distribution — 10 Agents Across 3 Machines

### Option A: 5-5-0 (Recommended)

| Machine | Agents | RAM Budget | Rationale |
|---------|--------|------------|-----------|
| **titan-prime** | Shuri, Happy, Hawkeye, Xavier, Friday | ~2.5GB for agents + services | Build agents need local codebase. Operator agents need local services. |
| **titan-pc** | Pepper, Fury, Banner, Stark, Loki | ~2.0GB for agents | Strategy/analysis agents don't need local codebases. |
| **titan-pi** | None | N/A | Unreliable — demoted to backup/monitoring only. |

**RAM requirements for titan-prime (estimated):**

| Component | RAM | Notes |
|-----------|-----|-------|
| Shuri (sonnet) | ~400MB | Code agent |
| Happy (sonnet) | ~400MB | Frontend/testing agent |
| Hawkeye (sonnet/opus) | ~500MB | Pipeline ops |
| Xavier (sonnet/opus) | ~500MB | Interview prep |
| Friday (sonnet) | ~400MB | Personal assistant |
| soul-v2 service | ~200MB | Go binary |
| Scout service | ~150MB | Go binary |
| Tutor service | ~150MB | Python service |
| soul-router + guardian | ~100MB | Python scripts |
| MCP servers (5x) | ~300MB | soul-team-mcp per agent (no playwright) |
| OS + buffer | ~1GB | systemd, SSH, etc. |
| **TOTAL** | **~4.1GB** | |

**Minimum titan-prime spec:** 8GB RAM, 4+ cores. **Recommended:** 16GB RAM, 6+ cores (comfortable headroom).

**titan-pc stays as-is (5 agents):**

| Component | RAM | Notes |
|-----------|-----|-------|
| Pepper (opus) | ~400MB | Product management |
| Fury (opus) | ~500MB | Strategy |
| Banner (sonnet) | ~350MB | Data science |
| Stark (sonnet) | ~500MB | Trading |
| Loki (sonnet) | ~400MB | Content/marketing |
| MCP servers (5x) | ~300MB | soul-team-mcp per agent |
| sshfs mounts | ~50MB | Network filesystem |
| OS + buffer | ~500MB | |
| **TOTAL** | **~3.0GB** | Fits in 7.6GB with 4.6GB free |

### Option B: 6-4-0 (If titan-prime has limited RAM)

Move Loki to titan-prime (he occasionally needs to work with portfolio frontend):

| Machine | Agents | Notes |
|---------|--------|-------|
| **titan-prime** | Shuri, Happy, Hawkeye, Xavier, Friday, Loki | 6 agents — requires 16GB+ RAM |
| **titan-pc** | Pepper, Fury, Banner, Stark | 4 agents — current config minus Loki |
| **titan-pi** | None | Backup only |

### Option C: 4-4-2 (If titan-pi is still needed)

Keep 2 lightweight agents on titan-pi for redundancy:

| Machine | Agents | Notes |
|---------|--------|-------|
| **titan-prime** | Shuri, Happy, Hawkeye, Xavier | 4 build + ops agents |
| **titan-pc** | Pepper, Fury, Banner, Stark | 4 strategy agents |
| **titan-pi** | Friday, Loki | 2 lightweight agents — monitoring + content |

**Not recommended** — titan-pi's instability makes it unreliable for any agent workload.

---

## 4. Migration Plan: titan-pi -> titan-prime

### Phase 0: Pre-Migration (Before New PC Arrives)

| Task | Owner | Time | Notes |
|------|-------|------|-------|
| Full backup of titan-pi to external storage | CEO | 30 min | `rsync -avz --progress /home/rishav/ /path/to/backup/` |
| Document all systemd services and configs | Shuri | 1 hr | List every enabled service, port, config file |
| Document all cron jobs and scheduled tasks | Friday | 30 min | `crontab -l`, system cron |
| Prepare soul-v2 git remote reconfiguration | Shuri | 15 min | Plan new Gitea setup or remote URL changes |
| Happy agent spec finalized | Pepper | DONE | See pepper-happy-agent-spec-2026-03-24.md |

### Phase 1: New PC Setup (Day 1 — ~4 hours)

| Step | Action | Time | Verification |
|------|--------|------|-------------|
| 1 | OS install (Ubuntu 24.04 LTS recommended) | 30 min | `uname -a`, `free -h` |
| 2 | Create rishav user, SSH keys, network config | 15 min | `ssh titan-prime` from titan-pc works |
| 3 | Install prerequisites (Go, Node.js, Python, Docker) | 30 min | `go version`, `node -v`, `python3 --version` |
| 4 | Install Claude CLI | 10 min | `claude --version` |
| 5 | Clone/copy soul-v2, soulgraph, portfolio_app | 30 min | `git status` in each repo |
| 6 | Copy ~/.claude/ (agents, skills, scripts, MCP servers) | 15 min | `ls ~/.claude/agents/` |
| 7 | Copy ~/soul-roles/ | 10 min | `ls ~/soul-roles/shared/briefs/` |
| 8 | Install Gitea (if migrating from titan-pi) | 30 min | `http://titan-prime:3000` |
| 9 | Build and start soul-v2 service | 20 min | `curl http://localhost:3002/api/health` |
| 10 | Build and start Scout service | 15 min | `curl http://localhost:3020/api/health` |
| 11 | Build and start Tutor service | 15 min | `curl http://localhost:3006/api/health` |
| 12 | Verify all services stable | 15 min | 15 min uptime, no errors in journal |

### Phase 2: Agent Migration (Day 1-2 — ~2 hours)

| Step | Action | Time | Verification |
|------|--------|------|-------------|
| 1 | Configure sshfs on titan-pc to point to titan-prime (instead of titan-pi) | 15 min | `ls ~/.claude/agents/` from titan-pc |
| 2 | Update soul-mounts.service on titan-pc | 10 min | `systemctl status soul-mounts.service` |
| 3 | Start agents on titan-prime: Friday, Xavier, Hawkeye | 20 min | `clawteam inbox peek soul-team --agent friday` |
| 4 | Deploy Happy agent on titan-prime | 15 min | Onboarding tasks from spec |
| 5 | Move Shuri from titan-pc to titan-prime | 30 min | `make verify-static` on titan-prime |
| 6 | Verify titan-pc agents still work with new sshfs target | 15 min | `clawteam inbox peek soul-team --agent pepper` |
| 7 | Run full team communication test | 15 min | All 10 agents receive + respond |

### Phase 3: titan-pi Demotion (Day 2-3 — ~1 hour)

| Step | Action | Time | Verification |
|------|--------|------|-------------|
| 1 | Stop all agent processes on titan-pi | 5 min | `pkill claude` on titan-pi |
| 2 | Stop soul-v2, Scout, Tutor services on titan-pi | 5 min | `systemctl stop soul-v2 scout tutor` |
| 3 | Configure rsync backup: titan-prime → titan-pi (hourly) | 15 min | `rsync` cron job verified |
| 4 | Deploy secondary soul-guardian on titan-pi | 15 min | Watches titan-prime + titan-pc health |
| 5 | Update DNS/hosts entries if needed | 5 min | `titan-prime` resolves correctly |
| 6 | Remove sshfs dependency on titan-pi for titan-pc | 10 min | titan-pc now mounts from titan-prime |
| 7 | Monitor 24h stability | — | All services stable on titan-prime |

### Phase 4: Stabilization (Day 3-5)

- Monitor all agents for 48h
- Verify no sshfs mount failures
- Verify all team communication working
- Run soul-guardian health check cycle
- Test failover: what happens if titan-prime reboots?
- Adjust cgroup limits if needed

---

## 5. 6-Pillar Alignment

| Pillar | Current State | After Expansion | How |
|--------|--------------|-----------------|-----|
| **RESILIENT** | Single point of failure (titan-pi). One crash = everything down. | 3-machine fleet. titan-pi as backup. rsync hourly. Secondary guardian. | Redundant data, distributed agents, backup monitoring |
| **PERFORMANT** | sshfs latency for Shuri's code edits. titan-pc RAM-constrained. | Shuri + Happy have LOCAL codebase. 5 agents per machine = balanced load. | Co-locate code agents with codebase. Balanced distribution. |
| **SOVEREIGN** | All data on local machines. No cloud dependency. | Same — new PC is local. Gitea stays self-hosted. | No change — already sovereign. |
| **SCALABLE** | 9 agents, can't add more without RAM pressure. | 10 agents with headroom. 3 machines can scale to 15+ agents. | More machines = more capacity. Clear role-per-machine pattern. |
| **OBSERVABLE** | soul-guardian on titan-pi only. Analytics DB on titan-pi. | Guardian on titan-prime + titan-pi. Cross-machine monitoring. | Dual guardians. Distributed observation. |
| **EFFICIENT** | Agents on wrong machines (Shuri editing remote files). | Agents co-located with their resources. Minimal network overhead. | Right agent, right machine, right data locality. |

---

## 6. Redundancy & Failover

### Can We Survive Any Single Machine Going Down?

| Machine Down | Impact | Recovery | Time to Recover |
|-------------|--------|----------|-----------------|
| **titan-prime** | Build agents + services down. Strategy agents on titan-pc still work. titan-pi has backup data. | Restart titan-prime. If hardware failure: restore from titan-pi backup to a replacement. | 5 min (reboot) / 2-4 hrs (hardware swap) |
| **titan-pc** | Strategy/analysis agents down. Build agents + services unaffected. | Restart titan-pc. | 5 min (reboot) |
| **titan-pi** | Backup monitoring down. No production impact. | Restart titan-pi. If hardware failure: lose backup node (acceptable). | 5 min / replaceable |

### Failover Improvements (Future)

1. **Auto-restart scripts**: systemd services with `Restart=always` + `RestartSec=5`
2. **Cross-machine guardian**: titan-pi's guardian can SSH to titan-prime and restart services
3. **Git mirror**: soul-v2 and soulgraph repos mirrored to both titan-pc and titan-pi (read-only)
4. **Service failover**: If titan-prime's Scout goes down, titan-pi could temporarily serve Scout (requires service migration script)

---

## 7. Resource Budgets Per Machine

### titan-prime (New PC)

| Resource | Budget | Headroom |
|----------|--------|----------|
| **RAM** | 4.1GB estimated use | Depends on machine spec. 8GB = tight. 16GB = comfortable. 32GB = unlimited. |
| **CPU** | 5 agents + 3 services | 6+ cores recommended. 8 cores = comfortable. |
| **Disk** | ~50GB for repos + DBs + logs | 256GB SSD minimum. 512GB recommended. |
| **Network** | Primary LAN node. sshfs server for titan-pc. | Gigabit Ethernet recommended. |

### titan-pc (Existing)

| Resource | Budget | Headroom |
|----------|--------|----------|
| **RAM** | ~3.0GB for 5 agents | 4.6GB free (61% headroom) — MUCH better than current |
| **CPU** | 5 strategy agents (bursty, not sustained) | 6 cores sufficient |
| **Disk** | Minimal — sshfs mount | Existing disk fine |

### titan-pi (Demoted)

| Resource | Budget | Headroom |
|----------|--------|----------|
| **RAM** | ~200MB for guardian + rsync | 14.8GB free — massively underutilized (acceptable for backup role) |
| **CPU** | Minimal | 4 ARM cores idle |
| **Disk** | Mirror of titan-prime | SD card — corruption risk remains for backup, but acceptable since it's NOT primary |

---

## 8. New PC Specification Recommendations

### Minimum Viable

| Component | Spec | Rationale |
|-----------|------|-----------|
| CPU | Intel i5/Ryzen 5, 6+ cores | 5 agents + 3 services + build commands |
| RAM | 8GB | Tight but workable. Would need careful management. |
| Storage | 256GB SSD | Repos, DBs, logs |
| Network | Gigabit Ethernet | sshfs server for titan-pc |
| OS | Ubuntu 24.04 LTS | Consistency with titan-pi |

### Recommended

| Component | Spec | Rationale |
|-----------|------|-----------|
| CPU | Intel i5-12400 / Ryzen 5 5600, 6 cores | Modern, efficient, handles concurrent agent load |
| RAM | **16GB** | Comfortable headroom for 5 agents + services + build processes + potential future agents |
| Storage | 512GB NVMe SSD | Fast I/O for Shuri's code operations. Room for Docker images, logs, backups. |
| Network | Gigabit Ethernet | Required for sshfs performance |
| OS | Ubuntu 24.04 LTS | |

### Ideal (Future-Proof)

| Component | Spec | Rationale |
|-----------|------|-----------|
| CPU | Intel i7 / Ryzen 7, 8+ cores | Room for 8+ agents, parallel builds, Docker |
| RAM | **32GB** | Can run ALL 10 agents on one machine if needed. Ultimate flexibility. |
| Storage | 1TB NVMe SSD | Room for everything + Docker images + database growth |

**Cost estimate (India):**
- Minimum: ~Rs 25-30K ($300-360)
- Recommended: ~Rs 35-45K ($420-540)
- Ideal: ~Rs 50-65K ($600-780)

---

## 9. Open Questions for CEO

1. **New PC specs?** — What hardware is being acquired? RAM amount determines which distribution option we use.
2. **Timeline?** — When does the new PC arrive? This sets the migration schedule.
3. **Gitea migration?** — Is the Gitea instance moving to the new PC, or staying on titan-pi?
4. **Domain name?** — What hostname for the new machine? Suggesting "titan-prime" but CEO may prefer different.
5. **titan-pi long-term?** — Keep as backup/monitoring indefinitely, or plan to retire eventually?

---

## 10. Coordination with Fury

This brief covers the **operational/product view** (agent placement, resource budgets, product dependencies, migration steps). Fury is preparing the **strategic view** (6-pillar deep analysis, sovereignty architecture, risk assessment, long-term scaling).

Joint recommendation will merge both into a single infrastructure expansion plan.

---

*DRAFT — Pepper (CPO). Operational view for 3-machine infrastructure expansion. Awaiting Fury's strategic assessment for joint merge.*
