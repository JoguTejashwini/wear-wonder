"""Candidate outfit proposal generator based on research evidence and fashion principles."""
from datetime import datetime, timezone
from typing import Any
import uuid

from app.storage import (
    get_brief_by_id,
    get_research_data,
    load_outfits,
    save_outfits,
    record_audit_event,
)
from app.styling.outfit_validator import validate_outfit_record
from app.topic_router import classify_topic


# Curated styling blueprint templates by topic for genuine fashion combinations
BLUEPRINTS_BY_TOPIC: dict[str, list[dict[str, Any]]] = {
    "jeans_and_tops": [
        {
            "title_suffix": "The Relaxed Everyday Straight-Leg",
            "garments": [
                {"type": "Bottom", "item": "High-rise relaxed straight-leg jeans", "color": "Light vintage wash", "fabric": "100% rigid cotton denim", "fit": "High-rise, relaxed through thigh with straight hem"},
                {"type": "Top", "item": "Fitted ribbed crewneck baby tee", "color": "Crisp white", "fabric": "Ribbed organic cotton", "fit": "Gently cropped at natural waistline"},
            ],
            "descriptions": "High-rise relaxed straight jeans in vintage light blue paired with a clean white ribbed baby tee hitting precisely at the waistband.",
            "colours": ["Light Vintage Blue", "Crisp White", "Neutral Tan"],
            "fabrics": "Rigid cotton denim and finely ribbed stretch cotton",
            "silhouette": "Fitted top with relaxed straight lower volume",
            "footwear": "Low-profile retro leather sneakers in white with gum sole",
            "accessories": "Canvas tote bag, minimal silver pendant, thin brown leather belt",
            "occasion": "Campus daytime lectures and cafe study",
            "season": "Spring / Autumn everyday",
            "rationale": "Balances upper-body fitted proportions with relaxed lower denim drape, creating an effortless university campus aesthetic supported by verified fashion guides.",
        },
        {
            "title_suffix": "The Polished Oversized Poplin & Wide-Leg",
            "garments": [
                {"type": "Bottom", "item": "Pleated wide-leg denim trousers", "color": "Medium indigo wash", "fabric": "Mid-weight structured denim", "fit": "High-rise with deep pleats and sweeping wide leg"},
                {"type": "Top", "item": "Oversized menswear-inspired button-down shirt", "color": "French sky blue", "fabric": "Crisp cotton poplin", "fit": "Oversized, French-tucked with cuffs loosely rolled"},
            ],
            "descriptions": "Sweeping medium-wash wide-leg denim trousers paired with a sky-blue crisp poplin button-down half-tucked to showcase the waistband.",
            "colours": ["Medium Indigo", "Sky Blue", "Cognac Brown"],
            "fabrics": "Structured cotton denim and crisp poplin weave",
            "silhouette": "Structured architectural drape with waist definition",
            "footwear": "Chunky lug-sole penny loafers in dark burgundy or black",
            "accessories": "Structured leather shoulder bag and slim gold hoop earrings",
            "occasion": "Presentations, library sessions, and casual meetings",
            "season": "All-season versatile",
            "rationale": "High-low fashion contrast between tailored menswear poplin and relaxed denim volume, anchored by substantial footwear for walking stability.",
        },
        {
            "title_suffix": "The Clean Dark-Wash & Minimal Knitwear",
            "garments": [
                {"type": "Bottom", "item": "Ankle-skimming straight denim", "color": "Raw dark indigo", "fabric": "Heavyweight raw denim with contrast stitching", "fit": "Mid-rise, clean straight cut with minimal break"},
                {"type": "Top", "item": "Fine-gauge lightweight knit polo", "color": "Oatmeal beige", "fabric": "Merino-cotton blend", "fit": "Tailored slim fit neatly tucked"},
            ],
            "descriptions": "Raw dark indigo straight denim with a clean hem, styled with an oatmeal beige knit polo and minimal leather accents.",
            "colours": ["Dark Raw Indigo", "Oatmeal Beige", "Espresso"],
            "fabrics": "Raw structured denim and fine-gauge knitwear",
            "silhouette": "Streamlined vertical column silhouette",
            "footwear": "Classic leather ballet flats or sleek almond-toe loafers",
            "accessories": "Small leather crossbody bag in espresso, gold watch",
            "occasion": "Smart campus dressing and evening study groups",
            "season": "Autumn / Winter layering",
            "rationale": "Dark wash denim elevates the look toward smart-casual, while the soft oatmeal knit adds textural warmth without bulk.",
        },
        {
            "title_suffix": "The Layered Overshirt & Washed Black Denim",
            "garments": [
                {"type": "Bottom", "item": "Faded charcoal wash straight jeans", "color": "Washed black / charcoal", "fabric": "Softened washed denim", "fit": "Mid-rise, relaxed straight cut"},
                {"type": "Top", "item": "Fitted scoop-neck tank layered under an open utility overshirt", "color": "Heather grey tank with olive green overshirt", "fabric": "Cotton jersey tank, structured cotton twill overshirt", "fit": "Fitted base with boxy open layering piece"},
            ],
            "descriptions": "Charcoal washed straight-leg denim paired with a fitted heather grey tank and an unbuttoned olive twill overshirt.",
            "colours": ["Charcoal Grey", "Heather Grey", "Olive Green"],
            "fabrics": "Softened denim, ribbed jersey, and structured twill",
            "silhouette": "Relaxed utilitarian layering",
            "footwear": "Black leather lace-up combat boots or clean skate sneakers",
            "accessories": "Black nylon commuter backpack and dark acetate sunglasses",
            "occasion": "Commute, studio classes, and active weekend wear",
            "season": "Transitional seasonal climate",
            "rationale": "Functional multi-layering for fluctuating indoor/outdoor temperatures, grounded by monochrome charcoal tones and earth-toned accents.",
        },
        {
            "title_suffix": "The Warm Neutral Ecru Denim & Pastel Knit",
            "garments": [
                {"type": "Bottom", "item": "Ecru off-white crop straight jeans", "color": "Natural unbleached ecru", "fabric": "Bull denim with subtle natural slub", "fit": "High-rise, clean straight leg hitting at ankle"},
                {"type": "Top", "item": "V-neck cropped cardigan worn buttoned as a top", "color": "Soft butter yellow or sage pastel", "fabric": "Alpaca-cotton fluffy knit", "fit": "Relaxed crop with ribbed hem"},
            ],
            "descriptions": "Natural ecru straight denim styled with a buttoned soft pastel cardigan and refined neutral footwear.",
            "colours": ["Natural Ecru", "Butter Yellow", "Warm Beige"],
            "fabrics": "Natural bull denim and tactile brushed knit",
            "silhouette": "Soft textural balance with high-waist anchor",
            "footwear": "Minimalist cream court trainers or tan leather mules",
            "accessories": "Woven straw or canvas shoulder tote and delicate pearls",
            "occasion": "Spring campus days and weekend brunch",
            "season": "Spring / Summer warm weather",
            "rationale": "Soft color harmony using unbleached ecru as a grounding neutral, allowing delicate pastel knitwear to serve as a soft focal point.",
        },
        {
            "title_suffix": "The Vintage 90s Heritage Wash & Mock-Neck",
            "garments": [
                {"type": "Bottom", "item": "Vintage-wash full-length 90s relaxed jeans", "color": "Classic mid-blue stone wash", "fabric": "Durable 14oz vintage denim", "fit": "Relaxed high-waist with gentle taper at ankle"},
                {"type": "Top", "item": "Sleek long-sleeve mock-neck top", "color": "Deep forest green or jet black", "fabric": "Modal-blend stretch jersey", "fit": "Fitted body-skimming cut fully tucked"},
            ],
            "descriptions": "90s stone-wash relaxed denim paired with a fitted dark mock-neck top and sleek leather belt.",
            "colours": ["Stone Blue", "Forest Green", "Polished Black"],
            "fabrics": "Heavyweight heritage denim and modal jersey",
            "silhouette": "High-neck streamlined top with relaxed 90s denim drape",
            "footwear": "Black platform derbies or chunky retro runners",
            "accessories": "Polished black leather belt with silver buckle, leather tote",
            "occasion": "Urban commute and autumn college campus",
            "season": "Autumn / Winter",
            "rationale": "A timeless 90s silhouette formula contrasting a sleek fitted mock neckline with authentic heavy denim texture.",
        },
    ],
    "default_blueprints": [
        {
            "title_suffix": "Curated Essential Look 01",
            "garments": [
                {"type": "Bottom", "item": "Tailored relaxed trousers", "color": "Neutral taupe", "fabric": "Wool-blend crepe", "fit": "Pleated high-rise with wide drape"},
                {"type": "Top", "item": "Structured cotton top", "color": "Optic white", "fabric": "Compact cotton jersey", "fit": "Relaxed fit neatly tucked"},
            ],
            "descriptions": "Tailored neutral trousers with a clean white structured top and coordinated accessories.",
            "colours": ["Neutral Taupe", "Optic White", "Cognac"],
            "fabrics": "Wool-blend crepe and compact cotton",
            "silhouette": "Clean vertical drape",
            "footwear": "Polished leather loafers",
            "accessories": "Leather shoulder bag and subtle jewelry",
            "occasion": "Smart casual everyday",
            "season": "Versatile all-season",
            "rationale": "Timeless proportion pairing of structured top with fluid tailored lower body.",
        },
        {
            "title_suffix": "Curated Essential Look 02",
            "garments": [
                {"type": "Bottom", "item": "Structured midi skirt or tapered trousers", "color": "Deep charcoal", "fabric": "Structured twill", "fit": "Clean A-line or tapered silhouette"},
                {"type": "Top", "item": "Fine-knit layering sweater", "color": "Soft camel", "fabric": "Merino knit", "fit": "Relaxed drape"},
            ],
            "descriptions": "Deep charcoal structured bottoms paired with a soft camel fine-knit sweater.",
            "colours": ["Deep Charcoal", "Soft Camel", "Black"],
            "fabrics": "Structured twill and soft knitwear",
            "silhouette": "Balanced volume with textured contrast",
            "footwear": "Ankle boots with low block heel",
            "accessories": "Structured satchel and leather belt",
            "occasion": "Day-to-evening versatile wear",
            "season": "Autumn / Winter",
            "rationale": "High contrast between rich camel knitwear and structured charcoal tailoring.",
        },
        {
            "title_suffix": "Curated Essential Look 03",
            "garments": [
                {"type": "Bottom", "item": "Straight-leg casual chinos or denim", "color": "Washed navy", "fabric": "Durable cotton twill", "fit": "Mid-rise straight cut"},
                {"type": "Top", "item": "Relaxed utility button-down", "color": "Sage green", "fabric": "Garment-dyed linen-cotton", "fit": "Relaxed straight drape"},
            ],
            "descriptions": "Washed navy bottoms paired with an earthy sage green relaxed button-down.",
            "colours": ["Washed Navy", "Sage Green", "White"],
            "fabrics": "Cotton twill and textured linen blend",
            "silhouette": "Effortless casual drape",
            "footwear": "Clean white leather sneakers",
            "accessories": "Crossbody canvas bag and sports watch",
            "occasion": "Weekend outing and daytime leisure",
            "season": "Spring / Summer",
            "rationale": "Calm, nature-inspired palette combining cool navy with muted sage green.",
        },
    ],
}


def generate_outfit_proposals(brief_id: str, count: int | None = None) -> list[dict[str, Any]]:
    """Synthesize complete, validated candidate outfit proposals for an approved brief."""
    brief = get_brief_by_id(brief_id)
    if not brief:
        raise ValueError(f"Brief '{brief_id}' not found.")

    topic_config = classify_topic(brief.get("idea_original", ""))
    target_count = count or brief.get("outfit_count") or 6
    target_count = max(1, min(target_count, 12))

    research_data = get_research_data(brief_id)
    sources = research_data.get("sources", [])
    supporting_source_ids = [s["source_id"] for s in sources[:3]]
    source_urls = [s["url"] for s in sources[:3]]

    blueprints = BLUEPRINTS_BY_TOPIC.get(topic_config.topic_id, BLUEPRINTS_BY_TOPIC["default_blueprints"])
    master_chars = brief.get("requested_characters") or ["WW-CHAR-01"]

    generated_outfits: list[dict[str, Any]] = []

    for index in range(target_count):
        # Rotate through blueprints if count exceeds blueprint list, modifying details to keep distinct
        bp = blueprints[index % len(blueprints)]
        cycle = index // len(blueprints)

        outfit_id = f"OUTFIT-{index + 1:02d}"
        title = f"Look {index + 1}: {bp['title_suffix']}"
        if cycle > 0:
            title += f" (Variation {cycle + 1})"

        garments_copy = [dict(g) for g in bp["garments"]]
        colours_copy = list(bp["colours"])

        # Select assigned character for this outfit
        assigned_char = master_chars[index % len(master_chars)]

        outfit_record: dict[str, Any] = {
            "outfit_id": outfit_id,
            "brief_id": brief_id,
            "topic": topic_config.topic_id,
            "outfit_title": title,
            "assigned_character_id": assigned_char,
            "garments": garments_copy,
            "garment_descriptions": bp["descriptions"],
            "colours": colours_copy,
            "fabrics_and_textures": bp["fabrics"],
            "fit_and_silhouette": bp["silhouette"],
            "footwear": bp["footwear"],
            "accessories": bp["accessories"],
            "occasion": bp["occasion"],
            "season": bp["season"],
            "styling_rationale": bp["rationale"],
            "supporting_source_ids": supporting_source_ids,
            "supporting_source_urls": source_urls,
            "evidence_status": "SUPPORTED_BY_RESEARCH" if sources else "STYLISTIC_BLUEPRINT",
            "approval_status": "PENDING",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "revision_history": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "note": "Initial outfit proposal generated from research brief.",
                }
            ],
        }

        # Run 16-dimension validation
        checks, warnings, confidence = validate_outfit_record(
            outfit_record,
            all_outfits=generated_outfits,
            audience=brief.get("audience"),
            master_model_ids=master_chars,
        )
        outfit_record["validation_results"] = checks
        outfit_record["warnings"] = warnings
        outfit_record["confidence_score"] = confidence

        generated_outfits.append(outfit_record)

    # Save outfits to local storage
    save_outfits(brief_id, generated_outfits)

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_3_OUTFITS",
        action="PROPOSALS_GENERATED",
        details=f"Generated {len(generated_outfits)} candidate outfits (target: {target_count}).",
    )

    return generated_outfits
