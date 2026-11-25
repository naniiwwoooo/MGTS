"""Тесты дашборда: данные, метрики, графики и запуск приложения."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from frontend import charts
from frontend import data_loader as dl
import llm

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "frontend" / "app.py"


@pytest.fixture(scope="module")
def data():
    return dl.load_intern_data(), dl.load_mentor_data()


def test_files_exist():
    assert dl.INTERN_FILE.exists(), "нет intern_survey.xlsx"
    assert dl.MENTOR_FILE.exists(), "нет mentor_survey.xlsx"


def test_intern_shape_and_columns(data):
    intern_df, _ = data
    assert intern_df.shape == (30, 10)
    assert set(dl.INTERN_COLUMNS).issubset(intern_df.columns)
    assert not intern_df[dl.INTERN_COLUMNS].isna().any().any()


def test_mentor_shape_and_columns(data):
    _, mentor_df = data
    assert mentor_df.shape == (30, 10)
    assert set(dl.MENTOR_COLUMNS).issubset(mentor_df.columns)
    assert not mentor_df[dl.MENTOR_COLUMNS].isna().any().any()


def test_six_months_for_every_intern(data):
    intern_df, _ = data
    for intern_id in dl.intern_ids(intern_df):
        months = sorted(dl.intern_timeline(intern_df, intern_id)[dl.MONTH].tolist())
        assert months == [1, 2, 3, 4, 5, 6]


def test_ids_are_anonymized_and_linked(data):
    intern_df, mentor_df = data
    intern_ids = set(dl.intern_ids(intern_df))
    assert len(intern_ids) == 5
    assert set(dl.mentor_ids(mentor_df)) == {"MENT-01", "MENT-02", "MENT-03", "MENT-04", "MENT-05"}
    assert set(mentor_df[dl.INTERN_ID].unique()) == intern_ids


def test_value_ranges(data):
    intern_df, mentor_df = data
    for metric in dl.INTERN_METRICS:
        assert intern_df[metric].between(1, 5).all()
    for metric in dl.MENTOR_METRICS:
        assert mentor_df[metric].between(1, 5).all()
    assert intern_df[dl.NPS].between(0, 10).all()
    assert mentor_df[dl.HIRE_READINESS].between(0, 10).all()
    assert (mentor_df[dl.HOURS] > 0).all()


def test_overall_metrics(data):
    intern_df, mentor_df = data
    m = dl.overall_metrics(intern_df, mentor_df)
    assert m["interns"] == 5
    assert m["mentors"] == 5
    assert m["months"] == 6
    assert m["responses"] == 60
    assert 1 <= m["intern_satisfaction"] <= 5
    assert 0 <= m["avg_nps"] <= 10
    assert m["mentor_hours"] > 0


def test_monthly_mean(data):
    intern_df, _ = data
    monthly = dl.monthly_mean(intern_df, dl.INTERN_METRICS)
    assert len(monthly) == 6
    assert monthly[dl.MONTH].tolist() == [1, 2, 3, 4, 5, 6]


def test_intern_summary(data):
    intern_df, _ = data
    summary = dl.intern_summary(intern_df)
    assert len(summary) == 5
    assert set(summary[dl.INTERN_ID]) == set(dl.intern_ids(intern_df))


def test_mentor_comments_present(data):
    _, mentor_df = data
    for intern_id in dl.intern_ids(mentor_df):
        comments = dl.mentor_comments(mentor_df, intern_id)
        assert len(comments) == 6
        assert comments[dl.COMMENT].str.len().gt(0).all()


def test_radar_profile_and_snapshot(data):
    intern_df, _ = data
    intern_id = dl.intern_ids(intern_df)[0]
    categories, first, last = dl.radar_profile(intern_df, intern_id)
    assert categories == dl.INTERN_METRICS
    assert len(first) == len(last) == len(categories)
    snapshot = dl.latest_snapshot(intern_df, intern_id)
    assert snapshot[dl.MONTH] == 6
    assert dl.NPS in snapshot


def test_chart_functions_return_figures(data):
    intern_df, mentor_df = data
    intern_id = dl.intern_ids(intern_df)[0]
    timeline = dl.intern_timeline(intern_df, intern_id)
    mentor_tl = dl.mentor_timeline(mentor_df, intern_id)

    figures = [
        charts.satisfaction_trend(intern_df, mentor_df),
        charts.progress_trend(intern_df, mentor_df),
        charts.nps_trend(intern_df),
        charts.hire_readiness_trend(mentor_df),
        charts.mentor_hours(mentor_df),
        charts.satisfaction_heatmap(intern_df),
        charts.nps_by_intern(intern_df),
        charts.team_radar(intern_df),
        charts.intern_timeline_chart(timeline),
        charts.intern_nps_chart(timeline),
        charts.intern_radar(intern_df, intern_id),
        charts.intern_mentor_progress(mentor_tl),
    ]
    for fig in figures:
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1


def test_llm_hook(data, monkeypatch):
    monkeypatch.setattr("llm.core.llm_available", lambda: False)
    intern_df, mentor_df = data
    context = llm.build_context(intern_df, mentor_df)
    assert "Сводные показатели" in context
    impression = llm.generate_overall_impression(intern_df, mentor_df)
    assert isinstance(impression, str) and impression


def test_help_sheets_present():
    from data.read_excel import load_sheets

    for path in (dl.INTERN_FILE, dl.MENTOR_FILE):
        sheets = load_sheets(path)
        assert set(sheets) == {"Данные", "Справка"}
        assert not sheets["Справка"].empty


@pytest.fixture
def dashboard(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(llm, "llm_available", lambda: False)
    return AppTest.from_file(str(APP), default_timeout=60).run()


def test_app_opens_program_overview(dashboard):
    assert not dashboard.exception
    navigation = dashboard.radio(key="dashboard_view")
    assert navigation.value == "Обзор программы"
    assert len(navigation.options) == 6
    assert any("<h1>Обзор программы</h1>" in item.value for item in dashboard.markdown)
    assert not any(item.label == "Предыдущие отзывы" for item in dashboard.expander)


def test_app_switches_between_interns_and_overview(dashboard, data):
    intern_df, mentor_df = data
    for intern_id in dl.intern_ids(intern_df):
        dashboard.radio(key="dashboard_view").set_value(intern_id).run()
        assert not dashboard.exception
        assert any(f"<h1>Стажёр {intern_id}</h1>" in item.value for item in dashboard.markdown)
        assert not any(item.label == "Сравнение стажёров" for item in dashboard.expander)
        history = next(item for item in dashboard.expander if item.label == "Предыдущие отзывы")
        latest = dl.mentor_comments(mentor_df, intern_id).iloc[-1]
        assert any(str(latest[dl.COMMENT]) in item.value for item in dashboard.markdown)
        assert all(str(latest[dl.COMMENT]) not in item.value for item in history.markdown)

    dashboard.radio(key="dashboard_view").set_value("Обзор программы").run()
    assert not dashboard.exception
    assert any("<h1>Обзор программы</h1>" in item.value for item in dashboard.markdown)


def test_model_runs_only_on_request_and_keeps_results_per_view(monkeypatch):
    from streamlit.testing.v1 import AppTest

    calls = []

    def overall(*args):
        calls.append("overview")
        return "Вывод по программе"

    def intern(intern_df, mentor_df, intern_id):
        calls.append(intern_id)
        return f"Вывод по {intern_id}"

    monkeypatch.setattr(llm, "llm_available", lambda: True)
    monkeypatch.setattr(llm, "generate_overall_impression", overall)
    monkeypatch.setattr(llm, "generate_intern_impression", intern)
    at = AppTest.from_file(str(APP)).run()
    assert calls == []
    at.button(key="generate_analysis").click().run()
    assert calls == ["overview"]
    assert at.text[0].value == "Вывод по программе"

    at.radio(key="dashboard_view").set_value("INT-02").run()
    assert calls == ["overview"]
    assert not at.text
    at.button(key="generate_analysis").click().run()
    assert calls == ["overview", "INT-02"]
    assert at.text[0].value == "Вывод по INT-02"

    at.radio(key="dashboard_view").set_value("Обзор программы").run()
    assert not at.exception
    assert calls == ["overview", "INT-02"]
    assert at.text[0].value == "Вывод по программе"
