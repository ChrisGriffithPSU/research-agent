"""Configuration for ArXiv fetcher.

Hardcoded categories with configurable fetch parameters.
No LLM-based query expansion - simple category-based fetching.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hardcoded ArXiv categories for MFT quant research
# Focused on ML, stats, quant finance, and mathematical modeling
HARDCODED_CATEGORIES: list[str] = [
    # Quantitative Finance (directly relevant)
    "q-fin.TR",  # Trading and Market Microstructure
    "q-fin.ST",  # Statistical Finance
    "q-fin.CP",  # Computational Finance
    "q-fin.PM",  # Portfolio Management
    "q-fin.RM",  # Risk Management
    "q-fin.GN",  # General Finance
    # Machine Learning & Artificial Intelligence
    "cs.LG",  # Machine Learning
    "cs.AI",  # Artificial Intelligence
    "cs.CL",  # Computation and Language (sequence modeling ideas)
    "cs.CV",  # Computer Vision (pattern extraction methods)
    "cs.NE",  # Neural and Evolutionary Computing
    "cs.RO",  # Robotics (control & state estimation ideas)
    "cs.SY",  # Systems and Control
    "cs.MA",  # Multiagent Systems
    "cs.IT",  # Information Theory (CS)
    "cs.SI",  # Social and Information Networks
    "cs.DS",  # Data Structures and Algorithms (graph methods)
    "cs.PF",  # Performance (queueing analogies)
    # Statistics & Statistical Learning
    "stat.ML",  # Machine Learning (Statistics)
    "stat.TH",  # Statistics Theory
    "stat.ME",  # Methodology
    "stat.CO",  # Computational Statistics
    "stat.AP",  # Applications
    "math.ST",  # Statistics (Mathematics)
    "math.PR",  # Probability Theory
    # Optimization, Control & Decision Systems
    "math.OC",  # Optimization and Control
    "math.CT",  # Control Theory
    "eess.SY",  # Systems and Control (engineering)
    "eess.SP",  # Signal Processing
    # Dynamical Systems & Nonlinear Science
    "math.DS",  # Dynamical Systems
    "nlin.AO",  # Adaptation and Self-Organizing Systems
    "nlin.CD",  # Chaotic Dynamics
    "nlin.CG",  # Cellular Automata and Lattice Gases
    "nlin.PS",  # Pattern Formation and Solitons
    "nlin.SI",  # Exactly Solvable and Integrable Systems
    # Statistical Physics & Complex Systems
    "cond-mat.stat-mech",  # Statistical Mechanics
    "cond-mat.dis-nn",  # Disordered Systems and Neural Networks
    "cond-mat.soft",  # Soft Condensed Matter
    "cond-mat.mtrl-sci",  # Materials Science (fracture/stress analogies)
    # Physics & Geophysics (cascade/regime analogies)
    "physics.soc-ph",  # Physics of Society (complex systems, networks)
    "physics.data-an",  # Data Analysis, Statistics and Probability
    "physics.flu-dyn",  # Fluid Dynamics
    "physics.geo-ph",  # Geophysics (earthquake/rupture analogies)
    # Information Theory & Signal Models
    "math.IT",  # Information Theory
    # Computational & Numerical Methods
    "cs.NA",  # Numerical Analysis
    "math.NA",  # Numerical Analysis
    "cs.MS",  # Mathematical Software
    # Geometry & Topology (manifold/TDA)
    "math.MG",  # Metric Geometry
    "math.AT",  # Algebraic Topology
    # Economics (game theory, econometrics)
    "econ.GN",  # General Economics
    "econ.TH",  # Theoretical Economics
    "econ.EM",  # Econometrics
    # Quantitative Biology (neuro/eco/epidemic analogies)
    "q-bio.NC",  # Neurons and Cognition (spike-train analogies)
    "q-bio.QM",  # Quantitative Methods
    "q-bio.PE",  # Populations and Evolution (ecology/contagion)
    "q-bio.OT",  # Other Quantitative Biology (contagion models)
    # Networking & Distributed Systems (queueing analogies)
    "cs.NI",  # Networking and Internet Architecture
    "cs.DC",  # Distributed, Parallel, and Cluster Computing
]


class ArxivFetcherConfig(BaseSettings):
    """Configuration for ArXiv fetcher worker.

    Categories are hardcoded - only fetch parameters are configurable.
    """

    # Hardcoded category list (not configurable)
    categories: list[str] = Field(
        default=HARDCODED_CATEGORIES, description="ArXiv categories to monitor (hardcoded)"
    )

    # Fetch parameters
    max_results_per_category: int = Field(
        default=50, ge=1, le=2000, description="Maximum papers per category per fetch"
    )
    days_back: int = Field(default=1, ge=1, le=30, description="Only fetch papers from last N days")

    # Rate limiting
    rate_limit_requests_per_second: float = Field(
        default=0.33,  # 1 request per 3 seconds
        gt=0,
        description="Rate limit for ArXiv API",
    )
    max_concurrent_categories: int = Field(
        default=3, ge=1, le=10, description="Maximum concurrent category fetches"
    )

    # Queue configuration
    output_queue: str = Field(
        default="paper.fulltext.request", description="Queue to publish discovered papers"
    )

    # Duplicate checking
    dedup_lookback_days: int = Field(
        default=30, ge=1, le=365, description="Days to look back for duplicate detection"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="ARXIV_",
    )
