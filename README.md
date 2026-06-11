# INIAD-AIO

INIAD-AIO is an experimental assistant project for finding and asking about
INIAD course information, lecture/page locations, assignments, and limited page
body text.

The project is currently **v0.2 Closed Alpha / experimental**. Behavior,
coverage, and operations are not stable yet, and the repository should be
treated as a proof of concept rather than a production-ready service.

## Documentation Policy

This README is only a public entry point. For detailed understanding, give the
project Overview / Context documents to an AI assistant together with the source
code, and let the assistant inspect the current implementation.

Internal operation notes, authenticated page handling, local browser state, and
raw probe data are intentionally not documented here.

## Current Scope

INIAD-AIO currently focuses on:

* Course, lecture, page, material, and assignment search.
* Importing structured course metadata into PostgreSQL.
* Search indexing with Meilisearch.
* Search-backed answers through a FastAPI API.
* Limited RAG over page body text when that text is available directly in HTML.

It should not yet be described as a full lecture-slide or PDF RAG system.

## Tech Stack

Current major components:

* FastAPI backend.
* PostgreSQL as the source of truth.
* Meilisearch for search indexing.
* Gemini API integration for answer generation.
* Playwright-based probing/import experiments.
* Simple frontend served by the backend.
* Docker Compose for local service startup.

## Known Unstable / Incomplete Areas

* Google Slides iframe text extraction is not implemented.
* PDF extraction is not implemented.
* OCR is not implemented.
* Embeddings/vector search are not implemented.
* Authenticated source retrieval is still experimental.
* Import flows and probe data handling may change during Closed Alpha.

## Minimal Local Startup

Create a local `.env` from the example and set your own secret values:

```powershell
Copy-Item .env.example .env
```

Build and start the local services:

```powershell
docker compose up --build -d
```

Initialize the database, then use the API endpoints exposed by the local backend
for import and search workflows:

```text
http://localhost:8000/api/init-db
http://localhost:8000
```

Stop the services:

```powershell
docker compose down
```
