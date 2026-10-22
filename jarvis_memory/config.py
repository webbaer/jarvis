from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class EmbeddingConfig:
    provider: str = "local_hash"
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "nomic-embed-text"


@dataclass(slots=True)
class ChunkingConfig:
    max_chars: int = 900
    overlap_chars: int = 180
    min_chunk_chars: int = 120


@dataclass(slots=True)
class RetrievalConfig:
    top_k: int = 6
    keyword_k: int = 10
    vector_k: int = 10
    rrf_k: int = 60
    enable_rerank: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass(slots=True)
class ContextConfig:
    max_chars: int = 3200
    max_facts: int = 12
    max_chunks: int = 8


@dataclass(slots=True)
class PathsConfig:
    base_dir: Path = field(default_factory=lambda: Path(".jarvis_memory"))
    sqlite_path: Path = field(default_factory=lambda: Path(".jarvis_memory") / "memory.sqlite3")
    chroma_dir: Path = field(default_factory=lambda: Path(".jarvis_memory") / "chroma")
    eval_dataset_path: Path = field(default_factory=lambda: Path("data") / "eval_dataset.yaml")


@dataclass(slots=True)
class MemoryConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    context: ContextConfig = field(default_factory=ContextConfig)

    def ensure_dirs(self) -> None:
        self.paths.base_dir.mkdir(parents=True, exist_ok=True)
        self.paths.chroma_dir.mkdir(parents=True, exist_ok=True)
