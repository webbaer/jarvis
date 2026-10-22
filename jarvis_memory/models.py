from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Document:
    doc_id: str
    source: str
    doc_type: str
    content: str
    doc_date: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    source: str
    doc_type: str
    doc_date: str | None
    created_at: datetime


@dataclass(slots=True)
class FactRecord:
    id: int
    subject: str
    attribute: str
    value: str
    source: str
    valid_from: str
    valid_to: str | None
    status: str
    created_at: str


@dataclass(slots=True)
class RetrievalResult:
    chunk_id: str
    text: str
    source: str
    doc_type: str
    doc_date: str | None
    score: float
    vector_rank: int | None = None
    keyword_rank: int | None = None
    vector_score: float | None = None
    keyword_score: float | None = None
    document_id: str | None = None


@dataclass(slots=True)
class DocumentInfo:
    id: str
    source_path: str
    name: str
    doc_type: str
    doc_date: str | None
    content_hash: str
    indexed_at: str
    duplicate_of: str | None
    chunk_count: int


@dataclass(slots=True)
class ChunkInfo:
    id: str
    document_id: str
    chunk_index: int
    text: str
    source: str
    doc_type: str
    doc_date: str | None
    created_at: str


@dataclass(slots=True)
class IngestResult:
    document_id: str | None
    source: str
    # processed | updated | skipped | duplicate
    action: str
    chunk_count: int = 0
    duplicate_of: str | None = None
