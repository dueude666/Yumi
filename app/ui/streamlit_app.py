import os
from datetime import date, time, timedelta
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

API_BASE = os.getenv("YUMI_API_URL", "http://127.0.0.1:8000")


def api_call(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{API_BASE}{path}"
    try:
        response = requests.request(method=method, url=url, json=payload, timeout=25)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"API 请求失败: {exc}")
        return None


def fetch_courses() -> List[Dict[str, Any]]:
    result = api_call("GET", "/courses")
    if not result:
        return []
    return result


def main() -> None:
    st.set_page_config(page_title="Yumi", page_icon="📘", layout="wide")
    st.title("Yumi - 大学离线学习助手")
    st.caption("本地部署 | 数据不出域 | 期末周学习事件排程")

    health = api_call("GET", "/health")
    if health:
        st.success(f"API 状态: {health.get('status')}")

    st.sidebar.header("课程管理")
    new_course_name = st.sidebar.text_input("课程名称", placeholder="例如：高等数学")
    new_course_code = st.sidebar.text_input("课程代码（可选）", placeholder="MATH101")
    if st.sidebar.button("创建/获取课程", use_container_width=True):
        if not new_course_name.strip():
            st.sidebar.warning("请输入课程名称")
        else:
            payload = {"name": new_course_name.strip(), "code": new_course_code.strip() or None}
            result = api_call("POST", "/courses", payload)
            if result:
                st.sidebar.success(f"课程已就绪: {result['name']}")

    courses = fetch_courses()
    course_options = {item["name"]: item["course_id"] for item in courses}

    tabs = st.tabs(["期末周排程", "笔记总结", "本地问答", "资料导入"])

    with tabs[0]:
        st.subheader("考试信息")
        col1, col2, col3, col4, col5 = st.columns(5)
        course_name_default = next(iter(course_options.keys()), "")
        exam_course_name = col1.text_input("课程名称", value=course_name_default)
        exam_date = col2.date_input("考试日期", value=date.today() + timedelta(days=10))
        difficulty = col3.slider("难度", 0.0, 1.0, 0.7, 0.05)
        mastery = col4.slider("掌握度", 0.0, 1.0, 0.4, 0.05)
        credit_weight = col5.slider("学分权重", 0.0, 1.0, 0.7, 0.05)
        if st.button("添加考试事件"):
            if not exam_course_name.strip():
                st.warning("请输入课程名称")
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
                    st.success(f"已添加考试: {result['course_name']} {result['exam_date']}")

        exam_list = api_call("GET", "/planner/exams") or []
        if exam_list:
            st.dataframe(exam_list, use_container_width=True)
        else:
            st.info("还没有考试数据")

        st.subheader("每周可学习时段")
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        slots: List[Dict[str, Any]] = []
        for idx, day_name in enumerate(weekday_names):
            c0, c1, c2 = st.columns([1, 1, 1])
            enabled = c0.checkbox(day_name, value=idx < 5, key=f"slot_enabled_{idx}")
            start_t = c1.time_input(f"{day_name} 开始", value=time(19, 0), key=f"slot_start_{idx}")
            end_t = c2.time_input(f"{day_name} 结束", value=time(22, 0), key=f"slot_end_{idx}")
            if enabled:
                if start_t >= end_t:
                    st.warning(f"{day_name} 时间段无效，已忽略")
                else:
                    slots.append(
                        {
                            "weekday": idx,
                            "start_time": start_t.strftime("%H:%M"),
                            "end_time": end_t.strftime("%H:%M"),
                        }
                    )

        if st.button("保存可学习时段"):
            result = api_call("PUT", "/planner/availability", {"slots": slots})
            if result is not None:
                st.success("可学习时段已更新")

        st.subheader("生成期末周计划")
        p1, p2, p3, p4, p5 = st.columns(5)
        plan_start = p1.date_input("开始日期", value=date.today())
        plan_end = p2.date_input("结束日期", value=date.today() + timedelta(days=6))
        deep_block = p3.number_input("深度学习(分钟)", min_value=30, max_value=180, value=90, step=15)
        review_block = p4.number_input("回顾复盘(分钟)", min_value=15, max_value=90, value=30, step=15)
        buffer_ratio = p5.slider("机动比例", min_value=0.0, max_value=0.5, value=0.2, step=0.05)

        if st.button("生成计划"):
            payload = {
                "start_date": plan_start.isoformat(),
                "end_date": plan_end.isoformat(),
                "deep_block_minutes": int(deep_block),
                "review_block_minutes": int(review_block),
                "buffer_ratio": float(buffer_ratio),
            }
            plan_result = api_call("POST", "/planner/final-week-plan", payload)
            if plan_result is not None:
                st.session_state["latest_plan_events"] = plan_result.get("events", [])
                st.success(f"已生成 {plan_result.get('count', 0)} 个学习事件")

        latest_events = st.session_state.get("latest_plan_events", [])
        if latest_events:
            st.dataframe(latest_events, use_container_width=True)

    with tabs[1]:
        st.subheader("一键总结笔记")
        if not course_options:
            st.info("先在侧栏创建课程")
        else:
            note_course = st.selectbox("选择课程", options=list(course_options.keys()), key="note_course")
            note_title = st.text_input("笔记标题", value="课堂总结")
            note_content = st.text_area("笔记内容", height=220, placeholder="粘贴课堂笔记或课程内容")
            if st.button("生成摘要"):
                if not note_content.strip():
                    st.warning("请输入笔记内容")
                else:
                    payload = {
                        "course_id": course_options[note_course],
                        "title": note_title.strip() or "课堂总结",
                        "content": note_content.strip(),
                    }
                    result = api_call("POST", "/notes/summarize", payload)
                    if result:
                        st.markdown("**摘要**")
                        st.write(result.get("summary", ""))
                        st.markdown("**关键词**")
                        st.write(", ".join(result.get("key_points", [])))

    with tabs[2]:
        st.subheader("本地问答")
        qa_course_labels = ["全部课程"] + list(course_options.keys())
        qa_course = st.selectbox("问答范围", options=qa_course_labels)
        qa_top_k = st.slider("检索片段数", min_value=1, max_value=10, value=4)
        question = st.text_input("输入问题", placeholder="例如：高数里泰勒展开常见应用有哪些？")
        if st.button("提问"):
            if not question.strip():
                st.warning("请输入问题")
            else:
                payload = {
                    "question": question.strip(),
                    "course_id": None if qa_course == "全部课程" else course_options[qa_course],
                    "top_k": qa_top_k,
                }
                result = api_call("POST", "/qa/ask", payload)
                if result:
                    st.markdown("**回答**")
                    st.write(result.get("answer", ""))
                    st.markdown("**来源**")
                    st.dataframe(result.get("sources", []), use_container_width=True)

    with tabs[3]:
        st.subheader("课程资料导入")
        if not course_options:
            st.info("先在侧栏创建课程")
        else:
            ingest_course = st.selectbox("选择课程", options=list(course_options.keys()), key="ingest_course")
            source_name = st.text_input("资料名称", value="lecture_notes.txt")
            page_number = st.number_input("页码（可选）", min_value=1, value=1, step=1)
            text = st.text_area("资料文本", height=220, placeholder="先 MVP：直接粘贴文本，后续可扩展 PDF/OCR")
            if st.button("导入资料"):
                if not text.strip():
                    st.warning("请输入资料文本")
                else:
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
                    if result:
                        st.success(f"导入完成，新增 {result['inserted_chunks']} 个片段")


if __name__ == "__main__":
    main()

