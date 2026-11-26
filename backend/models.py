"""Контракты веб-интерфейса."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Point(BaseModel):
    month: int
    value: float | None
    responses: int


class Change(BaseModel):
    first: Point
    latest: Point


class Metric(BaseModel):
    label: str
    value: float | None
    scale: int = 5
    source: str
    month: int | None = None
    change: Change | None = None
    participants: int | None = None


class Series(BaseModel):
    label: str
    points: list[Point]


class Chart(BaseModel):
    id: str
    label: str
    scale: tuple[int, int] = (1, 5)
    unit: str | None = None
    series: list[Series]


class Coverage(BaseModel):
    month: int
    intern_submitted: bool
    mentor_submitted: bool
    submitted_mentors: list[str] = Field(default_factory=list)
    pending_mentors: list[str] = Field(default_factory=list)


class Signal(BaseModel):
    level: Literal["attention", "critical"]
    label: str
    detail: str
    months: list[int]
    source: Literal["monthly", "feedback"]


class InternSummary(BaseModel):
    id: str
    department: str
    satisfaction: float | None
    coverage: list[Coverage]
    signals: list[Signal]


class Comment(BaseModel):
    month: int
    author: str
    question: str
    text: str


class SyncStatus(BaseModel):
    state: Literal["history", "connected", "partial", "error"] = "history"
    checked_at: datetime | None = None
    detail: str | None = None
    sources: list[Literal["interns", "mentors"]] = Field(default_factory=list)


class DashboardData(BaseModel):
    data_version: str
    first_month: int
    last_month: int
    metrics: list[Metric]
    charts: list[Chart]
    sync: SyncStatus


class Overview(DashboardData):
    intern_count: int
    mentor_count: int
    response_count: int
    intern_responses: int
    mentor_responses: int
    interns: list[InternSummary]
    recent_intern_ids: list[str]


class Profile(DashboardData):
    id: str
    department: str
    coverage: list[Coverage]
    signals: list[Signal]
    comments: list[Comment]
    intern_comments: list[Comment]


class Analysis(BaseModel):
    status: Literal["available", "unavailable", "running", "ready", "error"]
    text: str | None = None
    generated_at: datetime | None = None
    error_message: str | None = None
