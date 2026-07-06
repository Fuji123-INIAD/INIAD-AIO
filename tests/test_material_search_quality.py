from __future__ import annotations

import unittest

from backend.app.core.material_search import search_material_chunks
from scripts.evaluate_material_search import (
    DEFAULT_FILTERS,
    build_fixture_chunks,
    evaluate_search_quality,
    parse_args,
)


class MaterialSearchQualityTests(unittest.TestCase):
    def test_evaluation_fixture_passes_quality_checks(self) -> None:
        report = evaluate_search_quality(query="security", mode="hybrid", limit=5)

        self.assertEqual("ok", report["status"])
        self.assertTrue(all(check["passed"] for check in report["checks"]))

    def test_text_chunk_ranks_above_metadata_only(self) -> None:
        results = search_material_chunks(
            build_fixture_chunks(),
            query="security",
            mode="hybrid",
            limit=5,
            filters=DEFAULT_FILTERS,
        )

        metadata_index = next(
            index
            for index, result in enumerate(results)
            if result["chunk_type"] == "metadata"
        )
        text_indexes = [
            index
            for index, result in enumerate(results)
            if result["chunk_type"] != "metadata"
        ]
        self.assertTrue(text_indexes)
        self.assertLess(max(text_indexes), metadata_index)

    def test_exact_course_title_and_lecture_key_beat_partial_filter_matches(self) -> None:
        results = search_material_chunks(
            build_fixture_chunks(),
            query="security",
            mode="keyword",
            limit=5,
            filters=DEFAULT_FILTERS,
        )

        self.assertEqual("exact-text-1", results[0]["chunk_id"])
        self.assertEqual("Info Link I", results[0]["course_title"])
        self.assertEqual("08", results[0]["lecture_key"])

    def test_top_two_results_do_not_repeat_same_material_when_alternatives_exist(self) -> None:
        results = search_material_chunks(
            build_fixture_chunks(),
            query="security",
            mode="hybrid",
            limit=2,
            filters=DEFAULT_FILTERS,
        )

        material_ids = [result["material_id"] for result in results]
        self.assertEqual(2, len(material_ids))
        self.assertEqual(len(material_ids), len(set(material_ids)))

    def test_provider_source_type_and_method_are_preserved(self) -> None:
        results = search_material_chunks(
            build_fixture_chunks(),
            query="security",
            mode="hybrid",
            limit=5,
            filters=DEFAULT_FILTERS,
        )

        top = results[0]
        self.assertEqual("moocs_collect_search_index", top["provider"])
        self.assertEqual("moocs_collect_search_index", top["source_type"])
        self.assertEqual("search_index", top["extraction_method"])

    def test_evaluation_parser_accepts_helpful_options(self) -> None:
        args = parse_args(["--query", "security", "--mode", "keyword", "--format", "json"])

        self.assertEqual("security", args.query)
        self.assertEqual("keyword", args.mode)
        self.assertEqual("json", args.format)


if __name__ == "__main__":
    unittest.main()
