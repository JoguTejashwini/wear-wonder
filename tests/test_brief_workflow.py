"""Integration tests for the complete Stages 1–5 fashion production workflow."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.approval_workflow import (
    ApprovalStatus,
    WorkflowStage,
    approve_research,
    can_proceed_to_stage,
    get_workflow_prerequisites,
)
from app.fashion_ai import interpret_idea_with_gemini
from app.idea_intake import create_research_brief, save_research_brief
from app.image_generation.image_service import (
    approve_image,
    import_generated_image,
    prepare_image_prompts,
)
from app.research.provider import MockSearchProvider, SearchResult
from app.research.research_service import execute_fashion_research
from app.storage import (
    load_all_briefs,
    load_image_assets,
    load_outfits,
    load_video_assets,
    save_or_update_brief,
)
from app.styling.outfit_generator import generate_outfit_proposals
from app.styling.outfit_service import approve_all_outfits
from app.video_generation.video_service import (
    approve_video_clip,
    import_generated_video,
    prepare_video_prompts,
)
from app.publishing import (
    import_assembled_video,
    set_master_image_as_thumbnail,
    approve_and_schedule_video,
)


class MockInteraction:

    def __init__(self, output_text: str):
        self.output_text = output_text


class TestBriefWorkflow(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_data_dir = Path(self.temp_dir.name)
        self.test_data_file = self.test_data_dir / "research.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("app.fashion_ai.genai.Client")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key_12345"})
    def test_end_to_end_idea_to_saved_brief(self, mock_client_cls):
        # Existing records in research file
        existing_record = {
            "brief_id": "existing-brief-001",
            "idea_original": "Past existing idea",
            "audience": "General audience",
            "outfit_count": 3,
            "requested_characters": ["WW-CHAR-03"],
            "research_status": "APPROVED",
            "outfit_approval": "APPROVED",
        }
        self.test_data_file.write_text(
            json.dumps([existing_record], indent=2), encoding="utf-8"
        )

        mock_ai_response = {
            "audience": "College girls",
            "outfit_count": 6,
            "requested_characters": ["WW-CHAR-01", "WW-CHAR-02"],
            "concept_summary": "Six versatile campus denim combinations.",
            "styling_direction": "Casual chic layering with proportion play.",
            "research_plan": ["Research campus footwear trends", "Explore denim cuts"],
            "validation_checklist": ["Check movement comfort", "Verify colour harmony"],
            "clarifying_questions": ["Is this for spring or autumn?"],
            "assumptions": ["Assuming standard daytime university dress code"],
        }

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.interactions.create.return_value = MockInteraction(
            json.dumps(mock_ai_response)
        )

        idea_text = (
            "Create six jeans and top combinations for college girls "
            "using Female Model 01 and Female Model 02."
        )

        # 1. AI Interpretation
        ai_result = interpret_idea_with_gemini(
            idea=idea_text,
            additional_requirements="Sneakers only",
            reference_url="https://youtube.com/watch?v=example",
        )

        self.assertEqual(ai_result["outfit_count"], 6)
        self.assertEqual(ai_result["audience"], "College girls")
        self.assertEqual(
            ai_result["requested_characters"],
            ["WW-CHAR-01", "WW-CHAR-02"],
        )
        self.assertFalse(ai_result["live_research_performed"])

        # 2. Research Brief Creation (as done in dashboard.py)
        brief = create_research_brief(
            idea=idea_text,
            requested_characters=ai_result["requested_characters"],
            audience=ai_result["audience"],
            outfit_count=ai_result["outfit_count"],
            additional_requirements="Sneakers only",
        )
        brief["reference_url"] = "https://youtube.com/watch?v=example"
        brief["ai_analysis"] = ai_result
        brief["interpretation_method"] = "GEMINI_API"
        brief["interpretation_note"] = (
            "Gemini interpreted this idea. This is planning only: "
            "live research and outfit verification have not occurred."
        )

        # 3. Verify gate states: research and outfit approvals MUST remain pending
        self.assertEqual(brief["research_status"], "PENDING")
        self.assertEqual(brief["outfit_approval"], "PENDING")
        self.assertEqual(brief["requested_characters"], ["WW-CHAR-01", "WW-CHAR-02"])

        # 4. Save to storage without overwriting existing data
        with patch("app.idea_intake.DATA_FILE", self.test_data_file):
            save_research_brief(brief)

            # Re-read saved file
            saved_data = json.loads(self.test_data_file.read_text(encoding="utf-8"))
            self.assertEqual(len(saved_data), 2)
            self.assertEqual(saved_data[0]["brief_id"], "existing-brief-001")
            self.assertEqual(saved_data[1]["brief_id"], brief["brief_id"])
            self.assertEqual(saved_data[1]["outfit_count"], 6)
            self.assertEqual(
                saved_data[1]["requested_characters"],
                ["WW-CHAR-01", "WW-CHAR-02"],
            )
            self.assertEqual(saved_data[1]["research_status"], "PENDING")
            self.assertEqual(saved_data[1]["outfit_approval"], "PENDING")
            self.assertEqual(saved_data[1]["interpretation_method"], "GEMINI_API")

    @patch("app.research.research_service.check_url_accessibility", return_value=(True, 200))
    def test_complete_stages_1_to_5_lifecycle(self, mock_check):
        """Verify the integrated pipeline across Stages 1 through 5 with strict gate enforcement."""
        with (
            patch("app.storage.RESEARCH_FILE", self.test_data_dir / "research.json"),
            patch("app.storage.OUTFITS_FILE", self.test_data_dir / "outfits.json"),
            patch("app.storage.IMAGE_ASSETS_FILE", self.test_data_dir / "image_assets.json"),
            patch("app.storage.VIDEO_ASSETS_FILE", self.test_data_dir / "video_assets.json"),
            patch("app.storage.RESEARCH_SOURCES_FILE", self.test_data_dir / "research_sources.json"),
            patch("app.storage.AUDIT_LOG_FILE", self.test_data_dir / "workflow_audit.json"),
            patch("app.image_generation.image_service.GENERATED_IMAGES_DIR", self.test_data_dir / "images"),
            patch("app.video_generation.video_service.GENERATED_VIDEOS_DIR", self.test_data_dir / "videos"),
        ):
            # ----------------------------------------------------
            # STAGE 1: Idea Intake
            # ----------------------------------------------------
            idea_text = "Create three jeans and tops looks for college girls using female model 01"
            brief = create_research_brief(
                idea=idea_text,
                requested_characters=["WW-CHAR-01"],
                outfit_count=3,
                audience="College girls",
            )
            save_or_update_brief(brief)
            brief_id = brief["brief_id"]

            prereqs = get_workflow_prerequisites(brief_id)
            self.assertTrue(prereqs["has_brief"])
            self.assertFalse(prereqs["research_completed"])
            self.assertFalse(prereqs["outfits_approved"])

            # Verify Gate: Cannot jump directly to Stage 3 or Stage 4
            can_p, _ = can_proceed_to_stage(brief_id, WorkflowStage.STAGE_3_OUTFITS)
            self.assertFalse(can_p)
            can_p, _ = can_proceed_to_stage(brief_id, WorkflowStage.STAGE_4_IMAGES)
            self.assertFalse(can_p)

            # ----------------------------------------------------
            # STAGE 2: Live Fashion Research
            # ----------------------------------------------------
            mock_provider = MockSearchProvider([
                SearchResult(
                    title="Vogue Campus Denim Trends",
                    url="https://vogue.com/campus-denim",
                    snippet="Straight-leg jeans and clean baby tees define everyday styling.",
                    publisher="Vogue",
                ),
                SearchResult(
                    title="Elle Styling Playbook",
                    url="https://elle.com/denim-playbook",
                    snippet="Retro trainers balance relaxed denim volume.",
                    publisher="Elle",
                ),
            ])
            res_result = execute_fashion_research(brief_id, provider=mock_provider)
            self.assertEqual(len(res_result["sources"]), 2)

            # Research is completed, but still PENDING user approval
            prereqs = get_workflow_prerequisites(brief_id)
            self.assertTrue(prereqs["research_completed"])
            self.assertFalse(prereqs["research_approved"])

            # User reviews and explicitly approves research
            approve_research(brief_id, user_name="Test Fashion Lead")
            prereqs = get_workflow_prerequisites(brief_id)
            self.assertTrue(prereqs["research_approved"])

            # Now permitted to proceed to Stage 3
            can_p, _ = can_proceed_to_stage(brief_id, WorkflowStage.STAGE_3_OUTFITS)
            self.assertTrue(can_p)

            # ----------------------------------------------------
            # STAGE 3: Outfit Proposals & Validation
            # ----------------------------------------------------
            outfits = generate_outfit_proposals(brief_id, count=3)
            self.assertEqual(len(outfits), 3)
            self.assertTrue(all(o["approval_status"] == "PENDING" for o in outfits))

            # User approves all 3 outfit proposals
            approve_all_outfits(brief_id, user_name="Test Fashion Lead")
            prereqs = get_workflow_prerequisites(brief_id)
            self.assertTrue(prereqs["outfits_approved"])

            # Now permitted to proceed to Stage 4
            can_p, _ = can_proceed_to_stage(brief_id, WorkflowStage.STAGE_4_IMAGES)
            self.assertTrue(can_p)

            # ----------------------------------------------------
            # STAGE 4: Image Prompts, Generation & Approval
            # ----------------------------------------------------
            img_assets = prepare_image_prompts(brief_id)
            self.assertEqual(len(img_assets), 3)

            # Import images for each outfit and approve them
            fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtestbytes"
            for img in img_assets:
                import_generated_image(
                    brief_id=brief_id,
                    image_id=img["image_id"],
                    image_bytes=fake_png,
                    file_extension=".png",
                )
                approve_image(brief_id, img["image_id"], user_name="Test Fashion Lead")

            prereqs = get_workflow_prerequisites(brief_id)
            self.assertTrue(prereqs["images_approved"])

            # Now permitted to proceed to Stage 5
            can_p, _ = can_proceed_to_stage(brief_id, WorkflowStage.STAGE_5_VIDEOS)
            self.assertTrue(can_p)

            # ----------------------------------------------------
            # STAGE 5: Video Prompts, Generation & Approval
            # ----------------------------------------------------
            vid_assets = prepare_video_prompts(brief_id)
            self.assertEqual(len(vid_assets), 3)

            fake_mp4 = b"\x00\x00\x00\x18ftypmp42fakevideoclip"
            for vid in vid_assets:
                import_generated_video(
                    brief_id=brief_id,
                    clip_id=vid["clip_id"],
                    video_bytes=fake_mp4,
                    file_extension=".mp4",
                )
                approve_video_clip(brief_id, vid["clip_id"], user_name="Test Fashion Lead")

            # ----------------------------------------------------
            # STAGE 6: Video Assembly, Approval & Publishing
            # ----------------------------------------------------
            prereqs = get_workflow_prerequisites(brief_id)
            self.assertTrue(prereqs["videos_approved"])
            self.assertTrue(prereqs["stage_6_ready"])

            can_p, msg = can_proceed_to_stage(brief_id, WorkflowStage.STAGE_6_READY)
            self.assertTrue(can_p)
            self.assertIn("Ready for Stage 6", msg)

            can_p_pub, _ = can_proceed_to_stage(brief_id, WorkflowStage.STAGE_6_PUBLISHING)
            self.assertTrue(can_p_pub)

            # Ingest final assembled video and select approved look as thumbnail
            assembled_mp4 = b"\x00\x00\x00\x18ftypmp42assembledverticalshort"
            pub_record = import_assembled_video(brief_id, assembled_mp4, "assembled_lookbook_short.mp4")
            self.assertIsNotNone(pub_record["video_file_path"])

            thumb_record = set_master_image_as_thumbnail(brief_id, img_assets[0]["image_id"])
            self.assertIsNotNone(thumb_record["thumbnail_file_path"])

            # Execute final mandatory approval and scheduled dispatch
            future_iso = "2026-11-10T14:30:00Z"
            dispatched_record = approve_and_schedule_video(
                brief_id=brief_id,
                platforms=["youtube", "instagram"],
                scheduled_time_iso=future_iso,
                privacy_status="private",
                user_name="Lead Editor",
                mock_mode=True,
            )

            self.assertEqual(dispatched_record["status"], "SCHEDULED")
            self.assertTrue(dispatched_record["platforms_status"]["youtube"]["url"].startswith("https://youtube.com/shorts/"))
            self.assertTrue(dispatched_record["platforms_status"]["instagram"]["permalink"].startswith("https://www.instagram.com/reel/"))

            # Check prerequisites now reflect published/scheduled state
            prereqs_final = get_workflow_prerequisites(brief_id)
            self.assertTrue(prereqs_final["has_assembled_video"])
            self.assertTrue(prereqs_final["is_published_or_scheduled"])


if __name__ == "__main__":
    unittest.main()
