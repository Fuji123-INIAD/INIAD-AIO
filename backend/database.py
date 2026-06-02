import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "aio.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        instructor TEXT,
        semester TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        deadline TEXT,
        source_path TEXT,
        FOREIGN KEY (course_id) REFERENCES courses(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS lectures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER,
        title TEXT NOT NULL,
        content TEXT,
        source_path TEXT,
        created_at TEXT,
        FOREIGN KEY (course_id) REFERENCES courses(id)
    );
    """)

    cur.execute("PRAGMA table_info(lectures);")
    lecture_columns = {row[1] for row in cur.fetchall()}
    if "date" not in lecture_columns:
        cur.execute("ALTER TABLE lectures ADD COLUMN date TEXT;")

    cur.execute("SELECT COUNT(*) FROM courses;")
    course_count = cur.fetchone()[0]

    if course_count == 0:
        cur.execute("""
        INSERT INTO courses (name, instructor, semester)
        VALUES (?, ?, ?);
        """, ("情報連携基礎実習Ⅰ", "未設定", "2026春"))

        course_id = cur.lastrowid

        cur.execute("""
        INSERT INTO tasks (course_id, title, description, deadline, source_path)
        VALUES (?, ?, ?, ?, ?);
        """, (
            course_id,
            "task001",
            "これはSQLiteから取得した仮の課題情報です。",
            "2026-06-05",
            "sample"
        ))

        cur.execute("""
        INSERT INTO lectures (course_id, title, content, source_path, created_at)
        VALUES (?, ?, ?, ?, ?);
        """, (
            course_id,
            "第1回講義",
            "これはSQLiteから取得した仮の講義情報です。",
            "sample",
            "2026-05-30"
        ))

    conn.commit()
    conn.close()
