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
from backend.app.core.task_generator import generate_course_rule_tasks
from backend.app.core.task_list_composer import compose_task_list_items


def build_report(course_codes: list[str]) -> dict[str, Any]:
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

    items = compose_task_list_items(tasks)
    return {
        "course_codes": normalized_course_codes,
        "task_count": len(items),
        "active_count": sum(1 for item in items if item.active),
        "items": [asdict(item) for item in items],
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(build_report(args.course_codes), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
