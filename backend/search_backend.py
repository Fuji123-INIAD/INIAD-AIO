from database import get_connection


def search(question: str):
    conn = get_connection()
    conn.row_factory = None
    cur = conn.cursor()

    keyword = question.strip()

    cur.execute("""
    SELECT
        tasks.title,
        tasks.description,
        tasks.deadline,
        courses.name
    FROM tasks
    JOIN courses ON tasks.course_id = courses.id
    WHERE
        courses.name LIKE ?
        OR tasks.title LIKE ?
        OR tasks.description LIKE ?
        OR ? LIKE '%' || tasks.title || '%'
        OR ? LIKE '%' || courses.name || '%'
    LIMIT 5;
    """, (
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%",
        keyword,
        keyword,
    ))

    rows = cur.fetchall()
    conn.close()

    sources = []

    for row in rows:
        title, description, deadline, course_name = row

        sources.append({
            "type": "task",
            "course": course_name,
            "title": title,
            "content": description,
            "deadline": deadline
        })

    return sources
