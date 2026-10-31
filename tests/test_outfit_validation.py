"""Unit tests for Stage 3: Outfit Validation, Generation, and Editing."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.approval_workflow import ApprovalStatus
from app.storage import load_outfits, save_or_update_brief
from app.styling.outfit_generator import generate_outfit_proposals
from app.styling.outfit_service import (
    approve_all_outfits,
    approve_single_outfit,
    edit_outfit,
    reject_single_outfit,
)
from app.styling.outfit_validator import (
    VALIDATION_DIMENSIONS,
    check_outfit_distinctness,
    validate_outfit_record,
)


class TestOutfitValidation(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_data_dir = Path(self.temp_dir.name)
        self.brief_id = "test-brief-outfit-01"
        self.mock_brief = {
            "brief_id": self.brief_id,
            "idea_original": "Create six jeans and top combinations for college girls",
            "audience": "College girls",
            "outfit_count": 6,
            "requested_characters": ["WW-CHAR-01", "WW-CHAR-02"],
            "research_status": "APPROVED",
            "outfit_approval": "PENDING",
        }

        self.complete_outfit = {
            "outfit_id": "OUTFIT-01",
            "brief_id": self.brief_id,
            "topic": "jeans_and_tops",
            "outfit_title": "Relaxed Straight Denim and Baby Tee",
            "garments": [
                {"type": "Bottom", "item": "Straight leg jeans", "color": "Light blue", "fabric": "Denim", "fit": "High rise straight"},
                {"type": "Top", "item": "Fitted baby tee", "color": "White", "fabric": "Cotton", "fit": "Cropped fitted"},
            ],
            "garment_descriptions": "High rise straight jeans in vintage light wash paired with a cropped fitted baby tee.",
            "colours": ["Light Blue", "White", "Cognac"],
            "fabrics_and_textures": "Rigid denim and soft ribbed cotton",
            "fit_and_silhouette": "Fitted top with relaxed straight lower volume",
            "footwear": "Low-profile retro white sneakers",
            "accessories": "Canvas tote bag and silver jewelry",
            "occasion": "Campus daytime study",
            "season": "Spring / Autumn",
            "styling_rationale": "Balances upper-body fitted proportions with relaxed denim.",
            "approval_status": "PENDING",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validation_all_16_dimensions_present(self):
        checks, warnings, confidence = validate_outfit_record(
            self.complete_outfit,
            audience="College girls",
            master_model_ids=["WW-CHAR-01"],
        )
        self.assertEqual(len(checks), 16)
        self.assertEqual(set(checks.keys()), set(VALIDATION_DIMENSIONS))
        self.assertEqual(checks["garment_type"]["status"], "PASS")
        self.assertEqual(checks["silhouette"]["status"], "PASS")
        self.assertEqual(checks["colour_harmony"]["status"], "PASS")
        self.assertGreaterEqual(confidence, 0.85)

    def test_validation_warns_on_missing_footwear(self):
        incomplete = dict(self.complete_outfit)
        incomplete["footwear"] = ""
        checks, warnings, confidence = validate_outfit_record(incomplete)
        self.assertEqual(checks["footwear"]["status"], "WARN")
        self.assertTrue(any("footwear" in w.lower() for w in warnings))

    def test_near_duplicate_detection(self):
        outfit_a = dict(self.complete_outfit)
        outfit_b = dict(self.complete_outfit)
        outfit_b["outfit_id"] = "OUTFIT-02"

        is_distinct, notes = check_outfit_distinctness(outfit_b, [outfit_a])
        self.assertFalse(is_distinct)
        self.assertIn("similarity", notes.lower())

    def test_generate_outfit_proposals(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.RESEARCH_SOURCES_FILE", self.test_data_dir / "research_sources.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
        ):
            save_or_update_brief(self.mock_brief)
            proposals = generate_outfit_proposals(self.brief_id, count=4)
            self.assertEqual(len(proposals), 4)

            # Check character rotation between WW-CHAR-01 and WW-CHAR-02
            assigned_chars = [p["assigned_character_id"] for p in proposals]
            self.assertIn("WW-CHAR-01", assigned_chars)
            self.assertIn("WW-CHAR-02", assigned_chars)

            # Check all outfits have validation results
            for p in proposals:
                self.assertIn("validation_results", p)
                self.assertEqual(p["approval_status"], "PENDING")

    def test_approval_and_cascade_invalidation_on_edit(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.VIDEO_ASSETS_FILE", self.test_data_dir / "video_assets.json"),
            patch("app.storage.RESEARCH_SOURCES_FILE", self.test_data_dir / "research_sources.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
        ):
            save_or_update_brief(self.mock_brief)
            generate_outfit_proposals(self.brief_id, count=2)

            # 1. Approve outfit 01
            appr = approve_single_outfit(self.brief_id, "OUTFIT-01")
            self.assertEqual(appr["approval_status"], ApprovalStatus.APPROVED.value)

            # 2. Mock a downstream approved image for outfit 01
            from app.storage import save_image_assets, load_image_assets
            save_image_assets(self.brief_id, [{
                "image_id": "IMG-01",
                "outfit_id": "OUTFIT-01",
                "approval_status": ApprovalStatus.APPROVED.value,
            }])

            # 3. User edits outfit 01
            edited = edit_outfit(
                brief_id=self.brief_id,
                outfit_id="OUTFIT-01",
                footwear="Chunky burgundy loafers",
            )
            # Outfit itself should return to PENDING
            self.assertEqual(edited["approval_status"], ApprovalStatus.PENDING.value)

            # Downstream image MUST be invalidated back to PENDING!
            images = load_image_assets(self.brief_id)
            self.assertEqual(images[0]["approval_status"], ApprovalStatus.PENDING.value)


if __name__ == "__main__":
    unittest.main()
