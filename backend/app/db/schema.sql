PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    course_code TEXT,
    title TEXT NOT NULL,
    year INTEGER,
    moocs_url TEXT,
    source TEXT NOT NULL,
    source_key TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_course_settings (
    course_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_at TEXT NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS lectures (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    lecture_number INTEGER,
    title TEXT NOT NULL,
    moocs_url TEXT,
    source_key TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    lecture_id TEXT NOT NULL,
    page_number INTEGER,
    title TEXT,
    moocs_url TEXT,
    source_key TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (lecture_id) REFERENCES lectures(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    lecture_id TEXT,
    page_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    deadline_at TEXT,
    moocs_url TEXT,
    source_key TEXT,
    raw_json TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (lecture_id) REFERENCES lectures(id),
    FOREIGN KEY (page_id) REFERENCES pages(id)
);

CREATE TABLE IF NOT EXISTS user_task_status (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('open', 'done', 'ignored')),
    checked_done_at TEXT,
    note TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    lecture_id TEXT,
    page_id TEXT,
    title TEXT,
    material_type TEXT,
    moocs_url TEXT,
    local_path TEXT,
    source_key TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (lecture_id) REFERENCES lectures(id),
    FOREIGN KEY (page_id) REFERENCES pages(id)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id TEXT PRIMARY KEY,
    sync_type TEXT NOT NULL CHECK (
        sync_type IN ('moocs_metadata', 'moocs_collect_pdf', 'search_reindex')
    ),
    status TEXT NOT NULL CHECK (status IN ('running', 'ok', 'error')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    message TEXT,
    detail_json TEXT
);

