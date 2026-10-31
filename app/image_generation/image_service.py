"""Image generation and manual handoff service for Wear & Wonder."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import shutil

from app.approval_workflow import (
    ApprovalStatus,
    set_image_approval_status,
)
from app.image_generation.prompt_builder import (
    build_image_prompt_for_outfit,
    get_verified_character_profile,
)
from app.storage import (
    get_brief_by_id,
    load_image_assets,
    load_outfits,
    save_image_assets,
    record_audit_event,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
GENERATED_IMAGES_DIR = PROJECT_DIR / "assets" / "generated_images"


def prepare_image_prompts(brief_id: str) -> list[dict[str, Any]]:
    """Generate image prompts for all approved outfits in a brief."""
    brief = get_brief_by_id(brief_id)
    if not brief:
        raise ValueError(f"Brief '{brief_id}' not found.")

    outfits = load_outfits(brief_id)
    if not outfits:
        raise ValueError(f"No outfits found for brief '{brief_id}'. Generate outfits in Stage 3 first.")

    approved_outfits = [o for o in outfits if o.get("approval_status") == ApprovalStatus.APPROVED.value]
    if not approved_outfits:
        raise ValueError(
            "Cannot prepare image prompts: No approved outfits found. "
            "Please review and approve outfit proposals in Stage 3 first."
        )

    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    existing_assets = {img["outfit_id"]: img for img in load_image_assets(brief_id)}
    image_assets: list[dict[str, Any]] = []

    for index, outfit in enumerate(approved_outfits):
        outfit_id = outfit["outfit_id"]
        char_id = outfit.get("assigned_character_id") or "WW-CHAR-01"

        # Verify character reference image and profile
        char_profile = get_verified_character_profile(char_id)
        prompt_data = build_image_prompt_for_outfit(outfit, char_id)

        existing = existing_assets.get(outfit_id)
        image_id = existing.get("image_id") if existing else f"IMG-{index + 1:02d}"

        # Preserve existing imported image file path if present and unchanged
        file_path = existing.get("file_path") if existing else None
        approval_status = existing.get("approval_status") if existing else ApprovalStatus.PENDING.value

        asset_record: dict[str, Any] = {
            "image_id": image_id,
            "brief_id": brief_id,
            "outfit_id": outfit_id,
            "character_id": char_id,
            "character_name": char_profile["display_name"],
            "reference_image": char_profile["reference_image_path"],
            "prompt_data": prompt_data,
            "file_path": file_path,
            "provider": "MANUAL_HANDOFF_OR_LOCAL",
            "approval_status": approval_status,
            "quality_checklist": existing.get("quality_checklist") if existing else {
                "identity_consistency": False,
                "garment_accuracy": False,
                "anatomy_and_hands": False,
                "sharpness_and_lighting": False,
            },
            "created_at": existing.get("created_at") if existing else datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        image_assets.append(asset_record)

    save_image_assets(brief_id, image_assets)

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_4_IMAGES",
        action="PROMPTS_PREPARED",
        details=f"Prepared {len(image_assets)} image prompts for approved outfits.",
    )

    return image_assets


def import_generated_image(
    brief_id: str,
    image_id: str,
    image_bytes: bytes,
    file_extension: str = ".png",
    source_notes: str = "",
    user_name: str = "User",
) -> dict[str, Any]:
    """Import an image file for an image asset, save it locally, and set status to PENDING review."""
    if not image_bytes:
        raise ValueError("Image bytes cannot be empty.")

    ext = file_extension.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Image must be a PNG, JPG, JPEG, or WEBP file.")

    images = load_image_assets(brief_id)
    target = next((img for img in images if img.get("image_id") == image_id), None)
    if not target:
        raise ValueError(f"Image asset '{image_id}' not found in brief '{brief_id}'.")

    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    outfit_id = target.get("outfit_id", "outfit")
    char_id = target.get("character_id", "char")
    dest_filename = f"{brief_id[:8]}_{outfit_id}_{char_id}{ext}"
    dest_path = GENERATED_IMAGES_DIR / dest_filename

    dest_path.write_bytes(image_bytes)
    try:
        relative_path = str(dest_path.relative_to(PROJECT_DIR))
    except ValueError:
        relative_path = str(dest_path)

    old_status = target.get("approval_status", ApprovalStatus.PENDING.value)
    target["file_path"] = relative_path
    target["approval_status"] = ApprovalStatus.PENDING.value
    target["imported_at"] = datetime.now(timezone.utc).isoformat()
    target["import_notes"] = source_notes or "Imported via manual handoff workflow."
    target["updated_at"] = datetime.now(timezone.utc).isoformat()

    save_image_assets(brief_id, images)

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_4_IMAGES",
        action="IMAGE_IMPORTED",
        from_status=old_status,
        to_status=ApprovalStatus.PENDING.value,
        asset_id=image_id,
        details=f"Image imported for {image_id} ({dest_filename}) by {user_name}.",
    )

    return target


def import_image_from_path(
    brief_id: str,
    image_id: str,
    source_file_path: str,
    user_name: str = "User",
) -> dict[str, Any]:
    """Import image from a local file path."""
    src = Path(source_file_path).resolve()
    if not src.is_file():
        raise ValueError(f"Source image file does not exist: {source_file_path}")

    return import_generated_image(
        brief_id=brief_id,
        image_id=image_id,
        image_bytes=src.read_bytes(),
        file_extension=src.suffix,
        source_notes=f"Imported from {src.name}",
        user_name=user_name,
    )


def approve_image(brief_id: str, image_id: str, user_name: str = "User") -> dict:
    """Approve a reviewed image."""
    images = load_image_assets(brief_id)
    target = next((img for img in images if img.get("image_id") == image_id), None)
    if not target or not target.get("file_path"):
        raise ValueError("Cannot approve image: No image file has been imported or generated yet.")

    return set_image_approval_status(
        brief_id=brief_id,
        image_id=image_id,
        new_status=ApprovalStatus.APPROVED,
        reason="Image visually inspected and approved.",
        user_name=user_name,
    )


def reject_image(brief_id: str, image_id: str, reason: str, user_name: str = "User") -> dict:
    """Reject an image with feedback."""
    return set_image_approval_status(
        brief_id=brief_id,
        image_id=image_id,
        new_status=ApprovalStatus.REJECTED,
        reason=reason,
        user_name=user_name,
    )
