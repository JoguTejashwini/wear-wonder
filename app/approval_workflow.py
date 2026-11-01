"""Global workflow gatekeeper and status invalidation manager for Wear & Wonder."""
from enum import Enum
from pathlib import Path
from typing import Any
from app.storage import (
    get_brief_by_id,
    load_outfits,
    load_image_assets,
    load_video_assets,
    load_publishing_record,
    save_or_update_brief,
    save_outfits,
    save_image_assets,
    save_video_assets,
    record_audit_event,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent


class WorkflowStage(str, Enum):
    STAGE_1_IDEA = "STAGE_1_IDEA"
    STAGE_2_RESEARCH = "STAGE_2_RESEARCH"
    STAGE_3_OUTFITS = "STAGE_3_OUTFITS"
    STAGE_4_IMAGES = "STAGE_4_IMAGES"
    STAGE_5_VIDEOS = "STAGE_5_VIDEOS"
    STAGE_6_READY = "STAGE_6_READY"
    STAGE_6_PUBLISHING = "STAGE_6_PUBLISHING"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"


def get_workflow_prerequisites(brief_id: str) -> dict[str, bool]:
    """Inspect current brief and assets to verify completion of each stage's prerequisite gates."""
    brief = get_brief_by_id(brief_id)
    if not brief:
        return {
            "has_brief": False,
            "research_completed": False,
            "research_approved": False,
            "has_outfits": False,
            "outfits_approved": False,
            "images_generated": False,
            "images_approved": False,
            "videos_generated": False,
            "videos_approved": False,
            "stage_6_ready": False,
            "has_assembled_video": False,
            "is_published_or_scheduled": False,
        }

    research_status = brief.get("research_status", "PENDING")
    research_completed = research_status in ("COMPLETED", "APPROVED")
    research_approved = research_status == "APPROVED"

    outfits = load_outfits(brief_id)
    has_outfits = len(outfits) > 0
    # Outfits are approved if all outfits are approved, and at least 1 exists
    outfits_approved = has_outfits and all(
        o.get("approval_status") == ApprovalStatus.APPROVED.value for o in outfits
    )

    images = load_image_assets(brief_id)
    has_images = len(images) > 0
    # Every approved outfit must have a corresponding approved image with verified file on disk
    approved_outfit_ids = {o["outfit_id"] for o in outfits if o.get("approval_status") == ApprovalStatus.APPROVED.value}
    images_by_outfit = {img.get("outfit_id"): img for img in images}
    images_approved = (
        bool(approved_outfit_ids)
        and all(
            images_by_outfit.get(oid) is not None
            and images_by_outfit[oid].get("approval_status") == ApprovalStatus.APPROVED.value
            and bool(images_by_outfit[oid].get("file_path"))
            and (PROJECT_DIR / images_by_outfit[oid]["file_path"]).is_file()
            for oid in approved_outfit_ids
        )
    )

    videos = load_video_assets(brief_id)
    videos_by_outfit = {v.get("outfit_id"): v for v in videos}
    videos_approved = (
        bool(approved_outfit_ids)
        and all(
            videos_by_outfit.get(oid) is not None
            and videos_by_outfit[oid].get("approval_status") == ApprovalStatus.APPROVED.value
            for oid in approved_outfit_ids
        )
    )

    stage_6_ready = (
        research_approved
        and outfits_approved
        and images_approved
        and videos_approved
    )

    pub_rec = load_publishing_record(brief_id)
    has_assembled_video = bool(pub_rec and pub_rec.get("video_file_path") and (PROJECT_DIR / pub_rec["video_file_path"]).is_file())
    is_published_or_scheduled = bool(pub_rec and pub_rec.get("status") in ("SCHEDULED", "PUBLISHED"))

    return {
        "has_brief": True,
        "research_completed": research_completed,
        "research_approved": research_approved,
        "has_outfits": has_outfits,
        "outfits_approved": outfits_approved,
        "images_generated": has_images,
        "images_approved": images_approved,
        "videos_generated": len(videos) > 0,
        "videos_approved": videos_approved,
        "stage_6_ready": stage_6_ready,
        "has_assembled_video": has_assembled_video,
        "is_published_or_scheduled": is_published_or_scheduled,
    }


def can_proceed_to_stage(brief_id: str, stage: WorkflowStage) -> tuple[bool, str]:
    """Check if the brief meets mandatory approval gates to access a stage."""
    prereqs = get_workflow_prerequisites(brief_id)

    if not prereqs["has_brief"]:
        return False, "No active brief selected. Please create or load an idea in Idea Studio first."

    if stage == WorkflowStage.STAGE_2_RESEARCH:
        return True, "Ready for research."

    if stage == WorkflowStage.STAGE_3_OUTFITS:
        if not prereqs["research_approved"]:
            return False, "Research must be reviewed and marked as APPROVED before generating outfit proposals."
        return True, "Ready for outfit proposals."

    if stage == WorkflowStage.STAGE_4_IMAGES:
        if not prereqs["outfits_approved"]:
            return False, "All outfit proposals must be approved before generating image prompts and assets."
        return True, "Ready for image studio."

    if stage == WorkflowStage.STAGE_5_VIDEOS:
        if not prereqs["images_approved"]:
            return False, "All outfit images must be approved before generating video prompts and clips."
        return True, "Ready for video studio."

    if stage in (WorkflowStage.STAGE_6_READY, WorkflowStage.STAGE_6_PUBLISHING):
        if not prereqs["stage_6_ready"]:
            return False, "All clips, images, and outfits must be approved before video editing assembly."
        return True, "All assets approved. Ready for Stage 6 Publishing & Scheduling."

    return True, "Permitted."


def approve_research(brief_id: str, user_name: str = "User") -> dict:
    """Explicitly approve research findings for a brief."""
    brief = get_brief_by_id(brief_id)
    if not brief:
        raise ValueError("Brief not found.")

    old_status = brief.get("research_status", "PENDING")
    brief["research_status"] = ApprovalStatus.APPROVED.value
    save_or_update_brief(brief)

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_2_RESEARCH.value,
        action="APPROVE_RESEARCH",
        from_status=old_status,
        to_status=ApprovalStatus.APPROVED.value,
        details=f"Research reviewed and approved by {user_name}.",
    )
    return brief


def set_outfit_approval_status(
    brief_id: str,
    outfit_id: str,
    new_status: ApprovalStatus,
    reason: str = "",
    user_name: str = "User",
) -> dict:
    """Set approval status for a single outfit proposal with downstream cascade checks."""
    outfits = load_outfits(brief_id)
    target = None
    for o in outfits:
        if o.get("outfit_id") == outfit_id:
            target = o
            break

    if not target:
        raise ValueError(f"Outfit '{outfit_id}' not found.")

    old_status = target.get("approval_status", ApprovalStatus.PENDING.value)
    target["approval_status"] = new_status.value
    if reason:
        target.setdefault("status_notes", []).append({
            "status": new_status.value,
            "reason": reason,
            "by": user_name,
        })
    save_outfits(brief_id, outfits)

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_3_OUTFITS.value,
        action=f"OUTFIT_{new_status.value}",
        from_status=old_status,
        to_status=new_status.value,
        asset_id=outfit_id,
        details=f"Outfit {outfit_id} set to {new_status.value}. Reason: {reason or 'Direct user decision'}",
    )

    # Invalidate downstream image and video approvals for this specific outfit if rejected or returned to pending
    if new_status in (ApprovalStatus.REJECTED, ApprovalStatus.PENDING, ApprovalStatus.REVISION_REQUESTED):
        invalidate_downstream_for_outfit(brief_id, outfit_id, reason=f"Outfit status changed to {new_status.value}")

    # Synchronize overall brief outfit_approval flag
    all_approved = all(o.get("approval_status") == ApprovalStatus.APPROVED.value for o in outfits)
    brief = get_brief_by_id(brief_id)
    if brief:
        brief["outfit_approval"] = ApprovalStatus.APPROVED.value if all_approved else ApprovalStatus.PENDING.value
        save_or_update_brief(brief)

    return target


def invalidate_downstream_for_outfit(brief_id: str, outfit_id: str, reason: str) -> None:
    """Cascade invalidation: Reset downstream image and video approvals for an outfit when modified or rejected."""
    # 1. Reset image asset
    images = load_image_assets(brief_id)
    img_changed = False
    for img in images:
        if img.get("outfit_id") == outfit_id:
            if img.get("approval_status") != ApprovalStatus.PENDING.value:
                old = img.get("approval_status")
                img["approval_status"] = ApprovalStatus.PENDING.value
                img_changed = True
                record_audit_event(
                    brief_id=brief_id,
                    stage=WorkflowStage.STAGE_4_IMAGES.value,
                    action="IMAGE_INVALIDATED",
                    from_status=old,
                    to_status=ApprovalStatus.PENDING.value,
                    asset_id=img.get("image_id"),
                    details=f"Downstream image invalidated because {reason}.",
                )
    if img_changed:
        save_image_assets(brief_id, images)

    # 2. Reset video asset
    videos = load_video_assets(brief_id)
    vid_changed = False
    for vid in videos:
        if vid.get("outfit_id") == outfit_id:
            vid["is_outdated"] = True
            if vid.get("approval_status") != ApprovalStatus.PENDING.value:
                old = vid.get("approval_status")
                vid["approval_status"] = ApprovalStatus.PENDING.value
                vid_changed = True
                record_audit_event(
                    brief_id=brief_id,
                    stage=WorkflowStage.STAGE_5_VIDEOS.value,
                    action="VIDEO_INVALIDATED",
                    from_status=old,
                    to_status=ApprovalStatus.PENDING.value,
                    asset_id=vid.get("clip_id"),
                    details=f"Downstream video clip invalidated because {reason}.",
                )
            else:
                vid_changed = True
    if vid_changed:
        save_video_assets(brief_id, videos)


def set_image_approval_status(
    brief_id: str,
    image_id: str,
    new_status: ApprovalStatus,
    reason: str = "",
    user_name: str = "User",
) -> dict:
    """Set approval status for an image asset."""
    images = load_image_assets(brief_id)
    target = None
    for img in images:
        if img.get("image_id") == image_id:
            target = img
            break
    if not target:
        raise ValueError(f"Image asset '{image_id}' not found.")

    old_status = target.get("approval_status", ApprovalStatus.PENDING.value)
    target["approval_status"] = new_status.value
    save_image_assets(brief_id, images)

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_4_IMAGES.value,
        action=f"IMAGE_{new_status.value}",
        from_status=old_status,
        to_status=new_status.value,
        asset_id=image_id,
        details=f"Image {image_id} set to {new_status.value}. Reason: {reason or 'User review'}",
    )

    # If image rejected or reset to pending, invalidate downstream video clip
    if new_status in (ApprovalStatus.REJECTED, ApprovalStatus.PENDING):
        outfit_id = target.get("outfit_id")
        videos = load_video_assets(brief_id)
        vid_changed = False
        for vid in videos:
            if vid.get("outfit_id") == outfit_id and vid.get("approval_status") != ApprovalStatus.PENDING.value:
                old = vid.get("approval_status")
                vid["approval_status"] = ApprovalStatus.PENDING.value
                vid_changed = True
                record_audit_event(
                    brief_id=brief_id,
                    stage=WorkflowStage.STAGE_5_VIDEOS.value,
                    action="VIDEO_INVALIDATED",
                    from_status=old,
                    to_status=ApprovalStatus.PENDING.value,
                    asset_id=vid.get("clip_id"),
                    details=f"Video clip invalidated because image {image_id} was {new_status.value}.",
                )
        if vid_changed:
            save_video_assets(brief_id, videos)

    return target


def set_video_approval_status(
    brief_id: str,
    clip_id: str,
    new_status: ApprovalStatus,
    reason: str = "",
    user_name: str = "User",
) -> dict:
    """Set approval status for a single video clip."""
    videos = load_video_assets(brief_id)
    target = None
    for vid in videos:
        if vid.get("clip_id") == clip_id:
            target = vid
            break
    if not target:
        raise ValueError(f"Video clip '{clip_id}' not found.")

    old_status = target.get("approval_status", ApprovalStatus.PENDING.value)
    target["approval_status"] = new_status.value
    save_video_assets(brief_id, videos)

    record_audit_event(
        brief_id=brief_id,
        stage=WorkflowStage.STAGE_5_VIDEOS.value,
        action=f"VIDEO_{new_status.value}",
        from_status=old_status,
        to_status=new_status.value,
        asset_id=clip_id,
        details=f"Video clip {clip_id} set to {new_status.value}. Reason: {reason or 'User review'}",
    )
    return target
