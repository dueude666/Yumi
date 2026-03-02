from datetime import date
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile

from app.api.schemas import (
    AvailabilityReplaceRequest,
    CourseCreate,
    ExamCreateRequest,
    FinalWeekPlanRequest,
    FixedEventReplaceRequest,
    FixedEventRequest,
    GlossaryTermCreate,
    MaterialIngestRequest,
    NoteSummaryRequest,
    QARequest,
)
from app.core.db import get_db, init_db
from app.rag.repository import add_material_text
from app.services.audio_service import export_anki_csv, list_transcripts, process_audio_upload
from app.services.glossary_service import add_term, list_terms
from app.services.ingest_service import ingest_uploaded_material
from app.services.note_service import summarize_note
from app.services.planner_service import (
    add_fixed_event,
    analyze_plan,
    add_exam,
    export_plan_ics,
    generate_final_week_plan,
    list_availability,
    list_events,
    list_exams,
    list_fixed_events,
    replace_fixed_events,
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


@app.post("/glossary/terms")
def create_glossary_term(payload: GlossaryTermCreate, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    try:
        return add_term(
            conn=conn,
            term=payload.term,
            canonical=payload.canonical,
            description=payload.description,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/glossary/terms")
def get_glossary_terms(conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    return {"terms": list_terms(conn)}


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


@app.post("/courses/{course_id}/materials/upload")
async def ingest_material_upload(
    course_id: int,
    file: UploadFile = File(...),
    source_name: str = Form(default=""),
    conn: Any = Depends(get_conn),
) -> Dict[str, Any]:
    course = conn.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="course not found")

    filename = file.filename or "uploaded_file"
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    try:
        result = ingest_uploaded_material(
            conn=conn,
            course_id=course_id,
            filename=filename,
            file_bytes=file_bytes,
            source_name=source_name or filename,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result


@app.post("/audio/process-upload")
async def process_audio(
    course_id: int = Form(...),
    file: UploadFile = File(...),
    source_name: str = Form(default=""),
    language: str = Form(default=""),
    diarize: bool = Form(default=True),
    model_id: str = Form(default="openai/whisper-small"),
    local_only: bool = Form(default=False),
    conn: Any = Depends(get_conn),
) -> Dict[str, Any]:
    course = conn.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="course not found")

    filename = file.filename or "audio_file.wav"
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    try:
        return process_audio_upload(
            conn=conn,
            course_id=course_id,
            source_name=(source_name or filename).strip(),
            filename=filename,
            file_bytes=file_bytes,
            language=language.strip() or None,
            diarize=bool(diarize),
            model_id=model_id.strip() or "openai/whisper-small",
            local_only=bool(local_only),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/audio/transcripts")
def get_transcripts(
    course_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    conn: Any = Depends(get_conn),
) -> Dict[str, Any]:
    return {"items": list_transcripts(conn, course_id=course_id, limit=limit)}


@app.get("/audio/{transcript_id}/anki.csv")
def get_anki_csv(transcript_id: int, conn: Any = Depends(get_conn)) -> Response:
    try:
        csv_content = export_anki_csv(conn, transcript_id=transcript_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=anki_{transcript_id}.csv"},
    )


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


@app.post("/planner/fixed-events")
def create_fixed_event(payload: FixedEventRequest, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    return add_fixed_event(
        conn=conn,
        title=payload.title,
        weekday=payload.weekday,
        start_time=payload.start_time,
        end_time=payload.end_time,
        event_type=payload.event_type,
    )


@app.put("/planner/fixed-events")
def set_fixed_events(payload: FixedEventReplaceRequest, conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    events = [event.model_dump() for event in payload.events]
    result = replace_fixed_events(conn, events)
    return {"events": result}


@app.get("/planner/fixed-events")
def get_fixed_events(conn: Any = Depends(get_conn)) -> Dict[str, Any]:
    return {"events": list_fixed_events(conn)}


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


@app.get("/planner/analysis")
def get_plan_analysis(
    start_date: date = Query(...),
    end_date: date = Query(...),
    conn: Any = Depends(get_conn),
) -> Dict[str, Any]:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    return analyze_plan(conn, start_date=start_date, end_date=end_date)


@app.get("/planner/export/ics")
def export_ics(
    start_date: date = Query(...),
    end_date: date = Query(...),
    include_fixed: bool = Query(default=True),
    conn: Any = Depends(get_conn),
) -> Response:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    content = export_plan_ics(
        conn,
        start_date=start_date,
        end_date=end_date,
        include_fixed=include_fixed,
    )
    return Response(
        content=content,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=yumi_schedule.ics"},
    )
