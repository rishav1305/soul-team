# Phase 2 Implementation Spec — March 26, 2026

**Author:** Banner | **Pre-built:** March 25, 2026 (proactive)
**Priority stack (Pepper-approved):** (b) Scout reclassification -> (a) Alert dedup/threshold -> (d) Correlated dedup -> (c) Tutor weight

---

## 1. Scout Usage Reclassification (CPO-approved, highest priority)

### What
Move `artifacts_today` from Scout's business scoring to usage scoring, giving Scout instant usage signal.

### Current State
- `compute_usage_score()` only reads: `api_calls_period`, `unique_endpoints`, `active_sessions`, `tool_calls_period`
- Scout's `compute_business_score()` includes `artifacts_today` with weight 0.20
- Scout usage_score is always 0.0 because JSONL window misses real activity

### Change Required
**NOT pure config** — requires small code change:

1. **In `compute_usage_score()`:** Add product-aware branch:
```python
def compute_usage_score(usage: dict, product: str = None) -> tuple[float, dict]:
    # ... existing code ...

    # Scout: include artifacts_today as usage indicator (CPO-approved Mar 25)
    if product == "scout":
        artifacts = usage.get("artifacts_today", 0)
        scores["artifacts_today"] = min(10, artifacts * 2) if artifacts > 0 else 0
        weights["artifacts_today"] = 0.25
        # Rebalance: reduce api_calls weight from 0.30 to 0.15
        weights["api_calls"] = 0.15
```

2. **In collection flow:** Pass `artifacts_today` from business_metrics into usage_data for Scout:
```python
# After collecting Scout business metrics
if product == "scout" and "artifacts_today" in business_metrics:
    usage_data["artifacts_today"] = business_metrics["artifacts_today"]
```

3. **In config.yaml:** Remove `artifacts_today` from Scout business thresholds:
```yaml
scout:
  business:
    conversion_rate: {weight: 0.45}  # was 0.35, absorb freed weight
    stale_leads_ratio: {weight: 0.30}  # was 0.25
    followups_overdue: {weight: 0.25}  # was 0.20
    # artifacts_today: REMOVED (now in usage scoring)
```

### Expected Impact
Scout usage_score goes from 0.0 to ~5.0 when Hawkeye is active (19 artifacts today). Scout health_score would rise by ~1.0-1.5 during active hours.

---

## 2. Alert Dedup + Threshold Raise

### What
Deploy `alert_escalation_patch.py` (Layer 2+3) which adds:
- PERSISTENT escalation (4+ fires in 24h)
- Auto-dispatch to product owners
- Occurrence tagging

### Pre-deployment Steps
```bash
# On titan-pi
cd ~/.soul-v2/analytics/

# Dry run first
python3 alert_escalation_patch.py --dry-run

# If clean, apply
python3 alert_escalation_patch.py --apply

# Add schema columns
sqlite3 analytics.db 'ALTER TABLE alert_state ADD COLUMN fire_count INTEGER DEFAULT 0;'
sqlite3 analytics.db 'ALTER TABLE alert_state ADD COLUMN first_fired TEXT;'

# Restart collector
sudo systemctl restart soul-v2-observe
```

### Threshold Adjustment
Current: `health_score_critical: 2.0`, `health_score_warning: 2.5`
Proposed: **No change** — current thresholds already tuned from Phase 3.3. The escalation patch adds granularity without changing when alerts fire.

---

## 3. Correlated-Incident Dedup (Compliance Tracker)

### Schema
```sql
CREATE TABLE IF NOT EXISTS slo_compliance (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product             TEXT NOT NULL,
    tier                TEXT NOT NULL,  -- 'availability', 'latency', 'error_rate', 'health_score'
    window_start        TEXT NOT NULL,
    window_end          TEXT NOT NULL,
    total_observations  INTEGER NOT NULL,
    passing_count       INTEGER NOT NULL,
    compliance_pct      REAL NOT NULL,
    slo_target_pct      REAL NOT NULL,
    status              TEXT NOT NULL,  -- 'MEETING', 'AT_RISK', 'VIOLATED'
    correlated_incident BOOLEAN DEFAULT 0,  -- True if part of correlated Scout+Tutor event
    incident_group_id   TEXT,  -- Links correlated incidents
    computed_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS burn_rate (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product             TEXT NOT NULL,
    tier                TEXT NOT NULL,
    budget_total_min    REAL NOT NULL,     -- Total error budget for 30d window
    budget_consumed_min REAL NOT NULL,     -- Consumed so far
    budget_remaining_pct REAL NOT NULL,    -- % remaining
    burn_rate_1h        REAL,              -- Burn rate over last 1h (fast)
    burn_rate_6h        REAL,              -- Burn rate over last 6h (slow)
    alert_level         TEXT,              -- NULL, 'fast_burn', 'slow_burn', 'exhaustion'
    computed_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_slo_product_tier ON slo_compliance(product, tier, window_end);
CREATE INDEX IF NOT EXISTS idx_burn_product ON burn_rate(product, tier, computed_at);
```

### Correlated-Incident Dedup Logic
```python
CORRELATION_WINDOW_SEC = 300  # 5 minutes — tunable per Pepper

def detect_correlated_incident(conn, product, timestamp):
    """Check if Scout and Tutor went down within 5 min of each other."""
    if product not in ('scout', 'tutor'):
        return False, None

    other = 'tutor' if product == 'scout' else 'scout'

    row = conn.execute("""
        SELECT timestamp FROM service_snapshots
        WHERE product = ? AND is_up = 0
        AND abs(julianday(timestamp) - julianday(?)) * 86400 < ?
        ORDER BY abs(julianday(timestamp) - julianday(?))
        LIMIT 1
    """, (other, timestamp, CORRELATION_WINDOW_SEC, timestamp)).fetchone()

    if row:
        # Generate a shared incident group ID
        group_id = f"infra-{timestamp[:13]}"  # Group by hour
        return True, group_id
    return False, None
```

### Burn Rate Alert Thresholds
| Alert | Condition | Action |
|-------|-----------|--------|
| Fast burn | 14.4x consumption/1h | P1 → product owner + Pepper |
| Slow burn | 1x consumption/6h | P2 → product owner |
| Budget exhaustion | >80% consumed in 30d | P1 → CEO |

---

## 4. Tutor Human-Gated Weight (if time allows)

### What
Reduce Tutor's business_score weight during off-hours (00:00-15:00 IST, per existing time_profile).

### Current State
Tutor already has a `time_profile` in config with `idle` window (hours 0-15):
```yaml
idle:
  weights: {service: 0.70, usage: 0.05, business: 0.25}
```

**This is already partially implemented!** The idle window already reduces business weight from 0.50 to 0.25. The 46% WARNING rate means even 0.25 is too high for a product with zero-valued business metrics (readiness=0%, drills=0) during off-hours.

### Proposed Change
```yaml
idle:
  weights: {service: 0.80, usage: 0.05, business: 0.15}  # was 0.70/0.05/0.25
  business_floor:
    drills_today: 5.0
    readiness_pct: 5.0
    streak: 5.0  # ADD: streak should floor during idle too
```

This would push idle-mode health_score from ~2.8-3.0 up to ~4.0-4.5, keeping Tutor out of WARNING during Xavier's off-hours.

**Can defer to Phase 3.4** per Pepper — it's a scoring refinement, not a reliability fix.

---

## Implementation Order for Mar 26

| # | Task | Est. Time | Risk | Dependencies |
|---|------|-----------|------|--------------|
| 0 | ~~**Tutor collector query fix**~~ | ~~5 min~~ | ~~None~~ | **DONE by Shuri** — patched collector.py line 543 same session. Readiness now shows real data (9 mastered, 163 in_progress). |
| 1 | Scout usage reclassification | 20 min | Low | Config + small code change |
| 2 | Alert escalation patch deploy | 15 min | Low | Dry-run passed |
| 3 | Compliance tracker DDL | 10 min | None | Schema creation only |
| 4 | Compliance computation logic | 45 min | Medium | Needs rolling window SQL |
| 5 | Burn-rate alert logic | 30 min | Medium | Needs threshold tuning |
| 6 | Correlated-incident dedup | 20 min | Low | SQL pattern match |
| 7 | Tutor weight adjustment | 10 min | Low | Config change only |

**Total estimated:** ~2.5 hours if all 7 items. ~1.5 hours for priority items (1-3).

---

*Pre-built by Banner — March 25, 2026, Proactive Mode*
