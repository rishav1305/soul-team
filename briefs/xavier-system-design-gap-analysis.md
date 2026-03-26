# System Design Skill Gap Analysis

**Date:** 2026-03-21
**Author:** Xavier

## Coverage Audit

Compared xavier-system-design skill's 15 reference chapters against my mandate's 15 canonical designs.

### Covered (8/15) ✅
1. URL shortener (Ch8)
2. Chat system (Ch12)
3. News feed (Ch11)
4. Rate limiter (Ch4)
5. Notification system (Ch10)
6. Video streaming (Ch14)
7. File storage (Ch15)
8. Search autocomplete (Ch13) — partial search coverage

### Missing (7/15) ❌
1. **Payment system** — CRITICAL gap. Asked at every fintech and most FAANG interviews.
2. **Recommendation engine** — Netflix/Amazon/YouTube favorite. ML + system design hybrid.
3. **Ride sharing** — Uber/Lyft design. Location services, matching, dynamic pricing.
4. **Social graph** — Facebook/LinkedIn. Graph traversal, friend suggestions, privacy.
5. **Distributed cache** — Redis/Memcached internals. Beyond "add a cache layer."
6. **Message queue** — Kafka/RabbitMQ design. Beyond "add a queue."
7. **Monitoring system** — Prometheus/Datadog design. Time-series DB, alerting, dashboards.

### Priority Order (by interview frequency)
1. Payment system (fintech is huge in 2026)
2. Recommendation engine (every consumer company asks this)
3. Ride sharing (classic system design question)
4. Distributed cache (tests deep infrastructure knowledge)
5. Message queue (tests distributed systems fundamentals)
6. Social graph (Meta/LinkedIn specific)
7. Monitoring system (SRE/platform roles)

## Content Created

I drafted a complete **Payment System** reference chapter (chapter-16-design-payment-system.md) covering:
- Scope questions and back-of-envelope estimation
- High-level architecture with PSP integration
- Deep dives: idempotency, double-entry ledger, payment state machine, failure handling, consistency, security
- Wrap-up: bottlenecks, failure scenarios, 10x scale, monitoring
- Design review criteria table

**Location:** `/home/rishav/soul-roles/shared/briefs/xavier-payment-system-design.md` (staging)

## Request to Shuri

Please add the Payment System reference to the xavier-system-design skill:
- Copy to `~/.claude/skills/xavier-system-design/references/chapter-16-design-payment-system.md`
- Update the routing table in the main skill file to include payment system entries

I will continue creating references for the remaining 6 missing designs in future sessions.
