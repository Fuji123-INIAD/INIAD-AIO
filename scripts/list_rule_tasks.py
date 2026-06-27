"""List generated rule-based task prototypes as JSON."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.course_rules import normalize_course_code
from backend.app.core.task_html_evidence import load_html_evidence_by_course
from backend.app.core.task_slides_evidence import load_slides_evidence_by_course
from backend.app.core.task_generator import generate_course_rule_tasks
from backend.app.core.task_list_composer import compose_task_list_items


DEFAULT_HTML_EVIDENCE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "probe" / "moocs_course_details.json"
)


def build_report(
    course_codes: list[str],
    *,
    html_evidence_path: Path | None = DEFAULT_HTML_EVIDENCE_PATH,
    moocs_collect_db_path: Path | None = None,
) -> dict[str, Any]:
    normalized_course_codes = [normalize_course_code(code) for code in course_codes]
    tasks = []
    warnings = []

    for course_code in normalized_course_codes:
        course_tasks = generate_course_rule_tasks(course_code)
        if not course_tasks:
            warnings.append(
                {
                    "course_code": course_code,
                    "message": "No course rule tasks generated.",
                }
            )
        tasks.extend(course_tasks)

    html_evidence = {}
    slides_evidence = {}
    if html_evidence_path is not None:
        html_evidence, html_warnings = load_html_evidence_by_course(
            normalized_course_codes,
            html_evidence_path,
        )
        warnings.extend(html_warnings)
        slides_evidence, slides_warnings = load_slides_evidence_by_course(
            normalized_course_codes,
            html_evidence_path,
            moocs_collect_db_path=moocs_collect_db_path,
        )
        warnings.extend(slides_warnings)

    items = compose_task_list_items(
        tasks,
        extra_evidence=merge_task_evidence(html_evidence, slides_evidence),
    )
    item_dicts = [task_list_item_summary(item) for item in items]
    return {
        "course_codes": normalized_course_codes,
        "task_count": len(item_dicts),
        "active_count": sum(1 for item in item_dicts if item["active"]),
        "items": item_dicts,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List generated task prototypes from the Course Rule Registry."
    )
    parser.add_argument(
        "course_codes",
        nargs="+",
        help="One or more course codes, such as COT101 SEM101 COT105.",
    )
    parser.add_argument(
        "--moocs-collect-db-path",
        type=Path,
        help="Optional MOOCs-Collect db.sqlite path used read-only for Slides evidence.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(
        json.dumps(
            build_report(
                args.course_codes,
                moocs_collect_db_path=args.moocs_collect_db_path,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def merge_task_evidence(*evidence_maps: dict[str, list[Any]]) -> dict[str, list[Any]]:
    merged: dict[str, list[Any]] = {}
    for evidence_map in evidence_maps:
        for key, evidence_items in evidence_map.items():
            merged.setdefault(key, []).extend(evidence_items)
    return merged


def task_list_item_summary(item: Any) -> dict[str, Any]:
    item_dict = asdict(item)
    item_dict["evidence"] = [
        {
            "type": evidence.type,
            "label": evidence.label,
            "confidence": evidence.confidence,
        }
        for evidence in item.evidence
    ]
    item_dict["evidence_detail_url"] = f"/api/tasks/{item.task_id}/evidence"
    return item_dict


if __name__ == "__main__":
    main()
