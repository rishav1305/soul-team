# Cross-Product Integration Spec: Xavier ↔ Scout

**Author:** Pepper (CPO)
**Date:** 2026-03-21
**Priority:** P3 (backlog — after foundation restore sprint)
**Status:** Proposal — needs Shuri feasibility review

---

## Problem

Xavier operates Tutor (interview prep) and Hawkeye operates Scout (pipeline CRM) independently. Neither product knows about the other. This means:

1. Xavier can't automatically prep Rishav for interviews at companies in the pipeline
2. Xavier doesn't know which companies are Tier 1 (highest prep priority)
3. Xavier can't use Scout's rich data (tech stack, hiring manager, salary range) to customize prep
4. Hawkeye can't see Tutor readiness to time outreach (don't approach until ready)

## Opportunity

**Pipeline-Aware Interview Prep** — the highest-value cross-product integration in the ecosystem.

When a lead advances to "qualified" or "outreach" stage in Scout, Xavier should automatically:
1. Look up the company's tech stack, interview style, and role requirements
2. Create a company-specific study plan (prioritize topics that match their stack)
3. Generate practice questions tailored to the role description
4. Track readiness per company (not just overall)

This is a unique value prop. No interview prep tool does this because no one has a pipeline CRM feeding into their prep system.

## Data Available from Scout API

Scout leads at `http://localhost:3020/api/leads` expose:

| Field | Interview Prep Value |
|-------|---------------------|
| `jobTitle` | Maps to interview type (SDE vs AI Engineer vs Architect) |
| `description` | Full JD — extract required skills, experience, tech stack |
| `company` | Company name for culture/process research |
| `companyDomain` | Lookup company interview patterns (Glassdoor, Blind) |
| `companyIndustry` | Industry-specific domain questions |
| `companyEmployeeCount` | Startup (<100) vs enterprise (>5000) interview style |
| `companyFundingStage` | Startup maturity → interview depth expectations |
| `technologySlugs` | Direct map to Tutor topics (Python, LLM, Kubernetes, etc.) |
| `hiringManagerLinkedIn` | Research HM background for behavioral prep |
| `seniority` | Calibrate difficulty (mid → coding heavy, senior → design heavy) |
| `minAnnualSalaryUsd` / `maxAnnualSalaryUsd` | Negotiation prep |
| `tier` | Prep priority (Tier 1 first) |
| `stage` | Trigger (prep when qualified → outreach) |
| `matchScore` | Confidence level → how much prep to invest |

## Proposed Integration (3 Phases)

### Phase 1: Read-Only Data Pull (Low Effort)
- Xavier queries Scout API to get qualified + outreach leads
- Generates company-specific prep recommendations as a brief
- Manual trigger (Xavier skill: "prep for pipeline leads")
- **No code changes to Scout needed**

### Phase 2: Automated Prep Triggers (Medium Effort)
- When a lead moves to "outreach" in Scout, trigger Xavier to create a study plan
- Implement via file-based events or a webhook
- Xavier auto-creates a company-specific topic set in Tutor DB

### Phase 3: Readiness-Gated Outreach (High Effort)
- Hawkeye checks Tutor readiness score before sending outreach
- If readiness < threshold for that company's required topics → delay outreach
- Creates a feedback loop: prep → ready → outreach → interview → outcome → refine prep

## Value Assessment

| Metric | Without Integration | With Integration |
|--------|-------------------|-----------------|
| Prep specificity | Generic topics | Company + role specific |
| Prep timing | Manual, often late | Triggered by pipeline stage |
| Topic coverage | Random | Mapped to JD tech stack |
| Outreach quality | Portfolio only | Portfolio + demonstrated readiness |
| Time to prep | 2-3 hours manual research | Automated research → focused drill |

## Current State (Xavier Already Started)

Xavier has already manually researched top pipeline companies:
- Wissen Technology (Java/Spring, OOP, concurrency, LRU cache)
- Ripik.AI (CV, anomaly detection, Python, ML systems)
- Digital.ai (standard SWE process assumed)

This manual process validates the integration value. Phase 1 would automate what Xavier is already doing by hand.

## Implementation Request

**For Shuri:**
1. Feasibility check — can Xavier's Go binary call Scout's REST API directly?
2. What's the simplest way to pass Scout lead data to Tutor for company-specific topics?
3. Estimated effort for Phase 1?

**For Xavier:**
1. Define the mapping: `technologySlugs` → Tutor topic IDs
2. Define how company-specific prep differs from generic prep
3. What data from the JD (`description` field) is most useful?

---

## Decision for CEO

This integration doesn't block the current sprint. It's a Q2 backlog item. But the data alignment is already there — Scout has exactly the fields Xavier needs. Phase 1 (read-only data pull via skill) could be done in a few hours.

**Recommendation:** Approve Phase 1 as a stretch goal for the current sprint (if all P0-P2 items clear by Mar 28).

— Pepper (CPO)
