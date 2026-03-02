import re
from typing import Any, Dict, List, Tuple


def add_term(
    conn: Any,
    term: str,
    canonical: str = "",
    description: str = "",
) -> Dict[str, Any]:
    clean_term = term.strip()
    if not clean_term:
        raise RuntimeError("term is required")

    existing = conn.execute(
        "SELECT id, term, canonical, description FROM term_dictionary WHERE term = ?",
        (clean_term,),
    ).fetchone()
    if existing:
        return {
            "term_id": int(existing["id"]),
            "term": existing["term"],
            "canonical": existing["canonical"] or "",
            "description": existing["description"] or "",
        }

    cursor = conn.execute(
        """
        INSERT INTO term_dictionary (term, canonical, description)
        VALUES (?, ?, ?)
        """,
        (clean_term, canonical.strip(), description.strip()),
    )
    conn.commit()
    return {
        "term_id": int(cursor.lastrowid),
        "term": clean_term,
        "canonical": canonical.strip(),
        "description": description.strip(),
    }


def list_terms(conn: Any) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, term, canonical, description, created_at
        FROM term_dictionary
        ORDER BY term ASC
        """
    ).fetchall()
    return [
        {
            "term_id": int(row["id"]),
            "term": row["term"],
            "canonical": row["canonical"] or "",
            "description": row["description"] or "",
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _replace_whole_word(text: str, source: str, target: str) -> str:
    if not source:
        return text
    pattern = re.compile(rf"(?<!\w){re.escape(source)}(?!\w)", flags=re.IGNORECASE)
    return pattern.sub(target, text)


def apply_glossary(text: str, terms: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, str]]]:
    normalized = text
    hits: List[Dict[str, str]] = []

    for term_item in terms:
        source = term_item["term"]
        target = term_item["canonical"] or source
        description = term_item.get("description", "")

        is_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in source)
        if is_chinese:
            if source in normalized:
                normalized = normalized.replace(source, target)
                hits.append({"term": source, "canonical": target, "description": description})
        else:
            replaced = _replace_whole_word(normalized, source, target)
            if replaced != normalized:
                normalized = replaced
                hits.append({"term": source, "canonical": target, "description": description})

    return normalized, hits

