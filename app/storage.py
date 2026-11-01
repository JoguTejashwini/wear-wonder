"""Atomic local storage manager for Wear & Wonder."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

RESEARCH_FILE = DATA_DIR / "research.json"
OUTFITS_FILE = DATA_DIR / "outfits.json"
RESEARCH_SOURCES_FILE = DATA_DIR / "research_sources.json"
IMAGE_ASSETS_FILE = DATA_DIR / "image_assets.json"
VIDEO_ASSETS_FILE = DATA_DIR / "video_assets.json"
PUBLISHING_RECORDS_FILE = DATA_DIR / "publishing_records.json"
AUDIT_LOG_FILE = DATA_DIR / "workflow_audit.json"

PUBLISHED_VIDEOS_DIR = PROJECT_DIR / "assets" / "published_videos"
PUBLISHED_THUMBNAILS_DIR = PROJECT_DIR / "assets" / "published_thumbnails"


def _atomic_write_json(file_path: Path, data: Any) -> None:
    """Atomically write JSON data to file using a temporary replacement."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.with_suffix(f".tmp_{datetime.now().timestamp()}")
    try:
        temp_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp_file.replace(file_path)
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass


def _read_json_list(file_path: Path) -> list[dict]:
    """Safely read a JSON list from disk. Returns empty list if missing."""
    if not file_path.exists():
        return []
    try:
        content = file_path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        data = json.loads(content)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _read_json_dict(file_path: Path) -> dict[str, Any]:
    """Safely read a JSON dict from disk. Returns empty dict if missing."""
    if not file_path.exists():
        return {}
    try:
        content = file_path.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Briefs Storage (data/research.json)
# ---------------------------------------------------------------------------

def load_all_briefs() -> list[dict]:
    """Load all research brief records."""
    return _read_json_list(RESEARCH_FILE)


def get_brief_by_id(brief_id: str) -> dict | None:
    """Retrieve a single brief by its brief_id."""
    for record in load_all_briefs():
        if isinstance(record, dict) and record.get("brief_id") == brief_id:
            return record
    return None


def save_or_update_brief(brief: dict) -> None:
    """Save a new brief or update an existing one without overwriting others."""
    brief_id = brief.get("brief_id")
    if not brief_id:
        raise ValueError("Brief must contain a brief_id.")

    records = load_all_briefs()
    existing_index = next(
        (i for i, r in enumerate(records) if isinstance(r, dict) and r.get("brief_id") == brief_id),
        None,
    )

    if existing_index is not None:
        records[existing_index] = brief
    else:
        records.append(brief)

    _atomic_write_json(RESEARCH_FILE, records)


# ---------------------------------------------------------------------------
# Research Sources Storage (data/research_sources.json)
# ---------------------------------------------------------------------------

def load_research_sources(brief_id: str) -> list[dict]:
    """Load research sources for a given brief_id."""
    all_sources = _read_json_dict(RESEARCH_SOURCES_FILE)
    return all_sources.get(brief_id, [])


def save_research_sources(brief_id: str, sources: list[dict], summary: dict | None = None) -> None:
    """Save research sources and optional synthesis summary for a brief."""
    all_sources = _read_json_dict(RESEARCH_SOURCES_FILE)
    all_sources[brief_id] = {
        "sources": sources,
        "summary": summary or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(RESEARCH_SOURCES_FILE, all_sources)


def get_research_data(brief_id: str) -> dict[str, Any]:
    """Get full research data dictionary (sources + summary) for a brief."""
    all_sources = _read_json_dict(RESEARCH_SOURCES_FILE)
    data = all_sources.get(brief_id, {})
    if isinstance(data, list):
        # Backwards compatibility if stored as a list
        return {"sources": data, "summary": {}, "updated_at": None}
    return data


# ---------------------------------------------------------------------------
# Outfits Storage (data/outfits.json)
# ---------------------------------------------------------------------------

def load_outfits(brief_id: str) -> list[dict]:
    """Load outfit proposals for a given brief_id."""
    all_outfits = _read_json_dict(OUTFITS_FILE)
    return all_outfits.get(brief_id, [])


def save_outfits(brief_id: str, outfits: list[dict]) -> None:
    """Save outfit proposals for a given brief_id."""
    all_outfits = _read_json_dict(OUTFITS_FILE)
    all_outfits[brief_id] = outfits
    _atomic_write_json(OUTFITS_FILE, all_outfits)


def update_outfit(brief_id: str, outfit_id: str, updated_fields: dict) -> dict:
    """Update a specific outfit within a brief, preserving other outfits."""
    outfits = load_outfits(brief_id)
    target = None
    for outfit in outfits:
        if outfit.get("outfit_id") == outfit_id:
            outfit.update(updated_fields)
            outfit["updated_at"] = datetime.now(timezone.utc).isoformat()
            target = outfit
            break

    if target is None:
        raise ValueError(f"Outfit '{outfit_id}' not found in brief '{brief_id}'.")

    save_outfits(brief_id, outfits)
    return target


# ---------------------------------------------------------------------------
# Image Assets Storage (data/image_assets.json)
# ---------------------------------------------------------------------------

def load_image_assets(brief_id: str) -> list[dict]:
    """Load image asset records for a brief."""
    all_images = _read_json_dict(IMAGE_ASSETS_FILE)
    return all_images.get(brief_id, [])


def save_image_assets(brief_id: str, image_assets: list[dict]) -> None:
    """Save image asset records for a brief."""
    all_images = _read_json_dict(IMAGE_ASSETS_FILE)
    all_images[brief_id] = image_assets
    _atomic_write_json(IMAGE_ASSETS_FILE, all_images)


def update_image_asset(brief_id: str, image_id: str, updated_fields: dict) -> dict:
    """Update an individual image asset record."""
    images = load_image_assets(brief_id)
    target = None
    for img in images:
        if img.get("image_id") == image_id:
            img.update(updated_fields)
            img["updated_at"] = datetime.now(timezone.utc).isoformat()
            target = img
            break
    if target is None:
        raise ValueError(f"Image asset '{image_id}' not found in brief '{brief_id}'.")
    save_image_assets(brief_id, images)
    return target


# ---------------------------------------------------------------------------
# Video Assets Storage (data/video_assets.json)
# ---------------------------------------------------------------------------

def load_video_assets(brief_id: str) -> list[dict]:
    """Load video clip asset records for a brief."""
    all_videos = _read_json_dict(VIDEO_ASSETS_FILE)
    return all_videos.get(brief_id, [])


def save_video_assets(brief_id: str, video_assets: list[dict]) -> None:
    """Save video clip asset records for a brief."""
    all_videos = _read_json_dict(VIDEO_ASSETS_FILE)
    all_videos[brief_id] = video_assets
    _atomic_write_json(VIDEO_ASSETS_FILE, all_videos)


def update_video_asset(brief_id: str, clip_id: str, updated_fields: dict) -> dict:
    """Update an individual video asset record."""
    videos = load_video_assets(brief_id)
    target = None
    for vid in videos:
        if vid.get("clip_id") == clip_id:
            vid.update(updated_fields)
            vid["updated_at"] = datetime.now(timezone.utc).isoformat()
            target = vid
            break
    if target is None:
        raise ValueError(f"Video clip '{clip_id}' not found in brief '{brief_id}'.")
    save_video_assets(brief_id, videos)
    return target


# ---------------------------------------------------------------------------
# Workflow Audit Log (data/workflow_audit.json)
# ---------------------------------------------------------------------------

def record_audit_event(
    brief_id: str,
    action: str,
    stage: str,
    details: str,
    from_status: str | None = None,
    to_status: str | None = None,
    asset_id: str | None = None,
) -> dict:
    """Append a structured workflow transition event to the audit trail."""
    all_logs = _read_json_dict(AUDIT_LOG_FILE)
    brief_logs = all_logs.get(brief_id, [])

    event = {
        "event_id": f"EVT-{len(brief_logs) + 1:04d}",
        "brief_id": brief_id,
        "stage": stage,
        "action": action,
        "from_status": from_status,
        "to_status": to_status,
        "asset_id": asset_id,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    brief_logs.append(event)
    all_logs[brief_id] = brief_logs
    _atomic_write_json(AUDIT_LOG_FILE, all_logs)
    return event


def load_audit_events(brief_id: str) -> list[dict]:
    """Retrieve all audit events for a brief."""
    all_logs = _read_json_dict(AUDIT_LOG_FILE)
    return all_logs.get(brief_id, [])


# ---------------------------------------------------------------------------
# Publishing & Scheduling Records (data/publishing_records.json)
# ---------------------------------------------------------------------------

def load_all_publishing_records() -> dict[str, dict]:
    """Load all publishing records mapped by brief_id."""
    return _read_json_dict(PUBLISHING_RECORDS_FILE)


def load_publishing_record(brief_id: str) -> dict | None:
    """Retrieve the publishing and scheduling record for a specific brief."""
    all_records = load_all_publishing_records()
    return all_records.get(brief_id)


def save_publishing_record(brief_id: str, record: dict) -> None:
    """Save or update the publishing and scheduling record for a specific brief."""
    all_records = load_all_publishing_records()
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    all_records[brief_id] = record
    _atomic_write_json(PUBLISHING_RECORDS_FILE, all_records)

