"""Integration tests for the AI brief generation and saving workflow."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.fashion_ai import interpret_idea_with_gemini
from app.idea_intake import create_research_brief, save_research_brief


class MockInteraction:

    def __init__(self, output_text: str):
        self.output_text = output_text


class TestBriefWorkflow(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_data_file = Path(self.temp_dir.name) / "research.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_end_to_end_idea_to_saved_brief(self, mock_client_cls):
        # Existing records in research file
        existing_record = {
            "brief_id": "existing-brief-001",
            "idea_original": "Past existing idea",
            "audience": "General audience",
            "outfit_count": 3,
            "requested_characters": ["WW-CHAR-03"],
            "research_status": "APPROVED",
            "outfit_approval": "APPROVED",
        }
        self.test_data_file.write_text(
            json.dumps([existing_record], indent=2), encoding="utf-8"
        )

        mock_ai_response = {
            "audience": "College girls",
            "outfit_count": 6,
            "requested_characters": ["WW-CHAR-01", "WW-CHAR-02"],
            "concept_summary": "Six versatile campus denim combinations.",
            "styling_direction": "Casual chic layering with proportion play.",
            "research_plan": ["Research campus footwear trends", "Explore denim cuts"],
            "validation_checklist": ["Check movement comfort", "Verify colour harmony"],
            "clarifying_questions": ["Is this for spring or autumn?"],
            "assumptions": ["Assuming standard daytime university dress code"],
        }

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.interactions.create.return_value = MockInteraction(
            json.dumps(mock_ai_response)
        )

        idea_text = (
            "Create six jeans and top combinations for college girls "
            "using Female Model 01 and Female Model 02."
        )

        # 1. AI Interpretation
        ai_result = interpret_idea_with_gemini(
            idea=idea_text,
            additional_requirements="Sneakers only",
            reference_url="https://youtube.com/watch?v=example",
        )

        self.assertEqual(ai_result["outfit_count"], 6)
        self.assertEqual(ai_result["audience"], "College girls")
        self.assertEqual(
            ai_result["requested_characters"],
            ["WW-CHAR-01", "WW-CHAR-02"],
        )
        self.assertFalse(ai_result["live_research_performed"])

        # 2. Research Brief Creation (as done in dashboard.py)
        brief = create_research_brief(
            idea=idea_text,
            requested_characters=ai_result["requested_characters"],
            audience=ai_result["audience"],
            outfit_count=ai_result["outfit_count"],
            additional_requirements="Sneakers only",
        )
        brief["reference_url"] = "https://youtube.com/watch?v=example"
        brief["ai_analysis"] = ai_result
        brief["interpretation_method"] = "GEMINI_API"
        brief["interpretation_note"] = (
            "Gemini interpreted this idea. This is planning only: "
            "live research and outfit verification have not occurred."
        )

        # 3. Verify gate states: research and outfit approvals MUST remain pending
        self.assertEqual(brief["research_status"], "PENDING")
        self.assertEqual(brief["outfit_approval"], "PENDING")
        self.assertEqual(brief["requested_characters"], ["WW-CHAR-01", "WW-CHAR-02"])

        # 4. Save to storage without overwriting existing data
        with patch("app.idea_intake.DATA_FILE", self.test_data_file):
            save_research_brief(brief)

            # Re-read saved file
            saved_data = json.loads(self.test_data_file.read_text(encoding="utf-8"))
            self.assertEqual(len(saved_data), 2)
            self.assertEqual(saved_data[0]["brief_id"], "existing-brief-001")
            self.assertEqual(saved_data[1]["brief_id"], brief["brief_id"])
            self.assertEqual(saved_data[1]["outfit_count"], 6)
            self.assertEqual(
                saved_data[1]["requested_characters"],
                ["WW-CHAR-01", "WW-CHAR-02"],
            )
            self.assertEqual(saved_data[1]["research_status"], "PENDING")
            self.assertEqual(saved_data[1]["outfit_approval"], "PENDING")
            self.assertEqual(saved_data[1]["interpretation_method"], "GEMINI_API")


if __name__ == "__main__":
    unittest.main()
