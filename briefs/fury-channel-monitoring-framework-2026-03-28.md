---
author: fury
type: strategy-brief
deliverable: S4
due: 2026-03-28
status: delivered
created: 2026-03-23
---

# Channel Monitoring Framework + KPI Template

**Purpose:** Strategic health monitoring across all 4 salary-target channels. Complements Pepper's operational daily/weekly tracking with leading indicators, ROI comparison, and escalation decision trees.

**Scope:** Mar 24 - Jun 22 (90-day salary targeting plan)

---

## Framework Architecture

```
                    ┌─────────────────────┐
                    │   STRATEGIC GOAL     │
                    │  Signed offer at     │
                    │  Rs 50L+ / $100K+    │
                    └────────┬────────────┘
                             │
          ┌──────────┬───────┴───────┬──────────┐
          ▼          ▼               ▼          ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ Channel 1│ │ Channel 2│ │ Channel 3│ │ Channel 4│
    │ SoulGraph│ │ Scout    │ │ Content/ │ │ Expert   │
    │ (Proof)  │ │ Pipeline │ │ LinkedIn │ │ Networks │
    │          │ │ (Volume) │ │ (Inbound)│ │ (Revenue)│
    └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

Each channel has:
- **Leading indicators** (predict future outcomes — act on these FIRST)
- **Lagging indicators** (confirm outcomes — measure success with these)
- **Green / Yellow / Red thresholds** (traffic light system)
- **Escalation response** (what to do when Yellow or Red)
- **Owner** + **Data source**

---

## Channel 1: SoulGraph (Public Proof / Credibility)

**Strategic role:** Closes the "show me your work" gap. Without public proof, every channel underperforms because comp negotiation has no leverage.

### KPIs

| Metric | Type | Green | Yellow | Red | Cadence | Owner | Source |
|--------|------|-------|--------|-----|---------|-------|--------|
| Phase completion vs schedule | Leading | On schedule | 1-2 days behind | >3 days behind or blocked | Daily | Shuri | Pepper roadmap |
| GitHub stars (cumulative) | Lagging | >5 (W4), >25 (W8), >100 (W13) | 50-80% of target | <50% of target | Weekly | Loki | GitHub API |
| Star velocity (stars/week) | Leading | Accelerating week-over-week | Flat | Decelerating | Weekly | Loki | GitHub API |
| README quality score | Leading | All sections complete, demo GIF, architecture diagram | Missing 1-2 sections | No demo, sparse docs | Per-release | Shuri | Manual review |
| Contributor interest (forks + issues from non-team) | Leading | Any external contribution | Views but no forks | Zero external engagement | Bi-weekly | Loki | GitHub Insights |
| Mentions in outreach responses | Lagging | Referenced by prospects | Not mentioned | Asked about and absent | Weekly | Hawkeye | Outreach tracking |

### Escalation Decision Tree

```
Phase >3 days behind?
├─ YES → Is blocker technical (infra/dependency)?
│   ├─ YES → Shuri gets dedicated sprint, all other Shuri work paused
│   └─ NO → Is blocker CEO decision?
│       ├─ YES → Pepper escalates with 24hr deadline
│       └─ NO → Fury investigates, scope reduction recommended
└─ NO → Continue. Monitor star velocity weekly.

GitHub stars <50% of phase target?
├─ YES → Is content promoting SoulGraph?
│   ├─ NO → Loki shifts next 2 posts to SoulGraph content
│   └─ YES → Distribution problem. Cross-post to Reddit, HN, Dev.to
└─ NO → Continue. Track velocity trend.
```

### Phase Targets

| Phase | Stars Target | Phase Target | Evidence |
|-------|-------------|-------------|----------|
| Phase 1 (Mar 24-Apr 22) | 5+ | Ship to GitHub, README polished | Baseline launch |
| Phase 2 (Apr 23-May 22) | 25+ | Growing organically | Content + HN exposure |
| Phase 3 (May 23-Jun 22) | 100+ | Active community signal | Sustained quality + promotion |

---

## Channel 2: Scout Pipeline (Application Volume)

**Strategic role:** Creates deal flow. Without volume, there's nothing to close — and no leverage for comp negotiation.

### KPIs

| Metric | Type | Green | Yellow | Red | Cadence | Owner | Source |
|--------|------|-------|--------|-----|---------|-------|--------|
| Active leads above comp floor | Leading | >20 | 10-20 | <10 | Weekly | Hawkeye | Scout DB |
| T1 leads with warm path | Leading | >3 with engagement | 1-2 engaged | 0 warm T1 | Weekly | Hawkeye | Scout DB |
| Outreach response rate | Lagging | >15% | 8-15% | <8% | Weekly | Hawkeye | Outreach log |
| Interviews scheduled (Phase 2+) | Lagging | 2+/week | 1/week | 0/week for 2 weeks | Weekly | Hawkeye | Calendar |
| Application-to-response ratio | Leading | >20% | 10-20% | <10% | Bi-weekly | Hawkeye | Outreach log |
| Pipeline age (avg days since last touch) | Leading | <7 days | 7-14 days | >14 days | Weekly | Hawkeye | Scout DB |
| Comp research coverage (T1/T2) | Leading | 100% T1, >80% T2 | 100% T1, <80% T2 | Any T1 without comp data | Weekly | Hawkeye | Scout DB |
| Platform evaluation progress | Leading | On schedule | 1 week behind | >2 weeks behind | Bi-weekly | Hawkeye | Manual |
| Networking conversations | Leading | 5+/week | 3-4/week | <3/week | Weekly | Hawkeye | Connect log |

### Escalation Decision Tree

```
Active leads above floor <10?
├─ YES → Is pipeline stale (>14 day avg)?
│   ├─ YES → Hawkeye runs emergency sweep + re-tier existing leads
│   └─ NO → Pipeline shrinking. Expand sources:
│       ├─ Add Wellfound/AngelList sweep
│       ├─ LinkedIn job alerts for target roles
│       └─ Hawkeye network activation (warm intros)
└─ NO → Monitor trend. Flag if declining 2 weeks straight.

0 interviews by Apr 18 (end of Phase 1)?
├─ YES → Emergency pivot:
│   ├─ Fury: Review comp floor — consider 40L/80K temporary reduction
│   ├─ Hawkeye: Expand to agency channels (Andela, Turing, Toptal)
│   ├─ Xavier: Shift prep to platform evaluation formats
│   └─ Loki: Pivot 50% content to hiring manager direct engagement
└─ NO → Continue. Track conversion funnel for bottleneck.

Outreach response rate <8%?
├─ YES → Diagnose:
│   ├─ Resume quality issue? → Hawkeye + CEO review
│   ├─ Targeting wrong companies? → Fury re-evaluates tier criteria
│   ├─ Subject line / cold message issue? → Loki reviews copy
│   └─ Wrong channel? → Test LinkedIn DM vs email vs referral
└─ NO → A/B test message variants for optimization.
```

### Phase Targets

| Phase | Leads Above Floor | Interviews/Week | Response Rate |
|-------|-------------------|-----------------|---------------|
| Phase 1 | 20+ | 0 (building) | >15% |
| Phase 2 | 25+ | 2+ | >20% |
| Phase 3 | 30+ | 2+ (at target comp) | >25% |

---

## Channel 3: Content / LinkedIn (Inbound Visibility)

**Strategic role:** Creates pull. Positions Rishav as the production AI architect so inbound opportunities appear and outreach gets warmer responses.

### KPIs

| Metric | Type | Green | Yellow | Red | Cadence | Owner | Source |
|--------|------|-------|--------|-----|---------|-------|--------|
| Posts published/week | Leading | 3+/week | 2/week | <2/week for 2 weeks | Weekly | Loki | LinkedIn analytics |
| Avg impressions/post | Lagging | >2K | 500-2K | <500 | Weekly | Loki | LinkedIn analytics |
| Engagement rate | Lagging | >5.2% (above 2026 avg) | 3-5.2% | <3% | Weekly | Loki | LinkedIn analytics |
| Comments per post | Leading | >5 | 2-4 | <2 | Per-post | Loki | LinkedIn analytics |
| Saves/bookmarks per post | Leading | >3 | 1-2 | 0 | Per-post | Loki | LinkedIn analytics |
| Follower growth (net/week) | Lagging | >50/week | 20-50/week | <20/week | Weekly | Loki | LinkedIn analytics |
| Inbound connection requests (relevant) | Lagging | >5/week | 2-4/week | <2/week | Weekly | Loki | LinkedIn inbox |
| Content-to-pipeline attribution | Lagging | 1+ lead sourced from content | Impressions but no leads | Zero attribution | Monthly | Fury | Cross-reference |
| SEO organic traffic (portfolio) | Lagging | Growing MoM | Flat | Declining or zero | Monthly | Loki | GSC / Umami |
| Anchor article performance | Lagging | Top 3 traffic source | Published but low traffic | Not published | Monthly | Loki | Blog analytics |

### Content Format Performance Benchmarks (2026 LinkedIn)

Use these to guide format selection:

| Format | Avg Engagement Rate | Best For |
|--------|-------------------|----------|
| Native documents/carousels | 6.60-7.00% | Deep technical content, architecture diagrams |
| Polls | 8.90% | Audience research, engagement bait |
| Video (native) | 5.10% | Demos, build-in-public |
| Image posts | 2-3% | Quick insights, quotes |
| Text-only | 3-4% | Stories, hot takes |

**Algorithm signals to optimize for:** Comments (15x weight of likes), dwell time, saves/bookmarks (35% more distribution), first-hour engagement.

### Escalation Decision Tree

```
<2 posts/week for 2 consecutive weeks?
├─ YES → Is content drafted but blocked?
│   ├─ YES → Is CEO gate the blocker?
│   │   ├─ YES → Pepper escalates. Create content buffer (3 pre-approved posts)
│   │   └─ NO → Loki shifts to simpler formats (text-only, polls)
│   └─ NO → Loki capacity issue:
│       ├─ Reduce to 2/week and focus on carousels (highest engagement)
│       └─ Create content templates to reduce production time
└─ NO → Check engagement trend.

Avg impressions <500 after 5+ posts?
├─ YES → Distribution problem:
│   ├─ Post timing wrong? → Test 8-10 AM IST (India), 7-9 AM EST (US)
│   ├─ Hashtag strategy? → Use 3-5 relevant hashtags, avoid >10
│   ├─ Network too small? → Accelerate connection requests to target audience
│   └─ Format pivot: shift to carousels/documents (7% avg engagement)
└─ NO → Optimize for comments. Ask questions. Use controversial angles.

Zero content-to-pipeline attribution by end of Phase 1?
├─ YES → Not necessarily a failure — attribution takes time.
│   ├─ Check: Are the right people seeing content? (job titles, companies)
│   ├─ Check: Is content technically deep enough? (should filter out juniors)
│   └─ Adjust: Include explicit CTA in 1 of every 3 posts
└─ NO → Double down on what's working. Fury reviews top-performing themes.
```

### Phase Targets

| Phase | Posts Published | Impressions/Post | Followers (net) |
|-------|---------------|-----------------|-----------------|
| Phase 1 | 5+ total (ramp up) | >500 | +100 |
| Phase 2 | 12+/month (3/week) | >2K | +300 |
| Phase 3 | 12+/month (3/week) | >3K | +500 |

---

## Channel 4: Expert Networks (Immediate Revenue + Rate Anchoring)

**Strategic role:** Generates cash while job search runs. More importantly, establishes a public rate anchor that strengthens all comp negotiations. A $400/hr expert rate makes $160K salary look reasonable.

### KPIs

| Metric | Type | Green | Yellow | Red | Cadence | Owner | Source |
|--------|------|-------|--------|-----|---------|-------|--------|
| Platform registrations completed | Leading | 3+ (GLG, Guidepoint, Techspert) | 1-2 | 0 by Apr 1 | Weekly | Hawkeye | Manual |
| Profile acceptance rate | Lagging | >50% platforms accepted | 1 accepted | 0 accepted by Apr 15 | Bi-weekly | Hawkeye | Platform status |
| Consultation requests received | Leading | 2+/month | 1/month | 0 for 6 weeks | Monthly | Hawkeye | Platform inbox |
| Calls completed | Lagging | 1+/week (Phase 2+) | 1-2/month | 0 by May 1 | Monthly | Fury/Hawkeye | Call log |
| Average hourly rate achieved | Lagging | >INR 15K/hr (>$200/hr) | INR 10-15K/hr | <INR 10K/hr | Per-call | Fury | Invoice log |
| Revenue (cumulative) | Lagging | Track | Track | N/A | Monthly | Fury | Invoice log |
| Profile views / match rate | Leading | Increasing | Flat | Declining | Monthly | Hawkeye | Platform analytics |
| Repeat client rate | Lagging | Any repeat | N/A (early) | N/A (early) | Quarterly | Fury | Call log |

### Escalation Decision Tree

```
0 registrations by Apr 1?
├─ YES → Is it a CEO action blocker? (resume, profile review)
│   ├─ YES → Pepper escalates as P0 — 24hr turnaround
│   └─ NO → Hawkeye executes immediately. GLG and Guidepoint first.
└─ NO → Continue. Track acceptance notifications.

0 accepted by Apr 15?
├─ YES → Profile quality issue:
│   ├─ Is profile positioned correctly? → Fury reviews positioning
│   ├─ Is domain too niche? → Broaden to "AI Architecture + LLM Evaluation"
│   └─ Try alternative networks: Techspert, Maven, NewtonX, Prosapient
└─ NO → Optimize profile for consultation requests. Add recent project data.

0 calls completed by May 1 (red flag trigger)?
├─ YES → Multi-pronged response:
│   ├─ Reapply to 3 additional networks (Maven, NewtonX, Dialectica)
│   ├─ Adjust positioning: broader "AI Strategy" vs narrow "Multi-Agent Systems"
│   ├─ Lower initial rate to INR 10K/hr to build track record
│   └─ Activate personal network referrals for expert network introductions
└─ NO → Rate optimization: test market-rate pricing vs premium.
```

### Phase Targets

| Phase | Registrations | Calls | Revenue |
|-------|-------------|-------|---------|
| Phase 1 | 3+ platforms registered | 0-1 (building) | $0-500 |
| Phase 2 | 4+ platforms, 2+ accepted | 2-3 calls/month | $1K-3K/month |
| Phase 3 | Active on 3+ platforms | 4+/month | $3K+/month |

---

## Cross-Channel Health Dashboard

### Weekly Health Check Template

Use this template every Friday alongside Pepper's operational KPI review:

```
# Channel Health — Week {N} ({date range})
# Produced by: Fury

## Traffic Light Summary
| Channel | Status | Trend | Key Signal |
|---------|--------|-------|------------|
| SoulGraph | 🟢/🟡/🔴 | ↑/→/↓ | {one line} |
| Scout Pipeline | 🟢/🟡/🔴 | ↑/→/↓ | {one line} |
| Content/LinkedIn | 🟢/🟡/🔴 | ↑/→/↓ | {one line} |
| Expert Networks | 🟢/🟡/🔴 | ↑/→/↓ | {one line} |

## Cross-Channel Signals
- Pipeline↔Content: Are outreach targets seeing our content? Y/N
- SoulGraph↔Pipeline: Is SoulGraph being referenced in applications? Y/N
- Content↔Expert: Is content generating expert network interest? Y/N
- Pipeline↔Prep: Is Xavier prepping for the right companies? Y/N

## Leading Indicator Flags
{Any Yellow/Red leading indicators with 1-sentence explanation}

## Strategic Recommendation
{One clear recommendation for the coming week}
```

### Monthly Strategic Review Template

Use at the end of each month:

```
# Monthly Strategy Review — {Month}
# Produced by: Fury

## Channel ROI Comparison
| Channel | Investment (time/hrs) | Output | ROI Signal |
|---------|----------------------|--------|------------|
| SoulGraph | {dev hrs} | {stars, references} | {verdict} |
| Scout Pipeline | {ops hrs} | {leads, interviews} | {verdict} |
| Content/LinkedIn | {creation hrs} | {impressions, followers} | {verdict} |
| Expert Networks | {profile + call hrs} | {revenue} | {verdict} |

## Resource Allocation Recommendation
{Should we shift time/effort between channels? Which channel is underperforming relative to investment?}

## Strategy Freshness Audit
| Strategy Doc | Last Updated | Fresh? | Action Needed |
|-------------|-------------|--------|---------------|
| Market baseline | {date} | Y/N | {action} |
| Competitive landscape | {date} | Y/N | {action} |
| Salary targets | {date} | Y/N | {action} |
| Content calendar | {date} | Y/N | {action} |

## Kill List
{Strategies, activities, or channels to stop investing in}

## Next Month Focus
{Top 3 priorities for the coming month}
```

---

## Integration with Existing Systems

### How This Framework Relates to Pepper's Monitoring

| Pepper (Operational) | Fury (Strategic) |
|---------------------|-----------------|
| Daily standups | Weekly/monthly health checks |
| Task completion tracking | Leading indicator monitoring |
| Agent accountability | Channel ROI comparison |
| Red flag trigger response | Escalation decision trees |
| Weekly KPI table | Cross-channel correlation |

**Rule:** Pepper monitors *execution* (are agents doing what they promised?). Fury monitors *strategy* (are the right things being done at all?).

### Cadence Calendar

| Day | Activity | Owner |
|-----|----------|-------|
| Monday | Review weekend activity, check leading indicators | Fury |
| Tuesday-Thursday | Monitor only if Yellow/Red flags | Fury |
| Friday | Weekly health check (populate template above) | Fury |
| Last Friday of month | Monthly strategic review | Fury |
| Apr 18 | Phase 1 strategy review | Fury |
| May 22 | Phase 2 strategy review | Fury |
| Jun 22 | 90-day retrospective | Fury |

---

## Appendix: Data Sources and Collection

| Data Point | Source | How to Collect | Automation Possible? |
|-----------|--------|---------------|---------------------|
| GitHub stars | GitHub API | `gh api repos/{owner}/soulgraph` | Yes — script weekly |
| Scout pipeline leads | Scout DB | Hawkeye weekly report | Yes — query via Scout CLI |
| LinkedIn metrics | LinkedIn Analytics | Manual (CEO access required) | No — manual export |
| Expert network status | Platform dashboards | Manual (CEO access) | No |
| Outreach response rate | Hawkeye tracking log | Hawkeye weekly report | Partial — manual tagging |
| Interview count | Calendar | Friday / Hawkeye report | No |
| Content publication count | LinkedIn + blog | Loki weekly report | Partial |

### Automation Recommendations (for Shuri, post-SoulGraph)

1. **GitHub star tracker** — Cron job: `gh api repos/rishav1305/soulgraph --jq '.stargazers_count'` weekly → append to metrics file
2. **Scout pipeline health** — Scout CLI query for lead count, avg age, tier distribution → auto-report
3. **Standup reminder** — Automated ping to agents missing standups by 10 AM IST

---

## Appendix: Confidence & Sources

**Market benchmarks confidence: MEDIUM-HIGH**
- LinkedIn engagement benchmarks: Multiple 2026 sources corroborate 5.2% avg engagement, carousel/document outperformance
- Expert network market: $3B+ market, Big 5 validated, but specific acceptance rates are proprietary
- GitHub star targets: Based on similar AI/ML open-source projects; star gaming is prevalent (4.5M suspected fake stars on GitHub in 2026)

**Sources:**
- LinkedIn benchmarks: Social Insider (socialinsider.io), ContentIn (contentin.io), Sprout Social
- Pipeline KPIs: Forecastio (forecastio.ai), Apollo, Close.com
- GitHub metrics: GitHub OSPO health metrics, ToolJet blog, DasRoot analysis
- Expert networks: Inex One market analysis, Silverlight Research, ExpertNetworks.net
- Salary targeting decision: ~/soul-roles/shared/decisions/2026-03-23-salary-targeting-plan.md
