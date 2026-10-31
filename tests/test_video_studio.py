"""Unit tests for Stage 5: Video Prompts, Dialogue & Dual-Model Positioning, and Clip Approval."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.approval_workflow import ApprovalStatus, get_workflow_prerequisites
from app.storage import (
    load_video_assets,
    save_image_assets,
    save_or_update_brief,
    save_outfits,
)
from app.video_generation.video_prompt_builder import build_video_prompt_for_outfit
from app.video_generation.video_service import (
    approve_video_clip,
    import_generated_video,
    prepare_video_prompts,
    reject_video_clip,
)


class TestVideoStudio(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_data_dir = Path(self.temp_dir.name)
        self.brief_id = "test-brief-vid-01"
        self.mock_brief = {
            "brief_id": self.brief_id,
            "idea_original": "Create six jeans and top combinations for college girls",
            "requested_characters": ["WW-CHAR-01", "WW-CHAR-02"],
            "research_status": "APPROVED",
            "outfit_approval": "APPROVED",
        }
        self.mock_outfit = {
            "outfit_id": "OUTFIT-01",
            "brief_id": self.brief_id,
            "assigned_character_id": "WW-CHAR-01",
            "outfit_title": "Relaxed Straight Denim and White Tee",
            "garments": [
                {"type": "Bottom", "item": "Straight leg jeans", "color": "Light blue"},
                {"type": "Top", "item": "Fitted baby tee", "color": "White"},
            ],
            "garment_descriptions": "Light blue straight jeans with clean white baby tee.",
            "colours": ["Light Blue", "White"],
            "footwear": "White retro sneakers",
            "accessories": "Canvas tote",
            "approval_status": "APPROVED",
        }
        self.mock_image_asset = {
            "image_id": "IMG-01",
            "brief_id": self.brief_id,
            "outfit_id": "OUTFIT-01",
            "character_id": "WW-CHAR-01",
            "file_path": "assets/generated_images/test.png",
            "approval_status": "APPROVED",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_video_prompt_solo_character(self):
        prompt_data = build_video_prompt_for_outfit(
            outfit=self.mock_outfit,
            image_asset=self.mock_image_asset,
            clip_index=1,
            dual_character_id=None,
        )
        self.assertEqual(prompt_data["clip_id"], "CLIP-01")
        self.assertIn("Center frame", prompt_data["character_position"])
        self.assertIn("Look 1", prompt_data["dialogue"])
        self.assertEqual(prompt_data["duration_seconds"], 6)
        self.assertEqual(prompt_data["aspect_ratio"], "9:16")
        self.assertIn("lip-sync", prompt_data["lip_sync_instructions"].lower())

    def test_build_video_prompt_dual_character(self):
        prompt_data = build_video_prompt_for_outfit(
            outfit=self.mock_outfit,
            image_asset=self.mock_image_asset,
            clip_index=1,
            dual_character_id="WW-CHAR-02",
        )
        self.assertIn("Left frame", prompt_data["character_position"])
        self.assertIn("Right frame", prompt_data["character_position"])
        self.assertIn("remains silent", prompt_data["speaker_identity"])
        self.assertEqual(prompt_data["dual_character_id"], "WW-CHAR-02")

    def test_cannot_prepare_video_prompts_if_images_unapproved(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [self.mock_outfit])

            unapproved_img = dict(self.mock_image_asset)
            unapproved_img["approval_status"] = "PENDING"
            save_image_assets(self.brief_id, [unapproved_img])

            with self.assertRaises(ValueError) as ctx:
                prepare_video_prompts(self.brief_id)
            self.assertIn("do not have an approved image yet", str(ctx.exception))

    def test_prepare_video_prompts_import_and_approve_clip(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.VIDEO_ASSETS_FILE", self.test_data_dir / "video_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
            patch("app.video_generation.video_service.GENERATED_VIDEOS_DIR", self.test_data_dir / "videos"),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [self.mock_outfit])
            save_image_assets(self.brief_id, [self.mock_image_asset])

            # 1. Prepare video prompts
            prompts = prepare_video_prompts(self.brief_id)
            self.assertEqual(len(prompts), 1)
            self.assertEqual(prompts[0]["clip_id"], "CLIP-01")
            self.assertEqual(prompts[0]["approval_status"], "PENDING")

            # 2. Cannot approve before clip file is imported
            with self.assertRaises(ValueError):
                approve_video_clip(self.brief_id, "CLIP-01")

            # 3. Import fake video clip
            fake_mp4 = b"\x00\x00\x00\x18ftypmp42fakevideobytes"
            imported = import_generated_video(
                brief_id=self.brief_id,
                clip_id="CLIP-01",
                video_bytes=fake_mp4,
                file_extension=".mp4",
            )
            self.assertIsNotNone(imported["file_path"])
            self.assertEqual(imported["approval_status"], "PENDING")

            # 4. Approve clip
            approved = approve_video_clip(self.brief_id, "CLIP-01")
            self.assertEqual(approved["approval_status"], ApprovalStatus.APPROVED.value)

            # 5. Check prerequisites: should now be ready for Stage 6!
            prereqs = get_workflow_prerequisites(self.brief_id)
            self.assertTrue(prereqs["stage_6_ready"])


if __name__ == "__main__":
    unittest.main()
