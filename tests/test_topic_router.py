"""Unit tests for the Fashion Topic Router."""
import unittest

from app.topic_router import (
    TOPIC_REGISTRY,
    classify_topic,
    get_topic_config,
    list_supported_topics,
)


class TestTopicRouter(unittest.TestCase):

    def test_classifies_jeans_and_tops(self):
        idea = "Create 6 jeans and tops combinations for college girls"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "jeans_and_tops")
        self.assertIn("denim", config.description.lower())

    def test_classifies_colour_combinations(self):
        idea = "Show modern outfit color combinations with contrast and pastel tones"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "colour_combinations")

    def test_classifies_casual_college(self):
        idea = "Everyday university student casual outfits for autumn campus"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "casual_and_college")

    def test_classifies_formal_and_office(self):
        idea = "Smart formal office wear and business casual corporate blazers"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "formal_and_office")

    def test_classifies_shoes_and_footwear(self):
        idea = "How to style chunky loafers and retro sneakers with different outfits"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "shoes_and_footwear")

    def test_classifies_bags_and_accessories(self):
        idea = "Matching handbag shapes, jewelry, and belts to elevate simple looks"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "bags_and_accessories")

    def test_classifies_seasonal_styling(self):
        idea = "Cozy winter layering and weather appropriate coat styling"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "seasonal_styling")

    def test_classifies_couples_styling(self):
        idea = "Complementary coordinating couple outfits for a dinner date"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "couples_styling")

    def test_classifies_mens_fashion(self):
        idea = "Smart casual menswear essentials for guys with tailored trousers"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "mens_fashion")

    def test_fallback_to_general_fashion_for_abstract_text(self):
        idea = "Aesthetic futuristic minimalist expression"
        config = classify_topic(idea)
        self.assertEqual(config.topic_id, "general_fashion")

    def test_hint_overrides_text(self):
        idea = "Jeans and tops idea"
        config = classify_topic(idea, hint="formal_and_office")
        self.assertEqual(config.topic_id, "formal_and_office")

    def test_list_supported_topics_contains_all_major_categories(self):
        topics = list_supported_topics()
        topic_ids = {t.topic_id for t in topics}
        expected = {
            "jeans_and_tops",
            "colour_combinations",
            "casual_and_college",
            "formal_and_office",
            "shoes_and_footwear",
            "bags_and_accessories",
            "seasonal_styling",
            "couples_styling",
            "mens_fashion",
            "womens_fashion",
            "general_fashion",
        }
        self.assertTrue(expected.issubset(topic_ids))

    def test_get_topic_config_unknown_defaults_safely(self):
        cfg = get_topic_config("non_existent_topic_id")
        self.assertEqual(cfg.topic_id, "general_fashion")


if __name__ == "__main__":
    unittest.main()
