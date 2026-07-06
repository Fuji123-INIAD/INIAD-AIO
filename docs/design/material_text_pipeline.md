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
