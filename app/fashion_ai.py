
"""Gemini-powered idea interpretation for Wear & Wonder."""
import json
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DEFAULT_MODEL = "gemini-3.8-flash"
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


def _extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object returned by Gemini."""
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Gemini returned invalid JSON. Please retry."
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

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=200_000),
        )

        response = client.models.generate_content(
            model=model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=1200,
            ),
        )

        response_text = getattr(response, "text", None)

        if not response_text:
            raise RuntimeError(
                "Gemini returned an empty response. Check model availability "
                "and response metadata."
            )

        result = _extract_json(response_text)

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Gemini request failed ({type(exc).__name__}): {exc}"
        ) from exc
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

    characters = list(dict.fromkeys(
        item for item in characters
        if isinstance(item, str) and item in ALLOWED_CHARACTER_IDS
    ))

    def clean_list(value: Any, limit: int = 8) -> list[str]:
        if not isinstance(value, list):
            return []

        return [
            item.strip()[:500]
            for item in value
            if isinstance(item, str) and item.strip()
        ][:limit]

    return {
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
