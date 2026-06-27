from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.list_moocs_collect_page_keys import list_moocs_collect_page_keys


def create_dummy_db(db_path: Path) -> None:
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
        connection.executemany(
            "INSERT INTO pages (id, key) VALUES (?, ?)",
            [
                (1, "2026/COT000/00/exercise"),
                (2, "2026/COT000/01/lecture"),
                (3, "2026/COT999/00/other"),
            ],
        )
        connection.executemany(
            "INSERT INTO slides (id, page_id, url, pdf_path) VALUES (?, ?, ?, ?)",
            [
                (1, 1, "https://docs.example/slide-1", "slide-1.pdf"),
                (2, 1, "", None),
                (3, 2, None, "slide-2.pdf"),
            ],
        )
        connection.commit()


class MoocsCollectPageKeyListingTests(unittest.TestCase):
    def test_lists_page_keys_and_slide_availability_for_course(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "db.sqlite"
            probe_json = root / "probe.json"
            create_dummy_db(db_path)
            probe_json.write_text(
                json.dumps(
                    {
                        "courses": [
                            {
                                "lessons": [
                                    {
                                        "pages": [
                                            {
                                                "page_url": "https://moocs.iniad.org/courses/2026/COT000/00/exercise"
                                            },
                                            {
                                                "page_url": "https://moocs.iniad.org/courses/2026/COT000/01/lecture/"
                                            },
                                            {
                                                "page_url": "https://moocs.iniad.org/courses/2026/COT000/99/missing"
                                            },
                                            {
                                                "page_url": "https://moocs.iniad.org/courses/2026/COT999/00/other"
                                            },
                                            {
                                                "page_url": "https://example.com/not-moocs"
                                            },
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = list_moocs_collect_page_keys(
                probe_json=probe_json,
                db_path=db_path,
                course_code="COT000",
            )

        self.assertEqual("COT000", report["course_code"])
        self.assertEqual(3, report["page_count"])
        self.assertEqual(2, report["collect_page_exists_count"])
        self.assertEqual(1, report["slides_url_exists_count"])
        self.assertEqual(2, report["pdf_path_exists_count"])
        self.assertEqual(
            [
                {
                    "page_key": "2026/COT000/00/exercise",
                    "page_url": "https://moocs.iniad.org/courses/2026/COT000/00/exercise",
                    "collect_page_exists": True,
                    "slide_count": 2,
                    "slides_url_exists": True,
                    "slides_url_count": 1,
                    "pdf_path_exists": True,
                    "pdf_path_count": 1,
                },
                {
                    "page_key": "2026/COT000/01/lecture",
                    "page_url": "https://moocs.iniad.org/courses/2026/COT000/01/lecture/",
                    "collect_page_exists": True,
                    "slide_count": 1,
                    "slides_url_exists": False,
                    "slides_url_count": 0,
                    "pdf_path_exists": True,
                    "pdf_path_count": 1,
                },
                {
                    "page_key": "2026/COT000/99/missing",
                    "page_url": "https://moocs.iniad.org/courses/2026/COT000/99/missing",
                    "collect_page_exists": False,
                    "slide_count": 0,
                    "slides_url_exists": False,
                    "slides_url_count": 0,
                    "pdf_path_exists": False,
                    "pdf_path_count": 0,
                },
            ],
            report["rows"],
        )
        self.assertTrue(report["safety"]["db_read_only"])
        self.assertFalse(report["safety"]["slide_urls_fetched"])


if __name__ == "__main__":
    unittest.main()
