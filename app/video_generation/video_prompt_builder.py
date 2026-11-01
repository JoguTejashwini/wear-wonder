"""Video prompt generator for fashion clips, motion continuity, and Google Flow handoff."""
from pathlib import Path
from typing import Any

from app.image_generation.prompt_builder import get_verified_character_profile


def build_video_prompt_for_outfit(
    outfit: dict[str, Any],
    image_asset: dict[str, Any],
    clip_index: int = 1,
    dual_character_id: str | None = None,
) -> dict[str, Any]:
    """Construct an explicit video generation prompt aligned with the approved image visual description."""
    primary_char_id = image_asset.get("character_id") or outfit.get("assigned_character_id") or "WW-CHAR-01"
    primary_char = get_verified_character_profile(primary_char_id)

    # Use the approved image's reviewed visual description as the ground truth
    visual_desc = image_asset.get("visual_description") or {}
    title = outfit.get("outfit_title", f"Look {clip_index}")
    garment_desc = visual_desc.get("clothing") or outfit.get("garment_descriptions", "")
    colours = visual_desc.get("colours") or ", ".join(outfit.get("colours", ["curated fashion tones"]))
    fit_silhouette = visual_desc.get("fit_and_silhouette") or outfit.get("fit_and_silhouette", "Balanced silhouette")
    footwear = visual_desc.get("footwear") or outfit.get("footwear", "Coordinated footwear")
    accessories = visual_desc.get("accessories") or outfit.get("accessories", "Minimal accessories")
    hairstyle = visual_desc.get("hairstyle") or primary_char.get("hair_rules", "")
    background_desc = visual_desc.get("background") or "Contemporary warm architectural studio space with soft diffuse shadows, matching approved master image."

    # Identify approved starting frame filename
    file_path_str = image_asset.get("file_path", "")
    start_frame_name = Path(file_path_str).name if file_path_str else image_asset.get("image_id", "APPROVED_IMAGE")

    # Generate dialogue tailored to this specific outfit
    first_item = outfit.get("garments", [{}])[0].get("item", "essential piece") if outfit.get("garments") else "essential look"
    first_col = outfit.get("colours", ["curated"])[0].lower() if outfit.get("colours") else "curated"
    dialogue_script = (
        f"Look {clip_index}: Pairing our {first_col} {first_item} "
        f"with {footwear.lower()} for effortless everyday style."
    )

    is_dual = bool(dual_character_id and dual_character_id != primary_char_id) or bool(image_asset.get("is_dual_model"))
    if is_dual:
        sec_char_id = dual_character_id or image_asset.get("dual_character_id") or "WW-CHAR-02"
        secondary_char = get_verified_character_profile(sec_char_id)

        wardrobe_bg = "Stylish boutique walk-in wardrobe and dressing room with backlit vanity mirror, curated garment racks, and warm lighting, perfectly matching the approved starting frame."
        bg_val = visual_desc.get("background", "")
        if not bg_val or "wardrobe" not in bg_val.lower():
            background_desc = wardrobe_bg if not bg_val else f"{wardrobe_bg} with {bg_val}"
        else:
            background_desc = bg_val

        character_position = (
            f"Left frame: Model 1 ({primary_char['display_name']} - {primary_char_id}) wearing approved Model 1 look. "
            f"Right frame: Model 2 ({secondary_char['display_name']} - {sec_char_id}) standing alongside in complementary wardrobe styling."
        )
        speaker_identity = (
            f"Model 1 ({primary_char['display_name']} - {primary_char_id}) is the ONLY speaker. "
            f"Model 2 ({secondary_char['display_name']} - {sec_char_id}) remains silent with lips closed and NO mouth movement as if speaking."
        )
        interaction_notes = (
            f"Model 1 ({primary_char['display_name']}) speaks naturally to camera with warm, expressive gestures. "
            f"Model 2 ({secondary_char['display_name']}) reacts naturally and warmly, smiling subtly and holding silent poise without speaking."
        )
        facial_expressions = (
            f"Model 1 ({primary_char['display_name']}): Confident, warm expression; direct engaging eye contact with camera; relaxed natural smile and mouth movement during vocal delivery. "
            f"Model 2 ({secondary_char['display_name']}): Warm, pleasant smile; relaxed listening expression; lips remain closed at all times."
        )
        lip_sync_instructions = (
            f"Precise lip-sync timing exclusively for Model 1 ({primary_char['display_name']}), accurately matching spoken dialogue '{dialogue_script}'. "
            f"Model 2 ({secondary_char['display_name']}) has ZERO mouth movement and no lip-sync as if speaking."
        )
        continuity_requirements = (
            f"Both models' identities ({primary_char_id} and {sec_char_id}), both approved outfits, "
            f"and the stylish wardrobe/dressing-room background must maintain 100% visual consistency with approved start frame '{start_frame_name}' throughout all 6 seconds."
        )
        negative_constraints = (
            "Model 2 speaking, Model 2 moving mouth, Model 2 lip movement, speech desync, swapping outfits between models, "
            "morphing garments, altering fabric color mid-clip, floating limbs, extra fingers, disjointed mouth movement, "
            "jittery motion, background shifting, distorted face, unapproved hair change, blurry shoes, cut off feet"
        )
    else:
        character_position = f"Center frame: {primary_char['display_name']} ({primary_char_id}) standing full-length in vertical fashion framing."
        speaker_identity = f"{primary_char['display_name']} ({primary_char_id})"
        interaction_notes = "Solo model presentation."
        facial_expressions = "Calm, welcoming expression; eyes engaged directly with camera lens; relaxed natural smile while speaking."
        lip_sync_instructions = (
            f"Precise lip-sync timing strictly matching the spoken English dialogue: '{dialogue_script}'. "
            "Natural mouth articulation without exaggerated jaw movements or facial warping."
        )
        continuity_requirements = (
            f"Garments ({garment_desc} in {colours}), hairstyle ({hairstyle}), footwear ({footwear}), "
            "and physical identity must maintain 100% visual consistency with the approved starting frame throughout all 6 seconds."
        )
        negative_constraints = (
            "morphing garments, altering fabric color mid-clip, floating limbs, extra fingers, disjointed mouth movement, "
            "jittery motion, background shifting, distorted face, unapproved hair change, blurry shoes, cut off feet"
        )

    pose_and_movement = (
        "Model begins in poised standing posture, takes one subtle, confident half-step forward, "
        "gently turns shoulders 15 degrees to display side profile and denim drape, then smoothly returns facing camera."
    )

    hand_movements = "Right hand lightly brushes waistband or pocket; left arm rests naturally at side with relaxed fingers. Zero finger deformation."
    neck_head_movements = "Subtle natural head tilt emphasizing neckline and shoulder tailoring during vocal delivery."
    camera_framing = "Vertical 9:16 full-body fashion framing; complete head-to-toe coverage keeping footwear visible throughout the motion."
    camera_movement = "Very subtle slow tracking push-in (zoom 1.0x to 1.08x) with a completely stable horizon and zero camera shake."
    background = background_desc
    lighting = "Consistent soft commercial key lighting; high color fidelity maintaining exact garment hues matching approved starting frame."
    audio_requirements = "Clear, crisp studio vocal narration; subtle warm acoustic lo-fi fashion background music cue; zero audio distortion."

    # Master prompt block for Google Flow / Sora / Runway
    master_prompt = (
        f"Cinematic vertical fashion video (9:16 aspect ratio, 6 seconds, 24fps). "
        f"Start Frame: Approved master outfit image '{start_frame_name}' ({primary_char_id}). "
        f"Scene: {title}. {character_position} "
        f"Actual Wardrobe: {garment_desc} in {colours}. Fit: {fit_silhouette}. Footwear: {footwear}. Accessories: {accessories}. Hairstyle: {hairstyle}. "
        f"Motion: {pose_and_movement} {hand_movements} {neck_head_movements} "
        f"Facial & Dialogue: {facial_expressions} Spoken line: \"{dialogue_script}\". {speaker_identity}. {lip_sync_instructions} "
        f"Camera: {camera_framing} {camera_movement} "
        f"Lighting & Continuity: {lighting} {continuity_requirements} "
        f"Negative: {negative_constraints}"
    )

    return {
        "clip_id": f"CLIP-{clip_index:02d}",
        "outfit_id": outfit["outfit_id"],
        "approved_image_id": image_asset.get("image_id"),
        "start_frame_image": file_path_str,
        "character_id": primary_char_id,
        "dual_character_id": dual_character_id if is_dual else None,
        "scene_description": title,
        "character_position": character_position,
        "clothing_and_accessories": f"{garment_desc}. Shoes: {footwear}. Accessories: {accessories}.",
        "pose_and_movement": pose_and_movement,
        "facial_expressions": facial_expressions,
        "dialogue": dialogue_script,
        "speaker_identity": speaker_identity,
        "interaction_notes": interaction_notes,
        "lip_sync_instructions": lip_sync_instructions,
        "hand_movements": hand_movements,
        "neck_head_movements": neck_head_movements,
        "camera_framing": camera_framing,
        "camera_movement": camera_movement,
        "background": background,
        "lighting": lighting,
        "duration_seconds": 6,
        "aspect_ratio": "9:16",
        "audio_requirements": audio_requirements,
        "continuity_requirements": continuity_requirements,
        "negative_constraints": negative_constraints,
        "master_prompt": master_prompt,
        "prompt_version": image_asset.get("prompt_version", 1),
        "visual_description": visual_desc,
    }
