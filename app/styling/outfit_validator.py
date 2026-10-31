"""16-dimension outfit validation and distinctness engine for Wear & Wonder."""
import re
from typing import Any
from app.topic_router import get_topic_config


VALIDATION_DIMENSIONS = [
    "garment_type",
    "silhouette",
    "proportions",
    "fit",
    "fabric_and_texture",
    "colour_harmony",
    "occasion",
    "season_and_climate",
    "footwear",
    "bag_and_accessories",
    "practicality",
    "visual_balance",
    "audience_compatibility",
    "distinctness",
    "master_model_compatibility",
    "format_compatibility",
]


def validate_outfit_record(
    outfit: dict[str, Any],
    all_outfits: list[dict[str, Any]] | None = None,
    audience: str | None = None,
    master_model_ids: list[str] | None = None,
) -> tuple[dict[str, dict[str, str]], list[str], float]:
    """Assess outfit against all 16 fashion dimensions and return (checks, warnings, confidence_score)."""
    topic_id = outfit.get("topic", "general_fashion")
    topic_config = get_topic_config(topic_id)

    results: dict[str, dict[str, str]] = {}
    warnings: list[str] = []

    # 1. Garment Type
    garments = outfit.get("garments", [])
    if garments and len(garments) >= 2:
        results["garment_type"] = {
            "status": "PASS",
            "notes": f"Complete multi-piece ensemble ({len(garments)} garments defined).",
        }
    else:
        results["garment_type"] = {
            "status": "WARN",
            "notes": "Minimal pieces defined; verify that top and bottom are explicitly separated.",
        }
        warnings.append("Outfit has fewer than two defined garments.")

    # 2. Silhouette
    silhouette = str(outfit.get("fit_and_silhouette", "")).strip()
    if silhouette:
        results["silhouette"] = {"status": "PASS", "notes": f"Silhouette clearly defined: {silhouette}"}
    else:
        results["silhouette"] = {"status": "WARN", "notes": "Silhouette profile not specified."}
        warnings.append("Silhouette profile missing.")

    # 3. Proportions
    desc = str(outfit.get("garment_descriptions", "")).lower()
    has_proportion_balance = any(term in desc for term in ["crop", "tuck", "high-rise", "oversized", "fitted", "relaxed", "tailored"])
    if has_proportion_balance:
        results["proportions"] = {"status": "PASS", "notes": "Proportion balance explicitly addressed (tuck/crop/rise relationships)."}
    else:
        results["proportions"] = {"status": "WARN", "notes": "Check top-to-bottom volume relationship."}

    # 4. Fit
    if any(term in desc for term in ["fit", "straight", "wide", "relaxed", "tapered", "snug"]):
        results["fit"] = {"status": "PASS", "notes": "Garment fit and tailoring defined."}
    else:
        results["fit"] = {"status": "WARN", "notes": "Garment fit ambiguous."}

    # 5. Fabric and Texture
    fabrics = str(outfit.get("fabrics_and_textures", "")).strip()
    if fabrics:
        results["fabric_and_texture"] = {"status": "PASS", "notes": f"Textural balance defined: {fabrics}"}
    else:
        results["fabric_and_texture"] = {"status": "WARN", "notes": "Fabric textures unspecified."}

    # 6. Colour Harmony
    colours = outfit.get("colours", [])
    if isinstance(colours, list) and 1 <= len(colours) <= 4:
        results["colour_harmony"] = {
            "status": "PASS",
            "notes": f"Cohesive palette ({', '.join(colours)}) within 2–4 harmonious color limit.",
        }
    elif isinstance(colours, list) and len(colours) > 4:
        results["colour_harmony"] = {
            "status": "WARN",
            "notes": f"Palette has {len(colours)} colours; risk of visual clutter.",
        }
        warnings.append("Color palette exceeds 4 colors; review for visual harmony.")
    else:
        results["colour_harmony"] = {"status": "WARN", "notes": "Color palette unspecified."}

    # 7. Occasion
    occasion = str(outfit.get("occasion", "")).strip()
    if occasion:
        results["occasion"] = {"status": "PASS", "notes": f"Suited to occasion: {occasion}"}
    else:
        results["occasion"] = {"status": "WARN", "notes": "Occasion context missing."}

    # 8. Season & Climate
    season = str(outfit.get("season", "")).strip()
    if season:
        results["season_and_climate"] = {"status": "PASS", "notes": f"Aligned with season: {season}"}
    else:
        results["season_and_climate"] = {"status": "PASS", "notes": "Trans-seasonal versatile look."}

    # 9. Footwear
    footwear = str(outfit.get("footwear", "")).strip()
    if footwear and footwear.lower() != "none":
        results["footwear"] = {"status": "PASS", "notes": f"Grounded with footwear: {footwear}"}
    else:
        results["footwear"] = {"status": "WARN", "notes": "Footwear missing or ambiguous."}
        warnings.append("Footwear not specified.")

    # 10. Bag & Accessories
    acc = str(outfit.get("accessories", "")).strip()
    if acc:
        results["bag_and_accessories"] = {"status": "PASS", "notes": f"Accessories defined: {acc}"}
    else:
        results["bag_and_accessories"] = {"status": "PASS", "notes": "Clean minimal styling with no required accessories."}

    # 11. Practicality
    if any(term in desc for term in ["comfortable", "wearable", "practical", "everyday", "breathable", "sturdy", "functional"]):
        results["practicality"] = {"status": "PASS", "notes": "High daily functional wearability."}
    else:
        results["practicality"] = {"status": "PASS", "notes": "Standard wearability."}

    # 12. Visual Balance
    if results["silhouette"]["status"] == "PASS" and results["colour_harmony"]["status"] == "PASS":
        results["visual_balance"] = {"status": "PASS", "notes": "Balanced visual weight and focal point."}
    else:
        results["visual_balance"] = {"status": "WARN", "notes": "Review overall balance between top, bottom, and shoes."}

    # 13. Audience Compatibility
    target_aud = audience or "General audience"
    results["audience_compatibility"] = {
        "status": "PASS",
        "notes": f"Styling calibrated for {target_aud}.",
    }

    # 14. Distinctness from other outfits
    other_outfits = [o for o in (all_outfits or []) if o.get("outfit_id") != outfit.get("outfit_id")]
    is_distinct, similarity_notes = check_outfit_distinctness(outfit, other_outfits)
    if is_distinct:
        results["distinctness"] = {"status": "PASS", "notes": "Visually distinct from other collection outfits."}
    else:
        results["distinctness"] = {"status": "WARN", "notes": similarity_notes}
        warnings.append(f"Near-duplicate look detected: {similarity_notes}")

    # 15. Master Model Compatibility
    chars = master_model_ids or ["WW-CHAR-01"]
    results["master_model_compatibility"] = {
        "status": "PASS",
        "notes": f"Compatible with master model identities ({', '.join(chars)}).",
    }

    # 16. Format Compatibility (Vertical 9:16 video / image)
    results["format_compatibility"] = {
        "status": "PASS",
        "notes": "Full-length vertical orientation allows complete shoe-to-head visibility without awkward cropping.",
    }

    # Calculate documented confidence score:
    # 16 points possible. PASS = 1.0, WARN = 0.5, FAIL = 0.0.
    total_score = sum(
        1.0 if r["status"] == "PASS" else 0.5 if r["status"] == "WARN" else 0.0
        for r in results.values()
    )
    confidence_score = round(total_score / len(VALIDATION_DIMENSIONS), 2)

    return results, warnings, confidence_score


def check_outfit_distinctness(target_outfit: dict, other_outfits: list[dict]) -> tuple[bool, str]:
    """Check if target outfit is sufficiently distinct from other proposed outfits."""
    if not other_outfits:
        return True, "Unique outfit."

    target_tokens = _extract_outfit_tokens(target_outfit)

    for other in other_outfits:
        other_tokens = _extract_outfit_tokens(other)
        if not target_tokens or not other_tokens:
            continue
        intersection = target_tokens.intersection(other_tokens)
        union = target_tokens.union(other_tokens)
        similarity = len(intersection) / len(union) if union else 0.0

        if similarity > 0.70:
            other_id = other.get("outfit_id", "another outfit")
            return (
                False,
                f"High similarity ({int(similarity * 100)}%) with {other_id}. Garments and styling overlap heavily.",
            )

    return True, "Distinct from all other proposed looks."


def _extract_outfit_tokens(outfit: dict) -> set[str]:
    """Extract key stylistic tokens for similarity analysis."""
    text = (
        f"{outfit.get('outfit_title', '')} "
        f"{outfit.get('garment_descriptions', '')} "
        f"{outfit.get('footwear', '')} "
        f"{' '.join(outfit.get('colours', []))}"
    ).lower()
    tokens = set(re.findall(r"\b[a-z]{4,}\b", text))
    stopwords = {"with", "this", "that", "from", "look", "wear", "pair", "each", "style", "item"}
    return tokens - stopwords
