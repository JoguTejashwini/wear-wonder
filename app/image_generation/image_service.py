"""Image generation, visual inspection, and asset management service for Wear & Wonder."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import shutil

from app.approval_workflow import (
    ApprovalStatus,
    invalidate_downstream_for_outfit,
    set_image_approval_status,
)
from app.image_generation.prompt_builder import (
    build_dual_model_image_prompt,
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
    """Generate image prompts and initialize visual description baselines for all approved outfits."""
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
        provider = existing.get("provider") if existing else "CHATGPT_UPLOAD"
        prompt_version = existing.get("prompt_version", 1) if existing else 1

        # Pre-populate visual description baseline from approved outfit specifications
        visual_description = existing.get("visual_description") if existing else {
            "clothing": outfit.get("garment_descriptions", ""),
            "colours": ", ".join(outfit.get("colours", ["Coordinated fashion tones"])),
            "fit_and_silhouette": outfit.get("fit_and_silhouette", "Balanced silhouette"),
            "footwear": outfit.get("footwear", "Coordinated footwear"),
            "accessories": outfit.get("accessories", "Minimal accessories"),
            "hairstyle": char_profile.get("hair_rules", ""),
            "pose": "Poised standing fashion portrait, shoulders slightly turned to camera",
            "background": outfit.get("occasion", "Contemporary clean studio backdrop with soft commercial daylight"),
            "styling_notes": "Generated in ChatGPT using approved master character reference.",
        }

        asset_record: dict[str, Any] = {
            "image_id": image_id,
            "brief_id": brief_id,
            "outfit_id": outfit_id,
            "character_id": char_id,
            "character_name": char_profile["display_name"],
            "reference_image": char_profile["reference_image_path"],
            "prompt_data": prompt_data,
            "prompt_version": prompt_version,
            "visual_description": visual_description,
            "file_path": file_path,
            "provider": provider,
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
        details=f"Prepared {len(image_assets)} image prompts and visual baselines for approved outfits.",
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
    """Import and associate an actual generated image file for an outfit, save it locally, and invalidate downstream video assets."""
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
    
    # If an image was previously attached, increment the prompt/asset version
    if target.get("file_path"):
        target["prompt_version"] = target.get("prompt_version", 1) + 1

    # If this outfit had previously approved assets or downstream video prompts, invalidate them
    invalidate_downstream_for_outfit(brief_id, outfit_id, reason="New outfit image uploaded in Stage 4")

    target["file_path"] = relative_path
    target["provider"] = "CHATGPT_UPLOAD"
    target["approval_status"] = ApprovalStatus.PENDING.value
    target["uploaded_at"] = datetime.now(timezone.utc).isoformat()
    target["import_notes"] = source_notes or "Uploaded actual ChatGPT-generated outfit image."
    target["updated_at"] = datetime.now(timezone.utc).isoformat()

    save_image_assets(brief_id, images)

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_4_IMAGES",
        action="IMAGE_UPLOADED",
        from_status=old_status,
        to_status=ApprovalStatus.PENDING.value,
        asset_id=image_id,
        details=f"Actual generated image uploaded for {image_id} ({dest_filename}) by {user_name}. Downstream video prompts invalidated.",
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


def update_image_visual_description(
    brief_id: str,
    image_id: str,
    visual_description: dict[str, Any],
    user_name: str = "User",
) -> dict[str, Any]:
    """Update user-reviewed visual description for an image asset."""
    images = load_image_assets(brief_id)
    target = next((img for img in images if img.get("image_id") == image_id), None)
    if not target:
        raise ValueError(f"Image asset '{image_id}' not found in brief '{brief_id}'.")

    if "visual_description" not in target or not isinstance(target["visual_description"], dict):
        target["visual_description"] = {}

    target["visual_description"].update(visual_description)
    target["updated_at"] = datetime.now(timezone.utc).isoformat()

    save_image_assets(brief_id, images)

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_4_IMAGES",
        action="VISUAL_DESCRIPTION_UPDATED",
        asset_id=image_id,
        details=f"Visual description updated and aligned by {user_name} for {image_id}.",
    )
    return target


def approve_image(
    brief_id: str,
    image_id: str,
    visual_description: dict[str, Any] | None = None,
    user_name: str = "User",
) -> dict[str, Any]:
    """Approve a reviewed image. Strictly requires an actual uploaded image file verified on disk."""
    images = load_image_assets(brief_id)
    target = next((img for img in images if img.get("image_id") == image_id), None)
    if not target:
        raise ValueError(f"Image asset '{image_id}' not found in brief '{brief_id}'.")

    # Strict check: Image MUST be uploaded and verified on disk
    file_rel = target.get("file_path")
    if not file_rel:
        raise ValueError(f"Cannot approve {image_id}: Upload the actual generated image file first.")

    full_path = (PROJECT_DIR / file_rel).resolve()
    if not full_path.is_file():
        raise ValueError(f"Cannot approve {image_id}: Image file not found on disk at '{file_rel}'. Please re-upload.")

    if visual_description:
        if "visual_description" not in target or not isinstance(target["visual_description"], dict):
            target["visual_description"] = {}
        target["visual_description"].update(visual_description)

    target["approved_at"] = datetime.now(timezone.utc).isoformat()
    target["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_image_assets(brief_id, images)

    return set_image_approval_status(
        brief_id=brief_id,
        image_id=image_id,
        new_status=ApprovalStatus.APPROVED,
        reason="Visual inspection and garment details reviewed and approved by user.",
        user_name=user_name,
    )


def reject_image(brief_id: str, image_id: str, reason: str, user_name: str = "User") -> dict:
    """Reject an image with feedback and invalidate downstream assets."""
    return set_image_approval_status(
        brief_id=brief_id,
        image_id=image_id,
        new_status=ApprovalStatus.REJECTED,
        reason=reason,
        user_name=user_name,
    )


def configure_dual_model_image_look(
    brief_id: str,
    image_id: str,
    character_id_1: str,
    character_id_2: str,
    outfit_id_1: str,
    outfit_id_2: str | None = None,
    user_name: str = "User",
) -> dict[str, Any]:
    """Configure an image look as a dual-model look in a stylish wardrobe/dressing-room setting."""
    images = load_image_assets(brief_id)
    target = next((img for img in images if img.get("image_id") == image_id), None)
    if not target:
        raise ValueError(f"Image asset '{image_id}' not found in brief '{brief_id}'.")

    outfits = load_outfits(brief_id)
    outfit_1 = next((o for o in outfits if o.get("outfit_id") == outfit_id_1), None)
    if not outfit_1:
        raise ValueError(f"Outfit '{outfit_id_1}' not found in brief '{brief_id}'.")

    outfit_2 = next((o for o in outfits if o.get("outfit_id") == outfit_id_2), None) if outfit_id_2 else outfit_1

    dual_prompt_data = build_dual_model_image_prompt(
        outfit_1=outfit_1,
        character_id_1=character_id_1,
        character_id_2=character_id_2,
        outfit_2=outfit_2,
    )

    old_status = target.get("approval_status", ApprovalStatus.PENDING.value)

    # Invalidate downstream video if any
    invalidate_downstream_for_outfit(brief_id, outfit_id_1, reason="Configured dual-model wardrobe look")

    target["is_dual_model"] = True
    target["character_id"] = character_id_1
    target["dual_character_id"] = character_id_2
    target["character_name"] = dual_prompt_data["character_name"]
    target["reference_image"] = dual_prompt_data["reference_image"]
    target["reference_image_2"] = dual_prompt_data["reference_image_2"]
    target["prompt_data"] = dual_prompt_data
    target["approval_status"] = ApprovalStatus.PENDING.value
    target["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Pre-populate dual-model visual description
    target["visual_description"] = {
        "clothing_model_1": f"{outfit_1.get('garment_descriptions', '')} ({', '.join(outfit_1.get('colours', []))})",
        "clothing_model_2": f"{outfit_2.get('garment_descriptions', '')} ({', '.join(outfit_2.get('colours', []))})",
        "clothing": f"Model 1: {outfit_1.get('garment_descriptions', '')}; Model 2: {outfit_2.get('garment_descriptions', '')}",
        "colours": f"Model 1: {', '.join(outfit_1.get('colours', []))}; Model 2: {', '.join(outfit_2.get('colours', []))}",
        "fit": f"Model 1: {outfit_1.get('fit_and_silhouette', '')}; Model 2: {outfit_2.get('fit_and_silhouette', '')}",
        "footwear": f"Model 1: {outfit_1.get('footwear', '')}; Model 2: {outfit_2.get('footwear', '')}",
        "accessories": f"Model 1: {outfit_1.get('accessories', '')}; Model 2: {outfit_2.get('accessories', '')}",
        "hairstyle": f"Model 1: {character_id_1}; Model 2: {character_id_2}",
        "pose": "Model 1 on left/center posing confidently; Model 2 on right/center smiling warmly",
        "background": "Stylish boutique walk-in wardrobe and dressing room with backlit vanity mirror and curated garment racks",
        "positions": f"Left frame: Model 1 ({character_id_1}); Right frame: Model 2 ({character_id_2})",
        "expressions": "Model 1 confident and speaking; Model 2 smiling silently with natural reactions",
    }

    save_image_assets(brief_id, images)

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_4_IMAGES",
        action="DUAL_MODEL_CONFIGURED",
        from_status=old_status,
        to_status=ApprovalStatus.PENDING.value,
        asset_id=image_id,
        details=f"Configured two-model wardrobe look with {character_id_1} and {character_id_2} by {user_name}.",
    )

    return target
