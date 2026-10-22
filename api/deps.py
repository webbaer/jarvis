from __future__ import annotations

from fastapi import HTTPException, Request

from api.jobs import JobStore
from api.schemas import FiltersIn
from jarvis_memory.retrieval.hybrid import RetrievalFilters
from jarvis_memory.service import MemoryService


def get_service(request: Request) -> MemoryService:
    return request.app.state.service


def get_jobs(request: Request) -> JobStore:
    return request.app.state.jobs


def to_filters(filters: FiltersIn | None) -> RetrievalFilters | None:
    if filters is None:
        return None
    return RetrievalFilters(**filters.model_dump())


def check_limit(name: str, value: int | None, maximum: int) -> None:
    if value is not None and value > maximum:
        raise HTTPException(status_code=422, detail=f"{name} darf hoechstens {maximum} sein")
