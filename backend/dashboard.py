"""Расчёты по фактическим вопросам двух анкет."""

from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import pandas as pd

from . import surveys as dl
from .models import Change, Chart, Comment, Coverage, InternSummary, Metric, Overview, Point, Profile, Series, SyncStatus
from .signals import evaluate_signals

PERIODS = range(1, 7)
INTERN_CHART_IDS = ("clarity", "mentoring", "workload", "interest", "development", "team", "satisfaction")
MENTOR_CHART_IDS = ("expectations", "quality", "autonomy", "deadlines", "initiative", "collaboration")


@dataclass(frozen=True)
class Snapshot:
    version: tuple
    interns: pd.DataFrame
    mentors: pd.DataFrame
    sync: SyncStatus = field(default_factory=SyncStatus)

    @property
    def data_version(self) -> str:
        return sha256(repr(self.version).encode()).hexdigest()


def file_version(path: Path) -> tuple:
    stat = path.stat()
    return path, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def current_version() -> tuple:
    return file_version(dl.INTERN_FILE), file_version(dl.MENTOR_FILE)


@lru_cache(maxsize=4)
def read_snapshot(version: tuple) -> Snapshot:
    interns, mentors = dl.load_all()
    if version != current_version():
        raise dl.SurveyDataError("Книги обновляются. Повторите загрузку через несколько секунд.")
    return Snapshot(version, interns, mentors)


def make_series(label: str, data: pd.DataFrame, column: str) -> Series:
    monthly = data.groupby(dl.MONTH)[column].agg(["mean", "count"]).reindex(PERIODS)
    return Series(label=label, points=[
        Point(month=month, value=float(row["mean"]) if pd.notna(row["mean"]) else None,
              responses=int(row["count"]) if pd.notna(row["count"]) else 0)
        for month, row in monthly.iterrows()
    ])


def make_charts(interns: pd.DataFrame, mentors: pd.DataFrame) -> list[Chart]:
    charts = [Chart(id=key, label=metric, series=[make_series("Стажеры", interns, metric)])
              for key, metric in zip(INTERN_CHART_IDS, dl.INTERN_METRICS, strict=True)]
    charts.extend(Chart(id=key, label=metric, series=[make_series("Наставники", mentors, metric)])
                  for key, metric in zip(MENTOR_CHART_IDS, dl.MENTOR_METRICS, strict=True))
    return charts


def change_for(series: Series) -> Change | None:
    observed = [point for point in series.points if point.value is not None]
    return Change(first=observed[0], latest=observed[-1]) if observed else None


def make_metrics(charts: list[Chart], keys: tuple[str, ...]) -> list[Metric]:
    by_id = {chart.id: chart for chart in charts}
    metrics = []
    for key in keys:
        chart = by_id[key]
        series = chart.series[0]
        change = change_for(series)
        metrics.append(Metric(
            label=chart.label, source=series.label, change=change,
            month=change.latest.month if change else None, value=change.latest.value if change else None,
        ))
    return metrics


def coverage(interns: pd.DataFrame, mentors: pd.DataFrame) -> list[Coverage]:
    intern_months = set(interns[dl.MONTH])
    expected = set(dl.mentor_ids(mentors))
    rows = []
    for month in PERIODS:
        submitted = set(mentors.loc[mentors[dl.MONTH] == month, dl.MENTOR_ID])
        rows.append(Coverage(
            month=month, intern_submitted=month in intern_months, mentor_submitted=bool(submitted),
            submitted_mentors=sorted(submitted), pending_mentors=sorted(expected - submitted),
        ))
    return rows


def comments(data: pd.DataFrame, *, mentor: bool) -> list[Comment]:
    questions = dl.MENTOR_NOTES if mentor else dl.INTERN_NOTES
    return [
        Comment(month=int(row[dl.MONTH]), author=row[dl.MENTOR_ID] if mentor else "Стажер",
                question=question, text=str(row[question]).strip())
        for _, row in data.sort_values(dl.MONTH, ascending=False, kind="stable").iterrows()
        for question in questions
        if pd.notna(row[question]) and str(row[question]).strip()
    ]


def overview(snapshot: Snapshot) -> Overview:
    charts = make_charts(snapshot.interns, snapshot.mentors)
    directory = []
    for intern_id in dl.intern_ids(snapshot.interns):
        intern = dl.intern_timeline(snapshot.interns, intern_id)
        mentor = dl.mentor_timeline(snapshot.mentors, intern_id)
        own_charts = make_charts(intern, mentor)
        states = coverage(intern, mentor)
        metrics = make_metrics(own_charts, ("satisfaction",))
        directory.append(InternSummary(
            id=intern_id, department=intern[dl.DEPARTMENT].iloc[0], satisfaction=metrics[0].value,
            coverage=states, signals=evaluate_signals(own_charts, intern, mentor),
        ))
    return Overview(
        data_version=snapshot.data_version, sync=snapshot.sync, first_month=1, last_month=6,
        intern_count=len(directory), mentor_count=len(dl.mentor_ids(snapshot.mentors)),
        response_count=len(snapshot.interns) + len(snapshot.mentors),
        intern_responses=len(snapshot.interns), mentor_responses=len(snapshot.mentors),
        metrics=make_metrics(charts, ("satisfaction", "development", "quality")),
        charts=charts, interns=directory,
    )


def profile(snapshot: Snapshot, intern_id: str) -> Profile:
    intern = dl.intern_timeline(snapshot.interns, intern_id)
    mentor = dl.mentor_timeline(snapshot.mentors, intern_id)
    charts = make_charts(intern, mentor)
    return Profile(
        id=intern_id, data_version=snapshot.data_version, sync=snapshot.sync, first_month=1, last_month=6,
        department=intern[dl.DEPARTMENT].iloc[0], coverage=coverage(intern, mentor),
        metrics=make_metrics(charts, ("satisfaction", "development", "quality", "autonomy")),
        charts=charts, signals=evaluate_signals(charts, intern, mentor),
        comments=comments(mentor, mentor=True), intern_comments=comments(intern, mentor=False),
    )
