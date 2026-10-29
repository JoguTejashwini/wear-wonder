"""Unit tests for Gemini idea interpretation in fashion_ai.py."""
import json
import unittest
from unittest.mock import MagicMock, patch

from app.fashion_ai import (
    DEFAULT_MODEL,
    _extract_json,
    _extract_status_code,
    _sanitize_message,
    interpret_idea_with_gemini,
)


class MockInteraction:
    """Mock Interaction response object."""

    def __init__(self, output_text: str | None):
        self.output_text = output_text


class MockGenAiError(Exception):
    """Mock error simulating GenAiError with status_code."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class TestFashionAI(unittest.TestCase):

    def setUp(self):
        self.valid_payload = {
            "audience": "College girls",
            "outfit_count": 6,
            "requested_characters": ["WW-CHAR-01", "WW-CHAR-02"],
            "concept_summary": "Six stylish campus outfits for everyday wear.",
            "styling_direction": "Casual yet elevated styling with denim and tops.",
            "research_plan": ["Explore fall campus trends", "Check denim washes"],
            "validation_checklist": ["Check comfort for walking", "Ensure distinct looks"],
            "clarifying_questions": ["Is this for warm or cool climate?"],
            "assumptions": ["Assuming fall semester timing"],
        }

    def test_empty_idea_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            interpret_idea_with_gemini("   ")
        self.assertIn("cannot be empty", str(ctx.exception))

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_raises_runtime_error(self):
        with self.assertRaises(RuntimeError) as ctx:
            interpret_idea_with_gemini("Valid idea")
        self.assertIn("GEMINI_API_KEY was not found", str(ctx.exception))

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_successful_interpretation(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.interactions.create.return_value = MockInteraction(
            json.dumps(self.valid_payload)
        )

        result = interpret_idea_with_gemini(
            idea="Create 6 campus looks with denim",
            additional_requirements="Budget-friendly",
            reference_url="https://example.com/ref",
        )

        # Check call arguments
        mock_client.interactions.create.assert_called_once()
        call_kwargs = mock_client.interactions.create.call_args[1]
        self.assertEqual(call_kwargs["model"], DEFAULT_MODEL)
        self.assertEqual(call_kwargs["generation_config"], {"thinking_level": "low"})

        # Check returned fields
        self.assertEqual(result["audience"], "College girls")
        self.assertEqual(result["outfit_count"], 6)
        self.assertEqual(result["requested_characters"], ["WW-CHAR-01", "WW-CHAR-02"])
        self.assertEqual(result["concept_summary"], self.valid_payload["concept_summary"])
        self.assertEqual(result["styling_direction"], self.valid_payload["styling_direction"])
        self.assertEqual(result["research_plan"], self.valid_payload["research_plan"])
        self.assertEqual(result["validation_checklist"], self.valid_payload["validation_checklist"])
        self.assertEqual(result["clarifying_questions"], self.valid_payload["clarifying_questions"])
        self.assertEqual(result["assumptions"], self.valid_payload["assumptions"])
        self.assertEqual(result["interpretation_method"], "GEMINI_API")
        self.assertEqual(result["research_status"], "PENDING")
        self.assertEqual(result["outfit_approval"], "PENDING")
        self.assertFalse(result["live_research_performed"])

        mock_client.close.assert_called_once()

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_markdown_wrapped_json(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        wrapped = f"```json\n{json.dumps(self.valid_payload)}\n```"
        mock_client.interactions.create.return_value = MockInteraction(wrapped)

        result = interpret_idea_with_gemini("Create denim outfits")
        self.assertEqual(result["audience"], "College girls")
        self.assertEqual(result["outfit_count"], 6)

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_malformed_json_raises_value_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.interactions.create.return_value = MockInteraction("{ not valid json: ")

        with self.assertRaises(ValueError) as ctx:
            interpret_idea_with_gemini("Create denim outfits")
        self.assertIn("invalid or unparseable JSON", str(ctx.exception))

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_empty_response_raises_runtime_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.interactions.create.return_value = MockInteraction("")

        with self.assertRaises(RuntimeError) as ctx:
            interpret_idea_with_gemini("Create denim outfits")
        self.assertIn("empty response", str(ctx.exception))

    @patch("time.sleep", return_value=None)
    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_503_transient_error_retries_and_succeeds(self, mock_client_cls, mock_sleep):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        # First call fails with 503, second call succeeds
        mock_client.interactions.create.side_effect = [
            MockGenAiError("Service Unavailable", 503),
            MockInteraction(json.dumps(self.valid_payload)),
        ]

        result = interpret_idea_with_gemini("Create denim outfits")
        self.assertEqual(mock_client.interactions.create.call_count, 2)
        self.assertEqual(result["audience"], "College girls")
        mock_sleep.assert_called_once_with(1.0)

    @patch("time.sleep", return_value=None)
    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_504_gateway_timeout_exhausts_retries(self, mock_client_cls, mock_sleep):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        # All attempts fail with 504
        mock_client.interactions.create.side_effect = MockGenAiError("Gateway Timeout", 504)

        with self.assertRaises(RuntimeError) as ctx:
            interpret_idea_with_gemini("Create denim outfits")
        self.assertIn("temporarily unavailable or timed out", str(ctx.exception))
        # 1 initial + 1 retry = 2 calls
        self.assertEqual(mock_client.interactions.create.call_count, 2)

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_429_quota_fails_immediately_without_retries(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.interactions.create.side_effect = MockGenAiError("Resource Exhausted", 429)

        with self.assertRaises(RuntimeError) as ctx:
            interpret_idea_with_gemini("Create denim outfits")
        self.assertIn("quota exceeded", str(ctx.exception))
        # Exactly 1 call, no retries
        self.assertEqual(mock_client.interactions.create.call_count, 1)

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_404_invalid_model_fails_immediately_without_retries(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.interactions.create.side_effect = MockGenAiError("Model Not Found", 404)

        with self.assertRaises(RuntimeError) as ctx:
            interpret_idea_with_gemini("Create denim outfits", model="non-existent-model")
        self.assertIn("non-existent-model' was not found", str(ctx.exception))
        # Exactly 1 call, no retries
        self.assertEqual(mock_client.interactions.create.call_count, 1)

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_401_authentication_failure_fails_immediately_without_retries(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.interactions.create.side_effect = MockGenAiError("Invalid API key", 401)

        with self.assertRaises(RuntimeError) as ctx:
            interpret_idea_with_gemini("Create denim outfits")
        self.assertIn("authentication failed", str(ctx.exception))
        # Exactly 1 call, no retries
        self.assertEqual(mock_client.interactions.create.call_count, 1)

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_api_timeout_error_fails_immediately_without_repeated_waiting(self, mock_client_cls):
        class APITimeoutError(Exception):
            pass

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.interactions.create.side_effect = APITimeoutError("Request timed out.")

        with self.assertRaises(RuntimeError) as ctx:
            interpret_idea_with_gemini("Create denim outfits")
        self.assertIn("timed out", str(ctx.exception))
        # Client timeouts should not repeat long wait cycles
        self.assertEqual(mock_client.interactions.create.call_count, 1)

    def test_sanitize_message_strips_api_keys(self):
        secret = "AIzaSySecretKey987654321"
        raw_msg = f"Failed to connect using key={secret} at url https://example.com"
        clean = _sanitize_message(raw_msg, secret)
        self.assertNotIn(secret, clean)
        self.assertIn("[REDACTED_API_KEY]", clean)

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_character_filtering_and_deduplication(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        payload = dict(self.valid_payload)
        payload["requested_characters"] = [
            "WW-CHAR-01",
            "UNKNOWN-CHAR",
            "WW-CHAR-01",
            "WW-CHAR-03",
        ]
        mock_client.interactions.create.return_value = MockInteraction(json.dumps(payload))

        result = interpret_idea_with_gemini("Create denim outfits")
        # Should keep only allowed characters, deduplicated
        self.assertEqual(result["requested_characters"], ["WW-CHAR-01", "WW-CHAR-03"])

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_outfit_count_normalization(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        payload = dict(self.valid_payload)
        payload["outfit_count"] = 99  # > 20 is invalid
        mock_client.interactions.create.return_value = MockInteraction(json.dumps(payload))

        result = interpret_idea_with_gemini("Create denim outfits")
        self.assertIsNone(result["outfit_count"])

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_audience_normalization(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        payload = dict(self.valid_payload)
        payload["audience"] = "Toddlers and kids"  # Not in allowed audiences
        mock_client.interactions.create.return_value = MockInteraction(json.dumps(payload))

        result = interpret_idea_with_gemini("Create denim outfits")
        self.assertIsNone(result["audience"])


if __name__ == "__main__":
    unittest.main()
