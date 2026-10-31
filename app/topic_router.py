"""Fashion topic router and configuration for Wear & Wonder."""
from dataclasses import dataclass, field
import re
from typing import Any


@dataclass
class TopicConfig:
    topic_id: str
    display_name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    research_focus: list[str] = field(default_factory=list)
    query_templates: list[str] = field(default_factory=list)
    validation_priorities: list[str] = field(default_factory=list)
    styling_guidelines: list[str] = field(default_factory=list)
    image_prompt_focus: list[str] = field(default_factory=list)
    video_prompt_focus: list[str] = field(default_factory=list)


# Authoritative library of supported topic configurations
TOPIC_REGISTRY: dict[str, TopicConfig] = {
    "jeans_and_tops": TopicConfig(
        topic_id="jeans_and_tops",
        display_name="Jeans & Top Combinations",
        description="Denim styling, leg cuts, rises, top proportions, and complementary footwear.",
        keywords=[
            "jean", "jeans", "denim", "top", "tops", "t-shirt", "tee", "blouse",
            "shirt", "wide-leg", "straight-leg", "skinny", "flare", "mom jeans",
        ],
        research_focus=[
            "Trending denim cuts and silhouettes (e.g. wide-leg, barrel, straight)",
            "Top-to-bottom proportion balance (crop vs oversized, tucked vs untucked)",
            "Wash pairing (light wash, raw indigo, vintage wash, black denim)",
            "Footwear compatibility (loafers, retro sneakers, ankle boots)",
        ],
        query_templates=[
            "{audience} trending jeans and tops outfit combinations",
            "how to style {silhouette} jeans with tops {season}",
            "denim outfit inspiration {audience} styling guide",
        ],
        validation_priorities=[
            "silhouette", "proportions", "fit", "fabric", "footwear", "visual_balance",
        ],
        styling_guidelines=[
            "Balance volume: pair wide or relaxed denim with structured or fitted tops, and slim denim with relaxed layers.",
            "Consider rise and hemline: ensure tops do not awkwardly break the waistband line.",
            "Choose footwear that complements the denim break and puddle length.",
        ],
        image_prompt_focus=[
            "Clear depiction of denim texture, wash grading, seam details, and hemline break over footwear.",
            "Clean silhouette showing exact top tuck or crop relationship to the waistband.",
        ],
        video_prompt_focus=[
            "Subtle walking motion or gentle turn highlighting garment drape, denim structure, and movement.",
            "Natural hand gesture touching lapel or pocket.",
        ],
    ),
    "colour_combinations": TopicConfig(
        topic_id="colour_combinations",
        display_name="Colour Combinations",
        description="Colour harmony, contrast, undertones, tonal layering, and accent accents.",
        keywords=[
            "color", "colour", "palette", "combinations", "monochrome", "tonal",
            "contrast", "complementary", "undertone", "pastel", "earth tone", "neutrals",
        ],
        research_focus=[
            "Current trending color palettes and seasonal color harmonies",
            "High contrast vs subtle tonal styling techniques",
            "Rule of three colors in outfit coordination",
            "Accent color accessories and footwear grounding",
        ],
        query_templates=[
            "fashion colour combinations trends {season}",
            "outfit color palette coordination guide {audience}",
            "chic monochromatic and tonal outfit ideas",
        ],
        validation_priorities=[
            "colour_harmony", "visual_balance", "accessories", "proportions", "occasion",
        ],
        styling_guidelines=[
            "Limit primary outfit to 2–3 harmonious colours with one grounding neutral.",
            "Align temperature: pair warm undertones with warm accents, or use deliberate temperature contrast.",
            "Distribute colour weight evenly from top to bottom.",
        ],
        image_prompt_focus=[
            "Precise colour accuracy, natural lighting without harsh tints that alter colour perception.",
            "Visible fabric textures preventing solid blocks of colour from looking flat.",
        ],
        video_prompt_focus=[
            "Camera framing that captures the complete colour balance from head to toe.",
            "Natural lighting transitions keeping outfit hues consistent.",
        ],
    ),
    "casual_and_college": TopicConfig(
        topic_id="casual_and_college",
        display_name="Casual & College Outfits",
        description="Comfortable, versatile, youthful everyday looks suitable for campus, commute, and study.",
        keywords=[
            "college", "campus", "university", "student", "casual", "everyday",
            "daily", "commute", "laid-back", "streetwear", "effortless",
        ],
        research_focus=[
            "Campus lifestyle practicality and walking comfort",
            "Layering for variable indoor/outdoor temperatures",
            "Smart casual staples (overshirts, cardigans, clean sneakers, totes)",
            "Youthful trend integration without sacrificing comfort",
        ],
        query_templates=[
            "college campus fashion trends {audience} {season}",
            "casual everyday outfit ideas {audience}",
            "comfortable chic university student styling guide",
        ],
        validation_priorities=[
            "practicality", "audience_fit", "footwear", "season", "bag_and_accessories",
        ],
        styling_guidelines=[
            "Prioritize wearable comfort: flat shoes, functional bags (totes/backpacks), breathable fabrics.",
            "Layer lightweight knits, jackets, or overshirts for adaptable styling.",
            "Maintain relaxed yet intentional silhouettes.",
        ],
        image_prompt_focus=[
            "Authentic daytime lighting, realistic relaxed postures, campus-appropriate accessories like tote bags.",
            "Polished yet casual grooming matching master-model rules.",
        ],
        video_prompt_focus=[
            "Dynamic yet relaxed movement: swinging tote, adjusting jacket strap, confident campus walk.",
            "Friendly, approachable expression and engaging fashion dialogue.",
        ],
    ),
    "formal_and_office": TopicConfig(
        topic_id="formal_and_office",
        display_name="Formal & Office Wear",
        description="Tailored suiting, smart workwear, structured silhouettes, and professional dress codes.",
        keywords=[
            "formal", "office", "workwear", "corporate", "business", "professional",
            "blazer", "suit", "trousers", "pencil skirt", "tailoring", "executive",
        ],
        research_focus=[
            "Modern business casual vs formal corporate dress codes",
            "Contemporary tailoring: relaxed blazers, pleated trousers, structured dresses",
            "Fabric quality: wool blends, crisp poplin, crepe, matte silk",
            "Professional footwear and minimal sophisticated accessories",
        ],
        query_templates=[
            "modern office workwear outfit ideas {audience}",
            "contemporary business casual tailoring {season}",
            "smart formal fashion styling guide {audience}",
        ],
        validation_priorities=[
            "fit", "silhouette", "fabric", "occasion", "visual_balance", "footwear",
        ],
        styling_guidelines=[
            "Ensure precise tailoring at shoulders, sleeve lengths, and trouser breaks.",
            "Use refined neutral bases with subtle textured accents.",
            "Pair with polished loafers, pointed flats, or structured formal shoes.",
        ],
        image_prompt_focus=[
            "Crisp garment pressing, visible fabric weave, clean architectural background, refined posture.",
            "Strict adherence to sleek bun or low ponytail styling rules for master models.",
        ],
        video_prompt_focus=[
            "Composed, professional demeanor; deliberate and poised movements.",
            "Crisp audio delivery explaining professional tailoring details.",
        ],
    ),
    "shoes_and_footwear": TopicConfig(
        topic_id="shoes_and_footwear",
        display_name="Footwear & Shoe Matching",
        description="Pairing footwear styles with trousers, skirts, denim cuts, and styling occasions.",
        keywords=[
            "shoe", "shoes", "footwear", "sneaker", "sneakers", "boot", "boots",
            "loafer", "loafers", "heels", "sandals", "mules", "slides",
        ],
        research_focus=[
            "Footwear-to-pant hemline relationships (crop, cuff, full break, puddle)",
            "Trending footwear categories (chunky loafers, low-profile retro sneakers, sleek boots)",
            "Balancing visual weight between shoes and overall outfit silhouette",
        ],
        query_templates=[
            "how to style {footwear} with outfits {season}",
            "best shoes to wear with wide leg straight pants {audience}",
            "trending footwear styling combinations guide",
        ],
        validation_priorities=[
            "footwear", "proportions", "silhouette", "occasion", "practicality",
        ],
        styling_guidelines=[
            "Ensure trouser hem length cleanly showcases or drapes over the shoe without bunching awkwardly.",
            "Balance bulky chunky footwear with balanced lower-body volume.",
            "Match shoe formality with the rest of the outfit.",
        ],
        image_prompt_focus=[
            "Full-length shot with razor-sharp focus on shoe details, leather finish, and ankle/hem transition.",
        ],
        video_prompt_focus=[
            "Subtle footwork or step forward allowing clear viewer inspection of shoe movement and styling.",
        ],
    ),
    "bags_and_accessories": TopicConfig(
        topic_id="bags_and_accessories",
        display_name="Bags & Accessories Matching",
        description="Bag shapes, scales, jewelry, belts, scarves, and cohesive accessory curation.",
        keywords=[
            "bag", "bags", "handbag", "purse", "tote", "crossbody", "clutch",
            "accessory", "accessories", "jewelry", "belt", "sunglasses", "scarf",
        ],
        research_focus=[
            "Bag scale relative to body proportions and outfit bulk",
            "Hardware metal harmony (gold, silver, brass coordination)",
            "Texture mixing (leather, suede, raffia, canvas)",
            "Functional vs statement accessories",
        ],
        query_templates=[
            "how to match bags and accessories with outfits {audience}",
            "trending handbag styles and styling combinations {season}",
            "elevating simple outfits with accessories guide",
        ],
        validation_priorities=[
            "accessories", "bag_and_accessories", "visual_balance", "colour_harmony", "occasion",
        ],
        styling_guidelines=[
            "Choose bag scale appropriate to both body frame and activity.",
            "Harmonize metal hardware between belt, bag clasps, and jewelry.",
            "Avoid clutter: let one accessory be the focal statement while others support.",
        ],
        image_prompt_focus=[
            "Distinct, detailed rendering of bag leather grain, hardware shine, and precise accessory placement.",
        ],
        video_prompt_focus=[
            "Natural interaction with bag strap or clutch carry during fashion presentation.",
        ],
    ),
    "seasonal_styling": TopicConfig(
        topic_id="seasonal_styling",
        display_name="Seasonal Styling",
        description="Weather-appropriate layering, fabric weights, seasonal color palettes, and climate comfort.",
        keywords=[
            "season", "seasonal", "summer", "winter", "fall", "autumn", "spring",
            "monsoon", "rainy", "warm weather", "cold weather", "layering", "coat",
        ],
        research_focus=[
            "Seasonal transition layering techniques",
            "Fabric climate appropriateness (linen/cotton for heat; wool/cashmere for cold)",
            "Seasonal palette shifts (fresh pastels, rich earth tones, crisp winter neutrals)",
        ],
        query_templates=[
            "{season} fashion trends and outfit ideas {audience}",
            "how to layer outfits for {season} weather",
            "stylish seasonal wardrobe transition guide",
        ],
        validation_priorities=[
            "season", "fabric", "practicality", "silhouette", "colour_harmony",
        ],
        styling_guidelines=[
            "Ensure layers are functionally removable and look complete both layered and unlayered.",
            "Use texture contrast between layers (e.g. knit over silk or denim under wool).",
            "Verify weather practicality of footwear and outerwear.",
        ],
        image_prompt_focus=[
            "Atmospheric seasonal lighting, clear distinction between fabric weights (chunky knits vs airy cotton).",
        ],
        video_prompt_focus=[
            "Demonstration of garment versatility and movement in seasonal climate context.",
        ],
    ),
    "couples_styling": TopicConfig(
        topic_id="couples_styling",
        display_name="Couples' Styling",
        description="Complementary coordination between two models without identical matching.",
        keywords=[
            "couple", "couples", "his and hers", "duo", "two models", "partner",
            "matching couple", "coordinating couple",
        ],
        research_focus=[
            "Complementary color palettes for two individuals",
            "Formality alignment between partners",
            "Coordinated aesthetic without identical 'twinning'",
            "Dual-model visual balance in frame",
        ],
        query_templates=[
            "couple outfit ideas complementary styling {occasion}",
            "how to coordinate couple outfits without matching",
            "stylish couple fashion combinations trends",
        ],
        validation_priorities=[
            "visual_balance", "colour_harmony", "occasion", "proportions", "audience_fit",
        ],
        styling_guidelines=[
            "Coordinate color temperature and formality levels without using identical pieces.",
            "Balance visual weight: one partner in bold tones paired with complementary refined neutrals.",
            "Ensure both models feel individually authentic to their master character rules.",
        ],
        image_prompt_focus=[
            "Two distinct models positioned side-by-side with clear lighting on both and complementary postures.",
        ],
        video_prompt_focus=[
            "Explicit left/right staging, natural interaction (side glance, coordinated step), unambiguous speaking role.",
        ],
    ),
    "mens_fashion": TopicConfig(
        topic_id="mens_fashion",
        display_name="Men's Fashion & Styling",
        description="Masculine silhouettes, tailoring, casual staples, grooming, and proportion harmony.",
        keywords=[
            "men", "man", "mens", "male", "guy", "boys", "boy", "gentleman",
            "menswear", "trousers", "oxford", "overshirt",
        ],
        research_focus=[
            "Modern menswear proportions (relaxed tailoring, wide trousers, camp collar shirts)",
            "Classic staples updated with contemporary fits",
            "Masculine footwear (derbies, clean white leather sneakers, chelsea boots)",
        ],
        query_templates=[
            "men's style trends outfit combinations {season}",
            "casual and smart menswear outfit ideas {audience}",
            "mens fashion capsule wardrobe styling guide",
        ],
        validation_priorities=[
            "silhouette", "fit", "fabric", "footwear", "proportions", "practicality",
        ],
        styling_guidelines=[
            "Ensure shoulder seam alignment and proper sleeve/inseam lengths.",
            "Incorporate clean texture layering (e.g., suede, waffle knits, structured denim).",
            "Maintain consistency with WW-CHAR-03 master model identity.",
        ],
        image_prompt_focus=[
            "Strong masculine silhouette, natural grooming matching WW-CHAR-03 dark wavy hair guidelines.",
        ],
        video_prompt_focus=[
            "Confident, relaxed posture, clean vocal delivery, natural hand-in-pocket or cuff adjust gesture.",
        ],
    ),
    "womens_fashion": TopicConfig(
        topic_id="womens_fashion",
        display_name="Women's Fashion & Styling",
        description="Women's versatile styling, silhouettes, fabric drapes, layering, and occasion versatility.",
        keywords=[
            "women", "woman", "womens", "female", "girl", "girls", "ladies",
            "dress", "skirt", "feminine",
        ],
        research_focus=[
            "Contemporary women's trend forecasting and timeless styling formulas",
            "Silhouette variations (A-line, column, oversized drape, cinched waist)",
            "Versatile pieces transitioning from day to evening",
        ],
        query_templates=[
            "women fashion outfit combinations {season} {audience}",
            "chic everyday womens styling inspiration guide",
            "trending womens fashion looks {occasion}",
        ],
        validation_priorities=[
            "silhouette", "proportions", "colour_harmony", "fabric", "footwear",
        ],
        styling_guidelines=[
            "Balance volume and proportion across the silhouette.",
            "Respect approved hairstyles and profiles for WW-CHAR-01 / WW-CHAR-02.",
            "Incorporate clean layering and intentional accessories.",
        ],
        image_prompt_focus=[
            "High aesthetic fashion photography, graceful natural posture, accurate fabric drape and texture.",
        ],
        video_prompt_focus=[
            "Fluid, elegant movement showcasing garment silhouette in motion.",
        ],
    ),
    "general_fashion": TopicConfig(
        topic_id="general_fashion",
        display_name="Fashion & Style Curation",
        description="Comprehensive fashion styling, outfit coordination, and aesthetic curation.",
        keywords=[],
        research_focus=[
            "Modern fashion aesthetics and contemporary styling formulas",
            "Garment coordination, proportions, and fit",
            "Color harmony and fabric compatibility",
        ],
        query_templates=[
            "fashion outfit styling inspiration {season}",
            "contemporary wardrobe styling ideas guide",
        ],
        validation_priorities=[
            "proportions", "silhouette", "colour_harmony", "practicality", "visual_balance",
        ],
        styling_guidelines=[
            "Ensure cohesive styling across all pieces from top to footwear.",
            "Balance colors, textures, and silhouettes intentionally.",
        ],
        image_prompt_focus=[
            "Clear high-fashion studio shot with accurate colors and textures.",
        ],
        video_prompt_focus=[
            "Natural model movement with engaging fashion commentary.",
        ],
    ),
}


def classify_topic(idea_text: str, hint: str | None = None) -> TopicConfig:
    """Classify user idea into the most appropriate fashion topic configuration."""
    if hint and hint in TOPIC_REGISTRY:
        return TOPIC_REGISTRY[hint]

    text = idea_text.lower().strip()
    scores: dict[str, int] = {}

    for topic_id, config in TOPIC_REGISTRY.items():
        if topic_id == "general_fashion":
            continue
        score = 0
        for kw in config.keywords:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, text):
                # Stronger weight for longer or exact compound keywords
                score += 2 if len(kw) > 5 else 1
        scores[topic_id] = score

    best_topic, best_score = max(scores.items(), key=lambda x: x[1]) if scores else ("general_fashion", 0)

    if best_score > 0:
        return TOPIC_REGISTRY[best_topic]

    return TOPIC_REGISTRY["general_fashion"]


def get_topic_config(topic_id: str) -> TopicConfig:
    """Retrieve topic configuration by ID, fallback to general_fashion if unknown."""
    return TOPIC_REGISTRY.get(topic_id, TOPIC_REGISTRY["general_fashion"])


def list_supported_topics() -> list[TopicConfig]:
    """Return all pre-configured topics."""
    return list(TOPIC_REGISTRY.values())
