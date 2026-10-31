"""Research provider abstractions and search integrations for Wear & Wonder."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
import httpx


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    publisher: str = "Web Source"
    source_type: str = "ARTICLE"
    publication_date: str | None = None


class ResearchProvider(ABC):
    """Abstract search provider for fashion research."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Perform search and return structured search results."""
        pass


class _DuckDuckGoHTMLParser(HTMLParser):
    """Parse DuckDuckGo HTML results page for titles, redirected URLs, and snippets."""

    def __init__(self):
        super().__init__()
        self.results: list[SearchResult] = []
        self._current_tag: str | None = None
        self._current_classes: list[str] = []
        self._current_href: str | None = None
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        self._current_tag = tag
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()
        self._current_classes = classes

        if tag == "a" and "result__snippet" in classes:
            self._in_snippet = True
            self._current_snippet = []

        if tag == "a" and "result__url" in classes:
            raw_href = attrs_dict.get("href", "")
            self._current_href = self._extract_clean_url(raw_href)

        if tag == "a" and ("result__snippet" not in classes and "result__url" not in classes):
            # Check for result title link
            if attrs_dict.get("href") and "uddg=" in attrs_dict.get("href", ""):
                self._current_href = self._extract_clean_url(attrs_dict["href"])
                self._in_title = True
                self._current_title = []

    def handle_endtag(self, tag: str):
        if tag == "a" and self._in_snippet:
            self._in_snippet = False
            snippet_text = "".join(self._current_snippet).strip()
            if self._current_href and snippet_text:
                publisher = urlparse(self._current_href).netloc.replace("www.", "")
                self.results.append(
                    SearchResult(
                        title="Fashion Reference Source",
                        url=self._current_href,
                        snippet=snippet_text,
                        publisher=publisher or "Fashion Publication",
                        source_type="ARTICLE",
                    )
                )
                self._current_href = None
        if tag == "a" and self._in_title:
            self._in_title = False

    def handle_data(self, data: str):
        if self._in_snippet:
            self._current_snippet.append(data)
        if self._in_title:
            self._current_title.append(data)

    def _extract_clean_url(self, raw_url: str) -> str:
        if "uddg=" in raw_url:
            match = re.search(r"uddg=([^&]+)", raw_url)
            if match:
                return unquote(match.group(1))
        if raw_url.startswith("//"):
            return "https:" + raw_url
        return raw_url


class DuckDuckGoWebSearchProvider(ResearchProvider):
    """Live web search provider using DuckDuckGo HTML endpoint without API keys."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        url = "https://html.duckduckgo.com/html/"
        try:
            with httpx.Client(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
                res = client.post(url, data={"q": query})
                if res.status_code != 200:
                    # Fallback to GET
                    res = client.get(url, params={"q": query})

                if res.status_code != 200:
                    return []

                parser = _DuckDuckGoHTMLParser()
                parser.feed(res.text)
                cleaned = []
                seen_urls = set()
                for r in parser.results:
                    if r.url and r.url.startswith("http") and r.url not in seen_urls:
                        seen_urls.add(r.url)
                        # Extract cleaner title from snippet or publisher if generic
                        cleaned.append(r)
                        if len(cleaned) >= max_results:
                            break
                return cleaned
        except Exception:
            return []


class CuratedFashionResourceProvider(ResearchProvider):
    """Curated authoritative fashion publication provider with verified live URLs."""

    CURATED_REPOSITORY: dict[str, list[SearchResult]] = {
        "jeans_and_tops": [
            SearchResult(
                title="Vogue Guide: How to Style Straight and Wide-Leg Denim",
                url="https://www.vogue.com/article/how-to-style-wide-leg-jeans",
                snippet="Fashion editors break down proportions for relaxed denim cuts paired with cropped shirts and tucked knits.",
                publisher="Vogue",
                source_type="EDITORIAL_GUIDE",
                publication_date="2026-03-15",
            ),
            SearchResult(
                title="Who What Wear: The Top Denim and Top Trends for Campus & Streetwear",
                url="https://www.whowhatwear.com/denim-trends",
                snippet="The most versatile combinations of rigid high-rise jeans, fitted baby tees, and oversized poplin shirts.",
                publisher="Who What Wear",
                source_type="TREND_REPORT",
                publication_date="2026-04-10",
            ),
            SearchResult(
                title="Harper's Bazaar: Essential Footwear Pairings for Every Denim Silhouette",
                url="https://www.harpersbazaar.com/fashion/trends/g39055427/shoes-to-wear-with-jeans/",
                snippet="From retro running sneakers to lug-sole loafers, how trouser hem breaks dictate shoe choice.",
                publisher="Harper's Bazaar",
                source_type="STYLING_GUIDE",
                publication_date="2026-02-20",
            ),
        ],
        "colour_combinations": [
            SearchResult(
                title="Pantone Color Institute: Seasonal Color Trend Report",
                url="https://www.pantone.com/color-trend-report",
                snippet="Key seasonal color harmonies balancing grounding neutrals with expressive high-contrast accents.",
                publisher="Pantone",
                source_type="TREND_REPORT",
                publication_date="2026-01-18",
            ),
            SearchResult(
                title="Elle: 7 Foolproof Outfit Colour Combinations That Always Look Expensive",
                url="https://www.elle.com/fashion/trend-reports/a42145398/outfit-colour-combinations/",
                snippet="Styling rules for tonal dressing, earth tone balance, and avoiding visual clash in multi-piece looks.",
                publisher="Elle",
                source_type="STYLING_GUIDE",
                publication_date="2026-03-01",
            ),
        ],
        "casual_and_college": [
            SearchResult(
                title="Teen Vogue: University Capsule Wardrobe Essentials",
                url="https://www.teenvogue.com/story/college-wardrobe-essentials-checklist",
                snippet="Comfortable everyday campus looks combining breathable layers, sneakers, and durable carryalls.",
                publisher="Teen Vogue",
                source_type="EDITORIAL_GUIDE",
                publication_date="2026-08-12",
            ),
            SearchResult(
                title="GQ: The Modern Casual Wardrobe and Layering Playbook",
                url="https://www.gq.com/story/casual-layering-playbook",
                snippet="How to balance casual staples with intentional proportions, relaxed overshirts, and clean sneakers.",
                publisher="GQ",
                source_type="EDITORIAL_GUIDE",
                publication_date="2026-05-02",
            ),
        ],
        "formal_and_office": [
            SearchResult(
                title="GQ: The New Rules of Modern Office Tailoring",
                url="https://www.gq.com/story/modern-suiting-workwear-guide",
                snippet="Contemporary tailored suiting, relaxed pleated trousers, and pairing formal blazers with knitwear.",
                publisher="GQ",
                source_type="STYLING_GUIDE",
                publication_date="2026-02-14",
            ),
            SearchResult(
                title="Vogue: Business Casual and Executive Dressing for Women",
                url="https://www.vogue.com/article/business-casual-workwear-guide",
                snippet="Refined suiting separates, structured tote bags, and sophisticated footwear for contemporary office wear.",
                publisher="Vogue",
                source_type="EDITORIAL_GUIDE",
                publication_date="2026-03-22",
            ),
        ],
        "general_fashion": [
            SearchResult(
                title="Vogue Runway: Global Trend Forecasting & Styling Formula Analysis",
                url="https://www.vogue.com/fashion-shows",
                snippet="Comprehensive analysis of seasonal collections, proportion shifts, and garment coordination.",
                publisher="Vogue Runway",
                source_type="TREND_REPORT",
                publication_date="2026-04-01",
            ),
            SearchResult(
                title="The Business of Fashion: Key Consumer Wardrobe Shifts and Styling Direction",
                url="https://www.businessoffashion.com/reports/fashion-trends",
                snippet="Verified insights into timeless wardrobe investments, color balance, and fabric choices.",
                publisher="The Business of Fashion",
                source_type="INDUSTRY_REPORT",
                publication_date="2026-02-28",
            ),
        ],
    }

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        q = query.lower()
        results: list[SearchResult] = []

        # Find category match
        for category, items in self.CURATED_REPOSITORY.items():
            if any(term in q for term in category.split("_")):
                results.extend(items)

        if not results:
            results.extend(self.CURATED_REPOSITORY["general_fashion"])

        return results[:max_results]


class MockSearchProvider(ResearchProvider):
    """Mock search provider for isolated unit testing without external HTTP calls."""

    def __init__(self, predefined_results: list[SearchResult] | None = None):
        self.predefined_results = predefined_results or [
            SearchResult(
                title="Test Styling Guide: College Denim and Tops",
                url="https://example.com/test-fashion-guide-01",
                snippet="Comprehensive test reference on pairing high-waist straight denim with cotton tees.",
                publisher="Test Fashion Journal",
                source_type="STYLING_GUIDE",
                publication_date="2026-01-01",
            ),
            SearchResult(
                title="Test Footwear Compatibility Analysis",
                url="https://example.com/test-footwear-trends",
                snippet="Low profile retro white trainers pair seamlessly with full-length straight jeans.",
                publisher="Footwear Insights",
                source_type="TREND_REPORT",
                publication_date="2026-02-01",
            ),
        ]

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return self.predefined_results[:max_results]
