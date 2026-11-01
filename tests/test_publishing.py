"""Unit tests for Stage 6 Publishing & Metadata Studio in Wear & Wonder."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

import app.storage as storage
from app.approval_workflow import (
    ApprovalStatus,
    WorkflowStage,
    get_workflow_prerequisites,
)
from app.publishing.metadata_generator import (
    generate_publishing_metadata,
    get_recommended_thumbnail,
    _sanitize_title_shorts,
    _format_timestamps_from_clips,
)
from app.publishing.publishing_service import (
    get_or_create_publishing_record,
    refresh_publishing_metadata,
    update_publishing_metadata,
    set_recommended_thumbnail_choice,
    save_and_approve_publishing_package,
    import_assembled_video,
    import_custom_thumbnail,
    record_manual_publication,
)


class TestPublishingStudio(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_data_dir = storage.DATA_DIR
        self.orig_published_videos_dir = storage.PUBLISHED_VIDEOS_DIR
        self.orig_published_thumbnails_dir = storage.PUBLISHED_THUMBNAILS_DIR

        storage.DATA_DIR = Path(self.test_dir) / "data"
        storage.DATA_DIR.mkdir(parents=True, exist_ok=True)
        storage.RESEARCH_FILE = storage.DATA_DIR / "research.json"
        storage.OUTFITS_FILE = storage.DATA_DIR / "outfits.json"
        storage.IMAGE_ASSETS_FILE = storage.DATA_DIR / "image_assets.json"
        storage.VIDEO_ASSETS_FILE = storage.DATA_DIR / "video_assets.json"
        storage.PUBLISHING_RECORDS_FILE = storage.DATA_DIR / "publishing_records.json"
        storage.AUDIT_LOG_FILE = storage.DATA_DIR / "workflow_audit.json"

        storage.PUBLISHED_VIDEOS_DIR = Path(self.test_dir) / "assets" / "published_videos"
        storage.PUBLISHED_THUMBNAILS_DIR = Path(self.test_dir) / "assets" / "published_thumbnails"
        storage.PUBLISHED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        storage.PUBLISHED_THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

        self.brief_id = "test-task-pub-01"
        self.sample_brief = {
            "brief_id": self.brief_id,
            "idea_original": "Showcase three trendy color combinations for college girls",
            "audience": "College girls",
            "outfit_count": 3,
            "requested_characters": ["WW-CHAR-01"],
            "research_status": "APPROVED",
            "outfit_approval": "APPROVED",
        }
        storage.save_or_update_brief(self.sample_brief)

        self.sample_outfits = [
            {
                "outfit_id": "OUTFIT-01",
                "brief_id": self.brief_id,
                "topic": "colour_combinations",
                "outfit_title": "Look 1: Sage Green & Cream Knit",
                "garments": [{"type": "Top", "item": "Cream ribbed sweater"}, {"type": "Bottom", "item": "Sage pleated trousers"}],
                "garment_descriptions": "Cream knit layered with sage high-waist trousers.",
                "colours": ["Sage Green", "Cream"],
                "footwear": "Chunky white sneakers",
                "approval_status": "APPROVED",
            },
            {
                "outfit_id": "OUTFIT-02",
                "brief_id": self.brief_id,
                "topic": "colour_combinations",
                "outfit_title": "Look 2: Cobalt Blue & Crisp White",
                "garments": [{"type": "Top", "item": "Cobalt oversized blazer"}, {"type": "Bottom", "item": "White straight denim"}],
                "garment_descriptions": "Bold cobalt blue blazer over crisp white jeans.",
                "colours": ["Cobalt Blue", "Optic White"],
                "footwear": "Silver pointed flats",
                "approval_status": "APPROVED",
            },
            {
                "outfit_id": "OUTFIT-03",
                "brief_id": self.brief_id,
                "topic": "colour_combinations",
                "outfit_title": "Look 3: Mocha Brown & Powder Blue",
                "garments": [{"type": "Top", "item": "Powder blue button-down"}, {"type": "Bottom", "item": "Mocha tailored skirt"}],
                "garment_descriptions": "Mocha midi skirt paired with light powder blue poplin.",
                "colours": ["Mocha Brown", "Powder Blue"],
                "footwear": "Chocolate leather boots",
                "approval_status": "APPROVED",
            },
        ]
        storage.save_outfits(self.brief_id, self.sample_outfits)

        # Stage 5 Video clips with custom planned durations
        self.sample_clips = [
            {
                "clip_id": "CLIP-01",
                "brief_id": self.brief_id,
                "outfit_id": "OUTFIT-01",
                "prompt_data": {
                    "duration_seconds": 6,
                    "dialogue": "Fresh sage and cream tones bring a clean aesthetic to everyday classes.",
                },
                "approval_status": "APPROVED",
            },
            {
                "clip_id": "CLIP-02",
                "brief_id": self.brief_id,
                "outfit_id": "OUTFIT-02",
                "prompt_data": {
                    "duration_seconds": 8,
                    "dialogue": "Pairing electric cobalt with crisp white makes an unforgettable statement.",
                },
                "approval_status": "APPROVED",
            },
            {
                "clip_id": "CLIP-03",
                "brief_id": self.brief_id,
                "outfit_id": "OUTFIT-03",
                "prompt_data": {
                    "duration_seconds": 6,
                    "dialogue": "Soft powder blue and warm mocha brown create balanced contrast.",
                },
                "approval_status": "APPROVED",
            },
        ]
        storage.save_video_assets(self.brief_id, self.sample_clips)

        # Stage 4 Image assets
        self.sample_images = [
            {
                "image_id": "IMG-01",
                "brief_id": self.brief_id,
                "outfit_id": "OUTFIT-01",
                "character_name": "Female Model 01",
                "file_path": "assets/test_img_01.png",
                "approval_status": "APPROVED",
                "is_dual_model": False,
            },
            {
                "image_id": "IMG-02",
                "brief_id": self.brief_id,
                "outfit_id": "OUTFIT-02",
                "character_name": "Female Model 01",
                "file_path": "assets/test_img_02.png",
                "approval_status": "APPROVED",
                "is_dual_model": True,
            },
        ]
        storage.save_image_assets(self.brief_id, self.sample_images)

    def tearDown(self):
        storage.DATA_DIR = self.orig_data_dir
        storage.RESEARCH_FILE = self.orig_data_dir / "research.json"
        storage.OUTFITS_FILE = self.orig_data_dir / "outfits.json"
        storage.IMAGE_ASSETS_FILE = self.orig_data_dir / "image_assets.json"
        storage.VIDEO_ASSETS_FILE = self.orig_data_dir / "video_assets.json"
        storage.PUBLISHING_RECORDS_FILE = self.orig_data_dir / "publishing_records.json"
        storage.AUDIT_LOG_FILE = self.orig_data_dir / "workflow_audit.json"
        storage.PUBLISHED_VIDEOS_DIR = self.orig_published_videos_dir
        storage.PUBLISHED_THUMBNAILS_DIR = self.orig_published_thumbnails_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_generate_metadata_from_existing_task_data(self):
        """Verify metadata is generated strictly from the active task's brief, outfits, clips, and images."""
        meta = generate_publishing_metadata(self.brief_id)

        # 1. YouTube Shorts Package
        yt = meta["youtube"]
        self.assertIn("#Shorts", yt["title"])
        self.assertLessEqual(len(yt["title"]), 70)
        self.assertEqual(yt["category_id"], "26")
        self.assertIn("TIMESTAMPS", yt["description"])
        self.assertIn("0:00 Look 1: Sage Green & Cream Knit", yt["description"])
        self.assertIn("0:06 Look 2: Cobalt Blue & Crisp White", yt["description"])
        self.assertIn("0:14 Look 3: Mocha Brown & Powder Blue", yt["description"])
        # Dialogue from Stage 5 clips included
        self.assertIn("SCRIPT HIGHLIGHT", yt["description"])
        self.assertLessEqual(len(yt["tags_comma_separated"]), 500)

        # 2. Instagram Reels Package
        ig = meta["instagram"]
        self.assertIn("Save this for styling inspiration", ig["caption"])
        self.assertIn("Look 1", ig["caption"])
        self.assertIn("Look 2", ig["caption"])
        self.assertIn("Look 3", ig["caption"])
        self.assertIn("#reelsfashion", ig["hashtags"])
        self.assertIn("#colourcombinations", ig["hashtags"])

        # 3. Planned Duration based on Stage 5 clip durations (6 + 8 + 6 = 20s)
        self.assertEqual(meta["total_planned_duration_seconds"], 20)
        self.assertEqual(meta["total_planned_duration_formatted"], "0:20")

        # 4. Thumbnail Recommendation: prefers dual-model look image if approved
        rec_thumb = meta["recommended_thumbnail"]
        self.assertIsNotNone(rec_thumb)
        self.assertEqual(rec_thumb["image_id"], "IMG-02")
        self.assertTrue(rec_thumb["is_dual_model"])

    def test_timestamps_reflect_actual_clip_durations(self):
        """Verify timestamps accurately accumulate the duration_seconds of each outfit's clip."""
        custom_clips = [
            {"outfit_id": "OUTFIT-01", "prompt_data": {"duration_seconds": 10}},
            {"outfit_id": "OUTFIT-02", "prompt_data": {"duration_seconds": 15}},
            {"outfit_id": "OUTFIT-03", "prompt_data": {"duration_seconds": 5}},
        ]
        text, structured, total = _format_timestamps_from_clips(self.sample_outfits, custom_clips)
        self.assertEqual(total, 30)
        self.assertEqual(structured[0]["timestamp"], "0:00")
        self.assertEqual(structured[1]["timestamp"], "0:10")
        self.assertEqual(structured[2]["timestamp"], "0:25")
        self.assertIn("0:00 Look 1", text)
        self.assertIn("0:10 Look 2", text)
        self.assertIn("0:25 Look 3", text)

    def test_connect_metadata_to_correct_task(self):
        """Verify metadata generated for task A is completely isolated from task B."""
        task_b_id = "test-task-pub-02"
        storage.save_or_update_brief({
            "brief_id": task_b_id,
            "idea_original": "Six minimalist office blazer combinations for corporate women",
            "audience": "Corporate women",
            "outfit_count": 1,
            "research_status": "APPROVED",
            "outfit_approval": "APPROVED",
        })
        storage.save_outfits(task_b_id, [
            {
                "outfit_id": "OUTFIT-B1",
                "brief_id": task_b_id,
                "topic": "formal_and_office",
                "outfit_title": "Look 1: Charcoal Pinstripe Blazer",
                "garments": [{"type": "Top", "item": "Silk shirt"}, {"type": "Jacket", "item": "Charcoal blazer"}],
                "garment_descriptions": "Tailored charcoal blazer with ivory silk.",
                "colours": ["Charcoal Grey", "Ivory"],
                "approval_status": "APPROVED",
            }
        ])

        meta_a = generate_publishing_metadata(self.brief_id)
        meta_b = generate_publishing_metadata(task_b_id)

        self.assertIn("Sage Green", meta_a["youtube"]["description"])
        self.assertNotIn("Charcoal", meta_a["youtube"]["description"])

        self.assertIn("Charcoal", meta_b["youtube"]["description"])
        self.assertNotIn("Sage Green", meta_b["youtube"]["description"])
        self.assertIn("Corporate Women", meta_b["youtube"]["title"])

    def test_preserve_manual_edits_until_regeneration(self):
        """Manual edits must be preserved and only overwritten when explicitly regenerated."""
        record = get_or_create_publishing_record(self.brief_id)
        # Apply user edit
        update_publishing_metadata(
            self.brief_id,
            "youtube",
            {"title": "My Custom Edited YouTube Shorts Title #Shorts"},
        )
        updated = get_or_create_publishing_record(self.brief_id)
        self.assertEqual(updated["metadata"]["youtube"]["title"], "My Custom Edited YouTube Shorts Title #Shorts")

        # Explicit regeneration re-syncs from task data
        refreshed = refresh_publishing_metadata(self.brief_id)
        self.assertIn("Effortless", refreshed["metadata"]["youtube"]["title"])

    def test_save_and_approve_publishing_package_without_video_upload(self):
        """Verify approving and saving the publishing package requires no video upload."""
        record = get_or_create_publishing_record(self.brief_id)
        self.assertEqual(record["status"], "DRAFT")

        approved_record = save_and_approve_publishing_package(self.brief_id, user_name="Lead Curator")
        self.assertEqual(approved_record["status"], "APPROVED")
        self.assertEqual(approved_record["approved_by"], "Lead Curator")

        # Verify audit trail
        audit = storage.load_audit_events(self.brief_id)
        self.assertTrue(any(ev["action"] == "PUBLISHING_PACKAGE_APPROVED" for ev in audit))

        # Check workflow prerequisites reflect approval
        prereqs = get_workflow_prerequisites(self.brief_id)
        self.assertTrue(prereqs["publishing_approved"])

    def test_set_recommended_thumbnail_choice(self):
        """User can change the recommended thumbnail to another approved Stage 4 asset."""
        record = set_recommended_thumbnail_choice(self.brief_id, "IMG-01")
        self.assertEqual(record["recommended_thumbnail"]["image_id"], "IMG-01")
        self.assertEqual(record["recommended_thumbnail"]["character_name"], "Female Model 01")

    def test_safe_handling_of_empty_outfits(self):
        """Task with no approved outfits generates safe fallback metadata without error."""
        empty_id = "test-task-empty"
        storage.save_or_update_brief({
            "brief_id": empty_id,
            "idea_original": "Summer dresses preview",
            "audience": "Young adults",
            "outfit_count": 2,
            "research_status": "APPROVED",
        })
        meta = generate_publishing_metadata(empty_id)
        self.assertIn("#Shorts", meta["youtube"]["title"])
        self.assertEqual(meta["total_planned_duration_seconds"], 0)
        self.assertIsNone(meta["recommended_thumbnail"])


if __name__ == "__main__":
    unittest.main()
