from __future__ import annotations

import unittest

from backend.app.core.course_rules import (
    CourseRule,
    get_course_rule,
    list_course_rules,
)


class CourseRuleRegistryTests(unittest.TestCase):
    def test_cot101_rule_is_available(self) -> None:
        rule = get_course_rule("COT101")

        self.assertIsInstance(rule, CourseRule)
        self.assertEqual("next_lecture_previous_day", rule.deadline_rule)
        self.assertEqual("moocs", rule.submission_channel)
        self.assertEqual("medium", rule.confidence)
        self.assertIn("Slides", rule.notes)

    def test_sem101_rule_is_available(self) -> None:
        rule = get_course_rule("SEM101")

        self.assertIsNotNone(rule)
        self.assertEqual("same_week_sunday_2359", rule.deadline_rule)
        self.assertEqual("email_to_instructor", rule.submission_channel)
        self.assertEqual("medium", rule.confidence)

    def test_cot105_rule_is_available(self) -> None:
        rule = get_course_rule("COT105")

        self.assertIsNotNone(rule)
        self.assertEqual("explicit_or_unknown", rule.deadline_rule)
        self.assertEqual("moocs", rule.submission_channel)
        self.assertEqual("low", rule.confidence)

    def test_unknown_course_returns_none(self) -> None:
        self.assertIsNone(get_course_rule("UNKNOWN101"))

    def test_lookup_normalizes_course_code(self) -> None:
        rule = get_course_rule(" cot101 ")

        self.assertIsNotNone(rule)
        self.assertEqual("COT101", rule.course_code)

    def test_list_course_rules_contains_initial_courses(self) -> None:
        rules = list_course_rules()

        self.assertEqual({"COT101", "SEM101", "COT105"}, set(rules))
        self.assertTrue(all(isinstance(rule, CourseRule) for rule in rules.values()))

    def test_rule_does_not_hold_deadline_values(self) -> None:
        rule = get_course_rule("COT101")

        self.assertIsNotNone(rule)
        self.assertFalse(hasattr(rule, "deadline_at"))
        self.assertFalse(hasattr(rule, "estimated_deadline_at"))


if __name__ == "__main__":
    unittest.main()
