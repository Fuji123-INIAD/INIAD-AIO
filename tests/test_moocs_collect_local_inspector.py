from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.inspect_moocs_collect_local import inspect_moocs_collect_local


def create_dummy_moocs_collect_db(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE courses (
                id TEXT PRIMARY KEY,
                title TEXT
            );
            CREATE TABLE lectures (
                id TEXT PRIMARY KEY,
                course_id TEXT,
                title TEXT
            );
            CREATE TABLE pages (
                id TEXT PRIMARY KEY,
                lecture_id TEXT,
                key TEXT,
                slug TEXT
            );
            CREATE TABLE slides (
                id TEXT PRIMARY KEY,
                page_id TEXT,
                pdf_path TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO courses (id, title) VALUES (?, ?)",
            ("course-1", "Dummy Course"),
        )
        connection.execute(
            "INSERT INTO lectures (id, course_id, title) VALUES (?, ?, ?)",
            ("lecture-1", "course-1", "Dummy Lecture"),
        )
        connection.execute(
            "INSERT INTO pages (id, lecture_id, key, slug) VALUES (?, ?, ?, ?)",
            ("page-1", "lecture-1", "2026/COT000/01/01", "intro"),
        )
        connection.executemany(
            "INSERT INTO slides (id, page_id, pdf_path) VALUES (?, ?, ?)",
            [
                ("slide-1", "page-1", "lecture-1.pdf"),
                ("slide-2", "page-1", None),
                ("slide-3", "page-1", "missing.PDF"),
            ],
        )
        connection.commit()


class MoocsCollectLocalInspectorTests(unittest.TestCase):
    def test_inspector_reports_counts_pdf_presence_and_search_index_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "db.sqlite"
            pdf_path = root / "lecture-1.pdf"
            search_index = root / "search_index"
            nested_index = search_index / "nested"

            create_dummy_moocs_collect_db(db_path)
            pdf_path.write_bytes(b"%PDF-1.4\n% dummy only\n")
            search_index.mkdir()
            (search_index / "segment").write_bytes(b"abc")
            nested_index.mkdir()
            (nested_index / "terms").write_bytes(b"12345")

            report = inspect_moocs_collect_local(
                db_path=db_path,
                search_index=search_index,
                download_dir=root,
            )

        self.assertEqual(
            {"courses": 1, "lectures": 1, "pages": 1, "slides": 3},
            report["counts"],
        )
        self.assertIn("courses", report["schema"]["tables"])
        self.assertEqual(
            [{"key": "2026/COT000/01/01", "slug": "intro"}],
            report["pages"]["samples"],
        )
        self.assertEqual(3, report["slides_pdf_path"]["total"])
        self.assertEqual(1, report["slides_pdf_path"]["null"])
        self.assertEqual(2, report["slides_pdf_path"]["non_null"])
        self.assertEqual(1, report["slides_pdf_path"]["existing"])
        self.assertEqual(1, report["slides_pdf_path"]["missing"])
        self.assertEqual(0.5, report["slides_pdf_path"]["existing_ratio_of_non_null"])
        self.assertAlmostEqual(1 / 3, report["slides_pdf_path"]["existing_ratio_of_total"])
        self.assertEqual({".pdf": 2}, report["slides_pdf_path"]["extensions"])
        self.assertEqual(
            ["lecture-1.pdf", "missing.PDF"],
            report["slides_pdf_path"]["filename_samples"],
        )
        self.assertEqual(True, report["search_index"]["exists"])
        self.assertEqual(2, report["search_index"]["file_count"])
        self.assertEqual(8, report["search_index"]["total_size"])
        self.assertFalse(report["safety"]["pdf_text_read"])
        self.assertFalse(report["safety"]["lecture_text_printed"])
        self.assertFalse(report["safety"]["sensitive_files_read"])

    def test_page_samples_are_limited(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "db.sqlite"
            create_dummy_moocs_collect_db(db_path)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.executemany(
                    "INSERT INTO pages (id, lecture_id, key, slug) VALUES (?, ?, ?, ?)",
                    [
                        (f"page-extra-{index}", "lecture-1", f"key-{index}", f"slug-{index}")
                        for index in range(10)
                    ],
                )
                connection.commit()

            report = inspect_moocs_collect_local(db_path=db_path, sample_limit=5)

        self.assertEqual(5, len(report["pages"]["samples"]))


if __name__ == "__main__":
    unittest.main()
