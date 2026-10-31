"""Unit tests for Stage 2: Fashion Research and Source Verification."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.research.provider import (
    CuratedFashionResourceProvider,
    MockSearchProvider,
    SearchResult,
)
from app.research.research_service import (
    check_url_accessibility,
    execute_fashion_research,
    generate_research_queries,
    normalize_url,
)
from app.storage import get_research_data, save_or_update_brief


class TestResearchService(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_data_dir = Path(self.temp_dir.name)
        self.brief_id = "test-brief-res-01"
        self.mock_brief = {
            "brief_id": self.brief_id,
            "idea_original": "Create six jeans and top combinations for college girls",
            "audience": "College girls",
            "outfit_count": 6,
            "requested_characters": ["WW-CHAR-01"],
            "research_status": "PENDING",
            "ai_analysis": {
                "research_plan": ["Check denim rises", "Review shoe styles"],
                "styling_direction": "Casual yet elevated proportion play",
                "assumptions": ["College climate allows sneakers"],
            },
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalize_url(self):
        raw = "https://www.example.com/fashion/trends/?utm_source=twitter&utm_medium=social&ref=123#anchor"
        normalized = normalize_url(raw)
        self.assertEqual(normalized, "https://www.example.com/fashion/trends")

    def test_generate_research_queries(self):
        queries = generate_research_queries(self.mock_brief)
        self.assertGreaterEqual(len(queries), 2)
        # Should contain audience and topic keywords
        self.assertTrue(any("college girls" in q.lower() for q in queries))
        self.assertTrue(any("jeans" in q.lower() or "styling" in q.lower() for q in queries))

    @patch("app.research.research_service.httpx.Client")
    def test_check_url_accessibility_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_client.head.return_value = mock_res

        is_ok, code = check_url_accessibility("https://example.com/article")
        self.assertTrue(is_ok)
        self.assertEqual(code, 200)

    @patch("app.research.research_service.httpx.Client")
    def test_check_url_accessibility_failure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_res = MagicMock()
        mock_res.status_code = 404
        mock_client.head.return_value = mock_res
        mock_client.get.return_value = mock_res

        is_ok, code = check_url_accessibility("https://example.com/nonexistent")
        self.assertFalse(is_ok)
        self.assertEqual(code, 404)

    def test_curated_fashion_resource_provider(self):
        provider = CuratedFashionResourceProvider()
        results = provider.search("jeans_and_tops trending cuts", max_results=2)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, SearchResult) for r in results))
        self.assertTrue(all(r.url.startswith("http") for r in results))

    @patch("app.research.research_service.check_url_accessibility", return_value=(True, 200))
    def test_execute_fashion_research_with_mock_provider(self, mock_check):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.RESEARCH_SOURCES_FILE", self.test_data_dir / "research_sources.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
        ):
            # Save mock brief first
            save_or_update_brief(self.mock_brief)

            mock_provider = MockSearchProvider([
                SearchResult(
                    title="Vogue: Straight Leg Denim Guide",
                    url="https://vogue.com/article/denim-styling-guide?utm_source=test",
                    snippet="High-rise straight leg jeans balance fitted tops effortlessly.",
                    publisher="Vogue",
                    source_type="EDITORIAL_GUIDE",
                ),
                SearchResult(
                    title="Who What Wear: Campus Footwear",
                    url="https://whowhatwear.com/campus-shoes",
                    snippet="Retro court sneakers and loafers ground daily denim outfits.",
                    publisher="Who What Wear",
                    source_type="STYLING_GUIDE",
                ),
            ])

            result = execute_fashion_research(
                brief_id=self.brief_id,
                provider=mock_provider,
                verify_urls=True,
            )

            self.assertEqual(result["brief_id"], self.brief_id)
            sources = result["sources"]
            self.assertEqual(len(sources), 2)
            self.assertEqual(sources[0]["verification_status"], "VERIFIED")
            self.assertEqual(sources[0]["publisher"], "Vogue")

            summary = result["summary"]
            self.assertEqual(summary["total_sources_found"], 2)
            self.assertEqual(summary["verified_sources_count"], 2)
            self.assertGreaterEqual(len(summary["verified_facts"]), 1)

            # Check that data was persisted in storage
            saved_data = get_research_data(self.brief_id)
            self.assertEqual(len(saved_data["sources"]), 2)


if __name__ == "__main__":
    unittest.main()
