from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: Optional[str] = Field(default=None, max_length=50)


class GlossaryTermCreate(BaseModel):
    term: str = Field(min_length=1, max_length=100)
    canonical: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=300)


class MaterialIngestRequest(BaseModel):
    source_name: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1)
    page_number: Optional[int] = Field(default=None, ge=1)


class NoteSummaryRequest(BaseModel):
    course_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1)


class QARequest(BaseModel):
    question: str = Field(min_length=1)
    course_id: Optional[int] = Field(default=None, ge=1)
    top_k: int = Field(default=4, ge=1, le=10)


class ExamCreateRequest(BaseModel):
    course_name: str = Field(min_length=1, max_length=100)
    exam_date: date
    difficulty: float = Field(ge=0, le=1)
    mastery: float = Field(ge=0, le=1)
    credit_weight: float = Field(ge=0, le=1)


class AvailabilitySlotRequest(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: str
    end_time: str

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("time format must be HH:MM")
        hour, minute = parts
        if not (hour.isdigit() and minute.isdigit()):
            raise ValueError("time format must be HH:MM")
        h = int(hour)
        m = int(minute)
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError("time format must be HH:MM")
        return f"{h:02d}:{m:02d}"

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, value: str, info):
        start_time = info.data.get("start_time")
        if start_time and value <= start_time:
            raise ValueError("end_time must be later than start_time")
        return value


class AvailabilityReplaceRequest(BaseModel):
    slots: List[AvailabilitySlotRequest]


class FixedEventRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    weekday: int = Field(ge=0, le=6)
    start_time: str
    end_time: str
    event_type: str = Field(default="fixed", min_length=1, max_length=50)

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("time format must be HH:MM")
        hour, minute = parts
        if not (hour.isdigit() and minute.isdigit()):
            raise ValueError("time format must be HH:MM")
        h = int(hour)
        m = int(minute)
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError("time format must be HH:MM")
        return f"{h:02d}:{m:02d}"

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, value: str, info):
        start_time = info.data.get("start_time")
        if start_time and value <= start_time:
            raise ValueError("end_time must be later than start_time")
        return value


class FixedEventReplaceRequest(BaseModel):
    events: List[FixedEventRequest]


class FinalWeekPlanRequest(BaseModel):
    start_date: date
    end_date: date
    deep_block_minutes: int = Field(default=90, ge=30, le=180)
    review_block_minutes: int = Field(default=30, ge=15, le=90)
    buffer_ratio: float = Field(default=0.2, ge=0, le=0.5)
