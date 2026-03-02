from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import torch


@dataclass
class ExamRecord:
    id: int
    course_id: int
    course_name: str
    exam_date: date
    difficulty: float
    mastery: float
    credit_weight: float


@dataclass
class SlotRecord:
    weekday: int
    start_time: str
    end_time: str


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _priority(exam: ExamRecord, ref_date: date) -> float:
    days_to_exam = max((exam.exam_date - ref_date).days, 0)
    urgency = max(0.0, min(1.0, 1 - (days_to_exam / 14.0)))
    return (
        0.35 * urgency
        + 0.30 * (1 - exam.mastery)
        + 0.20 * exam.difficulty
        + 0.15 * exam.credit_weight
    )


def _take_interval(
    intervals: List[Tuple[datetime, datetime]], duration_minutes: int
) -> Optional[Tuple[datetime, datetime]]:
    while intervals:
        start_at, end_at = intervals[0]
        minutes = int((end_at - start_at).total_seconds() // 60)
        if minutes < duration_minutes:
            intervals.pop(0)
            continue

        block_end = start_at + timedelta(minutes=duration_minutes)
        intervals[0] = (block_end, end_at)
        if intervals[0][0] >= intervals[0][1]:
            intervals.pop(0)
        return start_at, block_end
    return None


def ensure_course(conn: Any, course_name: str) -> int:
    row = conn.execute("SELECT id FROM courses WHERE name = ?", (course_name,)).fetchone()
    if row:
        return int(row["id"])
    cursor = conn.execute("INSERT INTO courses (name) VALUES (?)", (course_name,))
    conn.commit()
    return int(cursor.lastrowid)


def add_exam(
    conn: Any,
    course_name: str,
    exam_date: date,
    difficulty: float,
    mastery: float,
    credit_weight: float,
) -> Dict[str, Any]:
    course_id = ensure_course(conn, course_name)
    cursor = conn.execute(
        """
        INSERT INTO exams (course_id, exam_date, difficulty, mastery, credit_weight)
        VALUES (?, ?, ?, ?, ?)
        """,
        (course_id, exam_date.isoformat(), difficulty, mastery, credit_weight),
    )
    conn.commit()
    return {
        "exam_id": int(cursor.lastrowid),
        "course_id": course_id,
        "course_name": course_name,
        "exam_date": exam_date.isoformat(),
        "difficulty": difficulty,
        "mastery": mastery,
        "credit_weight": credit_weight,
    }


def list_exams(conn: Any) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.id, e.course_id, c.name AS course_name, e.exam_date, e.difficulty, e.mastery, e.credit_weight
        FROM exams e
        JOIN courses c ON c.id = e.course_id
        ORDER BY e.exam_date ASC, c.name ASC
        """
    ).fetchall()
    return [
        {
            "exam_id": int(row["id"]),
            "course_id": int(row["course_id"]),
            "course_name": row["course_name"],
            "exam_date": row["exam_date"],
            "difficulty": float(row["difficulty"]),
            "mastery": float(row["mastery"]),
            "credit_weight": float(row["credit_weight"]),
        }
        for row in rows
    ]


def replace_availability(conn: Any, slots: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    conn.execute("DELETE FROM availability_slots")
    for slot in slots:
        conn.execute(
            """
            INSERT INTO availability_slots (weekday, start_time, end_time)
            VALUES (?, ?, ?)
            """,
            (int(slot["weekday"]), slot["start_time"], slot["end_time"]),
        )
    conn.commit()
    return list_availability(conn)


def list_availability(conn: Any) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT weekday, start_time, end_time
        FROM availability_slots
        ORDER BY weekday, start_time
        """
    ).fetchall()
    return [
        {
            "weekday": int(row["weekday"]),
            "start_time": row["start_time"],
            "end_time": row["end_time"],
        }
        for row in rows
    ]


def _fetch_exam_records(conn: Any, start_date: date) -> List[ExamRecord]:
    rows = conn.execute(
        """
        SELECT e.id, e.course_id, c.name AS course_name, e.exam_date, e.difficulty, e.mastery, e.credit_weight
        FROM exams e
        JOIN courses c ON c.id = e.course_id
        WHERE date(e.exam_date) >= date(?)
        ORDER BY e.exam_date ASC
        """,
        (start_date.isoformat(),),
    ).fetchall()

    records: List[ExamRecord] = []
    for row in rows:
        records.append(
            ExamRecord(
                id=int(row["id"]),
                course_id=int(row["course_id"]),
                course_name=row["course_name"],
                exam_date=date.fromisoformat(row["exam_date"]),
                difficulty=float(row["difficulty"]),
                mastery=float(row["mastery"]),
                credit_weight=float(row["credit_weight"]),
            )
        )
    return records


def _fetch_slots_by_weekday(conn: Any) -> Dict[int, List[SlotRecord]]:
    rows = conn.execute(
        """
        SELECT weekday, start_time, end_time
        FROM availability_slots
        ORDER BY weekday ASC, start_time ASC
        """
    ).fetchall()
    result: Dict[int, List[SlotRecord]] = {}
    for row in rows:
        slot = SlotRecord(
            weekday=int(row["weekday"]),
            start_time=row["start_time"],
            end_time=row["end_time"],
        )
        result.setdefault(slot.weekday, []).append(slot)
    return result


def _build_mandatory_review_map(
    exams: Sequence[ExamRecord], start_date: date, end_date: date
) -> Dict[date, List[ExamRecord]]:
    review_map: Dict[date, List[ExamRecord]] = {}
    for exam in exams:
        for delta in (7, 3, 1):
            review_date = exam.exam_date - timedelta(days=delta)
            if start_date <= review_date <= end_date:
                review_map.setdefault(review_date, []).append(exam)
    return review_map


def generate_final_week_plan(
    conn: Any,
    start_date: date,
    end_date: date,
    deep_block_minutes: int = 90,
    review_block_minutes: int = 30,
    buffer_ratio: float = 0.2,
) -> List[Dict[str, Any]]:
    exams = _fetch_exam_records(conn, start_date=start_date)
    if not exams:
        return []

    slots_by_weekday = _fetch_slots_by_weekday(conn)
    if not slots_by_weekday:
        return []

    mandatory_reviews = _build_mandatory_review_map(exams, start_date, end_date)
    created_events: List[Dict[str, Any]] = []

    conn.execute(
        """
        DELETE FROM study_events
        WHERE source = 'planner'
          AND date(start_at) >= date(?)
          AND date(start_at) <= date(?)
        """,
        (start_date.isoformat(), end_date.isoformat()),
    )

    day = start_date
    selection_cursor = 0
    while day <= end_date:
        day_slots = slots_by_weekday.get(day.weekday(), [])
        if not day_slots:
            day += timedelta(days=1)
            continue

        intervals: List[Tuple[datetime, datetime]] = []
        total_minutes = 0
        for slot in day_slots:
            slot_start = datetime.combine(day, _parse_time(slot.start_time))
            slot_end = datetime.combine(day, _parse_time(slot.end_time))
            if slot_end <= slot_start:
                continue
            intervals.append((slot_start, slot_end))
            total_minutes += int((slot_end - slot_start).total_seconds() // 60)

        usable_minutes = int(total_minutes * (1 - buffer_ratio))
        if usable_minutes <= 0:
            day += timedelta(days=1)
            continue

        for exam in mandatory_reviews.get(day, []):
            duration = review_block_minutes
            if usable_minutes < duration:
                break
            block = _take_interval(intervals, duration)
            if not block:
                break
            start_at, end_at = block
            priority = _priority(exam, day) + 0.25
            event = {
                "title": f"{exam.course_name} D-复盘",
                "course_id": exam.course_id,
                "start_at": start_at.isoformat(timespec="minutes"),
                "end_at": end_at.isoformat(timespec="minutes"),
                "event_type": "mandatory_review",
                "priority": round(priority, 4),
                "source": "planner",
            }
            created_events.append(event)
            usable_minutes -= duration

        block_pattern = [("deep", deep_block_minutes), ("deep", deep_block_minutes), ("review", review_block_minutes)]
        block_index = 0
        min_block = min(deep_block_minutes, review_block_minutes)

        while usable_minutes >= min_block:
            mode, duration = block_pattern[block_index % len(block_pattern)]
            block_index += 1
            if usable_minutes < duration and mode == "deep" and usable_minutes >= review_block_minutes:
                mode = "review"
                duration = review_block_minutes
            elif usable_minutes < duration:
                break

            active_exams = [exam for exam in exams if exam.exam_date >= day]
            if not active_exams:
                break

            dynamic_scores = []
            for exam in active_exams:
                base = _priority(exam, start_date)
                daily = _priority(exam, day)
                score = 0.7 * base + 0.3 * daily
                dynamic_scores.append(score)

            score_tensor = torch.tensor(dynamic_scores, dtype=torch.float32)
            ranking = torch.argsort(score_tensor, descending=True).tolist()
            chosen_exam = active_exams[ranking[selection_cursor % len(ranking)]]
            selection_cursor += 1

            block = _take_interval(intervals, duration)
            if not block:
                break
            start_at, end_at = block
            priority = _priority(chosen_exam, day)
            event_type = "deep_study" if mode == "deep" else "review"
            title_suffix = "深度学习" if mode == "deep" else "回顾复盘"

            event = {
                "title": f"{chosen_exam.course_name} {title_suffix}",
                "course_id": chosen_exam.course_id,
                "start_at": start_at.isoformat(timespec="minutes"),
                "end_at": end_at.isoformat(timespec="minutes"),
                "event_type": event_type,
                "priority": round(priority, 4),
                "source": "planner",
            }
            created_events.append(event)
            usable_minutes -= duration

        day += timedelta(days=1)

    for event in created_events:
        conn.execute(
            """
            INSERT INTO study_events (title, course_id, start_at, end_at, event_type, priority, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["title"],
                event["course_id"],
                event["start_at"],
                event["end_at"],
                event["event_type"],
                event["priority"],
                event["source"],
            ),
        )
    conn.commit()
    return created_events


def list_events(conn: Any, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT se.id, se.title, se.course_id, c.name AS course_name, se.start_at, se.end_at, se.event_type, se.priority, se.source
        FROM study_events se
        LEFT JOIN courses c ON c.id = se.course_id
        WHERE date(se.start_at) >= date(?) AND date(se.start_at) <= date(?)
        ORDER BY se.start_at ASC
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchall()

    events: List[Dict[str, Any]] = []
    for row in rows:
        events.append(
            {
                "event_id": int(row["id"]),
                "title": row["title"],
                "course_id": row["course_id"],
                "course_name": row["course_name"],
                "start_at": row["start_at"],
                "end_at": row["end_at"],
                "event_type": row["event_type"],
                "priority": float(row["priority"]),
                "source": row["source"],
            }
        )
    return events

