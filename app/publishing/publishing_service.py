"""End-to-end publishing and scheduling orchestration service for Wear & Wonder."""
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
        "video_file_path": None,
        "video_filename": None,
        "video_filesize": 0,
        "video_imported_at": None,
        "thumbnail_file_path": None,
        "thumbnail_filename": None,
        "thumbnail_source": None,
        "metadata": metadata,
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


def import_assembled_video(brief_id: str, video_bytes: bytes, filename: str) -> dict[str, Any]:
    """Import and persist the user's final assembled 9:16 video on disk."""
    if not video_bytes or len(video_bytes) == 0:
        raise ValueError("Cannot import empty video file.")

    ext = Path(filename).suffix.lower()
    if ext not in (".mp4", ".mov", ".webm"):
        raise ValueError(f"Unsupported video format '{ext}'. Allowed formats: .mp4, .mov, .webm")

    PUBLISHED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
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

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_6_PUBLISHING.value,
        action="ASSEMBLED_VIDEO_IMPORTED",
        from_status=record.get("status"),
        to_status="READY_FOR_APPROVAL",
        details=f"Assembled video '{filename}' ({len(video_bytes)} bytes) imported successfully.",
    )
    return record


def import_custom_thumbnail(brief_id: str, image_bytes: bytes, filename: str) -> dict[str, Any]:
    """Import and persist a custom cover thumbnail image on disk."""
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

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_6_PUBLISHING.value,
        action="CUSTOM_THUMBNAIL_IMPORTED",
        details=f"Custom thumbnail '{filename}' saved.",
    )
    return record


def set_master_image_as_thumbnail(brief_id: str, image_id: str | None = None) -> dict[str, Any]:
    """Select an approved Stage 4 master image as the video thumbnail."""
    images = load_image_assets(brief_id)
    approved_images = [
        img for img in images
        if img.get("approval_status") == ApprovalStatus.APPROVED.value
        and img.get("file_path")
        and (PROJECT_DIR / img["file_path"]).is_file()
    ]

    if not approved_images:
        raise ValueError("No approved images with valid files found in Stage 4 Image Studio.")

    target_img = None
    if image_id:
        target_img = next((img for img in approved_images if img.get("image_id") == image_id), None)
        if not target_img:
            raise ValueError(f"Approved image '{image_id}' not found.")
    else:
        target_img = approved_images[0]

    record = get_or_create_publishing_record(brief_id)
    record["thumbnail_file_path"] = target_img["file_path"]
    record["thumbnail_filename"] = Path(target_img["file_path"]).name
    record["thumbnail_source"] = f"STAGE_4_{target_img.get('image_id')}"
    save_publishing_record(brief_id, record)

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_6_PUBLISHING.value,
        action="STAGE_4_THUMBNAIL_SELECTED",
        asset_id=target_img.get("image_id"),
        details=f"Selected approved Stage 4 image ({target_img.get('image_id')}) as publishing thumbnail.",
    )
    return record


def update_publishing_metadata(brief_id: str, platform: str, updated_fields: dict[str, Any]) -> dict[str, Any]:
    """Update title, description, caption, tags, or hashtags in the publishing record."""
    record = get_or_create_publishing_record(brief_id)
    if platform not in record.get("metadata", {}):
        raise ValueError(f"Unknown platform '{platform}'. Must be 'youtube' or 'instagram'.")

    record["metadata"][platform].update(updated_fields)
    save_publishing_record(brief_id, record)
    return record


def refresh_publishing_metadata(brief_id: str) -> dict[str, Any]:
    """Regenerate platform metadata based on the latest approved outfits and brief contents."""
    record = get_or_create_publishing_record(brief_id)
    record["metadata"] = generate_publishing_metadata(brief_id)
    save_publishing_record(brief_id, record)
    return record


def approve_and_schedule_video(
    brief_id: str,
    platforms: list[str],
    scheduled_time_iso: str | None = None,
    privacy_status: str = "private",
    user_name: str = "User",
    mock_mode: bool = False,
) -> dict[str, Any]:
    """Mandatory Approval Gate: Publish or schedule video across selected platforms after explicit user confirmation."""
    record = get_or_create_publishing_record(brief_id)

    video_rel_path = record.get("video_file_path")
    if not video_rel_path:
        raise ValueError("Cannot publish: No assembled video uploaded. Please upload your final video in Stage 6 first.")

    full_video_path = PROJECT_DIR / video_rel_path
    if not full_video_path.is_file():
        raise FileNotFoundError(f"Cannot publish: Video file missing from disk at {video_rel_path}")

    full_thumb_path = None
    if record.get("thumbnail_file_path"):
        p = PROJECT_DIR / record["thumbnail_file_path"]
        if p.is_file():
            full_thumb_path = p

    metadata = record.get("metadata", {})
    yt_meta = metadata.get("youtube", {})
    ig_meta = metadata.get("instagram", {})

    results: dict[str, Any] = {}
    is_scheduled = bool(scheduled_time_iso)

    # 1. YouTube Dispatch
    if "youtube" in platforms:
        yt_res = publish_to_youtube(
            video_path=full_video_path,
            title=yt_meta.get("title", "Wear & Wonder Style Showcase #Shorts"),
            description=yt_meta.get("description", ""),
            tags=yt_meta.get("tags"),
            category_id=yt_meta.get("category_id", "26"),
            privacy_status=privacy_status,
            scheduled_publish_time=scheduled_time_iso,
            thumbnail_path=full_thumb_path,
            mock_mode=mock_mode,
        )
        record["platforms_status"]["youtube"] = {
            "status": yt_res.get("status"),
            "video_id": yt_res.get("video_id"),
            "url": yt_res.get("url"),
            "scheduled_time": scheduled_time_iso,
            "published_at": yt_res.get("published_at"),
        }
        results["youtube"] = yt_res

    # 2. Instagram Dispatch
    if "instagram" in platforms:
        # Convert ISO scheduled time to Unix timestamp for Instagram Graph API if present
        unix_ts = None
        if scheduled_time_iso:
            try:
                dt = datetime.fromisoformat(scheduled_time_iso.replace("Z", "+00:00"))
                unix_ts = int(dt.timestamp())
            except Exception:
                unix_ts = None

        ig_res = publish_to_instagram(
            video_path=full_video_path,
            caption=ig_meta.get("caption", ""),
            scheduled_publish_time=unix_ts,
            cover_path=full_thumb_path,
            mock_mode=mock_mode,
        )
        record["platforms_status"]["instagram"] = {
            "status": ig_res.get("status"),
            "media_id": ig_res.get("media_id"),
            "permalink": ig_res.get("permalink"),
            "scheduled_time": scheduled_time_iso,
            "published_at": ig_res.get("published_at"),
        }
        results["instagram"] = ig_res

    target_status = "SCHEDULED" if is_scheduled else "PUBLISHED"
    record["status"] = target_status
    record["platforms_selected"] = platforms
    record["scheduling"]["is_scheduled"] = is_scheduled
    record["scheduling"]["scheduled_time_iso"] = scheduled_time_iso
    record["scheduling"]["privacy_status"] = privacy_status

    save_publishing_record(brief_id, record)

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_6_PUBLISHING.value,
        action=f"VIDEO_{target_status}",
        from_status="READY_FOR_APPROVAL",
        to_status=target_status,
        details=(
            f"Approved and {target_status.lower()} by {user_name} across {', '.join(platforms)}. "
            f"YouTube: {record['platforms_status'].get('youtube', {}).get('url') or 'N/A'}, "
            f"Instagram: {record['platforms_status'].get('instagram', {}).get('permalink') or 'N/A'}."
        ),
    )

    return record


def record_manual_publication(
    brief_id: str,
    platform: str,
    live_url: str,
    scheduled_time_iso: str | None = None,
    notes: str = "",
    user_name: str = "User",
) -> dict[str, Any]:
    """Mode B helper: Record a manual upload completed via YouTube Studio or Meta Business Suite."""
    record = get_or_create_publishing_record(brief_id)

    plat_key = platform.lower()
    if plat_key not in ("youtube", "instagram"):
        raise ValueError("Platform must be either 'youtube' or 'instagram'.")

    status_val = "SCHEDULED" if scheduled_time_iso else "PUBLISHED"
    manual_entry = {
        "platform": plat_key,
        "url": live_url.strip(),
        "status": status_val,
        "scheduled_time": scheduled_time_iso,
        "notes": notes,
        "recorded_by": user_name,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    record.setdefault("manual_publications", []).append(manual_entry)

    # Update active platform status if URL provided
    if plat_key == "youtube":
        record["platforms_status"]["youtube"] = {
            "status": status_val,
            "video_id": re.sub(r".*shorts/|.*v=", "", live_url).split("&")[0].split("?")[0],
            "url": live_url.strip(),
            "scheduled_time": scheduled_time_iso,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
    elif plat_key == "instagram":
        record["platforms_status"]["instagram"] = {
            "status": status_val,
            "media_id": "manual_entry",
            "permalink": live_url.strip(),
            "scheduled_time": scheduled_time_iso,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    record["status"] = status_val
    save_publishing_record(brief_id, record)

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_6_PUBLISHING.value,
        action="MANUAL_PUBLICATION_CONFIRMED",
        to_status=status_val,
        details=f"User {user_name} confirmed manual upload to {platform.title()} at {live_url}. Notes: {notes or 'None'}",
    )
    return record
