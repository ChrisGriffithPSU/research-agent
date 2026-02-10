"""Configuration for ArXiv fetcher.

Hardcoded categories with configurable fetch parameters.
No LLM-based query expansion - simple category-based fetching.
"""

from typing import List
from pydantic import BaseModel, Field


# Hardcoded ArXiv categories for MFT quant research
# Focused on ML, stats, quant finance, and mathematical modeling
HARDCODED_CATEGORIES: List[str] = [
    # Machine Learning & Artificial Intelligence
    "cs.LG",  # Machine Learning
    "cs.AI",  # Artificial Intelligence
    "cs.CL",  # Computation and Language (useful for sequence modeling ideas)
    "cs.CV",  # Computer Vision (occasionally useful for pattern extraction methods)
    "cs.NE",  # Neural and Evolutionary Computing
    "cs.RO",  # Robotics (control & state estimation ideas)
    "cs.SY",  # Systems and Control
    "cs.MA",  # Multiagent Systems
    "cs.IT",  # Information Theory (CS)

    # Statistics & Statistical Learning
    "stat.ML",  # Machine Learning (Statistics)
    "stat.TH",  # Statistics Theory
    "stat.ME",  # Methodology
    "stat.CO",  # Computational Statistics
    "math.ST",  # Statistics (Mathematics)
    "math.PR",  # Probability Theory

    # Quantitative Finance (directly relevant)
    "q-fin.TR",  # Trading and Market Microstructure
    "q-fin.CP",  # Computational Finance
    "q-fin.ST",  # Statistical Finance
    "q-fin.PM",  # Portfolio Management
    "q-fin.RM",  # Risk Management
    "q-fin.GN",  # General Finance

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
    "physics.soc-ph",  # Physics of Society (complex systems, networks)
    "physics.data-an",  # Data Analysis, Statistics and Probability

    # Fluid Dynamics & Turbulence (useful for cascade/regime analogies)
    "physics.flu-dyn",  # Fluid Dynamics

    # Networks, Traffic & Queueing Analogies
    "physics.soc-ph",  # Complex social/network systems
    "cs.NI",  # Networking and Internet Architecture
    "cs.DC",  # Distributed, Parallel, and Cluster Computing

    # Information Theory & Signal Models
    "math.IT",  # Information Theory
    "cs.IT",  # Information Theory (CS)

    # Applied Probability & Queueing-Relevant Fields
    "math.PR",  # Probability Theory
    "stat.TH",  # Statistical Theory

    # Computational & Numerical Methods
    "cs.NA",  # Numerical Analysis
    "math.NA",  # Numerical Analysis
    "cs.MS",  # Mathematical Software
]


class ArxivFetcherConfig(BaseModel):
    """Configuration for ArXiv fetcher worker.

    Categories are hardcoded - only fetch parameters are configurable.
    """

    # Hardcoded category list (not configurable)
    categories: List[str] = Field(
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
        default="paper.triage.request", description="Queue to publish discovered papers"
    )

    # Duplicate checking
    dedup_lookback_days: int = Field(
        default=30, ge=1, le=365, description="Days to look back for duplicate detection"
    )

    class Config:
        env_prefix = "ARXIV_"
