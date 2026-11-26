"""Входные книги, общая опросная модель и резервный интерфейс."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from backend import dashboard, surveys
from frontend.charts import survey_chart
import llm

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_historical_survey_matches_brief():
    interns, mentors = surveys.load_all()
    assert len(interns) == len(mentors) == 30
    assert len(surveys.intern_ids(interns)) == len(surveys.mentor_ids(mentors)) == 5
    assert len(surveys.INTERN_METRICS) == 7 and len(surveys.MENTOR_METRICS) == 6
    assert interns.groupby(surveys.INTERN_ID)[surveys.MONTH].nunique().eq(6).all()
    assert mentors.groupby(surveys.INTERN_ID)[surveys.MONTH].nunique().eq(6).all()
    assert set(interns[surveys.INTERN_ID]) == set(mentors[surveys.INTERN_ID])


def test_streamlit_jumps_through_all_profiles(monkeypatch):
    monkeypatch.setattr(llm, "llm_available", lambda: False)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    ids = surveys.intern_ids(surveys.load_intern_data())
    for intern in ids:
        app.radio(key="dashboard_view").set_value(intern).run()
        assert not app.exception
        assert f"Стажёр {intern}" in [item.value for item in app.title]
    app.radio(key="dashboard_view").set_value("Обзор программы").run()
    assert not app.exception


@pytest.mark.parametrize("mode", ["overview", "profile"])
def test_shared_charts_render_all_six_months(mode):
    snapshot = dashboard.read_snapshot(dashboard.current_version())
    if mode == "overview":
        data = dashboard.overview(snapshot)
    else:
        data = dashboard.profile(snapshot, surveys.intern_ids(snapshot.interns)[0])
    for chart in data.charts:
        figure = survey_chart(chart)
        assert list(figure.data[0].x) == [1, 2, 3, 4, 5, 6]


def test_legacy_model_context_contains_only_scores():
    interns, mentors = surveys.load_all()
    intern_id = surveys.intern_ids(interns)[0]
    public = llm.build_intern_context(interns, mentors, intern_id)
    assert surveys.QUALITY in public
    assert intern_id not in public
    assert interns.iloc[0][surveys.INTERN_NOTES[0]] not in public
