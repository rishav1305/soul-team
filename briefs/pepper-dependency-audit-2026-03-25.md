# Dependency Acceleration Audit — Stale Timelines

**From:** Pepper (CPO)
**For:** CEO
**Date:** March 25, 2026 (Evening)
**Trigger:** CEO correction — preconditions clearing without dependent work being pulled forward

---

## FOUND: 9 Stale Items (Precondition Cleared, Dependent Work Not Accelerated)

### 1. FINE-TUNING SHIPPED → Outreach Risk Flag STALE

**Precondition cleared:** SoulGraph agent fine-tuning shipped today (137 tests, 83% coverage).

**Stale text (registry + roadmap):** "Fine-tuning claims — 3 outreach templates still reference Phase 3 Wave 3 (not built). CEO decision pending."

**Reality:** Fine-tuning IS built. The 3 outreach templates referencing it are now BACKED BY CODE. No CEO decision needed — the code IS the decision.

**Fix:** Remove risk flag. Notify Hawkeye + Loki: fine-tuning references in outreach templates are now legitimate. No rewording needed.

**Impact:** CEO was carrying a decision item ("fine-tuning decision, 5 min") that no longer exists. Removes 1 item from CEO action queue.

---

### 2. ALL 5 LEADS AT APPLY → Roadmap Still Shows "EXECUTING"

**Precondition cleared:** Hawkeye confirmed all 5 leads (DB, JAGGAER, Glean, OpenAI, Movius) at APPLY stage with cover letters generated.

**Stale text (roadmap):** "Advance 5 stuck leads | Hawkeye | 🟡 EXECUTING | Mar 26-27"

**Reality:** ALL 5 are done. DB+JAGGAER submissions are tomorrow AM (application artifacts ready, not execution lag).

**Fix:** Update to ✅ DONE. The Mar 26 AM item is "submit applications" (CEO-independent — Hawkeye handles).

---

### 3. COMP GATE FULLY OPERATIONAL → Bottleneck Text Stale

**Precondition cleared:** Stark completed all 5 UNKNOWN comp research. Pipeline: 12 PASS (57%), 5 BORDERLINE (24%), 4 FAIL (19%). Zero UNKNOWNs. T1 now 14.

**Stale text (registry):** "T1 comp clearance (Hawkeye finding) — Only 5/11 T1 leads have confident comp above 50L floor. 6 are borderline or unknown."

**Reality:** 12/21 confirmed PASS. Zero unknowns. HuggingFace promoted to T1. Varahi closed.

**Fix:** Update bottleneck to ✅ RESOLVED or update numbers.

---

### 4. SOUL-BENCH LIVE ON GITHUB → Pinning Can Happen NOW

**Precondition cleared:** Happy pushed soul-bench to GitHub today (commit b887335). Repo is live with content.

**Stale assumption:** GitHub pinning strategy says soul-bench is Pin #2, but earlier today the repo was EMPTY. Now it's live.

**Dependent work:** CEO can pin 6 repos NOW. Previously blocked by soul-bench empty + soul README missing. Both are now shipped.

**Fix:** Notify CEO: GitHub pinning preconditions met. All 6 Pin repos are ready (soulgraph already live, soul-bench now live, soul has README, soul-team clean, CCQ clean, portfolio_app clean). Can execute the full pinning plan whenever CEO has 2 minutes.

---

### 5. SOUL README COMMITTED → .gitignore Sanitization Can Start

**Precondition cleared:** Happy committed soul README (57d3472, pushed to Gitea).

**Dependent work:** The GitHub strategy requires .gitignore sanitization BEFORE soul goes public on GitHub. README was the first prerequisite. Now sanitization can proceed.

**Fix:** Verify with Shuri: is .gitignore sanitization part of Phase 2 merge, or a separate task? If separate, it should start now.

---

### 6. IBM NON-COMPETE CLEARED → Contract Entity Registration Unblocked

**Precondition cleared:** CEO confirmed no non-compete clause (Mar 25).

**Stale text (bottleneck #4):** "Contract strategy — Joint brief FINAL. 5 CEO decisions. 2 hard blockers (IBM non-compete, business entity)."

**Reality:** Only 1 hard blocker remains (business entity). And per Soul Labs conference: entity registration is Phase 1 (Mar 31+), domain/TM are Phase 0 (now). But the blocker being cleared means Phase 0 defensive actions are unblocked.

**Dependent work:** CEO can proceed with Phase 0 Soul Labs actions (domain registration, GitHub org, TM application) without waiting. Also: Fury flagged that entity formation specifically needed IBM non-compete clearance — that gate is now open.

**Fix:** Update bottleneck to "1 hard blocker (business entity only)." Notify CEO: Phase 0 actions are fully unblocked.

---

### 7. GNOME DISABLED → Chat Migration Evaluation Unblocked

**Precondition cleared:** GNOME disabled, titan-pi stable (load 3.82, 9GB free).

**Stale text (registry):** "Chat migration: DEFERRED. Cannot migrate to titan-pi while GNOME eats 53% CPU."

**Reality:** GNOME is gone. titan-pi has headroom. If CEO decides INVEST at Mar 28 review, Chat migration to titan-pi can START immediately — no infrastructure prerequisite.

**Fix:** Update to "Chat migration: PRECONDITION MET. Headroom available. Awaiting Mar 28 CEO decision (Invest/Hibernate/Sunset)." Not pulling forward (decision not made), but acknowledging the gate is clear.

---

### 8. CEO ACTION QUEUE → 3 Items Resolved, Still Listed

**Precondition cleared:** Multiple items resolved today.

**Stale text (bottleneck #2):** Lists "GNOME disable (2 min)" and "fine-tuning decision (5 min)" in CEO action queue — both are DONE.

**Reality:** CEO action queue should be:
- LinkedIn publish (3 posts, 15 min) — STILL PENDING
- Email 2+3 sign-off (10 min) — STILL PENDING (Mar 27 deadline)
- Platform registrations (30 min) — STILL PENDING
- HF #141 submit (15 min) — STILL PENDING (now T1, higher priority)
- T3 closes — PARTIALLY DONE (Varahi closed, Geeky Tech closed)
- Ask Effi tier — STILL PENDING
- ~~GNOME disable~~ — DONE
- ~~Fine-tuning decision~~ — RESOLVED (code shipped)

**Fix:** Update queue. New estimate: ~55 min (was 65 min). 2 items removed.

---

### 9. HUGGING FACE #141 T1 PROMOTION → Application Priority Elevated

**Precondition cleared:** HuggingFace promoted to T1 today (comp 84-197L AUTO-PASS).

**Stale text (registry):** "HF #141 application: CEO submit 🟡 Cover letter READY"

**Reality:** HF is now T1 (was T2). Application priority should be elevated. Cover letter exists. This should be in the Week 2 outreach queue alongside Stripe and DeepMind, not sitting as a backlog item.

**Fix:** Update milestone to reflect T1 status. Queue for Week 2 outreach batch.

---

## Actions Taken

| # | Stale Item | Fix | Status |
|---|-----------|-----|--------|
| 1 | Fine-tuning risk flag | Remove from registry + roadmap. Notify Hawkeye/Loki. | FIXING NOW |
| 2 | 5 leads EXECUTING | Update to ✅ DONE | FIXING NOW |
| 3 | Comp gate bottleneck | Update numbers | FIXING NOW |
| 4 | GitHub pinning | Notify CEO: all 6 repos ready to pin | SENDING NOW |
| 5 | .gitignore sanitization | Check with Shuri if part of Phase 2 | SENT |
| 6 | Contract blocker count | Update to 1 blocker | FIXING NOW |
| 7 | Chat migration gate | Update text to "precondition met" | FIXING NOW |
| 8 | CEO action queue | Remove 2 resolved items | FIXING NOW |
| 9 | HF #141 priority | Elevate to Week 2 outreach | FIXING NOW |

---

## The Pattern I Missed

These 9 items share a common failure mode: **I updated the PRIMARY record (the decision brief, the inbox message) but not the SECONDARY records (registry, roadmap, bottleneck list).** When a precondition clears, the fix isn't just "acknowledge it" — it's "trace every downstream reference and update them all."

**New process (added to operating protocol):**
1. Precondition clears → identify ALL downstream dependencies
2. Update the primary record (decision/brief)
3. Update the registry (product health, bottleneck list)
4. Update the roadmap (status, dates)
5. Notify the dependent task owner: "Your blocker cleared. Start now."
6. Notify CEO: "X cleared → Y pulled forward to Z"

This is a 6-step checklist, not a 2-step acknowledge-and-move-on.

---

*Dependency acceleration audit by Pepper (CPO) | March 25, 2026*
