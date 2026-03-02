from typing import Any, Dict, List, Optional

from app.models.torch_adapter import TorchNLPAdapter


def split_text(text: str, chunk_size: int = 480, overlap: int = 80) -> List[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end])
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


def add_material_text(
    conn: Any,
    course_id: int,
    source_name: str,
    text: str,
    page_number: Optional[int] = None,
) -> int:
    chunks = split_text(text)
    inserted = 0
    for chunk in chunks:
        conn.execute(
            """
            INSERT INTO document_chunks (course_id, source_name, page_number, chunk_text)
            VALUES (?, ?, ?, ?)
            """,
            (course_id, source_name, page_number, chunk),
        )
        inserted += 1
    conn.commit()
    return inserted


def retrieve_chunks(
    conn: Any,
    question: str,
    course_id: Optional[int] = None,
    top_k: int = 4,
) -> List[Dict[str, Any]]:
    params: List[Any]
    if course_id is None:
        rows = conn.execute(
            """
            SELECT dc.id, dc.course_id, c.name AS course_name, dc.source_name, dc.page_number, dc.chunk_text
            FROM document_chunks dc
            JOIN courses c ON c.id = dc.course_id
            ORDER BY dc.created_at DESC
            LIMIT 500
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT dc.id, dc.course_id, c.name AS course_name, dc.source_name, dc.page_number, dc.chunk_text
            FROM document_chunks dc
            JOIN courses c ON c.id = dc.course_id
            WHERE dc.course_id = ?
            ORDER BY dc.created_at DESC
            LIMIT 500
            """,
            (course_id,),
        ).fetchall()

    docs = [row["chunk_text"] for row in rows]
    adapter = TorchNLPAdapter()
    scores = adapter.score_overlap(question, docs)
    ranked = list(zip(rows, scores))
    ranked.sort(key=lambda x: x[1], reverse=True)
    selected = ranked[: max(1, top_k)]

    result: List[Dict[str, Any]] = []
    for row, score in selected:
        result.append(
            {
                "chunk_id": row["id"],
                "course_id": row["course_id"],
                "course_name": row["course_name"],
                "source_name": row["source_name"],
                "page_number": row["page_number"],
                "chunk_text": row["chunk_text"],
                "score": round(float(score), 4),
            }
        )
    return result

