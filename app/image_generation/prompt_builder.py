"""Traceable image prompt builder enforcing character identity and garment fidelity."""
from pathlib import Path
from typing import Any

from app.model_library import ALLOWED_MODELS, load_models

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent


def get_verified_character_profile(character_id: str) -> dict[str, Any]:
    """Retrieve verified master character profile and ensure reference image exists."""
    if character_id not in ALLOWED_MODELS:
        raise ValueError(f"Unknown character ID '{character_id}'. Allowed: {list(ALLOWED_MODELS.keys())}")

    profiles = load_models()
    profile = next((p for p in profiles if p.get("model_id") == character_id), None)
    if not profile:
        raise ValueError(f"Master character profile '{character_id}' is not registered in data/master_models.json.")

    if profile.get("approval_status") != "APPROVED":
        raise ValueError(f"Master character '{character_id}' ({profile.get('display_name')}) is not APPROVED in model library.")

    ref_rel = profile.get("reference_image", "")
    ref_path = (PROJECT_DIR / ref_rel).resolve()
    if not ref_path.is_file():
        raise ValueError(
            f"Master reference image file for '{character_id}' is missing on disk at: {ref_rel}. "
            "Please upload the master reference image in Master Models tab."
        )

    return {
        "character_id": character_id,
        "display_name": profile.get("display_name", character_id),
        "identity_notes": profile.get("identity_notes", ""),
        "hair_rules": profile.get("hair_rules", ""),
        "reference_image_path": str(ref_path.relative_to(PROJECT_DIR)),
    }


def build_image_prompt_for_outfit(outfit: dict[str, Any], character_id: str) -> dict[str, Any]:
    """Construct an ultra-detailed, traceable image generation prompt."""
    char_profile = get_verified_character_profile(character_id)

    title = outfit.get("outfit_title", "Fashion Look")
    descriptions = outfit.get("garment_descriptions", "")
    colours = ", ".join(outfit.get("colours", ["Coordinated fashion tones"]))
    fabrics = outfit.get("fabrics_and_textures", "High quality fabric weave")
    silhouette = outfit.get("fit_and_silhouette", "Balanced fashion silhouette")
    footwear = outfit.get("footwear", "Coordinated fashion footwear")
    accessories = outfit.get("accessories", "Minimal tasteful accessories")
    occasion = outfit.get("occasion", "Contemporary everyday wear")

    # Assemble structured positive prompt
    prompt_text = (
        f"High-end commercial fashion editorial full-body photography. "
        f"Model: {char_profile['display_name']} ({character_id}). "
        f"Identity specifications: {char_profile['identity_notes']} "
        f"Hairstyling rules: {char_profile['hair_rules']} "
        f"Outfit Title: {title}. "
        f"Garment Ensemble: {descriptions}. "
        f"Colour Palette: {colours}. "
        f"Fabrics & Textures: {fabrics}. "
        f"Silhouette & Fit: {silhouette}. "
        f"Footwear: {footwear}. "
        f"Accessories: {accessories}. "
        f"Occasion & Setting: {occasion}. "
        f"Framing: Full-body vertical portrait framing (9:16 aspect ratio), head-to-toe complete view, clean lower hem break over footwear. "
        f"Lighting & Atmosphere: Soft natural commercial studio daylight, gentle wrap-around key light, soft diffused fill, clean neutral contemporary studio backdrop. "
        f"Quality: Hasselblad medium format camera clarity, razor-sharp fabric weave, realistic authentic human skin pores and texture, zero plastic skin smoothing, accurate finger and hand anatomy."
    )

    negative_prompt = (
        "facial asymmetry, deformed face, altering original model facial features, wrong hair color, unapproved hairstyle, "
        "doll-like skin, plastic skin, excessive skin smoothing, airbrushed, cartoon, CGI, deformed hands, extra fingers, "
        "missing fingers, mutated limbs, cropped shoes, cut off feet, distorted garments, logos, watermark, text, low resolution"
    )

    return {
        "character_id": character_id,
        "character_name": char_profile["display_name"],
        "reference_image": char_profile["reference_image_path"],
        "prompt_text": prompt_text,
        "negative_prompt": negative_prompt,
        "aspect_ratio": "9:16",
        "guidance_scale": 7.5,
        "sampler": "DPM++ 2M Karras",
        "steps": 35,
    }
