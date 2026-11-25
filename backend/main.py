"""FastAPI для локального HR-дашборда."""

from pathlib import Path
from typing import Annotated

import plotly
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import dashboard, surveys
from .analysis import AnalysisService
from .models import Analysis, Overview, Profile

WEB = Path(__file__).resolve().parent.parent / "frontend" / "web"
PLOTLY = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


def get_snapshot() -> dashboard.Snapshot:
    try:
        return dashboard.read_snapshot(dashboard.current_version())
    except Exception as exc:
        raise HTTPException(503, "Не удалось прочитать файлы опросов.") from exc


Snapshot = Annotated[dashboard.Snapshot, Depends(get_snapshot)]


def require_intern(snapshot: dashboard.Snapshot, intern_id: str) -> None:
    if intern_id not in surveys.intern_ids(snapshot.interns):
        raise HTTPException(404, "Стажёр не найден.")


def create_app() -> FastAPI:
    app = FastAPI(title="МГТС · Стажёрская программа")
    analysis = AnalysisService()
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/assets-vendor/plotly.js", include_in_schema=False)
    def plotly_script():
        return FileResponse(PLOTLY, media_type="text/javascript")

    @app.get("/", include_in_schema=False)
    @app.get("/interns/{intern_id}", include_in_schema=False)
    def page(intern_id: str | None = None):
        return FileResponse(WEB / "index.html")

    @app.get("/api/overview")
    def overview(snapshot: Snapshot) -> Overview:
        return dashboard.overview(snapshot)

    @app.get("/api/interns/{intern_id}")
    def profile(snapshot: Snapshot, intern_id: str) -> Profile:
        require_intern(snapshot, intern_id)
        return dashboard.profile(snapshot, intern_id)

    @app.get("/api/analysis/overview")
    async def overview_analysis(snapshot: Snapshot) -> Analysis:
        return analysis.status(snapshot, None)

    @app.post("/api/analysis/overview", status_code=202)
    async def analyze_overview(snapshot: Snapshot, refresh: bool = True) -> Analysis:
        return analysis.start(snapshot, None, refresh)

    @app.get("/api/interns/{intern_id}/analysis")
    async def profile_analysis(snapshot: Snapshot, intern_id: str) -> Analysis:
        require_intern(snapshot, intern_id)
        return analysis.status(snapshot, intern_id)

    @app.post("/api/interns/{intern_id}/analysis", status_code=202)
    async def analyze_profile(snapshot: Snapshot, intern_id: str, refresh: bool = True) -> Analysis:
        require_intern(snapshot, intern_id)
        return analysis.start(snapshot, intern_id, refresh)

    return app


app = create_app()
