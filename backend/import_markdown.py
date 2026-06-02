from pathlib import Path
import re

from database import get_connection, init_db


BASE_DIR = Path(__file__).resolve().parent.parent
LECTURE_DIRS = [
    BASE_DIR / "data" / "obsidian_testdata" / "lectures",
]
TASK_DIRS = [
    BASE_DIR / "data" / "tasks",
    BASE_DIR / "data" / "obsidian_testdata" / "tasks",
]

MARKDOWN_SOURCE_PREFIXES = (
    "data/obsidian_testdata/lectures/",
    "data/obsidian_testdata/tasks/",
    "data/tasks/",
)


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def parse_markdown(path: Path):
    text = read_text(path)
    metadata = {}
    body = text

    if text.startswith("---"):
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
        if match:
            metadata = parse_frontmatter(match.group(1))
            body = text[match.end():]

    title = metadata.get("title") or extract_title(body) or path.stem

    return metadata, title.strip(), body.strip()


def parse_frontmatter(frontmatter: str):
    metadata = {}

    for line in frontmatter.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue

        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        metadata[key.strip()] = value

    return metadata


def extract_title(body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def relative_source_path(path: Path) -> str:
    return path.resolve().relative_to(BASE_DIR).as_posix()


def find_markdown_files(directories):
    files = []
    for directory in directories:
        if directory.exists():
            files.extend(sorted(directory.rglob("*.md")))
    return files


def get_or_create_course(cur, course_name: str) -> int:
    course_name = course_name.strip() or "未設定"

    cur.execute("SELECT id FROM courses WHERE name = ?;", (course_name,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        "INSERT INTO courses (name, instructor, semester) VALUES (?, ?, ?);",
        (course_name, "", ""),
    )
    return cur.lastrowid


def delete_markdown_rows(cur):
    for prefix in MARKDOWN_SOURCE_PREFIXES:
        cur.execute(
            "DELETE FROM lectures WHERE source_path LIKE ?;",
            (f"{prefix}%",),
        )
        cur.execute(
            "DELETE FROM tasks WHERE source_path LIKE ?;",
            (f"{prefix}%",),
        )


def import_lectures(cur):
    imported = 0

    for path in find_markdown_files(LECTURE_DIRS):
        metadata, title, content = parse_markdown(path)
        course_id = get_or_create_course(cur, metadata.get("course", ""))
        date = metadata.get("date", "")
        source_path = relative_source_path(path)

        cur.execute(
            """
            INSERT INTO lectures
                (course_id, title, content, source_path, created_at, date)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (course_id, title or "未設定", content, source_path, date, date),
        )
        imported += 1

    return imported


def import_tasks(cur):
    imported = 0

    for path in find_markdown_files(TASK_DIRS):
        metadata, title, description = parse_markdown(path)
        course_id = get_or_create_course(cur, metadata.get("course", ""))
        deadline = metadata.get("deadline", "")
        source_path = relative_source_path(path)

        cur.execute(
            """
            INSERT INTO tasks
                (course_id, title, description, deadline, source_path)
            VALUES (?, ?, ?, ?, ?);
            """,
            (course_id, title or "未設定", description, deadline, source_path),
        )
        imported += 1

    return imported


def main():
    init_db()
    conn = get_connection()
    cur = conn.cursor()

    delete_markdown_rows(cur)
    lecture_count = import_lectures(cur)
    task_count = import_tasks(cur)

    conn.commit()
    conn.close()

    print(f"Imported lectures: {lecture_count}")
    print(f"Imported tasks: {task_count}")


if __name__ == "__main__":
    main()
