import os
from datetime import date, time, timedelta
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

API_BASE = os.getenv("YUMI_API_URL", "http://127.0.0.1:8000")


def api_call(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{API_BASE}{path}"
    try:
        response = requests.request(method=method, url=url, json=payload, timeout=30)
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text
    except requests.RequestException as exc:
        st.error(f"API request failed: {exc}")
        return None


def api_upload(path: str, files: Dict[str, Any], data: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{API_BASE}{path}"
    try:
        response = requests.post(url=url, files=files, data=data or {}, timeout=60)
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
    result = api_call("GET", f"/planner/export/ics?{params}")
    return result if isinstance(result, str) else None


def render_course_sidebar() -> None:
    st.sidebar.header("Course")
    new_course_name = st.sidebar.text_input("Course name", placeholder="Advanced Mathematics")
    new_course_code = st.sidebar.text_input("Course code (optional)", placeholder="MATH101")
    if st.sidebar.button("Create / Get Course", use_container_width=True):
        if not new_course_name.strip():
            st.sidebar.warning("Please input a course name.")
        else:
            payload = {"name": new_course_name.strip(), "code": new_course_code.strip() or None}
            result = api_call("POST", "/courses", payload)
            if result:
                st.sidebar.success(f"Ready: {result['name']}")


def render_exam_section(course_options: Dict[str, int]) -> None:
    st.subheader("Exam Inputs")
    col1, col2, col3, col4, col5 = st.columns(5)
    course_name_default = next(iter(course_options.keys()), "")
    exam_course_name = col1.text_input("Course", value=course_name_default, key="exam_course_name")
    exam_date = col2.date_input("Exam date", value=date.today() + timedelta(days=10), key="exam_date")
    difficulty = col3.slider("Difficulty", 0.0, 1.0, 0.7, 0.05, key="difficulty")
    mastery = col4.slider("Mastery", 0.0, 1.0, 0.4, 0.05, key="mastery")
    credit_weight = col5.slider("Credit weight", 0.0, 1.0, 0.7, 0.05, key="credit_weight")
    if st.button("Add exam"):
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
            if result:
                st.success(f"Added: {result['course_name']} on {result['exam_date']}")

    exam_list = api_call("GET", "/planner/exams") or []
    if exam_list:
        st.dataframe(exam_list, use_container_width=True)
    else:
        st.info("No exams yet.")


def render_availability_section() -> None:
    st.subheader("Weekly Availability")
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    slots: List[Dict[str, Any]] = []
    for idx, day_name in enumerate(weekday_names):
        c0, c1, c2 = st.columns([1, 1, 1])
        enabled = c0.checkbox(day_name, value=idx < 5, key=f"slot_enabled_{idx}")
        start_t = c1.time_input(f"{day_name} start", value=time(19, 0), key=f"slot_start_{idx}")
        end_t = c2.time_input(f"{day_name} end", value=time(22, 0), key=f"slot_end_{idx}")
        if enabled and start_t < end_t:
            slots.append(
                {
                    "weekday": idx,
                    "start_time": start_t.strftime("%H:%M"),
                    "end_time": end_t.strftime("%H:%M"),
                }
            )
    if st.button("Save availability"):
        result = api_call("PUT", "/planner/availability", {"slots": slots})
        if result is not None:
            st.success("Availability updated.")


def render_fixed_events_section() -> None:
    st.subheader("Fixed Events (Conflict Avoidance)")
    f1, f2, f3, f4, f5 = st.columns(5)
    title = f1.text_input("Title", value="Class", key="fixed_title")
    weekday = f2.selectbox("Weekday", options=list(range(7)), format_func=lambda x: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][x], key="fixed_weekday")
    start_t = f3.time_input("Start", value=time(8, 0), key="fixed_start")
    end_t = f4.time_input("End", value=time(10, 0), key="fixed_end")
    event_type = f5.text_input("Type", value="class", key="fixed_type")

    if st.button("Add fixed event"):
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
            if result:
                st.success("Fixed event added.")

    if st.button("Clear all fixed events"):
        result = api_call("PUT", "/planner/fixed-events", {"events": []})
        if result is not None:
            st.success("All fixed events removed.")

    fixed_events = api_call("GET", "/planner/fixed-events")
    items = fixed_events.get("events", []) if isinstance(fixed_events, dict) else []
    if items:
        st.dataframe(items, use_container_width=True)
    else:
        st.info("No fixed events.")


def render_plan_generation_section() -> None:
    st.subheader("Final-Week Plan")
    p1, p2, p3, p4, p5 = st.columns(5)
    plan_start = p1.date_input("Start date", value=date.today(), key="plan_start")
    plan_end = p2.date_input("End date", value=date.today() + timedelta(days=6), key="plan_end")
    deep_block = p3.number_input("Deep (min)", min_value=30, max_value=180, value=90, step=15, key="deep_block")
    review_block = p4.number_input("Review (min)", min_value=15, max_value=90, value=30, step=15, key="review_block")
    buffer_ratio = p5.slider("Buffer ratio", min_value=0.0, max_value=0.5, value=0.2, step=0.05, key="buffer_ratio")

    if st.button("Generate plan"):
        payload = {
            "start_date": plan_start.isoformat(),
            "end_date": plan_end.isoformat(),
            "deep_block_minutes": int(deep_block),
            "review_block_minutes": int(review_block),
            "buffer_ratio": float(buffer_ratio),
        }
        plan_result = api_call("POST", "/planner/final-week-plan", payload)
        if isinstance(plan_result, dict):
            st.session_state["latest_plan_events"] = plan_result.get("events", [])
            st.success(f"Generated {plan_result.get('count', 0)} events.")

    latest_events = st.session_state.get("latest_plan_events", [])
    if latest_events:
        st.dataframe(latest_events, use_container_width=True)

    if st.button("Run analysis"):
        result = api_call(
            "GET",
            f"/planner/analysis?start_date={plan_start.isoformat()}&end_date={plan_end.isoformat()}",
        )
        if isinstance(result, dict):
            st.markdown("**Summary**")
            st.json(
                {
                    "total_events": result.get("total_events"),
                    "total_hours": result.get("total_hours"),
                    "deep_hours": result.get("deep_hours"),
                    "review_hours": result.get("review_hours"),
                    "mandatory_review_hours": result.get("mandatory_review_hours"),
                    "load_stability": result.get("load_stability"),
                }
            )
            by_course = result.get("by_course_hours", {})
            by_day = result.get("by_day_hours", {})
            if by_course:
                st.markdown("**Hours by course**")
                st.bar_chart(by_course)
            if by_day:
                st.markdown("**Hours by day**")
                st.bar_chart(by_day)

    include_fixed = st.checkbox("Include fixed events in ICS", value=True)
    if st.button("Prepare ICS download"):
        ics_content = fetch_ics(plan_start, plan_end, include_fixed)
        if ics_content:
            st.download_button(
                "Download yumi_schedule.ics",
                data=ics_content,
                file_name="yumi_schedule.ics",
                mime="text/calendar",
            )


def render_note_tab(course_options: Dict[str, int]) -> None:
    st.subheader("Note Summarization")
    if not course_options:
        st.info("Create a course first.")
        return
    note_course = st.selectbox("Course", options=list(course_options.keys()), key="note_course")
    note_title = st.text_input("Title", value="Lecture Summary")
    note_content = st.text_area("Content", height=240)
    if st.button("Generate summary"):
        if not note_content.strip():
            st.warning("Content is required.")
            return
        payload = {
            "course_id": course_options[note_course],
            "title": note_title.strip() or "Lecture Summary",
            "content": note_content.strip(),
        }
        result = api_call("POST", "/notes/summarize", payload)
        if isinstance(result, dict):
            st.markdown("**Summary**")
            st.write(result.get("summary", ""))
            st.markdown("**Keywords**")
            st.write(", ".join(result.get("key_points", [])))


def render_qa_tab(course_options: Dict[str, int]) -> None:
    st.subheader("Local QA")
    labels = ["All courses"] + list(course_options.keys())
    qa_course = st.selectbox("Scope", options=labels)
    qa_top_k = st.slider("Top-k chunks", min_value=1, max_value=10, value=4)
    question = st.text_input("Question", placeholder="What are common applications of Taylor expansion?")
    if st.button("Ask"):
        if not question.strip():
            st.warning("Question is required.")
            return
        payload = {
            "question": question.strip(),
            "course_id": None if qa_course == "All courses" else course_options[qa_course],
            "top_k": qa_top_k,
        }
        result = api_call("POST", "/qa/ask", payload)
        if isinstance(result, dict):
            st.markdown("**Answer**")
            st.write(result.get("answer", ""))
            st.markdown("**Sources**")
            st.dataframe(result.get("sources", []), use_container_width=True)


def render_material_tab(course_options: Dict[str, int]) -> None:
    st.subheader("Material Ingestion")
    if not course_options:
        st.info("Create a course first.")
        return
    ingest_course = st.selectbox("Course", options=list(course_options.keys()), key="ingest_course")
    source_name = st.text_input("Source name", value="lecture_notes.txt")
    page_number = st.number_input("Page number", min_value=1, value=1, step=1)
    text = st.text_area("Material text", height=240)
    if st.button("Ingest material"):
        if not text.strip():
            st.warning("Material text is required.")
            return
        payload = {
            "source_name": source_name.strip() or "manual_input",
            "text": text.strip(),
            "page_number": int(page_number),
        }
        result = api_call(
            "POST",
            f"/courses/{course_options[ingest_course]}/materials",
            payload,
        )
        if isinstance(result, dict):
            st.success(f"Inserted {result['inserted_chunks']} chunks.")

    st.markdown("---")
    st.subheader("File Upload (PDF / OCR)")
    uploaded = st.file_uploader(
        "Upload file",
        type=["txt", "md", "pdf", "png", "jpg", "jpeg", "bmp", "tiff"],
        accept_multiple_files=False,
    )
    upload_source_name = st.text_input(
        "Source alias (optional)",
        value="",
        placeholder="defaults to filename",
    )
    if st.button("Ingest uploaded file"):
        if uploaded is None:
            st.warning("Please choose a file first.")
            return
        files = {
            "file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream"),
        }
        data = {"source_name": upload_source_name.strip() or uploaded.name}
        result = api_upload(
            path=f"/courses/{course_options[ingest_course]}/materials/upload",
            files=files,
            data=data,
        )
        if isinstance(result, dict):
            st.success(
                "Uploaded successfully: "
                f"{result.get('inserted_chunks', 0)} chunks, "
                f"{result.get('ingested_pages', 0)} pages."
            )


def main() -> None:
    st.set_page_config(page_title="Yumi", page_icon="Y", layout="wide")
    st.title("Yumi - Local Campus Study Assistant")
    st.caption("Offline deployment | Local data only")

    health = api_call("GET", "/health")
    if isinstance(health, dict):
        st.success(f"API status: {health.get('status')}")

    render_course_sidebar()
    courses = fetch_courses()
    course_options = {item["name"]: item["course_id"] for item in courses}

    tabs = st.tabs(["Planner", "Notes", "QA", "Materials"])

    with tabs[0]:
        render_exam_section(course_options)
        render_availability_section()
        render_fixed_events_section()
        render_plan_generation_section()

    with tabs[1]:
        render_note_tab(course_options)

    with tabs[2]:
        render_qa_tab(course_options)

    with tabs[3]:
        render_material_tab(course_options)


if __name__ == "__main__":
    main()
