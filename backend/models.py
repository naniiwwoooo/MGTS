"""Контракты веб-интерфейса."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Point(BaseModel):
    month: int
    value: float | None


class Observation(Point):
    responses: int


class Change(BaseModel):
    first: Observation
    latest: Observation


class Metric(BaseModel):
    label: str
    value: float | None
    scale: int | None = None
    unit: str | None = None
    source: str
    month: int | None = None
    change: Change | None = None


class Series(BaseModel):
    label: str
    points: list[Point]


class Chart(BaseModel):
    id: str
    label: str
    scale: tuple[int, int] | None = None
    unit: str | None = None
    series: list[Series]


class InternSummary(BaseModel):
    id: str
    month: int
    satisfaction: float | None
    readiness: float | None
    mentor_month: int | None
    progress: Change | None = None


class Comment(BaseModel):
    month: int
    mentor: str
    text: str


class InternComment(BaseModel):
    month: int
    text: str


class RatingGroup(BaseModel):
    label: str
    count: int


class ProfileAxis(BaseModel):
    label: str
    first: float | None
    last: float | None


class Overview(BaseModel):
    data_version: str
    first_month: int
    last_month: int
    intern_count: int
    mentor_count: int
    response_count: int
    intern_responses: int
    mentor_responses: int
    metrics: list[Metric]
    charts: list[Chart]
    interns: list[InternSummary]
    readiness_distribution: list[RatingGroup]


class Profile(BaseModel):
    data_version: str
    id: str
    month: int
    first_month: int
    last_month: int
    metrics: list[Metric]
    charts: list[Chart]
    comments: list[Comment]
    intern_comments: list[InternComment]
    mentor_progress: Change | None = None
    response_profile: list[ProfileAxis]
    response_months: tuple[int, int]


class Analysis(BaseModel):
    status: Literal["available", "unavailable", "running", "ready", "error"]
    text: str | None = None
    generated_at: datetime | None = None
    error_message: str | None = None
