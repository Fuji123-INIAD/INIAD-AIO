from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.app.core.task_slides_evidence import load_slides_evidence_by_course


def create_collect_db(db_path: Path, *, with_url: bool) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY,
                key TEXT NOT NULL
            );
            CREATE TABLE slides (
                id INTEGER PRIMARY KEY,
                page_id INTEGER NOT NULL,
                url TEXT,
                pdf_path TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO pages (id, key) VALUES (?, ?)",
            (1, "2026/COT000/00/exercise"),
        )
        connection.execute(
            "INSERT INTO slides (id, page_id, url, pdf_path) VALUES (?, ?, ?, ?)",
            (
                1,
                1,
                "https://docs.example/slide" if with_url else "",
                "slide.pdf",
            ),
        )
        connection.commit()


class TaskSlidesEvidenceTests(unittest.TestCase):
    def test_loads_google_slides_material_from_probe_json(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "moocs_course_details_minimal.json"

        evidence_by_course, warnings = load_slides_evidence_by_course(
            ["COT101"],
            fixture,
        )

        self.assertEqual([], warnings)
        evidence = evidence_by_course["COT101"]
        self.assertEqual("slides", evidence[0].type)
        self.assertEqual("https://docs.google.com/presentation/d/example-1/embed", evidence[0].source)
        self.assertEqual("high", evidence[0].confidence)

    def test_uses_moocs_collect_slide_url_when_probe_page_has_no_slide_material(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            probe_json = root / "probe.json"
            db_path = root / "db.sqlite"
            create_collect_db(db_path, with_url=True)
            probe_json.write_text(
                json.dumps(
                    [
                        {
                            "pages": [
                                {
                                    "page_title": "Exercise",
                                    "page_url": "https://moocs.iniad.org/courses/2026/COT000/00/exercise",
                                    "materials": [],
                                }
                            ]
                        }
                    ]
                ),
                encoding="utf-8",
            )

            evidence_by_course, warnings = load_slides_evidence_by_course(
                ["COT000"],
                probe_json,
                moocs_collect_db_path=db_path,
            )

        self.assertEqual([], warnings)
        evidence = evidence_by_course["COT000"][0]
        self.assertEqual("slides", evidence.type)
        self.assertEqual("https://docs.example/slide", evidence.source)
        self.assertEqual("high", evidence.confidence)

    def test_uses_page_key_with_medium_confidence_when_collect_has_no_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            probe_json = root / "probe.json"
            db_path = root / "db.sqlite"
            create_collect_db(db_path, with_url=False)
            probe_json.write_text(
                json.dumps(
                    [
                        {
                            "pages": [
                                {
                                    "page_title": "Exercise",
                                    "page_url": "https://moocs.iniad.org/courses/2026/COT000/00/exercise",
                                    "materials": [],
                                }
                            ]
                        }
                    ]
                ),
                encoding="utf-8",
            )

            evidence_by_course, warnings = load_slides_evidence_by_course(
                ["COT000"],
                probe_json,
                moocs_collect_db_path=db_path,
            )

        self.assertEqual([], warnings)
        evidence = evidence_by_course["COT000"][0]
        self.assertEqual("slides", evidence.type)
        self.assertEqual("2026/COT000/00/exercise", evidence.source)
        self.assertEqual("medium", evidence.confidence)

    def test_page_without_slides_adds_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe_json = Path(temp_dir) / "probe.json"
            probe_json.write_text(
                json.dumps(
                    [
                        {
                            "pages": [
                                {
                                    "page_url": "https://moocs.iniad.org/courses/2026/COT000/00/exercise",
                                    "materials": [],
                                }
                            ]
                        }
                    ]
                ),
                encoding="utf-8",
            )

            evidence_by_course, warnings = load_slides_evidence_by_course(
                ["COT000"],
                probe_json,
            )

        self.assertEqual({}, evidence_by_course)
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
