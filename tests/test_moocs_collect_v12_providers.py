from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.app.core.material_chunks import MaterialChunk
from backend.app.core.material_search import search_material_chunks
from backend.app.core.moocs_collect_text import (
    load_metadata_records,
    load_moocs_collect_material_texts,
    open_readonly_database,
    parse_slide_url_kind,
)
from scripts.demo_aio_mcp_chat_flow import parse_args as parse_demo_args
from scripts.probe_moocs_collect_files import probe_moocs_collect_files
from scripts.probe_moocs_collect_search_index import probe_moocs_collect_search_index


def create_realistic_moocs_db(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE courses (
                id INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                sort_index INTEGER NOT NULL
            );
            CREATE TABLE lectures (
                id INTEGER PRIMARY KEY,
                course_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                sort_index INTEGER NOT NULL
            );
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY,
                lecture_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                sort_index INTEGER NOT NULL,
                key TEXT NOT NULL
            );
            CREATE TABLE slides (
                id INTEGER PRIMARY KEY,
                page_id INTEGER NOT NULL,
                idx INTEGER NOT NULL,
                url TEXT NOT NULL,
                pdf_path TEXT,
                downloaded_at INTEGER DEFAULT 0 NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO courses VALUES (1, 2026, 'COT105', '情報連携学概論 I', 1)"
        )
        connection.execute(
            "INSERT INTO lectures VALUES (1, 1, '08', '08: セキュリティ', 8)"
        )
        connection.execute(
            "INSERT INTO pages VALUES (1, 1, '04', 'Part2', 4, '2026/COT105/08/04')"
        )
        connection.execute(
            """
            INSERT INTO slides (id, page_id, idx, url, pdf_path)
            VALUES (
                1,
                1,
                0,
                'https://docs.google.com/presentation/d/e/demo/pubembed?start=false',
                'Part2.pdf'
            )
            """
        )
        connection.commit()


def create_tantivy_fixture(root: Path, text: str | None = None) -> Path:
    index = root / "search_index"
    index.mkdir()
    (index / "meta.json").write_text("{}", encoding="utf-8")
    (index / "abc.idx").write_bytes(b"idx")
    payload = text or "2026/COT105/08/04 情報連携学概論 セキュリティ 本文 サンプル 追加テキスト"
    (index / "abc.store").write_bytes(payload.encode("utf-8"))
    return index


class MoocsCollectV12ProviderTests(unittest.TestCase):
    def test_appdata_file_probe_finds_keyword_and_japanese_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "search_index").mkdir()
            (root / "notes.json").write_text(
                '{"text":"2026/COT105/08/04 セキュリティ 本文"}',
                encoding="utf-8",
            )

            report = probe_moocs_collect_files(root, keywords=["セキュリティ"])

        self.assertEqual("ok", report["status"])
        self.assertTrue(report["keyword_hits"])
        self.assertTrue(report["possible_text_sources"])
        self.assertIn(".json", report["extension_counts"])

    def test_search_index_probe_detects_tantivy_and_stored_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index = create_tantivy_fixture(root)

            report = probe_moocs_collect_search_index(index, keywords=["セキュリティ"])

        self.assertEqual("tantivy", report["engine_guess"])
        self.assertTrue(report["stored_documents"])
        self.assertEqual("2026/COT105/08/04", report["stored_documents"][0]["page_key"])

    def test_slide_url_pattern_parser_identifies_google_slides(self) -> None:
        parsed = parse_slide_url_kind(
            "https://docs.google.com/presentation/d/e/2PACX-demo/pubembed?start=false"
        )

        self.assertTrue(parsed["is_google_slides"])
        self.assertFalse(parsed["is_pdf"])
        self.assertEqual("/presentation/d/e/<deck>/pubembed", parsed["path_pattern"])

    def test_db_metadata_provider_reads_real_schema_without_text_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "db.sqlite"
            create_realistic_moocs_db(db_path)

            with closing(open_readonly_database(db_path)) as connection:
                records = load_metadata_records(connection, limit=None, course_code=None, lecture_key=None)
            materials, warnings = load_moocs_collect_material_texts(
                db_path,
                include_search_index=False,
                include_pdf_native=False,
            )

        self.assertEqual([], warnings)
        self.assertEqual(1, len(records))
        self.assertEqual("COT105", records[0].course_code)
        self.assertEqual(1, len(materials))
        self.assertFalse(materials[0].text_available)
        self.assertEqual("pdf_metadata", materials[0].source_type)

    def test_provider_fallback_order_prefers_search_index_over_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "db.sqlite"
            create_realistic_moocs_db(db_path)
            create_tantivy_fixture(root)

            materials, warnings = load_moocs_collect_material_texts(
                db_path,
                moocs_collect_root=root,
                include_pdf_native=False,
            )

        self.assertEqual([], warnings)
        self.assertEqual(1, len(materials))
        self.assertTrue(materials[0].text_available)
        self.assertEqual("moocs_collect_search_index", materials[0].source_type)
        self.assertIn("セキュリティ", materials[0].text)

    def test_metadata_only_hybrid_score_is_demoted_below_text_chunk(self) -> None:
        text_chunk = MaterialChunk(
            chunk_id="text",
            material_id="m1",
            course_code="COT105",
            course_title=None,
            lecture_key="08",
            lecture_title=None,
            title="Part2",
            chunk_index=0,
            chunk_type="slide",
            text="セキュリティの本文",
            text_length=8,
            source_label="Part2",
            open_url=None,
            source_type="moocs_collect_search_index",
            provider="moocs_collect_search_index",
            extraction_method="search_index",
            local_resource_id=None,
        )
        metadata_chunk = MaterialChunk(
            chunk_id="metadata",
            material_id="m2",
            course_code="COT105",
            course_title="情報連携学概論 I",
            lecture_key="08",
            lecture_title="セキュリティ",
            title="Part1",
            chunk_index=0,
            chunk_type="metadata",
            text="情報連携学概論 I / 第08回 セキュリティ / Part1",
            text_length=25,
            source_label="第08回 セキュリティ / Part1",
            open_url=None,
            source_type="pdf_metadata",
            provider="local_resource_index",
            extraction_method="metadata_only",
            local_resource_id=None,
        )

        results = search_material_chunks(
            [metadata_chunk, text_chunk],
            query="セキュリティ",
            mode="hybrid",
        )

        self.assertEqual("text", results[0]["chunk_id"])

    def test_demo_option_parser_accepts_material_filters(self) -> None:
        args = parse_demo_args(
            [
                "--query",
                "セキュリティ",
                "--course-title",
                "情報連携学概論 I",
                "--lecture-key",
                "08",
                "--mode",
                "keyword",
                "--show-source-type",
                "--show-provider",
            ]
        )

        self.assertEqual("セキュリティ", args.query)
        self.assertEqual("情報連携学概論 I", args.course_title)
        self.assertEqual("08", args.lecture_key)
        self.assertTrue(args.show_source_type)
        self.assertTrue(args.show_provider)


if __name__ == "__main__":
    unittest.main()
