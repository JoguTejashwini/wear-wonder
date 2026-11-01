"""Unit tests for Stage 4: Image Prompts, Character Fidelity, Upload, and Visual Verification."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.approval_workflow import ApprovalStatus
from app.image_generation.image_service import (
    approve_image,
    configure_dual_model_image_look,
    import_generated_image,
    prepare_image_prompts,
    reject_image,
    update_image_visual_description,
)
from app.image_generation.prompt_builder import (
    build_dual_model_image_prompt,
    build_image_prompt_for_outfit,
    get_verified_character_profile,
)
from app.storage import (
    load_image_assets,
    load_video_assets,
    save_or_update_brief,
    save_outfits,
    save_video_assets,
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

    def test_prepare_prompts_initializes_visual_baseline(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [self.mock_outfit])

            assets = prepare_image_prompts(self.brief_id)
            self.assertEqual(len(assets), 1)
            asset = assets[0]
            self.assertEqual(asset["prompt_version"], 1)
            self.assertIn("visual_description", asset)
            vd = asset["visual_description"]
            self.assertIn("Light blue", vd["clothing"])
            self.assertIn("White retro sneakers", vd["footwear"])
            self.assertIn("natural black", vd["hairstyle"].lower())

    def test_import_image_and_update_visual_description(self):
        img_dir = self.test_data_dir / "images"
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
            patch("app.image_generation.image_service.GENERATED_IMAGES_DIR", img_dir),
            patch("app.image_generation.image_service.PROJECT_DIR", self.test_data_dir),
            patch("app.approval_workflow.PROJECT_DIR", self.test_data_dir),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [self.mock_outfit])
            prepare_image_prompts(self.brief_id)

            # 1. Approval fails before file upload
            with self.assertRaises(ValueError) as ctx:
                approve_image(self.brief_id, "IMG-01")
            self.assertIn("Upload the actual generated image file first", str(ctx.exception))

            # 2. Upload image file
            fake_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakedata"
            imported = import_generated_image(
                brief_id=self.brief_id,
                image_id="IMG-01",
                image_bytes=fake_bytes,
                file_extension=".png",
            )
            self.assertIsNotNone(imported["file_path"])
            self.assertEqual(imported["provider"], "CHATGPT_UPLOAD")
            self.assertEqual(imported["approval_status"], "PENDING")

            # 3. Update visual description
            custom_vd = {
                "clothing": "Vintage washed straight denim and ribbed baby tee",
                "colours": "Washed light blue and crisp white",
                "fit": "High rise straight cut",
                "footwear": "White court sneakers with grey trim",
                "accessories": "Ecru canvas tote bag",
                "hairstyle": "Shoulder-length black hair parted neatly",
                "background": "Sunlit college campus courtyard",
                "pose": "Walking forward smiling naturally",
            }
            updated = update_image_visual_description(self.brief_id, "IMG-01", custom_vd)
            self.assertEqual(updated["visual_description"]["clothing"], "Vintage washed straight denim and ribbed baby tee")

            # 4. Now approve image
            approved = approve_image(self.brief_id, "IMG-01")
            self.assertEqual(approved["approval_status"], ApprovalStatus.APPROVED.value)

    def test_reupload_increments_version_and_invalidates_downstream_video(self):
        img_dir = self.test_data_dir / "images"
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.VIDEO_ASSETS_FILE", self.test_data_dir / "video_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
            patch("app.image_generation.image_service.GENERATED_IMAGES_DIR", img_dir),
            patch("app.image_generation.image_service.PROJECT_DIR", self.test_data_dir),
            patch("app.approval_workflow.PROJECT_DIR", self.test_data_dir),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [self.mock_outfit])
            prepare_image_prompts(self.brief_id)

            # Upload initial image (v1)
            import_generated_image(
                brief_id=self.brief_id,
                image_id="IMG-01",
                image_bytes=b"fake_v1_bytes",
                file_extension=".png",
            )
            approve_image(self.brief_id, "IMG-01")

            # Simulate an existing downstream video prompt in Stage 5
            mock_video = {
                "clip_id": "CLIP-01",
                "brief_id": self.brief_id,
                "outfit_id": "OUTFIT-01",
                "approved_image_id": "IMG-01",
                "character_id": "WW-CHAR-01",
                "approval_status": "APPROVED",
                "is_outdated": False,
            }
            save_video_assets(self.brief_id, [mock_video])

            # Re-upload a replacement image for the same outfit
            reuploaded = import_generated_image(
                brief_id=self.brief_id,
                image_id="IMG-01",
                image_bytes=b"fake_v2_bytes",
                file_extension=".png",
            )
            self.assertEqual(reuploaded["prompt_version"], 2)
            self.assertEqual(reuploaded["approval_status"], "PENDING")

            # Verify downstream video prompt is marked outdated and reset to PENDING
            vids = load_video_assets(self.brief_id)
            self.assertEqual(len(vids), 1)
            self.assertTrue(vids[0]["is_outdated"])
            self.assertEqual(vids[0]["approval_status"], "PENDING")


    def test_build_dual_model_image_prompt_wardrobe_setting(self):
        outfit2 = dict(self.mock_outfit)
        outfit2["outfit_id"] = "OUTFIT-02"
        outfit2["assigned_character_id"] = "WW-CHAR-02"
        outfit2["outfit_title"] = "Tailored Blazer and Linen Trousers"
        outfit2["garment_descriptions"] = "Charcoal oversized blazer and beige linen trousers."
        outfit2["colours"] = ["Charcoal", "Beige"]

        prompt_data = build_dual_model_image_prompt(
            outfit_1=self.mock_outfit,
            character_id_1="WW-CHAR-01",
            character_id_2="WW-CHAR-02",
            outfit_2=outfit2,
        )

        self.assertTrue(prompt_data["is_dual_model"])
        self.assertEqual(prompt_data["character_id"], "WW-CHAR-01")
        self.assertEqual(prompt_data["dual_character_id"], "WW-CHAR-02")
        self.assertIn("WW-CHAR-01", prompt_data["prompt_text"])
        self.assertIn("WW-CHAR-02", prompt_data["prompt_text"])
        self.assertIn("Model 1 (Left)", prompt_data["prompt_text"])
        self.assertIn("Model 2 (Right)", prompt_data["prompt_text"])

        # Check stylish wardrobe background
        self.assertIn("wardrobe and dressing room", prompt_data["prompt_text"].lower())
        self.assertIn("vanity mirror", prompt_data["prompt_text"].lower())

        # Check positions and expressions
        self.assertIn("confident", prompt_data["prompt_text"].lower())
        self.assertIn("smile", prompt_data["prompt_text"].lower())

        # Check references for both models
        self.assertTrue(prompt_data["reference_image"].endswith(".png"))
        self.assertTrue(prompt_data["reference_image_2"].endswith(".png"))

        # Check ChatGPT prompt explicitly tells user to attach BOTH references
        chat_prompt = prompt_data["chatgpt_prompt"]
        self.assertIn("TWO attached master model reference images", chat_prompt)
        self.assertIn("Model 1", chat_prompt)
        self.assertIn("Model 2", chat_prompt)

    def test_configure_dual_model_image_look(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
        ):
            save_or_update_brief(self.mock_brief)
            outfit2 = dict(self.mock_outfit)
            outfit2["outfit_id"] = "OUTFIT-02"
            outfit2["assigned_character_id"] = "WW-CHAR-02"
            save_outfits(self.brief_id, [self.mock_outfit, outfit2])

            prepare_image_prompts(self.brief_id)

            dual_look = configure_dual_model_image_look(
                brief_id=self.brief_id,
                image_id="IMG-01",
                character_id_1="WW-CHAR-01",
                character_id_2="WW-CHAR-02",
                outfit_id_1="OUTFIT-01",
                outfit_id_2="OUTFIT-02",
            )

            self.assertTrue(dual_look["is_dual_model"])
            self.assertEqual(dual_look["character_id"], "WW-CHAR-01")
            self.assertEqual(dual_look["dual_character_id"], "WW-CHAR-02")
            self.assertIn("wardrobe and dressing room", dual_look["visual_description"]["background"].lower())
            self.assertIn("Model 1", dual_look["visual_description"]["positions"])
            self.assertIn("Model 2", dual_look["visual_description"]["positions"])


if __name__ == "__main__":
    unittest.main()
