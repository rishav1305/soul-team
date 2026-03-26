---
author: pepper
date: 2026-03-22
type: launch-readiness-audit
sprint_day: 2/14
target: Mar 25 content launch + Mar 27 portfolio/outreach
---

# Cross-Product Launch Readiness Audit

**Audit date:** 2026-03-22 12:30 IST (Sprint Day 2)
**Launch windows:** Content Mar 25 | Portfolio Mar 27 | Outreach Mar 27

---

## Mar 25 Content Launch: 7 Checkpoints

| # | Checkpoint | Status | Notes |
|---|-----------|--------|-------|
| 1 | Anchor article draft | ✅ READY | ~2,200 words. QA passed. |
| 2 | LinkedIn 3-post series | ✅ READY | Posts 1-3 final. First comments drafted. |
| 3 | LinkedIn carousel (10 slides) | ✅ READY | Slides designed. "Senior AI Architect" in footer. |
| 4 | X/Twitter posts + thread | ✅ READY | Hook tweet, 6-tweet thread, hot take. |
| 5 | Title consistency | ✅ ALIGNED | "Senior AI Architect" used throughout all content. No "AI Systems Engineer" found. CEO Decision #8 would only change if CEO chooses option A. |
| 6 | No open-source claims | ✅ VERIFIED | Zero instances of "open source" across all content files. |
| 7 | No Gartner name | ✅ VERIFIED | All references use "Fortune 500 analytics company". |

### Blocking Decisions (must resolve by end of Mar 23)

| Decision | Content Impact | If Not Resolved |
|----------|---------------|-----------------|
| **#4: "40% cost reduction"** | Lines 104 + 158 of anchor article state as fact. Must soften to "30-40% estimated" if no measured data. | Loki has contingency language. Safe default exists. |
| **#11: GOAT numbers** | Article opening + LinkedIn Post 1 use "5,000+ users, 88% resolution". Only CEO can verify accuracy + NDA safety. | Option A: use ranges ("thousands of users, 85%+ resolution"). |
| **#8: Title** | Content uses "Senior AI Architect" throughout. If CEO chooses "AI Systems Engineer", all files need find/replace. | Safe default: keep "Senior AI Architect" (already in content). |

### Risk Assessment: YELLOW

Content is READY but CEO review gate has not opened. Loki's review package (`loki-ceo-gate-p1-review-package.md`) is formatted for 15-minute review. The Sprint Decision Quick Card (`pepper-sprint-decisions-quick-card-2026-03-22.md`) makes batch approval trivial.

**If CEO reviews by end of Mar 23:** Content publishes on time Mar 25. Zero risk.
**If CEO reviews Mar 24:** Tight but feasible. No buffer for revisions.
**If CEO reviews Mar 25+:** Content launch slips. Series 1 cadence broken.

---

## Mar 27 Portfolio Launch: 5 Checkpoints

| # | Checkpoint | Status | Notes |
|---|-----------|--------|-------|
| 1 | Portfolio URL accessible | ✅ LIVE | http://localhost:3002/portfolio returns 200. |
| 2 | Soul v2 service stable | ✅ 20h+ uptime | systemd-managed, reboot-safe. |
| 3 | Shuri capacity for UI/UX work | ❌ BLOCKED | Awaiting CEO decisions #1, #2, #6 (combined: 6-13h freed). |
| 4 | SEO indexing | ⚠️ P2 | GSC token fix needed (Shuri P1 task). Long-term fix. |
| 5 | Soul Bench CTA | ⚠️ GATED | Current CTA says "Reach out for access". If CEO approves Decision #3 (public), Loki must update to direct GitHub link across 5 mentions. |

### Risk Assessment: RED

Shuri has NOT started portfolio UI/UX work. She's waiting on 3 CEO decisions (#1, #2, #6) that free her 6-13 hours. Without these decisions by Monday Mar 23, the Mar 27 hard deadline is at serious risk.

---

## Mar 27 Outreach Activation: 4 Checkpoints

| # | Checkpoint | Status | Notes |
|---|-----------|--------|-------|
| 1 | Pipeline cleaned and tiered | ✅ DONE | 38 active leads: 5 T1, 13 T2, 20 T3. |
| 2 | Outreach templates | ✅ DONE | 6 templates drafted by Hawkeye. |
| 3 | Platform research | ✅ DONE | GLG, Guidepoint, Toptal, Flexiple all researched. |
| 4 | CEO outreach decisions | ❌ BLOCKED | 6 Hawkeye decisions pending (#7: approach, gate reviews, title, Varahi, Digital.ai, dream companies). |

### Risk Assessment: YELLOW

All prep work is complete. Hawkeye delivered Week 1 ahead of schedule. The only blocker is CEO decisions — specifically #7 (hybrid vs warm approach) and #8 (title lock).

---

## Soul Bench Content References (Cross-Product Check)

Soul Bench is referenced in 5 content pieces. The CTA strategy depends on Decision #3:

| Reference | Current CTA | If Public (Decision #3 = A) |
|-----------|-------------|---------------------------|
| Anchor article (2 mentions) | "Reach out for access" | Direct GitHub link |
| LinkedIn Post 2 | "Soul Bench automates steps 3-5" | Add link in comments |
| LinkedIn Carousel Slide 9 | "Soul Bench — the tool I built" | "Try it: github.com/..." |
| LinkedIn Post (carousel CTA) | "Link in comments" | Actual link |

**Action for Loki if #3 = A:** Find/replace CTA across 4 files. ~15 min effort.

---

## Summary

| Launch | Readiness | Blockers |
|--------|-----------|----------|
| Content (Mar 25) | 🟡 YELLOW | CEO review + decisions #4, #8, #11 |
| Portfolio (Mar 27) | 🔴 RED | CEO decisions #1, #2, #6 → Shuri capacity |
| Outreach (Mar 27) | 🟡 YELLOW | CEO decisions #7, #8 |

**Single point of failure across all 3 launches: CEO decision throughput.**

The Sprint Decision Quick Card makes it possible to resolve all 11 decisions in a single 5-minute batch.

---

*Pepper | CPO | Session 6 | Sprint Day 2*
