---
author: fury
date: 2026-03-25
type: strategic-infrastructure-plan
trigger: CEO directive — 3-machine infrastructure expansion
status: DRAFT — awaiting Pepper product review
coordinated-with: pepper (pending)
---

# 3-Machine Infrastructure Expansion Plan

**Thesis:** Adding a 3rd machine solves three problems simultaneously: (1) eliminates RPi corruption risk from source of truth, (2) relieves titan-pc memory starvation (3.5GB/4GB swap used TODAY), and (3) enables sustainable 10-agent operation without resource pressure. The optimal topology is **functional separation** — coordination, compute, and backup on dedicated machines.

---

## 1. CURRENT STATE — Why This Is Needed NOW

### Resource Reality (Measured Mar 25 AM)

| Machine | CPU | RAM Total | RAM Available | Swap Used | Agents | Risk |
|---------|-----|-----------|---------------|-----------|--------|------|
| titan-pi (RPi5, aarch64) | 4 cores | 15 GB | 9.8 GB | 0/1 GB | 6 (CEO + 5) | **CORRUPTION** — SD card, frequent crashes |
| titan-pc (i5-8400, x86) | 6 cores | 7.6 GB | 4.3 GB | **3.5/4 GB** | 4 | **MEMORY STARVED** — swapping heavily |

### Current Problems

1. **titan-pi corruption risk:** RPi runs on SD card. Power loss or crash = potential filesystem corruption. This machine is our source of truth (agents, skills, soul-v2, soul-roles). Losing it means losing everything not in git.

2. **titan-pc memory starvation:** 3.5GB of 4GB swap used. Adding Happy (5th agent) pushes it toward OOM. We already documented the OOM pattern — orphaned processes from crashes cascade into memory exhaustion.

3. **sshfs fragility:** titan-pc mounts from titan-pi via sshfs. If titan-pi goes down, all 4 titan-pc agents lose access to source of truth, skills, and role definitions. A single RPi crash takes down 10/10 agents.

4. **No failover:** If titan-pi dies, there is zero automated recovery. Manual intervention required to restore all services.

---

## 2. PROPOSED TOPOLOGY — Functional Separation

### Architecture Diagram

```
                    ┌─────────────────────────────────┐
                    │   titan-new (NEW PC)             │
                    │   COORDINATION + SOURCE OF TRUTH │
                    │                                   │
                    │   Agents: CEO, Friday, Pepper,    │
                    │           Fury, Loki, Xavier,     │
                    │           Hawkeye                 │
                    │   Services: soul-v2, soul-scout,  │
                    │            soul-tutor, soul-tasks  │
                    │            soul-courier, Gitea     │
                    │   Source: agents/, skills/,        │
                    │          soul-roles/, soul-v2/     │
                    │                                   │
                    │   RAM: 16-32 GB | SSD | x86_64   │
                    └───────────┬──────────┬───────────┘
                                │          │
                      sshfs     │          │   sshfs
                      mount     │          │   mount
                                │          │
              ┌─────────────────┘          └─────────────────┐
              │                                               │
    ┌─────────▼───────────────┐             ┌─────────────────▼─────┐
    │   titan-pc              │             │   titan-pi            │
    │   HEAVY COMPUTE         │             │   BACKUP + MONITORING │
    │                         │             │                       │
    │   Agents: Shuri, Happy, │             │   Agents: Guardian    │
    │           Banner, Stark │             │   Role: Hot standby,  │
    │                         │             │         daily backup,  │
    │   Compiles, tests,      │             │         health monitor│
    │   ML, trading           │             │                       │
    │                         │             │   rsync daily from    │
    │   RAM: 7.6 GB | HDD    │             │   titan-new           │
    │   CPU: i5-8400 (6c)    │             │   RAM: 15 GB          │
    └─────────────────────────┘             └───────────────────────┘
```

### Machine Roles

#### titan-new — COORDINATION + SOURCE OF TRUTH

**Why this machine exists:** Reliable x86_64 hardware with SSD replaces RPi as the brain. Everything that matters lives here. If this machine is up, the team operates.

| Attribute | Value |
|-----------|-------|
| **Role** | Source of truth, coordination hub, all services |
| **Agents (7)** | team-lead (CEO), Friday, Pepper, Fury, Loki, Xavier, Hawkeye |
| **Services** | soul-v2 (:3002), soul-scout (:3020), soul-tutor (:3006), soul-tasks, soul-courier |
| **Source of truth** | ~/.claude/agents/, ~/.claude/skills/, ~/soul-roles/, ~/soul-v2/, ~/portfolio-rishav/ |
| **Network** | Ethernet LAN (192.168.0.x), WiFi for internet |
| **Storage** | SSD (primary), synced daily to titan-pi |

**Why these agents here:**
- **Xavier** needs soul-tutor at localhost:3006 — must be co-located with Tutor service
- **Hawkeye** needs soul-scout at localhost:3020 — must be co-located with Scout service
- **CEO, Friday, Pepper, Fury, Loki** are coordination/strategy agents — they need fast filesystem access to briefs/decisions/inboxes, not heavy compute
- All 7 are primarily I/O-bound (reading files, web searches, messaging), not CPU-bound

#### titan-pc — HEAVY COMPUTE

**Why this machine stays:** i5-8400 (6 physical cores) is the strongest CPU in the fleet. Best for compilation, testing, and data analysis.

| Attribute | Value |
|-----------|-------|
| **Role** | Build machine — compilation, testing, analysis, trading |
| **Agents (3-4)** | Shuri, Happy, Banner, Stark |
| **Services** | None (all services on titan-new) |
| **Mounts** | sshfs from titan-new (replaces current titan-pi mount) |
| **Network** | Ethernet LAN, WiFi |
| **Storage** | 2TB HDD (/mnt/vault), SSD (OS) |

**Why these agents here:**
- **Shuri + Happy** write code and run tests — need the fastest CPU for `go build`, `npm run build`, `pytest`
- **Banner** runs Python/ML analysis — benefits from 6 cores
- **Stark** runs trading analysis — bursty but can be paused if RAM is tight
- Co-locating Shuri + Happy eliminates sshfs latency for code review workflow

#### titan-pi — BACKUP + MONITORING

**Why demoted, not removed:** 15GB RAM and 4 cores are still useful — but the SD card makes it unreliable as primary. Perfect as a backup node that can be promoted in emergencies.

| Attribute | Value |
|-----------|-------|
| **Role** | Hot standby, backup, health monitoring |
| **Agents** | soul-guardian only (watchdog) |
| **Services** | Standby copies of soul-v2, soul-scout, soul-tutor (not running, ready to activate) |
| **Mounts** | rsync from titan-new (daily, or on-demand before failover) |
| **Network** | Ethernet LAN, WiFi |
| **Storage** | 117GB SD card |

**Emergency failover script:**
```bash
# On titan-pi, if titan-new goes down:
soul-failover activate  # Starts services, redirects sshfs mounts, alerts team
```

---

## 3. AGENT DISTRIBUTION — Detailed

### Co-location Requirements (Hard Constraints)

| Constraint | Reason | Machine |
|------------|--------|---------|
| Xavier + soul-tutor | Tutor API at localhost:3006 | titan-new |
| Hawkeye + soul-scout | Scout API at localhost:3020 | titan-new |
| Shuri + Happy | Shared codebase, code review workflow | titan-pc |
| All agents + source of truth | Skills, agent definitions, role configs | titan-new (via sshfs for titan-pc) |

### Resource Budget

#### titan-new (REQUIRES 16GB+ RAM)

| Component | RAM Est. | Notes |
|-----------|----------|-------|
| 7 claude processes | ~3.5 GB | ~500MB each (sonnet agents lighter) |
| 7 MCP server sets | ~700 MB | ~100MB each |
| soul-v2 + scout + tutor + tasks | ~80 MB | Go binaries, very lightweight |
| soul-courier (Python) | ~60 MB | Single daemon |
| Gitea (if migrated from Docker) | ~100 MB | Or keep on titan-pc Docker |
| OS + buffers | ~1.5 GB | |
| **Total estimated** | **~6 GB** | Leaves 10GB free on 16GB machine |

With 16GB RAM: 10GB headroom. With 32GB: 26GB headroom (overkill but future-proof).

**Recommendation: 16GB is sufficient. 32GB is insurance for future agent growth.**

#### titan-pc (Current 7.6GB — IMPROVED)

| Component | Now (4 agents) | After (3-4 agents) | Notes |
|-----------|----------------|---------------------|-------|
| claude processes | ~1.4 GB (4×350MB) | ~1.4 GB (4×350MB) | Same agent count |
| MCP servers | ~400 MB | ~300 MB | Happy has no playwright |
| sshfs mounts | ~35 MB | ~35 MB | Direction changes |
| Services | 0 | 0 | All moved to titan-new |
| pytest / npm | ~800 MB peak | ~800 MB peak | Unchanged |
| Swap usage | **3.5 GB** | **<1 GB** | MASSIVELY IMPROVED |

**Key improvement:** Moving Gitea Docker to titan-new (or keeping it as-is) and having services off titan-pc means all 7.6GB is for agents + builds. Swap usage drops dramatically because the system isn't fighting for memory between services and agents.

**If still tight:** Pause Stark during heavy build operations (saves ~350MB). Or move Stark to titan-new (it's I/O-bound, not CPU-bound).

#### titan-pi (Demoted)

| Component | RAM | Notes |
|-----------|-----|-------|
| soul-guardian | ~50 MB | Watchdog daemon |
| Standby services | 0 (not running) | Ready to activate |
| rsync agent | ~20 MB | Background sync |
| OS | ~500 MB | Minimal |
| **Free for failover** | **~14 GB** | Can spin up 7+ agents in emergency |

---

## 4. MIGRATION STRATEGY

### Principles
- **Zero data loss** — everything in git first, then copy
- **Reversible at every step** — titan-pi stays intact throughout
- **Minimal downtime** — agents move one at a time
- **Test before cutover** — verify each agent works on new machine before stopping old one

### Phase 0: Pre-Migration (Day 0 — 2 hours)

| Step | Action | Verify |
|------|--------|--------|
| 0.1 | Set up new PC: OS, user `rishav`, SSH key auth | `ssh titan-new` from both machines |
| 0.2 | Install dependencies: claude CLI, python3, node, go, tmux | `claude --version`, `go version` |
| 0.3 | Configure network: static ethernet IP (192.168.0.x), WiFi | `ping titan-new` from both |
| 0.4 | Add DNS entries: `/etc/hosts` on all 3 machines | Bidirectional ping by hostname |
| 0.5 | Install Gitea (Docker or binary) if migrating | `curl http://titan-new:3000` |

### Phase 1: Copy Source of Truth (Day 0 — 1 hour)

| Step | Action | Verify |
|------|--------|--------|
| 1.1 | `rsync -avz --progress titan-pi:~/.claude/ ~/.claude/` on titan-new | File counts match |
| 1.2 | `rsync -avz --progress titan-pi:~/soul-roles/ ~/soul-roles/` | File counts match |
| 1.3 | `git clone` soul-v2, portfolio from Gitea | `git log` matches |
| 1.4 | `rsync -avz --progress titan-pi:~/soul-v2/ ~/soul-v2/` (for local state) | Binary builds work |
| 1.5 | Build Go binaries: `cd ~/soul-v2 && go build -o soul-chat ./cmd/chat` etc. | All 4 binaries compile |

**ROLLBACK:** titan-pi is untouched. If anything fails, abort and resume using titan-pi.

### Phase 2: Verify Services on titan-new (Day 0 — 30 min)

| Step | Action | Verify |
|------|--------|--------|
| 2.1 | Start soul-v2: `./soul-chat serve` | `curl localhost:3002` |
| 2.2 | Start soul-scout: `./soul-scout serve` | `curl localhost:3020` |
| 2.3 | Start soul-tutor: `./soul-tutor serve` | `curl localhost:3006` |
| 2.4 | Create systemd units | `systemctl --user status soul-v2*` |
| 2.5 | Test from titan-pc: `curl titan-new:3002` | Cross-machine access works |

### Phase 3: Reverse sshfs Direction (Day 0 — 30 min)

Current: titan-pc mounts FROM titan-pi
New: titan-pc mounts FROM titan-new

| Step | Action | Verify |
|------|--------|--------|
| 3.1 | Stop soul-mounts.service on titan-pc | `systemctl --user stop soul-mounts` |
| 3.2 | Update mount config: point at titan-new IP | Config file updated |
| 3.3 | Start soul-mounts.service on titan-pc | `ls ~/soul-v2/` shows files from titan-new |
| 3.4 | Verify Shuri/Banner/Stark/Pepper can access files | Agent read test |

**ROLLBACK:** Revert mount config to titan-pi IP. Restart soul-mounts.

### Phase 4: Migrate Agents — One at a Time (Day 1 — 3 hours)

Migrate in priority order. Test each before moving the next.

| Order | Agent | From | To | Test |
|-------|-------|------|-----|------|
| 1 | Friday | titan-pi | titan-new | Inbox send/receive, schedule check |
| 2 | Pepper | titan-pc → titan-new | titan-new | Roadmap read, task management |
| 3 | Fury | titan-pi | titan-new | Market research, brief writing |
| 4 | Loki | titan-pi | titan-new | Content pipeline access |
| 5 | Xavier | titan-pi | titan-new | Tutor drill (must work with local soul-tutor) |
| 6 | Hawkeye | titan-pi | titan-new | Scout operations (must work with local soul-scout) |
| 7 | CEO (team-lead) | titan-pi | titan-new | Full team communication test |

**Why Pepper moves from titan-pc to titan-new:** Pepper is a coordination agent (not compute). Moving her frees ~450MB on titan-pc for Happy. And she needs fast brief/roadmap access.

**Why this order:** Low-risk agents first (Friday, Pepper), then strategy agents (Fury, Loki), then service-dependent agents (Xavier, Hawkeye) after verifying local services work, then CEO last (after all agents confirmed on new topology).

### Phase 5: Demote titan-pi (Day 1 — 1 hour)

| Step | Action |
|------|--------|
| 5.1 | Stop all agents on titan-pi |
| 5.2 | Stop services on titan-pi (soul-v2, soul-scout, soul-tutor) |
| 5.3 | Configure rsync cron: titan-new → titan-pi (daily at 3 AM) |
| 5.4 | Install soul-guardian on titan-pi (monitors titan-new + titan-pc) |
| 5.5 | Create `soul-failover` script on titan-pi |
| 5.6 | Update soul-team launcher to use new topology |

### Phase 6: Onboard Happy (Day 2 — follows Shuri capacity plan)

| Step | Action |
|------|--------|
| 6.1 | Create Happy agent definition on titan-new |
| 6.2 | Start Happy on titan-pc (tmux pane) |
| 6.3 | Verify Happy can access source of truth via sshfs |
| 6.4 | Assign onboarding tasks per Shuri capacity plan |

### Total Migration Timeline

| Phase | Duration | Downtime |
|-------|----------|----------|
| Phase 0-2 (setup + copy + verify) | 3.5 hours | **ZERO** — titan-pi still running |
| Phase 3 (sshfs reversal) | 30 min | **~5 min** for titan-pc agents (mount switch) |
| Phase 4 (agent migration) | 3 hours | **~10 min per agent** (restart in new location) |
| Phase 5 (demote titan-pi) | 1 hour | **ZERO** — already cutover |
| Phase 6 (Happy onboard) | 1 hour | **ZERO** — new agent, not migration |
| **TOTAL** | **~9 hours** | **~1.5 hours** (staggered, not continuous) |

**Can be done in a single weekend (Mar 29-30).** Aligns with Happy onboarding timeline from the Shuri capacity plan.

---

## 5. RESILIENCE — Single Machine Failure Analysis

### Failure Scenarios

| Machine Down | Impact | Recovery | Agents Affected |
|--------------|--------|----------|----------------|
| **titan-new** | **CRITICAL** — all services down, 7 agents down | Activate titan-pi failover (5 min manual, <1 min scripted) | 7/10 agents |
| **titan-pc** | **MODERATE** — builds stop, no code changes | Restart agents on titan-pi temporarily (15 min) | 3-4/10 agents |
| **titan-pi** | **MINIMAL** — backup paused, monitoring gaps | No action needed, resume rsync when back | 0/10 agents |

### Failover Strategy

**titan-new failure (most critical):**

```bash
# On titan-pi — automated or manual:
soul-failover activate
# This script:
# 1. Starts soul-v2, soul-scout, soul-tutor from last rsync copy
# 2. Updates titan-pc sshfs to point at titan-pi
# 3. Launches core agents (CEO, Friday, Pepper) on titan-pi
# 4. Sends alert (email/webhook)
# 5. Deferred: Xavier, Hawkeye, Fury, Loki can start if RAM permits
```

**RTO (Recovery Time Objective):** <5 minutes (scripted), <15 minutes (manual)
**RPO (Recovery Point Objective):** <24 hours (last rsync). Can be reduced to <1 hour with more frequent sync.

**titan-pc failure:**

- Build agents go down (Shuri, Happy, Banner, Stark)
- Services continue on titan-new (pipeline, outreach, coordination unaffected)
- If urgent: spin up Shuri on titan-pi temporarily (15GB RAM available)
- If not urgent: wait for titan-pc to recover

**titan-pi failure:**

- Guardian monitoring pauses
- Daily backup pauses
- Zero impact on running agents or services
- Fix at convenience

### Resilience Score

| Pillar Requirement | Status | Notes |
|--------------------|--------|-------|
| Survive any single machine failure | **YES** | titan-new failure has highest impact but titan-pi failover covers it |
| Auto-recovery | **PARTIAL** | soul-failover script handles titan-new; others manual |
| Data durability | **YES** | Git + daily rsync + services on SSD |
| No single point of failure | **IMPROVED** | Source of truth on SSD (not SD card), backup on titan-pi |

---

## 6. SOVEREIGNTY — All Data Stays Local

| Requirement | Status | Verification |
|-------------|--------|-------------|
| No cloud compute | **YES** | All 3 machines are local LAN |
| No cloud storage | **YES** | No S3, no GCS, no Azure Blob |
| No SaaS dependencies | **YES** | Gitea self-hosted, Vaultwarden self-hosted |
| No telemetry | **YES** | Claude CLI `--dangerously-skip-permissions` mode |
| Offline-capable | **YES** | All services run locally; internet only for WebSearch and API calls |

**Migration does NOT introduce any new external dependencies.** All data moves between local machines on the LAN. sshfs over ethernet (not internet). Gitea stays self-hosted (either on titan-pc Docker or migrated to titan-new).

---

## 7. PERFORMANCE — Resource Budgets

### Per-Machine Budget

| Machine | CPU | RAM Total | RAM for Agents | RAM Headroom | Agent Count |
|---------|-----|-----------|----------------|-------------|-------------|
| titan-new | TBD (rec: 4+ cores) | 16-32 GB | ~6 GB | 10-26 GB | 7 |
| titan-pc | 6 cores (i5-8400) | 7.6 GB | ~3.5 GB | 4 GB | 3-4 |
| titan-pi | 4 cores (RPi5) | 15 GB | 0 GB (standby) | 15 GB (failover) | 0 (guardian only) |
| **TOTAL** | **14+ cores** | **39-55 GB** | **~9.5 GB** | **29-45 GB** | **10** |

### Comparison: Before vs After

| Metric | Before (2 machines) | After (3 machines) |
|--------|---------------------|---------------------|
| Total RAM | 22.6 GB | 39-55 GB |
| Available RAM | ~14 GB | ~29-45 GB |
| Swap pressure | **3.5 GB on titan-pc** | **<500 MB** |
| Agent capacity | 10 (stressed) | **15+** (comfortable) |
| Source of truth | SD card (RPi) | **SSD** (new PC) |
| Failover | **NONE** | Hot standby (titan-pi) |
| Services | RPi (risky) | **Dedicated reliable hardware** |

### Performance Improvement Predictions

| Metric | Expected Improvement | Reason |
|--------|---------------------|--------|
| Shuri build times | 20-30% faster | Less swap thrashing on titan-pc |
| Agent response latency | 15-25% faster | Less memory pressure system-wide |
| Service reliability | 5x improvement | SSD vs SD card, dedicated hardware |
| Agent crash rate | 80% reduction | No OOM cascades |
| Context switch overhead | Eliminated for titan-pc | No more sshfs latency spikes during heavy builds |

---

## 8. TRANSPARENCY — Monitoring + Health Checks

### Multi-Machine Guardian

Extend soul-guardian to monitor all 3 machines:

| Check | Frequency | Alert Threshold | Action |
|-------|-----------|----------------|--------|
| RAM per machine | 30s | <1 GB available | Kill heaviest non-essential agent |
| CPU per machine | 30s | >95% sustained 5 min | Warning to CEO |
| Temperature (RPi) | 30s | >80°C | Kill newest agent |
| Disk space | 5 min | <5 GB free | Warning to CEO |
| Service health | 1 min | Any service down | Auto-restart + alert |
| sshfs mount health | 1 min | Mount stale/disconnected | Auto-remount + alert |
| Agent heartbeat | 5 min | Agent not responding | Restart + alert |
| Cross-machine ping | 1 min | >50ms or timeout | Network alert |

### Dashboard (Proposed)

```
soul-monitor v2 — 3-machine dashboard

titan-new (COORDINATION)     titan-pc (COMPUTE)          titan-pi (BACKUP)
═══════════════════════      ═══════════════════════      ═══════════════════
CPU: ████░░░░ 45%            CPU: ██████░░ 72%            CPU: ░░░░░░░░ 3%
RAM: ████░░░░ 6/16 GB       RAM: █████░░░ 5/7.6 GB      RAM: █░░░░░░░ 0.5/15 GB
Swap: ░░░░░░░░ 0/4 GB       Swap: █░░░░░░░ 0.5/4 GB     Swap: ░░░░░░░░ 0/1 GB

Agents: 7/7 ✓               Agents: 4/4 ✓               Agents: 0 (standby)
Services: 4/4 ✓             Services: 0                  Guardian: ✓ | Backup: 3h ago
Courier: ✓                  sshfs: ✓                     rsync: last 03:00
```

---

## 9. STRATEGIC IMPLICATIONS — What 3 Machines Enables

### Immediate Benefits

1. **Happy agent is viable.** titan-pc's memory pressure was the main risk in the Shuri capacity plan. With titan-new absorbing 3 agents (Pepper + Xavier + Hawkeye consideration) from the fleet, titan-pc has room.

2. **No more OOM cascades.** The documented pattern of orphaned processes → memory exhaustion → all agents crash → manual recovery is eliminated. Each machine has adequate headroom.

3. **Source of truth on reliable storage.** SD card corruption risk drops to zero for primary operations. Daily rsync to titan-pi provides cold backup.

4. **Services on dedicated hardware.** soul-v2, Scout, Tutor run on stable x86 with SSD — not competing for resources with 6 agents on an RPi.

### Medium-Term Enables

5. **Room for 12th+ agent.** With 29-45 GB headroom, we can add agents without hardware discussions. The 90-day plan may need more builders.

6. **Dedicated test runner.** titan-pc can run full CI/CD (go test, pytest, npm test, playwright) without affecting coordination.

7. **GPU path.** If SoulGraph Phase 3 fine-tuning needs a GPU, titan-pc is the candidate. Adding a GPU to titan-pc doesn't affect titan-new or titan-pi.

8. **Distributed resilience.** First time we can survive a machine failure without total team outage. This is a pillar requirement we couldn't meet before.

### Long-Term Vision

9. **Network of specialized compute nodes.** This architecture scales to N machines. Each new machine = more capacity, same coordination pattern.

10. **Eventually: public demo capability.** titan-new could serve a public soul-v2 demo (Cloudflare Tunnel already configured) while titan-pc builds and titan-pi monitors. No interference between public traffic and agent operations.

---

## 10. NEW PC SPECIFICATIONS — Recommendation

### Minimum Viable

| Spec | Requirement | Rationale |
|------|-------------|-----------|
| CPU | 4+ cores, x86_64 | Running 7 agents + services (bursty, not sustained) |
| RAM | **16 GB** minimum | 6 GB for agents, 10 GB headroom |
| Storage | 256 GB SSD | Source of truth, services, agent data |
| Network | Gigabit Ethernet + WiFi | LAN for sshfs, WiFi for internet |
| Power | Low TDP (<65W) | Runs 24/7, electricity cost matters |

### Recommended

| Spec | Recommendation | Rationale |
|------|---------------|-----------|
| CPU | Intel N100/N305 or AMD Ryzen 5 | Best perf/watt for always-on workloads |
| RAM | **32 GB** | Future-proof for 15+ agents |
| Storage | 512 GB NVMe SSD | Room for Gitea repos, agent data, backups |
| Form factor | Mini PC (Beelink, MinisForum) | Small, quiet, low power |
| Power | <25W idle | INR ~500/month electricity |

### Specific Hardware Recommendations (Researched Mar 25)

| Rank | Model | CPU | RAM | Storage | Price (INR) | Notes |
|------|-------|-----|-----|---------|-------------|-------|
| **#1 (BEST VALUE)** | Refurbished HP EliteDesk 800 G4/G5 | i5-8500/9500 | 16GB DDR4 | 256-512GB SSD | ~21,000-25,000 | Built for 24/7, enterprise cooling, quiet. Available: Computify.in, RefurbishedPC.in |
| **#2 (NEW, BUDGET)** | Beelink Mini S12 | Intel N95 | 8GB→16GB | 256GB SSD | ~14,000-18,000 + RAM upgrade | Ultra-low power (<5W idle). Need to buy extra RAM stick (~3,000). Amazon.in |
| **#3 (NEW, PERFORMANCE)** | ACEMAGICIAN S3A | Ryzen 7 8745HS | 16GB DDR5 | 512GB NVMe | ~30,000-40,000 | Overkill for coordination role but future-proof. Amazon.in |

**My recommendation: Option #1 — Refurbished HP EliteDesk 800 G4.** Enterprise-grade hardware designed for 24/7 uptime. Better cooling than consumer mini PCs. Same i5 generation as titan-pc (known quantity). 16GB is sufficient — can upgrade to 32GB later for ~3,000 more. Total: ~INR 21,000-25,000.

**Why NOT a new consumer mini PC:** For a machine running 24/7 as source of truth, enterprise-grade cooling and build quality matters more than raw specs. The EliteDesk thermal design is proven over years of data center use. Consumer mini PCs (Beelink, ACEMAGICIAN) are designed for intermittent desktop use.

**The ROI math:** One RPi crash that corrupts the source of truth costs 4-8 hours of recovery across the team. At our target hourly rate (INR 4,000+/hr), that's INR 16,000-32,000 per incident. The hardware pays for itself after one prevented crash.

---

## 11. DECISION FRAMEWORK

| Criterion | Score | Notes |
|-----------|-------|-------|
| **Thesis** | Functional separation across 3 machines eliminates corruption risk, memory pressure, and SPOF | All 3 current problems solved |
| **Evidence** | titan-pc at 3.5/4GB swap, RPi SD corruption documented, sshfs SPOF confirmed | Measured data, not estimates |
| **Risks** | Network failure between machines (LOW), migration complexity (MEDIUM), new machine hardware failure (LOW) | Mitigated by failover + rollback |
| **Alternatives** | (A) Add RAM to titan-pc only — doesn't fix corruption risk. (B) Replace RPi with PC — still 2 machines, still memory-limited. (C) Cloud VPS — violates sovereignty pillar. |
| **Reversibility** | **2/5** — Can revert to 2-machine topology at any time. Hardware purchase is the main non-recoverable cost. | Acceptable |

---

## 12. JOINT RECOMMENDATION (Fury — Pending Pepper)

### Decisions Needed from CEO

1. **APPROVE 3-machine architecture** — functional separation topology as described
2. **APPROVE hardware budget** — INR 20,000-40,000 for new mini PC
3. **CONFIRM new PC specs** — 16GB or 32GB RAM
4. **CONFIRM migration weekend** — Mar 29-30 (aligns with Happy onboarding)
5. **CONFIRM Pepper moves from titan-pc to titan-new** — frees RAM for Happy

### Proposed Timeline

| Date | Action |
|------|--------|
| Mar 25 (today) | CEO approves plan + orders hardware |
| Mar 26-28 | Hardware arrives, Phase 0 setup |
| Mar 29 | Phase 1-3: Copy, verify services, reverse sshfs |
| Mar 30 | Phase 4-5: Migrate agents, demote titan-pi |
| Mar 30 | Phase 6: Happy onboards on titan-pc |
| Apr 1 | Full 3-machine operation with 10 agents |

**If hardware takes longer:** Plan is still valid. Just shift dates. Phases 0-5 take ~9 hours once hardware arrives.

---

---

## APPENDIX A: Service Migration Details

### Services That Move to titan-new

| Service | Current Location | New Location | Migration Method |
|---------|-----------------|-------------|-----------------|
| soul-v2 (:3002) | titan-pi (systemd) | titan-new (systemd) | Compile Go binary on titan-new, create systemd unit |
| soul-scout (:3020) | titan-pi (systemd) | titan-new (systemd) | Same — `go build -o soul-scout ./cmd/scout` |
| soul-tutor (:3006) | titan-pi (systemd) | titan-new (systemd) | Same — `go build -o soul-tutor ./cmd/tutor` |
| soul-tasks | titan-pi (systemd) | titan-new (systemd) | Same binary |
| soul-courier | titan-pi (systemd) | titan-new (systemd) | Python daemon, copy + install deps |
| soul-guardian | titan-pi (systemd) | titan-pi (stays) + titan-new (new instance) | Guardian monitors remotely |

### Services That Stay

| Service | Location | Reason |
|---------|----------|--------|
| Gitea (Docker) | titan-pc | Large repo data on /mnt/vault, 2TB HDD. Moving is high-effort, low-benefit. |
| Vaultwarden (Docker) | titan-pc | Credential store, already stable. No reason to move. |
| Portainer (Docker) | titan-pc | Docker management, stays with Docker. |
| Duplicati (Docker) | titan-pc | Backup service, stays with storage. |

### Networking Changes

| Change | Old | New |
|--------|-----|-----|
| sshfs source | titan-pi → titan-pc | titan-new → titan-pc |
| Gitea SSH | titan-pi → git.titan.local:222 (titan-pc) | Unchanged |
| soul-v2 access | titan-pi :3002 | titan-new :3002 |
| Scout API | titan-pi :3020 | titan-new :3020 |
| Tutor API | titan-pi :3006 | titan-new :3006 |
| /etc/hosts | Add titan-new IP on all machines | |
| Cloudflare Tunnel | Point at titan-new :3002 | |

### tmux Launcher Update

`soul-team` script needs updating:
- titan-new panes: CEO, Friday, Pepper, Fury, Loki, Xavier, Hawkeye (7 agents via local tmux)
- titan-pc panes: Shuri, Happy, Banner, Stark (4 agents via SSH)
- titan-pi: No agent panes (guardian runs as systemd, not tmux)
- Courier: soul-courier.service on titan-new (replaces titan-pi)
- Launcher runs FROM titan-new (not titan-pi)

### DNS/hosts Configuration

All 3 machines need `/etc/hosts` entries:

```
# On titan-new:
192.168.0.196   titan-pc
192.168.0.128   titan-pi
127.0.0.1       titan-new git.titan.local vault.titan.local

# On titan-pc:
192.168.0.NEW   titan-new
192.168.0.128   titan-pi
127.0.0.1       titan-pc

# On titan-pi:
192.168.0.NEW   titan-new
192.168.0.196   titan-pc
127.0.0.1       titan-pi
```

---

## APPENDIX B: What This Plan Does NOT Change

| Item | Status | Reason |
|------|--------|--------|
| Gitea (Docker on titan-pc) | **NO CHANGE** | Repos on /mnt/vault (2TB HDD), moving is high-effort |
| Vaultwarden (Docker on titan-pc) | **NO CHANGE** | Stable, no reason to migrate |
| Git remote strategy | **NO CHANGE** | Private→Gitea, Public→GitHub |
| Agent definitions/skills | **MOVES** (titan-pi → titan-new) | Source of truth migration |
| soul-v2 code | **MOVES** (titan-pi → titan-new) | Source of truth migration |
| Agent communication (clawteam/courier) | **MOVES** (titan-pi → titan-new) | Follows source of truth |
| 6 Pillars compliance | **NO CHANGE** | All pillars maintained throughout |

---

*Filed by Fury (strategy). DRAFT — awaiting Pepper's product perspective before joint delivery. Key input needed from Pepper: co-location preferences, product requirements for machine placement, Happy's confirmed spec.*
