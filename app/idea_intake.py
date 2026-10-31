import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.topic_router import classify_topic, get_topic_config

DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "research.json"
)


def interpret_idea(idea: str) -> dict:
    """Extract explicit details with local rules; this is not AI research."""
    original_idea = idea
    text = idea.strip()
    if not text:
        raise ValueError("Video idea cannot be empty.")

    topic_cfg = classify_topic(text)

    number_words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    count_match = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s+(?:\w+\s+){0,5}(?:outfits?|looks?|combinations?)\b",
        text, re.IGNORECASE,
    )
    outfit_count = None
    if count_match:
        count_text = count_match.group(1).lower()
        outfit_count = int(count_text) if count_text.isdigit() else number_words[count_text]

    audience = None
    if re.search(r"\bcollege girls\b", text, re.IGNORECASE):
        audience = "College girls"
    elif re.search(r"\bcollege boys\b", text, re.IGNORECASE):
        audience = "College boys"
    elif re.search(r"\bcouples?\b", text, re.IGNORECASE):
        audience = "Couples"

    characters = []
    if re.search(r"\b(female|woman|women|girl|girls)\b", text, re.IGNORECASE):
        characters.append("WW-CHAR-01")
    if re.search(r"\b(male|man|men|boy|boys)\b", text, re.IGNORECASE):
        characters.append("WW-CHAR-03")
    if re.search(r"\b(second female model|female model 2|ww-char-02)\b", text, re.IGNORECASE):
        characters.append("WW-CHAR-02")
    if re.search(r"\b(all three|three models|all models)\b", text, re.IGNORECASE):
        characters = ["WW-CHAR-01", "WW-CHAR-02", "WW-CHAR-03"]

    return {
        "idea_original": original_idea,
        "primary_topic": topic_cfg.topic_id,
        "topic_name": topic_cfg.display_name,
        "audience": audience,
        "outfit_count": outfit_count,
        "requested_characters": list(dict.fromkeys(characters)),
        "interpretation_method": "LOCAL_RULES",
        "interpretation_note": (
            "Extracted details are suggestions. Review them before approving "
            "the research brief. Local rules do not perform live research."
        ),
    }


def create_research_brief(
    idea: str,
    requested_characters: list[str] | None = None,
    audience: str | None = None,
    outfit_count: int | None = None,
    additional_requirements: str | None = None,
    primary_topic: str | None = None,
) -> dict:
    """Create a structured research brief with a unique ID."""
    interpreted = interpret_idea(idea)
    allowed_characters = {"WW-CHAR-01", "WW-CHAR-02", "WW-CHAR-03"}
    characters = requested_characters if requested_characters is not None else interpreted["requested_characters"]

    if len(characters) != len(set(characters)):
        raise ValueError("Duplicate character IDs are not allowed.")
    invalid = set(characters) - allowed_characters
    if invalid:
        raise ValueError(f"Unknown character IDs: {sorted(invalid)}")
    if outfit_count is not None and (isinstance(outfit_count, bool) or outfit_count < 1):
        raise ValueError("Outfit count must be at least 1.")
    if outfit_count is not None and outfit_count != int(outfit_count):
        raise ValueError("Outfit count must be a whole number.")

    topic_id = primary_topic or interpreted.get("primary_topic", "general_fashion")
    topic_cfg = get_topic_config(topic_id)

    return {
        "brief_id": str(uuid.uuid4()),
        **interpreted,
        "primary_topic": topic_cfg.topic_id,
        "topic_name": topic_cfg.display_name,
        "audience": audience if audience is not None else interpreted["audience"],
        "outfit_count": outfit_count if outfit_count is not None else interpreted["outfit_count"],
        "requested_characters": characters,
        "additional_requirements": additional_requirements,
        "research_status": "PENDING",
        "outfit_approval": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def save_research_brief(brief: dict) -> None:
    """Append or update a research brief without overwriting existing records."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        try:
            records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Research file contains invalid JSON: {DATA_FILE}") from exc
        if not isinstance(records, list):
            raise ValueError("Research data must be a JSON list.")
    else:
        records = []

    brief_id = brief.get("brief_id")
    if not brief_id:
        raise ValueError("Research brief must have a unique brief_id.")

    existing_index = next(
        (i for i, r in enumerate(records) if isinstance(r, dict) and r.get("brief_id") == brief_id),
        None,
    )
    if existing_index is not None:
        records[existing_index] = brief
    else:
        records.append(brief)

    temporary_file = DATA_FILE.with_suffix(".tmp")
    try:
        temporary_file.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary_file.replace(DATA_FILE)
    finally:
        if temporary_file.exists():
            temporary_file.unlink()
