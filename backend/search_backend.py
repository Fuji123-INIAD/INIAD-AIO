from datetime import date

from database import get_connection


def search(question: str):
    conn = get_connection()
    conn.row_factory = None
    cur = conn.cursor()

    keyword = question.strip()
    like_keyword = f"%{keyword}%"
    sources = []

    cur.execute("""
    SELECT
        tasks.title,
        tasks.description,
        tasks.deadline,
        tasks.source_path,
        courses.name
    FROM tasks
    JOIN courses ON tasks.course_id = courses.id
    WHERE
        courses.name LIKE ?
        OR tasks.title LIKE ?
        OR tasks.description LIKE ?
        OR tasks.deadline LIKE ?
        OR ? LIKE '%' || tasks.title || '%'
        OR ? LIKE '%' || courses.name || '%'
    LIMIT 5;
    """, (
        like_keyword,
        like_keyword,
        like_keyword,
        like_keyword,
        keyword,
        keyword,
    ))

    task_rows = cur.fetchall()

    for row in task_rows:
        title, description, deadline, source_path, course_name = row
        sources.append({
            "type": "task",
            "course": course_name,
            "title": title,
            "content": description,
            "deadline": deadline,
            "source_path": source_path,
        })

    cur.execute("""
    SELECT
        lectures.title,
        lectures.content,
        lectures.source_path,
        lectures.date,
        courses.name
    FROM lectures
    JOIN courses ON lectures.course_id = courses.id
    WHERE
        courses.name LIKE ?
        OR lectures.title LIKE ?
        OR lectures.content LIKE ?
        OR lectures.date LIKE ?
        OR ? LIKE '%' || lectures.title || '%'
        OR ? LIKE '%' || courses.name || '%'
    LIMIT 5;
    """, (
        like_keyword,
        like_keyword,
        like_keyword,
        like_keyword,
        keyword,
        keyword,
    ))

    lecture_rows = cur.fetchall()

    for row in lecture_rows:
        title, content, source_path, lecture_date, course_name = row
        sources.append({
            "type": "lecture",
            "course": course_name,
            "title": title,
            "content": content,
            "deadline": "",
            "source_path": source_path,
            "date": lecture_date,
        })

    if not sources and _looks_like_task_question(keyword):
        today = date.today().isoformat()
        cur.execute("""
        SELECT
            tasks.title,
            tasks.description,
            tasks.deadline,
            tasks.source_path,
            courses.name
        FROM tasks
        JOIN courses ON tasks.course_id = courses.id
        ORDER BY
            CASE
                WHEN tasks.deadline GLOB '????-??-??'
                    AND tasks.deadline >= ? THEN 0
                WHEN tasks.deadline GLOB '????-??-??' THEN 1
                WHEN tasks.deadline = '' OR tasks.deadline IS NULL THEN 3
                ELSE 2
            END,
            tasks.deadline ASC,
            tasks.id ASC
        LIMIT 5;
        """, (today,))

        for row in cur.fetchall():
            title, description, deadline, source_path, course_name = row
            sources.append({
                "type": "task",
                "course": course_name,
                "title": title,
                "content": description,
                "deadline": deadline,
                "source_path": source_path,
            })

    conn.close()
    return sources


def _looks_like_task_question(keyword: str) -> bool:
    task_words = ("課題", "宿題", "締切", "期限", "今週", "task", "deadline")
    lowered = keyword.lower()
    return any(word in lowered for word in task_words)
