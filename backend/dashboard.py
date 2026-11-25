"""Подготовка данных для API из общих расчётов стажёрской программы."""

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from pathlib import Path

import pandas as pd

from . import surveys as dl
from .models import Chart, Comment, InternSummary, Metric, Overview, Point, Profile, ProfileAxis, RatingGroup, Series


@dataclass(frozen=True)
class Snapshot:
    version: tuple
    interns: pd.DataFrame
    mentors: pd.DataFrame


def file_version(path: Path) -> tuple:
    stat = path.stat()
    return path, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@lru_cache(maxsize=4)
def read_snapshot(version: tuple) -> Snapshot:
    interns, mentors = dl.load_all()
    if interns.empty:
        raise ValueError("Опрос стажёров пуст")
    if version != current_version():
        raise ValueError("Файлы опросов изменились во время чтения")
    return Snapshot(version, interns, mentors)


def current_version() -> tuple:
    return file_version(dl.INTERN_FILE), file_version(dl.MENTOR_FILE)


def number(value) -> float | None:
    return float(value) if pd.notna(value) and isfinite(value) else None


def series(label: str, data: pd.DataFrame, column: str, months: range) -> Series:
    values = data.set_index(dl.MONTH)[column].reindex(months)
    points = [Point(month=month, value=number(value)) for month, value in values.items()]
    return Series(label=label, points=points)


def interval(data: pd.DataFrame) -> range:
    return range(int(data[dl.MONTH].min()), int(data[dl.MONTH].max()) + 1)


def latest_mentor(data: pd.DataFrame) -> tuple[int | None, float | None]:
    if data.empty:
        return None, None
    latest = data.iloc[-1]
    return int(latest[dl.MONTH]), number(latest[dl.HIRE_READINESS])


def overview(snapshot: Snapshot) -> Overview:
    interns, mentors = snapshot.interns, snapshot.mentors
    totals = dl.overall_metrics(interns, mentors)
    months = interval(interns)
    intern_means = dl.monthly_mean(interns, dl.INTERN_METRICS + [dl.NPS])
    mentor_means = dl.monthly_mean(mentors, dl.MENTOR_METRICS + [dl.HIRE_READINESS])
    hours = mentors.groupby(dl.MONTH, as_index=False)[dl.HOURS].sum(min_count=1)
    metrics = [
        Metric(label="Удовлетворённость", value=number(totals["intern_satisfaction"]), scale=5, source="Среднее по стажёрам"),
        Metric(label="Прогресс", value=number(totals["avg_progress"]), scale=5, source="Средняя оценка наставников"),
        Metric(label="Готовность к найму", value=number(totals["hire_readiness"]), scale=10, source="Средняя оценка наставников"),
    ]
    charts = [
        Chart(id="satisfaction", label="Удовлетворённость", scale=(1, 5), series=[
            series("Стажёры", intern_means, "Удовлетворённость", months),
            series("Наставники", mentor_means, "Удовлетворённость", months),
        ]),
        Chart(id="progress", label="Прогресс", scale=(1, 5), series=[
            series("Самооценка", intern_means, "Прогресс в обучении", months),
            series("Оценка наставников", mentor_means, "Прогресс стажёра", months),
        ]),
        Chart(id="readiness", label="Готовность к найму", scale=(0, 10), series=[
            series("Наставники", mentor_means, dl.HIRE_READINESS, months),
        ]),
        Chart(id="recommendation", label="Готовность рекомендовать", scale=(0, 10), series=[
            series("Стажёры", intern_means, dl.NPS, months),
        ]),
        Chart(id="hours", label="Часы наставничества", unit="ч", series=[
            series("Наставники", hours, dl.HOURS, months),
        ]),
    ]
    directory = []
    for intern_id in dl.intern_ids(interns):
        current = dl.latest_snapshot(interns, intern_id)
        mentor_month, readiness = latest_mentor(dl.mentor_timeline(mentors, intern_id))
        directory.append(InternSummary(
            id=intern_id, month=int(current[dl.MONTH]), satisfaction=number(current["Удовлетворённость"]),
            readiness=readiness, mentor_month=mentor_month,
        ))
    readiness = mentors[dl.HIRE_READINESS]
    readiness_distribution = [
        RatingGroup(label="0 — меньше 6", count=int((readiness.ge(0) & readiness.lt(6)).sum())),
        RatingGroup(label="6 — меньше 8", count=int((readiness.ge(6) & readiness.lt(8)).sum())),
        RatingGroup(label="8–10", count=int(readiness.between(8, 10).sum())),
    ]
    return Overview(
        first_month=months.start, last_month=months.stop - 1, intern_count=totals["interns"],
        mentor_count=totals["mentors"], response_count=totals["responses"],
        metrics=metrics, charts=charts, interns=directory, readiness_distribution=readiness_distribution,
    )


def profile(snapshot: Snapshot, intern_id: str) -> Profile:
    interns = dl.intern_timeline(snapshot.interns, intern_id)
    mentors = dl.mentor_timeline(snapshot.mentors, intern_id)
    latest = interns.iloc[-1]
    month = int(latest[dl.MONTH])
    mentor_month, readiness = latest_mentor(mentors)
    metrics = [
        Metric(label=label, value=number(latest[label]), scale=5, source=source, month=month)
        for label, source in (
            ("Удовлетворённость", "Ответ стажёра"),
            ("Прогресс в обучении", "Самооценка стажёра"),
            ("Мотивация", "Ответ стажёра"),
        )
    ]
    metrics.append(Metric(
        label="Готовность к найму", value=readiness, scale=10,
        source="Оценка наставника", month=mentor_month,
    ))
    months = interval(pd.concat([interns, mentors], ignore_index=True))
    intern_means = dl.monthly_mean(interns, dl.INTERN_METRICS + [dl.NPS])
    charts = [
        Chart(id=f"survey-{index}", label=label, scale=(1, 5), series=[
            series("Стажёр", intern_means, label, months),
        ])
        for index, label in enumerate(dl.INTERN_METRICS)
    ]
    charts.extend([
        Chart(id="mentor-progress", label="Прогресс по оценке наставника", scale=(1, 5), series=[
            series("Наставник", dl.monthly_mean(mentors, ["Прогресс стажёра"]), "Прогресс стажёра", months),
        ]),
        Chart(id="readiness", label="Готовность к найму", scale=(0, 10), series=[
            series("Наставник", dl.monthly_mean(mentors, [dl.HIRE_READINESS]), dl.HIRE_READINESS, months),
        ]),
        Chart(id="recommendation", label="Готовность рекомендовать", scale=(0, 10), series=[
            series("Стажёр", intern_means, dl.NPS, months),
        ]),
    ])
    raw_comments = dl.mentor_comments(snapshot.mentors, intern_id)
    comments = [
        Comment(month=int(row[dl.MONTH]), mentor=row[dl.MENTOR_ID], text=str(row[dl.COMMENT]).strip())
        for _, row in raw_comments.sort_values(dl.MONTH, ascending=False).iterrows()
        if pd.notna(row[dl.COMMENT]) and str(row[dl.COMMENT]).strip()
    ]
    axes = [
        ProfileAxis(label=label, first=number(intern_means.iloc[0][label]), last=number(intern_means.iloc[-1][label]))
        for label in dl.INTERN_METRICS if label != "Нагрузка"
    ]
    return Profile(
        id=intern_id, month=month, first_month=months.start, last_month=months.stop - 1,
        metrics=metrics, charts=charts, comments=comments, response_profile=axes,
        response_months=(int(intern_means.iloc[0][dl.MONTH]), month),
    )
