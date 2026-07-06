"""Optional PDF native text and OCR providers.

OCR dependencies are intentionally optional.  Callers can use these helpers in
fallback paths without making test or demo environments install heavy packages.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


@dataclass(frozen=True)
class PdfTextExtractionResult:
    provider: str
    extraction_method: str
    text: str
    page_count: int | None
    warnings: list[dict[str, str]]

    @property
    def text_available(self) -> bool:
        return bool(self.text.strip())


def extract_pdf_native_text(pdf_path: Path) -> PdfTextExtractionResult:
    """Extract embedded PDF text, preferring PyMuPDF and falling back to pypdf."""
    resolved = pdf_path.expanduser()
    warnings: list[dict[str, str]] = []
    if not resolved.is_file():
        return PdfTextExtractionResult(
            provider="pdf_native",
            extraction_method="metadata_only",
            text="",
            page_count=None,
            warnings=[{"message": f"PDF file not found: {resolved}"}],
        )

    if importlib.util.find_spec("fitz") is not None:
        result = _extract_with_pymupdf(resolved)
        if result.text_available:
            return result
        warnings.extend(result.warnings)

    if importlib.util.find_spec("pypdf") is not None:
        result = _extract_with_pypdf(resolved)
        result_warnings = [*warnings, *result.warnings]
        return PdfTextExtractionResult(
            provider=result.provider,
            extraction_method=result.extraction_method,
            text=result.text,
            page_count=result.page_count,
            warnings=result_warnings,
        )

    warnings.append({"message": "Neither PyMuPDF nor pypdf is installed."})
    return PdfTextExtractionResult(
        provider="pdf_native",
        extraction_method="metadata_only",
        text="",
        page_count=None,
        warnings=warnings,
    )


def _extract_with_pymupdf(pdf_path: Path) -> PdfTextExtractionResult:
    try:
        import fitz

        document = fitz.open(str(pdf_path))
        try:
            pages = [page.get_text("text") or "" for page in document]
        finally:
            document.close()
        text = "\n\n".join(
            f"Page {index}: {page_text.strip()}"
            for index, page_text in enumerate(pages, start=1)
            if page_text.strip()
        )
        return PdfTextExtractionResult(
            provider="pdf_native",
            extraction_method="pymupdf",
            text=compact_text(text),
            page_count=len(pages),
            warnings=[],
        )
    except Exception as exc:
        return PdfTextExtractionResult(
            provider="pdf_native",
            extraction_method="pymupdf",
            text="",
            page_count=None,
            warnings=[{"message": f"PyMuPDF failed: {type(exc).__name__}: {exc}"}],
        )


def _extract_with_pypdf(pdf_path: Path) -> PdfTextExtractionResult:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(
            f"Page {index}: {page_text.strip()}"
            for index, page_text in enumerate(pages, start=1)
            if page_text.strip()
        )
        return PdfTextExtractionResult(
            provider="pdf_native",
            extraction_method="pypdf",
            text=compact_text(text),
            page_count=len(pages),
            warnings=[],
        )
    except Exception as exc:
        return PdfTextExtractionResult(
            provider="pdf_native",
            extraction_method="pypdf",
            text="",
            page_count=None,
            warnings=[{"message": f"pypdf failed: {type(exc).__name__}: {exc}"}],
        )


def extract_pdf_ocr_text(pdf_path: Path) -> PdfTextExtractionResult:
    """Run OCRmyPDF when installed, then read the temporary OCR PDF text."""
    executable = shutil.which("ocrmypdf")
    if executable is None:
        return PdfTextExtractionResult(
            provider="pdf_ocr_fallback",
            extraction_method="ocrmypdf",
            text="",
            page_count=None,
            warnings=[{"message": "OCRmyPDF is not installed; OCR fallback skipped."}],
        )
    resolved = pdf_path.expanduser()
    if not resolved.is_file():
        return PdfTextExtractionResult(
            provider="pdf_ocr_fallback",
            extraction_method="ocrmypdf",
            text="",
            page_count=None,
            warnings=[{"message": f"PDF file not found: {resolved}"}],
        )
    try:
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "ocr.pdf"
            completed = subprocess.run(
                [executable, "--skip-text", str(resolved), str(output)],
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if completed.returncode != 0:
                return PdfTextExtractionResult(
                    provider="pdf_ocr_fallback",
                    extraction_method="ocrmypdf",
                    text="",
                    page_count=None,
                    warnings=[
                        {
                            "message": (
                                "OCRmyPDF failed: "
                                + (completed.stderr.strip()[:500] or completed.stdout.strip()[:500])
                            )
                        }
                    ],
                )
            native = extract_pdf_native_text(output)
            return PdfTextExtractionResult(
                provider="pdf_ocr_fallback",
                extraction_method="ocrmypdf",
                text=native.text,
                page_count=native.page_count,
                warnings=[
                    *native.warnings,
                    {"message": "OCR PDF was generated in a temporary directory and not saved."},
                ],
            )
    except Exception as exc:
        return PdfTextExtractionResult(
            provider="pdf_ocr_fallback",
            extraction_method="ocrmypdf",
            text="",
            page_count=None,
            warnings=[{"message": f"OCRmyPDF failed: {type(exc).__name__}: {exc}"}],
        )


def optional_provider_status() -> list[dict[str, Any]]:
    return [
        {
            "provider": "ocrmypdf",
            "available": shutil.which("ocrmypdf") is not None,
            "kind": "executable",
        },
        {
            "provider": "paddleocr",
            "available": importlib.util.find_spec("paddleocr") is not None,
            "kind": "python",
            "skeleton_only": True,
        },
        {
            "provider": "docling",
            "available": importlib.util.find_spec("docling") is not None,
            "kind": "python",
            "skeleton_only": True,
        },
        {
            "provider": "marker",
            "available": importlib.util.find_spec("marker") is not None,
            "kind": "python",
            "skeleton_only": True,
        },
    ]


def compact_text(value: str) -> str:
    return "\n".join(" ".join(line.split()) for line in str(value or "").splitlines()).strip()
