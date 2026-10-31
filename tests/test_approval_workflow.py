"""Unit tests for Global Workflow Gatekeeping and Cascade Invalidation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.approval_workflow import (
    ApprovalStatus,
    WorkflowStage,
    approve_research,
    can_proceed_to_stage,
    get_workflow_prerequisites,
    invalidate_downstream_for_outfit,
    set_image_approval_status,
    set_outfit_approval_status,
    set_video_approval_status,
)
from app.storage import (
    load_audit_events,
    load_image_assets,
    load_video_assets,
    save_image_assets,
    save_or_update_brief,
    save_outfits,
    save_video_assets,
)


class TestApprovalWorkflow(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_data_dir = Path(self.temp_dir.name)
        self.brief_id = "test-brief-gate-01"
        self.mock_brief = {
            "brief_id": self.brief_id,
            "idea_original": "Test fashion concept",
            "research_status": "PENDING",
            "outfit_approval": "PENDING",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_workflow_prerequisites_enforced(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.VIDEO_ASSETS_FILE", self.test_data_dir / "video_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
        ):
            save_or_update_brief(self.mock_brief)

            # Stage 3 cannot proceed because research is not approved
            can_p, reason = can_proceed_to_stage(self.brief_id, WorkflowStage.STAGE_3_OUTFITS)
            self.assertFalse(can_p)
            self.assertIn("Research must be reviewed", reason)

            # Approve research
            approve_research(self.brief_id)
            can_p, _ = can_proceed_to_stage(self.brief_id, WorkflowStage.STAGE_3_OUTFITS)
            self.assertTrue(can_p)

            # Stage 4 cannot proceed because outfits are not approved
            can_p, reason = can_proceed_to_stage(self.brief_id, WorkflowStage.STAGE_4_IMAGES)
            self.assertFalse(can_p)
            self.assertIn("outfit proposals must be approved", reason)

    def test_cascade_invalidation_matrix(self):
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.VIDEO_ASSETS_FILE", self.test_data_dir / "video_assets.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
        ):
            save_or_update_brief(self.mock_brief)
            save_outfits(self.brief_id, [
                {"outfit_id": "OUTFIT-01", "approval_status": ApprovalStatus.APPROVED.value},
                {"outfit_id": "OUTFIT-02", "approval_status": ApprovalStatus.APPROVED.value},
            ])
            save_image_assets(self.brief_id, [
                {"image_id": "IMG-01", "outfit_id": "OUTFIT-01", "approval_status": ApprovalStatus.APPROVED.value},
                {"image_id": "IMG-02", "outfit_id": "OUTFIT-02", "approval_status": ApprovalStatus.APPROVED.value},
            ])
            save_video_assets(self.brief_id, [
                {"clip_id": "CLIP-01", "outfit_id": "OUTFIT-01", "approval_status": ApprovalStatus.APPROVED.value},
                {"clip_id": "CLIP-02", "outfit_id": "OUTFIT-02", "approval_status": ApprovalStatus.APPROVED.value},
            ])

            # Invalidate outfit 01
            invalidate_downstream_for_outfit(self.brief_id, "OUTFIT-01", reason="test invalidation")

            images = load_image_assets(self.brief_id)
            videos = load_video_assets(self.brief_id)

            # Outfit 01 assets must be PENDING
            self.assertEqual(images[0]["approval_status"], ApprovalStatus.PENDING.value)
            self.assertEqual(videos[0]["approval_status"], ApprovalStatus.PENDING.value)

            # Outfit 02 assets MUST REMAIN APPROVED
            self.assertEqual(images[1]["approval_status"], ApprovalStatus.APPROVED.value)
            self.assertEqual(videos[1]["approval_status"], ApprovalStatus.APPROVED.value)

            # Audit trail must log the invalidation event
            logs = load_audit_events(self.brief_id)
            self.assertTrue(any(l["action"] == "IMAGE_INVALIDATED" for l in logs))
            self.assertTrue(any(l["action"] == "VIDEO_INVALIDATED" for l in logs))


if __name__ == "__main__":
    unittest.main()
