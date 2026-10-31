"""Outfit management service: approval actions, edits, and re-validation."""
from datetime import datetime, timezone
from typing import Any

from app.approval_workflow import (
    ApprovalStatus,
    invalidate_downstream_for_outfit,
    set_outfit_approval_status,
)
from app.storage import (
    get_brief_by_id,
    load_outfits,
    save_outfits,
    record_audit_event,
)
from app.styling.outfit_validator import validate_outfit_record


def edit_outfit(
    brief_id: str,
    outfit_id: str,
    title: str | None = None,
    garments: list[dict] | None = None,
    descriptions: str | None = None,
    colours: list[str] | None = None,
    fabrics: str | None = None,
    silhouette: str | None = None,
    footwear: str | None = None,
    accessories: str | None = None,
    occasion: str | None = None,
    user_name: str = "User",
) -> dict[str, Any]:
    """Edit outfit parameters, trigger re-validation, and invalidate downstream image/video assets."""
    outfits = load_outfits(brief_id)
    target = next((o for o in outfits if o.get("outfit_id") == outfit_id), None)
    if not target:
        raise ValueError(f"Outfit '{outfit_id}' not found in brief '{brief_id}'.")

    if title is not None:
        target["outfit_title"] = title.strip()
    if garments is not None:
        target["garments"] = garments
    if descriptions is not None:
        target["garment_descriptions"] = descriptions.strip()
    if colours is not None:
        target["colours"] = colours
    if fabrics is not None:
        target["fabrics_and_textures"] = fabrics.strip()
    if silhouette is not None:
        target["fit_and_silhouette"] = silhouette.strip()
    if footwear is not None:
        target["footwear"] = footwear.strip()
    if accessories is not None:
        target["accessories"] = accessories.strip()
    if occasion is not None:
        target["occasion"] = occasion.strip()

    # Re-validate
    brief = get_brief_by_id(brief_id) or {}
    checks, warnings, confidence = validate_outfit_record(
        target,
        all_outfits=outfits,
        audience=brief.get("audience"),
        master_model_ids=brief.get("requested_characters"),
    )
    target["validation_results"] = checks
    target["warnings"] = warnings
    target["confidence_score"] = confidence
    target["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Record revision note
    target.setdefault("revision_history", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": f"Outfit modified by {user_name}. Downstream assets invalidated.",
    })

    # Return outfit to PENDING approval if it was previously approved
    was_approved = target.get("approval_status") == ApprovalStatus.APPROVED.value
    target["approval_status"] = ApprovalStatus.PENDING.value

    save_outfits(brief_id, outfits)

    # Invalidate downstream image and video assets for this outfit!
    invalidate_downstream_for_outfit(
        brief_id=brief_id,
        outfit_id=outfit_id,
        reason=f"outfit '{outfit_id}' details were modified by user",
    )

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_3_OUTFITS",
        action="OUTFIT_EDITED",
        from_status=ApprovalStatus.APPROVED.value if was_approved else ApprovalStatus.PENDING.value,
        to_status=ApprovalStatus.PENDING.value,
        asset_id=outfit_id,
        details=f"Outfit {outfit_id} edited. Downstream image/video assets invalidated.",
    )

    return target


def approve_single_outfit(brief_id: str, outfit_id: str, user_name: str = "User") -> dict:
    """Mark an outfit as APPROVED."""
    return set_outfit_approval_status(
        brief_id=brief_id,
        outfit_id=outfit_id,
        new_status=ApprovalStatus.APPROVED,
        reason="Outfit approved by user.",
        user_name=user_name,
    )


def reject_single_outfit(brief_id: str, outfit_id: str, reason: str, user_name: str = "User") -> dict:
    """Mark an outfit as REJECTED with explicit feedback."""
    return set_outfit_approval_status(
        brief_id=brief_id,
        outfit_id=outfit_id,
        new_status=ApprovalStatus.REJECTED,
        reason=reason,
        user_name=user_name,
    )


def approve_all_outfits(brief_id: str, user_name: str = "User") -> list[dict]:
    """Approve all proposals for a brief."""
    outfits = load_outfits(brief_id)
    if not outfits:
        raise ValueError("No outfits to approve.")
    for o in outfits:
        approve_single_outfit(brief_id, o["outfit_id"], user_name=user_name)
    return load_outfits(brief_id)
