from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.app.core.material_chunks import chunk_material_texts
from backend.app.core.moocs_collect_text import (
    inspect_moocs_collect_text_quality,
    load_moocs_collect_material_texts,
    open_readonly_database,
)


def create_moocs_collect_text_db(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY,
                key TEXT NOT NULL,
                title TEXT
            );
            CREATE TABLE slides (
                id INTEGER PRIMARY KEY,
                page_id INTEGER NOT NULL,
                idx INTEGER NOT NULL,
                url TEXT,
                pdf_path TEXT,
                svg_text TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO pages (id, key, title) VALUES (?, ?, ?)",
            (1, "2026/COT105/08/lecture", "セキュリティ"),
        )
        connection.executemany(
            "INSERT INTO slides (id, page_id, idx, url, pdf_path, svg_text) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    1,
                    1,
                    1,
                    "https://docs.google.com/presentation/demo",
                    "Part1.pdf",
                    '<svg><g role="img" aria-label="暗号とセキュリティの基本"></g></svg>',
                ),
                (
                    2,
                    1,
                    2,
                    "https://docs.google.com/presentation/demo",
                    "Part1.pdf",
                    '<svg><g role="img" aria-label="認証とアクセス制御"></g></svg>',
                ),
            ],
        )
        connection.commit()


class MoocsCollectTextProviderTests(unittest.TestCase):
    def test_open_readonly_database_rejects_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "db.sqlite"
            create_moocs_collect_text_db(db_path)

            with closing(open_readonly_database(db_path)) as connection:
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("CREATE TABLE forbidden (id INTEGER)")

    def test_loads_slide_svg_text_as_material_and_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "db.sqlite"
            create_moocs_collect_text_db(db_path)
            resources = [
                {
                    "resource_id": "local-resource:test-1",
                    "course_code": "COT105",
                    "course_title": "情報連携学概論 I",
                    "lecture_key": "08",
                    "lecture_title": "セキュリティ",
                    "title": "Part1.pdf",
                    "local_path": str(Path(temp_dir) / "Part1.pdf"),
                }
            ]

            materials, warnings = load_moocs_collect_material_texts(
                db_path,
                local_resources=resources,
            )
            chunks = chunk_material_texts(materials)
            report = inspect_moocs_collect_text_quality(
                db_path,
                local_resources=resources,
                limit=10,
            )

        self.assertEqual([], warnings)
        self.assertEqual(1, len(materials))
        material = materials[0]
        self.assertEqual("moocs_collect_slide_text", material.source_type)
        self.assertEqual("moocs_collect", material.provider)
        self.assertEqual("local-resource:test-1", material.local_resource_id)
        self.assertIn("暗号とセキュリティ", material.text)
        self.assertEqual(2, len(chunks))
        self.assertEqual("slide", chunks[0].chunk_type)
        self.assertEqual("ok", report["status"])
        self.assertEqual(2, report["text_blocks_found"])
        self.assertTrue(report["sample_items"])


if __name__ == "__main__":
    unittest.main()
