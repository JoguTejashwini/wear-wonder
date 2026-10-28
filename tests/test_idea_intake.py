
import unittest

from app.idea_intake import create_research_brief


class TestIdeaIntake(unittest.TestCase):

    def test_preserves_original_idea(self):
        idea = (
            "Create six jeans and top combinations "
            "for college girls."
        )

        brief = create_research_brief(idea)

        self.assertEqual(brief["idea_original"], idea)

    def test_rejects_empty_idea(self):
        with self.assertRaises(ValueError):
            create_research_brief("   ")

    def test_accepts_three_character_ids(self):
        characters = [
            "WW-CHAR-01",
            "WW-CHAR-02",
            "WW-CHAR-03",
        ]

        brief = create_research_brief(
            "Create a fashion comparison video.",
            requested_characters=characters,
        )

        self.assertEqual(
            brief["requested_characters"],
            characters,
        )

    def test_rejects_invalid_character_id(self):
        with self.assertRaises(ValueError):
            create_research_brief(
                "Create a fashion video.",
                requested_characters=["UNKNOWN-CHAR"],
            )

    def test_rejects_invalid_outfit_count(self):
        with self.assertRaises(ValueError):
            create_research_brief(
                "Create a fashion video.",
                outfit_count=0,
            )

    def test_approval_starts_as_pending(self):
        brief = create_research_brief(
            "Create a fashion video."
        )

        self.assertEqual(
            brief["research_status"],
            "PENDING",
        )
        self.assertEqual(
            brief["outfit_approval"],
            "PENDING",
        )
    
    def test_extracts_outfit_count_from_number_word(self):
        brief = create_research_brief(
            "Create a video showing six jeans and top combinations "
            "for college girls, using my female master model consistently."
        )

        self.assertEqual(brief["outfit_count"], 6)

    def test_preserves_original_idea_exactly(self):
        idea = (
            "Create a video showing six jeans and top combinations "
            "for college girls, using my female master model consistently."
        )

        brief = create_research_brief(idea)

        self.assertEqual(brief["idea_original"], idea)


if __name__ == "__main__":
    unittest.main()
