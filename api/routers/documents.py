from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.deps import get_service
from api.schemas import ChunkOut, ChunkStatsOut, DocumentChunksOut, DocumentOut, IngestResultOut
from jarvis_memory.service import MemoryService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(service: MemoryService = Depends(get_service)) -> list[DocumentOut]:
    return [DocumentOut.model_validate(d) for d in service.list_documents()]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, service: MemoryService = Depends(get_service)) -> DocumentOut:
    document = service.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    return DocumentOut.model_validate(document)


@router.get("/{document_id}/chunks", response_model=DocumentChunksOut)
def get_chunks(document_id: str, service: MemoryService = Depends(get_service)) -> DocumentChunksOut:
    result = service.get_document_chunks(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    return DocumentChunksOut(
        document=DocumentOut.model_validate(result.document),
        stats=ChunkStatsOut.model_validate(result.stats),
        chunks=[
            ChunkOut(
                id=v.chunk.id,
                chunk_index=v.chunk.chunk_index,
                text=v.chunk.text,
                length=v.length,
                overlap_chars=v.overlap_chars,
                flag=v.flag,
                source=v.chunk.source,
                doc_type=v.chunk.doc_type,
                doc_date=v.chunk.doc_date,
                created_at=v.chunk.created_at,
            )
            for v in result.chunks
        ],
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, service: MemoryService = Depends(get_service)) -> Response:
    if not service.delete_document(document_id):
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/reindex", response_model=IngestResultOut)
def reindex_document(document_id: str, service: MemoryService = Depends(get_service)) -> IngestResultOut:
    try:
        result = service.reindex_document(document_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden") from None
    except FileNotFoundError:
        raise HTTPException(status_code=409, detail="Quelldatei existiert nicht mehr, Neu-Indexieren unmoeglich") from None
    return IngestResultOut.model_validate(result)
