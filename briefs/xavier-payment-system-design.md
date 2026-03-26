# Chapter 16: Design a Payment System

## Problem Statement

Design a payment system that processes online transactions — similar to Stripe, PayPal, or the payment layer in any e-commerce platform. The system must handle card payments, bank transfers, and wallet transactions while maintaining financial integrity across millions of concurrent transactions.

---

## Step 1: Scope

### Clarifying Questions to Ask

1. **What payment methods?** Credit/debit cards, bank transfers, digital wallets, UPI?
2. **Scale?** How many transactions per day? Peak QPS?
3. **Geography?** Single country or multi-currency?
4. **Payment flow?** One-time payments only, or also recurring/subscriptions?
5. **Settlement?** Do we need to handle merchant payouts?
6. **Refunds?** Full and partial refund support?
7. **Compliance?** PCI DSS, PSD2, SOX requirements?

### Typical Assumptions

- **DAU:** 1M daily active paying users
- **Daily transactions:** 5M (some users make multiple purchases)
- **Peak QPS:** ~200 TPS (peak at 2x average)
- **Payment methods:** Cards (via PSP), bank transfers, digital wallets
- **Latency:** < 3s end-to-end for payment confirmation
- **Consistency:** Strong consistency required — never charge twice, never lose a payment
- **Multi-currency:** Yes, with exchange rate service

### Back-of-Envelope

```
Average QPS: 5M / 86,400 ≈ 58 TPS
Peak QPS: ~200 TPS
Average transaction size: $50
Daily volume: $250M
Storage per transaction: ~2KB (metadata + audit trail)
Daily storage: 5M * 2KB = 10GB
Annual storage: ~3.6TB
```

---

## Step 2: High-Level Design

```
┌──────────┐     ┌───────────┐     ┌──────────────┐     ┌─────────────┐
│  Client   │────▶│ API Gateway│────▶│Payment Service│────▶│     PSP     │
│(Web/Mobile)│    │(Auth, Rate │     │ (Core Logic) │     │(Stripe/Adyen)│
└──────────┘     │ Limit, TLS)│     └──────┬───────┘     └─────────────┘
                 └───────────┘            │
                                          │
                      ┌───────────────────┼───────────────────┐
                      │                   │                   │
                ┌─────▼─────┐   ┌────────▼────────┐   ┌─────▼──────┐
                │   Ledger   │   │  Payment State  │   │  Message   │
                │  Service   │   │   Store (DB)    │   │   Queue    │
                │(Double-Entry)│  │ (Transactions)  │   │(Async Tasks)│
                └───────────┘   └─────────────────┘   └──────┬─────┘
                                                             │
                                                    ┌────────▼────────┐
                                                    │  Reconciliation │
                                                    │     Worker      │
                                                    └─────────────────┘
```

### Core Components

| Component | Responsibility |
|---|---|
| **API Gateway** | Authentication, rate limiting, TLS termination, idempotency key validation |
| **Payment Service** | Core payment orchestration — validates, routes, tracks state |
| **PSP (Payment Service Provider)** | External gateway (Stripe, Adyen, PayPal) — handles actual card/bank operations |
| **Ledger Service** | Double-entry bookkeeping — every transaction creates debit + credit entries |
| **Payment State Store** | Persistent transaction state — PostgreSQL for ACID guarantees |
| **Message Queue** | Async processing — notifications, webhooks, reconciliation triggers |
| **Reconciliation Worker** | Compares internal records vs PSP settlement files — catches discrepancies |

### Payment Flow (Happy Path)

1. Client sends payment request with **idempotency key**
2. API Gateway validates auth, checks rate limits, forwards to Payment Service
3. Payment Service creates transaction record in DB (status: `PENDING`)
4. Payment Service calls PSP API to process the charge
5. PSP returns success → Payment Service updates status to `COMPLETED`
6. Ledger Service records double-entry (debit buyer, credit merchant)
7. Async: notification sent to buyer, webhook sent to merchant

---

## Step 3: Deep Dive

### 3.1 Idempotency — The Most Critical Concept

**Problem:** Network failures, timeouts, and retries can cause duplicate charges. A $50 charge retried 3 times must result in exactly ONE $50 debit.

**Solution:** Idempotency key (UUID) sent by client with every request.

```
POST /v1/payments
Headers:
  Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

Body:
  { "amount": 5000, "currency": "USD", "method": "card", "card_token": "tok_xxx" }
```

**Implementation:**

```
1. Receive request with idempotency key
2. Check idempotency store:
   a. Key exists + completed → return stored result (no re-execution)
   b. Key exists + in-progress → return 409 Conflict (concurrent duplicate)
   c. Key not found → proceed with payment
3. Store key with status "in-progress" (with TTL, e.g., 24h)
4. Process payment
5. Update key with final result
```

**Storage:** Redis for fast lookup (TTL 24-48 hours), backed by persistent DB.

**Interview signal:** If you don't mention idempotency in a payment design, it's a major red flag.

### 3.2 Double-Entry Ledger

**Principle:** Every financial movement creates exactly TWO entries — a debit and a credit. The total sum across all entries must always be zero.

```
Transaction: User pays $50 to Merchant

Entries:
| ID | Account      | Type   | Amount | Currency | Transaction ID |
|----|-------------|--------|--------|----------|----------------|
| 1  | user_wallet  | DEBIT  | -5000  | USD      | txn_abc123     |
| 2  | merchant_acc | CREDIT | +5000  | USD      | txn_abc123     |
```

**Key properties:**
- **Append-only:** Entries are NEVER updated or deleted. Corrections create new entries.
- **Balance invariant:** SUM(all entries) = 0, always.
- **Audit trail:** Every dollar movement is traceable.
- **Refund:** Creates reverse entries (credit user, debit merchant).

### 3.3 Payment State Machine

Payments transition through well-defined states:

```
                    ┌──────────┐
              ┌────▶│ DECLINED │
              │     └──────────┘
┌─────────┐   │     ┌──────────┐     ┌───────────┐
│ CREATED │───┼────▶│ PENDING  │────▶│ COMPLETED │
└─────────┘   │     └────┬─────┘     └─────┬─────┘
              │          │                  │
              │     ┌────▼─────┐     ┌──────▼──────┐
              └────▶│  FAILED  │     │  REFUNDED   │
                    └──────────┘     │(full/partial)│
                                     └─────────────┘
```

**Key rules:**
- `COMPLETED` → only transition to `REFUNDED`
- `FAILED` → can retry (creates new transaction, NOT same one)
- `PENDING` → timeout after N seconds → `FAILED` + reconciliation check
- State transitions are idempotent and logged

### 3.4 Handling Failures — The Hard Part

| Failure Point | What Happens | How to Handle |
|---|---|---|
| Client → API Gateway timeout | Client doesn't know if payment was received | Client retries with same idempotency key |
| Payment Service → PSP timeout | We charged or didn't — we don't know | Mark as `UNKNOWN`, reconciliation job resolves |
| PSP returns error | Payment failed definitively | Mark `FAILED`, notify user, allow retry |
| DB write fails after PSP success | PSP charged but we lost the record | PSP webhook + reconciliation catches it |
| Partial network partition | Some services reachable, others not | Saga pattern with compensating transactions |

**Reconciliation is the safety net.** Every night (or more frequently), compare:
- Internal transaction records vs PSP settlement files
- Ledger balances vs bank statements
- Flag discrepancies for manual review

### 3.5 Consistency Strategy

**Payment systems are CP, not AP.** It's better to reject a payment (temporary unavailability) than to charge twice (data inconsistency).

- **Database:** PostgreSQL with SERIALIZABLE isolation for critical payment writes
- **No eventual consistency** for payment records — use synchronous replication
- **Distributed transactions:** Saga pattern with compensating actions (not 2PC — PSPs can't participate in 2PC)

### 3.6 Security

- **PCI DSS Compliance:** Never store raw card numbers. Use tokenization via PSP.
- **Encryption:** TLS 1.3 in transit, AES-256 at rest for sensitive fields
- **Card tokens:** PSP returns a token representing the card — we store the token, never the PAN
- **Fraud detection:** Rule engine + ML model scoring transactions in real-time
- **Audit logging:** Every API call, state change, and admin action logged immutably

---

## Step 4: Wrap-Up

### Top 3 Bottlenecks

1. **PSP latency/availability:** External dependency — use circuit breakers, multiple PSP fallbacks
2. **Hot merchant accounts:** Popular merchants create write hotspots — shard ledger by account
3. **Reconciliation lag:** Settlement files arrive in batches — may take hours to detect discrepancies

### Failure Scenario

**What if the PSP goes down?**
- Circuit breaker trips after N consecutive failures
- Queue payments for retry (with user notification of delay)
- Route to backup PSP if available
- Never silently drop a payment — always inform the user

### At 10x Scale

- Shard payment DB by merchant_id or region
- Multiple PSP integrations for redundancy and cost optimization
- Real-time streaming reconciliation (not batch)
- Dedicated fraud detection service with ML pipeline
- Geographic partitioning for multi-region deployment

### Monitoring

- **Business metrics:** Transaction success rate, average processing time, refund rate
- **Technical metrics:** PSP latency P50/P95/P99, DB connection pool utilization, queue depth
- **Alerts:** Success rate drops below 99%, PSP latency exceeds 5s, reconciliation discrepancy detected

---

## Design Review Criteria

| Criterion | What to Check |
|---|---|
| Idempotency | Is there an idempotency key mechanism? Does retry return stored result? |
| Double-entry ledger | Are all money movements recorded as debit + credit pairs? |
| State machine | Are payment states well-defined with valid transitions? |
| Failure handling | What happens at each failure point? Is there a reconciliation process? |
| Consistency | Is CP chosen over AP? Is the DB ACID-compliant for payment writes? |
| Security | Tokenization (no raw card storage)? PCI DSS awareness? Encryption? |
| Scalability | Can it handle 10x load? Sharding strategy? Multiple PSPs? |

---

## Key Terminology

| Term | Definition |
|---|---|
| **PSP** | Payment Service Provider — external service that handles actual card/bank operations (Stripe, Adyen, PayPal) |
| **PAN** | Primary Account Number — the card number. NEVER store this. |
| **Idempotency key** | Client-generated UUID ensuring exactly-once processing |
| **Double-entry** | Accounting principle: every transaction creates equal debit and credit entries |
| **Reconciliation** | Process of comparing internal records against external settlement data |
| **Settlement** | Transfer of funds from acquiring bank to merchant's bank account |
| **Chargeback** | Buyer disputes a charge — funds reversed from merchant to buyer |
| **Saga pattern** | Distributed transaction pattern using compensating actions instead of 2PC |
| **PCI DSS** | Payment Card Industry Data Security Standard — compliance framework |

---

## Sources

- Alex Xu, "System Design Interview Volume 2" — Chapter on Payment System
- Stripe Architecture (engineering blog)
- Gergely Orosz, "Designing a Payment System" (Pragmatic Engineer)
