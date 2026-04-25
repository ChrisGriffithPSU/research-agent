# Automated Quant Research System — Architecture Spec

## 1. System Overview

Three parallel autonomous processes share a common infrastructure layer and converge on a **Feature Idea Store**. Promising results surface to the researcher via Slack. Process 1 is largely built; Processes 2 and 3 are greenfield but reuse the same worker/message-bus/database patterns.

```
┌──────────────────────────────────┐  ┌──────────────────────────────────┐  ┌──────────────────────────┐
│  PROCESS 1: ArXiv Pipeline       │  │  PROCESS 2: DGP Research         │  │  PROCESS 3: Genetic Prog │
│  24/7 continuous                 │  │  24/7 continuous                 │  │  Daily @ market close    │
│                                  │  │                                  │  │                          │
│  ArXiv Fetcher (cron)            │  │  DGP Orchestrator (tree mgr)     │  │  Primitive Harvester     │
│  → PDF Parser                    │  │  → Structural Reader (×N)        │  │  → GP Runner             │
│  → Concept Generator             │  │  → DGP Interpreter               │  │                          │
│  → Experiment Exploder           │  │  → Hypothesis Validator (×N)     │  │                          │
│  → Code Executor                 │  │  → DGP Synthesizer (periodic)    │  │                          │
│  → Experiment Evaluator          │  │                                  │  │                          │
│  → Obsidian Writer               │  │                                  │  │                          │
└──────────────────┬───────────────┘  └───────────────┬──────────────────┘  └────────────┬─────────────┘
                   │                                  │                                  │
                   └──────────────────────────────────┴──────────────────────────────────┘
                                                      │
                                          ┌───────────▼────────────┐
                                          │   Feature Idea Store   │
                                          │   PostgreSQL + Obsidian│
                                          └───────────┬────────────┘
                                                      │
                                          ┌───────────▼────────────┐
                                          │   Slack Alerting       │
                                          │   EOD Digest           │
                                          │   Research Alert       │
                                          └────────────────────────┘
```

---

## 2. Shared Infrastructure

### 2.1 Services

| Service | Image | Port(s) | Purpose |
|---------|-------|---------|---------|
| PostgreSQL | `pgvector/pgvector:pg15` | 5432 | Persistent state, embeddings, research tree |
| RabbitMQ | `rabbitmq:3.12-management-alpine` | 5672 / 15672 | Message bus between all workers |
| Artifact Store | Local filesystem (S3-swappable) | — | Code files, plots, reports, execution outputs |
| LLM Gateway | OpenAI-compatible endpoint | configured | All LLM calls; per-worker model overrides |

### 2.2 RabbitMQ Exchange Topology

All messages use a single **topic exchange** named `researcher.topic`. Queues bind to routing key patterns. This allows multiple consumers to subscribe to the same message (e.g., notifier + obsidian writer both consuming evaluation results).

```
Exchange: researcher.topic (type: topic, durable: true)

Routing Key Pattern         → Queue Name                    Bound Workers
─────────────────────────────────────────────────────────────────────────
paper.triage.#              → paper.triage.request          ArXivFetcher → PaperTriageAgent
paper.fulltext.#            → paper.fulltext.request        PDFParser
paper.concepts.#            → paper.concepts.request        ConceptGenerator
concepts.generated          → plan.generate.request         ExperimentExploder
plan.generated              → plan.generated                CodeExecutor
experiment.evaluation.#     → experiment.evaluation.request ExperimentEvaluator
feature.idea.created        → feature.idea.created          ObsidianWriter, Notifier
notify.send                 → notify.send                   SlackNotifier

dgp.characterize.#          → dgp.characterize.request      StructuralReader
dgp.fingerprint.generated   → dgp.fingerprint.generated     DGPInterpreter
dgp.validate.#              → dgp.validate.request          HypothesisValidator
dgp.validation.result       → dgp.validation.result         DGPOrchestrator
dgp.synthesize.trigger      → dgp.synthesize.trigger        DGPSynthesizer

gp.session.trigger          → gp.session.trigger            GPPrimitiveHarvester
gp.primitives.ready         → gp.primitives.ready           GPRunner
```

Dead-letter queues: every queue declares `x-dead-letter-exchange: researcher.dlx` and `x-dead-letter-routing-key: dlq.{original_queue}`. DLQ messages are logged and held for inspection.

### 2.3 PostgreSQL Schema (Complete DDL)

All tables live in the `public` schema. Run via Alembic migrations.

#### Existing Tables (unchanged)

```sql
-- paper dedup tracking
CREATE TABLE papers (
    paper_id    TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'fetched',
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- raw sources with vector embeddings
CREATE TABLE sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     TEXT NOT NULL,
    url             TEXT UNIQUE,
    title           TEXT,
    content         TEXT,
    extracted_data  JSONB,
    metadata        JSONB,
    embedding       vector(1536),
    status          TEXT DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX sources_embedding_idx ON sources USING hnsw (embedding vector_cosine_ops);
```

#### New Tables (migration: `20250425_feature_store_and_dgp.py`)

```sql
-- ─── Feature Idea Store ───────────────────────────────────────────────────────

CREATE TABLE feature_ideas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_process  TEXT NOT NULL CHECK (source_process IN ('arxiv', 'dgp', 'gp')),
    source_ref      TEXT,               -- work_id, dgp thread_id, or gp_run_id
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    -- binary promising flag: set by metrics check, not agent judgment
    is_promising    BOOLEAN NOT NULL DEFAULT false,
    -- structured evidence: what metrics passed what thresholds
    evidence        JSONB NOT NULL DEFAULT '{}',
    tags            TEXT[] DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'promoted', 'killed', 'needs_more')),
    obsidian_path   TEXT,               -- vault-relative path, set by ObsidianWriter
    embedding       vector(1536),       -- for dedup via cosine similarity
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX feature_ideas_embedding_idx
    ON feature_ideas USING hnsw (embedding vector_cosine_ops);
CREATE INDEX feature_ideas_promising_idx
    ON feature_ideas (is_promising, created_at DESC);

-- ─── DGP Research Tree ────────────────────────────────────────────────────────

CREATE TABLE dgp_findings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id       UUID NOT NULL,          -- top-level research tree ID
    parent_id       UUID REFERENCES dgp_findings(id) ON DELETE SET NULL,
    instrument      TEXT NOT NULL,
    data_slice      JSONB NOT NULL,         -- see §5.2 DataSlice schema
    phase           TEXT NOT NULL CHECK (phase IN ('characterization','interpretation','validation')),
    fingerprint     JSONB,                  -- StructuralFingerprint JSON, set in phase 1
    dgp_hypothesis  TEXT,                   -- prose hypothesis, set in phase 2
    test_spec       JSONB,                  -- discriminating test specification
    findings        TEXT,                   -- prose findings from phase 3
    metrics         JSONB DEFAULT '{}',     -- raw statistical test results
    open_questions  JSONB DEFAULT '[]',     -- follow-on questions generated
    is_significant  BOOLEAN,               -- did metrics pass significance threshold?
    depth           INT NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','running','exhausted','promoted','killed')),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX dgp_findings_thread_idx ON dgp_findings (thread_id, depth);
CREATE INDEX dgp_findings_open_idx ON dgp_findings (status, is_significant);

CREATE TABLE dgp_research_queue (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_finding_id   UUID REFERENCES dgp_findings(id) ON DELETE CASCADE,
    question_type       TEXT NOT NULL CHECK (question_type IN ('seed','frontier','novel','depth')),
    question            TEXT NOT NULL,
    instrument          TEXT NOT NULL,
    data_slice          JSONB NOT NULL,
    priority            FLOAT NOT NULL DEFAULT 0.5,  -- 0.0–1.0, higher = dispatch sooner
    status              TEXT NOT NULL DEFAULT 'queued'
                            CHECK (status IN ('queued','dispatched','done','pruned')),
    created_at          TIMESTAMPTZ DEFAULT now(),
    dispatched_at       TIMESTAMPTZ
);
CREATE INDEX dgp_queue_priority_idx
    ON dgp_research_queue (status, priority DESC, created_at);

-- ─── Genetic Programming ──────────────────────────────────────────────────────

CREATE TABLE gp_primitives (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,          -- e.g. 'log_return', 'ema_ratio'
    expression      TEXT NOT NULL,          -- symbolic form: 'log(close_t / close_{t-1})'
    primitive_type  TEXT NOT NULL CHECK (primitive_type IN ('terminal','function')),
    time_scale      TEXT,                   -- '1m', '5m', 'daily', etc.
    source_idea_id  UUID REFERENCES feature_ideas(id),
    added_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    embedding       vector(1536),           -- for dedup
    UNIQUE (symbol)
);
CREATE INDEX gp_primitives_embedding_idx
    ON gp_primitives USING hnsw (embedding vector_cosine_ops);

CREATE TABLE gp_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_date            DATE NOT NULL DEFAULT CURRENT_DATE,
    primitives_snapshot JSONB NOT NULL,     -- full primitive set used in this run
    config              JSONB NOT NULL,     -- population_size, generations, fitness_metric, etc.
    best_programs       JSONB NOT NULL DEFAULT '[]',  -- top N {expression, fitness, oos_ic}
    total_programs      INT,
    artifact_path       TEXT,               -- path to full results file
    created_at          TIMESTAMPTZ DEFAULT now()
);
```

### 2.4 Artifact Store Directory Layout

```
{ARTIFACTS_BASE_DIR}/
├── arxiv/
│   └── {paper_id}/
│       ├── pdf/          raw PDF
│       ├── fulltext/     extracted text + tables
│       ├── concepts/     concepts.json
│       ├── plan/         plan.json
│       ├── code/         {experiment_id}.py
│       ├── output/       {experiment_id}_stdout.txt, {experiment_id}_stderr.txt
│       ├── plots/        {experiment_id}_{n}.png
│       └── evaluation/   {experiment_id}_eval.json
├── dgp/
│   └── {thread_id}/
│       └── {finding_id}/
│           ├── fingerprint.json
│           ├── analysis.py
│           ├── output.txt
│           └── plots/    {n}.png
├── gp/
│   └── {run_date}/
│       ├── primitives.yaml
│       ├── runner.py
│       └── results.json
└── obsidian_exports/
    └── {feature_idea_id}.md
```

---

## 3. Coding Harness

### 3.1 Recommendation: `jupyter_client` with `KernelSessionManager`

**Rationale:** The DGP research loop requires stateful Python sessions — data loaded once, fitted models and computed arrays reused across multiple agent iterations. `jupyter_client` is the only self-hosted, Python-native option with true persistent kernel state, rich output capture (matplotlib as PNG via MIME types, pandas DataFrames as text), and built-in timeout/interrupt control. All alternatives either lack statefulness (LLM-Sandbox, Piston, SWE-ReX), require external cloud services (E2B), or are overengineered full platforms (OpenHands).

**Usage by process:**
- **Process 1**: Ephemeral kernel per experiment (short-lived, `destroy_session` after each experiment)
- **Process 2**: Persistent kernel per DGP research thread (lives for the thread's full lifetime, typically hours)
- **Process 3**: Ephemeral kernel for the GP runner script (single execution)

### 3.2 Module Location

`src/shared/harness/` — shared across all three processes.

```
src/shared/harness/
├── __init__.py
├── kernel_session_manager.py   # KernelSessionManager
├── execution_result.py         # ExecutionResult dataclass
├── output_capture.py           # MIME output parser (plots, dataframes, errors)
└── prelude.py                  # Standard prelude code injected into every new kernel
```

### 3.3 `ExecutionResult` Schema

```python
@dataclass
class ExecutionResult:
    session_id: str
    code: str
    status: Literal["ok", "error", "timeout", "interrupted"]
    stdout: str                          # captured print() output
    stderr: str                          # captured warnings, tracebacks
    error_type: str | None               # exception class name if status == "error"
    error_traceback: str | None          # full traceback string
    plots: list[str]                     # list of base64-encoded PNG strings
    display_outputs: list[dict]          # non-image display_data (HTML, text/plain)
    execution_time_ms: int
    kernel_alive: bool                   # False if kernel died mid-execution
```

### 3.4 `KernelSessionManager` Interface

```python
class KernelSessionManager:
    """
    Manages a pool of IPython kernels. Each session maps to one kernel process.
    Thread-safe for use from async worker event loops.
    """

    def __init__(self, max_sessions: int = 10, kernel_name: str = "python3"):
        ...

    async def create_session(
        self,
        session_id: str,
        prelude_code: str | None = None,    # injected immediately after kernel start
        env_overrides: dict | None = None,  # extra env vars for the kernel process
    ) -> None:
        """Starts a new IPython kernel. Raises if session_id already exists."""

    async def execute(
        self,
        session_id: str,
        code: str,
        timeout_seconds: int = 300,
    ) -> ExecutionResult:
        """
        Executes code in the named session's kernel.
        Collects all iopub messages until kernel reports idle.
        Extracts: stdout, stderr, display_data (plots as base64 PNG), errors.
        Raises SessionNotFoundError if session doesn't exist.
        On timeout: calls interrupt_kernel(), waits 5s, then returns status="timeout".
        """

    async def interrupt(self, session_id: str) -> None:
        """Sends SIGINT to kernel. Does not destroy session."""

    async def restart(self, session_id: str) -> None:
        """Restarts kernel, preserving session registration but clearing all state."""

    async def destroy_session(self, session_id: str) -> None:
        """Graceful shutdown: shutdown_kernel() → cleanup socket files."""

    async def session_alive(self, session_id: str) -> bool:
        """Returns True if kernel process is running and responsive."""

    def list_sessions(self) -> list[str]:
        """Returns all active session IDs."""
```

### 3.5 Output Capture Implementation

The kernel communicates via ZMQ IOPub channel. Parse message types:

| `msg_type` | Action |
|------------|--------|
| `stream` (name=stdout) | Append to `stdout` |
| `stream` (name=stderr) | Append to `stderr` |
| `error` | Set `error_type`, `error_traceback`; set `status="error"` |
| `display_data` with `image/png` | Base64-decode and append to `plots` |
| `execute_result` with `text/plain` | Append to `display_outputs` |
| `status` (execution_state=idle) | Stop collecting (execution complete) |

Collecting messages example pattern (simplified):

```python
# send execute_request
msg_id = kc.execute(code)

outputs = {"stdout": "", "stderr": "", "plots": [], "display_outputs": [], "error_type": None}
while True:
    try:
        msg = kc.get_iopub_msg(timeout=timeout_seconds)
    except queue.Empty:
        # timeout hit — interrupt kernel
        km.interrupt_kernel()
        outputs["status"] = "timeout"
        break

    mt = msg["msg_type"]
    content = msg["content"]

    if mt == "stream":
        if content["name"] == "stdout":
            outputs["stdout"] += content["text"]
        else:
            outputs["stderr"] += content["text"]

    elif mt == "display_data" and "image/png" in content.get("data", {}):
        outputs["plots"].append(content["data"]["image/png"])

    elif mt == "execute_result":
        outputs["display_outputs"].append(content.get("data", {}))

    elif mt == "error":
        outputs["error_type"] = content["ename"]
        outputs["error_traceback"] = "\n".join(content["traceback"])
        outputs["status"] = "error"

    elif mt == "status" and content["execution_state"] == "idle":
        if "status" not in outputs:
            outputs["status"] = "ok"
        break
```

### 3.6 Standard Kernel Prelude

Injected once when any kernel session is created (`src/shared/harness/prelude.py`):

```python
STANDARD_PRELUDE = """
import warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')           # no display — outputs via MIME protocol
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats, signal
import statsmodels.api as sm

# Force inline plot display so figures emit display_data messages
from IPython.display import display
import io

def show():
    \"\"\"Call show() instead of plt.show() to emit plot as PNG to harness.\"\"\"
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    from IPython.display import Image
    display(Image(data=buf.read()))
    plt.close('all')
"""
```

Agents are instructed (in their system prompts) to call `show()` instead of `plt.show()`.

### 3.7 Error Recovery Loop

Used by Code Executor (Process 1) and Hypothesis Validator (Process 2):

```
Execute code → ExecutionResult
  if status == "ok":
      return result
  if status == "error" and attempt < max_attempts:
      feed (original_code + error_traceback) back to LLM with:
          "Fix the error. Return only the corrected complete script."
      attempt += 1; goto Execute
  if status == "timeout":
      log; mark experiment as timeout_failure; do not retry
  if attempt >= max_attempts:
      mark experiment as unrecoverable_failure; escalate to evaluator
```

`max_attempts` defaults to 5 (configurable via `CODE_EXECUTOR_MAX_RETRIES` env var).

---

## 4. Message Schemas (Complete Reference)

All messages extend `BaseMessage`. All field names are snake_case. All `JSONB` fields serialize to/from typed dataclasses via Pydantic.

### 4.1 BaseMessage

```python
class BaseMessage(BaseModel):
    work_id:        str         # UUID, unique per unit of work
    parent_work_id: str | None  # traces lineage back to originating paper/thread
    created_at:     datetime
    attempt:        int = 1
    max_attempts:   int = 3
    priority:       int = 5     # 1 (low) – 10 (high)
```

### 4.2 Process 1 Messages

```python
class PaperFullTextRequest(BaseMessage):
    arxiv_id:       str
    title:          str
    authors:        list[str]
    abstract:       str
    pdf_url:        str
    categories:     list[str]
    published_date: str         # ISO 8601

class ConceptGenerationRequest(BaseMessage):
    arxiv_id:       str
    title:          str
    full_text:      str         # extracted by PDF parser
    sections:       dict[str, str]  # section_title → section_text

class ConceptObject(BaseModel):
    concept_id:             str
    name:                   str
    origin_domain:          str
    problem_solved:         str
    system_abstraction:     str
    invariant_structures:   list[str]
    assumptions:            list[str]
    regime_behavior:        str
    failure_modes:          list[str]
    research_hooks:         list[str]
    mathematical_structures: list[str]  # tagged for DGP taxonomy feeder

class ConceptsGenerated(BaseMessage):
    arxiv_id:       str
    concepts:       list[ConceptObject]
    artifact_path:  str         # path to concepts.json

class PlanGenerated(BaseMessage):
    arxiv_id:           str
    plan_artifact_path: str
    experiment_count:   int

class CodeExecutionRequest(BaseMessage):
    arxiv_id:           str
    experiment_id:      str
    experiment_spec:    dict    # from plan.json: hypothesis, parameters, expected_metrics
    plan_artifact_path: str

class CodeExecutionResult(BaseMessage):
    arxiv_id:       str
    experiment_id:  str
    session_id:     str         # KernelSession ID used
    status:         str         # "ok" | "error" | "timeout" | "unrecoverable"
    code_path:      str
    stdout:         str
    stderr:         str
    plots:          list[str]   # artifact paths to saved PNGs
    metrics:        dict        # key metrics extracted from stdout (structured)
    attempt:        int

class ExperimentEvaluationRequest(BaseMessage):
    arxiv_id:       str
    experiment_id:  str
    execution_result: CodeExecutionResult
    experiment_spec: dict

class ExperimentEvaluationResult(BaseMessage):
    arxiv_id:       str
    experiment_id:  str
    recommendation: str         # "PROMOTE" | "KILL" | "INVESTIGATE" | "RETRY"
    is_promising:   bool        # True if recommendation in (PROMOTE, INVESTIGATE)
    findings:       str         # prose summary of what was found
    feature_implication: str    # what feature this suggests
    open_questions: list[str]
    artifact_path:  str         # evaluation.json path
```

### 4.3 Process 2 Messages

```python
class DataSlice(BaseModel):
    instrument:     str         # e.g. "ES", "NQ"
    frequency:      str         # "tick" | "1m" | "5m" | "15m" | "1h" | "daily"
    window_type:    str         # "rolling" | "regime" | "full"
    window_days:    int | None  # for rolling; None = full history
    regime_label:   str | None  # "high_vol" | "low_vol" | "trending" | "ranging"
    start_date:     str | None
    end_date:       str | None

class DGPCharacterizeRequest(BaseMessage):
    queue_entry_id: str         # dgp_research_queue.id
    finding_id:     str         # dgp_findings.id (phase=characterization)
    thread_id:      str
    data_slice:     DataSlice
    depth:          int

class StructuralFingerprint(BaseModel):
    # Distributional
    mean:           float
    std:            float
    skewness:       float
    kurtosis:       float
    tail_index:     float       # Hill estimator
    jb_pvalue:      float       # Jarque-Bera normality test
    # Memory / autocorrelation
    hurst_exponent: float
    hurst_method:   str         # "rs" | "dfa"
    hurst_ci:       tuple[float, float]
    acf_lags:       dict[int, float]   # lag → acf value
    ljung_box_pvalue: float
    # Nonlinearity
    bds_pvalue:     float
    # Stationarity
    adf_pvalue:     float
    kpss_pvalue:    float
    structural_breaks: list[str]  # approximate dates of detected breaks
    # Volatility
    arch_lm_pvalue: float
    # Complexity
    sample_entropy: float
    permutation_entropy: float
    # Regimes
    hmm_n_states_best: int      # best BIC among 2/3/4-state HMMs
    hmm_bic_scores:    dict[int, float]

class DGPFingerprintGenerated(BaseMessage):
    finding_id:     str
    thread_id:      str
    data_slice:     DataSlice
    fingerprint:    StructuralFingerprint
    artifact_path:  str
    notable_features: list[str]  # prose descriptions of most distinctive findings

class DGPHypothesis(BaseModel):
    hypothesis_id:      str
    process_class:      str      # e.g. "multifractal cascade", "Hawkes process"
    prose:              str      # full hypothesis statement
    predicted_properties: list[str]
    discriminating_test: str     # specific test that would confirm/deny
    implied_features:   list[str]  # candidate features if hypothesis is true
    concept_pair:       tuple[str, str]  # two cross-domain concepts that motivated this

class DGPFingerprintInterpreted(BaseMessage):
    finding_id:         str     # parent characterization finding
    thread_id:          str
    hypotheses:         list[DGPHypothesis]
    new_finding_ids:    list[str]  # dgp_findings rows created for each hypothesis

class DGPValidateRequest(BaseMessage):
    finding_id:     str         # dgp_findings row for this validation phase
    parent_id:      str         # parent interpretation finding
    thread_id:      str
    data_slice:     DataSlice
    hypothesis:     DGPHypothesis

class DGPValidationResult(BaseMessage):
    finding_id:     str
    thread_id:      str
    hypothesis:     DGPHypothesis
    is_significant: bool        # did metrics pass significance threshold?
    metrics:        dict        # raw statistical outputs
    findings_prose: str
    open_questions: list[str]
    should_promote: bool        # True → write to feature_ideas
    depth:          int

class DGPSynthesisRequest(BaseMessage):
    thread_id:          str | None   # None = synthesize all threads with unsynthesized findings
    since_hours:        int = 4      # only look at findings from last N hours
```

### 4.4 Process 3 Messages

```python
class GPSessionTrigger(BaseMessage):
    trigger_date:   str     # ISO date, today's date
    since_date:     str     # look for feature_ideas since this date (yesterday)

class GPPrimitivesReady(BaseMessage):
    run_date:       str
    primitives_path: str    # path to gp_primitives.yaml
    new_primitive_count: int
    total_primitive_count: int
```

### 4.5 Cross-Cutting Messages

```python
class FeatureIdeaCreated(BaseMessage):
    feature_idea_id:    str
    source_process:     str     # "arxiv" | "dgp" | "gp"
    title:              str
    summary:            str
    is_promising:       bool
    evidence:           dict
    tags:               list[str]

class ObsidianWriteRequest(BaseMessage):
    feature_idea_id:    str
    template_type:      str     # "arxiv_feature" | "dgp_finding" | "gp_program"
    content:            dict    # template-specific fields

class NotificationRequest(BaseMessage):
    alert_type:         str     # "research" | "eod_digest"
    title:              str
    body:               str
    attachments:        list[str]  # artifact paths (images, etc.)
    feature_idea_ids:   list[str]  # linked feature ideas
```

---

## 5. Process 1 — ArXiv Pipeline (24/7)

### 5.1 Status: Largely Built

Workers exist: `ArXivFetcher`, `PDFParser`, `ConceptGenerator`, `ExperimentExploder`, `CodeExecutor`, `ExperimentEvaluator`, `SlackNotifier`. 

Gaps to close:
- `ObsidianWriterWorker` (new)
- `feature_ideas` table integration in `ExperimentEvaluator`
- Concept taxonomy feeder in `ConceptGenerator` (append `mathematical_structures` to DGP taxonomy)
- Binary promising flag (no confidence score — see §5.7)

### 5.2 Worker: ArXivFetcher

**Module:** `src/workers/arxiv_fetcher/`  
**Trigger:** Cron schedule, default every 30 minutes  
**Output queue:** `paper.triage.request` (routing key: `paper.triage.fetch`)

Publishes one `PaperFullTextRequest` per new paper. Duplicate detection via `PaperRepository.exists(arxiv_id)`. Rate limit: 0.33 req/s. Categories from `ARXIV_CATEGORIES` env var.

### 5.3 Worker: PDFParser

**Module:** `src/workers/pdf_parser/`  
**Input queue:** `paper.fulltext.request`  
**Output queue:** `paper.concepts.request`  
**Library:** `docling`

Extracts structured full text including equations. Stores raw text artifact. Publishes `ConceptGenerationRequest`.

### 5.4 Worker: ConceptGenerator

**Module:** `src/workers/concept_generator/`  
**Input queue:** `paper.concepts.request`  
**Output queue:** `plan.generate.request`  
**LLM profile:** `concept_gen`

**Output:** `ConceptsGenerated` containing list of `ConceptObject`. The `mathematical_structures` field on each concept is new — it lists named mathematical tools used (e.g., "Fokker-Planck equation", "Hawkes point process", "persistent homology"). After publishing `ConceptsGenerated`, the worker **also writes each entry in `mathematical_structures` to `config/dgp/concept_taxonomy.yaml`** (deduped by name), closing the feedback loop to Process 2.

**System prompt requirements (encode in LLM config):**
- Extract concepts that are applicable to financial time series
- For each concept, identify the mathematical structures used — be specific (name the equations/theorems/processes, not just the domain)
- Focus on MFT-relevant timescales (5–30 second holding periods)
- Generate research hooks: specific questions that could be empirically tested

### 5.5 Worker: ExperimentExploder

**Module:** `src/workers/experiment_exploder/`  
**Input queue:** `plan.generate.request`  
**Output queue:** `plan.generated`  
**LLM profile:** `experiment_exploder`

Generates a `plan.json` artifact with a list of experiment specs. Each experiment spec contains:

```json
{
  "experiment_id": "uuid",
  "concept_id":    "uuid",
  "hypothesis":    "prose null hypothesis statement",
  "null_hypothesis": "formal H0",
  "test_statistic": "name of statistical test to run",
  "expected_metrics": {
    "metric_name": {"direction": "positive|negative", "threshold": 0.05}
  },
  "data_requirements": {
    "frequency": "1m",
    "lookback_days": 30,
    "features": ["close", "volume", "bid_ask_spread"]
  },
  "code_guidance": "prose description of what the Python script should do"
}
```

**Constraints** (enforce in system prompt and config):
- `max_experiments_per_concept`: 5 (configurable)
- `max_total_experiments`: 20
- All experiments must specify `null_hypothesis` and `expected_metrics` before code generation
- Holding time: 5–30 second range for signal validation

### 5.6 Worker: CodeExecutor

**Module:** `src/workers/code_executor/`  
**Input queue:** `plan.generated`  
**Output queue:** `experiment.evaluation.request`  
**LLM profile:** `code_executor`  
**Harness:** `KernelSessionManager` — ephemeral session per experiment

For each experiment in the plan:
1. Create ephemeral kernel session (`session_id = experiment_id`)
2. Inject standard prelude
3. LLM generates Python script given `experiment_spec` and data file path
4. Execute via `KernelSessionManager.execute()`
5. If `status == "error"`: feed code + traceback back to LLM for fix (up to `CODE_EXECUTOR_MAX_RETRIES`, default 5)
6. If `status == "timeout"`: mark as `timeout_failure`, do not retry
7. Save plots to artifact store: `artifacts/arxiv/{paper_id}/plots/{experiment_id}_{n}.png`
8. Extract key metrics from stdout (structured JSON block expected in script output — instruct LLM to emit `METRICS: {...}` line)
9. Publish `CodeExecutionResult`
10. `destroy_session(session_id)` after result published

**Metrics extraction pattern:** Scripts must emit a line matching `^METRICS: \{.*\}$` to stdout. The worker parses this as JSON into `CodeExecutionResult.metrics`.

### 5.7 Worker: ExperimentEvaluator

**Module:** `src/workers/experiment_evaluator/`  
**Input queue:** `experiment.evaluation.request`  
**Output queues:** `feature.idea.created`, `notify.send`  
**LLM profile:** `evaluator`

Evaluates `CodeExecutionResult` against the experiment spec's `expected_metrics`.

**Binary promising determination (no confidence scoring):**

```python
def is_promising(metrics: dict, expected_metrics: dict) -> bool:
    """
    Returns True if ANY expected metric meets its threshold
    OR is within NEAR_THRESHOLD_FACTOR of its threshold.
    All threshold comparisons are metric-type-aware.
    """
    near_factor = float(os.environ.get("NEAR_THRESHOLD_FACTOR", "1.5"))
    for metric_name, spec in expected_metrics.items():
        if metric_name not in metrics:
            continue
        value = metrics[metric_name]
        threshold = spec["threshold"]
        direction = spec["direction"]
        if direction == "positive":
            if value >= threshold / near_factor:
                return True
        elif direction == "negative":   # e.g. p-values: lower is better
            if value <= threshold * near_factor:
                return True
    return False
```

If `is_promising=True`:
- Write row to `feature_ideas`
- Publish `FeatureIdeaCreated` (routing key: `feature.idea.created`)
- `FeatureIdeaCreated` is consumed by both `ObsidianWriterWorker` and `SlackNotifier`

If `is_promising=False`: write to artifact store only; no further propagation.

**LLM role (evaluator):** Interpret the results, write `findings` prose and `feature_implication`. Does NOT assign a confidence score or probability. Does NOT determine whether something is promising (that is determined by the metric check above).

### 5.8 Worker: ObsidianWriter (NEW)

**Module:** `src/workers/obsidian_writer/`  
**Input queue:** `feature.idea.created`  
**Config:** `OBSIDIAN_VAULT_PATH` (mounted volume), `OBSIDIAN_FEATURE_DIR`

Writes a Markdown note to `{OBSIDIAN_VAULT_PATH}/{OBSIDIAN_FEATURE_DIR}/{feature_idea_id}.md`.

**Note template (arxiv_feature):**

```markdown
---
id: {feature_idea_id}
source: arxiv
paper: {arxiv_id}
tags: [feature-candidate, {domain_tag}, {status}]
created: {date}
status: pending
---

# {title}

## Source
**Paper:** [{paper_title}](https://arxiv.org/abs/{arxiv_id})  
**Concept:** {concept_name} ({origin_domain})

## Hypothesis
{hypothesis}

## Null Hypothesis
{null_hypothesis}

## Experiment Results
{findings}

## Feature Implication
{feature_implication}

## Metrics
```json
{metrics_json}
```

## Open Questions
{open_questions_list}
```

After writing, updates `feature_ideas.obsidian_path` in the database.

---

## 6. Process 2 — DGP Research Pipeline (24/7)

### 6.1 Overview

Reverse-engineers the data-generating process of configured instruments rather than projecting known concepts onto data. Runs as a self-expanding research tree managed by `DGPOrchestrator`. All workers reuse the existing `BaseWorker` / RabbitMQ / `KernelSessionManager` patterns.

### 6.2 Worker: DGPOrchestrator

**Module:** `src/workers/dgp_orchestrator/`  
**Trigger:** Starts on container launch; polls `dgp_research_queue` table continuously  
**Does NOT consume a RabbitMQ queue** — it IS the queue manager

**Startup seeding:** On first run (no existing queue entries for an instrument), inserts seed `DGPCharacterizeRequest` entries covering the full cross-product:

```python
instruments = os.environ["INSTRUMENTS"].split(",")   # e.g. "ES,NQ,CL"
frequencies = ["1m", "5m", "15m", "1h", "daily"]
window_specs = [
    {"window_type": "rolling", "window_days": 30},
    {"window_type": "rolling", "window_days": 90},
    {"window_type": "rolling", "window_days": 365},
    {"window_type": "full"},
]
# regime slices added later once HMM labels are computed by Structural Reader
```

**Dispatch loop:**

```python
while True:
    jobs = db.query(
        "SELECT * FROM dgp_research_queue "
        "WHERE status = 'queued' "
        "ORDER BY priority DESC, created_at ASC "
        "LIMIT {DGP_DISPATCH_BATCH_SIZE}"
    )
    for job in jobs:
        db.update(job.id, status='dispatched', dispatched_at=now())
        publisher.publish(routing_key='dgp.characterize.request', message=build_message(job))
    await asyncio.sleep(DGP_ORCHESTRATOR_POLL_INTERVAL_SECONDS)  # default 10s
```

**On receiving `DGPValidationResult`** (subscribes to `dgp.validation.result`):

```python
async def on_validation_result(result: DGPValidationResult):
    # Update finding record
    db.update_finding(result.finding_id, is_significant=result.is_significant, ...)

    if result.is_significant and result.depth < DGP_MAX_DEPTH:
        for question in result.open_questions:
            priority = compute_priority(question, existing_findings)
            if priority > DGP_PRUNE_THRESHOLD:
                db.insert_queue_entry(
                    parent_finding_id=result.finding_id,
                    question_type='depth',
                    question=question,
                    priority=priority,
                    ...
                )

    if result.should_promote:
        write_feature_idea(result)  # → feature_ideas table + FeatureIdeaCreated message
```

**Priority scoring function:**

```python
def compute_priority(question: str, existing_findings: list) -> float:
    """
    0.0–1.0. Higher = dispatch sooner.
    Factors:
    - Semantic novelty vs existing findings (via pgvector cosine: high similarity → lower priority)
    - Presence of known-predictive phenomenon keywords (boost +0.2)
    - Depth penalty: priority * (1 - depth * 0.1) to prefer breadth at low depths
    """
    embedding = llm.embed(question)
    max_similarity = db.max_cosine_similarity(embedding, table='dgp_findings')
    novelty = 1.0 - max_similarity
    keyword_boost = 0.2 if any(kw in question.lower() for kw in PREDICTIVE_KEYWORDS) else 0.0
    depth_penalty = result.depth * 0.1
    return min(1.0, max(0.0, novelty + keyword_boost - depth_penalty))
```

### 6.3 Worker: StructuralReader

**Module:** `src/workers/dgp_structural_reader/`  
**Input queue:** `dgp.characterize.request`  
**Output queue:** `dgp.fingerprint.generated`  
**Harness:** `KernelSessionManager` — persistent session per `thread_id`  
**Scale:** `DGP_STRUCTURAL_READER_REPLICAS` (default 3)

Runs a **fixed analysis battery** — no LLM involved in analysis code generation. The analysis code is deterministic Python, not agent-generated. This is the most important design choice: Phase 1 must be reproducible and not subject to LLM interpretation bias.

**Kernel session management:**
- On first characterization for a `thread_id`: create persistent session, load data
- On subsequent characterizations for same thread: reuse session (data already loaded)
- Session key: `f"dgp_{thread_id}"`

**Data loading prelude (injected once per thread session):**

```python
DATA_LOAD_TEMPLATE = """
import pandas as pd
import numpy as np

df = pd.read_parquet('{data_path}')
df.index = pd.to_datetime(df.index)
df = df.sort_index()

# Apply data slice filter
if '{start_date}' != 'None':
    df = df[df.index >= '{start_date}']
if '{end_date}' != 'None':
    df = df[df.index <= '{end_date}']

# Compute log returns
df['log_return'] = np.log(df['close'] / df['close'].shift(1)).dropna()
series = df['log_return'].dropna().values
print(f"Loaded {len(series)} observations")
"""
```

**Analysis battery** (each block executes in sequence; all results emitted as `METRICS: {...}`):

```python
ANALYSIS_BATTERY = [
    "01_distributional.py",    # moments, tail index (Hill), Jarque-Bera
    "02_autocorrelation.py",   # ACF/PACF, Ljung-Box
    "03_hurst.py",             # R/S and DFA Hurst exponent with 95% CI
    "04_stationarity.py",      # ADF, KPSS, Zivot-Andrews structural breaks
    "05_nonlinearity.py",      # BDS test
    "06_volatility.py",        # ARCH-LM, volatility clustering
    "07_entropy.py",           # sample entropy, permutation entropy
    "08_regimes.py",           # HMM 2/3/4 states, PELT change-point detection
]
```

These are static Python scripts stored at `src/workers/dgp_structural_reader/battery/`. They are NOT LLM-generated. They run in the persistent kernel session so each shares the loaded `df` and `series` variables.

**Output:** `DGPFingerprintGenerated` with fully populated `StructuralFingerprint`. Worker writes `fingerprint.json` to artifact store. Also generates a set of `notable_features` — a ranked list of the most unusual/distinctive findings (e.g., "Hurst exponent 0.71 — strong long memory", "BDS p=0.002 — significant nonlinear structure").

### 6.4 Worker: DGPInterpreter

**Module:** `src/workers/dgp_interpreter/`  
**Input queue:** `dgp.fingerprint.generated`  
**Output queue:** `dgp.validate.request` (one message per hypothesis)  
**LLM profile:** `dgp_interpreter`

Receives `DGPFingerprintGenerated`. Uses LLM to map the fingerprint onto candidate process explanations from the concept taxonomy.

**Concept taxonomy format** (`config/dgp/concept_taxonomy.yaml`):

```yaml
concepts:
  - name: "Hawkes Point Process"
    domain: "point_processes"
    predicted_fingerprint_indicators:
      - "volatility clustering (ARCH-LM significant)"
      - "heavy tails (tail_index < 3)"
      - "nonlinear dependence (BDS significant)"
    discriminating_test: "Fit Hawkes process via MLE; test branching ratio < 1 (stationarity condition); compare AIC vs Poisson baseline"
    implied_features:
      - "conditional intensity λ(t)"
      - "branching ratio η"
      - "kernel decay rate β"

  - name: "Multifractal Cascade"
    domain: "statistical_mechanics"
    predicted_fingerprint_indicators:
      - "Hurst exponent between 0.6 and 0.8"
      - "non-Gaussian returns (kurtosis > 6)"
      - "volatility clustering"
    discriminating_test: "Multifractal spectrum via wavelet leaders; compare D(h) width vs monofractal null"
    implied_features:
      - "local Hölder exponent h(t)"
      - "multifractal spectrum D(h)"
      - "intermittency parameter λ²"

  # ... (grows over time via ConceptGenerator mathematical_structures feeder)
```

**LLM task:** Given the fingerprint's `notable_features`, identify the N most consistent process explanations from the taxonomy. For each, formulate a structured `DGPHypothesis`. Cross-domain forcing: LLM must include at least one hypothesis that combines concepts from two different domains (e.g., topology + statistical mechanics).

**N hypotheses per fingerprint:** Configurable via `DGP_HYPOTHESES_PER_FINGERPRINT` (default 5).

Creates one `dgp_findings` row per hypothesis (phase=`interpretation`) and publishes one `DGPValidateRequest` per hypothesis to `dgp.validate.request`.

### 6.5 Worker: HypothesisValidator

**Module:** `src/workers/dgp_validator/`  
**Input queue:** `dgp.validate.request`  
**Output queue:** `dgp.validation.result`  
**LLM profile:** `dgp_validator`  
**Harness:** `KernelSessionManager` — reuses persistent session by `thread_id`  
**Scale:** `DGP_VALIDATOR_REPLICAS` (default 3)

Receives a `DGPValidateRequest` with a fully-specified `discriminating_test`. Unlike the Structural Reader (which runs fixed code), this worker uses LLM to generate the test code — but the test is theoretically motivated and the null hypothesis is pre-specified.

**Execution flow:**
1. Build system prompt: includes the hypothesis, discriminating test specification, data already loaded in kernel session (from StructuralReader phase), and the SKILL.md constraints
2. LLM generates Python code implementing the discriminating test
3. Execute in the thread's persistent kernel session (data already loaded)
4. Apply error recovery loop (max `DGP_VALIDATOR_MAX_RETRIES`, default 5)
5. Extract `METRICS: {...}` from stdout
6. Apply significance check:

```python
def is_significant(metrics: dict, test_spec: DGPHypothesis) -> bool:
    """
    Returns True if the discriminating test result is consistent with the hypothesis.
    Uses the same near-threshold logic as Process 1 (§5.7).
    """
    p_values = {k: v for k, v in metrics.items() if k.endswith("_pvalue")}
    effect_sizes = {k: v for k, v in metrics.items() if k.endswith("_effect") or k.endswith("_stat")}
    p_threshold = float(os.environ.get("DGP_SIGNIFICANCE_PVALUE", "0.05"))
    near_factor = float(os.environ.get("NEAR_THRESHOLD_FACTOR", "1.5"))
    return any(v <= p_threshold * near_factor for v in p_values.values())
```

7. LLM writes `findings_prose` and `open_questions` (no confidence scoring)
8. Sets `should_promote = is_significant and has_feature_implication`
9. Publish `DGPValidationResult`

**SKILL.md constraints** (enforced in system prompt for code generation):
- Formulate and state the null hypothesis before writing any test code
- Use train/test split: characterize on first 70% of window, validate on last 30%
- Report effect size alongside p-values
- Apply Bonferroni correction if running more than one test in the same script
- Emit results as `METRICS: {"test_name_pvalue": 0.03, "test_name_effect": 0.42, ...}`
- Call `show()` for any plots

### 6.6 Worker: DGPSynthesizer

**Module:** `src/workers/dgp_synthesizer/`  
**Trigger:** Periodic — cron every `DGP_SYNTHESIS_INTERVAL_HOURS` hours (default 4)  
**LLM profile:** `dgp_synthesizer`

Runs across all completed findings in recent windows. Asks:
- Do findings from different branches describe the same phenomenon?
- What coherent DGP model best explains the joint set of findings from a thread?
- What natural features (sufficient statistics of the candidate DGP) fall out of this model?

If synthesis produces a coherent DGP model with at least one feature implication:
- Write to `feature_ideas` (source_process='dgp')
- Publish `FeatureIdeaCreated`
- Write Obsidian note via `ObsidianWriterWorker` (template: `dgp_finding`)

**DGP Obsidian note template:**

```markdown
---
id: {feature_idea_id}
source: dgp
thread_id: {thread_id}
instrument: {instrument}
tags: [dgp-research, {process_class}, feature-candidate]
created: {date}
status: pending
---

# {title}

## Data Slice
- Instrument: {instrument}
- Frequency: {frequency}
- Window: {window_description}
- Regime: {regime_label or "unconditional"}

## Structural Fingerprint Summary
{notable_features_prose}

## Candidate DGP
**Process class:** {process_class}
**Hypothesis:** {hypothesis_prose}

## Validation Evidence
{findings_prose}

### Test Metrics
```json
{metrics_json}
```

## Implied Features
{implied_features_list}

## Open Research Questions
{open_questions_list}

## Related Findings
{links_to_parent_and_sibling_findings}
```

---

## 7. Process 3 — Genetic Programming (Daily @ Market Close)

### 7.1 Overview

Cron-triggered daily at market close (configurable, default `15 16 * * 1-5` — 4:15 PM ET on weekdays). Two steps: (1) Primitive Harvester reads that day's `feature_ideas` and expands the primitive set; (2) GP Runner executes evolution. Results are logged to `gp_runs`; top programs are written to the Feature Idea Store directly. Researcher interprets all results — no evaluator agent.

### 7.2 Worker: GPPrimitiveHarvester

**Module:** `src/workers/gp_primitive_harvester/`  
**Input queue:** `gp.session.trigger`  
**Output queue:** `gp.primitives.ready`  
**LLM profile:** `gp_harvester`

**Step 1 — Identify new feature ideas:**

```sql
SELECT * FROM feature_ideas
WHERE is_promising = true
  AND created_at >= :since_date
  AND status IN ('pending', 'promoted')
  AND source_process IN ('arxiv', 'dgp');
```

**Step 2 — Extract primitives via LLM:**

For each `feature_idea`, prompt the LLM to extract one or more symbolic primitives. Each primitive must have:

```yaml
- symbol: log_volume_ratio
  expression: "log(volume_t / volume_{t-1})"
  primitive_type: terminal   # or "function"
  time_scale: "1m"
  description: "Log ratio of consecutive volume bars"
```

The LLM is instructed to:
- Express features as composable symbolic building blocks
- Distinguish terminals (leaf nodes in GP trees, produce a time series) from functions (operators on series)
- Use parameterized expressions where relevant (e.g., `ema(series, window)` with `window` as an evolvable constant)

**Step 3 — Dedup against existing primitives:**

For each extracted primitive, compute embedding and check cosine similarity against `gp_primitives`:
```python
embedding = llm.embed(f"{symbol}: {expression}")
max_sim = db.max_cosine_similarity(embedding, table='gp_primitives')
if max_sim < GP_PRIMITIVE_DEDUP_THRESHOLD:   # default 0.92
    db.insert_primitive(...)
```

**Step 4 — Write `config/gp/primitives.yaml`** with the full current primitive set and publish `GPPrimitivesReady`.

### 7.3 Worker: GPRunner

**Module:** `src/workers/gp_runner/`  
**Input queue:** `gp.primitives.ready`  
**Library:** `DEAP` (`pip install deap`)

The GP runner is a **deterministic Python algorithm**, not an LLM agent. The only agent involvement was in §7.2.

**Configuration** (from environment / `gp_runs.config`):

```python
GP_POPULATION_SIZE     = int(os.environ.get("GP_POPULATION_SIZE", "500"))
GP_GENERATIONS         = int(os.environ.get("GP_GENERATIONS", "100"))
GP_TOURNAMENT_SIZE     = int(os.environ.get("GP_TOURNAMENT_SIZE", "7"))
GP_CROSSOVER_PROB      = float(os.environ.get("GP_CROSSOVER_PROB", "0.7"))
GP_MUTATION_PROB       = float(os.environ.get("GP_MUTATION_PROB", "0.2"))
GP_PARSIMONY_COEFF     = float(os.environ.get("GP_PARSIMONY_COEFF", "0.001"))
GP_FITNESS_METRIC      = os.environ.get("GP_FITNESS_METRIC", "ic")    # "ic" | "sharpe"
GP_MAX_TREE_DEPTH      = int(os.environ.get("GP_MAX_TREE_DEPTH", "6"))
GP_OOS_SPLIT           = float(os.environ.get("GP_OOS_SPLIT", "0.3"))  # last 30% = OOS
GP_TOP_N_PROGRAMS      = int(os.environ.get("GP_TOP_N_PROGRAMS", "20"))
```

**DEAP primitive set construction:**

```python
import operator
from deap import gp

pset = gp.PrimitiveSetTyped("main", [np.ndarray], np.ndarray)

# Base operators (always present)
pset.addPrimitive(np.add,    [np.ndarray, np.ndarray], np.ndarray, name="add")
pset.addPrimitive(np.subtract, [np.ndarray, np.ndarray], np.ndarray, name="sub")
pset.addPrimitive(np.multiply, [np.ndarray, np.ndarray], np.ndarray, name="mul")
pset.addPrimitive(safe_divide, [np.ndarray, np.ndarray], np.ndarray, name="div")
pset.addPrimitive(np.log1p,  [np.ndarray], np.ndarray, name="log1p")
pset.addPrimitive(np.abs,    [np.ndarray], np.ndarray, name="abs")
pset.addPrimitive(rolling_mean, [np.ndarray, int], np.ndarray, name="ema")
pset.addPrimitive(rolling_std,  [np.ndarray, int], np.ndarray, name="std")
pset.addPrimitive(lag,          [np.ndarray, int], np.ndarray, name="lag")

# Dynamic primitives from primitives.yaml (added at runtime)
for p in load_primitives(primitives_path):
    if p.primitive_type == "terminal":
        pset.addTerminal(load_series(p.symbol), np.ndarray, name=p.symbol)
    elif p.primitive_type == "function":
        pset.addPrimitive(build_function(p), [...], np.ndarray, name=p.symbol)
```

**Fitness function:**

```python
def evaluate(individual, data_train, data_oos, target_train, target_oos):
    func = gp.compile(individual, pset)
    signal_train = func(data_train)
    signal_oos   = func(data_oos)

    # Parsimony penalty
    complexity_penalty = GP_PARSIMONY_COEFF * len(individual)

    if GP_FITNESS_METRIC == "ic":
        ic_train = np.corrcoef(signal_train[:-1], target_train[1:])[0, 1]
        ic_oos   = np.corrcoef(signal_oos[:-1],   target_oos[1:])[0, 1]
        # Penalize overfitting: IC degrades >30% from train to OOS
        overfitting_penalty = max(0, (ic_train - ic_oos) / (abs(ic_train) + 1e-8) - 0.3) * 0.5
        fitness = ic_oos - complexity_penalty - overfitting_penalty
    elif GP_FITNESS_METRIC == "sharpe":
        returns_oos = target_oos * np.sign(signal_oos[:-1])
        sharpe = returns_oos.mean() / (returns_oos.std() + 1e-8) * np.sqrt(252)
        fitness = sharpe - complexity_penalty

    return (fitness,)
```

**Target variable:** Forward log return at the configured prediction horizon (`GP_PREDICTION_HORIZON_BARS`, default 6 bars at the primary frequency).

**Post-run output:**

```python
best_programs = sorted(population, key=lambda ind: ind.fitness.values[0], reverse=True)[:GP_TOP_N_PROGRAMS]

# Write to gp_runs
run_record = {
    "best_programs": [
        {
            "rank": i+1,
            "expression": str(program),
            "tree_depth": program.height,
            "train_fitness": ...,
            "oos_fitness": ...,
            "oos_ic": ...,
        }
        for i, program in enumerate(best_programs)
    ],
    ...
}
db.insert_gp_run(run_record)

# Write top programs to feature_ideas (no agent evaluation — researcher interprets)
for i, program in enumerate(best_programs[:5]):
    is_promising = program.oos_ic > float(os.environ.get("GP_PROMISING_IC_THRESHOLD", "0.03"))
    db.insert_feature_idea(
        source_process='gp',
        title=f"GP Program #{i+1} — {run_date}",
        summary=str(program),
        is_promising=is_promising,
        evidence={"oos_ic": program.oos_ic, "oos_fitness": program.oos_fitness, "rank": i+1},
    )
```

**Research alert trigger:** Publish `NotificationRequest` (alert_type='research') for any GP program where `oos_ic >= GP_PROMISING_IC_THRESHOLD`. EOD digest includes full top-N summary regardless.

---

## 8. Alert System

Two alert types only. No confidence scoring by agents. Promising = metric threshold check.

### 8.1 Research Alert

**Trigger conditions (any of):**
- Process 1: `ExperimentEvaluationResult.is_promising == True`
- Process 2: `DGPValidationResult.is_significant == True` and `should_promote == True`
- Process 3: GP program with `oos_ic >= GP_PROMISING_IC_THRESHOLD`

**Slack message format:**

```
[RESEARCH] {title}

Source: {source_process} | {instrument or arxiv_id}
{one-sentence summary}

Key Metrics:
• {metric_1}: {value_1}
• {metric_2}: {value_2}

Implied Feature: {feature_implication}

📎 Obsidian: {obsidian_path}
```

Plots (if any) attached as Slack file uploads. Max 3 plots per alert.

### 8.2 EOD Digest

**Trigger:** Cron daily at `EOD_DIGEST_TIME` (default `17:00 ET`, weekdays only)

**Content:**

```
[EOD DIGEST] {date}

─── Process 1: ArXiv ───────────────────
Papers ingested: {N}
Experiments run: {N}
Promising findings: {N}
  • {title_1}
  • {title_2}

─── Process 2: DGP ─────────────────────
Characterizations completed: {N}
Hypotheses tested: {N}
Significant findings: {N}
  • {title_1}
  • {title_2}
New taxonomy entries added: {N}

─── Process 3: GP ──────────────────────
Run date: {date}
Primitives used: {N} (+{N} new)
Top OOS IC: {value}
Programs to review: {N}
  • Rank 1: {expression} (IC={value})
  • Rank 2: {expression} (IC={value})

─── Feature Idea Store ─────────────────
New ideas today: {N}
Pending review: {N}
```

**Implementation:** `EODDigestWorker` (`src/workers/eod_digest/`) triggered by cron, queries all relevant tables for today's stats, formats and posts to Slack.

### 8.3 `SlackNotifierWorker` Changes

**Module:** `src/workers/notifier/slack_worker.py` (existing, modify)

Currently sends all notifications. Change: filter by `NotificationRequest.alert_type`:
- `'research'`: post immediately
- `'eod_digest'`: post immediately (already batched by digest worker)
- Any other `alert_type`: drop silently and log

Remove all logic that gates on confidence scores.

---

## 9. Feature Idea Store — Dedup Algorithm

Before inserting any new `feature_ideas` row:

```python
async def dedup_or_insert(idea: FeatureIdeaCandidate, db, llm) -> str:
    """
    Returns the ID of the existing or newly created feature_ideas row.
    """
    embedding = await llm.embed(f"{idea.title}. {idea.summary}")

    # Check cosine similarity against all existing ideas
    existing = await db.fetch_one("""
        SELECT id, title, 1 - (embedding <=> :embedding) AS similarity
        FROM feature_ideas
        ORDER BY embedding <=> :embedding
        LIMIT 1
    """, embedding=embedding)

    if existing and existing.similarity >= FEATURE_DEDUP_THRESHOLD:  # default 0.92
        # Append new evidence rather than creating duplicate
        await db.execute("""
            UPDATE feature_ideas
            SET evidence = evidence || :new_evidence,
                updated_at = now(),
                is_promising = is_promising OR :new_is_promising
            WHERE id = :id
        """, id=existing.id, new_evidence=idea.evidence, new_is_promising=idea.is_promising)
        return existing.id
    else:
        new_id = await db.insert_feature_idea({**idea.dict(), "embedding": embedding})
        return new_id
```

---

## 10. Concept Taxonomy Feeder

Connects Process 1 to Process 2. After `ConceptGenerator` emits `ConceptsGenerated`, it also appends new mathematical structures to the taxonomy file.

**Location:** `config/dgp/concept_taxonomy.yaml` (read-write, git-tracked)

**Logic in ConceptGenerator** (after publishing message):

```python
taxonomy = load_yaml("config/dgp/concept_taxonomy.yaml")
existing_names = {c["name"].lower() for c in taxonomy["concepts"]}

for concept in concepts_generated.concepts:
    for struct in concept.mathematical_structures:
        if struct.lower() not in existing_names:
            taxonomy["concepts"].append({
                "name": struct,
                "domain": concept.origin_domain,
                "source": "arxiv_intake",
                "arxiv_id": concept.concept_id,
                "predicted_fingerprint_indicators": [],  # populated by DGP research
                "discriminating_test": "",
                "implied_features": concept.research_hooks,
            })
            existing_names.add(struct.lower())

save_yaml(taxonomy, "config/dgp/concept_taxonomy.yaml")
```

---

## 11. Docker Compose (Complete Service List)

`infra/docker/docker-compose.yml` — add to existing file:

```yaml
# ─── Shared Infrastructure (existing) ──────────────────────────────────────
services:
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_DB: researcher
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s; timeout: 5s; retries: 5

  rabbitmq:
    image: rabbitmq:3.12-management-alpine
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASS}
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
    ports: ["5672:5672", "15672:15672"]

# ─── Process 1 Workers (existing) ──────────────────────────────────────────
  arxiv-fetcher:
    build: .
    command: python -m src.main scheduler --interval 30
    env_file: .env
    depends_on: [postgres, rabbitmq]

  pdf-parser:
    build: .
    command: python -m src.main worker pdf_parser
    env_file: .env
    depends_on: [postgres, rabbitmq]

  concept-generator:
    build: .
    command: python -m src.main worker concept_generator
    env_file: .env
    depends_on: [postgres, rabbitmq]

  experiment-exploder:
    build: .
    command: python -m src.main worker experiment_exploder
    env_file: .env
    depends_on: [postgres, rabbitmq]

  code-executor:
    build: .
    command: python -m src.main worker code_executor
    env_file: .env
    depends_on: [postgres, rabbitmq]

  experiment-evaluator:
    build: .
    command: python -m src.main worker experiment_evaluator
    env_file: .env
    depends_on: [postgres, rabbitmq]

  obsidian-writer:
    build: .
    command: python -m src.main worker obsidian_writer
    env_file: .env
    volumes:
      - ${OBSIDIAN_VAULT_PATH}:/vault:rw
    depends_on: [postgres, rabbitmq]

  notifier:
    build: .
    command: python -m src.main worker notifier
    env_file: .env
    depends_on: [rabbitmq]

# ─── Process 2 Workers (new) ────────────────────────────────────────────────
  dgp-orchestrator:
    build: .
    command: python -m src.main worker dgp_orchestrator
    env_file: .env
    depends_on: [postgres, rabbitmq]

  dgp-structural-reader:
    build: .
    command: python -m src.main worker dgp_structural_reader
    env_file: .env
    volumes:
      - ${MARKET_DATA_PATH}:/data:ro
      - artifacts:/artifacts
    deploy:
      replicas: ${DGP_STRUCTURAL_READER_REPLICAS:-3}
    depends_on: [postgres, rabbitmq]

  dgp-interpreter:
    build: .
    command: python -m src.main worker dgp_interpreter
    env_file: .env
    depends_on: [postgres, rabbitmq]

  dgp-validator:
    build: .
    command: python -m src.main worker dgp_validator
    env_file: .env
    volumes:
      - ${MARKET_DATA_PATH}:/data:ro
      - artifacts:/artifacts
    deploy:
      replicas: ${DGP_VALIDATOR_REPLICAS:-3}
    depends_on: [postgres, rabbitmq]

  dgp-synthesizer:
    build: .
    command: python -m src.main worker dgp_synthesizer
    env_file: .env
    depends_on: [postgres, rabbitmq]

# ─── Process 3 Workers (new) ────────────────────────────────────────────────
  gp-scheduler:
    build: .
    command: python -m src.main scheduler gp --cron "${GP_CRON_SCHEDULE:-15 16 * * 1-5}"
    env_file: .env
    depends_on: [postgres, rabbitmq]

  gp-primitive-harvester:
    build: .
    command: python -m src.main worker gp_primitive_harvester
    env_file: .env
    depends_on: [postgres, rabbitmq]

  gp-runner:
    build: .
    command: python -m src.main worker gp_runner
    env_file: .env
    volumes:
      - ${MARKET_DATA_PATH}:/data:ro
      - artifacts:/artifacts
    depends_on: [postgres, rabbitmq]

# ─── Cross-Cutting ──────────────────────────────────────────────────────────
  eod-digest:
    build: .
    command: python -m src.main scheduler eod_digest --cron "${EOD_DIGEST_CRON:-0 17 * * 1-5}"
    env_file: .env
    depends_on: [postgres, rabbitmq]

volumes:
  postgres-data:
  rabbitmq-data:
  artifacts:

networks:
  default:
    name: researcher-net
```

---

## 12. Environment Variables (Complete Reference)

```bash
# ─── Core ──────────────────────────────────────────────────────────────────
ENVIRONMENT=production
LOG_LEVEL=INFO

# ─── LLM (global + per-agent overrides) ────────────────────────────────────
CUSTOM_LLM_BASE_URL=http://your-llm-endpoint/v1
CUSTOM_LLM_API_KEY=your-key
CUSTOM_LLM_MODEL=claude-sonnet-4-6

CUSTOM_LLM_CONCEPT_GEN_MODEL=claude-sonnet-4-6
CUSTOM_LLM_EXPERIMENT_EXPLODER_MODEL=claude-sonnet-4-6
CUSTOM_LLM_CODE_EXECUTOR_MODEL=claude-sonnet-4-6
CUSTOM_LLM_EVALUATOR_MODEL=claude-sonnet-4-6
CUSTOM_LLM_DGP_INTERPRETER_MODEL=claude-sonnet-4-6
CUSTOM_LLM_DGP_VALIDATOR_MODEL=claude-sonnet-4-6
CUSTOM_LLM_DGP_SYNTHESIZER_MODEL=claude-sonnet-4-6
CUSTOM_LLM_GP_HARVESTER_MODEL=claude-sonnet-4-6

# ─── PostgreSQL ─────────────────────────────────────────────────────────────
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=researcher
POSTGRES_USER=researcher
POSTGRES_PASSWORD=changeme

# ─── RabbitMQ ───────────────────────────────────────────────────────────────
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_VHOST=/

# ─── ArXiv (Process 1) ──────────────────────────────────────────────────────
ARXIV_FETCH_INTERVAL_MINUTES=30
ARXIV_CATEGORIES=q-fin.TR,q-fin.ST,stat.ML,cs.LG,math.ST,physics.data-an
ARXIV_MAX_RESULTS_PER_CATEGORY=50
ARXIV_DAYS_BACK=1

# ─── Code Executor ──────────────────────────────────────────────────────────
CODE_EXECUTOR_MAX_RETRIES=5
CODE_EXECUTOR_TIMEOUT_SECONDS=300

# ─── Feature Idea Store ─────────────────────────────────────────────────────
FEATURE_DEDUP_THRESHOLD=0.92            # cosine similarity above which we merge
NEAR_THRESHOLD_FACTOR=1.5               # how "near" threshold counts as promising

# ─── Obsidian ───────────────────────────────────────────────────────────────
OBSIDIAN_VAULT_PATH=/path/to/vault      # mounted into obsidian-writer container
OBSIDIAN_FEATURE_DIR=Research/Features  # subdirectory for feature notes
OBSIDIAN_DGP_DIR=Research/DGP

# ─── Slack ──────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL=#quant-research

# ─── DGP Research (Process 2) ────────────────────────────────────────────────
INSTRUMENTS=ES,NQ                       # comma-separated
MARKET_DATA_PATH=/path/to/parquet/data  # directory of {instrument}_{frequency}.parquet
DGP_ORCHESTRATOR_POLL_INTERVAL_SECONDS=10
DGP_DISPATCH_BATCH_SIZE=10
DGP_MAX_DEPTH=6
DGP_PRUNE_THRESHOLD=0.2                 # minimum priority score to enqueue child
DGP_SIGNIFICANCE_PVALUE=0.05
DGP_HYPOTHESES_PER_FINGERPRINT=5
DGP_VALIDATOR_MAX_RETRIES=5
DGP_VALIDATOR_TIMEOUT_SECONDS=300
DGP_STRUCTURAL_READER_REPLICAS=3
DGP_VALIDATOR_REPLICAS=3
DGP_SYNTHESIS_INTERVAL_HOURS=4

# ─── Genetic Programming (Process 3) ─────────────────────────────────────────
GP_CRON_SCHEDULE=15 16 * * 1-5
GP_POPULATION_SIZE=500
GP_GENERATIONS=100
GP_TOURNAMENT_SIZE=7
GP_CROSSOVER_PROB=0.7
GP_MUTATION_PROB=0.2
GP_PARSIMONY_COEFF=0.001
GP_FITNESS_METRIC=ic
GP_MAX_TREE_DEPTH=6
GP_OOS_SPLIT=0.3
GP_TOP_N_PROGRAMS=20
GP_PROMISING_IC_THRESHOLD=0.03
GP_PRIMITIVE_DEDUP_THRESHOLD=0.92
GP_PREDICTION_HORIZON_BARS=6

# ─── EOD Digest ─────────────────────────────────────────────────────────────
EOD_DIGEST_CRON=0 17 * * 1-5
```

---

## 13. New Modules Build Order

Dependencies listed explicitly. Build in this order.

```
1.  src/shared/harness/                       # KernelSessionManager — no dependencies
2.  src/shared/git_commit.py                  # ResearchRepoCommitter — no dependencies
3.  Alembic migration: feature_store_and_dgp  # adds 5 new tables
4.  src/workers/obsidian_writer/              # depends on: feature_ideas table, vault mount
5.  Modify ExperimentEvaluator                # add is_promising check + feature_ideas write
6.  Modify ConceptGenerator                   # add mathematical_structures + taxonomy feeder
7.  Modify SlackNotifier                      # add alert_type filtering, remove confidence gating
8.  Modify CodeExecutor                       # add harness, templates, typed recovery, git commit
9.  config/dgp/concept_taxonomy.yaml          # seed file (manual curation of initial entries)
10. src/workers/dgp_orchestrator/             # depends on: dgp_research_queue table
11. src/workers/dgp_structural_reader/        # depends on: harness, battery scripts, dgp_findings
    src/workers/dgp_structural_reader/battery/    # 8 static analysis scripts
12. src/workers/dgp_interpreter/              # depends on: concept_taxonomy.yaml
13. src/workers/dgp_validator/                # depends on: harness, templates, typed recovery, git commit
14. src/workers/dgp_synthesizer/              # depends on: dgp_findings, feature_ideas
15. src/workers/eod_digest/                   # depends on: all tables
16. src/workers/gp_primitive_harvester/       # depends on: feature_ideas, gp_primitives table
17. src/workers/gp_runner/                    # depends on: DEAP, gp_primitives.yaml, market data, git commit
18. Docker Compose additions                  # wire all new services
```

---

## 14. Code-Writing Agent Spec

Applies to: `CodeExecutor` (§5.6) and `HypothesisValidator` (§6.5). Both workers follow the same pattern — differ only in their system prompts and template variables.

### 14.1 Context Injection

Before any LLM call, the worker queries the kernel session for live data schema and injects it into the prompt. This eliminates the most common class of runtime errors (wrong column names, wrong dtypes, wrong assumptions about shape).

```python
# Executed inside the kernel session to gather schema info
SCHEMA_PROBE = """
import json
schema_info = {
    "columns": {col: str(dtype) for col, dtype in df.dtypes.items()},
    "shape": list(df.shape),
    "index_type": str(df.index.dtype),
    "date_range": [str(df.index[0]), str(df.index[-1])],
    "sample": df.head(3).to_string(),
    "series_len": len(series),
    "series_stats": {
        "mean": float(series.mean()),
        "std": float(series.std()),
        "min": float(series.min()),
        "max": float(series.max()),
    },
}
print(f"SCHEMA: {json.dumps(schema_info)}")
"""
```

The worker parses the `SCHEMA:` line and stores the result in a `CodeGenerationContext` dataclass:

```python
@dataclass
class CodeGenerationContext:
    # From message
    experiment_id:      str
    null_hypothesis:    str
    code_guidance:      str
    frequency:          str
    lookback_days:      int
    # From schema probe
    columns:            dict[str, str]      # col → dtype string
    shape:              tuple[int, int]
    date_range:         tuple[str, str]
    sample_rows:        str
    series_len:         int
    series_stats:       dict[str, float]
```

### 14.2 Script Template

The worker never asks the LLM to write a complete script. It injects fixed setup and teardown sections, and asks the LLM to fill in only the analysis block. The agent's output is slotted into `{agent_analysis_code}`.

```python
SCRIPT_TEMPLATE = '''
# ── INJECTED SETUP — DO NOT INCLUDE IN YOUR RESPONSE ──────────────────────
# Data already loaded in this kernel session:
#   df     : pd.DataFrame  shape={shape}  cols={columns}
#   series : np.ndarray    len={series_len}  (log returns, NaN-dropped)
#   Date range : {date_start} → {date_end}
#   Sample:
# {sample_rows_indented}
#
# Available helpers: show() — saves current figure and emits as PNG
# Pre-installed: numpy, pandas, scipy, statsmodels, arch, sklearn, hurst
# ── END INJECTED SETUP ─────────────────────────────────────────────────────

# Experiment : {experiment_id}
# H0         : {null_hypothesis}

{agent_analysis_code}

# ── INJECTED TEARDOWN — DO NOT INCLUDE IN YOUR RESPONSE ───────────────────
import json as _json
assert isinstance(metrics, dict), (
    "ERROR: you must define a variable named `metrics` (dict) "
    "containing your results before this line."
)
print("METRICS: " + _json.dumps({k: float(v) for k, v in metrics.items()}))
show()
# ── END INJECTED TEARDOWN ──────────────────────────────────────────────────
'''.strip()
```

The LLM sees only the injected comments (as context) and is asked to return the analysis block only — not a full script. The worker assembles the full script by substituting `{agent_analysis_code}` before passing to the kernel.

**LLM user message format:**

```python
USER_MESSAGE_TEMPLATE = """
Write the Python analysis block for the following experiment.

TASK: {code_guidance}
NULL HYPOTHESIS: {null_hypothesis}

DATA CONTEXT:
- DataFrame `df` is loaded. Columns: {columns}
- `series` is the log return array (len={series_len})
- Date range: {date_start} → {date_end}
- Sample stats: mean={mean:.6f}, std={std:.6f}

REQUIREMENTS:
1. At the end of your code, define a dict named `metrics` containing all numeric results.
2. Call show() after any matplotlib plot (not plt.show()).
3. State H0 as a comment before any hypothesis test.
4. Report both p-value and effect size for every test.
5. Train on first 70% of data, validate on last 30% — never mix.

Return ONLY the analysis code block. No import statements, no data loading,
no print(METRICS...) — those are injected automatically.
"""
```

### 14.3 Pre-Flight AST Check

Run before touching the kernel. Catches syntax errors instantly without consuming a kernel execution slot.

```python
import ast

def preflight_check(agent_code: str, context: CodeGenerationContext) -> str | None:
    """
    Returns an error string if the code should not be executed, None if clean.
    """
    # 1. Syntax check
    try:
        tree = ast.parse(agent_code)
    except SyntaxError as e:
        return f"SyntaxError at line {e.lineno}: {e.msg}"

    # 2. Forbidden pattern checks
    forbidden = []
    for node in ast.walk(tree):
        # Agent must not re-load data (it's already in session)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ("read_parquet", "read_csv"):
                forbidden.append("Do not load data files — df and series are already in session.")
        # Agent must not redefine series or df (would shadow injected data)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id in ("df", "series"):
                    forbidden.append(f"Do not reassign `{t.id}` — it is injected by the harness.")

    if forbidden:
        return "\n".join(forbidden)

    return None
```

If `preflight_check` returns a non-None string, send it directly to the fix loop (§14.4) as attempt 1 — the kernel is never touched.

### 14.4 Typed Error Recovery Loop

Different error types need different recovery strategies. A generic retry wastes attempts.

```python
class ErrorStrategy(str, Enum):
    FIX            = "fix"              # send back to LLM with traceback
    INSTALL_RETRY  = "install_and_retry" # pip install missing package, retry without LLM
    RESTART_FIX    = "restart_and_fix"  # restart kernel (clear state pollution), then fix
    ABORT          = "abort"            # do not retry

@dataclass
class ErrorClassification:
    strategy:       ErrorStrategy
    fix_hint:       str             # injected into fix-loop prompt
    missing_module: str | None = None

def classify_error(result: ExecutionResult) -> ErrorClassification:
    if result.status == "timeout":
        return ErrorClassification(ErrorStrategy.ABORT, "")

    tb = result.error_traceback or ""
    etype = result.error_type or ""

    if etype == "SyntaxError":
        line = extract_lineno(tb)
        return ErrorClassification(
            ErrorStrategy.FIX,
            f"SyntaxError at line {line}. Fix only that line."
        )

    if etype == "ModuleNotFoundError":
        module = extract_missing_module(result.stderr)
        return ErrorClassification(
            ErrorStrategy.INSTALL_RETRY,
            f"Install missing package: {module}",
            missing_module=module,
        )

    if etype in ("MemoryError", "RecursionError", "SystemError"):
        return ErrorClassification(
            ErrorStrategy.RESTART_FIX,
            f"{etype} — kernel will be restarted. Reduce memory usage or recursion depth."
        )

    if result.status == "ok" and "METRICS:" not in result.stdout:
        return ErrorClassification(
            ErrorStrategy.FIX,
            "Script ran without error but did not emit a METRICS line. "
            "Ensure your code defines a dict named `metrics` containing numeric results."
        )

    # Default: generic runtime error
    return ErrorClassification(ErrorStrategy.FIX, tb)
```

**Recovery loop orchestration:**

```python
async def execute_with_recovery(
    session_id: str,
    agent_code: str,
    context: CodeGenerationContext,
    harness: KernelSessionManager,
    llm: ILLMClient,
    max_attempts: int,
) -> ExecutionResult:

    attempt = 0
    current_code = agent_code

    while attempt < max_attempts:
        # Pre-flight (attempt 0 only on first run, always on LLM-fixed code)
        preflight_error = preflight_check(current_code, context)
        if preflight_error:
            classification = ErrorClassification(ErrorStrategy.FIX, preflight_error)
        else:
            script = assemble_script(SCRIPT_TEMPLATE, current_code, context)
            result = await harness.execute(session_id, script, timeout_seconds=CODE_EXECUTOR_TIMEOUT_SECONDS)

            if result.status == "ok" and "METRICS:" in result.stdout:
                return result  # success

            classification = classify_error(result)

        if classification.strategy == ErrorStrategy.ABORT:
            result.status = "timeout_failure"
            return result

        if classification.strategy == ErrorStrategy.INSTALL_RETRY:
            await harness.execute(
                session_id,
                f"import subprocess; subprocess.run(['pip', 'install', '-q', '{classification.missing_module}'])"
            )
            attempt += 1
            continue  # retry with same code

        if classification.strategy == ErrorStrategy.RESTART_FIX:
            await harness.restart(session_id)
            # Re-inject data loading prelude after restart
            await harness.execute(session_id, build_data_load_prelude(context))

        # FIX or RESTART_FIX: ask LLM to correct the code
        current_code = await llm.complete(
            system_prompt=get_system_prompt(context.worker_type),
            user_message=FIX_LOOP_PROMPT.format(
                code_guidance=context.code_guidance,
                null_hypothesis=context.null_hypothesis,
                error_type=classification.strategy.value,
                fix_hint=classification.fix_hint,
                original_code=current_code,
            )
        )
        attempt += 1

    result.status = "unrecoverable_failure"
    return result
```

### 14.5 System Prompts

**`CodeExecutor` system prompt** (`config/prompts/code_executor.txt`):

```
You are an expert quantitative researcher writing Python code to empirically test
financial time series hypotheses. Your code runs inside a Jupyter kernel that already
has data loaded. You are writing the analysis body only — setup and output are injected.

HARD CONSTRAINTS:
- Define a variable named `metrics` (dict, numeric values only) before your code ends.
- State H0 as a comment immediately before any hypothesis test.
- Train/test split: fit on first 70% of the series, evaluate on last 30%. Never mix.
- Report p-value AND effect size (Cohen's d, R², eta², etc.) for every test.
- No lookahead: features must be computable from data at time t using only t and earlier.
- Call show() for any plot. Do not call plt.show() or plt.savefig().
- Do not load data, do not import libraries — both are pre-injected.
- Do not reassign `df` or `series`.
- Keep code under 150 lines.
- Prefer scipy.stats and statsmodels over custom implementations.
- If a test assumption is violated (e.g. normality for a t-test), use the appropriate
  non-parametric alternative and note the assumption violation in a comment.

OUTPUT:
Return ONLY the analysis block. No markdown fences, no explanation.
The last statement in your code must be the `metrics` dict assignment.
```

**`HypothesisValidator` system prompt** (`config/prompts/dgp_validator.txt`):

```
You are an expert quantitative researcher implementing a specific statistical test
to validate or falsify a DGP hypothesis. The null hypothesis and discriminating test
are pre-specified — your job is to implement them faithfully and rigorously.

HARD CONSTRAINTS:
- Do NOT change the null hypothesis. Implement exactly the discriminating test specified.
- Apply Bonferroni correction if your implementation runs more than one test.
- Train/validation split: first 70% for model fitting, last 30% for validation. Hard boundary.
- Report for every test: p-value, effect size, 95% CI, and sample size n.
- For model comparison: report AIC and BIC alongside the primary test statistic.
- For process fitting (e.g. MLE): report convergence status and standard errors.
- Call show() for any diagnostic plot.
- Do not load data — it is already in the session from the Structural Reader phase.
- Do not reassign `df` or `series`.
- Define `metrics` dict before code ends.

metrics must contain at minimum:
  - One key ending in `_pvalue` for the primary discriminating test
  - One key ending in `_effect` for the effect size
  - `n_train` and `n_test` (sample sizes)
  - `conclusion`: "consistent" | "inconsistent" | "inconclusive"

Return ONLY the analysis block.
```

### 14.6 Fix-Loop Prompt

```python
FIX_LOOP_PROMPT = """
A Python analysis script produced an error. Fix it.

ORIGINAL TASK:
{code_guidance}

NULL HYPOTHESIS:
{null_hypothesis}

ERROR TYPE: {error_type}
FIX HINT:
{fix_hint}

ORIGINAL CODE:
{original_code}

Instructions:
- Fix ONLY the error described above.
- Do not change the analysis design, hypothesis, or metrics structure.
- Do not add data loading or import statements.
- Return ONLY the corrected analysis block. No explanation, no markdown.
"""
```

---

## 15. Git Integration

Every generated script is committed to a dedicated `research-code` git repository immediately after execution. This provides an off-VPS backup of all generated research code independent of the artifact store.

### 15.1 Module

**`src/shared/git_commit.py`**

```python
import git
from pathlib import Path
from dataclasses import dataclass

@dataclass
class CommitResult:
    hexsha:     str
    pushed:     bool
    skipped:    bool    # True if no changes (file already committed at this content)

class ResearchRepoCommitter:
    """
    Wraps a local git repo that tracks all generated research code.
    One instance per process — thread-safe for concurrent workers.
    """

    def __init__(self, repo_path: str, remote: str = "origin", push: bool = True):
        self.repo_path = Path(repo_path)
        self.repo = git.Repo(repo_path)
        self.remote = remote
        self.push_enabled = push

    def commit(
        self,
        file_paths: list[str],       # absolute paths to files to add
        message: str,                # commit message
        allow_empty: bool = False,
    ) -> CommitResult:
        """
        Stage files, commit, and push.
        Returns CommitResult. If nothing changed, returns skipped=True.
        """
        relative_paths = [str(Path(fp).relative_to(self.repo_path)) for fp in file_paths]

        self.repo.index.add(relative_paths)

        if not self.repo.index.diff("HEAD") and not allow_empty:
            return CommitResult(hexsha=self.repo.head.commit.hexsha, pushed=False, skipped=True)

        commit = self.repo.index.commit(message)

        pushed = False
        if self.push_enabled:
            self.repo.remote(self.remote).push()
            pushed = True

        return CommitResult(hexsha=commit.hexsha, pushed=pushed, skipped=False)
```

### 15.2 Research Code Repo Layout

A separate git repository at `RESEARCH_CODE_REPO_PATH`. Mounted read-write into `code-executor`, `dgp-validator`, and `gp-runner` containers.

```
research-code/
├── arxiv/
│   └── {paper_id}/
│       ├── {experiment_id}.py        # generated analysis script
│       └── {experiment_id}_out.txt   # stdout captured from execution
├── dgp/
│   └── {thread_id}/
│       ├── {finding_id}_analysis.py  # generated discriminating test
│       └── {finding_id}_out.txt
└── gp/
    └── {run_date}/
        ├── primitives.yaml           # primitive set used in this run
        └── runner.py                 # GP runner script for this session
```

### 15.3 Commit Points per Worker

**`CodeExecutor`** — commits after each experiment regardless of success/failure:

```python
# After execute_with_recovery() returns:
script_path = artifact_store.save_code(experiment_id, assembled_script)
stdout_path = artifact_store.save_output(experiment_id, result.stdout)

committer.commit(
    file_paths=[script_path, stdout_path],
    message=f"[arxiv] {paper_id}/{experiment_id}: {null_hypothesis[:72]}"
             f" — {result.status}",
)
```

**`HypothesisValidator`** — commits after each validation:

```python
script_path = artifact_store.save_code(finding_id, assembled_script)
stdout_path = artifact_store.save_output(finding_id, result.stdout)

significance = "significant" if validation_result.is_significant else "not_significant"
committer.commit(
    file_paths=[script_path, stdout_path],
    message=f"[dgp] {thread_id[:8]}/{finding_id[:8]}: "
             f"{hypothesis.process_class} — {significance}",
)
```

**`GPRunner`** — commits at the start of each run (before evolution begins), so the exact input state is always recoverable:

```python
committer.commit(
    file_paths=[primitives_path, runner_script_path],
    message=f"[gp] {run_date}: {total_primitives} primitives, "
             f"pop={GP_POPULATION_SIZE} gen={GP_GENERATIONS}",
)
```

### 15.4 Environment Variables (additions to §12)

```bash
# ─── Git Integration ────────────────────────────────────────────────────────
RESEARCH_CODE_REPO_PATH=/path/to/research-code   # local path, mounted into containers
RESEARCH_CODE_REMOTE_URL=git@github.com:org/research-code.git  # for initial clone/setup
RESEARCH_CODE_PUSH=true                          # false = commit only, no push
```

### 15.5 Docker Compose Additions

Add the `research-code` volume mount to code-writing containers:

```yaml
  code-executor:
    volumes:
      - ${RESEARCH_CODE_REPO_PATH}:/research-code:rw

  dgp-validator:
    volumes:
      - ${MARKET_DATA_PATH}:/data:ro
      - artifacts:/artifacts
      - ${RESEARCH_CODE_REPO_PATH}:/research-code:rw

  gp-runner:
    volumes:
      - ${MARKET_DATA_PATH}:/data:ro
      - artifacts:/artifacts
      - ${RESEARCH_CODE_REPO_PATH}:/research-code:rw
```

### 15.6 Initial Repo Setup (one-time)

```bash
git init research-code
cd research-code
mkdir -p arxiv dgp gp
touch .gitkeep arxiv/.gitkeep dgp/.gitkeep gp/.gitkeep
git add .
git commit -m "init research-code repo"
git remote add origin ${RESEARCH_CODE_REMOTE_URL}
git push -u origin main
```

---

## 16. DGP Research Session Management

### 16.1 Session vs. Thread — Two Separate Concepts

These must be managed independently. Conflating them means a container restart silently kills a multi-hour research investigation.

| Concept | What it is | Lifetime | Storage |
|---------|-----------|----------|---------|
| **Kernel session** | A live Jupyter kernel process | Container lifetime — dies on restart | `KernelSessionManager` (in-memory) |
| **Research thread** | The logical lineage of findings for one instrument+slice | Until exhausted — survives restarts | `dgp_thread_contexts` table (Postgres) |

The orchestrator manages both. When a kernel session dies (container restart, OOM), the thread is not lost — the orchestrator recreates the kernel session and re-injects the data loading prelude. The research context lives in the DB, not in the kernel.

### 16.2 Thread Context Object

Stored in `dgp_thread_contexts` (see §16.3). Read by every LLM call that needs research context. Written by the orchestrator after every `DGPValidationResult`. This is the primary mechanism for keeping agents oriented across iterations — they receive this, not raw finding history.

```python
@dataclass
class DGPThreadContext:
    thread_id:              str
    instrument:             str
    data_slice:             DataSlice

    # Phase 1 result — written once, never changes
    fingerprint_summary:    str         # 3–5 sentence prose of notable structure
    notable_features:       list[str]  # ordered list from StructuralFingerprint

    # Accumulates across iterations
    confirmed_properties:   list[str]  # properties validated as real in this data
                                        # e.g. "significant long memory (Hurst=0.71)"
    falsified_hypotheses:   list[str]  # process classes ruled out + one-line reason
                                        # e.g. "simple GARCH: cannot explain long memory"
    inconclusive:           list[str]  # tested but result was inconclusive
    tested_count:           int
    significant_count:      int

    # Rolling narrative — rewritten by orchestrator after each finding (§16.5)
    rolling_summary:        str        # current 3–5 sentence state of understanding

    # Open frontier — questions generated but not yet dispatched
    open_questions:         list[str]

    # Control
    depth:                  int
    iteration_count:        int
    status:                 str        # "active" | "exhausted" | "synthesized"
    last_updated:           datetime
```

### 16.3 Database Table

Add to Alembic migration `20250425_feature_store_and_dgp.py`:

```sql
CREATE TABLE dgp_thread_contexts (
    thread_id               TEXT PRIMARY KEY,
    instrument              TEXT NOT NULL,
    data_slice              JSONB NOT NULL,

    -- Phase 1 (written once)
    fingerprint_summary     TEXT,
    notable_features        JSONB DEFAULT '[]',

    -- Accumulated research state
    confirmed_properties    JSONB DEFAULT '[]',
    falsified_hypotheses    JSONB DEFAULT '[]',
    inconclusive            JSONB DEFAULT '[]',
    tested_count            INT  NOT NULL DEFAULT 0,
    significant_count       INT  NOT NULL DEFAULT 0,

    -- Rolling narrative
    rolling_summary         TEXT,

    -- Open frontier
    open_questions          JSONB DEFAULT '[]',

    -- Control
    depth                   INT  NOT NULL DEFAULT 0,
    iteration_count         INT  NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active','exhausted','synthesized')),
    created_at              TIMESTAMPTZ DEFAULT now(),
    last_updated            TIMESTAMPTZ DEFAULT now()
);
```

### 16.4 Orchestrator Lifecycle Methods

All of these live in `src/workers/dgp_orchestrator/context_manager.py`.

**`init_thread_context`** — called once, after the first `DGPFingerprintGenerated` for a thread:

```python
async def init_thread_context(
    fingerprint_msg: DGPFingerprintGenerated,
) -> DGPThreadContext:
    """
    Bootstraps a new thread context from the Phase 1 fingerprint.
    Generates the initial fingerprint_summary via a single cheap LLM call.
    """
    fingerprint_summary = await llm.complete(
        system_prompt=(
            "You are summarizing statistical properties of a financial time series. "
            "Be precise and factual. Use the values from the fingerprint directly."
        ),
        user_message=(
            f"Summarize the following structural fingerprint in 3–5 sentences. "
            f"Focus on what is most unusual or distinctive compared to a random walk.\n\n"
            f"{json.dumps(fingerprint_msg.fingerprint.__dict__, indent=2)}"
        ),
    )

    ctx = DGPThreadContext(
        thread_id=fingerprint_msg.thread_id,
        instrument=fingerprint_msg.data_slice.instrument,
        data_slice=fingerprint_msg.data_slice,
        fingerprint_summary=fingerprint_summary,
        notable_features=fingerprint_msg.notable_features,
        rolling_summary=fingerprint_summary,  # seed rolling summary with fingerprint
        confirmed_properties=[],
        falsified_hypotheses=[],
        inconclusive=[],
        tested_count=0,
        significant_count=0,
        open_questions=[],
        depth=0,
        iteration_count=0,
        status="active",
        last_updated=datetime.utcnow(),
    )
    await db.upsert_thread_context(ctx)
    return ctx
```

**`update_thread_context`** — called by orchestrator after every `DGPValidationResult`:

```python
async def update_thread_context(
    thread_id: str,
    result: DGPValidationResult,
) -> DGPThreadContext:
    ctx = await db.get_thread_context(thread_id)

    # 1. Update confirmed / falsified / inconclusive lists
    conclusion = result.metrics.get("conclusion", "inconclusive")
    process_class = result.hypothesis.process_class

    if conclusion == "consistent" and result.is_significant:
        # Append the key validated property, not just the process class
        key_property = (
            f"{process_class}: {result.findings_prose[:120].split('.')[0]}"
        )
        ctx.confirmed_properties.append(key_property)
    elif conclusion == "inconsistent":
        ctx.falsified_hypotheses.append(
            f"{process_class}: {result.findings_prose[:80].split('.')[0]}"
        )
    else:
        ctx.inconclusive.append(process_class)

    ctx.tested_count += 1
    if result.is_significant:
        ctx.significant_count += 1

    # 2. Merge new open questions (deduplicate against existing)
    for question in result.open_questions:
        embedding = await llm.embed(question)
        if not await db.similar_question_exists(thread_id, embedding, threshold=0.88):
            ctx.open_questions.append(question)

    # 3. Update depth
    ctx.depth = max(ctx.depth, result.depth)
    ctx.iteration_count += 1

    # 4. Rewrite rolling summary (cheap LLM call — short prompt, short output)
    ctx.rolling_summary = await llm.complete(
        system_prompt=ROLLING_SUMMARY_SYSTEM_PROMPT,
        user_message=ROLLING_SUMMARY_USER_TEMPLATE.format(
            prior_summary=ctx.rolling_summary,
            new_finding_prose=result.findings_prose,
            conclusion=conclusion,
            process_class=process_class,
            confirmed=ctx.confirmed_properties,
            falsified=ctx.falsified_hypotheses,
        ),
    )

    ctx.last_updated = datetime.utcnow()
    await db.upsert_thread_context(ctx)
    return ctx
```

**Rolling summary prompts** (`config/prompts/rolling_summary.txt`):

```python
ROLLING_SUMMARY_SYSTEM_PROMPT = """
You maintain a running scientific summary of a DGP research thread.
Update the summary concisely. Be precise: use numbers from findings where available.
Never speculate beyond the evidence. Maximum 5 sentences.
"""

ROLLING_SUMMARY_USER_TEMPLATE = """
PRIOR SUMMARY:
{prior_summary}

NEW FINDING:
Process class tested: {process_class}
Conclusion: {conclusion}
Finding: {new_finding_prose}

CURRENT CONFIRMED PROPERTIES: {confirmed}
CURRENT FALSIFIED: {falsified}

Rewrite the summary (3–5 sentences) incorporating this new finding.
State what has been confirmed, what has been ruled out, and what the
leading DGP candidate currently is. Return only the updated summary.
"""
```

**`should_continue`** — called by orchestrator after `update_thread_context`. Returns `(bool, reason_string)`:

```python
async def should_continue(thread_id: str) -> tuple[bool, str]:
    ctx = await db.get_thread_context(thread_id)

    # Hard depth limit
    if ctx.depth >= DGP_MAX_DEPTH:
        return False, "max_depth_reached"

    # Hard iteration limit (safety valve — prevents runaway threads)
    if ctx.iteration_count >= DGP_MAX_ITERATIONS:
        return False, "max_iterations_reached"

    # Diminishing returns: last N consecutive findings all not significant
    recent = await db.get_recent_findings(
        thread_id, n=DGP_DIMINISHING_RETURNS_WINDOW  # default 3
    )
    if (
        len(recent) == DGP_DIMINISHING_RETURNS_WINDOW
        and not any(f.is_significant for f in recent)
    ):
        return False, "diminishing_returns"

    # Novelty collapse: open questions too similar to already-answered ones
    if ctx.open_questions:
        answered_embeddings = await db.get_finding_question_embeddings(thread_id)
        if answered_embeddings:
            new_embeddings = [
                await llm.embed(q) for q in ctx.open_questions[:5]
            ]
            max_sim = max_pairwise_cosine(new_embeddings, answered_embeddings)
            if max_sim > DGP_NOVELTY_COLLAPSE_THRESHOLD:  # default 0.88
                return False, f"novelty_collapsed (max_sim={max_sim:.3f})"

    # No open questions and nothing left to dispatch
    if not ctx.open_questions:
        queued = await db.count_queued_jobs(thread_id)
        if queued == 0:
            return False, "frontier_exhausted"

    return True, "continue"
```

When `should_continue` returns `False`, the orchestrator:
1. Sets `dgp_thread_contexts.status = 'exhausted'`
2. Immediately publishes a `DGPSynthesisRequest` for this thread (doesn't wait for the periodic synthesizer)
3. Logs the reason

### 16.5 Context Injection into LLM Calls

Every LLM call in the DGP pipeline receives the thread context. The context is formatted as a structured block prepended to the user message — not buried in the system prompt, so the model can reference it explicitly.

```python
def format_thread_context_block(ctx: DGPThreadContext) -> str:
    """Rendered into every DGPInterpreter and HypothesisValidator user message."""
    falsified_str = "\n".join(f"  - {h}" for h in ctx.falsified_hypotheses) or "  None yet"
    confirmed_str = "\n".join(f"  - {p}" for p in ctx.confirmed_properties) or "  None yet"

    return f"""
RESEARCH THREAD CONTEXT (read before generating anything)
══════════════════════════════════════════════════════════
Instrument : {ctx.instrument}  |  Depth: {ctx.depth}  |  Iterations: {ctx.iteration_count}

FINGERPRINT SUMMARY:
{ctx.fingerprint_summary}

CURRENT UNDERSTANDING:
{ctx.rolling_summary}

CONFIRMED PROPERTIES:
{confirmed_str}

ALREADY FALSIFIED (do not re-propose these):
{falsified_str}

INCONCLUSIVE (may revisit with different approach):
{", ".join(ctx.inconclusive) or "None"}
══════════════════════════════════════════════════════════
""".strip()
```

**DGPInterpreter user message** injects this block before the fingerprint details:

```python
user_message = f"""
{format_thread_context_block(ctx)}

STRUCTURAL FINGERPRINT:
{json.dumps(fingerprint.notable_features, indent=2)}

Generate {N} DGP hypotheses consistent with this fingerprint.
Do not propose any process class listed under ALREADY FALSIFIED.
At least one hypothesis must combine concepts from two different domains.
For each hypothesis, specify the exact discriminating test that would
confirm or deny it, and the natural features implied if it is true.
"""
```

**HypothesisValidator user message** injects this block before the specific hypothesis:

```python
user_message = f"""
{format_thread_context_block(ctx)}

YOUR SPECIFIC TASK:
Hypothesis   : {hypothesis.prose}
Process class: {hypothesis.process_class}
Discriminating test: {hypothesis.discriminating_test}
Null hypothesis: {null_hypothesis}

Write the analysis block that implements this test.
Use the confirmed properties above as prior context when interpreting results.
"""
```

### 16.6 Kernel Namespace Isolation

Every analysis block executed in a persistent DGP kernel session is wrapped in a function to prevent local variable leakage across iterations. After N iterations, the kernel namespace contains only `df`, `series`, and the per-finding `_metrics_{id}` results — not the hundreds of intermediate variables from every prior analysis.

```python
ISOLATED_WRAPPER = """
def _run_{finding_id}(df, series):
{indented_analysis_code}
    return metrics

_metrics_{finding_id} = _run_{finding_id}(df, series)
metrics = _metrics_{finding_id}
"""

def wrap_analysis_code(finding_id: str, analysis_code: str) -> str:
    indented = "\n".join(f"    {line}" for line in analysis_code.splitlines())
    return ISOLATED_WRAPPER.format(
        finding_id=finding_id.replace("-", "_"),
        indented_analysis_code=indented,
    )
```

The full assembled script becomes:

```
[INJECTED SETUP COMMENTS — data schema, date range, sample]

def _run_{finding_id}(df, series):
    [agent analysis code]
    return metrics

_metrics_{finding_id} = _run_{finding_id}(df, series)
metrics = _metrics_{finding_id}

[INJECTED TEARDOWN — assert metrics, print METRICS:, show()]
```

The pre-flight AST check (§14.3) is applied to the agent's inner block before wrapping.

### 16.7 Kernel Health Check and Session Recovery

The orchestrator tracks kernel health independently of thread health. After every `KERNEL_HEALTH_CHECK_INTERVAL` validations within a thread (default 10), it runs a health probe in the kernel session:

```python
KERNEL_HEALTH_PROBE = """
import json
_health = {
    "df_rows": len(df),
    "df_cols": len(df.columns),
    "series_len": len(series),
    "series_has_nan": bool(np.isnan(series).any()),
    "memory_mb": round(__import__('psutil').Process().memory_info().rss / 1e6, 1),
}
print("HEALTH: " + json.dumps(_health))
"""

async def check_kernel_health(
    session_id: str,
    harness: KernelSessionManager,
    expected_rows: int,
    expected_series_len: int,
) -> tuple[bool, str]:
    result = await harness.execute(session_id, KERNEL_HEALTH_PROBE, timeout_seconds=10)

    if "HEALTH:" not in result.stdout:
        return False, "health_probe_failed"

    health = json.loads(result.stdout.split("HEALTH: ")[1].split("\n")[0])

    if health["df_rows"] != expected_rows:
        return False, f"df corrupted: expected {expected_rows} rows, got {health['df_rows']}"
    if health["series_has_nan"]:
        return False, "series contains NaN — data was mutated"
    if health["memory_mb"] > KERNEL_MAX_MEMORY_MB:  # default 4096
        return False, f"memory {health['memory_mb']}MB exceeds limit"

    return True, "ok"
```

**Recovery procedure** when health check fails or kernel session is missing (container restart):

```python
async def recover_kernel_session(
    thread_id: str,
    data_slice: DataSlice,
    harness: KernelSessionManager,
) -> None:
    """
    Recreates a kernel session for a thread after restart or health failure.
    Thread context in DB is unaffected — only execution state is lost.
    """
    session_id = f"dgp_{thread_id}"

    # Destroy existing session if zombie
    if await harness.session_alive(session_id):
        await harness.destroy_session(session_id)

    # Recreate and re-inject data loading prelude
    await harness.create_session(session_id)
    data_path = resolve_data_path(data_slice)
    prelude = build_data_load_prelude(data_slice, data_path)
    await harness.execute(session_id, prelude, timeout_seconds=60)

    # Verify recovery succeeded
    healthy, reason = await check_kernel_health(
        session_id, harness,
        expected_rows=data_slice.expected_rows,
        expected_series_len=data_slice.expected_series_len,
    )
    if not healthy:
        raise KernelRecoveryError(f"Recovery failed: {reason}")
```

The orchestrator calls `recover_kernel_session` in two cases:
1. Before dispatching any job for a thread when `harness.session_alive(session_id)` returns `False`
2. After a failed health check (the health check itself triggers recovery)

Previously completed analyses are not re-run — their results are already in `dgp_findings`. Only the execution environment (loaded data) needs to be restored.

### 16.8 Complete Thread Lifecycle

```
BIRTH
  Orchestrator seeds dgp_research_queue with data slice
    ↓
PHASE 1 — StructuralReader
  Creates kernel session "dgp_{thread_id}" (or recovers existing)
  Loads data via DATA_LOAD_TEMPLATE
  Runs 8-script analysis battery (static code, no LLM)
  Emits DGPFingerprintGenerated
    ↓
  Orchestrator: init_thread_context() → dgp_thread_contexts row created
    ↓
PHASE 2 — DGPInterpreter
  Reads ThreadContext (fingerprint_summary + rolling_summary)
  Generates N hypotheses, excluding falsified_hypotheses
  Creates N dgp_findings rows (phase=interpretation)
  Publishes N DGPValidateRequest messages
    ↓
PHASE 3 — HypothesisValidator (×N in parallel)
  Reuses kernel session "dgp_{thread_id}"
  Injects ThreadContext block into user message
  LLM generates analysis code for discriminating test
  Code wrapped in isolation function, AST-checked, executed
  Error recovery loop if needed (§14.4)
  Emits DGPValidationResult
  Commits script + output to research-code repo (§15.3)
    ↓
  Orchestrator (per result):
    update_thread_context()         → updates confirmed/falsified/rolling_summary
    should_continue()?
      YES → dispatch highest-priority open questions from ctx.open_questions
             (filtered by priority score, pruned if priority < DGP_PRUNE_THRESHOLD)
      NO  → mark thread exhausted, fire immediate DGPSynthesisRequest
    every KERNEL_HEALTH_CHECK_INTERVAL validations → check_kernel_health()
      FAIL → recover_kernel_session(), continue
    ↓
    [loop back to PHASE 3 with new validation jobs,
     or back to PHASE 2 if orchestrator decides a new
     interpretation pass is needed at a deeper depth]
    ↓
EXHAUSTION
  status = 'exhausted'
  DGPSynthesisRequest published
    ↓
SYNTHESIS — DGPSynthesizer
  Reads ThreadContext (rolling_summary, confirmed_properties, all findings)
  Generates coherent DGP model + implied features
  Writes feature_ideas row
  Publishes FeatureIdeaCreated → ObsidianWriter + Slack
  Sets status = 'synthesized'
```

### 16.9 Environment Variables (additions to §12)

```bash
# ─── DGP Thread / Session Management ────────────────────────────────────────
DGP_MAX_ITERATIONS=50               # hard cap on validations per thread
DGP_DIMINISHING_RETURNS_WINDOW=3    # consecutive non-significant findings before stop
DGP_NOVELTY_COLLAPSE_THRESHOLD=0.88 # max cosine similarity before declaring repetition
KERNEL_HEALTH_CHECK_INTERVAL=10     # run health probe every N validations
KERNEL_MAX_MEMORY_MB=4096           # restart kernel if RSS exceeds this
```

### 16.10 Build Order Additions (update §13)

Insert after step 10 (dgp_orchestrator):

```
10a. src/workers/dgp_orchestrator/context_manager.py   # DGPThreadContext, lifecycle methods
10b. config/prompts/rolling_summary.txt                # rolling summary prompts
10c. config/prompts/dgp_interpreter.txt                # thread-context-aware system prompt
10d. config/prompts/dgp_validator.txt                  # (update) inject context block format
```

---

## 17. Gap Resolutions

Addresses every issue identified in the architectural review. Organised by severity: critical → significant → spec gaps → small.

---

### 17.1 CRITICAL — Kernel Session Ownership: Validators Get Ephemeral Sessions

**Problem:** With N parallel `dgp-validator` replicas, multiple workers can execute code concurrently on the same persistent kernel session (`dgp_{thread_id}`), causing namespace collisions and silent metric corruption.

**Resolution:** Hypothesis Validators no longer share the Structural Reader's persistent kernel session. Each validation job gets its own ephemeral session — exactly like Process 1's CodeExecutor. The persistent session is owned exclusively by the StructuralReader for Phase 1 analysis.

**Revised kernel session ownership:**

| Worker | Session type | Session key | Lifetime |
|--------|-------------|-------------|---------|
| StructuralReader | Persistent | `sr_{thread_id}` | Thread lifetime, owned exclusively |
| HypothesisValidator | Ephemeral | `val_{finding_id}` | Single validation, destroyed after |
| CodeExecutor (P1) | Ephemeral | `exp_{experiment_id}` | Single experiment, destroyed after |

The StructuralReader session stays alive for the thread lifetime so the orchestrator can run health probes and kernel restarts against it. Validators load the data themselves via the standard `DATA_LOAD_TEMPLATE` (data is a read-only parquet file — multiple readers are safe). The trade-off is a ~2s data load per validation instead of zero; this is acceptable given it eliminates a class of silent corruption.

**`dgp_thread_contexts` addition:** Store the `data_path` resolved during Phase 1 so validators know exactly which file to load without re-resolving it:

```sql
ALTER TABLE dgp_thread_contexts
    ADD COLUMN data_path TEXT,              -- absolute path to parquet file
    ADD COLUMN expected_rows INT,           -- for health check validation
    ADD COLUMN expected_series_len INT;     -- for health check validation
```

**`HypothesisValidator` session lifecycle:**

```python
async def run_validation(msg: DGPValidateRequest) -> DGPValidationResult:
    ctx = await db.get_thread_context(msg.thread_id)
    session_id = f"val_{msg.finding_id.replace('-', '_')}"

    try:
        await harness.create_session(session_id)
        # Load data into this ephemeral session
        prelude = build_data_load_prelude(ctx.data_slice, ctx.data_path)
        await harness.execute(session_id, prelude, timeout_seconds=60)

        # Generate and execute the discriminating test
        result = await execute_with_recovery(session_id, ...)
        return build_validation_result(result, msg)
    finally:
        await harness.destroy_session(session_id)   # always clean up
```

---

### 17.2 CRITICAL — Message Ordering Buffer for Per-Thread Results

**Problem:** RabbitMQ does not guarantee delivery order. Two validators finishing hypotheses H1 and H2 for the same thread can deliver results in any order. `update_thread_context` called out of order produces an incoherent rolling summary.

**Resolution:** The orchestrator buffers all `DGPValidationResult` messages in a DB table and processes them in strict per-thread sequence order before updating the thread context.

**New table** (add to migration `20250425_feature_store_and_dgp.py`):

```sql
CREATE TABLE dgp_result_buffer (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id       TEXT NOT NULL,
    finding_id      TEXT NOT NULL UNIQUE,
    depth           INT  NOT NULL,
    iteration_seq   INT  NOT NULL,          -- assigned by orchestrator at dispatch time
    result_json     JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'done')),
    received_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX dgp_result_buffer_thread_idx
    ON dgp_result_buffer (thread_id, status, depth, iteration_seq);
```

`iteration_seq` is set by the orchestrator at dispatch time (not at result time), guaranteeing a stable ordering:

```sql
-- At dispatch time, stamp the finding with its sequence number
UPDATE dgp_findings
SET iteration_seq = (
    SELECT COALESCE(MAX(iteration_seq), 0) + 1
    FROM dgp_findings
    WHERE thread_id = :thread_id
)
WHERE id = :finding_id;
```

**Orchestrator result processing loop:**

```python
async def process_result_buffer(thread_id: str) -> None:
    """
    Processes all pending results for a thread in strict iteration_seq order.
    Skips if the next expected result hasn't arrived yet.
    """
    while True:
        # Get the lowest pending sequence number for this thread
        next_result = await db.fetch_one("""
            SELECT * FROM dgp_result_buffer
            WHERE thread_id = :thread_id AND status = 'pending'
            ORDER BY depth ASC, iteration_seq ASC
            LIMIT 1
        """, thread_id=thread_id)

        if not next_result:
            break  # nothing to process

        # Check all lower-sequence results are done (no gaps)
        gap = await db.fetch_one("""
            SELECT 1 FROM dgp_result_buffer
            WHERE thread_id = :thread_id
              AND status = 'pending'
              AND (depth < :depth OR (depth = :depth AND iteration_seq < :seq))
            LIMIT 1
        """, thread_id=thread_id, depth=next_result.depth, seq=next_result.iteration_seq)

        if gap:
            break  # predecessor not yet received — wait

        # Mark processing and update context
        await db.execute(
            "UPDATE dgp_result_buffer SET status='processing' WHERE id=:id",
            id=next_result.id
        )
        result = DGPValidationResult(**next_result.result_json)
        await update_thread_context(thread_id, result)

        await db.execute(
            "UPDATE dgp_result_buffer SET status='done' WHERE id=:id",
            id=next_result.id
        )
```

The orchestrator calls `process_result_buffer(thread_id)` each time a result arrives. If predecessors haven't arrived yet, it returns immediately — the buffer will be drained when those arrive.

---

### 17.3 CRITICAL — Stale Dispatched Job Watchdog

**Problem:** If a validator worker crashes after receiving a message but before publishing a result, the `dgp_research_queue` job stays in `dispatched` state permanently. The thread silently stalls with no error.

**Resolution:** Add a `dispatched_at` expiry and a watchdog loop in the orchestrator that re-queues stale jobs.

**Schema change:**

```sql
ALTER TABLE dgp_research_queue
    ADD COLUMN dispatch_timeout_at TIMESTAMPTZ;  -- set at dispatch time

-- Index for watchdog query
CREATE INDEX dgp_queue_stale_idx
    ON dgp_research_queue (status, dispatch_timeout_at)
    WHERE status = 'dispatched';
```

At dispatch time:
```python
timeout_minutes = int(os.environ.get("DGP_DISPATCH_TIMEOUT_MINUTES", "30"))
db.update(job.id,
    status='dispatched',
    dispatched_at=now(),
    dispatch_timeout_at=now() + timedelta(minutes=timeout_minutes),
)
```

**Watchdog loop** — runs inside the orchestrator's main async loop:

```python
async def watchdog_loop() -> None:
    while True:
        # Re-queue any jobs that timed out without a result
        requeued = await db.execute("""
            UPDATE dgp_research_queue
            SET status       = 'queued',
                dispatched_at = NULL,
                dispatch_timeout_at = NULL,
                priority      = priority + 0.1   -- boost priority so it retries promptly
            WHERE status = 'dispatched'
              AND dispatch_timeout_at < now()
            RETURNING id, thread_id
        """)

        for job in requeued:
            logger.warning(
                f"Re-queued stale job {job.id} for thread {job.thread_id}"
            )

        await asyncio.sleep(60)  # run every minute
```

Also add to `dgp_research_queue`: a `retry_count` column. Jobs that are re-queued more than `DGP_MAX_JOB_RETRIES` (default 3) times are marked `pruned` and logged for manual inspection.

---

### 17.4 SIGNIFICANT — Thread Context Distillation (Prevent String Explosion)

**Problem:** `confirmed_properties`, `falsified_hypotheses`, and `rolling_summary` grow unboundedly. At iteration 40+, the context block injected into every LLM call is 8–10KB — degrading reasoning quality and burning context window.

**Resolution:** Every `DGP_CONTEXT_DISTILL_INTERVAL` iterations (default 10), run a distillation pass that compresses the lists to their most significant entries and rewrites the rolling summary from scratch.

**`distill_thread_context`** — called inside `update_thread_context` at the distillation checkpoint:

```python
DISTILL_INTERVAL = int(os.environ.get("DGP_CONTEXT_DISTILL_INTERVAL", "10"))
DISTILL_MAX_ENTRIES = int(os.environ.get("DGP_CONTEXT_MAX_ENTRIES", "5"))

async def distill_thread_context(ctx: DGPThreadContext, llm: ILLMClient) -> DGPThreadContext:
    """
    Compresses accumulated lists to top-N most informative entries.
    Rewrites rolling_summary from the full confirmed/falsified state.
    Only runs at distillation checkpoints to avoid per-iteration LLM cost.
    """
    if ctx.iteration_count % DISTILL_INTERVAL != 0:
        return ctx

    # Distill confirmed_properties → top N
    if len(ctx.confirmed_properties) > DISTILL_MAX_ENTRIES:
        ctx.confirmed_properties = json.loads(await llm.complete(
            system_prompt=(
                "You are distilling a list of confirmed scientific properties. "
                "Select the most significant entries — those that most constrain "
                "the space of plausible DGP models. Return a JSON array of strings only."
            ),
            user_message=(
                f"Select the {DISTILL_MAX_ENTRIES} most significant from:\n"
                + json.dumps(ctx.confirmed_properties, indent=2)
            ),
        ))

    # Distill falsified_hypotheses → top N (those ruling out most territory)
    if len(ctx.falsified_hypotheses) > DISTILL_MAX_ENTRIES:
        ctx.falsified_hypotheses = json.loads(await llm.complete(
            system_prompt=(
                "You are distilling a list of falsified DGP hypotheses. "
                "Select those that rule out the broadest classes of process. "
                "Return a JSON array of strings only."
            ),
            user_message=(
                f"Select the {DISTILL_MAX_ENTRIES} most important from:\n"
                + json.dumps(ctx.falsified_hypotheses, indent=2)
            ),
        ))

    # Rewrite rolling_summary fresh from distilled state
    ctx.rolling_summary = await llm.complete(
        system_prompt=ROLLING_SUMMARY_SYSTEM_PROMPT,
        user_message=(
            f"Write a 3–5 sentence summary of this DGP research thread.\n\n"
            f"Instrument: {ctx.instrument}\n"
            f"Fingerprint: {ctx.fingerprint_summary}\n"
            f"Confirmed: {json.dumps(ctx.confirmed_properties)}\n"
            f"Falsified: {json.dumps(ctx.falsified_hypotheses)}\n"
            f"Iterations: {ctx.iteration_count}\n\n"
            f"State what is known, what is ruled out, and what the leading DGP candidate is."
        ),
    )

    return ctx
```

Call `distill_thread_context` inside `update_thread_context` after updating lists, before saving to DB. The context block rendered by `format_thread_context_block` (§16.5) is now bounded at `DISTILL_MAX_ENTRIES` entries regardless of thread age.

**`dgp_thread_contexts` schema addition:**
```sql
ALTER TABLE dgp_thread_contexts
    ADD COLUMN last_distilled_at TIMESTAMPTZ;
```

---

### 17.5 SIGNIFICANT — Hypothesis Space Local Maxima: Pivot Trigger

**Problem:** The pipeline can get stuck exploring variants of one process class (e.g., all 5 hypotheses are cascade variants, all fail, all open questions are cascade follow-ups). The novelty collapse check catches exact repetition but not topic lock-in.

**Resolution:** After N consecutive failures within the same process class, the orchestrator injects a pivot instruction into the next DGPInterpreter call, explicitly forcing it away from the trapped class.

**Detection** — called inside `should_continue` before returning `True`:

```python
def detect_local_maxima(
    ctx: DGPThreadContext,
    window: int = 3,
) -> str | None:
    """
    Returns the trapped process class name if the last `window` falsified
    hypotheses are all the same class. None otherwise.
    """
    if len(ctx.falsified_hypotheses) < window:
        return None

    recent = ctx.falsified_hypotheses[-window:]
    # Extract process class (text before the first colon)
    classes = [h.split(":")[0].strip() for h in recent]
    if len(set(classes)) == 1:
        return classes[0]
    return None
```

**Pivot instruction** — appended to DGPInterpreter user message when a trapped class is detected:

```python
trapped_class = detect_local_maxima(ctx)
pivot_instruction = ""
if trapped_class:
    pivot_instruction = f"""
⚠ PIVOT REQUIRED: The last {window} validations all tested variants of
"{trapped_class}" and were falsified. Do NOT propose any hypothesis related
to {trapped_class}. Generate hypotheses from completely different domains.
Consider cross-domain combinations not yet attempted.
"""
```

Store the `trapped_class` in `dgp_thread_contexts.pivot_class` (nullable TEXT) so the instruction persists across message hops:

```sql
ALTER TABLE dgp_thread_contexts
    ADD COLUMN pivot_class TEXT;  -- non-null when pivot is active
```

Clear `pivot_class` once a hypothesis from a different class returns significant.

---

### 17.6 SIGNIFICANT — Concept Taxonomy Moved to Database

**Problem:** `config/dgp/concept_taxonomy.yaml` is written by multiple `concept-generator` container instances simultaneously. YAML has no atomic append and no row-level locking — concurrent writes corrupt the file.

**Resolution:** Move the taxonomy to a PostgreSQL table. Reads use vector search (already have pgvector) instead of loading the full file. Writes use `INSERT ... ON CONFLICT DO NOTHING` — safe for any number of concurrent writers.

**New table** (add to migration):

```sql
CREATE TABLE dgp_concept_taxonomy (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                            TEXT NOT NULL,
    domain                          TEXT NOT NULL,
    source                          TEXT NOT NULL DEFAULT 'seed',
                                        -- 'seed' | 'arxiv_intake'
    source_ref                      TEXT,       -- arxiv_id if source='arxiv_intake'
    predicted_fingerprint_indicators JSONB DEFAULT '[]',
    discriminating_test             TEXT,
    implied_features                JSONB DEFAULT '[]',
    embedding                       vector(1536),
    created_at                      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (lower(name))
);
CREATE INDEX concept_taxonomy_embedding_idx
    ON dgp_concept_taxonomy USING hnsw (embedding vector_cosine_ops);
```

**ConceptGenerator write** (replaces YAML append in §10):

```python
for struct in concept.mathematical_structures:
    embedding = await llm.embed(struct)
    await db.execute("""
        INSERT INTO dgp_concept_taxonomy (name, domain, source, source_ref, embedding)
        VALUES (:name, :domain, 'arxiv_intake', :arxiv_id, :embedding)
        ON CONFLICT (lower(name)) DO NOTHING
    """, name=struct, domain=concept.origin_domain,
         arxiv_id=paper_id, embedding=embedding)
```

**DGPInterpreter read** — instead of loading all entries, use vector search to retrieve the N concepts most relevant to the observed fingerprint:

```python
async def get_relevant_concepts(
    fingerprint_text: str,
    n: int = 20,
) -> list[dict]:
    """
    Returns top-N taxonomy entries most semantically similar to the fingerprint.
    At scale this prevents blowing the LLM context with 1000+ taxonomy entries.
    """
    embedding = await llm.embed(fingerprint_text)
    return await db.fetch_all("""
        SELECT name, domain, discriminating_test, implied_features,
               1 - (embedding <=> :emb) AS similarity
        FROM dgp_concept_taxonomy
        ORDER BY embedding <=> :emb
        LIMIT :n
    """, emb=embedding, n=n)
```

Seed the table via a one-time migration script that reads the existing `config/dgp/concept_taxonomy.yaml` and inserts all entries.

---

### 17.7 SIGNIFICANT — Feature Idea Dedup Race: Advisory Lock

**Problem:** The dedup algorithm (§9) is a check-then-insert: two concurrent workers can both pass the similarity check and both insert near-identical feature ideas before either has committed.

**Resolution:** Use a PostgreSQL session-level advisory lock keyed to a hash of the idea title. Only one writer at a time can execute the check+insert for semantically similar ideas.

```python
async def dedup_or_insert(idea: FeatureIdeaCandidate, db, llm) -> str:
    embedding = await llm.embed(f"{idea.title}. {idea.summary}")

    # Advisory lock key: stable hash of the first 60 chars of title
    # Two ideas with the same ~title compete for the same lock slot
    lock_key = abs(hash(idea.title[:60])) % (2**31)

    async with db.transaction():
        # Acquire advisory lock scoped to this transaction
        await db.execute("SELECT pg_advisory_xact_lock(:key)", key=lock_key)

        existing = await db.fetch_one("""
            SELECT id, title, 1 - (embedding <=> :emb) AS sim
            FROM feature_ideas
            ORDER BY embedding <=> :emb
            LIMIT 1
        """, emb=embedding)

        if existing and existing.sim >= FEATURE_DEDUP_THRESHOLD:
            # Merge: append evidence AND append source_ref
            await db.execute("""
                UPDATE feature_ideas
                SET evidence       = evidence || :new_evidence,
                    source_refs    = source_refs || :new_ref::jsonb,
                    is_promising   = is_promising OR :new_promising,
                    updated_at     = now()
                WHERE id = :id
            """, id=existing.id, new_evidence=json.dumps(idea.evidence),
                 new_ref=json.dumps([idea.source_ref]),
                 new_promising=idea.is_promising)
            return existing.id
        else:
            return await db.insert_feature_idea({**idea.__dict__, "embedding": embedding})
```

`pg_advisory_xact_lock` is automatically released at transaction end — no cleanup needed.

**Schema change:**
```sql
ALTER TABLE feature_ideas
    ADD COLUMN source_refs JSONB DEFAULT '[]';  -- list of all source_refs that merged here
```

---

### 17.8 SPEC GAP — DGPSynthesizer: Full Spec

**Problem:** §6.6 describes what the synthesizer "asks" but not its output schema, prompt structure, or how it handles contradictions between branches.

**Output schema:**

```python
class DGPSynthesisOutput(BaseModel):
    candidate_dgp_class:        str             # e.g. "Hawkes process with GARCH volatility"
    candidate_dgp_description:  str             # 2–3 sentence mechanistic description
    supporting_evidence:        list[str]       # finding_ids + one-line summaries
    contradicting_evidence:     list[str]       # finding_ids that don't fit the model
    contradiction_resolution:   str | None      # how contradictions are explained, if any
    evidence_strength:          str             # "strong" | "moderate" | "weak" | "speculative"
    implied_features:           list[ImpliedFeature]
    open_research:              list[str]       # questions the thread didn't answer

class ImpliedFeature(BaseModel):
    name:           str             # e.g. "conditional_intensity"
    expression:     str             # symbolic form: "lambda(t) = mu + sum(alpha*exp(-beta*(t-ti)))"
    time_scale:     str             # "1m" | "5m" | etc.
    rationale:      str             # why this falls out of the candidate DGP
```

**System prompt** (`config/prompts/dgp_synthesizer.txt`):

```
You are synthesizing a body of empirical findings into a coherent DGP model.
You receive a structured research thread: what properties were confirmed, what
was falsified, and the statistical evidence supporting each finding.

YOUR TASK:
1. Identify the most parsimonious process class consistent with the confirmed properties.
2. Note any findings that contradict the leading hypothesis and explain if/how they can be reconciled.
3. Extract the natural sufficient statistics (features) implied by the candidate DGP — these
   must follow directly from the model structure, not from ad hoc correlation mining.
4. Rate evidence strength honestly: strong only if multiple independent tests are consistent;
   speculative if based on a single test or borderline significance.

Return a single JSON object matching the DGPSynthesisOutput schema. No prose outside the JSON.
```

**User message:**

```python
synthesis_user_message = f"""
THREAD SUMMARY:
{ctx.rolling_summary}

CONFIRMED PROPERTIES:
{json.dumps(ctx.confirmed_properties, indent=2)}

FALSIFIED HYPOTHESES:
{json.dumps(ctx.falsified_hypotheses, indent=2)}

DETAILED FINDINGS (last {N} validations):
{json.dumps([f.to_synthesis_dict() for f in recent_findings], indent=2)}

Synthesize these findings into a coherent DGP model. Return DGPSynthesisOutput JSON.
"""
```

The synthesizer validates the LLM output against `DGPSynthesisOutput` via Pydantic before writing to `feature_ideas.evidence`. If validation fails, retry once with a correction prompt.

---

### 17.9 SPEC GAP — DGPInterpreter Re-Run Trigger

**Problem:** §16.8 mentions looping "back to Phase 2 if a new interpretation pass is needed" but never defines when or how.

**Resolution:** The orchestrator re-runs Phase 2 (publishes a new `DGPFingerprintInterpreted` → interpretation pass) under two conditions:

**Condition A — Depth increment:** After every `DGP_REINTERPRET_DEPTH_INTERVAL` depth increments (default 2), a new interpretation pass runs. The updated thread context (with confirmed/falsified state) gives the interpreter fundamentally different information than it had at depth 0.

**Condition B — Confirmed property triggers reinterpret:** When a validation result adds a new entry to `confirmed_properties` that wasn't previously known, it may open new hypothesis territory. The orchestrator checks: is the confirmed property consistent with any taxonomy entry not yet tested? If yes, queue an interpretation pass.

**Implementation in orchestrator:**

```python
async def maybe_reinterpret(thread_id: str, ctx: DGPThreadContext) -> None:
    """
    Decides whether to trigger a new Phase 2 interpretation pass.
    Called after update_thread_context().
    """
    # Condition A: depth-based reinterpretation
    depth_trigger = (
        ctx.depth > 0
        and ctx.depth % DGP_REINTERPRET_DEPTH_INTERVAL == 0
        and ctx.depth != ctx.last_reinterpret_depth  # don't double-trigger
    )

    # Condition B: new confirmed property potentially opens new territory
    new_confirmed = len(ctx.confirmed_properties) > ctx.confirmed_count_at_last_reinterpret

    if depth_trigger or new_confirmed:
        # Publish a new interpretation request using the SAME fingerprint
        # but with updated thread context
        fingerprint = await db.get_thread_fingerprint(thread_id)
        await publisher.publish(
            routing_key="dgp.fingerprint.generated",
            message=DGPFingerprintGenerated(
                thread_id=thread_id,
                finding_id=generate_new_finding_id(),
                data_slice=ctx.data_slice,
                fingerprint=fingerprint,
                notable_features=fingerprint.notable_features,
            )
        )
        ctx.last_reinterpret_depth = ctx.depth
        ctx.confirmed_count_at_last_reinterpret = len(ctx.confirmed_properties)
        await db.upsert_thread_context(ctx)
```

**Schema additions:**
```sql
ALTER TABLE dgp_thread_contexts
    ADD COLUMN last_reinterpret_depth INT NOT NULL DEFAULT 0,
    ADD COLUMN confirmed_count_at_last_reinterpret INT NOT NULL DEFAULT 0;
```

**New env var:**
```bash
DGP_REINTERPRET_DEPTH_INTERVAL=2   # trigger new Phase 2 every N depth increments
```

---

### 17.10 SPEC GAP — Regime-Based Data Slice Seeding

**Problem:** §6.2 mentions "regime slices added later once HMM labels are computed by Structural Reader" but never specifies the mechanism.

**Resolution:** After StructuralReader completes Phase 1 for a `window_type="full"` characterization AND `fingerprint.hmm_n_states_best >= 2`, the orchestrator seeds new characterization jobs — one per detected regime.

**Regime range extraction** — the StructuralReader emits regime state assignments in its `08_regimes.py` battery output. Add to `DGPFingerprintGenerated`:

```python
class DGPFingerprintGenerated(BaseMessage):
    ...
    regime_assignments: dict[str, tuple[str, str]] | None
    # Maps regime_label → (start_date, end_date)
    # e.g. {"high_vol": ("2022-01-03", "2022-06-30"), "low_vol": ("2022-07-01", "2023-12-31")}
```

The `08_regimes.py` battery script emits regime date ranges alongside the standard `METRICS:` block:

```python
# At end of 08_regimes.py
regime_ranges = {}
for state_id in range(n_states_best):
    mask = hidden_states == state_id
    dates_in_state = df.index[mask]
    if len(dates_in_state) > 0:
        label = f"regime_{state_id}"  # orchestrator can rename based on vol/trend stats
        regime_ranges[label] = (str(dates_in_state[0].date()), str(dates_in_state[-1].date()))

print("REGIMES: " + json.dumps(regime_ranges))
```

**Orchestrator seeding** — called after `init_thread_context`:

```python
async def seed_regime_slices(
    thread_id: str,
    fingerprint_msg: DGPFingerprintGenerated,
    parent_data_slice: DataSlice,
) -> None:
    if not fingerprint_msg.regime_assignments:
        return
    if fingerprint_msg.fingerprint.hmm_n_states_best < 2:
        return

    for regime_label, (start_date, end_date) in fingerprint_msg.regime_assignments.items():
        regime_slice = DataSlice(
            instrument=parent_data_slice.instrument,
            frequency=parent_data_slice.frequency,
            window_type="regime",
            regime_label=regime_label,
            start_date=start_date,
            end_date=end_date,
        )
        await db.insert_queue_entry(
            question_type="seed",
            question=(
                f"Characterize {parent_data_slice.instrument} "
                f"during {regime_label} ({start_date} to {end_date})"
            ),
            instrument=parent_data_slice.instrument,
            data_slice=regime_slice.__dict__,
            priority=0.8,   # high — regime-conditional DGP is high-value
        )
```

Regime slices spawn independent threads with their own `thread_id`. Their fingerprints and findings are stored separately in `dgp_findings` and contribute independently to the Feature Idea Store.

---

### 17.11 SPEC GAP — GP Parameterized Primitives (DEAP Ephemeral Constants)

**Problem:** §7.2 mentions `window` as "an evolvable constant" and §7.3's DEAP setup never specifies how constants are initialized, what their range is, or what mutation operators apply.

**Resolution:** Use DEAP's `EphemeralConstant` for parameterized terminals and a custom constant mutation operator.

**Primitive set additions:**

```python
import random
from deap import gp

# Window size: integer in [2, 200], initialized uniformly
pset.addEphemeralConstant("window_int", lambda: random.randint(2, 200), int)

# Threshold constant: float in [-3.0, 3.0] for z-score based features
pset.addEphemeralConstant("zscore_thresh", lambda: round(random.uniform(-3.0, 3.0), 2), float)

# Parameterized primitives that consume a window constant
def ema_windowed(series: np.ndarray, window: int) -> np.ndarray:
    w = max(2, int(window))
    return pd.Series(series).ewm(span=w, adjust=False).mean().values

def rolling_std_windowed(series: np.ndarray, window: int) -> np.ndarray:
    w = max(2, int(window))
    return pd.Series(series).rolling(w, min_periods=1).std().fillna(0).values

def rolling_zscore(series: np.ndarray, window: int) -> np.ndarray:
    w = max(2, int(window))
    s = pd.Series(series)
    mu = s.rolling(w, min_periods=1).mean()
    sigma = s.rolling(w, min_periods=1).std().fillna(1)
    return ((s - mu) / sigma.replace(0, 1)).values

pset.addPrimitive(ema_windowed,      [np.ndarray, int], np.ndarray, name="ema_w")
pset.addPrimitive(rolling_std_windowed, [np.ndarray, int], np.ndarray, name="std_w")
pset.addPrimitive(rolling_zscore,    [np.ndarray, int], np.ndarray, name="zscore_w")
```

**Constant mutation operator** — added to the DEAP toolbox alongside `mutUniform`:

```python
def mutate_constants(individual, sigma_int=20, sigma_float=0.5, indpb=0.15):
    """
    Gaussian perturbation for EphemeralConstant nodes.
    Applied in addition to standard subtree mutation.
    """
    for i, node in enumerate(individual):
        if isinstance(node, gp.Terminal) and node.name.startswith("window_int"):
            if random.random() < indpb:
                new_val = int(np.clip(
                    node.value + int(random.gauss(0, sigma_int)), 2, 200
                ))
                individual[i] = type(node)(new_val, node.ret)

        elif isinstance(node, gp.Terminal) and node.name.startswith("zscore_thresh"):
            if random.random() < indpb:
                new_val = round(np.clip(
                    node.value + random.gauss(0, sigma_float), -3.0, 3.0
                ), 2)
                individual[i] = type(node)(new_val, node.ret)

    return individual,

toolbox.register("mutate_constants", mutate_constants)
```

**Evolution loop** — apply constant mutation after each generation:

```python
for gen in range(GP_GENERATIONS):
    offspring = algorithms.varAnd(population, toolbox, GP_CROSSOVER_PROB, GP_MUTATION_PROB)
    # Apply constant mutation on top of structural mutation
    for ind in offspring:
        if random.random() < 0.3:  # 30% of individuals get constant mutation
            toolbox.mutate_constants(ind)
            del ind.fitness.values
    ...
```

---

### 17.12 SMALL — Metrics JSON Validation

**Problem:** Scripts that run without error but emit malformed `METRICS:` JSON produce a silent `None` — misclassified as "no output" rather than "parse failure." Multiple `METRICS:` lines (possible if code prints inside a loop) produce ambiguous output.

**Resolution:** Replace the naive `stdout.split("METRICS: ")[1]` extraction with a validated parser:

```python
def extract_and_validate_metrics(stdout: str) -> tuple[dict | None, str | None]:
    """
    Returns (metrics_dict, error_message).
    On success: (dict, None). On failure: (None, error_string).
    """
    lines = [l for l in stdout.splitlines() if l.startswith("METRICS:")]

    if not lines:
        return None, "No METRICS line found in stdout."

    if len(lines) > 1:
        logger.warning(f"Multiple METRICS lines ({len(lines)}); using last.")

    raw = lines[-1][len("METRICS:"):].strip()

    try:
        metrics = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"METRICS JSON parse error: {e}. Raw: {raw[:200]}"

    if not isinstance(metrics, dict):
        return None, f"METRICS must be a dict, got {type(metrics).__name__}."

    # Coerce values — warn on non-numeric but don't fail
    clean = {}
    for k, v in metrics.items():
        if isinstance(v, (int, float)) and not (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            clean[k] = float(v)
        elif isinstance(v, str) and k == "conclusion":
            clean[k] = v  # 'conclusion' field is a string (§14.5)
        else:
            logger.warning(f"Metric '{k}' has invalid value {v!r} — setting to None")
            clean[k] = None

    return clean, None
```

If `extract_and_validate_metrics` returns `(None, error)`, treat as a `missing_output` error and route to the fix loop with the parse error as the hint.

---

### 17.13 SMALL — LLM Circuit Breaker

**Problem:** There is no fault tolerance for the LLM endpoint going down. Workers will repeatedly fail, exhaust retries, and flood the DLQ. Long-running research loops stall with no alerting.

**Resolution:** Wrap the LLM client in a circuit breaker, reusing the existing `CircuitBreaker` abstraction already present in `src/shared/messaging/circuit_breaker.py`.

**In `src/shared/llm/openai_client.py`:**

```python
class OpenAIClient:
    def __init__(self, ...):
        self._cb = CircuitBreaker(
            failure_threshold=int(os.environ.get("LLM_CB_FAILURE_THRESHOLD", "5")),
            recovery_timeout=int(os.environ.get("LLM_CB_RECOVERY_TIMEOUT", "60")),
        )

    async def complete(self, system_prompt: str, user_message: str, **kwargs) -> str:
        if not self._cb.allow_request():
            raise LLMCircuitOpenError(
                "LLM circuit breaker open — backing off after repeated failures"
            )
        try:
            result = await self._raw_complete(system_prompt, user_message, **kwargs)
            self._cb.record_success()
            return result
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            self._cb.record_failure()
            raise LLMUnavailableError(str(e)) from e
```

**Worker behaviour on `LLMCircuitOpenError`:**
- Nack the RabbitMQ message with `requeue=True` (not `reject`) — returns to queue for retry
- Back off with exponential wait: `await asyncio.sleep(2 ** min(attempt, 6))`
- If circuit has been open > `LLM_CB_ALERT_MINUTES` (default 5), publish a `NotificationRequest` (alert_type='research', title='LLM endpoint down') to Slack

**New env vars:**
```bash
LLM_CB_FAILURE_THRESHOLD=5    # consecutive failures before circuit opens
LLM_CB_RECOVERY_TIMEOUT=60    # seconds before circuit attempts half-open probe
LLM_CB_ALERT_MINUTES=5        # minutes of open circuit before Slack alert
```

---

### 17.14 SMALL — Feature Idea Source Lineage Preservation

**Problem:** When two feature ideas are merged by the dedup algorithm, `source_ref` on the existing row is not updated — the merged idea loses traceability to the second discovery source.

**Resolution:** Add `source_refs JSONB DEFAULT '[]'` to `feature_ideas` (already included in §17.7 schema change). Ensure all code that creates a `FeatureIdeaCreated` message populates `source_ref`, and the dedup merge appends it to `source_refs`.

The ObsidianWriter template should render `source_refs` as a list of backlinks:

```markdown
## Sources
{% for ref in source_refs %}
- [{{ ref.source_process }}] {{ ref.source_ref }}
{% endfor %}
```

---

### 17.15 Schema Additions Summary (add to Alembic migration)

All DDL changes from this section consolidated:

```sql
-- §17.2 result ordering buffer
CREATE TABLE dgp_result_buffer (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id       TEXT NOT NULL,
    finding_id      TEXT NOT NULL UNIQUE,
    depth           INT  NOT NULL,
    iteration_seq   INT  NOT NULL,
    result_json     JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    received_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX dgp_result_buffer_thread_idx
    ON dgp_result_buffer (thread_id, status, depth, iteration_seq);

-- §17.3 stale job watchdog
ALTER TABLE dgp_research_queue
    ADD COLUMN dispatch_timeout_at TIMESTAMPTZ,
    ADD COLUMN retry_count INT NOT NULL DEFAULT 0;
CREATE INDEX dgp_queue_stale_idx
    ON dgp_research_queue (status, dispatch_timeout_at)
    WHERE status = 'dispatched';

-- §17.1 session decoupling
ALTER TABLE dgp_thread_contexts
    ADD COLUMN data_path TEXT,
    ADD COLUMN expected_rows INT,
    ADD COLUMN expected_series_len INT;

-- §17.4 distillation tracking
ALTER TABLE dgp_thread_contexts
    ADD COLUMN last_distilled_at TIMESTAMPTZ;

-- §17.5 pivot tracking
ALTER TABLE dgp_thread_contexts
    ADD COLUMN pivot_class TEXT;

-- §17.7 source lineage
ALTER TABLE feature_ideas
    ADD COLUMN source_refs JSONB NOT NULL DEFAULT '[]';

-- §17.9 reinterpretation tracking
ALTER TABLE dgp_thread_contexts
    ADD COLUMN last_reinterpret_depth INT NOT NULL DEFAULT 0,
    ADD COLUMN confirmed_count_at_last_reinterpret INT NOT NULL DEFAULT 0;

-- §17.6 concept taxonomy table (replaces YAML)
CREATE TABLE dgp_concept_taxonomy (
    id                               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                             TEXT NOT NULL,
    domain                           TEXT NOT NULL,
    source                           TEXT NOT NULL DEFAULT 'seed',
    source_ref                       TEXT,
    predicted_fingerprint_indicators JSONB DEFAULT '[]',
    discriminating_test              TEXT,
    implied_features                 JSONB DEFAULT '[]',
    embedding                        vector(1536),
    created_at                       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (lower(name))
);
CREATE INDEX concept_taxonomy_embedding_idx
    ON dgp_concept_taxonomy USING hnsw (embedding vector_cosine_ops);

-- §17.10 regime label extension on dgp_findings
ALTER TABLE dgp_findings
    ADD COLUMN iteration_seq INT;
```

---

### 17.16 Additional Environment Variables

```bash
# §17.3 Stale job watchdog
DGP_DISPATCH_TIMEOUT_MINUTES=30
DGP_MAX_JOB_RETRIES=3

# §17.4 Context distillation
DGP_CONTEXT_DISTILL_INTERVAL=10
DGP_CONTEXT_MAX_ENTRIES=5

# §17.9 DGPInterpreter re-run
DGP_REINTERPRET_DEPTH_INTERVAL=2

# §17.13 LLM circuit breaker
LLM_CB_FAILURE_THRESHOLD=5
LLM_CB_RECOVERY_TIMEOUT=60
LLM_CB_ALERT_MINUTES=5
```
