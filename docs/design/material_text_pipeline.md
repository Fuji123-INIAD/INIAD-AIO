# Material Text Pipeline

## Model

`MaterialText` represents one source-level material. It keeps course, lecture, title, source type, extraction method, provider, source URL, local resource ID, bounded warnings, and text.

`MaterialChunk` represents searchable snippets. Chunks keep `source_label`, `open_url`, `source_type`, `provider`, `extraction_method`, and ontology tags so Claude can cite where the snippet came from.

## Source Types

- `pdf_native`
- `pdf_metadata`
- `moocs_collect_slide_text`
- `moocs_html`
- `ocr`
- `unknown`

## Extraction Methods

- `pypdf`
- `pymupdf`
- `metadata_only`
- `moocs_collect_svg_text`
- `moocs_html_parser`
- `ocrmypdf`
- `paddleocr`
- `docling`
- `marker`
- `unknown`

## Fallback Order

1. Material indexes under `data/local/`
2. Transient chunks built from `resource_index.json`
3. Metadata-only chunk when no body text exists

This means the MCP demo can still explain a resource even when PDF text extraction returns zero characters.

## Search

`backend/app/core/material_search.py` supports:

- `keyword`
- `semantic`
- `hybrid`

The semantic path uses the existing deterministic hashed embedding fallback, so no API key is required. Context packs return `summary + items + caution`, not full raw text dumps.

## v1.2 MOOCs-Collect Providers

The real MOOCs-Collect `db.sqlite` is metadata-only. `slides` stores `url`, `pdf_path`, and timestamps, but not body text.

Provider order:

1. `MoocsCollectDbMetadataProvider`: read-only joins across `courses`, `lectures`, `pages`, and `slides`.
2. `MoocsCollectSearchIndexProvider`: reads stored text from AppData `search_index` when available. The source app uses Tantivy fields `content`, `content_ja`, and `content_bi`.
3. `MoocsCollectAppDataFileProvider`: safe local JSON/HTML/SVG/text probe path for future layouts.
4. `MoocsCollectSlideUrlDomProvider`: optional live Playwright probe for Google Slides DOM/SVG/aria-label text.
5. `MoocsCollectPdfPathProvider`: native PDF text extraction through PyMuPDF/pypdf.
6. `PdfOcrFallbackProvider`: optional OCRmyPDF only when installed.
7. Metadata-only fallback.

New source types include:

- `moocs_collect_search_index`
- `moocs_collect_appdata_file`
- `moocs_collect_slide_url_dom`
- `moocs_collect_pdf_native`
- `moocs_collect_pdf_ocr`

Hybrid search demotes metadata-only chunks and skips semantic-only metadata hits unless the query has a keyword match. Exact keyword hits in body text rank above metadata title matches.
