---
authors: fury, pepper
date: 2026-03-25
type: joint-infrastructure-plan
trigger: CEO P1 directive — 3-machine infrastructure expansion
status: JOINT RECOMMENDATION — Ready for CEO review
---

# Joint Infrastructure Expansion Plan — 3-Machine Fleet

**From:** Fury (Strategy) + Pepper (Product)
**To:** CEO
**Date:** Mar 25, 2026
**Priority:** P1 — CEO directive

---

## Executive Summary

Adding a 3rd machine solves three critical problems: (1) eliminates RPi SD card corruption risk from source of truth, (2) relieves titan-pc memory starvation (3.5GB/4GB swap), and (3) enables sustainable 10-agent operation with failover. We jointly recommend **functional separation** — coordination on titan-new, compute on titan-pc, backup on titan-pi — using a **7-4-0 agent distribution**.

**Total investment:** INR 21,000-25,000 (refurbished HP EliteDesk)
**Migration time:** ~9 hours, ~1.5 hours staggered downtime
**Target date:** Mar 29-30 (syncs with Happy onboarding)
**ROI:** One prevented RPi crash = INR 16,000-32,000 in recovery costs. Hardware pays for itself after one incident.

---

## 1. Current State — Why This Is Needed NOW

### Resource Reality (Measured Mar 25)

| Machine | CPU | RAM Total | RAM Available | Swap Used | Agents | Risk |
|---------|-----|-----------|---------------|-----------|--------|------|
| titan-pi (RPi5, aarch64) | 4 cores | 15 GB | 9.8 GB | 0/1 GB | 6 (CEO + 5) | **CORRUPTION** — SD card, frequent crashes |
| titan-pc (i5-8400, x86) | 6 cores | 7.6 GB | 4.3 GB | **3.5/4 GB** | 4 | **MEMORY STARVED** — swapping heavily |

### Critical Problems

1. **titan-pi corruption risk (P0):** RPi runs on SD card. Power loss or crash = potential filesystem corruption. This machine is our source of truth (agents, skills, soul-v2, soul-roles). Losing it means losing everything not in git. 4+ crashes documented in the last week.

2. **titan-pc memory starvation (P1):** 3.5GB of 4GB swap used. Adding Happy (5th agent) pushes toward OOM. Orphaned processes from crashes cascade into memory exhaustion — documented pattern.

3. **sshfs single point of failure (P1):** titan-pc mounts from titan-pi. If titan-pi goes down, all 4 titan-pc agents lose access to source of truth, skills, and role definitions. A single RPi crash takes down 10/10 agents.

4. **No failover (P1):** If titan-pi dies, zero automated recovery. Manual intervention required to restore all services.

5. **sshfs latency (P2):** Shuri writes code through sshfs to titan-pi. Not ideal for heavy build workflows but currently acceptable.

---

## 2. Agreed Topology — Functional Separation (7-4-0)

### Architecture

```
                    +----------------------------------+
                    |   titan-new (NEW PC)              |
                    |   COORDINATION + SOURCE OF TRUTH  |
                    |                                    |
                    |   Agents (7): CEO, Friday, Pepper, |
                    |     Fury, Loki, Xavier, Hawkeye    |
                    |                                    |
                    |   Services: soul-v2 (:3002),       |
                    |     soul-scout (:3020),            |
                    |     soul-tutor (:3006),            |
                    |     soul-tasks, soul-courier       |
                    |                                    |
                    |   Source of truth: agents/, skills/,|
                    |     soul-roles/, soul-v2/           |
                    |                                    |
                    |   RAM: 16-32 GB | SSD | x86_64    |
                    +--------+--------------+-----------+
                             |              |
                   sshfs     |              |   rsync (daily)
                   mount     |              |
                             |              |
              +--------------+              +-------------------+
              |                                                  |
    +---------v--------------+             +--------------------v--+
    |   titan-pc             |             |   titan-pi            |
    |   HEAVY COMPUTE        |             |   BACKUP + MONITORING |
    |                        |             |                       |
    |   Agents (4): Shuri,   |             |   Agents: Guardian    |
    |     Happy, Banner,     |             |   Role: Hot standby,  |
    |     Stark              |             |     daily backup,     |
    |                        |             |     health monitor    |
    |   Builds, tests,       |             |                       |
    |   ML, trading          |             |   rsync daily from    |
    |                        |             |   titan-new           |
    |   RAM: 7.6 GB | HDD   |             |   RAM: 15 GB          |
    |   CPU: i5-8400 (6c)   |             |                       |
    +-----------+------------+             +-----------------------+
                |
                sshfs mount from titan-new
```

### Why 7-4-0 (Not 5-5-0)

Both Fury and Pepper independently evaluated topology options. Pepper initially proposed 5-5-0 (Shuri+Happy on titan-new for local codebase), Fury proposed 7-4-0 (functional separation). After review, we jointly agree **7-4-0 is superior**:

| Factor | 5-5-0 | 7-4-0 (Chosen) |
|--------|-------|-----------------|
| Shuri build speed | Local SSD (fast) | titan-pc i5-8400 = strongest CPU in fleet |
| Code access | Local disk | sshfs to titan-new SSD (fast enough for code ops) |
| titan-pc memory | 5 agents = tight | 4 agents = comfortable headroom |
| Pepper placement | titan-pc (no change) | titan-new (frees ~450MB for Happy) |
| Functional clarity | Mixed workloads | Clean separation: coordination vs compute |

**Key insight:** titan-pc's i5-8400 (6 physical cores) is the strongest CPU in the fleet. Shuri's builds (`go build`, `pytest`, `npm`) benefit more from CPU than from local disk. sshfs to an SSD on titan-new eliminates the latency concern.

---

## 3. Machine Roles — Detailed

### titan-new — COORDINATION + SOURCE OF TRUTH

| Attribute | Value |
|-----------|-------|
| **Role** | Source of truth, coordination hub, all services |
| **Agents (7)** | team-lead (CEO), Friday, Pepper, Fury, Loki, Xavier, Hawkeye |
| **Services** | soul-v2 (:3002), soul-scout (:3020), soul-tutor (:3006), soul-tasks, soul-courier |
| **Source of truth** | ~/.claude/agents/, ~/.claude/skills/, ~/soul-roles/, ~/soul-v2/, ~/portfolio-rishav/ |
| **Network** | Ethernet LAN (192.168.0.x), sshfs server for titan-pc |
| **Storage** | SSD (primary), synced daily to titan-pi |

**Why these agents here:**
- **Xavier** needs soul-tutor at localhost:3006 (hard constraint)
- **Hawkeye** needs soul-scout at localhost:3020 (hard constraint)
- **CEO, Friday, Pepper, Fury, Loki** are coordination/strategy agents — need fast filesystem access to briefs/decisions/inboxes, not heavy compute
- All 7 are primarily I/O-bound (reading files, web searches, messaging), not CPU-bound

### titan-pc — HEAVY COMPUTE

| Attribute | Value |
|-----------|-------|
| **Role** | Build machine — compilation, testing, analysis, trading |
| **Agents (4)** | Shuri, Happy, Banner, Stark |
| **Services** | None (all services on titan-new). Gitea Docker + Vaultwarden Docker stay here. |
| **Mounts** | sshfs from titan-new (replaces current titan-pi mount) |
| **Storage** | 2TB HDD (/mnt/vault), SSD (OS) |

**Why these agents here:**
- **Shuri + Happy** write code and run tests — need the fastest CPU for `go build`, `npm run build`, `pytest`
- **Banner** runs Python/ML analysis — benefits from 6 cores
- **Stark** runs trading analysis — bursty, can be paused if RAM is tight
- Co-locating Shuri + Happy enables code review workflow without network hop between them

### titan-pi — BACKUP + MONITORING

| Attribute | Value |
|-----------|-------|
| **Role** | Hot standby, backup, health monitoring |
| **Agents** | soul-guardian only (watchdog) |
| **Services** | Standby copies (not running, ready to activate on failover) |
| **Mounts** | rsync from titan-new (daily at 3 AM) |
| **Storage** | 117GB SD card |

**Why demoted, not removed:** 15GB RAM + 4 cores are useful for emergency failover. SD card is unreliable as primary, but acceptable for backup. Can run 7+ agents in emergency if titan-new fails.

---

## 4. Co-location Requirements (Hard Constraints)

| Constraint | Reason | Machine |
|------------|--------|---------|
| Xavier + soul-tutor | Tutor API at localhost:3006 | titan-new |
| Hawkeye + soul-scout | Scout API at localhost:3020 | titan-new |
| Shuri + Happy | Shared codebase, code review workflow, strongest CPU | titan-pc |
| All agents + source of truth | Skills, agent defs, role configs | titan-new (via sshfs for titan-pc) |

### Product Integration Dependencies (Pepper)

| Integration | Requirement | Satisfied? |
|-------------|-------------|------------|
| Xavier prepping for Scout pipeline companies | Xavier reads Hawkeye's briefs | YES — both on titan-new, local filesystem |
| Loki content driving inbound | Loki reads Scout data for content | YES — both on titan-new |
| SoulGraph credential in outreach | Hawkeye templates reference SoulGraph | YES — both on titan-new, git repo accessible |
| Banner analytics on all products | Banner reads all agent briefs | YES — sshfs mount from titan-new |
| Stark market data for strategy | Stark and Fury share briefs | YES — Fury on titan-new, Stark reads via sshfs |

---

## 5. Resource Budgets

### titan-new (Requires 16GB+ RAM)

| Component | RAM Est. | Notes |
|-----------|----------|-------|
| 7 claude processes | ~3.5 GB | ~500MB each (sonnet agents lighter) |
| 7 MCP server sets | ~700 MB | ~100MB each |
| soul-v2 + scout + tutor + tasks | ~80 MB | Go binaries, lightweight |
| soul-courier (Python) | ~60 MB | Single daemon |
| Gitea (if migrated) | ~100 MB | Optional — see Decision #5 below |
| OS + buffers | ~1.5 GB | |
| **Total estimated** | **~6 GB** | Leaves 10GB free on 16GB machine |

**With 16GB:** 10GB headroom. **With 32GB:** 26GB headroom (future-proof).

### titan-pc (Current 7.6GB — MASSIVELY IMPROVED)

| Component | Now (4 agents) | After (4 agents) | Delta |
|-----------|----------------|-------------------|-------|
| claude processes | ~1.4 GB | ~1.4 GB | Same agent count |
| MCP servers | ~400 MB | ~300 MB | Happy has no playwright (~100MB saved) |
| sshfs mounts | ~35 MB | ~35 MB | Direction changes (titan-new instead of titan-pi) |
| Swap usage | **3.5 GB** | **<0.5 GB** | **3GB FREED** — no more memory starvation |

**Key improvement:** Pepper moves to titan-new, freeing ~450MB. No services on titan-pc. All 7.6GB is for agents + builds.

**If still tight:** Pause Stark during heavy build operations (saves ~350MB).

### titan-pi (Demoted)

| Component | RAM | Notes |
|-----------|-----|-------|
| soul-guardian | ~50 MB | Watchdog daemon |
| rsync agent | ~20 MB | Background sync |
| OS | ~500 MB | Minimal |
| **Free for failover** | **~14 GB** | Can spin up 7+ agents in emergency |

### Before vs After

| Metric | Before (2 machines) | After (3 machines) |
|--------|---------------------|---------------------|
| Total RAM | 22.6 GB | 39-55 GB (+72-143%) |
| Available RAM | ~14 GB | ~29-45 GB |
| Swap pressure | **3.5 GB on titan-pc** | **<0.5 GB** |
| Agent capacity | 10 (stressed) | **15+** (comfortable) |
| Source of truth | SD card (RPi) | **SSD** (new PC) |
| Failover | **NONE** | Hot standby (titan-pi) |
| Services | RPi (risky) | **Dedicated reliable hardware** |

---

## 6. Migration Strategy

### Principles
- **Zero data loss** — everything in git first, then copy
- **Reversible at every step** — titan-pi stays intact throughout
- **Minimal downtime** — agents move one at a time
- **Test before cutover** — verify each agent works on new machine before stopping old one

### Phase 0: Pre-Migration (Day 0 — 2 hours)

| Step | Action | Verify |
|------|--------|--------|
| 0.1 | Set up new PC: OS (Ubuntu 24.04 LTS), user `rishav`, SSH key auth | `ssh titan-new` from both machines |
| 0.2 | Install dependencies: claude CLI, python3, node, go, tmux | `claude --version`, `go version` |
| 0.3 | Configure network: static ethernet IP (192.168.0.x), WiFi | `ping titan-new` from both |
| 0.4 | Add DNS entries: `/etc/hosts` on all 3 machines | Bidirectional ping by hostname |
| 0.5 | Install Gitea (Docker or binary) if migrating | `curl http://titan-new:3000` |

### Phase 1: Copy Source of Truth (Day 0 — 1 hour)

| Step | Action | Verify |
|------|--------|--------|
| 1.1 | `rsync -avz --progress titan-pi:~/.claude/ ~/.claude/` on titan-new | File counts match |
| 1.2 | `rsync -avz --progress titan-pi:~/soul-roles/ ~/soul-roles/` | File counts match |
| 1.3 | `git clone` soul-v2, portfolio, soulgraph from Gitea | `git log` matches |
| 1.4 | `rsync -avz --progress titan-pi:~/soul-v2/ ~/soul-v2/` (local state) | Binary builds work |
| 1.5 | Build Go binaries: `cd ~/soul-v2 && go build -o soul-chat ./cmd/chat` etc. | All binaries compile |

**ROLLBACK:** titan-pi untouched. If anything fails, abort and resume using titan-pi.

### Phase 2: Verify Services on titan-new (Day 0 — 30 min)

| Step | Action | Verify |
|------|--------|--------|
| 2.1 | Start soul-v2: `./soul-chat serve` | `curl localhost:3002` returns 200 |
| 2.2 | Start soul-scout: `./soul-scout serve` | `curl localhost:3020` returns 200 |
| 2.3 | Start soul-tutor: `./soul-tutor serve` | `curl localhost:3006` returns 200 |
| 2.4 | Create systemd units with `Restart=always` | `systemctl --user status soul-v2*` |
| 2.5 | Test cross-machine: `curl titan-new:3002` from titan-pc | Cross-machine access works |

### Phase 3: Reverse sshfs Direction (Day 0 — 30 min)

| Step | Action | Verify |
|------|--------|--------|
| 3.1 | Stop soul-mounts.service on titan-pc | Mounts unmounted |
| 3.2 | Update mount config: point at titan-new IP | Config file updated |
| 3.3 | Start soul-mounts.service on titan-pc | `ls ~/soul-v2/` shows files from titan-new |
| 3.4 | Verify Shuri/Banner/Stark can access files | Agent read test |

**ROLLBACK:** Revert mount config to titan-pi IP. Restart soul-mounts. ~2 minutes.

### Phase 4: Migrate Agents — One at a Time (Day 1 — 3 hours)

| Order | Agent | From | To | Test |
|-------|-------|------|----|------|
| 1 | Friday | titan-pi | titan-new | Inbox send/receive, schedule check |
| 2 | Pepper | titan-pc | titan-new | Roadmap read, registry update |
| 3 | Fury | titan-pi | titan-new | Market research, brief writing |
| 4 | Loki | titan-pi | titan-new | Content pipeline access |
| 5 | Xavier | titan-pi | titan-new | Tutor drill (must work with local soul-tutor) |
| 6 | Hawkeye | titan-pi | titan-new | Scout operations (must work with local soul-scout) |
| 7 | CEO (team-lead) | titan-pi | titan-new | Full team communication test |

**Why this order:** Low-risk agents first (Friday, Pepper), then strategy (Fury, Loki), then service-dependent (Xavier, Hawkeye) after verifying local services, then CEO last after all agents confirmed.

**2-hour stabilization window after Phase 4 before proceeding.** (Pepper recommendation — catch any sshfs mount issues, memory pressure, or communication failures before adding more changes.)

### Phase 5: Demote titan-pi (Day 1 — 1 hour)

| Step | Action |
|------|--------|
| 5.1 | Stop all agents on titan-pi |
| 5.2 | Stop services on titan-pi (soul-v2, soul-scout, soul-tutor) |
| 5.3 | Configure rsync cron: titan-new -> titan-pi (daily at 3 AM) |
| 5.4 | Deploy soul-guardian on titan-pi (monitors titan-new + titan-pc) |
| 5.5 | Create `soul-failover` script on titan-pi |
| 5.6 | Update soul-team launcher to use new topology |

### Phase 6: Onboard Happy (Day 2)

| Step | Action |
|------|--------|
| 6.1 | Create Happy agent definition on titan-new (source of truth) |
| 6.2 | Start Happy on titan-pc (tmux pane, via SSH from titan-new) |
| 6.3 | Verify Happy can access source of truth via sshfs |
| 6.4 | Assign onboarding tasks per Shuri capacity plan |

**Happy spec:** ~/soul-roles/shared/briefs/pepper-happy-agent-spec-2026-03-24.md (deployment-ready, CEO-approved)

### Total Migration Timeline

| Phase | Duration | Downtime |
|-------|----------|----------|
| Phase 0-2 (setup + copy + verify) | 3.5 hours | **ZERO** — titan-pi still running |
| Phase 3 (sshfs reversal) | 30 min | **~5 min** for titan-pc agents (mount switch) |
| Phase 4 (agent migration) | 3 hours | **~10 min per agent** (restart in new location) |
| Stabilization window | 2 hours | **ZERO** — monitoring only |
| Phase 5 (demote titan-pi) | 1 hour | **ZERO** — already cutover |
| Phase 6 (Happy onboard) | 1 hour | **ZERO** — new agent, not migration |
| **TOTAL** | **~11 hours** | **~1.5 hours** (staggered, not continuous) |

**Can be done Mar 29-30 weekend.** Good synergy with Happy onboarding. If hardware takes longer, plan remains valid — just shift dates.

---

## 7. Resilience — Single Machine Failure Analysis

| Machine Down | Impact | Recovery | RTO |
|--------------|--------|----------|-----|
| **titan-new** | **CRITICAL** — all services down, 7 agents down | Activate titan-pi failover: start services from rsync copy, redirect sshfs, launch core agents | <5 min (scripted), <15 min (manual) |
| **titan-pc** | **MODERATE** — builds stop, no code changes | Restart agents on titan-pi temporarily (15 min). Services + coordination unaffected. | 5 min (reboot) / 15 min (failover to titan-pi) |
| **titan-pi** | **MINIMAL** — backup paused, monitoring gaps | No action needed. Resume rsync when back. | No impact on operations |

### titan-new Failover Script

```bash
# On titan-pi — automated or manual:
soul-failover activate
# 1. Starts soul-v2, soul-scout, soul-tutor from last rsync copy
# 2. Updates titan-pc sshfs to point at titan-pi
# 3. Launches core agents (CEO, Friday, Pepper) on titan-pi
# 4. Sends alert (email/webhook)
# 5. Deferred: Xavier, Hawkeye, Fury, Loki can start if RAM permits
```

**RPO (Recovery Point Objective):** <24 hours (last rsync). Reduce to <1 hour with more frequent sync.

### Resilience Score

| Requirement | Current | After |
|-------------|---------|-------|
| Survive any single machine failure | **NO** | **YES** |
| Auto-recovery | **NONE** | **PARTIAL** (soul-failover script for titan-new) |
| Data durability | Git only | **Git + daily rsync + SSD** |
| No single point of failure | **titan-pi = SPOF** | **Distributed, backup on titan-pi** |

---

## 8. 6-Pillar Alignment

| Pillar | Current State | After Expansion |
|--------|--------------|-----------------|
| **RESILIENT** | Single point of failure (titan-pi). One crash = everything down. | 3-machine fleet. Hot standby. rsync daily. Dual guardians. First time we survive any single machine failure. |
| **PERFORMANT** | sshfs latency for code edits. titan-pc RAM-constrained (3.5GB swap). | Shuri on fastest CPU. titan-pc swap drops from 3.5GB to <0.5GB. Services on SSD instead of SD card. |
| **SOVEREIGN** | All local. No cloud dependency. | Same — new PC is local. Gitea stays self-hosted. No new external dependencies introduced. |
| **SCALABLE** | 10 agents, can't add more without RAM pressure. | 10 agents with headroom. 3 machines scale to 15+ agents. GPU path available (titan-pc). |
| **OBSERVABLE** | soul-guardian on titan-pi only. | Dual guardians (titan-new + titan-pi). Cross-machine health checks. Proposed 3-machine dashboard. |
| **EFFICIENT** | Agents on suboptimal machines. Strategy + compute mixed. | Functional separation: right agent, right machine, right data locality. |

---

## 9. Monitoring — Multi-Machine Guardian

### Health Check Matrix

| Check | Frequency | Alert Threshold | Action |
|-------|-----------|----------------|--------|
| RAM per machine | 30s | <1 GB available | Kill heaviest non-essential agent |
| CPU per machine | 30s | >95% sustained 5 min | Warning to CEO |
| Disk space | 5 min | <5 GB free | Warning to CEO |
| Service health | 1 min | Any service down | Auto-restart + alert |
| sshfs mount health | 1 min | Mount stale/disconnected | Auto-remount + alert |
| Agent heartbeat | 5 min | Agent not responding | Restart + alert |
| Cross-machine ping | 1 min | >50ms or timeout | Network alert |

### Proposed Dashboard (soul-monitor v2)

```
soul-monitor v2 -- 3-machine dashboard

titan-new (COORDINATION)     titan-pc (COMPUTE)          titan-pi (BACKUP)
========================     ========================     ========================
CPU: ####.... 45%            CPU: ######.. 72%            CPU: ........ 3%
RAM: ####.... 6/16 GB       RAM: #####... 5/7.6 GB      RAM: #....... 0.5/15 GB
Swap: ........ 0/4 GB       Swap: #....... 0.5/4 GB     Swap: ........ 0/1 GB

Agents: 7/7 OK              Agents: 4/4 OK               Agents: 0 (standby)
Services: 4/4 OK            Services: 0                  Guardian: OK | Backup: 3h ago
Courier: OK                 sshfs: OK                    rsync: last 03:00
```

---

## 10. Hardware Recommendation (Fury — Researched Mar 25)

### Specific Options

| Rank | Model | CPU | RAM | Storage | Price (INR) | Notes |
|------|-------|-----|-----|---------|-------------|-------|
| **#1 (BEST VALUE)** | Refurbished HP EliteDesk 800 G4/G5 | i5-8500/9500 | 16GB DDR4 | 256-512GB SSD | ~21,000-25,000 | Enterprise-grade, 24/7 cooling, quiet. Computify.in, RefurbishedPC.in |
| **#2 (BUDGET)** | Beelink Mini S12 | Intel N95 | 8GB->16GB | 256GB SSD | ~14,000-18,000 + 3K RAM | Ultra-low power (<5W idle). Consumer-grade. Amazon.in |
| **#3 (PERFORMANCE)** | ACEMAGICIAN S3A | Ryzen 7 8745HS | 16GB DDR5 | 512GB NVMe | ~30,000-40,000 | Overkill but future-proof. Amazon.in |

**Joint recommendation: Option #1 — Refurbished HP EliteDesk 800 G4.**
- Enterprise hardware designed for 24/7 uptime (data center cooling)
- Same i5 generation as titan-pc (known quantity)
- 16GB sufficient, upgradeable to 32GB for ~3,000
- Better thermal design than consumer mini PCs for always-on server use
- **ROI:** One prevented RPi crash costs 4-8 hours x INR 4,000+/hr = INR 16,000-32,000. Hardware pays for itself after one incident.

---

## 11. Operational Additions (Pepper)

### Items to Include in Migration

1. **soul-courier daemon** — must move to titan-new (handles inter-agent messaging via clawteam). Currently on titan-pi.

2. **cgroup limits** — Shuri's current slice config (`soul-agents.slice`) must be replicated on both titan-new and titan-pc. Include Happy in titan-pc's cgroup config.

3. **Analytics collector** — Banner's data collection needs to be configured for the new topology. Analytics DB location should be on titan-new (source of truth) with Banner accessing via sshfs.

4. **systemd auto-start** — All services on titan-new MUST have `Restart=always` and be enabled at boot. Current issue: Scout and Tutor don't auto-start after reboot (ongoing Day 2 outage proves this).

5. **Cloudflare Tunnel** — If configured for public soul-v2 demo, reconfigure to point at titan-new:3002 (was titan-pi:3002).

### Items That Stay Put

| Service | Location | Reason |
|---------|----------|--------|
| Gitea (Docker) | titan-pc | See Decision #5 below |
| Vaultwarden (Docker) | titan-pc | Stable, no reason to migrate |
| Portainer (Docker) | titan-pc | Docker management, stays with Docker |
| Duplicati (Docker) | titan-pc | Backup service, stays with storage |

---

## 12. Networking Changes

| Change | Old | New |
|--------|-----|-----|
| sshfs source | titan-pi -> titan-pc | titan-new -> titan-pc |
| soul-v2 access | titan-pi :3002 | titan-new :3002 |
| Scout API | titan-pi :3020 | titan-new :3020 |
| Tutor API | titan-pi :3006 | titan-new :3006 |
| Gitea SSH | titan-pc :222 (Docker) | Unchanged |
| /etc/hosts | 2-machine entries | Add titan-new IP on all 3 machines |
| Cloudflare Tunnel | titan-pi :3002 | titan-new :3002 |

### DNS/hosts Configuration

All 3 machines need `/etc/hosts` entries:

```
# On titan-new:
192.168.0.196   titan-pc
192.168.0.128   titan-pi
127.0.0.1       titan-new

# On titan-pc:
192.168.0.NEW   titan-new
192.168.0.128   titan-pi
127.0.0.1       titan-pc

# On titan-pi:
192.168.0.NEW   titan-new
192.168.0.196   titan-pc
127.0.0.1       titan-pi
```

### tmux Launcher Update

`soul-team` script needs rewriting:
- Runs FROM titan-new (not titan-pi)
- titan-new panes: CEO, Friday, Pepper, Fury, Loki, Xavier, Hawkeye (7 agents via local tmux)
- titan-pc panes: Shuri, Happy, Banner, Stark (4 agents via SSH)
- titan-pi: No agent panes (guardian runs as systemd)
- soul-courier.service on titan-new

---

## 13. Strategic Implications (Fury)

### Immediate Benefits
1. **Happy agent is viable** — titan-pc memory pressure was the main risk. Resolved.
2. **No more OOM cascades** — documented pattern eliminated. Each machine has adequate headroom.
3. **Source of truth on SSD** — SD card corruption risk drops to zero for primary operations.
4. **Services on dedicated hardware** — soul-v2, Scout, Tutor run on stable x86 with SSD.

### Medium-Term Enables
5. **Room for 12th+ agent** — 29-45 GB headroom. Can add agents without hardware discussions.
6. **Dedicated test runner** — titan-pc runs full CI/CD without affecting coordination.
7. **GPU path** — If SoulGraph Phase 3 fine-tuning needs GPU, titan-pc is the candidate.
8. **Distributed resilience** — First time we survive a machine failure without total team outage.

### Long-Term Vision
9. **Network of specialized compute nodes** — architecture scales to N machines.
10. **Public demo capability** — titan-new serves public demo via Cloudflare Tunnel while titan-pc builds and titan-pi monitors. No interference between public traffic and agent operations.

---

## 14. CEO Decisions Required

| # | Decision | Options | Joint Recommendation |
|---|----------|---------|---------------------|
| 1 | **APPROVE 3-machine topology** | 7-4-0 functional separation as described | **APPROVE** — both Fury and Pepper aligned |
| 2 | **APPROVE hardware budget** | INR 21K-40K depending on model | **Option #1: HP EliteDesk 800 G4, ~INR 21-25K** |
| 3 | **CONFIRM new PC RAM** | 16GB (sufficient) vs 32GB (future-proof) | **16GB** — 10GB headroom, upgradeable later for 3K |
| 4 | **CONFIRM migration weekend** | Mar 29-30 (aligns with Happy onboarding) | **Mar 29-30** with 2-hour stabilization window between migration and Happy onboard |
| 5 | **Gitea migration** | (A) Keep on titan-pc Docker (/mnt/vault 2TB HDD) or (B) Move to titan-new | **Keep on titan-pc** (Fury) — large repo data on 2TB HDD, high-effort move, low benefit. titan-new accesses via LAN. |
| 6 | **Hostname for new machine** | titan-new / titan-prime / other | CEO preference (we used "titan-new" throughout but either works) |
| 7 | **titan-pi long-term plan** | (A) Keep as backup indefinitely, (B) Repurpose eventually, (C) Phase out | **Keep as backup** — 15GB RAM for failover is valuable insurance at zero ongoing cost |

---

## 15. Proposed Timeline

| Date | Action |
|------|--------|
| Mar 25 (today) | CEO reviews plan, approves, orders hardware |
| Mar 26-28 | Hardware arrives, Phase 0 setup during evenings |
| Mar 29 (Sat) | Phase 1-4: Copy source of truth, verify services, reverse sshfs, migrate agents |
| Mar 29 PM | 2-hour stabilization window |
| Mar 30 (Sun) | Phase 5: Demote titan-pi. Phase 6: Onboard Happy on titan-pc. |
| Mar 31 (Mon) | Full 3-machine operation with 10 agents |
| Apr 1-2 | 48-hour stability monitoring |

**If hardware takes longer:** Plan remains valid. Phases 0-6 take ~11 hours once hardware arrives. Weekend execution minimizes disruption to the 90-day plan.

---

## Appendix: What Does NOT Change

| Item | Status |
|------|--------|
| Gitea (Docker on titan-pc) | No change — repos on /mnt/vault |
| Vaultwarden (Docker on titan-pc) | No change — stable |
| Git remote strategy (private->Gitea, public->GitHub) | No change |
| 6 Pillars compliance | Maintained throughout |
| Agent definitions / skills format | No change (just moves to titan-new) |
| clawteam communication protocol | No change (courier moves to titan-new) |

---

*Joint recommendation by Fury (Strategy) and Pepper (Product). Ready for CEO review and approval.*
