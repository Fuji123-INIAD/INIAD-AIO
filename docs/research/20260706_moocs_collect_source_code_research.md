# MOOCs-Collect Source Code Research

Date: 2026-07-06

## Scope

Local source checked first:

`C:\Users\iniad\Documents\circle\GeeKEN\Experiments\moocs-collect`

The directory exists and has a `.git` directory. `git status` could not be read from the sandbox because Git reported dubious ownership, but the files were readable.

## Stack

- Rust workspace at the repository root.
- Desktop app under `apps/desktop`.
- Tauri desktop backend under `apps/desktop/src-tauri`.
- Drizzle schema/migrations for SQLite.
- `sqlx` for runtime SQLite access.
- Tantivy for local search.
- `reqwest`, `scraper`, `regex`, `unicode_escape`, `svg2pdf`, `lopdf`, and `lol_html` for MOOCs/Google Slides/SVG/PDF handling.

## Database

`apps/desktop/src-tauri/src/db/mod.rs` resolves:

- `app.path().app_data_dir()/db.sqlite`

The migration and Drizzle schema define:

- `courses(id, year, slug, name, sort_index, created_at, updated_at)`
- `lectures(id, course_id, slug, name, sort_index, created_at, updated_at)`
- `pages(id, lecture_id, slug, name, sort_index, key, created_at, updated_at)`
- `slides(id, page_id, idx, url, pdf_path, downloaded_at)`

No table stores slide body text in SQLite.

## Slide URL And Download Flow

`src/repository/slide.rs` fetches a MOOCs page, finds `iframe` elements, and keeps Google Slides embed/pubembed URLs matching:

`https://docs.google.com/.../presentation/d/.../(embed|pubembed)?...`

`apps/desktop/src-tauri/src/command/download_slides.rs`:

1. Builds a `PageKey`.
2. Fetches page/course/lecture metadata.
3. Calls `collect.get_slides`.
4. Calls `collect.get_slide_content` for each slide URL.
5. Converts SVG slide content to PDF and saves it.
6. Persists `slides.url` and `slides.pdf_path` to SQLite.
7. Indexes the fetched slide content into Tantivy.

## Text Source

`src/repository/slide.rs` fetches the Google Slides embed page and extracts escaped SVG blocks with:

`\\x3csvg.*?\\x3c\\/svg\\x3e`

`src/domain/models/slide.rs` extracts text from each SVG by reading:

`<g role="img" aria-label="...">`

`apps/desktop/src-tauri/src/search/service.rs` indexes:

`slide_content.get_texts().join("\n")`

This text is written to Tantivy fields:

- `key`
- `facet`
- `content`
- `content_ja`
- `content_bi`

The search index path is:

`app_data_dir/search_index`

## PDF Handling

`src/pdf/mod.rs` converts SVG to PDF. During preprocessing it can append transparent `<text>` elements from the same `aria-label` values before conversion. In this environment, PyMuPDF and pypdf returned zero text for the sampled COT105/08 generated PDFs, so AIO cannot rely on normal PDF text extraction as the main path.

## Search Index

MOOCs-Collect uses Tantivy with Japanese and bigram analyzers. Stored fields include the raw content, so AIO can recover text from `search_index` when a Tantivy reader is available. In the current Python venv, the `tantivy` Python binding is not installed, so AIO implements a conservative best-effort `.store` extractor and falls back to metadata/PDF/OCR paths when needed.

## Conclusion

MOOCs-Collect does not store body text in `db.sqlite`. It derives searchable text from Google Slides SVG `aria-label` values during download and stores that text in the Tantivy `search_index`. SQLite is a metadata ledger for courses, lectures, pages, slide URLs, and downloaded PDF paths.

## AIO Reuse

AIO now mirrors this finding:

- DB metadata provider for joins and fallback.
- Search index provider for Tantivy stored text.
- AppData file probe/provider skeleton.
- Slide URL DOM probe path kept optional because it may require live Google/MOOCs authentication.
- PDF native and OCR providers kept as fallback only.

No MOOCs-Collect source code, DB, PDF, cookies, storage state, browser profile, or lecture text dump was copied into AIO.
