from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.check_moocs_collect_page_join import (
    check_moocs_collect_page_join,
    load_aio_page_keys,
    page_url_to_key,
)


def create_dummy_moocs_collect_db(db_path: Path) -> None:
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
                pdf_path TEXT
            );
            """
        )
        connection.executemany(
            "INSERT INTO pages (id, key) VALUES (?, ?)",
            [
                (1, "2026/COT000/00/exercise"),
                (2, "2026/COT000/01/lecture"),
                (3, "2026/COT000/02/review"),
            ],
        )
        connection.executemany(
            "INSERT INTO slides (id, page_id, pdf_path) VALUES (?, ?, ?)",
            [
                (1, 1, "existing.pdf"),
                (2, 1, None),
                (3, 2, "missing.pdf"),
                (4, 3, "unused.pdf"),
            ],
        )
        connection.commit()


class MoocsCollectPageJoinTests(unittest.TestCase):
    def test_page_url_to_key_normalizes_trailing_slash_and_query(self) -> None:
        self.assertEqual(
            "2026/COT105/00/exercise",
            page_url_to_key(
                "https://moocs.iniad.org/courses/2026/COT105/00/exercise/?x=1#top"
            ),
        )
        self.assertEqual(
            "2026/COT105/01/lecture",
            page_url_to_key("https://moocs.iniad.org/courses/2026/COT105/01/lecture"),
        )
        self.assertIsNone(page_url_to_key("https://moocs.iniad.org/courses/2026/COT105"))

    def test_load_aio_page_keys_accepts_list_object_and_courses_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            list_probe = root / "list_probe.json"
            object_probe = root / "object_probe.json"
            courses_probe = root / "courses_probe.json"

            list_probe.write_text(
                json.dumps(
                    [
                        {
                            "lessons": [
                                {
                                    "pages": [
                                        {
                                            "page_url": "https://moocs.iniad.org/courses/2026/COT000/00/exercise"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                ),
                encoding="utf-8",
            )
            object_probe.write_text(
                json.dumps(
                    {
                        "lessons": [
                            {
                                "pages": [
                                    {
                                        "page_url": "https://moocs.iniad.org/courses/2026/COT000/01/lecture"
                                    }
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            courses_probe.write_text(
                json.dumps(
                    {
                        "courses": [
                            {
                                "lessons": [
                                    {
                                        "pages": [
                                            {
                                                "page_url": "https://moocs.iniad.org/courses/2026/COT000/02/review"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                ["2026/COT000/00/exercise"],
                load_aio_page_keys(list_probe)["unique_keys"],
            )
            self.assertEqual(
                ["2026/COT000/01/lecture"],
                load_aio_page_keys(object_probe)["unique_keys"],
            )
            self.assertEqual(
                ["2026/COT000/02/review"],
                load_aio_page_keys(courses_probe)["unique_keys"],
            )

    def test_join_reports_matches_unmatched_and_pdf_presence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "db.sqlite"
            probe_path = root / "probe.json"
            download_dir = root / "downloads"

            download_dir.mkdir()
            (download_dir / "existing.pdf").write_bytes(b"%PDF-1.4\n% dummy only\n")
            create_dummy_moocs_collect_db(db_path)
            probe_path.write_text(
                json.dumps(
                    {
                        "courses": [
                            {
                                "lessons": [
                                    {
                                        "pages": [
                                            {
                                                "page_url": "https://moocs.iniad.org/courses/2026/COT000/00/exercise/"
                                            },
                                            {
                                                "page_url": "https://moocs.iniad.org/courses/2026/COT000/01/lecture?from=aio"
                                            },
                                            {
                                                "page_url": "https://moocs.iniad.org/courses/2026/COT000/99/missing"
                                            },
                                            {
                                                "page_url": "https://example.com/not-a-moocs-page"
                                            },
                                            {
                                                "page_url": "https://moocs.iniad.org/courses/2026/COT000/00/exercise"
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

            report = check_moocs_collect_page_join(
                probe_json=probe_path,
                db_path=db_path,
                download_dir=download_dir,
            )

        self.assertEqual(4, report["total_aio_pages"])
        self.assertEqual(5, report["total_aio_page_urls"])
        self.assertEqual(1, report["invalid_page_urls"])
        self.assertEqual(3, report["unique_aio_page_keys"])
        self.assertEqual(2, report["matched_keys_count"])
        self.assertEqual(1, report["unmatched_keys_count"])
        self.assertAlmostEqual(2 / 3, report["match_ratio"])
        self.assertEqual(3, report["matched_slides_count"])
        self.assertEqual(2, report["matched_slides_with_pdf_path_count"])
        self.assertEqual(1, report["matched_slides_existing_pdf_count"])
        self.assertEqual(["2026/COT000/99/missing"], report["unmatched_key_samples"])
        self.assertEqual(
            ["2026/COT000/00/exercise", "2026/COT000/01/lecture"],
            report["matched_key_samples"],
        )
        self.assertFalse(report["safety"]["pdf_text_read"])
        self.assertFalse(report["safety"]["tantivy_index_read"])
        self.assertFalse(report["safety"]["sensitive_files_read"])


if __name__ == "__main__":
    unittest.main()
