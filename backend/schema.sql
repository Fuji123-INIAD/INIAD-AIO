CREATE TABLE IF NOT EXISTS courses (
    id SERIAL PRIMARY KEY,
    course_code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lectures (
    id SERIAL PRIMARY KEY,
    course_id INTEGER REFERENCES courses(id),
    lecture_number INTEGER,
    title TEXT
);

CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    lecture_id INTEGER REFERENCES lectures(id),
    page_number INTEGER,
    title TEXT,
    url TEXT,
    raw_json JSONB,
    UNIQUE (lecture_id, page_number)
);

CREATE TABLE IF NOT EXISTS materials (
    id SERIAL PRIMARY KEY,
    page_id INTEGER REFERENCES pages(id),
    material_number INTEGER,
    material_type TEXT,
    url TEXT,
    retrieval_method TEXT,
    raw_json JSONB,
    UNIQUE (page_id, material_number)
);

CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    course_id INTEGER REFERENCES courses(id),
    lecture_id INTEGER REFERENCES lectures(id),
    title TEXT NOT NULL,
    status TEXT,
    due_date TIMESTAMP,
    source_type TEXT,
    source_url TEXT,
    raw_json JSONB
);

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS lecture_id INTEGER REFERENCES lectures(id);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS source_type TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS raw_json JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS tasks_course_title_source_url_idx
ON tasks (course_id, title, COALESCE(source_url, ''));
