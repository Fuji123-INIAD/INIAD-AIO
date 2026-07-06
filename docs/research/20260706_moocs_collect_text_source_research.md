# MOOCs-Collect Text Source Research

Date: 2026-07-06

## Question

Where does MOOCs-Collect get searchable/displayable slide text if `db.sqlite.slides` has no text columns?

## Local AppData Findings

Root checked:

`%APPDATA%\me.yu7400ki.moocs-collect`

Observed structure:

- `db.sqlite`
- `store.json`
- `search_index/`

No standalone `.html`, `.svg`, `.txt`, `.md`, `.cache`, or local AppData PDF files were found under this root. The PDF paths are stored in SQLite and point to files outside the AppData root.

`search_index/` had Tantivy-style files:

- `.idx`
- `.fieldnorm`
- `.store`
- `.pos`
- `.term`
- `.fast`
- `meta.json`
- `.managed.json`
- lock files

Plain keyword probing found Japanese text fragments in `.store` files, including COT105/08 security-related pages. This confirms the index contains stored text, not only token postings.

## DB Findings

The real DB has:

- `courses`: metadata
- `lectures`: metadata
- `pages`: metadata plus `pages.key`
- `slides`: `page_id`, `idx`, Google Slides `url`, local `pdf_path`, `downloaded_at`

All checked `slides.pdf_path` values were non-null and pointed to existing `.pdf` files, but COT105/08 samples had no extractable text through PyMuPDF or pypdf.

Conclusion: `db.sqlite` is not a body-text store.

## Search Index Findings

MOOCs-Collect source shows `app_data_dir/search_index` is a Tantivy index. Schema fields:

- `key`
- `facet`
- `content`
- `content_ja`
- `content_bi`

The indexed content comes from `SlideContent.get_texts()`, which extracts SVG `aria-label` values from Google Slides embed pages.

AIO can use this path as the primary text provider. Since the Python venv does not include a Tantivy binding, the current implementation uses a conservative `.store` extractor. It filters obvious cross-page contamination and still keeps PDF/OCR/metadata fallbacks.

## Slide URL Findings

All checked `slides.url` hosts were:

- `docs.google.com`

URL pattern:

- `/presentation/d/e/<deck>/embed`
- `/presentation/d/e/<deck>/pubembed`

This matches MOOCs-Collect source code, which scrapes Google Slides iframe URLs from MOOCs pages.

Live DOM probing is intentionally optional because it may require Google/MOOCs authentication. The probe script supports a bounded Playwright mode, but the default path does not use cookies, storage state, or browser profiles.

## AppData File Provider

The real AppData root did not contain useful standalone text files beyond `search_index`. AIO still includes a safe AppData file provider/probe for future versions or changed storage layouts. It skips sensitive path names and does not read PDF/image bodies.

## OCR Fallback

OCR is not the main path. AIO includes:

- native PDF extraction through PyMuPDF/pypdf
- OCRmyPDF fallback when installed
- optional provider status skeletons for PaddleOCR, Docling, and Marker

OCR output is generated only in temporary directories and is not committed.

## AIO Text Extraction Result

Using the real `search_index`, AIO generated `MaterialText` and `MaterialChunk` entries with:

- `source_type = moocs_collect_search_index`
- `extraction_method = search_index`
- `provider = moocs_collect_search_index`

For the query `セキュリティ`, keyword and hybrid searches returned COT105 lecture `08` security materials above metadata-only fallbacks.

## What Can Be Said In The Demo

- MOOCs-Collect SQLite is a metadata ledger, not the text database.
- Searchable text is produced from Google Slides SVG accessibility labels during download.
- The text is stored in a local Tantivy search index under AppData.
- AIO can expose bounded snippets through MaterialText/MaterialChunk.
- If the index cannot be read, AIO says metadata-only and gives the open URL/PDF path where available.

## What Must Not Be Said Or Committed

- Do not commit `db.sqlite`, `search_index`, PDFs, OCR PDFs, cookies, storage state, browser profiles, Claude Desktop config, or `data/local/*`.
- Do not paste long lecture text dumps into docs or commits.
- Do not claim deadline/submission facts that are not in tool results.
