"""Source type enums used in messaging schemas."""

from enum import Enum


class SourceType(str, Enum):
    """Supported upstream content sources."""

    ARXIV = "arxiv"
    KAGGLE = "kaggle"
    GITHUB = "github"
    WEB = "web"
    MANUAL = "manual"
