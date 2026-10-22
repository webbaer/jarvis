from __future__ import annotations

import os
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
    uploads_dir: Path = field(default_factory=lambda: Path(".jarvis_memory") / "uploads")

    @classmethod
    def under(cls, base_dir: Path) -> "PathsConfig":
        """All storage paths below one base directory (eval dataset stays repo-relative)."""
        return cls(
            base_dir=base_dir,
            sqlite_path=base_dir / "memory.sqlite3",
            chroma_dir=base_dir / "chroma",
            uploads_dir=base_dir / "uploads",
        )


@dataclass(slots=True)
class UploadConfig:
    max_file_bytes: int = 25 * 1024 * 1024
    max_files_per_request: int = 20
    allowed_extensions: tuple[str, ...] = (".pdf", ".md", ".txt", ".eml")
    max_filename_chars: int = 120
    write_chunk_bytes: int = 1024 * 1024
    max_tracked_jobs: int = 1000


@dataclass(slots=True)
class InspectionConfig:
    # How deep to search when locating an expected chunk in the Query-Inspector.
    locate_depth: int = 100
    max_locate_depth: int = 500
    max_top_k: int = 50
    # Chunks shorter than chunking.min_chunk_chars or longer than
    # chunking.max_chars * long_chunk_factor are flagged in the chunk browser.
    long_chunk_factor: float = 1.2


@dataclass(slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass(slots=True)
class MemoryConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)
    inspection: InspectionConfig = field(default_factory=InspectionConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        """Defaults, overridable via JARVIS_* environment variables."""
        config = cls()
        if base := os.environ.get("JARVIS_DATA_DIR"):
            config.paths = PathsConfig.under(Path(base))
        if max_mb := os.environ.get("JARVIS_MAX_UPLOAD_MB"):
            config.upload.max_file_bytes = int(max_mb) * 1024 * 1024
        if host := os.environ.get("JARVIS_API_HOST"):
            config.server.host = host
        if port := os.environ.get("JARVIS_API_PORT"):
            config.server.port = int(port)
        return config

    def ensure_dirs(self) -> None:
        self.paths.base_dir.mkdir(parents=True, exist_ok=True)
        self.paths.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.paths.uploads_dir.mkdir(parents=True, exist_ok=True)
