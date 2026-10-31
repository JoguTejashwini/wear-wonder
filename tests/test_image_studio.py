"""Unit tests for Stage 4: Image Prompts, Character Fidelity, and Manual Handoff."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.approval_workflow import ApprovalStatus
from app.image_generation.image_service import (
    approve_image,
    import_generated_image,
    prepare_image_prompts,
    reject_image,
)
from app.image_generation.prompt_builder import (
    build_image_prompt_for_outfit,
    get_verified_character_profile,
)
from app.storage import (
    load_image_assets,
    save_or_update_brief,
    save_outfits,
)


class TestImageStudio(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_data_dir = Path(self.temp_dir.name)
        self.brief_id = "test-brief-img-01"
        self.mock_brief = {
            "brief_id": self.brief_id,
            "idea_original": "Create six jeans and top combinations for college girls",
            "requested_characters": ["WW-CHAR-01"],
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
            "fabrics_and_textures": "Rigid cotton denim and ribbed cotton",
            "fit_and_silhouette": "High-rise straight silhouette",
            "footwear": "White retro sneakers",
            "accessories": "Canvas tote",
            "occasion": "Campus daytime",
            "approval_status": "APPROVED",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_verified_character_profile_loads_real_model(self):
        profile = get_verified_character_profile("WW-CHAR-01")
        self.assertEqual(profile["character_id"], "WW-CHAR-01")
        self.assertIn("Female Model 01", profile["display_name"])
        self.assertIn("natural black", profile["hair_rules"].lower())
        self.assertTrue(profile["reference_image_path"].endswith(".png"))

    def test_verified_character_profile_rejects_unknown(self):
        with self.assertRaises(ValueError):
            get_verified_character_profile("UNKNOWN-CHAR-99")

    def test_build_image_prompt_for_outfit(self):
        prompt_data = build_image_prompt_for_outfit(self.mock_outfit, "WW-CHAR-01")
        self.assertEqual(prompt_data["character_id"], "WW-CHAR-01")
        self.assertEqual(prompt_data["aspect_ratio"], "9:16")

        p_text = prompt_data["prompt_text"]
        self.assertIn("WW-CHAR-01", p_text)
        self.assertIn("Light blue straight jeans", p_text)
        self.assertIn("White retro sneakers", p_text)
        self.assertIn("9:16", p_text)

        neg = prompt_data["negative_prompt"]
        self.assertIn("deformed", neg)
        self.assertIn("plastic skin", neg)

    def test_cannot_prepare_prompts_if_outfits_unapproved(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
        ):
            save_or_update_brief(self.mock_brief)
            unapproved = dict(self.mock_outfit)
            unapproved["approval_status"] = "PENDING"
            save_outfits(self.brief_id, [unapproved])

            with self.assertRaises(ValueError) as ctx:
                prepare_image_prompts(self.brief_id)
            self.assertIn("No approved outfits found", str(ctx.exception))

    def test_prepare_prompts_and_import_generated_image(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
            patch("app.image_generation.image_service.GENERATED_IMAGES_DIR", self.test_data_dir / "images"),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [self.mock_outfit])

            # 1. Prepare prompt
            assets = prepare_image_prompts(self.brief_id)
            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0]["approval_status"], "PENDING")
            self.assertIsNone(assets[0]["file_path"])

            # 2. Cannot approve before image file is imported
            with self.assertRaises(ValueError):
                approve_image(self.brief_id, "IMG-01")

            # 3. Import image bytes
            fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakeimagebytes"
            imported = import_generated_image(
                brief_id=self.brief_id,
                image_id="IMG-01",
                image_bytes=fake_png,
                file_extension=".png",
            )
            self.assertIsNotNone(imported["file_path"])
            self.assertEqual(imported["approval_status"], "PENDING")

            # 4. Now approve
            approved = approve_image(self.brief_id, "IMG-01")
            self.assertEqual(approved["approval_status"], ApprovalStatus.APPROVED.value)


if __name__ == "__main__":
    unittest.main()
