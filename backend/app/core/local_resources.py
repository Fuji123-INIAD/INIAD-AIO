"""Build a local resource index from MOOCs-Collect filesystem artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable


RESOURCE_TYPE_PDF = "pdf"
DISCOVERED_FROM_FILESYSTEM = "filesystem"
COURSE_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z]{2,6}\d{2,4})(?![A-Za-z0-9])"
)
LECTURE_KEY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(\d{1,2}-\d{1,2}|\d{2})(?![A-Za-z0-9])"
)
LECTURE_FOLDER_PATTERN = re.compile(
    r"^(?:[A-Za-z]+-)?(?P<key>\d{1,2}(?:-\d{1,2})?)\s*[_＿]\s*(?P<title>.+)$"
)
YEAR_FOLDER_PATTERN = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class LocalResource:
    resource_id: str
    course_code: str | None
    course_title: str | None
    lecture_key: str | None
    lecture_title: str | None
    title: str
    resource_type: str
    source_url: str | None
    local_path: str
    page_key: str | None
    text_available: bool
    text_cache_path: str | None
    discovered_from: str
    warnings: list[dict[str, str]]


@dataclass(frozen=True)
class LocalResourcePathContext:
    course_title: str | None
    lecture_folder: str | None


@dataclass(frozen=True)
class LocalResourceIndex:
    resources: list[LocalResource]
    warnings: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "resources": [asdict(resource) for resource in self.resources],
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class PdfTextPage:
    page_number: int
    text: str


PdfTextExtractor = Callable[[Path], list[PdfTextPage]]


def build_local_resource_index(
    root: Path,
    *,
    extract_text: bool = False,
    text_cache_dir: Path | None = None,
    text_cache_path_base: Path | None = None,
    extractor: PdfTextExtractor | None = None,
) -> LocalResourceIndex:
    resolved_root = root.expanduser().resolve()
    if not resolved_root.exists():
        return LocalResourceIndex(
            resources=[],
            warnings=[
                {
                    "message": f"Local resource root does not exist: {resolved_root}",
                }
            ],
        )
    if not resolved_root.is_dir():
        return LocalResourceIndex(
            resources=[],
            warnings=[
                {
                    "message": f"Local resource root is not a directory: {resolved_root}",
                }
            ],
        )

    warnings: list[dict[str, str]] = []
    resources = [
        create_pdf_resource(pdf_path, root=resolved_root)
        for pdf_path in iter_pdf_paths(resolved_root, warnings)
    ]
    if extract_text:
        resources = cache_pdf_text_for_resources(
            resources,
            text_cache_dir=text_cache_dir or Path("data/local/text_cache"),
            text_cache_path_base=text_cache_path_base,
            extractor=extractor or extract_pdf_text_layer,
        )
    return LocalResourceIndex(resources=resources, warnings=warnings)


def iter_pdf_paths(root: Path, warnings: list[dict[str, str]]) -> list[Path]:
    pdf_paths: list[Path] = []

    def onerror(error: OSError) -> None:
        warnings.append({"message": f"Could not scan local resource path: {error}"})

    for dirpath, _, filenames in os.walk(root, onerror=onerror):
        directory = Path(dirpath)
        for filename in filenames:
            path = directory / filename
            if path.suffix.lower() == ".pdf":
                pdf_paths.append(path)

    return sorted(pdf_paths, key=normalized_path_string)


def create_pdf_resource(pdf_path: Path, root: Path | None = None) -> LocalResource:
    resolved_pdf_path = pdf_path.expanduser().resolve()
    context = infer_path_context(root, resolved_pdf_path)
    local_path = str(resolved_pdf_path)
    return LocalResource(
        resource_id=stable_resource_id(local_path),
        course_code=infer_course_code(resolved_pdf_path),
        course_title=context.course_title,
        lecture_key=infer_lecture_key(
            resolved_pdf_path,
            lecture_folder=context.lecture_folder,
        ),
        lecture_title=infer_lecture_title(context.lecture_folder),
        title=resolved_pdf_path.name,
        resource_type=RESOURCE_TYPE_PDF,
        source_url=None,
        local_path=local_path,
        page_key=None,
        text_available=False,
        text_cache_path=None,
        discovered_from=DISCOVERED_FROM_FILESYSTEM,
        warnings=[],
    )


def cache_pdf_text_for_resources(
    resources: list[LocalResource],
    *,
    text_cache_dir: Path,
    text_cache_path_base: Path | None = None,
    extractor: PdfTextExtractor,
) -> list[LocalResource]:
    return [
        cache_pdf_text_for_resource(
            resource,
            text_cache_dir=text_cache_dir,
            text_cache_path_base=text_cache_path_base,
            extractor=extractor,
        )
        for resource in resources
    ]


def cache_pdf_text_for_resource(
    resource: LocalResource,
    *,
    text_cache_dir: Path,
    text_cache_path_base: Path | None = None,
    extractor: PdfTextExtractor,
) -> LocalResource:
    pdf_path = Path(resource.local_path)
    try:
        pages = normalize_pdf_text_pages(extractor(pdf_path))
        if not pages:
            return resource_with_text_warning(
                resource,
                "PDF text extraction produced no text.",
            )

        cache_path = write_pdf_text_cache(
            resource,
            pages,
            text_cache_dir=text_cache_dir,
        )
    except Exception as exc:
        return resource_with_text_warning(
            resource,
            f"PDF text extraction failed: {exc}",
        )

    return replace(
        resource,
        text_available=True,
        text_cache_path=display_text_cache_path(cache_path, text_cache_path_base),
        warnings=resource.warnings,
    )


def normalize_pdf_text_pages(pages: list[PdfTextPage]) -> list[PdfTextPage]:
    normalized_pages: list[PdfTextPage] = []
    for page in pages:
        text = page.text.strip()
        if text:
            normalized_pages.append(
                PdfTextPage(page_number=page.page_number, text=text)
            )
    return normalized_pages


def resource_with_text_warning(resource: LocalResource, message: str) -> LocalResource:
    return replace(
        resource,
        text_available=False,
        text_cache_path=None,
        warnings=[*resource.warnings, {"message": message}],
    )


def extract_pdf_text_layer(pdf_path: Path) -> list[PdfTextPage]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required for --extract-text. Install backend requirements."
        ) from exc

    reader = PdfReader(str(pdf_path))
    pages: list[PdfTextPage] = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append(
            PdfTextPage(
                page_number=index,
                text=page.extract_text() or "",
            )
        )
    return pages


def write_pdf_text_cache(
    resource: LocalResource,
    pages: list[PdfTextPage],
    *,
    text_cache_dir: Path,
) -> Path:
    cache_dir = text_cache_dir.expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / safe_text_cache_filename(resource.resource_id)
    cache_payload = {
        "resource_id": resource.resource_id,
        "local_path": resource.local_path,
        "title": resource.title,
        "pages": [asdict(page) for page in pages],
    }
    cache_path.write_text(
        json.dumps(cache_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return cache_path


def safe_text_cache_filename(resource_id: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", resource_id).strip("._")
    return f"{safe_name or 'resource'}.json"


def display_text_cache_path(cache_path: Path, base_path: Path | None) -> str:
    if base_path is not None:
        try:
            return cache_path.resolve().relative_to(
                base_path.expanduser().resolve()
            ).as_posix()
        except ValueError:
            pass
    return cache_path.as_posix()


def stable_resource_id(local_path: str) -> str:
    digest = hashlib.sha256(normalize_local_path(local_path).encode("utf-8")).hexdigest()
    return f"local-resource:{digest}"


def normalize_local_path(local_path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(local_path)))


def normalized_path_string(path: Path) -> str:
    return normalize_local_path(str(path))


def infer_path_context(root: Path | None, pdf_path: Path) -> LocalResourcePathContext:
    if root is None:
        return LocalResourcePathContext(course_title=None, lecture_folder=None)

    resolved_root = root.expanduser().resolve()
    try:
        relative_path = pdf_path.relative_to(resolved_root)
    except ValueError:
        return LocalResourcePathContext(course_title=None, lecture_folder=None)

    parent_parts = list(relative_path.parts[:-1])
    if YEAR_FOLDER_PATTERN.fullmatch(resolved_root.name):
        return LocalResourcePathContext(
            course_title=parent_parts[0] if len(parent_parts) >= 1 else None,
            lecture_folder=parent_parts[1] if len(parent_parts) >= 2 else None,
        )

    if parent_parts and YEAR_FOLDER_PATTERN.fullmatch(parent_parts[0]):
        return LocalResourcePathContext(
            course_title=parent_parts[1] if len(parent_parts) >= 2 else None,
            lecture_folder=parent_parts[2] if len(parent_parts) >= 3 else None,
        )

    if len(parent_parts) >= 2:
        return LocalResourcePathContext(
            course_title=parent_parts[0],
            lecture_folder=parent_parts[1],
        )

    return LocalResourcePathContext(
        course_title=resolved_root.name or None,
        lecture_folder=parent_parts[0] if parent_parts else None,
    )


def infer_course_code(path: Path) -> str | None:
    for value in path_metadata_candidates(path):
        match = COURSE_CODE_PATTERN.search(value)
        if match:
            return match.group(1).upper()
    return None


def infer_lecture_key(path: Path, lecture_folder: str | None = None) -> str | None:
    if lecture_folder is not None:
        parsed_key, _ = parse_lecture_folder(lecture_folder)
        if parsed_key is not None:
            return parsed_key

    for value in path_metadata_candidates(path):
        match = LECTURE_KEY_PATTERN.search(value)
        if match:
            return match.group(1)
    return None


def infer_lecture_title(lecture_folder: str | None) -> str | None:
    if lecture_folder is None:
        return None

    _, parsed_title = parse_lecture_folder(lecture_folder)
    return parsed_title


def parse_lecture_folder(value: str) -> tuple[str | None, str | None]:
    match = LECTURE_FOLDER_PATTERN.match(value.strip())
    if not match:
        return None, None

    title = match.group("title").strip()
    return match.group("key"), title or None


def path_metadata_candidates(path: Path) -> list[str]:
    return [
        path.stem,
        *reversed(path.parts),
    ]


def write_local_resource_index(index: LocalResourceIndex, output_path: Path) -> None:
    resolved_output = output_path.expanduser()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(
        json.dumps(index.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
