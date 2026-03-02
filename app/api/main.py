from datetime import date
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, Query

from app.api.schemas import (
    AvailabilityReplaceRequest,
    CourseCreate,
    ExamCreateRequest,
    FinalWeekPlanRequest,
    MaterialIngestRequest,
    NoteSummaryRequest,
    QARequest,
)
from app.core.db import get_db, init_db
from app.rag.repository import add_material_text
from app.services.note_service import summarize_note
from app.services.planner_service import (
    add_exam,
    generate_final_week_plan,
    list_availability,
    list_events,
    list_exams,
    replace_availability,
)
from app.services.qa_service import ask_local_question

app = FastAPI(title="Yumi API", version="0.1.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def get_conn():
    with get_db() as conn:
        yield conn


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "yumi-api"}


@app.post("/courses")
def create_course(payload: CourseCreate, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    existing = conn.execute("SELECT id, name, code FROM courses WHERE name = ?", (payload.name,)).fetchone()
    if existing:
        return {"course_id": int(existing["id"]), "name": existing["name"], "code": existing["code"]}

    cursor = conn.execute(
        "INSERT INTO courses (name, code) VALUES (?, ?)",
        (payload.name, payload.code),
    )
    conn.commit()
    return {"course_id": int(cursor.lastrowid), "name": payload.name, "code": payload.code}


@app.get("/courses")
def get_courses(conn: Any = Depends(get_conn)) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, code, created_at FROM courses ORDER BY created_at DESC, name ASC"
    ).fetchall()
    return [
        {
            "course_id": int(row["id"]),
            "name": row["name"],
            "code": row["code"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@app.post("/courses/{course_id}/materials")
def ingest_material(course_id: int, payload: MaterialIngestRequest, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    course = conn.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="course not found")

    inserted_chunks = add_material_text(
        conn=conn,
        course_id=course_id,
        source_name=payload.source_name,
        text=payload.text,
        page_number=payload.page_number,
    )
    return {"course_id": course_id, "inserted_chunks": inserted_chunks}


@app.post("/notes/summarize")
def summarize(payload: NoteSummaryRequest, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    course = conn.execute("SELECT id FROM courses WHERE id = ?", (payload.course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="course not found")
    return summarize_note(conn, payload.course_id, payload.title, payload.content)


@app.post("/qa/ask")
def ask(payload: QARequest, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    return ask_local_question(
        conn=conn,
        question=payload.question,
        course_id=payload.course_id,
        top_k=payload.top_k,
    )


@app.post("/planner/exams")
def create_exam(payload: ExamCreateRequest, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    return add_exam(
        conn=conn,
        course_name=payload.course_name,
        exam_date=payload.exam_date,
        difficulty=payload.difficulty,
        mastery=payload.mastery,
        credit_weight=payload.credit_weight,
    )


@app.get("/planner/exams")
def get_exams(conn: Any = Depends(get_conn)) -> List[Dict[str, Any]]:
    return list_exams(conn)


@app.put("/planner/availability")
def set_availability(payload: AvailabilityReplaceRequest, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    slots = [slot.model_dump() for slot in payload.slots]
    result = replace_availability(conn, slots)
    return {"slots": result}


@app.get("/planner/availability")
def get_availability(conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    return {"slots": list_availability(conn)}


@app.post("/planner/final-week-plan")
def build_final_week_plan(payload: FinalWeekPlanRequest, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    events = generate_final_week_plan(
        conn=conn,
        start_date=payload.start_date,
        end_date=payload.end_date,
        deep_block_minutes=payload.deep_block_minutes,
        review_block_minutes=payload.review_block_minutes,
        buffer_ratio=payload.buffer_ratio,
    )
    return {"events": events, "count": len(events)}


@app.get("/planner/events")
def get_plan_events(
    start_date: date = Query(...),
    end_date: date = Query(...),
    conn: Any = Depends(get_conn),
) -> Dict[str, Any]:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    events = list_events(conn, start_date=start_date, end_date=end_date)
    return {"events": events, "count": len(events)}

