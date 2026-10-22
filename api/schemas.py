from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.jobs import JobStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- health ----------------------------------------------------------------

class HealthOut(BaseModel):
    status: str
    documents: int
    chunks: int
    facts: int


# --- ingest ----------------------------------------------------------------

class UploadItemOut(BaseModel):
    filename: str
    # "queued" if accepted, "rejected" if validation failed.
    status: str
    job_id: str | None = None
    document_id: str | None = None
    error: str | None = None


class IngestJobOut(ORMModel):
    id: str
    filename: str
    document_id: str
    status: JobStatus
    error: str | None
    duplicate_of: str | None
    chunk_count: int
    created_at: str
    updated_at: str


class IngestResultOut(ORMModel):
    document_id: str | None
    source: str
    action: str
    chunk_count: int
    duplicate_of: str | None


# --- documents -------------------------------------------------------------

class DocumentOut(ORMModel):
    id: str
    name: str
    source_path: str
    doc_type: str
    doc_date: str | None
    content_hash: str
    indexed_at: str
    duplicate_of: str | None
    chunk_count: int


class ChunkOut(BaseModel):
    id: str
    chunk_index: int
    text: str
    length: int
    overlap_chars: int
    flag: str | None
    source: str
    doc_type: str
    doc_date: str | None
    created_at: str


class ChunkStatsOut(ORMModel):
    count: int
    avg_length: float
    min_length: int
    max_length: int
    short_count: int
    long_count: int
    short_threshold: int
    long_threshold: int


class DocumentChunksOut(BaseModel):
    document: DocumentOut
    stats: ChunkStatsOut
    chunks: list[ChunkOut]


# --- query -----------------------------------------------------------------

class FiltersIn(BaseModel):
    source: str | None = None
    doc_type: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class QueryIn(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1)
    filters: FiltersIn | None = None
    rerank: bool | None = None


class HitOut(ORMModel):
    chunk_id: str
    document_id: str | None
    source: str
    doc_type: str
    doc_date: str | None
    text: str
    score: float
    vector_rank: int | None
    vector_score: float | None
    keyword_rank: int | None
    keyword_score: float | None


class FusedHitOut(HitOut):
    fused_rank: int


class QueryOut(BaseModel):
    vector_hits: list[HitOut]
    keyword_hits: list[HitOut]
    fused_hits: list[FusedHitOut]
    context: str


class LocateIn(BaseModel):
    query: str = Field(min_length=1)
    document_id: str
    chunk_id: str | None = None
    top_k: int | None = Field(default=None, ge=1)
    filters: FiltersIn | None = None
    depth: int | None = Field(default=None, ge=1)


class ChunkLocationOut(ORMModel):
    chunk_id: str
    document_id: str
    vector_rank: int | None
    vector_score: float | None
    keyword_rank: int | None
    keyword_score: float | None
    fused_rank: int | None
    fused_score: float | None
    deep_fused_rank: int | None
    in_top_k: bool


# --- facts -----------------------------------------------------------------

class FactIn(BaseModel):
    subject: str = Field(min_length=1)
    attribute: str = Field(min_length=1)
    value: str = Field(min_length=1)
    source: str = Field(min_length=1)
    valid_from: str | None = None


class FactUpdateIn(BaseModel):
    value: str = Field(min_length=1)
    source: str = Field(min_length=1)
    valid_from: str | None = None


class FactOut(ORMModel):
    id: int
    subject: str
    attribute: str
    value: str
    source: str
    valid_from: str
    valid_to: str | None
    status: str
    created_at: str


# --- eval ------------------------------------------------------------------

class EvalRunIn(BaseModel):
    k: int | None = Field(default=None, ge=1)


class EvalCaseOut(ORMModel):
    id: str
    query: str
    expected_sources: list[str]
    rank: int | None
    retrieved_sources: list[str]


class EvalRunOut(ORMModel):
    id: int
    created_at: str
    k: int
    cases: int
    recall_at_k: float
    mrr: float
    dataset: str
    config: dict[str, Any]
    per_case: list[EvalCaseOut]
