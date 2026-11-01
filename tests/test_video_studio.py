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
    save_video_assets,
)
from app.video_generation.video_prompt_builder import build_video_prompt_for_outfit
from app.video_generation.video_service import (
    approve_video_clip,
    import_generated_video,
    prepare_video_prompts,
    regenerate_single_video_prompt,
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

        # Create a real test image file on disk in temp dir
        self.fake_img_path = self.test_data_dir / "test_outfit.png"
        self.fake_img_path.write_bytes(b"\x89PNG\r\n\x1a\nfakeimagebytes")

        self.mock_image_asset = {
            "image_id": "IMG-01",
            "brief_id": self.brief_id,
            "outfit_id": "OUTFIT-01",
            "character_id": "WW-CHAR-01",
            "file_path": "test_outfit.png",
            "approval_status": "APPROVED",
            "visual_description": {
                "clothing": "Light blue straight jeans and white baby tee",
                "colours": "Light blue, white",
                "fit": "High-rise straight",
                "footwear": "White retro sneakers",
                "accessories": "Canvas tote",
                "hairstyle": "WW-CHAR-01 signature neat hair",
                "background": "Minimal studio setting",
                "pose": "Standing facing forward",
            },
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
        self.assertEqual(prompt_data["start_frame_image"], "test_outfit.png")
        self.assertIn("test_outfit.png", prompt_data["master_prompt"])

    def test_build_video_prompt_dual_character(self):
        prompt_data = build_video_prompt_for_outfit(
            outfit=self.mock_outfit,
            image_asset=self.mock_image_asset,
            clip_index=1,
            dual_character_id="WW-CHAR-02",
        )
        self.assertIn("Left frame", prompt_data["character_position"])
        self.assertIn("Right frame", prompt_data["character_position"])

        # Model 1 must be the only speaker
        self.assertIn("ONLY speaker", prompt_data["speaker_identity"])
        self.assertIn("Model 1", prompt_data["lip_sync_instructions"])

        # Model 2 must remain silent with lips closed and zero mouth movement
        self.assertIn("remains silent", prompt_data["speaker_identity"])
        self.assertIn("lips closed", prompt_data["speaker_identity"])
        self.assertIn("NO mouth movement", prompt_data["speaker_identity"])
        self.assertIn("ZERO mouth movement", prompt_data["lip_sync_instructions"])

        # Both identities preserved
        self.assertEqual(prompt_data["dual_character_id"], "WW-CHAR-02")
        self.assertIn("WW-CHAR-01", prompt_data["master_prompt"])
        self.assertIn("WW-CHAR-02", prompt_data["master_prompt"])

        # Wardrobe background preserved
        self.assertIn("wardrobe", prompt_data["background"].lower())

        # Negative constraints prevent Model 2 from speaking or moving lips
        self.assertIn("Model 2 speaking", prompt_data["negative_constraints"])
        self.assertIn("Model 2 moving mouth", prompt_data["negative_constraints"])

    def test_cannot_prepare_video_prompts_if_images_unapproved_or_missing_file(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.video_generation.video_service.PROJECT_DIR", self.test_data_dir),
            patch("app.approval_workflow.PROJECT_DIR", self.test_data_dir),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [self.mock_outfit])

            # Case 1: Image unapproved
            unapproved_img = dict(self.mock_image_asset)
            unapproved_img["approval_status"] = "PENDING"
            save_image_assets(self.brief_id, [unapproved_img])

            with self.assertRaises(ValueError) as ctx:
                prepare_video_prompts(self.brief_id)
            self.assertIn("do not have an approved image file on disk", str(ctx.exception))

            # Case 2: Image approved but file missing on disk
            missing_img = dict(self.mock_image_asset)
            missing_img["file_path"] = "non_existent_file.png"
            missing_img["approval_status"] = "APPROVED"
            save_image_assets(self.brief_id, [missing_img])

            with self.assertRaises(ValueError) as ctx:
                prepare_video_prompts(self.brief_id)
            self.assertIn("image file not found on disk", str(ctx.exception))

    def test_prepare_video_prompts_import_and_approve_clip(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.VIDEO_ASSETS_FILE", self.test_data_dir / "video_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
            patch("app.video_generation.video_service.GENERATED_VIDEOS_DIR", self.test_data_dir / "videos"),
            patch("app.video_generation.video_service.PROJECT_DIR", self.test_data_dir),
            patch("app.approval_workflow.PROJECT_DIR", self.test_data_dir),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [self.mock_outfit])
            save_image_assets(self.brief_id, [self.mock_image_asset])

            # 1. Prepare video prompts
            prompts = prepare_video_prompts(self.brief_id)
            self.assertEqual(len(prompts), 1)
            self.assertEqual(prompts[0]["clip_id"], "CLIP-01")
            self.assertEqual(prompts[0]["approval_status"], "PENDING")
            self.assertEqual(prompts[0]["prompt_data"]["start_frame_image"], "test_outfit.png")

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

    def test_regenerate_single_video_prompt_after_image_update(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.VIDEO_ASSETS_FILE", self.test_data_dir / "video_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
            patch("app.video_generation.video_service.PROJECT_DIR", self.test_data_dir),
            patch("app.approval_workflow.PROJECT_DIR", self.test_data_dir),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [self.mock_outfit])
            save_image_assets(self.brief_id, [self.mock_image_asset])

            prepare_video_prompts(self.brief_id)

            # Now update the visual description of the approved image asset
            updated_image = dict(self.mock_image_asset)
            updated_image["visual_description"]["clothing"] = "Updated denim jacket with high waist trousers"
            save_image_assets(self.brief_id, [updated_image])

            # Regenerate single prompt
            realigned = regenerate_single_video_prompt(self.brief_id, "CLIP-01")
            self.assertFalse(realigned.get("is_outdated", False))
            self.assertEqual(realigned["approval_status"], "PENDING")
            self.assertIn("Updated denim jacket with high waist trousers", realigned["prompt_data"]["master_prompt"])


if __name__ == "__main__":
    unittest.main()
