# Soul v2 Data Quality Audit
**Author:** Banner (Data Science) | **Date:** 2026-03-24 | **Type:** Proactive audit

---

## Summary

Profiled 8 databases across the Soul v2 ecosystem. 3 are actively producing data (scout, tutor, analytics). 5 are stale or nearly empty.

## Findings by Database

### Active & Healthy

| Database | Size | Records | Last Activity | Status |
|----------|------|---------|---------------|--------|
| **analytics** | 1.5 MB | 1,111 collections, 849 health scores | Mar 24 (today) | Healthy |
| **scout** | 964 KB | 131 leads, 15 artifacts | Mar 24 (today) | Healthy (pre-outreach) |
| **tutor** | 964 KB | 179 topics, 236 progress | Mar 24 (today) | Healthy |

### Stale

| Database | Size | Last Activity | Days Stale | Notes |
|----------|------|---------------|------------|-------|
| **chat** | 784 KB | Mar 18 | **6 days** | 33 sessions, 154 messages. No new sessions since Mar 18. |
| **tasks** | 44 KB | Mar 15 | **9 days** | 9 tasks. 100% null `description` and `workflow` fields. |
| **projects** | 84 KB | Mar 14 | **10 days** | 11 projects. 100% null `synced_at` in profile_syncs. |

### Minimal Use

| Database | Size | Records | Notes |
|----------|------|---------|-------|
| **mesh** | 36 KB | 1 node, 0 peers | Networking feature unused |
| **sentinel** | 60 KB | 14 challenges, 3 attempts | Security sandbox barely used |
| **soul-v2.db** | 0 bytes | Empty | Placeholder? |

## Key Data Quality Issues

### 1. Chat Stale (P3)
No new sessions since Mar 18. This is 6 days of no usage data, which means the analytics dashboard's Chat business_score (constant 5.75) is structurally stale, not just structurally limited. The session tracking issue noted in Phase 3 spec is compounded by this.

**Recommendation:** Check if Soul v2 chat is actually being used via browser but just not logging sessions.

### 2. Scout Empty Feature Tables (Expected, P4)
6 of 12 Scout tables have 0 rows: `agent_runs`, `content_backlog`, `content_posts`, `interactions`, `optimizations`, `platform_trust`. These are expected to populate when outreach activates Mar 27.

**Action:** After Mar 27, if `interactions` and `agent_runs` remain at 0 for 48h, flag to Hawkeye.

### 3. Tutor Unused Features (P4)
`mock_sessions`, `star_stories`, and `confidence_ratings` have 0 rows despite active learning data. These features may not be integrated yet, or they need Xavier to start using them.

**Recommendation:** Ask Xavier if mock interview and STAR story features are functional.

### 4. Tasks/Projects Data Quality (P3)
- `tasks.description`: 100% null (9/9 tasks have no description)
- `tasks.workflow`: 100% null
- `projects.profile_syncs.synced_at`: 100% null (77 sync records with no timestamp)
- Both databases stale for 9-10 days

**Recommendation:** These may be legacy tables from an earlier version. Ask Shuri if they're still in use or can be archived.

## For Pepper (CPO)

The analytics infrastructure (Phase 3 now deployed) is the strongest data producer. Scout and Tutor are active. The main gap is Chat — if it's being used but not tracked, that's a data integrity issue. If it's genuinely unused, the health score is misleading in a different way (it looks healthy but there's no actual product engagement).

## For Shuri (TPM)

- `soul-v2.db` is 0 bytes — intentional or bug?
- `tasks.db` and `projects.db` appear to be legacy. Confirm if they can be deprecated.
- Chat session tracking is the highest-priority data gap.
