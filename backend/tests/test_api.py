"""API, совместимость расчётов и сценарии ИИ без внешних запросов."""

import asyncio
import ssl
from threading import Event

import httpx
import pandas as pd
import pytest

import llm
from llm import core
from backend import dashboard, surveys
from backend.main import create_app, get_snapshot


@pytest.fixture
def run():
    app = create_app()

    def execute(scenario):
        async def session():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await scenario(client)

        asyncio.run(session())

    return app, execute


async def wait_for_result(client, path):
    for _ in range(100):
        result = (await client.get(path)).json()
        if result["status"] != "running":
            return result
        await asyncio.sleep(0.01)
    pytest.fail("Анализ остался в состоянии загрузки")


def test_html_assets_and_deep_links(run):
    _, execute = run

    async def scenario(client):
        for path in ("/", "/interns/INT-02"):
            response = await client.get(path)
            assert response.status_code == 200
            assert 'lang="ru"' in response.text
            assert "/assets/dashboard.js" in response.text
        for path in ("/assets/dashboard.js", "/assets/dashboard.css", "/assets-vendor/plotly.js"):
            assert (await client.get(path)).status_code == 200
        assert (await client.get("/api/interns/missing")).status_code == 404
        assert (await client.post("/api/interns/missing/analysis")).status_code == 404

    execute(scenario)


def test_plotly_is_compressed_and_supports_cache_validation(run):
    _, execute = run

    async def scenario(client):
        path = "/assets-vendor/plotly.js"
        async with client.stream("GET", path, headers={"Accept-Encoding": "gzip"}) as response:
            assert response.status_code == 200
            assert response.headers["content-encoding"] == "gzip"
            assert "accept-encoding" in response.headers["vary"].lower()
            etag = response.headers["etag"]
            compressed_size = sum([len(chunk) async for chunk in response.aiter_raw()])
        identity = await client.get(path, headers={"Accept-Encoding": "identity"})
        assert compressed_size < len(identity.content) * 0.6
        cached = await client.get(path, headers={"If-None-Match": etag})
        assert cached.status_code == 304
        assert not cached.content

    execute(scenario)


def test_overview_matches_existing_calculations_and_all_profiles(run):
    _, execute = run
    interns, mentors = surveys.load_all()
    totals = surveys.overall_metrics(interns, mentors)

    async def scenario(client):
        overview = (await client.get("/api/overview")).json()
        assert overview["response_count"] == totals["responses"]
        assert overview["intern_responses"] == overview["mentor_responses"] == 30
        progress = overview["metrics"][1]["change"]
        assert progress["first"] == {"month": 1, "value": 1.4, "responses": 5}
        assert progress["latest"] == {"month": 6, "value": 4.2, "responses": 5}
        assert {"materials", "support"} <= {chart["id"] for chart in overview["charts"]}
        assert [item["value"] for item in overview["metrics"]] == [
            totals[key] for key in ("intern_satisfaction", "avg_progress", "hire_readiness")
        ]
        assert sum(group["count"] for group in overview["readiness_distribution"]) == len(mentors)
        assert [item["id"] for item in overview["interns"]] == surveys.intern_ids(interns)
        for row in overview["interns"]:
            profile = (await client.get(f"/api/interns/{row['id']}")).json()
            assert profile["id"] == row["id"]
            assert profile["data_version"] == overview["data_version"]
            assert row["progress"] == profile["mentor_progress"]
            assert {item["month"] for item in profile["intern_comments"]} == set(range(1, 7))
            assert profile["month"] == row["month"]
            assert profile["metrics"][0]["value"] == row["satisfaction"]
            assert profile["metrics"][-1]["value"] == row["readiness"]
            assert profile["comments"][0]["month"] == row["mentor_month"]
            assert profile["response_months"][-1] == profile["month"]
            assert len(profile["response_profile"]) == 5
            assert next(axis for axis in profile["response_profile"] if axis["label"] == "Удовлетворённость")["last"] == row["satisfaction"]

    execute(scenario)


def test_profile_handles_missing_month_and_mentor_feedback(run):
    app, execute = run
    interns, mentors = surveys.load_all()
    interns = interns.loc[~((interns[surveys.INTERN_ID] == "INT-01") & (interns[surveys.MONTH] == 2))].copy()
    interns.loc[(interns[surveys.INTERN_ID] == "INT-01") & (interns[surveys.MONTH] == 6), "Удовлетворённость"] = float("nan")
    mentors = mentors.loc[mentors[surveys.INTERN_ID] != "INT-01"]
    app.dependency_overrides[get_snapshot] = lambda: dashboard.Snapshot(("test",), interns, mentors)

    async def scenario(client):
        response = await client.get("/api/interns/INT-01")
        assert response.status_code == 200
        profile = response.json()
        assert profile["metrics"][0]["value"] is None
        assert profile["metrics"][0]["change"]["latest"]["month"] == 5
        assert profile["metrics"][-1]["month"] is None
        assert profile["comments"] == []
        assert profile["charts"][0]["series"][0]["points"][1] == {"month": 2, "value": None}

    execute(scenario)


def test_analysis_deduplicates_requests_and_keeps_results_per_scope(run, monkeypatch):
    _, execute = run
    gate = Event()
    calls = []

    def provider(prompt):
        calls.append(prompt)
        assert gate.wait(3)
        return "Вывод по стажёру" if "Показатели одного стажёра" in prompt else "Вывод по программе"

    monkeypatch.setattr(llm, "llm_available", lambda: True)
    monkeypatch.setattr(llm, "_call_model", provider)

    async def scenario(client):
        overview = "/api/analysis/overview"
        profile = "/api/interns/INT-02/analysis"
        assert (await client.get(overview)).json()["status"] == "available"
        assert not calls
        try:
            assert (await client.post(overview + "?refresh=false")).status_code == 202
            assert (await client.post(overview + "?refresh=false")).json()["status"] == "running"
            assert (await client.get(overview)).json()["status"] == "running"
            assert (await client.post(profile)).status_code == 202
            assert len(calls) <= 1
        finally:
            gate.set()
        assert (await wait_for_result(client, overview))["text"] == "Вывод по программе"
        assert (await wait_for_result(client, profile))["text"] == "Вывод по стажёру"
        cached = (await client.post(overview + "?refresh=false")).json()
        assert cached["status"] == "ready"
        assert cached["text"] == "Вывод по программе"
        assert len(calls) == 2
        assert all("HR-эксперт" in prompt and "без вопросов" in prompt and "Не повторяй числа" in prompt for prompt in calls)
        assert any("Сводные показатели" in prompt and "месяц 6: 4.20/5, ответов: 5" in prompt for prompt in calls)
        assert any("Показатели одного стажёра" in prompt and "Прогресс в обучении · Оценка наставников" in prompt
                   for prompt in calls)
        assert all("INT-02" not in prompt and "Комментарии наставников" not in prompt for prompt in calls)
        assert (await client.get("/api/interns/INT-03/analysis")).json()["status"] == "available"
        monkeypatch.setenv("LLM_MODEL", "updated-model")
        assert (await client.get(overview)).json()["status"] == "available"

    execute(scenario)


def test_analysis_failure_can_be_retried_and_snapshot_changes_invalidate_cache(run, monkeypatch):
    app, execute = run
    snapshot = get_snapshot()
    version = ("first",)
    app.dependency_overrides[get_snapshot] = lambda: dashboard.Snapshot(version, snapshot.interns, snapshot.mentors)
    monkeypatch.setattr(llm, "llm_available", lambda: True)
    attempts = []

    def provider(prompt):
        attempts.append(prompt)
        if len(attempts) == 1:
            raise TimeoutError("provider timeout")
        return "Готовый вывод"

    monkeypatch.setattr(llm, "_call_model", provider)

    async def scenario(client):
        nonlocal version
        path = "/api/analysis/overview"
        await client.post(path)
        failure = await wait_for_result(client, path)
        assert failure["status"] == "error"
        assert "не ответил вовремя" in failure["error_message"]
        assert (await client.get("/api/overview")).status_code == 200
        await client.post(path + "?refresh=false")
        assert (await wait_for_result(client, path))["text"] == "Готовый вывод"
        old = (await client.get("/api/overview")).json()["data_version"]
        version = ("changed",)
        assert (await client.get(path)).json()["status"] == "available"
        assert (await client.get(path, params={"version": old})).status_code == 409
        assert (await client.post(path, params={"version": old})).status_code == 409

    execute(scenario)


def test_analysis_without_credentials(run, monkeypatch):
    _, execute = run
    monkeypatch.setattr(llm, "llm_available", lambda: False)

    async def scenario(client):
        path = "/api/analysis/overview"
        assert (await client.get(path)).json()["status"] == "unavailable"
        assert (await client.post(path)).json()["status"] == "unavailable"
        assert (await client.get("/api/overview")).status_code == 200

    execute(scenario)


def test_gigachat_ca_is_scoped_to_provider(monkeypatch):
    monkeypatch.delenv("LLM_CA_FILE", raising=False)
    bundled_ca = ssl.PEM_cert_to_DER_cert(core.GIGACHAT_ROOT_CA.read_text())
    giga = core._ssl_context("https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
    other = core._ssl_context("https://example.test/")
    assert giga.verify_mode == ssl.CERT_REQUIRED
    assert giga.check_hostname
    assert bundled_ca in giga.get_ca_certs(binary_form=True)
    assert set(other.get_ca_certs(binary_form=True)) == set(
        ssl.create_default_context().get_ca_certs(binary_form=True)
    )


def test_analysis_rewrites_questions_and_numbers_before_publishing(run, monkeypatch):
    _, execute = run
    prompts = []
    responses = iter([
        "Прогресс вырос. Что обсудить на следующей встрече?",
        "Оценка прогресса наставниками выросла за период.",
        "Оценка выросла вдвое благодаря усилиям команды.",
        "Итоговый результат равен 10.",
    ])

    def provider(prompt):
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr(llm, "llm_available", lambda: True)
    monkeypatch.setattr(llm, "_call_model", provider)

    async def scenario(client):
        path = "/api/analysis/overview"
        await client.post(path)
        result = await wait_for_result(client, path)
        assert result["status"] == "ready"
        assert result["text"] == "Оценка прогресса наставниками выросла за период."
        assert "Опиши только указанные изменения" in prompts[1]
        assert "рост между первой и последней оценками" in prompts[1]
        assert "4.20" not in prompts[1]

        await client.post(path)
        result = await wait_for_result(client, path)
        assert result["status"] == "error"
        assert result["text"] == "Оценка прогресса наставниками выросла за период."
        assert len(prompts) == 4

    execute(scenario)


@pytest.mark.parametrize(("column", "value", "message"), [
    (surveys.MONTH, 1.5, "целым числом"),
    (surveys.MONTH, 7, "от 1 до 6"),
    (surveys.INTERN_ID, "", "Заполните колонку"),
    ("Удовлетворённость", 9, "Проверьте значение"),
])
def test_workbook_validation_reports_row(monkeypatch, column, value, message):
    data = surveys.load_intern_data()
    data[column] = data[column].astype(object)
    data.loc[0, column] = value
    monkeypatch.setattr(surveys, "load_excel", lambda *args, **kwargs: data)
    with pytest.raises(surveys.SurveyDataError, match=f"строка 2.*{message}"):
        surveys.load_intern_data()


def test_workbooks_reject_duplicate_rows_and_orphan_mentor_records(monkeypatch):
    interns, mentors = surveys.load_all()
    duplicate = pd.concat([interns, interns.iloc[[0]]], ignore_index=True)
    with monkeypatch.context() as patch:
        patch.setattr(surveys, "load_excel", lambda *args, **kwargs: duplicate)
        with pytest.raises(surveys.SurveyDataError, match="повторная строка"):
            surveys.load_intern_data()
    mentors.loc[0, surveys.INTERN_ID] = "UNKNOWN"
    monkeypatch.setattr(surveys, "load_mentor_data", lambda: mentors)
    with pytest.raises(surveys.SurveyDataError, match="которых нет"):
        surveys.load_all()


def test_overview_keeps_months_seen_only_in_mentor_survey():
    interns, mentors = surveys.load_all()
    shortened = interns.loc[interns[surveys.MONTH] < 6]
    result = dashboard.overview(dashboard.Snapshot(("test",), shortened, mentors))
    assert result.last_month == 6
    assert result.metrics[0].change.latest.month == 5
    assert result.metrics[1].change.latest.month == 6
    assert result.charts[0].series[0].points[-1].value is None
    assert result.charts[0].series[1].points[-1].value == 4.8
