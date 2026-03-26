# Chapter 19: Design a Message Queue

## Problem Statement

Design a distributed message queue similar to Apache Kafka, RabbitMQ, or Amazon SQS that enables asynchronous communication between services. The system must handle high throughput, guarantee message delivery, and support both point-to-point and publish-subscribe patterns at scale.

---

## Step 1: Scope

### Clarifying Questions to Ask

1. **Messaging pattern?** Point-to-point (work queue) or pub/sub (fan-out) or both?
2. **Ordering guarantees?** Strict FIFO per partition? Global ordering? Best-effort?
3. **Delivery semantics?** At-most-once, at-least-once, or exactly-once?
4. **Throughput?** Messages per second? Average message size?
5. **Retention?** How long to keep messages? Time-based or size-based?
6. **Consumer model?** Push or pull? Consumer groups?
7. **Durability?** Can messages be lost? Or must they survive node failures?
8. **Latency?** P99 for produce and consume?

### Typical Assumptions

- **Throughput:** 1M messages/second (writes), 2M messages/second (reads — fan-out)
- **Message size:** 1KB average, 1MB max
- **Retention:** 7 days (configurable per topic)
- **Delivery:** At-least-once (exactly-once for specific use cases)
- **Ordering:** Per-partition FIFO
- **Durability:** Messages survive up to 2 node failures (RF=3)
- **Latency:** P99 < 10ms produce, < 50ms consume
- **Topics:** 10K topics, 100K total partitions

### Back-of-Envelope

```
Write throughput: 1M msg/s * 1KB = 1GB/s
With RF=3 replication: 3GB/s internal network traffic
Daily storage: 1GB/s * 86,400 = ~86TB/day
7-day retention: ~600TB
Brokers needed (10TB SSD each): 600TB / 8TB usable ≈ 75 brokers
Network: Each broker handles ~40MB/s writes → 10Gbps NIC sufficient
```

---

## Step 2: High-Level Design

```
┌──────────┐     ┌───────────┐     ┌──────────────────────────┐     ┌──────────┐
│ Producer  │────▶│  Broker   │     │    Topic: "orders"       │     │ Consumer │
│ (App)    │     │  Cluster  │     │  ┌────┐ ┌────┐ ┌────┐   │◀────│  Group   │
└──────────┘     │           │     │  │P0  │ │P1  │ │P2  │   │     └──────────┘
                 │  ┌─────┐  │     │  │    │ │    │ │    │   │
                 │  │Broker│  │     │  │msg1│ │msg2│ │msg4│   │
                 │  │  1   │  │     │  │msg3│ │msg5│ │msg7│   │
                 │  └─────┘  │     │  │msg6│ │msg8│ │    │   │
                 │  ┌─────┐  │     │  └────┘ └────┘ └────┘   │
                 │  │Broker│  │     └──────────────────────────┘
                 │  │  2   │  │
                 │  └─────┘  │
                 │  ┌─────┐  │     ┌──────────────┐
                 │  │Broker│  │     │ Coordination │
                 │  │  3   │  │     │   Service    │
                 │  └─────┘  │     │  (ZooKeeper/ │
                 └───────────┘     │   KRaft)     │
                                   └──────────────┘
```

### Core Abstractions

1. **Topic** — Named stream of messages (e.g., "orders", "user-events", "logs")
2. **Partition** — Ordered, immutable sequence of messages within a topic. Unit of parallelism.
3. **Producer** — Publishes messages to a topic (optionally with partition key)
4. **Consumer Group** — Set of consumers that collectively process all partitions of a topic. Each partition assigned to exactly one consumer in the group.
5. **Offset** — Position of a message within a partition. Consumers track their offset.
6. **Broker** — Server that stores partitions and serves read/write requests.

### Key Design Decisions

| Decision | Choice | Why |
|---|---|---|
| Storage model | Append-only log on disk | Sequential I/O is fast, enables replay |
| Consumer model | Pull-based | Consumer controls pace, natural backpressure |
| Partition assignment | Hash(key) % num_partitions | Ensures ordering per key |
| Replication | Leader-follower per partition | Durability + read scalability |

---

## Step 3: Deep Dives

### Deep Dive 1: Storage Engine (The Append-Only Log)

**Why append-only log works:**
- Sequential disk writes: 600MB/s on modern SSDs (vs 100MB/s random)
- No seeks, no compaction needed during writes
- Messages are immutable once written

**Segment Structure:**
```
Partition-0/
├── 00000000000000000000.log    # Segment file (messages)
├── 00000000000000000000.index  # Offset → file position mapping
├── 00000000000000000000.timeindex  # Timestamp → offset mapping
├── 00000000000005242880.log    # Next segment (after rollover)
├── 00000000000005242880.index
└── ...
```

- Each segment: fixed size (e.g., 1GB) or time-based rollover
- Index: sparse (every Nth offset) → binary search + sequential scan
- Old segments deleted after retention period expires

**Zero-Copy Transfer:**
- `sendfile()` system call: data moves from disk → NIC without user-space copy
- Kafka's key optimization: no serialization/deserialization on broker for reads
- Throughput: single broker can serve 2-5GB/s read throughput

**Page Cache Leverage:**
- Broker doesn't manage its own cache — relies on OS page cache
- Recent messages (tail reads) served from memory without explicit caching
- Historical reads (catch-up consumers) hit disk but benefit from sequential prefetch

### Deep Dive 2: Replication Protocol

**ISR (In-Sync Replicas):**
- Each partition has 1 leader + N-1 followers
- ISR = set of replicas that are "caught up" (within configurable lag threshold)
- **Write is committed** when all ISR replicas acknowledge (configurable: `acks=all`)
- If a follower falls behind, it's removed from ISR (can rejoin after catching up)

**Leader Election:**
1. Leader fails → controller detects via heartbeat miss
2. Controller selects new leader from ISR (prefer most up-to-date)
3. If ISR is empty → either wait (lose availability) or elect non-ISR replica (risk data loss)
4. **Unclean leader election:** Configurable tradeoff between availability and durability

**Replication Flow:**
```
Producer → Leader Broker
                │
                ├──▶ Write to local log
                │
                ├──▶ Follower 1 fetches (pull-based replication)
                │         └── Write to local log → ACK
                │
                └──▶ Follower 2 fetches (pull-based replication)
                          └── Write to local log → ACK

All ISR ACKed → Message committed → Producer gets success response
```

**High-Watermark:**
- Each partition tracks "high-watermark" = offset of last committed message
- Consumers can only read up to high-watermark (prevents reading uncommitted data)
- If leader fails, new leader truncates any messages beyond its own high-watermark

### Deep Dive 3: Consumer Groups and Partition Assignment

**Consumer Group Protocol:**
- Each consumer group has a **group coordinator** (a broker)
- Consumers send heartbeats to coordinator
- When group membership changes (join/leave/crash), coordinator triggers **rebalance**

**Rebalance Strategies:**

| Strategy | How | Tradeoff |
|---|---|---|
| Eager (stop-the-world) | All consumers release partitions → reassign all | Simple but causes processing pause |
| Cooperative (incremental) | Only affected partitions reassigned | No global pause, more complex |
| Sticky | Try to preserve existing assignments | Minimizes partition migration |

**Exactly-Once Semantics:**
- **Idempotent producer:** Broker deduplicates by (producer_id, sequence_number) per partition
- **Transactional produce:** Atomic writes across multiple partitions (all-or-nothing)
- **Consumer:** Read committed messages only → process → commit offset atomically
- End-to-end exactly-once requires: idempotent producer + transactional produce + consume-process-commit atomicity

### Deep Dive 4: Ordering and Partitioning

**Per-Partition FIFO Guarantee:**
- Messages with same partition key → same partition → strict order
- Example: all events for `user_id=123` go to same partition → ordered
- Cross-partition: NO ordering guarantee (intentional — enables parallelism)

**Partition Key Design:**
- Good: `user_id`, `order_id`, `device_id` — events that must be ordered go together
- Bad: `country_code` — skewed distribution, one partition gets 50% of traffic
- No key: round-robin distribution (max throughput, no ordering)

**Hot Partition Problem:**
- One partition key generates disproportionate traffic (e.g., celebrity user)
- Solution 1: Compound key with salt: `user_id + random(0,N)` — trades ordering for balance
- Solution 2: Sub-partitioning: process hot key on dedicated consumer
- Solution 3: Increase partition count and use more granular keys

### Deep Dive 5: Delivery Semantics Deep Dive

**At-Most-Once:**
```
1. Consumer reads message
2. Consumer commits offset
3. Consumer processes message
If crash between 2 and 3 → message lost (already committed)
```
- Use case: Metrics, logs where occasional loss is OK

**At-Least-Once:**
```
1. Consumer reads message
2. Consumer processes message
3. Consumer commits offset
If crash between 2 and 3 → message reprocessed (offset not committed)
```
- Use case: Most applications — combine with idempotent processing
- **Idempotent consumer:** Use message ID or idempotency key to detect reprocessing

**Exactly-Once (End-to-End):**
```
1. Consumer reads message within transaction
2. Consumer processes message
3. Consumer writes output + commits offset atomically
```
- Requires: transactional writes + offset stored in same system as output
- Example: Kafka Streams stores offsets in output topic via transactions

---

## Step 4: Wrap-Up

### Bottlenecks and Scaling

| Component | Bottleneck | Mitigation |
|---|---|---|
| Single partition throughput | ~10MB/s per partition | Increase partition count for parallelism |
| Broker disk I/O | Sequential write saturation | Spread partitions across multiple disks, use NVMe |
| Replication network | RF=3 triples internal bandwidth | Compression (snappy, lz4, zstd) |
| Consumer lag | Slow consumers fall behind | Autoscale consumer group, alert on lag |
| Partition rebalance | Stop-the-world during rebalance | Cooperative/sticky rebalance, static membership |

### Failure Scenarios

1. **Broker crash:** Leader partitions fail over to ISR replicas. Brief unavailability per partition (seconds). No data loss if `acks=all`.
2. **Network partition:** Minority side loses leadership. Majority continues. Risk of split-brain prevented by controller quorum.
3. **Disk failure:** Partition replicas on failed disk unavailable. Replica on other brokers promotes. Re-replicate to new broker.
4. **Consumer crash:** Coordinator detects via heartbeat timeout → rebalance assigns orphaned partitions to remaining consumers.
5. **Slow consumer:** Lag increases → messages may expire before consumption. Alert on consumer lag, autoscale consumers.

### Kafka vs RabbitMQ vs SQS (Common Interview Question)

| Feature | Kafka | RabbitMQ | SQS |
|---|---|---|---|
| Model | Append-only log | Message broker (AMQP) | Managed queue |
| Ordering | Per-partition FIFO | Per-queue FIFO | FIFO queues (optional) |
| Retention | Time/size based (replay possible) | Deleted on ACK | 4-14 days |
| Throughput | Millions msg/s | Thousands msg/s | Thousands msg/s |
| Consumer model | Pull | Push or Pull | Pull (long polling) |
| Use case | Event streaming, logs, CDC | Task queues, RPC, routing | Serverless, decoupling |
| Exactly-once | Yes (transactions) | No (at-least-once) | Yes (deduplication) |

### 10x Scale Discussion

- **10x throughput:** More partitions + more brokers. Kafka scales linearly with brokers.
- **10x retention:** Tiered storage — recent data on SSD, older data on S3/HDFS (Kafka KIP-405).
- **Global:** Multi-datacenter replication (MirrorMaker 2 / Confluent Replicator). Active-active with conflict resolution or active-passive.
- **Multi-tenancy:** Quotas per client (produce/consume rate limits), namespace isolation.

### Design Review Criteria

| Criterion | Key Signal |
|---|---|
| Requirements | Clarified: pattern (pub/sub vs P2P), ordering, delivery semantics, retention |
| Storage | Append-only log, segment files, zero-copy transfer, page cache leverage |
| Partitioning | Partition key design, parallelism tradeoffs, hot partition mitigation |
| Replication | ISR protocol, leader election, high-watermark, unclean election tradeoff |
| Consumer model | Consumer groups, rebalance strategies, offset management |
| Delivery guarantees | At-least-once vs exactly-once with implementation detail |
| Failure handling | Broker crash, network partition, consumer lag, disk failure |

---

## Interview Tips

1. **Lead with the log abstraction.** "A message queue is fundamentally an append-only log with consumer offsets." This shows you understand the core, not just the API.
2. **Partition = unit of everything.** Parallelism, ordering, replication, storage — all partition-scoped. Make this clear early.
3. **The delivery semantics question is coming.** Know the difference between at-most-once, at-least-once, exactly-once AND how each is implemented (not just defined).
4. **ISR is the most elegant part.** Explaining ISR + high-watermark + unclean leader election shows deep distributed systems knowledge.
5. **Don't forget the consumer side.** Most candidates design only the broker. Consumer groups, rebalancing, and offset management are equally important.
