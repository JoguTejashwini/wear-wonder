"""Unit tests for Stage 6 Publishing & Scheduling Studio in Wear & Wonder."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import app.storage as storage
from app.approval_workflow import (
    ApprovalStatus,
    WorkflowStage,
    get_workflow_prerequisites,
    can_proceed_to_stage,
)
from app.publishing.metadata_generator import (
    generate_publishing_metadata,
    _sanitize_title_shorts,
    _format_timestamps,
)
from app.publishing.youtube_publisher import (
    check_youtube_auth_status,
    publish_to_youtube,
)
from app.publishing.instagram_publisher import (
    check_instagram_auth_status,
    publish_to_instagram,
)
from app.publishing.publishing_service import (
    get_or_create_publishing_record,
    import_assembled_video,
    import_custom_thumbnail,
    set_master_image_as_thumbnail,
    update_publishing_metadata,
    refresh_publishing_metadata,
    approve_and_schedule_video,
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

        self.brief_id = "test-brief-pub-01"
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

    def test_generate_publishing_metadata(self):
        """Verify automated generation of YouTube Shorts and Instagram Reels metadata with multi-look timestamps."""
        metadata = generate_publishing_metadata(self.brief_id, clip_duration_seconds=12)

        # YouTube Shorts tests
        yt = metadata["youtube"]
        self.assertIn("#Shorts", yt["title"])
        self.assertLessEqual(len(yt["title"]), 70)
        self.assertEqual(yt["category_id"], "26")
        self.assertIn("TIMESTAMPS", yt["description"])
        self.assertIn("0:00 Look 1: Sage Green & Cream Knit", yt["description"])
        self.assertIn("0:12 Look 2: Cobalt Blue & Crisp White", yt["description"])
        self.assertIn("0:24 Look 3: Mocha Brown & Powder Blue", yt["description"])
        self.assertLessEqual(len(yt["tags_comma_separated"]), 500)

        # Instagram Reels tests
        ig = metadata["instagram"]
        self.assertIn("Save this for styling inspo", ig["caption"])
        self.assertIn("Look 1", ig["caption"])
        self.assertIn("Look 2", ig["caption"])
        self.assertIn("Look 3", ig["caption"])
        self.assertIn("#reelsfashion", ig["hashtags"])
        self.assertIn("#wearandwonder", ig["hashtags"])
        self.assertTrue(len(ig["hashtags"]) >= 10)

        # Timestamps structure
        ts = metadata["timestamps"]
        self.assertEqual(len(ts), 3)
        self.assertEqual(ts[0]["timestamp"], "0:00")
        self.assertEqual(ts[1]["timestamp"], "0:12")

    def test_import_assembled_video(self):
        """Verify uploading assembled video writes to disk and updates publishing record."""
        fake_video_bytes = b"\x00\x00\x00\x1cftypisom" + b"A" * 1024
        record = import_assembled_video(self.brief_id, fake_video_bytes, "final_assembled_shorts.mp4")

        self.assertIsNotNone(record["video_file_path"])
        self.assertEqual(record["video_filename"], "final_assembled_shorts.mp4")
        self.assertEqual(record["video_filesize"], len(fake_video_bytes))

        # Check file exists on disk
        video_full_path = storage.PROJECT_DIR / record["video_file_path"]
        self.assertTrue(video_full_path.is_file())
        self.assertEqual(video_full_path.stat().st_size, len(fake_video_bytes))

    def test_reject_invalid_video_upload(self):
        """Reject empty video bytes or invalid file formats."""
        with self.assertRaises(ValueError):
            import_assembled_video(self.brief_id, b"", "empty.mp4")

        with self.assertRaises(ValueError):
            import_assembled_video(self.brief_id, b"some content", "document.pdf")

    def test_import_custom_thumbnail(self):
        """Verify custom thumbnail upload and persistence."""
        fake_thumb_bytes = b"\x89PNG\r\n\x1a\n" + b"P" * 512
        record = import_custom_thumbnail(self.brief_id, fake_thumb_bytes, "custom_cover.png")

        self.assertIsNotNone(record["thumbnail_file_path"])
        self.assertEqual(record["thumbnail_source"], "CUSTOM_UPLOAD")
        thumb_full_path = storage.PROJECT_DIR / record["thumbnail_file_path"]
        self.assertTrue(thumb_full_path.is_file())

    def test_set_master_image_as_thumbnail(self):
        """Verify selecting an approved Stage 4 master image as publishing thumbnail."""
        img_file = Path(self.test_dir) / "stage4_look1.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"X" * 256)
        rel_img_path = str(img_file.relative_to(storage.PROJECT_DIR)) if img_file.is_relative_to(storage.PROJECT_DIR) else str(img_file)

        sample_images = [
            {
                "image_id": "IMG-01",
                "brief_id": self.brief_id,
                "outfit_id": "OUTFIT-01",
                "character_id": "WW-CHAR-01",
                "file_path": str(img_file),
                "approval_status": "APPROVED",
            }
        ]
        storage.save_image_assets(self.brief_id, sample_images)

        record = set_master_image_as_thumbnail(self.brief_id, image_id="IMG-01")
        self.assertEqual(record["thumbnail_file_path"], str(img_file))
        self.assertEqual(record["thumbnail_source"], "STAGE_4_IMG-01")

    def test_mandatory_approval_gate_fails_without_video(self):
        """Approve & Schedule must fail if no video has been uploaded."""
        with self.assertRaises(ValueError):
            approve_and_schedule_video(
                brief_id=self.brief_id,
                platforms=["youtube", "instagram"],
                user_name="Curator",
                mock_mode=True,
            )

    def test_approve_and_schedule_video_immediate_mock(self):
        """Verify end-to-end immediate publication dispatch with live URL return."""
        fake_video_bytes = b"\x00\x00\x00\x1cftypisom" + b"V" * 500
        import_assembled_video(self.brief_id, fake_video_bytes, "assembled_outfit_reel.mp4")

        record = approve_and_schedule_video(
            brief_id=self.brief_id,
            platforms=["youtube", "instagram"],
            privacy_status="public",
            user_name="Lead Editor",
            mock_mode=True,
        )

        self.assertEqual(record["status"], "PUBLISHED")
        # YouTube verification
        yt_stat = record["platforms_status"]["youtube"]
        self.assertEqual(yt_stat["status"], "PUBLISHED")
        self.assertTrue(yt_stat["url"].startswith("https://youtube.com/shorts/"))

        # Instagram verification
        ig_stat = record["platforms_status"]["instagram"]
        self.assertEqual(ig_stat["status"], "PUBLISHED")
        self.assertTrue(ig_stat["permalink"].startswith("https://www.instagram.com/reel/"))

        # Audit trail verification
        audit = storage.load_audit_events(self.brief_id)
        self.assertTrue(any(ev["action"] == "VIDEO_PUBLISHED" for ev in audit))

    def test_approve_and_schedule_video_scheduled_mock(self):
        """Verify scheduling publication for a future ISO timestamp."""
        fake_video_bytes = b"\x00\x00\x00\x1cftypisom" + b"S" * 500
        import_assembled_video(self.brief_id, fake_video_bytes, "scheduled_short.mp4")

        future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        record = approve_and_schedule_video(
            brief_id=self.brief_id,
            platforms=["youtube", "instagram"],
            scheduled_time_iso=future_time,
            privacy_status="private",
            user_name="Lead Editor",
            mock_mode=True,
        )

        self.assertEqual(record["status"], "SCHEDULED")
        self.assertEqual(record["scheduling"]["scheduled_time_iso"], future_time)
        self.assertEqual(record["platforms_status"]["youtube"]["status"], "SCHEDULED")
        self.assertEqual(record["platforms_status"]["instagram"]["status"], "SCHEDULED")

    def test_record_manual_publication(self):
        """Verify Mode B Zero-Setup manual publication recording for user uploads."""
        record = record_manual_publication(
            brief_id=self.brief_id,
            platform="youtube",
            live_url="https://youtube.com/shorts/dQw4w9WgXcQ",
            notes="Uploaded via YouTube Studio web app",
            user_name="Solo Creator",
        )
        self.assertEqual(record["status"], "PUBLISHED")
        self.assertEqual(record["platforms_status"]["youtube"]["url"], "https://youtube.com/shorts/dQw4w9WgXcQ")
        self.assertEqual(len(record["manual_publications"]), 1)

    def test_youtube_auth_status_check(self):
        """Verify detection of YouTube credentials."""
        status = check_youtube_auth_status()
        self.assertIn("configured", status)
        self.assertIn("auth_type", status)

    def test_instagram_auth_status_check(self):
        """Verify detection of Instagram credentials."""
        status = check_instagram_auth_status()
        self.assertIn("configured", status)
        self.assertIn("auth_type", status)


if __name__ == "__main__":
    unittest.main()
