# Chapter 18: Design a Distributed Cache

## Problem Statement

Design a distributed caching system similar to Redis or Memcached that provides low-latency key-value storage across a cluster of machines. The system must handle millions of reads/writes per second, support eviction policies, and maintain availability during node failures.

---

## Step 1: Scope

### Clarifying Questions to Ask

1. **Data model?** Simple key-value? Support for data structures (lists, sets, sorted sets, hashes)?
2. **Scale?** How many keys? Total data size? Read/write QPS?
3. **Latency target?** P99 for reads and writes?
4. **Consistency model?** Strong consistency or eventual? What happens during partitions?
5. **Persistence?** Pure in-memory, or optional durability (AOF, snapshots)?
6. **Eviction policy?** LRU, LFU, TTL-based? What happens when memory is full?
7. **Multi-tenancy?** Single application or shared across services?
8. **Data types?** String-only or complex types (lists, sorted sets, hashes)?

### Typical Assumptions

- **Total data:** 1TB distributed across cluster
- **Keys:** 100M active keys
- **Read QPS:** 1M (80% of traffic)
- **Write QPS:** 250K (20% of traffic)
- **Average value size:** 1-10KB
- **P99 latency:** < 1ms for reads, < 5ms for writes
- **Availability target:** 99.99%
- **Eviction:** LRU with TTL support
- **Consistency:** Eventual (AP system), last-write-wins for conflicts

### Back-of-Envelope

```
Total data: 1TB
Nodes needed (128GB RAM each): 1TB / 100GB usable ≈ 10 nodes
With replication (RF=3): 30 nodes
Read QPS per node: 1M / 10 = 100K reads/node (feasible for in-memory)
Write QPS per node: 250K / 10 = 25K writes/node
Network bandwidth per node: 100K * 5KB = 500MB/s reads (need 10Gbps NICs)
```

---

## Step 2: High-Level Design

```
┌──────────┐     ┌───────────────┐     ┌──────────────────┐
│  Client   │────▶│  Cache Proxy  │────▶│   Cache Cluster   │
│ (App SDK) │     │ (Routing +    │     │  ┌─────┐ ┌─────┐ │
└──────────┘     │  Connection   │     │  │Node1│ │Node2│ │
                 │  Pool)        │     │  └─────┘ └─────┘ │
                 └───────────────┘     │  ┌─────┐ ┌─────┐ │
                                       │  │Node3│ │Node4│ │
                                       │  └─────┘ └─────┘ │
                                       └──────────────────┘
                                              │
                                       ┌──────▼──────┐
                                       │ Coordination │
                                       │  Service     │
                                       │ (ZooKeeper/  │
                                       │  etcd)       │
                                       └─────────────┘
```

### Key Components

1. **Client SDK / Proxy Layer**
   - Consistent hashing to route keys to correct shard
   - Connection pooling to cache nodes
   - Client-side caching (local L1 cache) for hot keys
   - Retry logic with circuit breaker

2. **Cache Node**
   - In-memory hash table for key-value storage
   - Eviction engine (LRU/LFU/TTL)
   - Replication to followers (async or semi-sync)
   - Snapshot + AOF for optional persistence

3. **Cluster Manager**
   - Tracks node health (heartbeats)
   - Manages shard assignment (hash slot mapping)
   - Orchestrates failover when a node dies
   - Handles rebalancing when nodes are added/removed

4. **Coordination Service**
   - Stores cluster topology and shard map
   - Leader election for shard groups
   - Provides consistent view of cluster state

---

## Step 3: Deep Dives

### Deep Dive 1: Data Partitioning (Sharding)

**Consistent Hashing with Virtual Nodes**
- Hash ring with each physical node mapped to 100-200 virtual nodes
- Key → hash(key) → walk clockwise to nearest virtual node → map to physical node
- Adding/removing a node only moves ~1/N of keys (minimal disruption)

**Hash Slot Approach (Redis Cluster Style)**
- Divide keyspace into 16,384 hash slots
- Each node owns a subset of slots: `slot = CRC16(key) % 16384`
- Slot-to-node mapping stored in cluster state
- Resharding = migrate slots between nodes one at a time

**Comparison:**
| Approach | Pros | Cons |
|---|---|---|
| Consistent hashing | Smooth scaling, minimal data movement | Virtual node count tuning, uneven distribution possible |
| Hash slots | Explicit control, easy to reason about | Slot migration requires coordination |

### Deep Dive 2: Eviction Policies

**LRU (Least Recently Used)**
- Doubly-linked list + hash map (O(1) get/put/evict)
- On access: move node to head
- On eviction: remove from tail
- **Redis approximation:** Sample 5 random keys, evict the oldest — avoids O(n) linked list overhead

**LFU (Least Frequently Used)**
- Track access frequency per key
- Evict keys with lowest frequency
- Better for skewed workloads (hot keys stay, rare keys evict)
- **Redis implementation:** Uses Morris counter (logarithmic, probabilistic) to save memory — 8 bits per key

**TTL-Based Eviction**
- Each key has an expiry timestamp
- **Lazy deletion:** Check TTL on read, delete if expired
- **Active expiry:** Background thread samples 20 keys with TTL, deletes expired ones. If >25% expired, repeat immediately.
- Combine: lazy + active = low CPU overhead + bounded memory waste

**Eviction Decision Tree:**
```
Memory full?
├── TTL keys exist with expired TTL? → Delete those first
├── LRU/LFU policy configured? → Evict per policy
└── No eviction policy? → Return OOM error on writes
```

### Deep Dive 3: Replication and Consistency

**Leader-Follower Replication**
- Each shard has 1 leader + N-1 followers (typically RF=3)
- Writes go to leader → async replicated to followers
- Reads can go to leader (strong) or any replica (eventually consistent, lower latency)

**Replication Lag Handling:**
- **Read-your-writes:** Client pins to leader for read-after-write consistency
- **Monotonic reads:** Client pins to a specific replica
- **Version vectors:** Detect stale reads and retry from leader

**Failover:**
1. Coordination service detects leader heartbeat miss (configurable timeout, typically 5-10s)
2. Followers with most up-to-date replication offset elected as new leader
3. Client SDK updated with new shard map
4. Old leader's remaining writes may be lost (async replication tradeoff)

**Split-brain prevention:**
- Fencing tokens: new leader gets monotonically increasing token
- Old leader's writes rejected by followers if token < current leader's token
- Use lease-based leader election (leader must renew lease to remain leader)

### Deep Dive 4: Hot Key Problem

**Problem:** A single key (e.g., celebrity profile, viral post) gets millions of QPS → single node overwhelmed.

**Solutions:**

1. **Local cache (L1):** Client caches hot keys locally with short TTL (1-5s)
   - Reduces cache cluster QPS dramatically
   - Tradeoff: slightly stale data for hot keys

2. **Read replicas for hot keys:** Detect hot keys → replicate to multiple nodes → spread reads
   - Detection: track per-key QPS, flag keys exceeding threshold

3. **Key replication:** Append random suffix to key: `hot_key:1`, `hot_key:2`, ..., `hot_key:N`
   - Write to all N variants, read from random one
   - Spreads load across N nodes

4. **Embedded caching (client-side):** Application maintains in-process cache (Guava/Caffeine)
   - Zero network overhead for cached hits
   - Must handle invalidation (pub/sub or TTL)

### Deep Dive 5: Cache Patterns with Backend

**Cache-Aside (Lazy Loading)**
```
Read: Check cache → miss → read DB → write cache → return
Write: Write DB → invalidate cache
```
- Most common pattern
- Risk: cache stampede on miss (many requests hit DB simultaneously)
- Mitigation: mutex/lock on cache miss, or probabilistic early expiration

**Write-Through**
```
Write: Write cache → cache writes DB → return
Read: Always from cache (populated on write)
```
- Consistent cache+DB state
- Higher write latency (synchronous DB write)
- Good for read-heavy workloads with predictable writes

**Write-Behind (Write-Back)**
```
Write: Write cache → return immediately → async batch write to DB
```
- Lowest write latency
- Risk: data loss if cache node crashes before DB write
- Good for: analytics counters, session data, non-critical data

**Cache Stampede Prevention:**
- **Mutex:** First thread to miss acquires lock, others wait
- **Early recompute:** Refresh cache before TTL expires (probabilistic: each read has TTL_remaining/TTL chance of refresh)
- **Stale-while-revalidate:** Serve stale value while background refresh happens

---

## Step 4: Wrap-Up

### Bottlenecks and Scaling

| Component | Bottleneck | Mitigation |
|---|---|---|
| Single hot key | One node overwhelmed | Local L1 cache, key replication, read replicas |
| Network bandwidth | Large values saturate NIC | Compression, pagination for large values |
| Memory fragmentation | Long-running nodes waste memory | Jemalloc allocator, periodic restart with snapshot restore |
| Cluster rebalancing | Adding nodes triggers massive data migration | Slot-by-slot migration, throttled transfer |
| Thundering herd | Cache miss storm on popular key expiry | Mutex, stale-while-revalidate, jittered TTL |

### Failure Scenarios

1. **Node crash:** Followers promote to leader. Async replication means last few writes may be lost — acceptable for cache.
2. **Network partition:** Minority partition stops accepting writes (if using quorum). Majority partition continues.
3. **Memory OOM:** Eviction kicks in. If all keys are critical, scale horizontally (add nodes).
4. **Cascading failure:** Cache goes down → all traffic hits DB → DB overloaded. Mitigation: circuit breaker, rate limiting on DB, graceful degradation.

### 10x Scale Discussion

- **10x data:** Add more shards. Consistent hashing/hash slots make this smooth.
- **10x QPS:** Add read replicas per shard. Client-side L1 cache for ultra-hot keys.
- **Global distribution:** Cache clusters in each region. Cross-region invalidation via pub/sub or eventual consistency with conflict resolution.
- **Multi-tenancy:** Namespace isolation, per-tenant memory quotas, priority-based eviction (high-tier tenants protected).

### Redis vs Memcached (Common Interview Question)

| Feature | Redis | Memcached |
|---|---|---|
| Data structures | Strings, lists, sets, sorted sets, hashes, streams | Strings only |
| Persistence | RDB snapshots + AOF | None |
| Replication | Built-in leader-follower | None (client-side sharding only) |
| Clustering | Redis Cluster (hash slots) | Client-side consistent hashing |
| Threading | Single-threaded event loop (+ I/O threads in 6.0+) | Multi-threaded |
| Memory efficiency | Higher overhead per key | Lower overhead (slab allocator) |
| Use case | Feature-rich caching, pub/sub, streams | Simple high-throughput KV cache |

### Design Review Criteria

| Criterion | Key Signal |
|---|---|
| Requirements | Clarified: data model, scale, consistency, eviction, persistence |
| Partitioning | Consistent hashing or hash slots with clear tradeoff discussion |
| Eviction | LRU/LFU/TTL with implementation detail (not just "use LRU") |
| Replication | Leader-follower with failover strategy and split-brain prevention |
| Hot keys | Explicit solution (L1 cache, key replication, read replicas) |
| Cache patterns | Cache-aside vs write-through vs write-behind with stampede prevention |
| Failure handling | Graceful degradation, circuit breakers, thundering herd mitigation |

---

## Interview Tips

1. **Start with "What kind of cache?"** There's a big difference between a CDN cache, application-level cache, and database query cache. Clarify scope.
2. **The hot key problem is the #1 follow-up.** Every interviewer asks "what if one key gets 10x more traffic than others?" Have L1 cache + key replication ready.
3. **Cache stampede = instant credibility.** Mentioning mutex-based miss protection or stale-while-revalidate shows production experience.
4. **Don't say "just use Redis."** Interviewers want you to design Redis from scratch. Show the hash table, eviction algorithm, replication protocol.
5. **Consistency tradeoffs matter.** "Do we need read-your-writes? Can we tolerate stale reads?" This shows systems maturity.
