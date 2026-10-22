"""FastAPI app factory. Run with `python -m api` (binds to 127.0.0.1 by default)."""
from __future__ import annotations

from fastapi import Depends, FastAPI

from api.deps import get_service
from api.jobs import JobStore
from api.routers import documents, evaluation, facts, ingest, query
from api.schemas import HealthOut
from jarvis_memory.config import MemoryConfig
from jarvis_memory.service import MemoryService


def create_app(config: MemoryConfig | None = None, service: MemoryService | None = None) -> FastAPI:
    config = config or MemoryConfig.from_env()
    app = FastAPI(
        title="Jarvis Memory API",
        description="Lokale API fuer Ingestion, Retrieval, Fakten und Eval. Keine Auth: nur lokal betreiben.",
        version="0.1.0",
    )
    app.state.service = service or MemoryService(config)
    app.state.jobs = JobStore(max_jobs=config.upload.max_tracked_jobs)

    @app.get("/health", response_model=HealthOut, tags=["meta"])
    def health(svc: MemoryService = Depends(get_service)) -> HealthOut:
        return HealthOut(status="ok", **svc.stats())

    app.include_router(ingest.router)
    app.include_router(documents.router)
    app.include_router(query.router)
    app.include_router(facts.router)
    app.include_router(evaluation.router)
    return app
