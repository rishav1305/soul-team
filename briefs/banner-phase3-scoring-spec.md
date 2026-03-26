# Phase 3: Time-Aware Scoring Specification
**Author:** Banner (Data Science) | **Date:** 2026-03-24 | **Status:** SPEC — awaiting Pepper review
**Depends on:** Phase 2 collector (running), 72h baseline analysis (complete)

---

## Problem Statement

The current scoring system produces misleading health scores for products with natural usage cycles:

1. **Tutor scores 2.8 during idle hours (00:00-15:00 IST)** despite 100% service uptime. The low score is driven by zero `drills_today`, zero `readiness_pct`, and low `streak` during sleeping hours. This is expected behavior, not a health problem.

2. **Scout scores a constant 4.5** because it's in pre-outreach phase (outreach starts Mar 27). Zero `conversion_rate` and zero `artifacts_today` are by design, not failures.

3. **Chat's business_score is constant at 5.75** because `tool_call_success_rate` is hardcoded at 10/10 and `sessions_today` is always 0 (sessions aren't being tracked by the JSONL event stream).

These structural issues make the dashboard misleading and generate unnecessary cognitive load for Pepper (CPO) reviewing health.

---

## Design Overview

Three changes, implemented in order:

| # | Change | Purpose | Effort |
|---|--------|---------|--------|
| 3.1 | Time-aware scoring windows | Eliminate Tutor idle-hour penalty | 3 hrs |
| 3.2 | Pipeline-phase weighting | Eliminate Scout pre-outreach penalty | 1.5 hrs |
| 3.3 | Percentile calibration | Replace guessed thresholds with data-driven ones | 2 hrs |

**Not in scope (deferred):**
- Chat session tracking fix (requires Shuri code change in soul-v2 server)
- Phase 5: Trading product class (Stark)
- Dashboard serving via Soul v2 tab

---

## 3.1 Time-Aware Scoring Windows

### Concept

Define "time profiles" per product. Each profile has a set of time windows with adjusted scoring weights. During idle windows, usage and business metrics are scored more leniently.

### Data Evidence (72h baseline)

**Tutor hourly pattern (Mar 23):**

| Time Block | Hours | Avg Health | Business Score | Pattern |
|------------|-------|------------|----------------|---------|
| Idle | 00:00-15:59 IST | 2.8 | 1.19 | Flat, zero variance |
| Transition | 16:00 IST | 3.95 | 3.43 | Sharp step up |
| Active | 17:00-23:59 IST | 5.1 | 5.67 | Flat, zero variance |

The transition is exactly at 16:00 IST. No gradual ramp. This suggests a binary active/idle model is appropriate (no need for complex time series smoothing).

### Config Changes

Add `time_profiles` section to `config.yaml`:

```yaml
products:
  tutor:
    # ... existing fields ...
    time_profile:
      timezone: "Asia/Kolkata"
      windows:
        - name: "idle"
          hours: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
          weights:
            service: 0.70    # was 0.25 — service health is what matters when idle
            usage: 0.05      # was 0.25 — zero usage is expected
            business: 0.25   # was 0.50 — weight down heavily
          business_floor:     # minimum scores for idle-expected metrics
            drills_today: 5.0     # neutral (don't penalize 0 drills at 3am)
            readiness_pct: 5.0    # neutral
            due_reviews_backlog: null  # still score normally (backlog exists regardless)
        - name: "active"
          hours: [16, 17, 18, 19, 20, 21, 22, 23]
          weights:
            service: 0.25    # unchanged
            usage: 0.25      # unchanged
            business: 0.50   # unchanged
          business_floor: null  # no floor — score everything normally

  chat:
    # Chat doesn't need time windows yet — constant 5.75 is a tracking issue, not a time issue
    time_profile: null

  scout:
    # Scout uses pipeline-phase weighting instead (see 3.2)
    time_profile: null
```

### Scoring Logic Change

In `collector.py`, during `compute_health_score()`:

```python
def compute_health_score(product, config, metrics, timestamp):
    profile = config.get('time_profile')

    if profile:
        tz = pytz.timezone(profile['timezone'])
        local_hour = timestamp.astimezone(tz).hour

        # Find matching window
        window = None
        for w in profile['windows']:
            if local_hour in w['hours']:
                window = w
                break

        if window:
            # Override weights
            weights = window['weights']

            # Apply business_floor for idle-expected metrics
            if window.get('business_floor'):
                for metric, floor in window['business_floor'].items():
                    if floor is not None and metrics.get(metric, 0) < floor:
                        metrics[metric] = floor
    else:
        weights = config['weights']  # use default

    # ... rest of scoring unchanged
```

### Expected Impact

| Product | Current Idle Score | Projected Idle Score | Change |
|---------|-------------------|---------------------|--------|
| Tutor | 2.8 | ~6.5 | +3.7 |
| Chat | 4.67 (no change) | 4.67 | 0 |
| Scout | 4.5 (no change) | 4.5 | 0 |

Calculation for Tutor idle projected:
- service: 9.0 * 0.70 = 6.30
- usage: 0.0 * 0.05 = 0.00
- business: (floor-adjusted ~5.0) * 0.25 = 1.25
- Total: ~7.55... let me recalculate properly.

Actually: health_score = (service * w_svc) + (usage * w_use) + (business * w_biz) where each component is already a 0-10 score.

- service_score = 9.0 (consistent)
- usage_score = 0.0 (idle)
- business_score with floors: readiness_pct=5.0 (floor), streak=5.0 (actual), due_reviews_backlog=0.0 (still penalized), drills_today=5.0 (floor)
  - business = 5.0*0.30 + 5.0*0.20 + 0.0*0.25 + 5.0*0.25 = 1.50 + 1.00 + 0.00 + 1.25 = 3.75

health = 9.0*0.70 + 0.0*0.05 + 3.75*0.25 = 6.30 + 0 + 0.94 = **7.24**

| Product | Current Idle Score | Projected Idle Score | Change |
|---------|-------------------|---------------------|--------|
| Tutor | 2.8 | **~7.2** | +4.4 |

This feels more honest — Tutor IS healthy at 3am. Service is up, backlog exists but drills are appropriately zero.

### Edge Cases

1. **Timezone changes / DST:** India doesn't observe DST. For future products in DST zones, use `pytz` for correct local time.
2. **Stale window config:** If user changes active hours, the transition appears as a score jump in historical data. Add a `profile_version` field to track.
3. **Cross-midnight windows:** Use hour list (not ranges) so windows can span midnight if needed.
4. **Missing window match:** If current hour doesn't match any window, fall back to default weights.

---

## 3.2 Pipeline-Phase Weighting

### Concept

Products in known operational phases get adjusted scoring that doesn't penalize expected zero-state metrics.

### Design

Add `pipeline_phase` to product config:

```yaml
products:
  scout:
    pipeline_phase:
      current: "pre-outreach"
      since: "2026-03-20"
      expected_transition: "2026-03-27"
      phases:
        bootstrap:
          # First 48h after deployment
          neutral_metrics: ["conversion_rate", "stale_leads_ratio", "followups_overdue", "artifacts_per_day"]
          neutral_score: 5.0
          weights: {service: 0.70, usage: 0.20, business: 0.10}
        pre-outreach:
          # Outreach paused by CEO directive
          neutral_metrics: ["conversion_rate", "artifacts_per_day"]
          neutral_score: 5.0
          weights: {service: 0.40, usage: 0.20, business: 0.40}
        active:
          # Full operation
          neutral_metrics: []
          neutral_score: null
          weights: {service: 0.25, usage: 0.25, business: 0.50}
        mature:
          # 30+ days of active operation
          neutral_metrics: []
          neutral_score: null
          weights: {service: 0.20, usage: 0.25, business: 0.55}
```

### Scoring Logic

```python
def apply_phase_adjustments(product, config, business_metrics):
    phase_config = config.get('pipeline_phase')
    if not phase_config:
        return config['weights'], business_metrics

    current_phase = phase_config['current']
    phase_def = phase_config['phases'][current_phase]

    # Override weights
    weights = phase_def['weights']

    # Apply neutral scores for expected-zero metrics
    for metric in phase_def.get('neutral_metrics', []):
        if business_metrics.get(metric, 0) == 0:
            business_metrics[metric] = phase_def['neutral_score']

    return weights, business_metrics
```

### Expected Impact

**Scout in pre-outreach phase:**

Current: service=9.0*0.25 + usage=0.0*0.25 + business=4.5*0.50 = 2.25 + 0 + 2.25 = **4.5**

Phase-adjusted:
- business with neutral floors: conversion_rate=5.0, stale_leads_ratio=10.0 (actual), followups_overdue=10.0 (actual), artifacts=5.0
  - business = 5.0*0.35 + 10.0*0.25 + 10.0*0.20 + 5.0*0.20 = 1.75 + 2.50 + 2.00 + 1.00 = 7.25
- health = 9.0*0.40 + 0.0*0.20 + 7.25*0.40 = 3.60 + 0 + 2.90 = **6.5**

| Phase | Current Score | Projected Score | Change |
|-------|--------------|-----------------|--------|
| pre-outreach | 4.5 | **~6.5** | +2.0 |

### Hawkeye Integration

When Hawkeye activates outreach (expected Mar 27):
1. Update `config.yaml`: change `current: "pre-outreach"` → `current: "active"`
2. Collector picks up new phase on next run (no restart needed)
3. Scores will naturally adjust as real business metrics start populating

**Question for Pepper:** Should phase transitions be manual (config edit) or should the collector auto-detect? Auto-detection criteria could be: `artifacts_per_day > 0 for 3 consecutive collections → transition to active`. Manual is safer initially.

---

## 3.3 Percentile Calibration

### Concept

Replace hardcoded thresholds with data-driven percentile boundaries. After accumulating 237+ full collections per product, compute percentiles for each metric and map them to score bands.

### Approach

```python
def calibrate_thresholds(db_path, product, metric, window=None):
    """Compute P10/P25/P50/P75/P90 for a metric, optionally within a time window."""

    query = """
    SELECT {metric} FROM health_scores
    WHERE product = ?
    AND collection_type = 'full'
    """
    if window:
        query += f" AND strftime('%H', timestamp, 'localtime') IN ({window})"

    values = [row[0] for row in cursor.execute(query, (product,))]

    return {
        'p10': np.percentile(values, 10),
        'p25': np.percentile(values, 25),
        'p50': np.percentile(values, 50),
        'p75': np.percentile(values, 75),
        'p90': np.percentile(values, 90),
    }
```

### Percentile-to-Score Mapping

| Percentile Range | Health Score Band | Label |
|-----------------|-------------------|-------|
| >= P90 | 9-10 | Excellent |
| P75 - P90 | 7-8 | Healthy |
| P25 - P75 | 5-6 | Normal |
| P10 - P25 | 3-4 | Below normal |
| < P10 | 1-2 | Critical |

### When to Calibrate

- **Initial:** Run once after 3.1 + 3.2 are deployed and 48h of new data accumulates under the new scoring regime.
- **Re-calibrate:** Monthly, or on-demand via `python3 collector.py --calibrate`
- **Store:** Write calibrated thresholds to `config.yaml` under `calibration:` section with `calibrated_at` timestamp.

### Important: Calibrate AFTER 3.1 and 3.2

Percentiles computed on pre-3.1 data would encode the idle-hour penalty. We must first deploy time-aware scoring, collect 48+ hours of corrected scores, THEN calibrate.

---

## Implementation Plan

| Step | Description | Effort | Dependency | Risk |
|------|-------------|--------|------------|------|
| **3.1a** | Add `time_profile` config schema | 30 min | None | Low |
| **3.1b** | Implement window detection + weight override in collector | 1.5 hrs | 3.1a | Medium — test with dry-run |
| **3.1c** | Add business_floor logic | 1 hr | 3.1b | Low |
| **3.2a** | Add `pipeline_phase` config schema | 30 min | None | Low |
| **3.2b** | Implement phase-aware scoring | 1 hr | 3.2a | Low |
| **3.3a** | Percentile computation script | 1 hr | 48h post-3.1+3.2 | Low |
| **3.3b** | Auto-calibration flag | 30 min | 3.3a | Low |
| **Test** | Dry-run with historical data | 1 hr | 3.1+3.2 complete | Medium |
| **Deploy** | Update collector + config on titan-pi | 30 min | Test pass | Low |

**Total: ~7.5 hours over 2 sessions**

### Recommended Sequence

```
3.1a + 3.2a (parallel config changes)
  → 3.1b + 3.1c (time-aware scoring)
  → 3.2b (phase-aware scoring)
  → Test (dry-run with historical replay)
  → Deploy
  → Wait 48h
  → 3.3a + 3.3b (percentile calibration)
```

### Rollback Plan

All changes are config-driven. To rollback:
1. Remove `time_profile` and `pipeline_phase` from config.yaml
2. Collector reverts to default weights on next run
3. No data migration needed — score_details field captures the weights used

---

## Validation Plan

### Before Deploy
- Replay last 24h of raw metrics through new scoring logic
- Compare old scores vs new scores
- Verify: Tutor idle-hour scores increase, active-hour scores unchanged
- Verify: Scout pre-outreach score increases, other products unchanged

### After Deploy (48h monitoring)
- Check health_scores for score discontinuity at deploy time (expected one-time jump)
- Verify Tutor idle-hour average > 6.0 (was 2.8)
- Verify no false alerts triggered by score jump
- Verify alert thresholds still meaningful under new scoring

---

## Open Questions for Pepper

1. **Phase transitions — manual or auto-detect?** Safer to start manual. Auto-detect adds complexity.
2. **Should dashboard show "raw" and "adjusted" scores?** Or just adjusted? Showing both adds transparency but visual complexity.
3. **Chat session tracking fix — who owns?** Requires code change in soul-v2 `internal/chat/server/server.go` to emit session events. Is this a Shuri task or a Banner+Shuri collaboration?
4. **Alert threshold adjustment:** After 3.1+3.2, the current CRITICAL<2.0 / WARNING<2.5 may be too low given scores will generally be higher. Should we recalibrate alerts as part of 3.3, or leave them as-is?

---

*Previous design: [phase3-scoring-refinement-design.md](../banner-analyses/phase3-scoring-refinement-design.md) (2026-03-21)*
*72h analysis: [health-trend-72h-2026-03-24.md](../banner-analyses/health-trend-72h-2026-03-24.md)*
*Config reference: `~/.soul-v2/analytics/config.yaml` on titan-pi*
