"""Platform-specific metadata and SEO content generator for YouTube Shorts & Instagram Reels."""
import re
from datetime import datetime, timezone
from typing import Any

from app.storage import (
    get_brief_by_id,
    load_outfits,
    load_image_assets,
    load_video_assets,
)
from app.approval_workflow import ApprovalStatus


def _sanitize_title_shorts(title: str, max_chars: int = 70) -> str:
    """Ensure Shorts title is punchy and includes #Shorts tag."""
    base = title.strip()
    if "#Shorts" not in base and "#shorts" not in base:
        base = f"{base} #Shorts"
    if len(base) > max_chars:
        # Trim gracefully at word boundary before appending #Shorts
        trimmed = base[: max_chars - 8].rsplit(" ", 1)[0]
        base = f"{trimmed} #Shorts"
    return base


def _format_timestamps(outfits: list[dict], clip_duration_seconds: int = 10) -> tuple[str, list[dict]]:
    """Format structured timestamp chapters for multi-look videos."""
    lines = []
    structured = []
    total_sec = 0

    for i, outfit in enumerate(outfits):
        minutes = total_sec // 60
        seconds = total_sec % 60
        ts_str = f"{minutes}:{seconds:02d}"
        title = outfit.get("outfit_title") or f"Look {i + 1}"
        lines.append(f"{ts_str} {title}")
        structured.append({
            "timestamp": ts_str,
            "seconds": total_sec,
            "look_index": i + 1,
            "label": title,
        })
        total_sec += clip_duration_seconds

    return "\n".join(lines), structured


def generate_publishing_metadata(brief_id: str, clip_duration_seconds: int = 10) -> dict[str, Any]:
    """Generate high-performing, platform-tailored metadata for YouTube Shorts and Instagram Reels."""
    brief = get_brief_by_id(brief_id)
    if not brief:
        raise ValueError(f"Brief '{brief_id}' not found.")

    all_outfits = load_outfits(brief_id)
    # Prefer approved outfits; fall back to all outfits if none yet approved
    approved_outfits = [o for o in all_outfits if o.get("approval_status") == ApprovalStatus.APPROVED.value]
    active_outfits = approved_outfits if approved_outfits else all_outfits

    outfit_count = len(active_outfits) or brief.get("outfit_count") or 1
    audience = brief.get("audience") or "everyday style"
    raw_idea = brief.get("idea_original") or ""

    # Derive core topic from outfits or idea
    primary_topic = "fashion"
    if active_outfits and active_outfits[0].get("topic"):
        primary_topic = active_outfits[0]["topic"].replace("_", " ")
    elif "jeans" in raw_idea.lower():
        primary_topic = "jeans & tops"
    elif "color" in raw_idea.lower() or "colour" in raw_idea.lower():
        primary_topic = "color combinations"

    # --- 1. YouTube Shorts Package ---
    yt_title_base = f"{outfit_count} Effortless {primary_topic.title()} Outfits for {audience.title()} ✨"
    yt_title = _sanitize_title_shorts(yt_title_base, max_chars=68)

    timestamps_text, structured_timestamps = _format_timestamps(active_outfits, clip_duration_seconds)

    outfit_breakdown_lines = []
    for i, outfit in enumerate(active_outfits, 1):
        otitle = outfit.get("outfit_title") or f"Look {i}"
        garments = outfit.get("garment_descriptions") or ", ".join([g.get("item", "") for g in outfit.get("garments", [])])
        colours = ", ".join(outfit.get("colours", [])) if isinstance(outfit.get("colours"), list) else outfit.get("colours", "")
        footwear = outfit.get("footwear") or ""
        outfit_breakdown_lines.append(f"• {otitle}: {garments}" + (f" (Colors: {colours})" if colours else "") + (f" | Shoes: {footwear}" if footwear else ""))

    yt_description = (
        f"Looking for effortless {primary_topic} styling ideas? Here are {outfit_count} curated, chic outfit combinations "
        f"tailored for {audience.lower()} that you can recreate instantly!\n\n"
        f"⏱️ TIMESTAMPS & OUTFIT BREAKDOWN:\n"
        f"{timestamps_text}\n\n"
        f"👗 LOOK DETAILS:\n"
        + "\n".join(outfit_breakdown_lines)
        + "\n\n"
        f"💬 Which look is your absolute favorite? Let us know in the comments below! 👇\n\n"
        f"✨ Subscribe to Wear & Wonder for daily styling guides, aesthetic capsule wardrobe ideas, and runway-to-street inspiration.\n\n"
        f"#Shorts #Fashion #OutfitIdeas #{primary_topic.replace(' ', '')} #StyleInspo #{audience.replace(' ', '')}Outfits #OOTD #WearAndWonder"
    )

    yt_tags = [
        "fashion shorts",
        f"{primary_topic} outfits",
        f"{audience.lower()} style",
        "outfit ideas 2026",
        "aesthetic fashion",
        "styling guide",
        "capsule wardrobe",
        "lookbook",
        "wear and wonder",
        "outfit transition",
        "how to style",
        "trending fashion reels",
    ]
    # Ensure tags string does not exceed 500 characters
    yt_tags_str = ", ".join(yt_tags)
    if len(yt_tags_str) > 490:
        yt_tags = [t for t in yt_tags if len(", ".join(yt_tags[:yt_tags.index(t)])) < 450]
        yt_tags_str = ", ".join(yt_tags)

    # --- 2. Instagram Reels Package ---
    ig_caption_lines = [
        f"✨ Save this for styling inspo! {outfit_count} curated {primary_topic} looks for {audience.lower()} 🤍💫",
        "",
        "Breakdown of each look:",
    ]
    for i, outfit in enumerate(active_outfits, 1):
        otitle = outfit.get("outfit_title") or f"Look {i}"
        garments = outfit.get("garment_descriptions") or ", ".join([g.get("item", "") for g in outfit.get("garments", [])])
        colours = ", ".join(outfit.get("colours", [])) if isinstance(outfit.get("colours"), list) else outfit.get("colours", "")
        ig_caption_lines.append(f"✨ {otitle} — {garments}" + (f" ({colours})" if colours else ""))

    ig_caption_lines.extend([
        "",
        f"Drop your favorite look (1 to {outfit_count}) in the comments! 👇",
        "Follow @wearandwonder for daily aesthetic styling inspo 🕊️",
        "",
        ".",
        ".",
    ])

    topic_slug = primary_topic.replace("&", "").replace(" ", "").lower()
    audience_slug = audience.replace(" ", "").lower()
    ig_hashtags = [
        "#reelsfashion",
        "#fashionreels",
        "#outfitinspo",
        "#aestheticoutfits",
        "#ootdindia",
        "#styletips",
        "#capsulewardrobe",
        "#outfitideas",
        f"#{topic_slug}",
        f"#{topic_slug}outfits",
        f"#{audience_slug}style",
        "#wearandwonder",
        "#everydaystyle",
        "#streetstyle",
        "#fashiontrends2026",
    ]
    # Deduplicate while preserving order
    seen = set()
    ig_hashtags = [h for h in ig_hashtags if not (h in seen or seen.add(h))]
    ig_hashtags_text = " ".join(ig_hashtags)

    ig_full_caption = "\n".join(ig_caption_lines) + "\n" + ig_hashtags_text

    return {
        "brief_id": brief_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "youtube": {
            "title": yt_title,
            "description": yt_description,
            "tags": yt_tags,
            "tags_comma_separated": yt_tags_str,
            "category_id": "26",  # Howto & Style
            "privacy_status": "private",
        },
        "instagram": {
            "caption": ig_full_caption,
            "caption_without_hashtags": "\n".join(ig_caption_lines),
            "hashtags": ig_hashtags,
            "hashtags_text": ig_hashtags_text,
        },
        "timestamps": structured_timestamps,
        "timestamps_text": timestamps_text,
    }
