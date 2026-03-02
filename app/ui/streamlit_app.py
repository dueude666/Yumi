import os
import socket
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

API_BASE = os.getenv("YUMI_API_URL", "http://127.0.0.1:8000")


def _get_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _parse_hhmm(value: str, default: time) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except (TypeError, ValueError):
        return default


def _inject_css(mobile_mode: bool) -> None:
    if mobile_mode:
        width_style = "max-width: 760px;"
    else:
        width_style = "max-width: 1200px;"
    st.markdown(
        f"""
<style>
.block-container {{
    {width_style}
    padding-top: 1.0rem;
    padding-bottom: 2.0rem;
}}
div[data-testid="stButton"] button {{
    width: 100%;
    min-height: 2.7rem;
    border-radius: 0.6rem;
    font-weight: 600;
}}
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {{
    border-radius: 0.6rem;
}}
div[data-testid="stDataFrame"] {{
    border-radius: 0.6rem;
    overflow: hidden;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def api_call(method: str, path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 35) -> Any:
    url = f"{API_BASE}{path}"
    try:
        response = requests.request(method=method, url=url, json=payload, timeout=timeout)
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text
    except requests.RequestException as exc:
        st.error(f"API request failed: {exc}")
        return None


def api_upload(path: str, files: Dict[str, Any], data: Optional[Dict[str, Any]] = None, timeout: int = 1800) -> Any:
    url = f"{API_BASE}{path}"
    try:
        response = requests.post(url=url, files=files, data=data or {}, timeout=timeout)
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text
    except requests.RequestException as exc:
        st.error(f"Upload failed: {exc}")
        return None


def fetch_courses() -> List[Dict[str, Any]]:
    result = api_call("GET", "/courses")
    return result if isinstance(result, list) else []


def fetch_ics(start_date: date, end_date: date, include_fixed: bool) -> Optional[str]:
    params = (
        f"start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
        f"&include_fixed={'true' if include_fixed else 'false'}"
    )
    result = api_call("GET", f"/planner/export/ics?{params}", timeout=60)
    return result if isinstance(result, str) else None


def fetch_anki_csv(transcript_id: int) -> Optional[str]:
    result = api_call("GET", f"/audio/{transcript_id}/anki.csv", timeout=60)
    return result if isinstance(result, str) else None


def render_records(records: List[Dict[str, Any]], empty_text: str, mobile_mode: bool) -> None:
    if not records:
        st.info(empty_text)
        return

    if mobile_mode:
        for idx, item in enumerate(records, start=1):
            title = (
                item.get("title")
                or item.get("source_name")
                or item.get("course_name")
                or item.get("term")
                or f"Record {idx}"
            )
            with st.expander(str(title), expanded=False):
                for k, v in item.items():
                    st.write(f"**{k}**: {v}")
    else:
        st.dataframe(records, use_container_width=True)


def render_sidebar() -> tuple[str, bool]:
    st.sidebar.title("Yumi")
    mobile_mode = st.sidebar.toggle("Mobile mode", value=True)
    st.session_state["mobile_mode"] = mobile_mode

    st.sidebar.caption(f"API: `{API_BASE}`")
    st.sidebar.markdown("---")

    st.sidebar.subheader("Quick Course")
    with st.sidebar.form("course_create_form", clear_on_submit=True):
        name = st.text_input("Course name")
        code = st.text_input("Course code")
        submitted = st.form_submit_button("Create / Get")
    if submitted:
        if not name.strip():
            st.sidebar.warning("Course name is required.")
        else:
            payload = {"name": name.strip(), "code": code.strip() or None}
            result = api_call("POST", "/courses", payload)
            if isinstance(result, dict):
                st.sidebar.success(f"Ready: {result['name']}")

    nav = st.sidebar.radio(
        "Navigation",
        [
            "Dashboard",
            "Planner",
            "Notes",
            "QA",
            "Materials",
            "Audio Assistant",
        ],
    )
    return nav, mobile_mode


def render_header() -> None:
    st.title("Yumi - Mobile Ready Campus Study Assistant")
    lan_ip = _get_local_ip()
    ui_port = os.getenv("YUMI_UI_PORT", "8501")
    st.caption(
        f"Phone access (same Wi-Fi): http://{lan_ip}:{ui_port} | "
        "Offline inference + local data only"
    )

    health = api_call("GET", "/health")
    if isinstance(health, dict):
        st.success(f"API status: {health.get('status')}")
    else:
        st.warning("API is not reachable. Start backend first.")


def render_dashboard_page(courses: List[Dict[str, Any]], mobile_mode: bool) -> None:
    st.subheader("Overview")
    exams = api_call("GET", "/planner/exams")
    terms = api_call("GET", "/glossary/terms")
    transcripts = api_call("GET", "/audio/transcripts?limit=10")

    course_count = len(courses)
    exam_count = len(exams) if isinstance(exams, list) else 0
    term_count = len(terms.get("terms", [])) if isinstance(terms, dict) else 0
    transcript_count = len(transcripts.get("items", [])) if isinstance(transcripts, dict) else 0

    if mobile_mode:
        st.metric("Courses", course_count)
        st.metric("Exams", exam_count)
        st.metric("Glossary Terms", term_count)
        st.metric("Recent Transcripts", transcript_count)
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Courses", course_count)
        c2.metric("Exams", exam_count)
        c3.metric("Glossary Terms", term_count)
        c4.metric("Recent Transcripts", transcript_count)

    st.markdown("### Mobile Workflow")
    st.write("1. Add course -> 2. Upload notes/audio -> 3. Generate summary/QA -> 4. Export calendar/Anki")


def render_planner_page(courses: List[Dict[str, Any]], mobile_mode: bool) -> None:
    course_options = {item["name"]: item["course_id"] for item in courses}

    st.subheader("Exams")
    with st.form("planner_exam_form", clear_on_submit=True):
        exam_course_name = st.text_input("Course", value=next(iter(course_options.keys()), ""))
        exam_date = st.date_input("Exam date", value=date.today() + timedelta(days=10))
        difficulty = st.slider("Difficulty", 0.0, 1.0, 0.7, 0.05)
        mastery = st.slider("Mastery", 0.0, 1.0, 0.4, 0.05)
        credit_weight = st.slider("Credit weight", 0.0, 1.0, 0.7, 0.05)
        add_exam = st.form_submit_button("Add exam")

    if add_exam:
        if not exam_course_name.strip():
            st.warning("Course is required.")
        else:
            payload = {
                "course_name": exam_course_name.strip(),
                "exam_date": exam_date.isoformat(),
                "difficulty": difficulty,
                "mastery": mastery,
                "credit_weight": credit_weight,
            }
            result = api_call("POST", "/planner/exams", payload)
            if isinstance(result, dict):
                st.success(f"Added: {result['course_name']} ({result['exam_date']})")

    exam_list = api_call("GET", "/planner/exams")
    render_records(
        exam_list if isinstance(exam_list, list) else [],
        empty_text="No exams yet.",
        mobile_mode=mobile_mode,
    )

    st.markdown("---")
    st.subheader("Weekly Availability")
    saved_slots = api_call("GET", "/planner/availability")
    slot_map: Dict[int, Dict[str, str]] = {}
    if isinstance(saved_slots, dict):
        for item in saved_slots.get("slots", []):
            slot_map[int(item["weekday"])] = {"start": item["start_time"], "end": item["end_time"]}

    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    slots: List[Dict[str, Any]] = []
    for idx, day_name in enumerate(weekday_names):
        default_start = _parse_hhmm(slot_map.get(idx, {}).get("start"), time(19, 0))
        default_end = _parse_hhmm(slot_map.get(idx, {}).get("end"), time(22, 0))
        enabled_default = idx in slot_map
        if mobile_mode:
            enabled = st.checkbox(f"{day_name} enabled", value=enabled_default, key=f"slot_en_{idx}")
            start_t = st.time_input(f"{day_name} start", value=default_start, key=f"slot_st_{idx}")
            end_t = st.time_input(f"{day_name} end", value=default_end, key=f"slot_ed_{idx}")
        else:
            c0, c1, c2 = st.columns([1, 1, 1])
            enabled = c0.checkbox(day_name, value=enabled_default, key=f"slot_en_{idx}")
            start_t = c1.time_input("Start", value=default_start, key=f"slot_st_{idx}")
            end_t = c2.time_input("End", value=default_end, key=f"slot_ed_{idx}")

        if enabled and start_t < end_t:
            slots.append(
                {
                    "weekday": idx,
                    "start_time": start_t.strftime("%H:%M"),
                    "end_time": end_t.strftime("%H:%M"),
                }
            )

    if st.button("Save availability", key="save_availability"):
        result = api_call("PUT", "/planner/availability", {"slots": slots})
        if isinstance(result, dict):
            st.success("Availability saved.")

    st.markdown("---")
    st.subheader("Fixed Events (Conflict Avoidance)")
    with st.form("fixed_event_form", clear_on_submit=True):
        title = st.text_input("Title", value="Class")
        weekday = st.selectbox("Weekday", options=list(range(7)), format_func=lambda x: weekday_names[x])
        start_t = st.time_input("Start time", value=time(8, 0))
        end_t = st.time_input("End time", value=time(10, 0))
        event_type = st.text_input("Type", value="class")
        add_fixed = st.form_submit_button("Add fixed event")

    if add_fixed:
        if not title.strip():
            st.warning("Title is required.")
        elif start_t >= end_t:
            st.warning("End time must be later than start time.")
        else:
            payload = {
                "title": title.strip(),
                "weekday": int(weekday),
                "start_time": start_t.strftime("%H:%M"),
                "end_time": end_t.strftime("%H:%M"),
                "event_type": event_type.strip() or "fixed",
            }
            result = api_call("POST", "/planner/fixed-events", payload)
            if isinstance(result, dict):
                st.success("Fixed event added.")

    if st.button("Clear all fixed events", key="clear_fixed_events"):
        result = api_call("PUT", "/planner/fixed-events", {"events": []})
        if isinstance(result, dict):
            st.success("All fixed events removed.")

    fixed_result = api_call("GET", "/planner/fixed-events")
    fixed_events = fixed_result.get("events", []) if isinstance(fixed_result, dict) else []
    render_records(fixed_events, empty_text="No fixed events.", mobile_mode=mobile_mode)

    st.markdown("---")
    st.subheader("Final-Week Plan")
    plan_start = st.date_input("Plan start", value=date.today(), key="plan_start")
    plan_end = st.date_input("Plan end", value=date.today() + timedelta(days=6), key="plan_end")
    deep_block = st.number_input("Deep minutes", min_value=30, max_value=180, value=90, step=15)
    review_block = st.number_input("Review minutes", min_value=15, max_value=90, value=30, step=15)
    buffer_ratio = st.slider("Buffer ratio", 0.0, 0.5, 0.2, 0.05)

    if st.button("Generate plan", key="generate_plan"):
        payload = {
            "start_date": plan_start.isoformat(),
            "end_date": plan_end.isoformat(),
            "deep_block_minutes": int(deep_block),
            "review_block_minutes": int(review_block),
            "buffer_ratio": float(buffer_ratio),
        }
        result = api_call("POST", "/planner/final-week-plan", payload, timeout=80)
        if isinstance(result, dict):
            st.session_state["latest_plan_events"] = result.get("events", [])
            st.success(f"Generated {result.get('count', 0)} events.")

    render_records(
        st.session_state.get("latest_plan_events", []),
        empty_text="No plan generated yet.",
        mobile_mode=mobile_mode,
    )

    if st.button("Run analysis", key="run_analysis"):
        result = api_call(
            "GET",
            f"/planner/analysis?start_date={plan_start.isoformat()}&end_date={plan_end.isoformat()}",
            timeout=60,
        )
        if isinstance(result, dict):
            st.session_state["plan_analysis"] = result

    analysis = st.session_state.get("plan_analysis")
    if isinstance(analysis, dict):
        st.markdown("**Analysis**")
        st.json(
            {
                "total_events": analysis.get("total_events"),
                "total_hours": analysis.get("total_hours"),
                "deep_hours": analysis.get("deep_hours"),
                "review_hours": analysis.get("review_hours"),
                "mandatory_review_hours": analysis.get("mandatory_review_hours"),
                "load_stability": analysis.get("load_stability"),
            }
        )
        if analysis.get("by_course_hours"):
            st.bar_chart(analysis["by_course_hours"])
        if analysis.get("by_day_hours"):
            st.bar_chart(analysis["by_day_hours"])

    include_fixed = st.checkbox("Include fixed events in ICS", value=True)
    if st.button("Prepare ICS", key="prepare_ics"):
        content = fetch_ics(plan_start, plan_end, include_fixed)
        if content:
            st.session_state["ics_content"] = content
            st.success("ICS ready.")
    ics_content = st.session_state.get("ics_content")
    if isinstance(ics_content, str):
        st.download_button(
            "Download yumi_schedule.ics",
            data=ics_content,
            file_name="yumi_schedule.ics",
            mime="text/calendar",
            key="download_ics",
        )


def render_notes_page(courses: List[Dict[str, Any]], mobile_mode: bool) -> None:
    st.subheader("Note Summarization")
    if not courses:
        st.info("Create a course first.")
        return
    course_options = {item["name"]: item["course_id"] for item in courses}
    with st.form("notes_form"):
        course_name = st.selectbox("Course", options=list(course_options.keys()))
        title = st.text_input("Title", value="Lecture Summary")
        content = st.text_area("Content", height=240)
        submit = st.form_submit_button("Generate summary")

    if submit:
        if not content.strip():
            st.warning("Content is required.")
            return
        payload = {
            "course_id": course_options[course_name],
            "title": title.strip() or "Lecture Summary",
            "content": content.strip(),
        }
        result = api_call("POST", "/notes/summarize", payload, timeout=80)
        if isinstance(result, dict):
            st.markdown("**Summary**")
            st.write(result.get("summary", ""))
            st.markdown("**Keywords**")
            keywords = result.get("key_points", [])
            if isinstance(keywords, list):
                st.write(", ".join(keywords))
            else:
                st.write("")


def render_qa_page(courses: List[Dict[str, Any]], mobile_mode: bool) -> None:
    st.subheader("Local QA")
    course_options = {item["name"]: item["course_id"] for item in courses}
    scope_labels = ["All courses"] + list(course_options.keys())
    question = st.text_input("Question", placeholder="What are common applications of Taylor expansion?")
    scope = st.selectbox("Scope", options=scope_labels)
    top_k = st.slider("Top-k chunks", 1, 10, 4)
    if st.button("Ask", key="ask_qa"):
        if not question.strip():
            st.warning("Question is required.")
            return
        payload = {
            "question": question.strip(),
            "course_id": None if scope == "All courses" else course_options[scope],
            "top_k": top_k,
        }
        result = api_call("POST", "/qa/ask", payload, timeout=80)
        if isinstance(result, dict):
            st.markdown("**Answer**")
            st.write(result.get("answer", ""))
            st.markdown("**Sources**")
            sources = result.get("sources", [])
            if isinstance(sources, list):
                render_records(sources, empty_text="No source.", mobile_mode=mobile_mode)


def render_materials_page(courses: List[Dict[str, Any]], mobile_mode: bool) -> None:
    st.subheader("Material Ingestion")
    if not courses:
        st.info("Create a course first.")
        return
    course_options = {item["name"]: item["course_id"] for item in courses}
    course_name = st.selectbox("Course", options=list(course_options.keys()), key="mat_course")

    with st.form("material_text_form"):
        source_name = st.text_input("Source name", value="lecture_notes.txt")
        page_number = st.number_input("Page number", min_value=1, value=1, step=1)
        text = st.text_area("Material text", height=200)
        submit = st.form_submit_button("Ingest text")
    if submit:
        if not text.strip():
            st.warning("Material text is required.")
        else:
            payload = {
                "source_name": source_name.strip() or "manual_input",
                "text": text.strip(),
                "page_number": int(page_number),
            }
            result = api_call(
                "POST",
                f"/courses/{course_options[course_name]}/materials",
                payload,
                timeout=80,
            )
            if isinstance(result, dict):
                st.success(f"Inserted {result.get('inserted_chunks', 0)} chunks.")

    st.markdown("---")
    st.subheader("File Upload (PDF / OCR)")
    uploaded = st.file_uploader(
        "Upload file",
        type=["txt", "md", "pdf", "png", "jpg", "jpeg", "bmp", "tiff"],
        accept_multiple_files=False,
        key="materials_uploader",
    )
    source_alias = st.text_input("Source alias", value="", placeholder="optional")
    if st.button("Ingest uploaded file", key="upload_material_file"):
        if uploaded is None:
            st.warning("Please choose a file first.")
            return
        files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")}
        data = {"source_name": source_alias.strip() or uploaded.name}
        result = api_upload(
            path=f"/courses/{course_options[course_name]}/materials/upload",
            files=files,
            data=data,
            timeout=180,
        )
        if isinstance(result, dict):
            st.success(
                f"Uploaded: {result.get('inserted_chunks', 0)} chunks, "
                f"{result.get('ingested_pages', 0)} pages."
            )


def render_audio_page(courses: List[Dict[str, Any]], mobile_mode: bool) -> None:
    st.subheader("Classroom Audio Assistant")
    st.caption(
        "Lecture recording -> offline transcription -> structured notes -> flashcards"
    )
    if not courses:
        st.info("Create a course first.")
        return
    course_options = {item["name"]: item["course_id"] for item in courses}

    st.markdown("### Custom Terminology")
    with st.form("glossary_form", clear_on_submit=True):
        term = st.text_input("Term")
        canonical = st.text_input("Canonical")
        description = st.text_input("Description")
        add_term_submit = st.form_submit_button("Add term")
    if add_term_submit:
        if not term.strip():
            st.warning("Term is required.")
        else:
            result = api_call(
                "POST",
                "/glossary/terms",
                {
                    "term": term.strip(),
                    "canonical": canonical.strip(),
                    "description": description.strip(),
                },
            )
            if isinstance(result, dict):
                st.success(f"Term ready: {result.get('term')}")

    glossary = api_call("GET", "/glossary/terms")
    terms = glossary.get("terms", []) if isinstance(glossary, dict) else []
    render_records(terms, empty_text="No glossary terms.", mobile_mode=mobile_mode)

    st.markdown("---")
    st.markdown("### Batch Audio Processing")
    course_name = st.selectbox("Course", options=list(course_options.keys()), key="audio_course_name")
    source_prefix = st.text_input("Source prefix", value="lecture_audio")
    language = st.selectbox("Language hint", options=["", "zh", "en"], format_func=lambda x: "auto" if not x else x)
    model_id = st.text_input("ASR model", value="openai/whisper-small")
    diarize = st.checkbox("Enable simple speaker diarization (A/B)", value=True)
    local_only = st.checkbox("Local model files only", value=False)

    audio_files = st.file_uploader(
        "Upload audio files",
        type=["wav", "mp3", "m4a", "flac", "ogg"],
        accept_multiple_files=True,
        key="audio_upload",
    )

    if st.button("Process batch", key="process_audio_batch"):
        if not audio_files:
            st.warning("Please upload at least one file.")
            return

        progress = st.progress(0.0)
        status_rows: List[Dict[str, Any]] = []
        detail_rows: List[Dict[str, Any]] = []
        total = len(audio_files)
        course_id = course_options[course_name]

        for idx, audio in enumerate(audio_files, start=1):
            files = {"file": (audio.name, audio.getvalue(), audio.type or "application/octet-stream")}
            source_name = f"{source_prefix}_{idx}_{audio.name}"
            data = {
                "course_id": str(course_id),
                "source_name": source_name,
                "language": language,
                "diarize": "true" if diarize else "false",
                "model_id": model_id.strip() or "openai/whisper-small",
                "local_only": "true" if local_only else "false",
            }
            result = api_upload("/audio/process-upload", files=files, data=data, timeout=3600)
            if isinstance(result, dict) and result.get("transcript_id"):
                status_rows.append(
                    {
                        "file": audio.name,
                        "status": "ok",
                        "transcript_id": result.get("transcript_id"),
                        "duration_seconds": result.get("duration_seconds"),
                        "flashcards": result.get("flashcard_count"),
                    }
                )
                detail_rows.append(result)
            else:
                status_rows.append({"file": audio.name, "status": "failed"})

            progress.progress(idx / total, text=f"Processed {idx}/{total}")

        st.session_state["audio_batch_status"] = status_rows
        st.session_state["audio_batch_details"] = detail_rows
        st.success("Batch processing complete.")

    render_records(
        st.session_state.get("audio_batch_status", []),
        empty_text="No batch result yet.",
        mobile_mode=mobile_mode,
    )

    details = st.session_state.get("audio_batch_details", [])
    for item in details:
        tid = int(item.get("transcript_id"))
        with st.expander(f"Transcript #{tid} - {item.get('source_name')}"):
            st.markdown("**Summary**")
            st.write(item.get("summary", ""))
            st.markdown("**Structured Notes**")
            st.json(item.get("structured_notes", {}))
            segments = item.get("speaker_segments", [])
            if isinstance(segments, list) and segments:
                st.markdown("**Speaker Segments**")
                render_records(segments, empty_text="No segments.", mobile_mode=mobile_mode)

            if st.button("Prepare Anki CSV", key=f"anki_prepare_{tid}"):
                csv_content = fetch_anki_csv(tid)
                if csv_content:
                    st.session_state[f"anki_csv_{tid}"] = csv_content
                    st.success("Anki CSV ready.")
            csv_cached = st.session_state.get(f"anki_csv_{tid}")
            if isinstance(csv_cached, str):
                st.download_button(
                    f"Download Anki CSV #{tid}",
                    data=csv_cached,
                    file_name=f"anki_{tid}.csv",
                    mime="text/csv",
                    key=f"anki_download_{tid}",
                )

    st.markdown("---")
    st.markdown("### Recent Transcripts")
    filter_by_course = st.checkbox("Filter by selected course", value=True)
    params = f"?limit=20&course_id={course_options[course_name]}" if filter_by_course else "?limit=20"
    recent = api_call("GET", f"/audio/transcripts{params}")
    items = recent.get("items", []) if isinstance(recent, dict) else []
    render_records(items, empty_text="No transcript records.", mobile_mode=mobile_mode)


def main() -> None:
    st.set_page_config(page_title="Yumi", page_icon="Y", layout="centered")
    nav, mobile_mode = render_sidebar()
    _inject_css(mobile_mode)
    render_header()

    courses = fetch_courses()
    if nav == "Dashboard":
        render_dashboard_page(courses, mobile_mode)
    elif nav == "Planner":
        render_planner_page(courses, mobile_mode)
    elif nav == "Notes":
        render_notes_page(courses, mobile_mode)
    elif nav == "QA":
        render_qa_page(courses, mobile_mode)
    elif nav == "Materials":
        render_materials_page(courses, mobile_mode)
    elif nav == "Audio Assistant":
        render_audio_page(courses, mobile_mode)


if __name__ == "__main__":
    main()

