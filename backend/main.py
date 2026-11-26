"""FastAPI для локального HR-дашборда."""

from pathlib import Path
from typing import Annotated

import plotly
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import assistant, dashboard, surveys
from .analysis import AnalysisService
from .google_forms import FormsSync
from .models import Analysis, Overview, Profile

WEB = Path(__file__).resolve().parent.parent / "frontend" / "web"
PLOTLY = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


forms = FormsSync()


def get_snapshot() -> dashboard.Snapshot:
    try:
        return forms.update(dashboard.read_snapshot(dashboard.current_version()))
    except surveys.SurveyDataError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "Не удалось прочитать файлы опросов. Проверьте Excel-файлы в папке data.") from exc


Snapshot = Annotated[dashboard.Snapshot, Depends(get_snapshot)]


def analysis_snapshot(snapshot: Snapshot, version: str | None = None) -> dashboard.Snapshot:
    if version is not None and version != snapshot.data_version:
        raise HTTPException(409, "Опросы обновились. Загрузите актуальные данные.")
    return snapshot


AnalysisSnapshot = Annotated[dashboard.Snapshot, Depends(analysis_snapshot)]


def require_intern(snapshot: dashboard.Snapshot, intern_id: str) -> None:
    if intern_id not in surveys.intern_ids(snapshot.interns):
        raise HTTPException(404, "Стажёр не найден.")


def create_app() -> FastAPI:
    app = FastAPI(title="МГТС · Стажёрская программа")
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    analysis = AnalysisService()
    plotly_assets = StaticFiles(directory=PLOTLY.parent)
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/assets-vendor/plotly.js", include_in_schema=False)
    async def plotly_script(request: Request):
        return await plotly_assets.get_response(PLOTLY.name, request.scope)

    @app.get("/", include_in_schema=False)
    @app.get("/interns/{intern_id}", include_in_schema=False)
    def page(intern_id: str | None = None):
        return FileResponse(WEB / "index.html")

    @app.get("/api/data-status")
    def data_status(snapshot: Snapshot):
        return {"data_version": snapshot.data_version, "sync": snapshot.sync}

    @app.get("/api/overview")
    def overview(snapshot: Snapshot) -> Overview:
        return dashboard.overview(snapshot)

    @app.get("/api/interns/{intern_id}")
    def profile(snapshot: Snapshot, intern_id: str) -> Profile:
        require_intern(snapshot, intern_id)
        return dashboard.profile(snapshot, intern_id)

    @app.get("/api/analysis/overview")
    async def overview_analysis(snapshot: AnalysisSnapshot) -> Analysis:
        return analysis.status(snapshot, None)

    @app.post("/api/analysis/overview", status_code=202)
    async def analyze_overview(snapshot: AnalysisSnapshot, refresh: bool = True) -> Analysis:
        return analysis.start(snapshot, None, refresh)

    @app.get("/api/interns/{intern_id}/analysis")
    async def profile_analysis(snapshot: AnalysisSnapshot, intern_id: str) -> Analysis:
        require_intern(snapshot, intern_id)
        return analysis.status(snapshot, intern_id)

    @app.post("/api/interns/{intern_id}/analysis", status_code=202)
    async def analyze_profile(snapshot: AnalysisSnapshot, intern_id: str, refresh: bool = True) -> Analysis:
        require_intern(snapshot, intern_id)
        return analysis.start(snapshot, intern_id, refresh)

    @app.post("/api/assistant/overview")
    async def overview_assistant(snapshot: Snapshot, message: assistant.Question) -> assistant.Answer:
        expected = analysis_snapshot(snapshot, message.version)
        return await assistant.answer_question(expected, None, message, analysis.provider_lock)

    @app.post("/api/interns/{intern_id}/assistant")
    async def profile_assistant(snapshot: Snapshot, intern_id: str, message: assistant.Question) -> assistant.Answer:
        expected = analysis_snapshot(snapshot, message.version)
        require_intern(expected, intern_id)
        return await assistant.answer_question(expected, intern_id, message, analysis.provider_lock)

    return app


app = create_app()
