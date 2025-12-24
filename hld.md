# Quant Research Agent - High-Level Design

## **Architecture Patterns**

### **1. Microservices Architecture**
- Independent, loosely coupled services
- Each service owns its domain and data
- Services communicate via message queues and APIs
- Independent deployment and scaling

### **2. Event-Driven Architecture**
- Services communicate through events/messages
- Asynchronous processing via message queues
- Decoupled producers and consumers
- Enables parallel processing

### **3. Pipeline Architecture (ETL Pattern)**
- Linear flow: Discovery → Processing → Extraction → Synthesis → Digest
- Each stage transforms and enriches data
- Intermediate results cached between stages
- Clear separation of concerns per stage

### **4. Plugin Architecture**
- Source fetchers as pluggable components
- Easy to add new sources without changing core system
- Each plugin implements standard interface
- Fetchers can be enabled/disabled independently

### **5. API Gateway Pattern**
- Single entry point for external API calls (arXiv, Kaggle, etc.)
- Centralized rate limiting and retry logic
- Load balancing across providers
- Circuit breaker for failing APIs

### **6. Orchestration Pattern**
- Airflow DAGs coordinate workflow execution
- Manages dependencies between services
- Handles scheduling (daily runs + on-demand)
- Provides workflow visibility and monitoring

### **7. Intelligent Routing Pattern**
- LLM Router selects best model for each task
- Cost-aware and capability-aware routing
- Abstraction layer over multiple LLM providers
- Failover and rate limit management

### **8. CQRS-Inspired Pattern**
- Separate services for querying (Search) vs writing (Deduplication)
- Both operate on same data store but optimized for different use cases
- Search: Complex queries, ranking, filtering
- Deduplication: Fast similarity checks, threshold-based matching

---

## **System Components**

### **Core Services**

#### **1. Orchestration Service (Airflow)**
**Responsibility:** Coordinate entire workflow, manage scheduling, handle dependencies

**Functions:**
- Schedule daily digest generation (configurable interval)
- Trigger on-demand digest generation
- Manage service dependencies (ensure fetchers complete before processing)
- Monitor workflow health
- Handle retries at workflow level
- Provide workflow visualization

**Interfaces:**
- Dashboard triggers manual runs via API
- Schedules automatic daily runs
- Monitors all downstream services

---

#### **2. Source Fetcher Services (Plugin Architecture)**

**Base Plugin Interface:**
```python
class SourceFetcher:
    def fetch() -> List[RawContent]
    def health_check() -> bool
    def get_config() -> FetcherConfig
```

---

**2a. arXiv/SSRN Fetcher**

**Responsibility:** Discover academic papers using hybrid query + category monitoring

**Functions:**
- Generate search queries via LLM (70% targeted, 30% exploratory)
- Monitor specific categories (cs.LG, stat.ML, q-fin.TR, stat.AP)
- Fetch recent papers from categories (last 30 days)
- Execute query-based searches via arXiv API
- Return: paper metadata (title, abstract, URL, authors, date)

**Strategy:**
- Query-based: LLM generates 5-10 unique daily queries
- Category monitoring: Pull top 20 recent papers per category
- No duplicate queries (maintains query history)

**Output:** List of paper metadata objects → Message Queue

---

**2b. Kaggle Fetcher**

**Responsibility:** Discover winning notebooks and techniques from competitions

**Functions:**
- Monitor active/completed competitions in relevant categories
- Fetch top 10 notebooks per competition (sorted by medals/votes)
- Search notebooks by tags (time-series, forecasting, feature-engineering)
- Filter for tabular and time-series competitions
- Return: notebook metadata (title, URL, competition, tags, votes)

**Strategy:**
- Competition exploration (Strategy 1)
- Topic-based search (Strategy 2)
- Prioritize gold/silver/bronze medal notebooks

**Output:** List of notebook metadata → Message Queue

---

**2c. HuggingFace Fetcher**

**Responsibility:** Discover model architectures and implementations

**Functions:**
- Search models by task (time-series-forecasting, tabular-classification)
- Fetch trending/most-downloaded models weekly
- Link paper implementations (when arXiv paper found, search for HF implementation)
- Extract model cards and architecture details
- Return: model metadata (title, URL, task, architecture, paper link)

**Strategy:**
- Model card exploration (Strategy 1)
- Paper-to-implementation linking (Strategy 2)
- Trending models (Strategy 3)

**Output:** List of model metadata → Message Queue

---

**2d. Web Search Fetcher**

**Responsibility:** Discover blog posts, forums, Medium articles via novel searches

**Functions:**
- LLM generates 10 unique search queries daily (50% exploitation, 50% exploration)
- Execute searches via Google Search API / Serper API
- Prioritize: Medium, QuantConnect forums, researcher blogs, r/algotrading
- Filter out: news sites, commercial content, low-quality forums
- Return: article metadata (title, URL, source, snippet)

**Strategy:**
- Novel LLM-generated queries (Strategy 1)
- Adaptive searches based on feedback (Strategy 3)
- Topic clustering (Core + Adjacent + Exploratory)

**Output:** List of article metadata → Message Queue

---

**Fetcher Coordination:**
- All fetchers run in parallel
- Each publishes to dedicated message queue topic
- Airflow monitors completion of all fetchers
- If fetcher fails: log error, continue with other sources
- Results aggregated before moving to processing stage

---

#### **3. API Gateway Service**

**Responsibility:** Centralized external API management with rate limiting

**Functions:**
- Proxy all external API calls (arXiv, Kaggle, HuggingFace, Google Search)
- Enforce rate limits per provider (avoid 429 errors)
- Implement retry logic with exponential backoff
- Circuit breaker for failing APIs (skip after N failures)
- Track API usage and costs
- Load balance across multiple API keys (if available)

**Rate Limiting Strategy:**
- Per-provider limits (e.g., arXiv: 3 req/sec, Google: 100/day)
- Shared quota across fetchers
- Queue requests if limit exceeded

**Retry Logic:**
- 3 retries with exponential backoff
- 429 (rate limit) → backoff and retry
- 5xx (server error) → retry
- 4xx (client error) → fail immediately

**Output:** Successful API responses or errors → Calling fetchers

---

#### **4. Deduplication Service**

**Responsibility:** Prevent duplicate content from appearing in digests

**Functions:**
- Generate embeddings for incoming content (title + abstract/summary)
- Perform similarity search against vector DB
- Flag duplicates (cosine similarity > 0.85 threshold)
- Store embeddings of new content
- Maintain deduplication index

**Flow:**
1. Receive content from processing stage
2. Generate embedding via LLM Router
3. Query vector DB for similar items (k-NN search)
4. If similarity > threshold → mark as duplicate, skip
5. If unique → store embedding, pass to extraction

**Performance:**
- Batch embedding generation (process 50 items at once)
- Cache embeddings to avoid regeneration
- Async processing (doesn't block pipeline)

**Output:** Unique content only → Extraction Service

---

#### **5. Intelligence Layer**

**5a. Extraction Service**

**Responsibility:** Extract actionable insights from raw content using LLM

**Functions:**
- Parse raw content (papers, notebooks, articles)
- Generate structured extractions via LLM:
  - Key methodology insights
  - Core techniques/algorithms
  - Code/pseudocode snippets
  - Actionability assessment (can this be used in quant research?)
- Quality filtering: Score based on actionability (0-1)
- Filter out: purely theoretical, non-actionable content

**LLM Prompt Strategy:**
```
Extract from this [paper/notebook/article]:
1. Core technique/methodology
2. Algorithm or logic (pseudocode if possible)
3. How this could apply to:
   - Feature engineering for time series
   - Data exploration techniques
   - Model architecture ideas
   - Optimization methods
4. Actionability score (0-1): Can this be implemented in quant research?

Only include if score > 0.6
```

**Output:** Structured extractions (JSON) → Message Queue → Synthesis Service

---

**5b. Synthesis Service**

**Responsibility:** Combine all extracted insights into cohesive digest with categorization

**Functions:**
- Aggregate extractions from all sources
- LLM-based dynamic categorization:
  - Analyze content and assign to categories
  - Categories: Feature Engineering, Model Architecture, Optimization, Data Exploration, etc.
  - Can create new categories if content doesn't fit existing
- Generate "application ideas" per item (multiple ways to use in research)
- Rank items by relevance (if learning model available)
- Format digest structure

**Categorization Prompt:**
```
Given these extracted insights, categorize each into:
- Feature Engineering
- Model Architecture
- Optimization Techniques
- Data Exploration
- Statistical Methods
- Time Series Analysis
- [Or suggest new category if doesn't fit]

For each item, generate 2-3 specific application ideas for MFT futures trading research.
```

**Output:** Categorized digest items (JSON) → Digest Generation Service

---

#### **6. Digest Generation Service**

**Responsibility:** Compile final digest and deliver to user

**Functions:**
- Receive categorized items from Synthesis Service
- Apply item limit (10-15 items, configurable)
- Generate digest format (email HTML or dashboard JSON)
- Store digest in database (metadata + items)
- Trigger delivery (email or dashboard update)
- Log generation metrics

**Digest Format:**
```
## [Category Name]

### [Item Title]
**Source:** [Link]
**Key Insights:** [Extracted methodology]
**Code/Logic:** [Snippets]
**Application Ideas:**
- [Idea 1: Feature engineering application]
- [Idea 2: Model optimization application]
- [Idea 3: Data exploration application]
```

**Delivery:**
- Email: Send HTML digest via SMTP
- Dashboard: Update latest digest endpoint
- Notification: Alert user of new digest

**Output:** Stored digest + delivered to user

---

#### **7. Search Service**

**Responsibility:** Semantic search over historical digests for user queries

**Functions:**
- Accept search queries from dashboard
- Generate query embedding
- Perform vector similarity search (k-NN)
- Rank results by relevance
- Filter by date range, category, source (optional)
- Return digest items with metadata

**API Endpoints:**
- `POST /search` - Semantic search over all digests
  - Input: query text, filters (date, category), limit
  - Output: ranked list of digest items
- `GET /digest/{id}` - Retrieve specific digest
- `GET /digests/recent` - List recent digests (pagination)

**Search Strategy:**
- Generate embedding for user query
- Cosine similarity against all stored item embeddings
- Hybrid search: combine vector similarity + keyword matching (full-text)
- Boost recent items slightly

**Output:** Ranked search results → Dashboard

---

#### **8. Feedback Service**

**Responsibility:** Collect and store user feedback for reinforcement learning

**Functions:**
- Receive ratings from dashboard (1-5 stars or thumbs up/down)
- Store "implemented" flags for items
- Store timestamps and user notes
- Aggregate feedback metrics (avg rating per category, source, etc.)
- Trigger learning service retraining when threshold reached

**API Endpoints:**
- `POST /feedback` - Submit rating for digest item
  - Input: item_id, rating, implemented (bool), notes
- `POST /feedback/batch` - Submit multiple ratings at once
- `GET /feedback/stats` - Get aggregated feedback statistics

**Retraining Trigger:**
- Collect feedback until threshold (e.g., 100 ratings)
- Trigger learning service to retrain model
- Reset counter after training

**Output:** Stored feedback → Database, trigger → Learning Service

---

#### **9. Learning Service**

**Responsibility:** Train and maintain recommendation model for personalization

**Functions:**
- Collect training data from feedback table
- Train preference model (Option A: simple statistical tracking initially)
- Calculate:
  - Category preferences (avg rating per category)
  - Source preferences (avg rating per source)
  - Topic preferences (via content embeddings + ratings)
  - Search query effectiveness
- Generate feature importance scores
- Store model state and weights
- Provide scoring API for digest generation

**Training Process (Option A - Simple):**
```python
category_scores = feedback.groupby('category').mean('rating')
source_scores = feedback.groupby('source').mean('rating')
topic_embeddings = aggregate(item_embeddings, weights=ratings)
```

**Model Evolution:**
- Phase 1 (0-100 ratings): Pure data collection, no filtering
- Phase 2 (100-500 ratings): Simple preference tracking (Option A)
- Phase 3 (500+ ratings): ML-based personalization (train regression model)

**API Endpoints:**
- `POST /train` - Trigger model retraining
- `POST /score` - Score content items for relevance
  - Input: list of content items
  - Output: relevance scores (0-1)
- `GET /preferences` - Get current user preferences

**Output:** 
- Influence search query generation (via API to fetchers)
- Score items during synthesis (boost high-relevance items)

---

#### **10. LLM Router Service**

**Responsibility:** Abstract LLM providers and route requests optimally

**Functions:**
- Maintain registry of available LLM providers (Anthropic, OpenAI, etc.)
- Route requests based on task requirements:
  - Extraction: Claude Sonnet (high quality)
  - Categorization: Claude Sonnet
  - Query generation: Claude Haiku (fast, cheap)
  - Embeddings: OpenAI text-embedding-3-small (cost-effective)
- Track costs and rate limits per provider
- Implement failover (if Claude unavailable → OpenAI)
- Circuit breaker: shut down if cost cap exceeded

**Routing Logic:**
```python
task_to_model = {
    'extraction': 'claude-sonnet-4',
    'synthesis': 'claude-sonnet-4', 
    'query_generation': 'claude-haiku',
    'categorization': 'claude-sonnet-4',
    'embeddings': 'openai-text-embedding-3-small'
}
```

**Cost Management:**
- Track daily spend per provider
- Alert at 80% of budget
- Auto-pause at 100% budget (resume next day or manual override)
- Dashboard shows cost metrics

**API:**
- Unified interface: `llm_router.complete(prompt, task_type)`
- Returns: LLM response + metadata (model used, cost, latency)

**Output:** LLM responses → Calling services

---

### **Supporting Services**

#### **11. Dashboard Service (Streamlit)**

**Responsibility:** Simple web interface for feedback and search

**Features:**
- **View Latest Digest:** Display most recent digest items
- **Rate Items:** Submit ratings (1-5 stars), mark as implemented
- **Batch Feedback Submission:** Rate multiple items, click "Submit All"
- **Search Historical Digests:** Semantic search interface
- **Manual Controls:**
  - Trigger digest generation on-demand
  - Pause/resume specific fetchers
  - Adjust filtering parameters (item limit, quality threshold)
  - View system health (last successful run, errors)
- **Analytics:**
  - Feedback statistics (avg rating by category)
  - Source effectiveness
  - Cost tracking

**API Consumption:**
- Calls Search Service for queries
- Calls Feedback Service for ratings
- Calls Digest Generation Service for manual triggers
- Calls Orchestration Service for fetcher controls

**Tech Stack:** Streamlit (Python), hosted in Docker container

---

#### **12. Observability Service**

**Responsibility:** Centralized logging and monitoring

**Components:**

**12a. Application Logging**
- Structured logs (JSON format)
- Log aggregation via centralized log file or ELK stack (optional)
- Log levels: DEBUG, INFO, WARNING, ERROR
- Each service logs: request_id, timestamp, service_name, event

**12b. LangSmith Integration**
- Track LLM calls and workflow execution
- Visualize agent decision-making
- Debug LLM prompt/response pairs
- Monitor LangGraph state transitions
- Cost tracking per LLM call

**12c. Health Monitoring**
- Dashboard endpoint: `/health` per service
- Track last successful run timestamp
- Email alerts on failures (via SMTP)
- Error rate tracking

**Output:** Logs → Files, Traces → LangSmith

---

### **Data Storage**

#### **13. PostgreSQL Database (with pgvector)**

**Schema:**

```sql
-- Digests
digests
  - digest_id (PK)
  - generated_at (timestamp)
  - item_count (int)
  - delivery_status (enum: sent, failed)
  - source_breakdown (jsonb)

-- Digest Items
digest_items
  - item_id (PK)
  - digest_id (FK)
  - source (enum: arxiv, kaggle, huggingface, web)
  - source_url (text)
  - title (text)
  - category (text)
  - summary (text)
  - key_insights (text)
  - code_snippets (text)
  - application_ideas (jsonb)
  - embedding (vector(1536))
  - created_at (timestamp)

-- Feedback
feedback
  - feedback_id (PK)
  - item_id (FK)
  - rating (int, 1-5)
  - implemented (boolean)
  - notes (text)
  - submitted_at (timestamp)

-- System State
system_state
  - key (text, PK)
  - value (jsonb)
  - updated_at (timestamp)
  
-- Fetcher State
fetcher_state
  - fetcher_name (text, PK)
  - last_fetch_time (timestamp)
  - status (enum: active, paused, error)
  - error_count (int)
  - config (jsonb)

-- Search Query History
search_queries
  - query_id (PK)
  - source (text)
  - query_text (text)
  - executed_at (timestamp)
  - results_count (int)

-- Learning Model Metadata
model_metadata
  - model_id (PK)
  - version (text)
  - trained_at (timestamp)
  - training_samples (int)
  - performance_metrics (jsonb)
  - file_path (text)

-- Preference Weights
preference_weights
  - dimension (text, PK, e.g., 'category:feature_engineering')
  - weight (float)
  - updated_at (timestamp)
```

**Indexes:**
- Vector index on `digest_items.embedding` (HNSW)
- Full-text index on `digest_items.title`, `summary`
- Time-based index on `digests.generated_at`
- Foreign key indexes

---

#### **14. Message Queue (RabbitMQ or Redis Streams)**

**Topics/Queues:**
- `content.discovered` - Raw content from fetchers
- `content.deduplicated` - Unique content after deduplication
- `insights.extracted` - Extracted insights from Intelligence Layer
- `digest.ready` - Synthesized digest ready for generation
- `feedback.submitted` - User feedback events
- `training.trigger` - Trigger learning service retraining

**Purpose:**
- Decouple services (async communication)
- Handle backpressure (if extraction is slow, queue buffers)
- Enable parallel processing
- Retry failed messages
- Dead letter queue for failed processing

---

## **Data Flow Through System**

### **Daily Digest Generation Flow**

```
┌─────────────────────────────────────────────────────────────────┐
│                      1. ORCHESTRATION                           │
│  Airflow DAG triggers at scheduled time (e.g., 3 AM daily)     │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   2. DISCOVERY PHASE (Parallel)                 │
│                                                                   │
│  ┌────────────────┐  ┌─────────────┐  ┌──────────────┐         │
│  │ arXiv Fetcher  │  │   Kaggle    │  │ HuggingFace  │         │
│  │                │  │   Fetcher   │  │   Fetcher    │         │
│  │ - Query search │  │ - Comp win  │  │ - Models     │         │
│  │ - Categories   │  │ - Tag search│  │ - Trending   │         │
│  └───────┬────────┘  └──────┬──────┘  └──────┬───────┘         │
│          │                  │                 │                  │
│  ┌───────┴──────────────────┴─────────────────┴───────┐         │
│  │              API Gateway                            │         │
│  │  - Rate limiting                                    │         │
│  │  - Retry logic                                      │         │
│  │  - Circuit breaker                                  │         │
│  └───────┬─────────────────────────────────────────────┘         │
│          │                                                        │
│  ┌───────┴──────┐                                                │
│  │ Web Search   │                                                │
│  │ Fetcher      │                                                │
│  │ - LLM queries│                                                │
│  │ - Adaptive   │                                                │
│  └───────┬──────┘                                                │
└──────────┼───────────────────────────────────────────────────────┘
           │
           ▼ (All fetchers publish to message queue)
┌─────────────────────────────────────────────────────────────────┐
│                   Message Queue: content.discovered              │
│  Raw content from all sources (papers, notebooks, articles)     │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   3. DEDUPLICATION PHASE                         │
│                                                                   │
│  ┌─────────────────────────────────────────────────┐            │
│  │  Deduplication Service                          │            │
│  │  1. Receive raw content                         │            │
│  │  2. Generate embedding via LLM Router           │            │
│  │  3. Query vector DB for similar items           │            │
│  │  4. If similarity > 0.85 → mark duplicate       │            │
│  │  5. If unique → store embedding, pass forward   │            │
│  └────────────┬────────────────────────────────────┘            │
│               │                                                   │
│               ▼                                                   │
│       Vector DB (pgvector) - Deduplication Index                │
└────────────┬──────────────────────────────────────────────────────┘
             │
             ▼ (Unique content only)
┌─────────────────────────────────────────────────────────────────┐
│                   Message Queue: content.deduplicated            │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   4. EXTRACTION PHASE                            │
│                                                                   │
│  ┌─────────────────────────────────────────────────┐            │
│  │  Extraction Service (Intelligence Layer)        │            │
│  │  1. Parse content (paper/notebook/article)      │            │
│  │  2. LLM extraction via Router:                  │            │
│  │     - Key methodology                           │            │
│  │     - Algorithms/techniques                     │            │
│  │     - Code/pseudocode                           │            │
│  │     - Actionability score (0-1)                 │            │
│  │  3. Filter: Keep only if score > 0.6            │            │
│  └────────────┬────────────────────────────────────┘            │
│               │                                                   │
│               ▼                                                   │
│       LLM Router (calls Claude Sonnet)                           │
└────────────┬──────────────────────────────────────────────────────┘
             │
             ▼ (Structured extractions)
┌─────────────────────────────────────────────────────────────────┐
│                   Message Queue: insights.extracted              │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   5. SYNTHESIS PHASE                             │
│                                                                   │
│  ┌─────────────────────────────────────────────────┐            │
│  │  Synthesis Service (Intelligence Layer)         │            │
│  │  1. Aggregate all extractions                   │            │
│  │  2. LLM-based categorization via Router:        │            │
│  │     - Assign to categories dynamically          │            │
│  │     - Generate application ideas (2-3 per item) │            │
│  │  3. Rank items (by learning model if available) │            │
│  │  4. Format digest structure                     │            │
│  └────────────┬────────────────────────────────────┘            │
│               │                                                   │
│               ▼                                                   │
│       LLM Router + Learning Service (scoring)                    │
└────────────┬──────────────────────────────────────────────────────┘
             │
             ▼ (Categorized, ranked items)
┌─────────────────────────────────────────────────────────────────┐
│                   Message Queue: digest.ready                    │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   6. DIGEST GENERATION PHASE                     │
│                                                                   │
│  ┌─────────────────────────────────────────────────┐            │
│  │  Digest Generation Service                      │            │
│  │  1. Receive categorized items                   │            │
│  │  2. Apply item limit (10-15 configurable)       │            │
│  │  3. Format digest (HTML for email, JSON for UI) │            │
│  │  4. Store in database                           │            │
│  │  5. Send email via SMTP                         │            │
│  │  6. Update dashboard endpoint                   │            │
│  └────────────┬────────────────────────────────────┘            │
└────────────┬──────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   PostgreSQL Database                            │
│  - Store digest metadata                                         │
│  - Store digest items with embeddings                           │
└─────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   7. DELIVERY                                    │
│  - Email sent to user (HTML digest)                             │
│  - Dashboard updated with new digest                            │
└─────────────────────────────────────────────────────────────────┘
```

---

### **User Feedback & Learning Loop**

```
┌─────────────────────────────────────────────────────────────────┐
│                   1. USER INTERACTION                            │
│  User reads digest, rates items, marks implemented              │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   2. FEEDBACK SUBMISSION                         │
│  Dashboard → Feedback Service API                               │
│  POST /feedback/batch                                           │
│    - item_id, rating, implemented, notes                        │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   3. FEEDBACK STORAGE                            │
│  Feedback Service stores in PostgreSQL                          │
│  Checks if retraining threshold reached (e.g., 100 ratings)     │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼ (If threshold reached)
┌─────────────────────────────────────────────────────────────────┐
│                   Message Queue: training.trigger                │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   4. MODEL TRAINING                              │
│  ┌─────────────────────────────────────────────────┐            │
│  │  Learning Service                               │            │
│  │  1. Fetch feedback data from PostgreSQL        │            │
│  │  2. Calculate preferences:                      │            │
│  │     - Category scores                           │            │
│  │     - Source scores                             │            │
│  │     - Topic embeddings                          │            │
│  │  3. Store preference weights                    │            │
│  │  4. Update model metadata                       │            │
│  └─────────────────────────────────────────────────┘            │
└────────────┬──────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   5. MODEL DEPLOYMENT                            │
│  Preferences stored in PostgreSQL                               │
│  Used in next digest generation cycle:                          │
│  - Influences search query generation (fetchers)                │
│  - Scores/ranks items during synthesis                          │
└─────────────────────────────────────────────────────────────────┘
```

---

### **Historical Search Flow**

```
┌─────────────────────────────────────────────────────────────────┐
│                   1. USER SEARCH                                 │
│  User enters query in Dashboard                                 │
│  "attention mechanisms for time series"                         │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   2. SEARCH REQUEST                              │
│  Dashboard → Search Service API                                 │
│  POST /search                                                   │
│    query: "attention mechanisms for time series"                │
│    filters: {date_range, category, source}                      │
│    limit: 20                                                    │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   3. EMBEDDING GENERATION                        │
│  Search Service → LLM Router                                    │
│  Generate embedding for query                                   │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   4. VECTOR SEARCH                               │
│  Search Service queries PostgreSQL (pgvector)                   │
│  - Cosine similarity against all item embeddings                │
│  - Apply filters (date, category, source)                       │
│  - Hybrid: vector similarity + full-text search                 │
│  - Rank results                                                 │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   5. RESULTS RETURNED                            │
│  Search Service → Dashboard                                     │
│  Returns: List of matching digest items with metadata           │
│  Dashboard displays results                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## **Service Communication Matrix**

| Service | Communicates With | Method | Purpose |
|---------|-------------------|--------|---------|
| Orchestration (Airflow) | All Fetchers | HTTP (trigger) | Start fetching |
| Fetchers | API Gateway | HTTP | External API calls |
| Fetchers | Message Queue | Publish | Send raw content |
| Deduplication | Message Queue | Subscribe/Publish | Receive content, send unique items |
| Deduplication | Vector DB | SQL | Similarity search |
| Deduplication | LLM Router | HTTP | Generate embeddings |
| Extraction | Message Queue | Subscribe/Publish | Receive unique content, send insights |
| Extraction | LLM Router | HTTP | Extract insights |
| Synthesis | Message Queue | Subscribe/Publish | Receive insights, send digest |
| Synthesis | LLM Router | HTTP | Categorize |
| Synthesis | Learning Service | HTTP | Score items |
| Digest Generation | Message Queue | Subscribe | Receive ready digest |
| Digest Generation | PostgreSQL | SQL | Store digest |
| Digest Generation | SMTP | Protocol | Send email |
| Dashboard | Search Service | HTTP API | Search queries |
| Dashboard | Feedback Service | HTTP API | Submit ratings |
| Dashboard | Digest Generation | HTTP API | Manual triggers |
| Feedback Service | PostgreSQL | SQL | Store feedback |
| Feedback Service | Message Queue | Publish | Trigger training |
| Learning Service | Message Queue | Subscribe | Training trigger |
| Learning Service | PostgreSQL | SQL | Read feedback, store model |
| Search Service | PostgreSQL | SQL | Query embeddings |
| Search Service | LLM Router | HTTP | Generate query embeddings |
| LLM Router | External LLM APIs | HTTP | Claude, OpenAI, etc. |

---

## **Technology Stack Summary**

### **Core Services**
- **Language:** Python 3.11+
- **Framework:** LangGraph (for orchestration within services), FastAPI (for APIs)
- **Orchestration:** Apache Airflow
- **Message Queue:** RabbitMQ or Redis Streams
- **Databases:** 
  - PostgreSQL 15+ with pgvector extension
- **LLM Providers:** Anthropic (Claude), OpenAI (embeddings)

### **Infrastructure**
- **Containerization:** Docker + Docker Compose
- **Deployment:** Container-based (DigitalOcean, AWS ECS, or local)
- **Web Server:** Uvicorn (ASGI)
- **Dashboard:** Streamlit

### **Observability**
- **Logging:** Python logging → JSON logs → Files
- **Tracing:** LangSmith (LLM call tracing)
- **Monitoring:** Custom health check endpoints
- **Alerting:** SMTP email alerts

### **External APIs**
- arXiv API
- Kaggle API (or web scraping)
- HuggingFace Hub API
- Google Search API / Serper API
- Anthropic API (Claude)
- OpenAI API (embeddings)

---

## **Deployment Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                       Docker Host                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Airflow     │  │  Fetchers    │  │ Deduplication│          │
│  │  Container   │  │  Container   │  │  Service     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Extraction  │  │  Synthesis   │  │  Digest Gen  │          │
│  │  Service     │  │  Service     │  │  Service     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Search      │  │  Feedback    │  │  Learning    │          │
│  │  Service     │  │  Service     │  │  Service     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  LLM Router  │  │  API Gateway │  │  Dashboard   │          │
│  │  Service     │  │  Service     │  │  (Streamlit) │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │  PostgreSQL  │  │  RabbitMQ    │                             │
│  │  (pgvector)  │  │              │                             │
│  └──────────────┘  └──────────────┘                             │
│                                                                   │
│  ┌─────────────────────────────────────────────────┐            │
│  │  Shared Volumes                                 │            │
│  │  - /logs (centralized logs)                     │            │
│  │  - /models (ML model weights)                   │            │
│  │  - /config (YAML configs)                       │            │
│  └─────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

---

## **Configuration Management**

**Config Structure:**
```yaml
# config/sources.yaml
sources:
  arxiv:
    enabled: true
    categories: ["cs.LG", "stat.ML", "q-fin.TR", "stat.AP"]
    queries_per_day: 5
    papers_per_query: 10
  
  kaggle:
    enabled: true
    competitions: true
    notebook_tags: ["time-series", "forecasting", "feature-engineering"]
  
  huggingface:
    enabled: true
    tasks: ["time-series-forecasting", "tabular-classification"]
  
  web_search:
    enabled: true
    queries_per_day: 10
    sources_priority: ["medium.com", "quantconnect.com", "reddit.com/r/algotrading"]

# config/llm.yaml
llm:
  providers:
    - name: anthropic
      api_key: ${ANTHROPIC_API_KEY}
      models:
        extraction: claude-sonnet-4
        synthesis: claude-sonnet-4
        query_generation: claude-haiku
      rate_limits:
        requests_per_minute: 50
        cost_cap_daily: 50.0
    
    - name: openai
      api_key: ${OPENAI_API_KEY}
      models:
        embeddings: text-embedding-3-small
      rate_limits:
        requests_per_minute: 3000
        cost_cap_daily: 10.0

# config/digest.yaml
digest:
  items_per_digest: 12
  quality_threshold: 0.6
  email:
    smtp_server: smtp.gmail.com
    smtp_port: 587
    from_address: ${EMAIL_FROM}
    to_address: ${EMAIL_TO}
  
# config/learning.yaml
learning:
  retraining_threshold: 100  # ratings before retraining
  similarity_threshold: 0.85  # deduplication
  
# config/airflow.yaml
scheduling:
  daily_digest_time: "03:00"  # 3 AM
  timezone: "America/Phoenix"
```

---

## **Error Handling & Resilience**

### **Fetcher Failures**
- If fetcher fails → log error, continue with other sources
- Circuit breaker: After 3 consecutive failures → pause fetcher for 1 hour
- Retry: 3 attempts with exponential backoff
- Dashboard shows fetcher health status

### **LLM Failures**
- LLM Router implements fallback: Claude unavailable → OpenAI
- Cost cap exceeded → pause system, send alert, require manual resume
- Rate limit hit → queue requests, process when available
- Timeout: 30s per LLM call, retry once

### **Database Failures**
- Connection pooling with retry
- Transaction rollback on failure
- Read replica for search (if scaling needed)
- Daily backups

### **Message Queue Failures**
- Dead letter queue for failed messages
- Retry failed messages 3 times
- Alert on persistent failures
- Manual replay capability

### **Digest Generation Failures**
- If < 5 items after filtering → send anyway with warning
- If email fails → retry 3 times, then store for dashboard access
- If entire pipeline fails → alert user, provide last successful digest link

---

## **Security Considerations**

- **API Keys:** Stored as environment variables, never in code
- **Database:** Password-protected, no public access
- **Dashboard:** Simple password auth (Streamlit secrets)
- **LLM Cost Controls:** Hard caps with auto-shutoff
- **Rate Limiting:** Centralized in API Gateway
- **Logs:** Sanitize sensitive data (API keys, passwords)