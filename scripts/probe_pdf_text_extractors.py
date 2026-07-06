"""Compare optional PDF text extractors without making OCR a required dependency."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe PyMuPDF, pypdf, OCRmyPDF, PaddleOCR, Docling, and Marker availability."
    )
    parser.add_argument("pdf_path", type=Path, nargs="?", help="Optional PDF path to inspect.")
    parser.add_argument("--sample-chars", type=int, default=240)
    return parser.parse_args(argv)


def probe_pdf_text_extractors(pdf_path: Path | None, *, sample_chars: int = 240) -> dict[str, Any]:
    providers = [
        probe_pypdf(pdf_path, sample_chars=sample_chars),
        probe_pymupdf(pdf_path, sample_chars=sample_chars),
        probe_ocrmypdf(pdf_path, sample_chars=sample_chars),
        availability_only("paddleocr", "paddleocr"),
        availability_only("docling", "docling"),
        availability_only("marker", "marker"),
        {
            "provider": "moocs_collect_slide_text",
            "available": None,
            "extracted_text_length": None,
            "page_count": None,
            "sample_preview": "",
            "elapsed_seconds": 0,
            "warnings": ["Use scripts/probe_moocs_collect_text_quality.py with db.sqlite."],
        },
    ]
    return {
        "status": "ok",
        "pdf_path": str(pdf_path.expanduser().resolve()) if pdf_path else None,
        "providers": providers,
        "safety": {
            "ocr_output_committed": False,
            "external_api_used": False,
            "missing_optional_dependencies_skip": True,
        },
    }


def probe_pypdf(pdf_path: Path | None, *, sample_chars: int) -> dict[str, Any]:
    if importlib.util.find_spec("pypdf") is None:
        return unavailable("pypdf", "Python package pypdf is not installed.")
    if pdf_path is None:
        return available_without_input("pypdf")
    start = time.perf_counter()
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path.expanduser()))
        texts = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(texts)
        return provider_result("pypdf", True, text, len(texts), start, sample_chars)
    except Exception as exc:
        return failed("pypdf", exc, start)


def probe_pymupdf(pdf_path: Path | None, *, sample_chars: int) -> dict[str, Any]:
    if importlib.util.find_spec("fitz") is None:
        return unavailable("pymupdf", "Python package PyMuPDF/fitz is not installed.")
    if pdf_path is None:
        return available_without_input("pymupdf")
    start = time.perf_counter()
    try:
        import fitz

        document = fitz.open(str(pdf_path.expanduser()))
        try:
            texts = [page.get_text("text") or "" for page in document]
        finally:
            document.close()
        text = "\n".join(texts)
        return provider_result("pymupdf", True, text, len(texts), start, sample_chars)
    except Exception as exc:
        return failed("pymupdf", exc, start)


def probe_ocrmypdf(pdf_path: Path | None, *, sample_chars: int) -> dict[str, Any]:
    executable = shutil.which("ocrmypdf")
    if executable is None:
        return unavailable("ocrmypdf", "ocrmypdf executable is not installed.")
    if pdf_path is None:
        return available_without_input("ocrmypdf")
    start = time.perf_counter()
    try:
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "ocr.pdf"
            completed = subprocess.run(
                [executable, "--skip-text", str(pdf_path.expanduser()), str(output)],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if completed.returncode != 0:
                return {
                    **unavailable("ocrmypdf", completed.stderr.strip()[:500]),
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                }
            return {
                "provider": "ocrmypdf",
                "available": True,
                "extracted_text_length": None,
                "page_count": None,
                "sample_preview": "",
                "elapsed_seconds": round(time.perf_counter() - start, 3),
                "warnings": ["OCR PDF was generated in a temporary directory and not saved."],
            }
    except Exception as exc:
        return failed("ocrmypdf", exc, start)


def availability_only(provider: str, module_name: str) -> dict[str, Any]:
    if importlib.util.find_spec(module_name) is None:
        return unavailable(provider, f"Python package {module_name} is not installed.")
    return available_without_input(provider)


def provider_result(
    provider: str,
    available: bool,
    text: str,
    page_count: int | None,
    start: float,
    sample_chars: int,
) -> dict[str, Any]:
    compact = " ".join(text.split())
    return {
        "provider": provider,
        "available": available,
        "extracted_text_length": len(compact),
        "page_count": page_count,
        "sample_preview": compact[:sample_chars],
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "warnings": [],
    }


def unavailable(provider: str, warning: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "available": False,
        "extracted_text_length": None,
        "page_count": None,
        "sample_preview": "",
        "elapsed_seconds": 0,
        "warnings": [warning],
    }


def available_without_input(provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "available": True,
        "extracted_text_length": None,
        "page_count": None,
        "sample_preview": "",
        "elapsed_seconds": 0,
        "warnings": ["No PDF path was provided; availability only."],
    }


def failed(provider: str, exc: Exception, start: float) -> dict[str, Any]:
    return {
        "provider": provider,
        "available": True,
        "extracted_text_length": 0,
        "page_count": None,
        "sample_preview": "",
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "warnings": [f"{type(exc).__name__}: {exc}"],
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    report = probe_pdf_text_extractors(args.pdf_path, sample_chars=args.sample_chars)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
