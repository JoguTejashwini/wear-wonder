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


def build_dual_model_image_prompt(
    outfit_1: dict[str, Any],
    character_id_1: str,
    character_id_2: str,
    outfit_2: dict[str, Any] | None = None,
    background_setting: str = "stylish luxury walk-in wardrobe and dressing room",
) -> dict[str, Any]:
    """Construct an explicit two-model image generation prompt in a stylish wardrobe/dressing-room background."""
    char1 = get_verified_character_profile(character_id_1)
    char2 = get_verified_character_profile(character_id_2)

    o1 = outfit_1
    o2 = outfit_2 or outfit_1

    title_1 = o1.get("outfit_title", "Model 1 Look")
    desc_1 = o1.get("garment_descriptions", "")
    colours_1 = ", ".join(o1.get("colours", ["Coordinated fashion tones"]))
    fabrics_1 = o1.get("fabrics_and_textures", "Refined fashion fabrics")
    fit_1 = o1.get("fit_and_silhouette", "Balanced silhouette")
    footwear_1 = o1.get("footwear", "Fashion footwear")
    acc_1 = o1.get("accessories", "Minimal accessories")

    title_2 = o2.get("outfit_title", "Model 2 Complementary Look")
    desc_2 = o2.get("garment_descriptions", "")
    colours_2 = ", ".join(o2.get("colours", ["Coordinated fashion tones"]))
    fabrics_2 = o2.get("fabrics_and_textures", "Refined fashion fabrics")
    fit_2 = o2.get("fit_and_silhouette", "Balanced silhouette")
    footwear_2 = o2.get("footwear", "Fashion footwear")
    acc_2 = o2.get("accessories", "Minimal accessories")

    wardrobe_bg = (
        "High-end luxury boutique walk-in wardrobe and dressing room. "
        "Background features backlit floor-to-ceiling vanity mirror, warm recessed ceiling lights, "
        "sleek minimalist brass and matte black clothing racks with neatly hung neutral garments, "
        "soft ambient lighting, and polished hardwood parquet or marble flooring."
    )

    prompt_text = (
        f"High-end commercial fashion editorial full-body photography featuring two models together in a {background_setting}. "
        f"Model 1 (Left): {char1['display_name']} ({character_id_1}). "
        f"Identity specifications for Model 1: {char1['identity_notes']} Hairstyling rules: {char1['hair_rules']}. "
        f"Model 1 Outfit ({title_1}): {desc_1}. Colour Palette: {colours_1}. Fabrics: {fabrics_1}. Fit: {fit_1}. Footwear: {footwear_1}. Accessories: {acc_1}. "
        f"Model 2 (Right): {char2['display_name']} ({character_id_2}). "
        f"Identity specifications for Model 2: {char2['identity_notes']} Hairstyling rules: {char2['hair_rules']}. "
        f"Model 2 Outfit ({title_2}): {desc_2}. Colour Palette: {colours_2}. Fabrics: {fabrics_2}. Fit: {fit_2}. Footwear: {footwear_2}. Accessories: {acc_2}. "
        f"Positions & Staging: Both models stand side by side in full-length vertical framing. Model 1 is positioned on the left/center in a confident, poised standing posture. Model 2 is positioned on the right/center with a natural, complementary posture. "
        f"Facial Expressions: Model 1 has a warm, confident expression looking directly at camera. Model 2 has a pleasant, engaging smile looking naturally toward Model 1 / camera. "
        f"Setting & Background: {wardrobe_bg} "
        f"Framing: Vertical 9:16 full-body portrait, head-to-toe complete view, all footwear fully visible. "
        f"Lighting & Atmosphere: Soft warm boutique dressing-room lighting, gentle wrap-around key light, soft diffused fill, clean upscale aesthetic. "
        f"Quality: Hasselblad medium format camera clarity, razor-sharp fabric weave, realistic authentic human skin pores and texture, zero plastic skin smoothing, accurate finger and hand anatomy."
    )

    negative_prompt = (
        "facial asymmetry, deformed face, blending or merging model faces, swapping identities, altered hair color, "
        "unapproved hairstyle, doll-like skin, plastic skin, airbrushed, cartoon, CGI, deformed hands, extra fingers, "
        "missing fingers, mutated limbs, cropped shoes, cut off feet, distorted garments, logos, watermark, text, low resolution"
    )

    chatgpt_prompt = (
        f"Please reference the TWO attached master model reference images: \n"
        f"1. Model 1 (Left): {char1['display_name']} ({character_id_1}) — attach her reference photo.\n"
        f"2. Model 2 (Right): {char2['display_name']} ({character_id_2}) — attach her reference photo.\n\n"
        f"Strictly maintain both models' distinct facial structures, eye shapes, noses, lips, jawlines, skin tones, "
        f"facial proportions, and individual hair styling rules without blending, morphing, or swapping their identities:\n"
        f"- Model 1 Hair Rules: {char1['hair_rules']}\n"
        f"- Model 2 Hair Rules: {char2['hair_rules']}\n\n"
        f"Generate ONE full-body vertical fashion editorial photograph (9:16 aspect ratio) containing BOTH models together in a stylish wardrobe/dressing-room background:\n"
        f"- Model 1 ({character_id_1}, Left/Center): Wearing {title_1} — {desc_1} in {colours_1}. Silhouette: {fit_1}. Shoes: {footwear_1}. Accessories: {acc_1}. Expression: confident, warm, looking at camera.\n"
        f"- Model 2 ({character_id_2}, Right/Center): Wearing {title_2} — {desc_2} in {colours_2}. Silhouette: {fit_2}. Shoes: {footwear_2}. Accessories: {acc_2}. Expression: relaxed, friendly smile, interacting naturally.\n"
        f"- Setting & Background: {wardrobe_bg}\n"
        f"- Framing: Full-length vertical portrait (9:16) showing both models from head to toe with complete footwear visible.\n"
        f"- Quality: Realistic skin textures, natural hand anatomy, sharp garment drape, upscale commercial fashion magazine aesthetic."
    )

    return {
        "character_id": character_id_1,
        "dual_character_id": character_id_2,
        "is_dual_model": True,
        "character_name": f"{char1['display_name']} & {char2['display_name']}",
        "reference_image": char1["reference_image_path"],
        "reference_image_2": char2["reference_image_path"],
        "prompt_text": prompt_text,
        "chatgpt_prompt": chatgpt_prompt,
        "negative_prompt": negative_prompt,
        "background_setting": wardrobe_bg,
        "aspect_ratio": "9:16",
        "guidance_scale": 7.5,
        "sampler": "DPM++ 2M Karras",
        "steps": 35,
    }


def build_image_prompt_for_outfit(
    outfit: dict[str, Any],
    character_id: str,
    secondary_character_id: str | None = None,
    secondary_outfit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct an ultra-detailed, traceable image generation prompt."""
    if secondary_character_id and secondary_character_id != character_id:
        return build_dual_model_image_prompt(
            outfit_1=outfit,
            character_id_1=character_id,
            character_id_2=secondary_character_id,
            outfit_2=secondary_outfit,
        )

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

    # Tailored multi-modal prompt specifically formatted for ChatGPT web with reference image attachment
    chatgpt_prompt = (
        f"Please reference the attached master model reference image for {char_profile['display_name']} ({character_id}). "
        f"Strictly maintain her exact facial structure, facial features, eye shape, nose, lips, jawline, skin tone, "
        f"facial proportions, hairline, and hair styling rules: {char_profile['hair_rules']}. "
        f"Do not redesign or alter her facial identity. "
        f"Generate a full-body vertical fashion editorial photograph (9:16 aspect ratio) of her wearing this look: "
        f"Outfit Title: {title}. "
        f"Garments: {descriptions}. "
        f"Colour Palette: {colours}. "
        f"Fabrics & Textures: {fabrics}. "
        f"Silhouette: {silhouette}. "
        f"Footwear: {footwear}. "
        f"Accessories: {accessories}. "
        f"Setting & Atmosphere: {occasion}, clean neutral contemporary studio backdrop with soft diffused commercial daylight. "
        f"Framing: Full-length vertical portrait showing head to toe with complete footwear visible. "
        f"Photographic quality: authentic skin texture, realistic hands, razor-sharp garment drape."
    )

    return {
        "character_id": character_id,
        "character_name": char_profile["display_name"],
        "reference_image": char_profile["reference_image_path"],
        "prompt_text": prompt_text,
        "chatgpt_prompt": chatgpt_prompt,
        "negative_prompt": negative_prompt,
        "aspect_ratio": "9:16",
        "guidance_scale": 7.5,
        "sampler": "DPM++ 2M Karras",
        "steps": 35,
    }
