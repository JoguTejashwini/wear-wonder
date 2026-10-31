"""Fashion research package for Wear & Wonder."""
from app.research.provider import (
    CuratedFashionResourceProvider,
    DuckDuckGoWebSearchProvider,
    MockSearchProvider,
    ResearchProvider,
    SearchResult,
)
from app.research.research_service import (
    check_url_accessibility,
    execute_fashion_research,
    generate_research_queries,
    normalize_url,
)

__all__ = [
    "ResearchProvider",
    "SearchResult",
    "DuckDuckGoWebSearchProvider",
    "CuratedFashionResourceProvider",
    "MockSearchProvider",
    "normalize_url",
    "check_url_accessibility",
    "generate_research_queries",
    "execute_fashion_research",
]
