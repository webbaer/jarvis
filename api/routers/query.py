from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import check_limit, get_service, to_filters
from api.schemas import ChunkLocationOut, FusedHitOut, HitOut, LocateIn, QueryIn, QueryOut
from jarvis_memory.service import MemoryService

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryOut)
def query(body: QueryIn, service: MemoryService = Depends(get_service)) -> QueryOut:
    check_limit("top_k", body.top_k, service.config.inspection.max_top_k)
    result = service.query(body.query, top_k=body.top_k, filters=to_filters(body.filters), rerank=body.rerank)
    return QueryOut(
        vector_hits=[HitOut.model_validate(r) for r in result.vector],
        keyword_hits=[HitOut.model_validate(r) for r in result.keyword],
        fused_hits=[
            FusedHitOut.model_validate({**HitOut.model_validate(r).model_dump(), "fused_rank": rank})
            for rank, r in enumerate(result.fused, start=1)
        ],
        context=result.context,
    )


@router.post("/locate", response_model=list[ChunkLocationOut])
def locate(body: LocateIn, service: MemoryService = Depends(get_service)) -> list[ChunkLocationOut]:
    """Where do a document's chunks (or one chunk) rank for this query, also beyond top_k?"""
    inspection = service.config.inspection
    check_limit("top_k", body.top_k, inspection.max_top_k)
    check_limit("depth", body.depth, inspection.max_locate_depth)
    if service.get_document(body.document_id) is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    locations = service.locate(
        body.query,
        document_id=body.document_id,
        chunk_id=body.chunk_id,
        top_k=body.top_k,
        filters=to_filters(body.filters),
        depth=body.depth,
    )
    if body.chunk_id and not locations:
        raise HTTPException(status_code=404, detail="Chunk gehoert nicht zu diesem Dokument")
    return [ChunkLocationOut.model_validate(loc) for loc in locations]
