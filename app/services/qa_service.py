from typing import Any, Dict, Optional

from app.models.torch_adapter import TorchNLPAdapter
from app.rag.repository import retrieve_chunks


def ask_local_question(
    conn: Any, question: str, course_id: Optional[int] = None, top_k: int = 4
) -> Dict[str, Any]:
    chunks = retrieve_chunks(conn, question=question, course_id=course_id, top_k=top_k)
    adapter = TorchNLPAdapter()
    answer = adapter.answer_from_context(question, [item["chunk_text"] for item in chunks])

    sources = []
    for item in chunks:
        sources.append(
            {
                "course_name": item["course_name"],
                "source_name": item["source_name"],
                "page_number": item["page_number"],
                "score": item["score"],
                "excerpt": item["chunk_text"][:180],
            }
        )

    return {"answer": answer, "sources": sources}

