import json
from typing import Any, Dict

from app.models.torch_adapter import TorchNLPAdapter


def summarize_note(conn: Any, course_id: int, title: str, content: str) -> Dict[str, Any]:
    adapter = TorchNLPAdapter()
    summary = adapter.summarize(content, max_sentences=4)
    key_points = adapter.extract_keywords(content, top_k=10)

    cursor = conn.execute(
        """
        INSERT INTO notes (course_id, title, content, summary, key_points)
        VALUES (?, ?, ?, ?, ?)
        """,
        (course_id, title, content, summary, json.dumps(key_points, ensure_ascii=False)),
    )
    conn.commit()

    return {
        "note_id": cursor.lastrowid,
        "course_id": course_id,
        "title": title,
        "summary": summary,
        "key_points": key_points,
    }

