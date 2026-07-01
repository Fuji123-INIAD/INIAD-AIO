from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app.core.local_resources import (
    build_local_resource_index,
    create_pdf_resource,
    write_local_resource_index,
)


class LocalResourcesTests(unittest.TestCase):
    def test_pdf_discovery_infers_course_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "2026" / "COT101" / "11-1" / "example.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.4\n% dummy only\n")

            index = build_local_resource_index(root)

        self.assertEqual(1, len(index.resources))
        resource = index.resources[0]
        self.assertEqual("COT101", resource.course_code)
        self.assertEqual("COT101", resource.course_title)
        self.assertIsNone(resource.lecture_title)
        self.assertEqual("example.pdf", resource.title)
        self.assertEqual("pdf", resource.resource_type)
        self.assertFalse(resource.text_available)
        self.assertIsNone(resource.text_cache_path)
        self.assertEqual("filesystem", resource.discovered_from)

    def test_future_course_code_shapes_can_be_inferred(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "INFO1001" / "02" / "slides.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.4\n% dummy only\n")

            index = build_local_resource_index(root)

        self.assertEqual("INFO1001", index.resources[0].course_code)

    def test_unknown_course_code_still_keeps_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "saved-materials" / "handout.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.4\n% dummy only\n")

            index = build_local_resource_index(root)

        self.assertEqual(1, len(index.resources))
        self.assertIsNone(index.resources[0].course_code)
        self.assertEqual("handout.pdf", index.resources[0].title)

    def test_course_and_lecture_titles_are_inferred_when_root_is_year_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            year_root = Path(temp_dir) / "2026"
            pdf_path = (
                year_root
                / "情報連携学概論 I"
                / "08_ セキュリティ"
                / "Part1.pdf"
            )
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.4\n")

            index = build_local_resource_index(year_root)

        self.assertEqual(1, len(index.resources))
        resource = index.resources[0]
        self.assertIsNone(resource.course_code)
        self.assertEqual("情報連携学概論 I", resource.course_title)
        self.assertEqual("08", resource.lecture_key)
        self.assertEqual("セキュリティ", resource.lecture_title)

    def test_course_title_is_root_name_when_root_is_course_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            course_root = Path(temp_dir) / "情報連携学概論 I"
            first_pdf = course_root / "AI-05_ 回帰の復習" / "Part1.pdf"
            second_pdf = (
                course_root
                / "DS-00_ データ解析のための環境構築"
                / "Part2.pdf"
            )
            first_pdf.parent.mkdir(parents=True)
            second_pdf.parent.mkdir(parents=True)
            first_pdf.write_bytes(b"%PDF-1.4\n")
            second_pdf.write_bytes(b"%PDF-1.4\n")

            index = build_local_resource_index(course_root)

        resources_by_title = {resource.title: resource for resource in index.resources}
        first = resources_by_title["Part1.pdf"]
        second = resources_by_title["Part2.pdf"]
        self.assertEqual("情報連携学概論 I", first.course_title)
        self.assertEqual("05", first.lecture_key)
        self.assertEqual("回帰の復習", first.lecture_title)
        self.assertEqual("情報連携学概論 I", second.course_title)
        self.assertEqual("00", second.lecture_key)
        self.assertEqual("データ解析のための環境構築", second.lecture_title)

    def test_lecture_key_is_inferred_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_pdf = root / "COT101" / "11-1" / "lecture.pdf"
            second_pdf = root / "SEM101" / "material_00-3.pdf"
            third_pdf = root / "COT105" / "02" / "intro.PDF"
            first_pdf.parent.mkdir(parents=True)
            second_pdf.parent.mkdir(parents=True)
            third_pdf.parent.mkdir(parents=True)
            first_pdf.write_bytes(b"%PDF-1.4\n")
            second_pdf.write_bytes(b"%PDF-1.4\n")
            third_pdf.write_bytes(b"%PDF-1.4\n")

            index = build_local_resource_index(root)

        lecture_by_title = {
            resource.title: resource.lecture_key for resource in index.resources
        }
        self.assertEqual("11-1", lecture_by_title["lecture.pdf"])
        self.assertEqual("00-3", lecture_by_title["material_00-3.pdf"])
        self.assertEqual("02", lecture_by_title["intro.PDF"])

    def test_resource_id_is_stable_for_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "COT101" / "01" / "stable.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.4\n")

            first = create_pdf_resource(pdf_path)
            second = create_pdf_resource(pdf_path)
            first_index = build_local_resource_index(root)
            second_index = build_local_resource_index(root)

        self.assertEqual(first.resource_id, second.resource_id)
        self.assertEqual(first_index.resources[0].resource_id, second_index.resources[0].resource_id)

    def test_json_output_shape_matches_resource_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "data" / "local" / "resource_index.json"
            pdf_path = root / "COT101" / "11-1" / "example.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.4\n")

            index = build_local_resource_index(root)
            write_local_resource_index(index, output)
            data = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(["resources", "warnings"], list(data))
        self.assertEqual(1, len(data["resources"]))
        resource = data["resources"][0]
        self.assertEqual("COT101", resource["course_code"])
        self.assertEqual("COT101", resource["course_title"])
        self.assertEqual("11-1", resource["lecture_key"])
        self.assertIsNone(resource["lecture_title"])
        self.assertEqual("example.pdf", resource["title"])
        self.assertEqual("pdf", resource["resource_type"])
        self.assertIsNone(resource["source_url"])
        self.assertTrue(resource["local_path"].endswith("example.pdf"))
        self.assertIsNone(resource["page_key"])
        self.assertFalse(resource["text_available"])
        self.assertIsNone(resource["text_cache_path"])
        self.assertEqual("filesystem", resource["discovered_from"])
        self.assertEqual([], resource["warnings"])
        self.assertEqual([], data["warnings"])

    def test_missing_root_returns_empty_index_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_root = Path(temp_dir) / "missing"

            index = build_local_resource_index(missing_root)

        self.assertEqual([], index.resources)
        self.assertTrue(index.warnings)
        self.assertIn("does not exist", index.warnings[0]["message"])


if __name__ == "__main__":
    unittest.main()
