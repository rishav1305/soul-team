# Chapter 17: Design a Recommendation Engine

## Problem Statement

Design a recommendation system that surfaces personalized content to users — similar to Netflix's movie recommendations, Amazon's "Customers also bought," YouTube's video suggestions, or Spotify's Discover Weekly. The system must serve real-time recommendations at scale while continuously learning from user behavior.

---

## Step 1: Scope

### Clarifying Questions to Ask

1. **What are we recommending?** Products, videos, articles, music, people to follow?
2. **Scale?** How many users? How many items in the catalog? QPS for recommendation requests?
3. **Freshness?** How quickly should new items appear in recommendations? Real-time vs batch?
4. **Cold start?** How do we handle new users with no history? New items with no interactions?
5. **Context?** Should recommendations vary by time of day, device, location, session context?
6. **Diversity vs relevance?** How much exploration vs exploitation? Do we need to avoid filter bubbles?
7. **Feedback signals?** Explicit (ratings, likes) or implicit (clicks, watch time, dwell time, purchases)?
8. **Latency requirements?** How fast must recommendations render? P99 target?

### Typical Assumptions

- **DAU:** 100M users
- **Catalog:** 10M items
- **Recommendation requests:** 500M/day (users visit multiple pages)
- **Peak QPS:** ~20K
- **Latency:** P99 < 200ms for serving recommendations
- **Feedback signals:** Implicit (clicks, watch time, purchases, skips)
- **Model refresh:** Hourly for candidate generation, real-time for ranking
- **Cold start:** Must handle ~5% new users daily and ~1% new items daily

### Back-of-Envelope

```
Average QPS: 500M / 86,400 ≈ 5,800
Peak QPS: ~20K
User embedding dimension: 128 floats = 512 bytes
Item embedding storage: 10M * 512B = 5GB (fits in single machine)
User embedding storage: 100M * 512B = 50GB (fits in memory cluster)
Interaction events: 500M/day * 100B = 50GB/day raw events
Annual event storage: ~18TB
```

---

## Step 2: High-Level Design

The standard architecture is a **two-stage pipeline**: candidate generation (recall) → ranking (precision).

```
┌──────────┐     ┌───────────┐     ┌─────────────────┐     ┌──────────────┐
│   User    │────▶│ API Gateway│────▶│  Recommendation  │────▶│   Response   │
│  Request  │     │            │     │     Service      │     │  (Top-K items)│
└──────────┘     └───────────┘     └────────┬────────┘     └──────────────┘
                                            │
                              ┌─────────────┼──────────────┐
                              │             │              │
                    ┌─────────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐
                    │   Candidate    │ │  Ranker  │ │  Re-ranker │
                    │  Generation    │ │ (ML Model)│ │  (Business │
                    │ (Recall Stage) │ │          │ │   Rules)   │
                    └───────┬────────┘ └────┬─────┘ └────────────┘
                            │               │
                  ┌─────────┼────┐    ┌─────▼──────┐
                  │         │    │    │   Feature   │
            ┌─────▼───┐ ┌──▼──┐ │    │    Store    │
            │  ANN    │ │ CF  │ │    │ (User+Item  │
            │ Index   │ │     │ │    │  features)  │
            │(Embeddings)│    │ │    └────────────┘
            └─────────┘ └─────┘ │
                                │
                         ┌──────▼──────┐
                         │  Content-   │
                         │  Based      │
                         │  Filter     │
                         └─────────────┘
```

### Offline Pipeline (Batch)

```
┌──────────┐     ┌───────────┐     ┌──────────────┐     ┌─────────────┐
│  Event   │────▶│  Feature   │────▶│    Model     │────▶│  Embedding  │
│  Stream  │     │ Engineering│     │  Training    │     │   Store     │
│(Kafka/   │     │ Pipeline   │     │ (Daily/Hourly)│    │  (ANN Index)│
│ Kinesis) │     │            │     │              │     │             │
└──────────┘     └───────────┘     └──────────────┘     └─────────────┘
```

### Key Components

1. **Candidate Generation** — Fast recall of 100-1000 candidates from millions of items
   - Collaborative filtering (user-user, item-item)
   - Content-based filtering (item features → similarity)
   - ANN (approximate nearest neighbor) search on embeddings
   - Popular/trending items (fallback for cold start)

2. **Ranking** — ML model scores each candidate with full feature set
   - Deep learning model (Wide & Deep, DeepFM, DCN)
   - Features: user profile, item features, context, interaction history
   - Outputs: P(click), P(purchase), P(watch_complete), etc.

3. **Re-ranking** — Business logic layer
   - Diversity enforcement (don't show 5 action movies in a row)
   - Freshness boost (promote new items)
   - Fairness constraints (ensure representation)
   - Ad/promoted content insertion
   - Deduplication

4. **Feature Store** — Low-latency access to user and item features
   - Real-time features: recent clicks, session behavior
   - Batch features: user demographics, item popularity, historical CTR

---

## Step 3: Deep Dives

### Deep Dive 1: Candidate Generation Strategies

**Collaborative Filtering (CF)**
- **Item-based CF:** "Users who liked X also liked Y." Compute item-item similarity matrix offline.
  - Scalable: precompute top-K similar items per item
  - Limitation: cold start for new items
- **Matrix Factorization (ALS):** Decompose user-item interaction matrix into user and item embeddings
  - U(m x k) x V(k x n) ≈ R(m x n)
  - Train via Alternating Least Squares or SGD
  - Embeddings enable ANN search at serving time

**Two-Tower Model (Deep Retrieval) — Industry Standard 2026**
- User tower: encodes user features → user embedding
- Item tower: encodes item features → item embedding
- Trained to maximize dot product for positive pairs
- At serving time: user embedding → ANN search against item embeddings
- Used by YouTube, Instagram, Pinterest, TikTok

**ANN Index (Approximate Nearest Neighbors)**
- HNSW (Hierarchical Navigable Small World) — best recall/speed tradeoff
- ScaNN (Google) — optimized for large-scale retrieval
- FAISS (Meta) — GPU-accelerated, supports billion-scale
- Query: given user embedding, find top-K items in < 10ms
- Index refresh: hourly or on-demand when embeddings update

**Content-Based Filtering**
- Use item metadata (genre, tags, description) to find similar items
- Useful for cold start: new items have metadata even without interactions
- Text embeddings (BERT/sentence-transformers) for unstructured descriptions

### Deep Dive 2: Ranking Model Architecture

**Wide & Deep (Google, 2016)**
```
Wide component: Cross-product features (memorization)
  → Linear model on hand-crafted feature crosses

Deep component: Embedding + DNN (generalization)
  → Categorical features → embeddings → concat → DNN layers

Output: sigmoid(wide + deep) → P(click)
```

**Feature Categories for Ranking:**

| Category | Examples | Storage |
|---|---|---|
| User features | age, gender, country, account_age, subscription_tier | Feature Store (batch) |
| Item features | category, price, avg_rating, publish_date, duration | Feature Store (batch) |
| Interaction features | user_click_count_7d, user_genre_affinity, item_CTR_24h | Feature Store (near real-time) |
| Context features | time_of_day, device, session_length, previous_item_viewed | Request context |
| Cross features | user_genre_affinity x item_genre, user_price_range x item_price | Computed at serving |

**Multi-Objective Ranking:**
- Optimize for multiple objectives: P(click) x w1 + P(purchase) x w2 + P(watch_complete) x w3
- Weights tuned to balance engagement vs revenue vs user satisfaction
- Use multi-task learning: shared bottom layers, task-specific heads

### Deep Dive 3: Cold Start Problem

**New User (no interaction history):**
1. **Popularity-based fallback:** Show globally trending items
2. **Demographic-based:** Use age, location, device to find similar users
3. **Onboarding survey:** Ask preferences explicitly (Netflix genre selection)
4. **Exploration:** Use epsilon-greedy or Thompson sampling to try diverse items
5. **Contextual bandits:** Optimize exploration-exploitation with real-time feedback

**New Item (no interaction data):**
1. **Content-based:** Use item metadata and text embeddings for similarity
2. **Boosted exploration:** Guarantee impressions for new items in first 24-48h
3. **Transfer learning:** If item has a category, borrow category-level CTR as prior
4. **Hybrid:** Blend content-based scores with CF scores as interactions accumulate

### Deep Dive 4: Real-Time Personalization

**Event Stream Architecture:**
```
User Action → Kafka → Stream Processor (Flink/Spark Streaming)
                         │
                    ┌────┼────┐
                    │    │    │
              ┌─────▼┐ ┌▼───┐ ┌▼─────────┐
              │Update│ │Log │ │Update     │
              │Feature│ │to  │ │Session    │
              │Store │ │Lake│ │Context    │
              └──────┘ └────┘ └───────────┘
```

- **Session-aware ranking:** Boost items related to what user is currently browsing
- **Real-time feature updates:** "User clicked on 3 horror movies in this session" → update genre affinity in real-time
- **Streaming model updates:** Use online learning or frequent micro-batch retraining

### Deep Dive 5: Evaluation and A/B Testing

**Offline Metrics:**
- **Recall@K:** Of all relevant items, how many are in top-K recommendations?
- **NDCG@K:** Are the best items ranked highest?
- **Hit Rate:** Does the user interact with at least 1 recommended item?
- **Diversity:** Average pairwise distance between recommended items
- **Coverage:** What % of the catalog is ever recommended?

**Online Metrics (A/B Test):**
- **CTR:** Click-through rate on recommendations
- **Engagement:** Watch time, session length, pages per session
- **Conversion:** Purchase rate, subscription rate
- **Long-term retention:** 7-day, 30-day return rate (guards against engagement hacking)

**A/B Testing Pitfalls:**
- **Novelty effect:** New recommendations get attention just for being different
- **Primacy bias:** Position 1 always gets more clicks regardless of relevance
- **Network effects:** User A's behavior changes User B's recommendations
- **Solution:** Use interleaving experiments (blend control/treatment results in same list) for faster convergence

---

## Step 4: Wrap-Up

### Bottlenecks and Scaling

| Component | Bottleneck | Mitigation |
|---|---|---|
| ANN Index | Memory for 10M+ embeddings | Sharding by item category, distributed FAISS |
| Feature Store | P99 latency under load | Redis cluster with read replicas, pre-computed features |
| Ranking Model | GPU inference at 20K QPS | Model distillation, batched inference, TensorRT |
| Event Pipeline | 500M events/day throughput | Kafka partitioning, Flink auto-scaling |
| Training Pipeline | Daily retraining on TB-scale data | Distributed training (Horovod/DeepSpeed), incremental updates |

### Failure Scenarios

1. **ANN index stale:** Fallback to popularity-based recommendations
2. **Feature store down:** Serve with default/cached features (graceful degradation)
3. **Ranking model timeout:** Return candidate generation results without ranking (still better than nothing)
4. **Event pipeline lag:** Real-time features stale → session recommendations less personalized (acceptable)

### 10x Scale Discussion

- Move from single ANN index to distributed index (sharded by category or locality-sensitive hash)
- Model serving: batch inference for less-active users (precompute and cache), real-time only for active users
- Feature store: move from Redis to ScyllaDB for cost at scale
- Training: move to streaming/online learning to reduce retraining cost

### Design Review Criteria

| Criterion | Key Signal |
|---|---|
| Requirements | Clarified: item type, scale, latency, cold start, diversity |
| Architecture | Two-stage pipeline (recall → rank), offline + online paths |
| Candidate Generation | Multiple retrieval strategies (CF + content + embeddings + ANN) |
| Ranking | Feature-rich ML model, multi-objective optimization |
| Cold Start | Explicit strategy for new users AND new items |
| Real-time | Session-aware features, streaming event pipeline |
| Evaluation | Offline metrics + online A/B testing, long-term retention |
| Tradeoffs | Latency vs model complexity, diversity vs relevance, exploration vs exploitation |

---

## Interview Tips

1. **Don't jump to models.** Spend 5+ minutes on scope and requirements. "What signals do we have?" matters more than "which algorithm."
2. **The two-stage pipeline is non-negotiable.** You cannot rank millions of items with a complex model. Recall first, then rank.
3. **Cold start is the interviewer's favorite follow-up.** Have a clear strategy for both new users and new items.
4. **Mention evaluation.** Most candidates forget metrics. Bringing up NDCG, interleaving experiments, and long-term retention shows maturity.
5. **Draw the offline pipeline.** Training data → feature engineering → model training → embedding store → ANN index. This shows you understand the full lifecycle, not just serving.
