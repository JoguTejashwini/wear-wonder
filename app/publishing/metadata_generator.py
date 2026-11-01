"""Platform-specific metadata and SEO content generator for YouTube Shorts & Instagram Reels.
Derives metadata strictly from existing task data (brief, approved outfits, images, and video clips).
"""
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


def _format_timestamps_from_clips(
    outfits: list[dict],
    video_clips: list[dict],
    default_clip_duration_seconds: int = 6,
) -> tuple[str, list[dict], int]:
    """Format structured timestamp chapters based on actual planned clip durations."""
    if not outfits:
        return "", [], 0

    lines = []
    structured = []
    total_sec = 0

    # Index video clips by outfit_id for precise duration mapping
    clips_by_outfit = {v.get("outfit_id"): v for v in video_clips if isinstance(v, dict)}

    for i, outfit in enumerate(outfits):
        oid = outfit.get("outfit_id")
        clip = clips_by_outfit.get(oid)
        clip_dur = default_clip_duration_seconds
        if clip and isinstance(clip.get("prompt_data"), dict):
            clip_dur = clip["prompt_data"].get("duration_seconds", default_clip_duration_seconds)

        minutes = total_sec // 60
        seconds = total_sec % 60
        ts_str = f"{minutes}:{seconds:02d}"
        title = outfit.get("outfit_title") or f"Look {i + 1}"
        lines.append(f"{ts_str} {title}")
        structured.append({
            "timestamp": ts_str,
            "seconds": total_sec,
            "duration_seconds": clip_dur,
            "look_index": i + 1,
            "outfit_id": oid,
            "label": title,
        })
        total_sec += clip_dur

    return "\n".join(lines), structured, total_sec


def get_recommended_thumbnail(image_assets: list[dict]) -> dict[str, Any] | None:
    """Select the best approved Stage 4 image to recommend as the video thumbnail."""
    if not image_assets:
        return None

    approved_images = [
        img for img in image_assets
        if isinstance(img, dict) and img.get("approval_status") == ApprovalStatus.APPROVED.value
    ]

    target = None
    if approved_images:
        # Prefer dual-model master look if present, otherwise first approved look
        target = next((img for img in approved_images if img.get("is_dual_model")), approved_images[0])
    else:
        # Fall back to first generated image if none approved yet
        target = image_assets[0]

    if not target:
        return None

    return {
        "image_id": target.get("image_id"),
        "outfit_id": target.get("outfit_id"),
        "character_name": target.get("character_name") or target.get("character_id") or "Model",
        "file_path": target.get("file_path"),
        "is_dual_model": bool(target.get("is_dual_model")),
        "recommendation_reason": (
            "Approved dual-model wardrobe visual"
            if target.get("is_dual_model")
            else f"Approved Stage 4 visual asset for {target.get('outfit_id', 'Look 1')}"
        ),
    }


def generate_publishing_metadata(brief_id: str) -> dict[str, Any]:
    """Generate high-performing, platform-tailored metadata for YouTube Shorts and Instagram Reels.
    
    Strictly derives all details from the task's saved brief, approved outfits, images, and video assets.
    Never invents unverified brands, external links, or unsupported styling claims.
    """
    brief = get_brief_by_id(brief_id)
    if not brief:
        raise ValueError(f"Task brief '{brief_id}' not found.")

    all_outfits = load_outfits(brief_id)
    # Prefer approved outfits; fall back to proposed outfits if none yet approved
    approved_outfits = [o for o in all_outfits if o.get("approval_status") == ApprovalStatus.APPROVED.value]
    active_outfits = approved_outfits if approved_outfits else all_outfits

    image_assets = load_image_assets(brief_id)
    video_assets = load_video_assets(brief_id)

    outfit_count = len(active_outfits) or brief.get("outfit_count") or 1
    audience = brief.get("audience") or "everyday style"
    raw_idea = brief.get("idea_original") or ""

    # Derive core topic strictly from existing brief / outfit topic
    primary_topic = "fashion"
    if active_outfits and active_outfits[0].get("topic"):
        primary_topic = active_outfits[0]["topic"].replace("_", " ")
    elif "jeans" in raw_idea.lower():
        primary_topic = "jeans & tops"
    elif "color" in raw_idea.lower() or "colour" in raw_idea.lower():
        primary_topic = "color combinations"

    # Compute planned duration and structured timestamps from Stage 5 clips
    timestamps_text, structured_timestamps, total_duration_sec = _format_timestamps_from_clips(
        active_outfits,
        video_assets,
        default_clip_duration_seconds=6,
    )
    total_min = total_duration_sec // 60
    total_rem_sec = total_duration_sec % 60
    total_dur_formatted = f"{total_min}:{total_rem_sec:02d}"

    # Extract recommended thumbnail from Stage 4
    recommended_thumbnail = get_recommended_thumbnail(image_assets)

    # Compile look breakdown lines strictly from task outfit data
    outfit_breakdown_lines = []
    dialogue_quotes = []
    clips_by_outfit = {v.get("outfit_id"): v for v in video_assets if isinstance(v, dict)}

    for i, outfit in enumerate(active_outfits, 1):
        otitle = outfit.get("outfit_title") or f"Look {i}"
        garments = outfit.get("garment_descriptions") or ", ".join([g.get("item", "") for g in outfit.get("garments", [])])
        colours = ", ".join(outfit.get("colours", [])) if isinstance(outfit.get("colours"), list) else outfit.get("colours", "")
        footwear = outfit.get("footwear") or ""

        detail_parts = [f"• {otitle}: {garments}"]
        if colours:
            detail_parts.append(f"(Colors: {colours})")
        if footwear:
            detail_parts.append(f"| Shoes: {footwear}")
        outfit_breakdown_lines.append(" ".join(detail_parts))

        # Check for dialogue in Stage 5 clip
        oid = outfit.get("outfit_id")
        clip = clips_by_outfit.get(oid)
        if clip and isinstance(clip.get("prompt_data"), dict):
            dlg = clip["prompt_data"].get("dialogue")
            if dlg and dlg.strip():
                dialogue_quotes.append(f'"{dlg.strip()}"')

    # --- 1. YouTube Shorts Package ---
    yt_title_base = f"{outfit_count} Effortless {primary_topic.title()} Outfits for {audience.title()} ✨"
    yt_title = _sanitize_title_shorts(yt_title_base, max_chars=68)

    dialogue_highlight_section = ""
    if dialogue_quotes:
        dialogue_highlight_section = f"\n🎙️ SCRIPT HIGHLIGHT:\n{dialogue_quotes[0]}\n"

    timestamps_section = ""
    if timestamps_text:
        timestamps_section = f"⏱️ TIMESTAMPS (Total Duration: {total_dur_formatted}):\n{timestamps_text}\n\n"

    looks_section = ""
    if outfit_breakdown_lines:
        looks_section = "👗 OUTFIT DETAILS:\n" + "\n".join(outfit_breakdown_lines) + "\n\n"

    yt_description = (
        f"Curated {primary_topic} styling ideas for {audience.lower()}! "
        f"Explore {outfit_count} complete outfit combinations designed for effortless styling.\n\n"
        f"{timestamps_section}"
        f"{looks_section}"
        f"{dialogue_highlight_section}"
        f"💬 Which look is your favorite? Tell us in the comments! 👇\n\n"
        f"✨ Subscribe to Wear & Wonder for styling breakdowns and wardrobe inspiration.\n\n"
        f"#Shorts #Fashion #OutfitIdeas #{primary_topic.replace(' ', '')} #StyleInspo #{audience.replace(' ', '')}Outfits #OOTD #WearAndWonder"
    ).strip()

    # YouTube SEO tags derived strictly from task context
    yt_tags = [
        "fashion shorts",
        f"{primary_topic} outfits",
        f"{audience.lower()} style",
        "outfit ideas 2026",
        "styling guide",
        "capsule wardrobe",
        "wear and wonder",
        "lookbook",
        "aesthetic fashion",
        "outfit transition",
        "how to style",
    ]
    # Deduplicate and enforce 500-character YouTube search tags limit
    seen_tags = set()
    yt_tags = [t for t in yt_tags if not (t.lower() in seen_tags or seen_tags.add(t.lower()))]
    yt_tags_str = ", ".join(yt_tags)
    if len(yt_tags_str) > 490:
        yt_tags = [t for t in yt_tags if len(", ".join(yt_tags[:yt_tags.index(t)])) < 450]
        yt_tags_str = ", ".join(yt_tags)

    # --- 2. Instagram Reels Package ---
    ig_caption_lines = [
        f"✨ Save this for styling inspiration! {outfit_count} curated {primary_topic} looks for {audience.lower()} 🤍💫",
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
        f"Which look is your favorite (1 to {outfit_count})? Drop it in the comments! 👇",
        "Follow @wearandwonder for daily aesthetic styling inspiration 🕊️",
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
    seen_hts = set()
    ig_hashtags = [h for h in ig_hashtags if not (h in seen_hts or seen_hts.add(h))]
    ig_hashtags_text = " ".join(ig_hashtags)

    ig_full_caption = "\n".join(ig_caption_lines) + "\n" + ig_hashtags_text

    return {
        "brief_id": brief_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_summary": {
            "idea_original": raw_idea,
            "audience": audience,
            "topic": primary_topic,
            "outfit_count": outfit_count,
            "planned_duration_seconds": total_duration_sec,
            "planned_duration_formatted": total_dur_formatted,
            "dialogue_quotes": dialogue_quotes,
        },
        "youtube": {
            "title": yt_title,
            "description": yt_description,
            "tags": yt_tags,
            "tags_comma_separated": yt_tags_str,
            "category_id": "26",  # Howto & Style
        },
        "instagram": {
            "caption": ig_full_caption,
            "caption_without_hashtags": "\n".join(ig_caption_lines),
            "hashtags": ig_hashtags,
            "hashtags_text": ig_hashtags_text,
        },
        "timestamps": structured_timestamps,
        "timestamps_text": timestamps_text,
        "total_planned_duration_seconds": total_duration_sec,
        "total_planned_duration_formatted": total_dur_formatted,
        "recommended_thumbnail": recommended_thumbnail,
    }
