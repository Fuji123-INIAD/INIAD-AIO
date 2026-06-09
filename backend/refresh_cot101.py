from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from urllib import request

from moocs_probe import (
    DEFAULT_DETAILS_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_PROFILE_DIR,
    DEFAULT_STORAGE_STATE,
    configure_logging,
    probe_course_details,
)


def post_import(api_base_url: str) -> dict:
    url = api_base_url.rstrip("/") + "/api/import-moocs-details"
    req = request.Request(url, data=b"", method="POST")
    with request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch COT101 MOOCs details and import them into PostgreSQL through the running API."
    )
    parser.add_argument("--course-code", default="COT101")
    parser.add_argument("--courses-input", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--details-output", type=Path, default=DEFAULT_DETAILS_OUTPUT_PATH)
    parser.add_argument("--storage-state", type=Path, default=DEFAULT_STORAGE_STATE)
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="Persistent Chromium user data directory for MOOCs login state.",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help="Deprecated alias for --user-data-dir.",
    )
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--lesson-limit", type=int, default=None)
    parser.add_argument("--page-limit", type=int, default=None)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--skip-probe", action="store_true", help="Only import the current details JSON.")
    parser.add_argument("--skip-import", action="store_true", help="Only refresh the details JSON.")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.verbose)
    user_data_dir = args.user_data_dir or args.profile_dir

    if not args.skip_probe:
        details = probe_course_details(
            storage_state=args.storage_state,
            profile_dir=user_data_dir,
            courses_input_path=args.courses_input,
            output_path=args.details_output,
            headless=not args.headed,
            timeout_ms=args.timeout_ms,
            details_limit=None,
            lesson_limit=args.lesson_limit,
            page_limit=args.page_limit,
            course_code=args.course_code,
        )
        lecture_count = sum(len(course.lessons) for course in details)
        page_count = sum(len(lesson.pages) for course in details for lesson in course.lessons)
        material_count = sum(
            len(page.materials)
            for course in details
            for lesson in course.lessons
            for page in lesson.pages
        )
        logging.info(
            "fetched courses=%s lectures=%s pages=%s materials=%s",
            len(details),
            lecture_count,
            page_count,
            material_count,
        )

    if args.skip_import:
        return

    result = post_import(args.api_base_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
