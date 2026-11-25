"""API, совместимость расчётов и сценарии ИИ без внешних запросов."""

import asyncio
from threading import Event
import ssl

import httpx
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


def test_overview_matches_existing_calculations_and_all_profiles(run):
    _, execute = run
    interns, mentors = surveys.load_all()
    totals = surveys.overall_metrics(interns, mentors)

    async def scenario(client):
        overview = (await client.get("/api/overview")).json()
        assert overview["response_count"] == totals["responses"]
        assert [item["value"] for item in overview["metrics"]] == [
            totals[key] for key in ("intern_satisfaction", "avg_progress", "hire_readiness")
        ]
        assert sum(group["count"] for group in overview["readiness_distribution"]) == len(mentors)
        assert [item["id"] for item in overview["interns"]] == surveys.intern_ids(interns)
        for row in overview["interns"]:
            profile = (await client.get(f"/api/interns/{row['id']}")).json()
            assert profile["id"] == row["id"]
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
        return "Вывод по стажёру" if "Стажёр: INT-02" in prompt else "Вывод по программе"

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
        finally:
            gate.set()
        assert (await wait_for_result(client, overview))["text"] == "Вывод по программе"
        assert (await wait_for_result(client, profile))["text"] == "Вывод по стажёру"
        cached = (await client.post(overview + "?refresh=false")).json()
        assert cached["status"] == "ready"
        assert cached["text"] == "Вывод по программе"
        assert len(calls) == 2
        assert all("HR-эксперт" in prompt and "до 100 слов" in prompt and "Не задавай вопросов" in prompt for prompt in calls)
        assert any("Сводные показатели" in prompt for prompt in calls)
        assert any("Комментарии наставников" in prompt and "Стажёр: INT-02" in prompt for prompt in calls)
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
        version = ("changed",)
        assert (await client.get(path)).json()["status"] == "available"

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


def test_analysis_rewrites_questions_before_publishing(run, monkeypatch):
    _, execute = run
    prompts = []
    responses = iter([
        "Прогресс вырос. Что обсудить на следующей встрече?",
        "За шесть месяцев оценка прогресса выросла с 2 до 4 из 5.",
        "Оценка изменилась. В чём причина?",
        "Что это означает?",
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
        assert result["text"] == "За шесть месяцев оценка прогресса выросла с 2 до 4 из 5."
        assert prompts[1].endswith(prompts[0])
        assert "только утверждения" in prompts[1]

        await client.post(path)
        result = await wait_for_result(client, path)
        assert result["status"] == "error"
        assert result["text"] == "За шесть месяцев оценка прогресса выросла с 2 до 4 из 5."
        assert len(prompts) == 4

    execute(scenario)
