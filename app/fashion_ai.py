"""Gemini-powered idea interpretation for Wear & Wonder."""
import json
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
import httpx

from app.topic_router import classify_topic

load_dotenv()

DEFAULT_MODEL = "gemini-3.5-flash"
ALLOWED_CHARACTER_IDS = {
    "WW-CHAR-01",
    "WW-CHAR-02",
    "WW-CHAR-03",
}
ALLOWED_AUDIENCES = {
    "College girls",
    "College boys",
    "Couples",
    "General audience",
    None,
}

MAX_RETRIES = 1
INITIAL_BACKOFF = 1.0
REQUEST_TIMEOUT = 90.0


def _sanitize_message(message: str, secret: str | None = None) -> str:
    """Remove potential API keys or sensitive tokens from error messages."""
    if not message:
        return ""
    clean = message
    if secret:
        clean = clean.replace(secret, "[REDACTED_API_KEY]")
    clean = re.sub(
        r'(?:key|api_key|token)[=:]\s*[\w-]+',
        'key=[REDACTED]',
        clean,
        flags=re.IGNORECASE,
    )
    return clean


def _extract_status_code(exc: Exception) -> int | None:
    """Safely extract an HTTP status code from an exception if present."""
    if hasattr(exc, "status_code") and isinstance(exc.status_code, int):
        return exc.status_code
    if hasattr(exc, "code") and isinstance(exc.code, int):
        return exc.code
    raw_res = getattr(exc, "raw_response", None) or getattr(exc, "response", None)
    if (
        raw_res is not None
        and hasattr(raw_res, "status_code")
        and isinstance(raw_res.status_code, int)
    ):
        return raw_res.status_code
    msg = str(exc)
    for code in (401, 403, 404, 429, 500, 502, 503, 504):
        if (
            f" {code} " in f" {msg} "
            or f"HTTP {code}" in msg
            or f"status_code={code}" in msg
            or f"{code} " in msg
        ):
            return code
    return None


def _extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object returned by Gemini."""
    if not text or not text.strip():
        raise ValueError("Gemini returned an empty response. Please retry.")

    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Gemini returned invalid or unparseable JSON. Please retry."
        ) from exc

    if not isinstance(result, dict):
        raise ValueError("Gemini response must be a JSON object.")

    return result


def interpret_idea_with_gemini(
    idea: str,
    additional_requirements: str | None = None,
    reference_url: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Interpret a fashion video idea and prepare a research plan."""
    idea = idea.strip()

    if not idea:
        raise ValueError("Video idea cannot be empty.")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY was not found. Check the project-root .env file."
        )

    target_model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    classified_topic = classify_topic(idea)

    prompt = f"""
Plan a fashion video for Wear & Wonder. Interpret the user's idea faithfully.
This is planning only: do not claim to have researched the live web, verified
trends, approved outfits, or generated assets.

Consider complete looks, proportions, fit, fabric, colour harmony, occasion,
season, footwear, accessories, practicality, and distinctness between outfits.
Do not generate image or video prompts.

Character IDs:
WW-CHAR-01 = Female Model 01
WW-CHAR-02 = Female Model 02
WW-CHAR-03 = Male Model 01

Return one JSON object with exactly these fields:
{{
  "primary_topic": "{classified_topic.topic_id}",
  "audience": null,
  "outfit_count": null,
  "requested_characters": [],
  "concept_summary": "",
  "styling_direction": "",
  "research_plan": [],
  "validation_checklist": [],
  "clarifying_questions": [],
  "assumptions": []
}}

Rules:
- audience must be "College girls", "College boys", "Couples",
  "General audience", or null.
- outfit_count must be an integer from 1 to 20 or null.
- Include only the character IDs listed above.
- Do not invent an outfit count or character selection.
- Keep lists concise. Ask only essential clarification questions.
- Separate stylistic suggestions from claims requiring external evidence.

USER IDEA:
{idea}

ADDITIONAL REQUIREMENTS:
{additional_requirements or "None"}

REFERENCE URL:
{reference_url or "None"}
""".strip()

    client = None
    result = None

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

        last_transient_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = client.interactions.create(
                    model=target_model,
                    input=prompt,
                    generation_config={"thinking_level": "low"},
                    timeout=REQUEST_TIMEOUT,
                )

                response_text = getattr(response, "output_text", None)
                if not response_text:
                    raise RuntimeError(
                        "Gemini returned an empty response. Check model availability "
                        "and response metadata."
                    )

                result = _extract_json(response_text)
                break

            except (ValueError, json.JSONDecodeError):
                raise
            except Exception as exc:
                exc_type_name = type(exc).__name__
                status_code = _extract_status_code(exc)

                is_auth = (status_code in (401, 403)) or exc_type_name in (
                    "AuthenticationError",
                    "PermissionDeniedError",
                )
                is_not_found = (status_code == 404) or (
                    exc_type_name == "NotFoundError"
                )
                is_quota = (status_code == 429) or (
                    exc_type_name == "RateLimitError"
                )
                is_client_timeout = (
                    isinstance(exc, (httpx.TimeoutException, TimeoutError))
                    or exc_type_name in (
                        "APITimeoutError",
                        "ReadTimeout",
                        "ConnectTimeout",
                        "TimeoutException",
                    )
                )
                is_timeout = is_client_timeout or (status_code == 504)
                is_connection = isinstance(
                    exc, (httpx.ConnectError, httpx.NetworkError)
                ) or exc_type_name in ("APIConnectionError", "ConnectError")
                is_server_error = (status_code in (500, 502, 503, 504)) or (
                    exc_type_name == "InternalServerError"
                )

                # Permanent error handling: fail immediately without retrying
                if is_auth:
                    raise RuntimeError(
                        "Gemini authentication failed (HTTP 401/403). Please verify that "
                        "GEMINI_API_KEY in your .env file is valid and active."
                    ) from exc

                if is_not_found:
                    raise RuntimeError(
                        f"Configured Gemini model '{target_model}' was not found (HTTP 404). "
                        "Please verify that the model identifier is correct and available for your account."
                    ) from exc

                if is_quota:
                    raise RuntimeError(
                        "Gemini API rate limit or quota exceeded (HTTP 429). "
                        "Please wait before submitting another request or check your Google AI Studio quota."
                    ) from exc

                if is_client_timeout:
                    # Client-side timeout: do not wait through another long cycle
                    raise RuntimeError(
                        "Gemini request timed out. Please try again shortly."
                    ) from exc

                is_transient = is_connection or is_server_error

                if not is_transient:
                    sanitized = _sanitize_message(str(exc), api_key)
                    raise RuntimeError(
                        f"Gemini API request failed ({exc_type_name}): {sanitized}"
                    ) from exc

                # Transient error: retry with bounded backoff
                last_transient_error = exc
                if attempt < MAX_RETRIES:
                    delay = INITIAL_BACKOFF * (2 ** attempt)
                    time.sleep(delay)
                    continue

                # Retries exhausted
                raise RuntimeError(
                    f"Gemini service is temporarily unavailable or timed out (HTTP {status_code or 503}). "
                    "Please try again shortly."
                ) from last_transient_error

    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    audience = result.get("audience")
    if audience not in ALLOWED_AUDIENCES:
        audience = None

    count = result.get("outfit_count")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not 1 <= count <= 20
    ):
        count = None

    characters = result.get("requested_characters", [])
    if not isinstance(characters, list):
        characters = []

    characters = list(
        dict.fromkeys(
            item
            for item in characters
            if isinstance(item, str) and item in ALLOWED_CHARACTER_IDS
        )
    )

    def clean_list(value: Any, limit: int = 8) -> list[str]:
        if not isinstance(value, list):
            return []

        return [
            item.strip()[:500]
            for item in value
            if isinstance(item, str) and item.strip()
        ][:limit]

    return {
        "primary_topic": classified_topic.topic_id,
        "topic_name": classified_topic.display_name,
        "audience": audience,
        "outfit_count": count,
        "requested_characters": characters,
        "concept_summary": str(
            result.get("concept_summary", "")
        ).strip()[:1500],
        "styling_direction": str(
            result.get("styling_direction", "")
        ).strip()[:2000],
        "research_plan": clean_list(result.get("research_plan")),
        "validation_checklist": clean_list(
            result.get("validation_checklist")
        ),
        "clarifying_questions": clean_list(
            result.get("clarifying_questions")
        ),
        "assumptions": clean_list(result.get("assumptions")),
        "interpretation_method": "GEMINI_API",
        "research_status": "PENDING",
        "outfit_approval": "PENDING",
        "live_research_performed": False,
    }
