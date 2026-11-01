"""Publishing package and metadata management service for Wear & Wonder.
Generates, edits, and finalizes platform-ready metadata packages directly from task data.
"""
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.approval_workflow import ApprovalStatus, WorkflowStage
from app.publishing.metadata_generator import generate_publishing_metadata
from app.publishing.youtube_publisher import (
    check_youtube_auth_status,
    publish_to_youtube,
)
from app.publishing.instagram_publisher import (
    check_instagram_auth_status,
    publish_to_instagram,
)
from app.storage import (
    PROJECT_DIR,
    PUBLISHED_VIDEOS_DIR,
    PUBLISHED_THUMBNAILS_DIR,
    get_brief_by_id,
    load_image_assets,
    load_publishing_record,
    save_publishing_record,
    record_audit_event,
)


def get_or_create_publishing_record(brief_id: str) -> dict[str, Any]:
    """Retrieve existing publishing record for brief or initialize a new draft with generated metadata."""
    existing = load_publishing_record(brief_id)
    if existing:
        return existing

    brief = get_brief_by_id(brief_id)
    if not brief:
        raise ValueError(f"Brief '{brief_id}' not found.")

    metadata = generate_publishing_metadata(brief_id)
    record: dict[str, Any] = {
        "brief_id": brief_id,
        "status": "DRAFT",
        "metadata": metadata,
        "recommended_thumbnail": metadata.get("recommended_thumbnail"),
        "video_file_path": None,
        "video_filename": None,
        "video_filesize": 0,
        "video_imported_at": None,
        "thumbnail_file_path": metadata.get("recommended_thumbnail", {}).get("file_path") if metadata.get("recommended_thumbnail") else None,
        "thumbnail_filename": None,
        "thumbnail_source": "STAGE_4_RECOMMENDED" if metadata.get("recommended_thumbnail") else None,
        "platforms_selected": ["youtube", "instagram"],
        "scheduling": {
            "is_scheduled": False,
            "scheduled_time_iso": None,
            "privacy_status": "private",
        },
        "platforms_status": {
            "youtube": {
                "status": "PENDING",
                "video_id": None,
                "url": None,
                "scheduled_time": None,
                "published_at": None,
            },
            "instagram": {
                "status": "PENDING",
                "media_id": None,
                "permalink": None,
                "scheduled_time": None,
                "published_at": None,
            },
        },
        "manual_publications": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_publishing_record(brief_id, record)
    return record


def refresh_publishing_metadata(brief_id: str) -> dict[str, Any]:
    """Regenerate platform metadata based on the latest task idea, approved outfits, and video assets."""
    record = get_or_create_publishing_record(brief_id)
    new_metadata = generate_publishing_metadata(brief_id)
    record["metadata"] = new_metadata
    if new_metadata.get("recommended_thumbnail"):
        record["recommended_thumbnail"] = new_metadata["recommended_thumbnail"]
        if not record.get("thumbnail_file_path"):
            record["thumbnail_file_path"] = new_metadata["recommended_thumbnail"].get("file_path")
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_publishing_record(brief_id, record)

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_6_PUBLISHING.value,
        action="METADATA_REGENERATED",
        details="Regenerated platform publishing metadata from latest task brief and approved outfits.",
    )
    return record


def update_publishing_metadata(brief_id: str, platform: str, updated_fields: dict[str, Any]) -> dict[str, Any]:
    """Update title, description, caption, tags, or hashtags in the publishing record while preserving manual edits."""
    record = get_or_create_publishing_record(brief_id)
    if platform not in record.get("metadata", {}):
        raise ValueError(f"Unknown platform '{platform}'. Must be 'youtube' or 'instagram'.")

    record["metadata"][platform].update(updated_fields)
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_publishing_record(brief_id, record)
    return record


def set_recommended_thumbnail_choice(brief_id: str, image_id: str) -> dict[str, Any]:
    """Set or update the recommended Stage 4 thumbnail for this task."""
    images = load_image_assets(brief_id)
    target_img = next((img for img in images if img.get("image_id") == image_id), None)
    if not target_img:
        raise ValueError(f"Image '{image_id}' not found in task assets.")

    record = get_or_create_publishing_record(brief_id)
    rec_thumb = {
        "image_id": target_img.get("image_id"),
        "outfit_id": target_img.get("outfit_id"),
        "character_name": target_img.get("character_name") or target_img.get("character_id") or "Model",
        "file_path": target_img.get("file_path"),
        "is_dual_model": bool(target_img.get("is_dual_model")),
        "recommendation_reason": f"Selected approved Stage 4 visual for {target_img.get('outfit_id', 'Look')}",
    }
    record["recommended_thumbnail"] = rec_thumb
    record["thumbnail_file_path"] = target_img.get("file_path")
    record["thumbnail_source"] = f"STAGE_4_{target_img.get('image_id')}"
    if "metadata" in record and isinstance(record["metadata"], dict):
        record["metadata"]["recommended_thumbnail"] = rec_thumb

    save_publishing_record(brief_id, record)
    return record


def save_and_approve_publishing_package(
    brief_id: str,
    user_name: str = "Creator",
    notes: str = "",
) -> dict[str, Any]:
    """Approve and finalize the platform publishing package for the given brief/task."""
    record = get_or_create_publishing_record(brief_id)
    old_status = record.get("status", "DRAFT")
    record["status"] = "APPROVED"
    record["approved_by"] = user_name
    record["approved_at"] = datetime.now(timezone.utc).isoformat()
    record["approval_notes"] = notes
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_publishing_record(brief_id, record)

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_6_PUBLISHING.value,
        action="PUBLISHING_PACKAGE_APPROVED",
        from_status=old_status,
        to_status="APPROVED",
        details=f"Publishing package reviewed and approved by {user_name}. Notes: {notes or 'Ready for distribution'}.",
    )
    return record


# --- Retained Storage Utilities (Preserves existing file storage and backward compatibility) ---

def import_assembled_video(brief_id: str, video_bytes: bytes, filename: str) -> dict[str, Any]:
    """Optional storage helper: persist an assembled video file if user has one."""
    if not video_bytes or len(video_bytes) == 0:
        raise ValueError("Cannot import empty video file.")

    ext = Path(filename).suffix.lower()
    if ext not in (".mp4", ".mov", ".webm"):
        raise ValueError(f"Unsupported video format '{ext}'. Allowed formats: .mp4, .mov, .webm")

    PUBLISHED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    saved_filename = f"{brief_id[:8]}_assembled_{int(datetime.now().timestamp())}{ext}"
    dest_path = PUBLISHED_VIDEOS_DIR / saved_filename

    dest_path.write_bytes(video_bytes)
    relative_path = str(dest_path.relative_to(PROJECT_DIR))

    record = get_or_create_publishing_record(brief_id)
    record["video_file_path"] = relative_path
    record["video_filename"] = filename
    record["video_filesize"] = len(video_bytes)
    record["video_imported_at"] = datetime.now(timezone.utc).isoformat()
    save_publishing_record(brief_id, record)
    return record


def import_custom_thumbnail(brief_id: str, image_bytes: bytes, filename: str) -> dict[str, Any]:
    """Optional storage helper: persist a custom thumbnail image if user has one."""
    if not image_bytes or len(image_bytes) == 0:
        raise ValueError("Cannot import empty thumbnail image.")

    ext = Path(filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError(f"Unsupported image format '{ext}'. Allowed formats: .png, .jpg, .jpeg, .webp")

    PUBLISHED_THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
    saved_filename = f"{brief_id[:8]}_thumb_{int(datetime.now().timestamp())}{ext}"
    dest_path = PUBLISHED_THUMBNAILS_DIR / saved_filename

    dest_path.write_bytes(image_bytes)
    relative_path = str(dest_path.relative_to(PROJECT_DIR))

    record = get_or_create_publishing_record(brief_id)
    record["thumbnail_file_path"] = relative_path
    record["thumbnail_filename"] = filename
    record["thumbnail_source"] = "CUSTOM_UPLOAD"
    save_publishing_record(brief_id, record)
    return record


def set_master_image_as_thumbnail(brief_id: str, image_id: str | None = None) -> dict[str, Any]:
    """Alias for set_recommended_thumbnail_choice for backwards compatibility."""
    images = load_image_assets(brief_id)
    if not images:
        raise ValueError("No images found in Stage 4 Image Studio.")
    target_id = image_id or images[0].get("image_id")
    return set_recommended_thumbnail_choice(brief_id, target_id)


def approve_and_schedule_video(
    brief_id: str,
    platforms: list[str],
    scheduled_time_iso: str | None = None,
    privacy_status: str = "private",
    user_name: str = "User",
    mock_mode: bool = False,
) -> dict[str, Any]:
    """Optional direct dispatch helper for future API scheduling (retained for backward compatibility)."""
    record = get_or_create_publishing_record(brief_id)
    target_status = "SCHEDULED" if scheduled_time_iso else "PUBLISHED"
    record["status"] = target_status
    record["platforms_selected"] = platforms
    record.setdefault("scheduling", {})["is_scheduled"] = bool(scheduled_time_iso)
    record["scheduling"]["scheduled_time_iso"] = scheduled_time_iso
    record["scheduling"]["privacy_status"] = privacy_status

    for p in platforms:
        if p == "youtube":
            mock_id = f"yt_{int(datetime.now().timestamp())}"
            record.setdefault("platforms_status", {})["youtube"] = {
                "status": target_status,
                "video_id": mock_id,
                "url": f"https://youtube.com/shorts/{mock_id}",
                "scheduled_time": scheduled_time_iso,
                "published_at": datetime.now(timezone.utc).isoformat(),
            }
        elif p == "instagram":
            mock_id = f"ig_{int(datetime.now().timestamp())}"
            record.setdefault("platforms_status", {})["instagram"] = {
                "status": target_status,
                "media_id": mock_id,
                "permalink": f"https://www.instagram.com/reel/C{mock_id[-6:]}/",
                "scheduled_time": scheduled_time_iso,
                "published_at": datetime.now(timezone.utc).isoformat(),
            }

    save_publishing_record(brief_id, record)
    return record


def record_manual_publication(
    brief_id: str,
    platform: str,
    live_url: str,
    scheduled_time_iso: str | None = None,
    notes: str = "",
    user_name: str = "User",
) -> dict[str, Any]:
    """Record a publication link in the audit history."""
    record = get_or_create_publishing_record(brief_id)
    plat_key = platform.lower()
    status_val = "SCHEDULED" if scheduled_time_iso else "PUBLISHED"
    entry = {
        "platform": plat_key,
        "url": live_url.strip(),
        "status": status_val,
        "scheduled_time": scheduled_time_iso,
        "notes": notes,
        "recorded_by": user_name,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    record.setdefault("manual_publications", []).append(entry)
    record["status"] = status_val
    save_publishing_record(brief_id, record)
    return record
