# Product Enhancement Spec: Scout Comp-Awareness Gate

**From:** Pepper (CPO)
**To:** Shuri (build), Hawkeye (input)
**Priority:** P2 (post-Mar 28 launch)
**Date:** March 25, 2026

---

## Problem Statement

Scout's profiledb match score weights technical keyword overlap but **completely ignores company compensation bands**. This creates misleading priority rankings:

| Lead | Match Score | Actual Comp Range | 50L Floor |
|------|------------|-------------------|-----------|
| Wissen #33 | 97 | 25-40L | BELOW |
| Glean #53 | 90 | 95-168L | MASSIVE PASS |
| Energy Exemplar #5 | 92 | 15-27L | BELOW |

A lead scoring 97 that can't meet the salary floor is worse than a lead scoring 90 that pays 3x the floor. Hawkeye currently does manual comp checks per lead — this should be surfaced as a pipeline field.

## Evidence

From Hawkeye's T1 comp research (Mar 25):
- Only **5/11 T1 leads** have confident comp above 50L floor
- 4 are BORDERLINE (30-50L range)
- 2 are UNKNOWN (insufficient data)
- The pattern: IT services firms posting "AI/ML + LangChain + RAG" score 90+ on keyword match but pay 25-40L. Well-funded Silicon Valley companies posting generic "Software Engineer" score 75-90 but pay 95-168L.

## Proposed Solution

### Phase 1: Manual Gate (Immediate — Hawkeye process change)
Add `comp_floor_status` as a free-text field during qualification:
- `PASS` — confirmed above 50L (with source)
- `BORDERLINE` — 30-50L range or thin data
- `BELOW` — confirmed under 50L
- `UNKNOWN` — no data yet
- `N/A` — US/remote role (different floor applies)

**Hawkeye populates during gate review.** This requires no code changes — just a process convention.

### Phase 2: ProfileDB Field (Shuri — post-Mar 28)
Add `comp_floor_pass` boolean + `comp_range_estimate` text fields to profiledb schema:
```
comp_floor_pass: boolean (null = unassessed)
comp_range_estimate: string (e.g., "95-168L" or "25-40L")
comp_source: string (e.g., "levels.fyi", "glassdoor", "6figr")
comp_assessed_date: date
```

### Phase 3: Adjusted Priority Score (Future)
`adjusted_priority = match_score * comp_multiplier`
- PASS: 1.0x
- BORDERLINE: 0.7x
- BELOW: 0.3x
- UNKNOWN: 0.5x

This keeps high-match/low-comp leads visible but de-prioritizes them in sorted views.

## Impact

- **Outreach efficiency:** Stop spending premium outreach effort on leads that can't meet comp floor
- **Pipeline clarity:** Tier distribution becomes meaningful (T1 = high match + comp pass, not just high match)
- **Negotiation prep:** Hawkeye knows upfront which leads need floor stated early vs. leads where comp is a non-issue

## Acceptance Criteria

Phase 1:
- [ ] Hawkeye adds comp status to all T1 leads by Mar 28
- [ ] Gate review template includes comp check as formal step

Phase 2:
- [ ] ProfileDB schema updated with 4 new fields
- [ ] Scout API returns comp fields in lead detail
- [ ] Hawkeye can update comp fields via API or CLI

---

*Filed by Pepper. Source: Hawkeye T1 comp research brief, Banner cross-product analysis.*
