"""Video clip generation and Google Flow handoff management service."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.approval_workflow import (
    ApprovalStatus,
    set_video_approval_status,
)
from app.storage import (
    get_brief_by_id,
    load_image_assets,
    load_outfits,
    load_video_assets,
    save_video_assets,
    record_audit_event,
)
from app.video_generation.video_prompt_builder import build_video_prompt_for_outfit

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
GENERATED_VIDEOS_DIR = PROJECT_DIR / "assets" / "generated_videos"


def prepare_video_prompts(brief_id: str) -> list[dict[str, Any]]:
    """Construct complete video prompts and clip records for approved outfit images."""
    brief = get_brief_by_id(brief_id)
    if not brief:
        raise ValueError(f"Brief '{brief_id}' not found.")

    outfits = load_outfits(brief_id)
    approved_outfits = [o for o in outfits if o.get("approval_status") == ApprovalStatus.APPROVED.value]
    if not approved_outfits:
        raise ValueError("Cannot prepare video prompts: No approved outfits found. Approve outfits in Stage 3 first.")

    images = load_image_assets(brief_id)
    images_by_outfit = {img["outfit_id"]: img for img in images}

    # Strict prerequisite check: every approved outfit must have an APPROVED image
    unapproved_images = []
    for outfit in approved_outfits:
        oid = outfit["outfit_id"]
        img = images_by_outfit.get(oid)
        if not img or img.get("approval_status") != ApprovalStatus.APPROVED.value or not img.get("file_path"):
            unapproved_images.append(oid)

    if unapproved_images:
        raise ValueError(
            f"Cannot prepare video prompts: The following approved outfits do not have an approved image yet: {', '.join(unapproved_images)}. "
            "Please generate and approve images in Stage 4 first."
        )

    GENERATED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    existing_videos = {v["outfit_id"]: v for v in load_video_assets(brief_id)}
    video_assets: list[dict[str, Any]] = []

    # Check for dual-character setup from brief
    requested_chars = brief.get("requested_characters") or []
    has_dual_chars = len(requested_chars) >= 2

    for index, outfit in enumerate(approved_outfits):
        oid = outfit["outfit_id"]
        img = images_by_outfit[oid]

        dual_char = requested_chars[1] if (has_dual_chars and requested_chars[0] == img.get("character_id")) else (requested_chars[0] if has_dual_chars else None)

        prompt_data = build_video_prompt_for_outfit(
            outfit=outfit,
            image_asset=img,
            clip_index=index + 1,
            dual_character_id=dual_char,
        )

        existing = existing_videos.get(oid)
        clip_id = existing.get("clip_id") if existing else f"CLIP-{index + 1:02d}"
        file_path = existing.get("file_path") if existing else None
        approval_status = existing.get("approval_status") if existing else ApprovalStatus.PENDING.value

        asset_record: dict[str, Any] = {
            "clip_id": clip_id,
            "brief_id": brief_id,
            "outfit_id": oid,
            "approved_image_id": img.get("image_id"),
            "character_id": img.get("character_id"),
            "dual_character_id": dual_char,
            "prompt_data": prompt_data,
            "file_path": file_path,
            "provider": "GOOGLE_FLOW_MANUAL_HANDOFF",
            "approval_status": approval_status,
            "review_checklist": existing.get("review_checklist") if existing else {
                "character_identity": False,
                "garment_accuracy": False,
                "natural_movement": False,
                "lip_sync_and_dialogue": False,
                "background_stability": False,
            },
            "created_at": existing.get("created_at") if existing else datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        video_assets.append(asset_record)

    save_video_assets(brief_id, video_assets)

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_5_VIDEOS",
        action="VIDEO_PROMPTS_PREPARED",
        details=f"Prepared {len(video_assets)} video prompts for approved outfit images.",
    )

    return video_assets


def import_generated_video(
    brief_id: str,
    clip_id: str,
    video_bytes: bytes,
    file_extension: str = ".mp4",
    source_notes: str = "",
    user_name: str = "User",
) -> dict[str, Any]:
    """Import a generated video clip file, save it locally, and set status to PENDING review."""
    if not video_bytes:
        raise ValueError("Video bytes cannot be empty.")

    ext = file_extension.lower()
    if ext not in {".mp4", ".mov", ".webm", ".mkv"}:
        raise ValueError("Video clip must be an MP4, MOV, WEBM, or MKV file.")

    videos = load_video_assets(brief_id)
    target = next((v for v in videos if v.get("clip_id") == clip_id), None)
    if not target:
        raise ValueError(f"Video clip record '{clip_id}' not found in brief '{brief_id}'.")

    GENERATED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    outfit_id = target.get("outfit_id", "outfit")
    dest_filename = f"{brief_id[:8]}_{outfit_id}_{clip_id}{ext}"
    dest_path = GENERATED_VIDEOS_DIR / dest_filename

    dest_path.write_bytes(video_bytes)
    try:
        relative_path = str(dest_path.relative_to(PROJECT_DIR))
    except ValueError:
        relative_path = str(dest_path)

    old_status = target.get("approval_status", ApprovalStatus.PENDING.value)
    target["file_path"] = relative_path
    target["approval_status"] = ApprovalStatus.PENDING.value
    target["imported_at"] = datetime.now(timezone.utc).isoformat()
    target["import_notes"] = source_notes or "Imported via Google Flow manual handoff workflow."
    target["updated_at"] = datetime.now(timezone.utc).isoformat()

    save_video_assets(brief_id, videos)

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_5_VIDEOS",
        action="VIDEO_IMPORTED",
        from_status=old_status,
        to_status=ApprovalStatus.PENDING.value,
        asset_id=clip_id,
        details=f"Video clip imported for {clip_id} ({dest_filename}) by {user_name}.",
    )

    return target


def import_video_from_path(
    brief_id: str,
    clip_id: str,
    source_file_path: str,
    user_name: str = "User",
) -> dict[str, Any]:
    """Import video clip from a local file path."""
    src = Path(source_file_path).resolve()
    if not src.is_file():
        raise ValueError(f"Source video file does not exist: {source_file_path}")

    return import_generated_video(
        brief_id=brief_id,
        clip_id=clip_id,
        video_bytes=src.read_bytes(),
        file_extension=src.suffix,
        source_notes=f"Imported from {src.name}",
        user_name=user_name,
    )


def approve_video_clip(brief_id: str, clip_id: str, user_name: str = "User") -> dict:
    """Approve a reviewed video clip."""
    videos = load_video_assets(brief_id)
    target = next((v for v in videos if v.get("clip_id") == clip_id), None)
    if not target or not target.get("file_path"):
        raise ValueError("Cannot approve clip: No video file has been imported or generated yet.")

    approved = set_video_approval_status(
        brief_id=brief_id,
        clip_id=clip_id,
        new_status=ApprovalStatus.APPROVED,
        reason="Video clip playback inspected and approved.",
        user_name=user_name,
    )

    # Check if all clips for this brief are now approved
    all_videos = load_video_assets(brief_id)
    if all_videos and all(v.get("approval_status") == ApprovalStatus.APPROVED.value for v in all_videos):
        record_audit_event(
            brief_id=brief_id,
            stage="STAGE_6_READY",
            action="ALL_CLIPS_APPROVED",
            details="All video clips approved. Ready for Stage 6: Video Editing & Assembly.",
        )

    return approved


def reject_video_clip(brief_id: str, clip_id: str, reason: str, user_name: str = "User") -> dict:
    """Reject a video clip with feedback."""
    return set_video_approval_status(
        brief_id=brief_id,
        clip_id=clip_id,
        new_status=ApprovalStatus.REJECTED,
        reason=reason,
        user_name=user_name,
    )
