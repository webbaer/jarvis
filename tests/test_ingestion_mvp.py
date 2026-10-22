from pathlib import Path

from jarvis_memory.config import MemoryConfig
from jarvis_memory.ingestion.pipeline import IngestionPipeline


class DummyVectorStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}

    def upsert_chunks(self, ids: list[str], texts: list[str], metadatas: list[dict[str, object]]) -> None:
        for idx, chunk_id in enumerate(ids):
            self.rows[chunk_id] = {
                "text": texts[idx],
                "metadata": metadatas[idx],
            }

    def delete_by_document(self, document_id: str) -> None:
        to_delete = [cid for cid, row in self.rows.items() if row["metadata"]["document_id"] == document_id]
        for cid in to_delete:
            del self.rows[cid]


def test_ingestion_skips_unchanged_file(tmp_path: Path) -> None:
    text_file = tmp_path / "note.txt"
    text_file.write_text("Erster Absatz.\n\nZweiter Absatz.", encoding="utf-8")

    cfg = MemoryConfig()
    cfg.paths.base_dir = tmp_path / ".memory"
    cfg.paths.sqlite_path = cfg.paths.base_dir / "memory.sqlite3"
    cfg.paths.chroma_dir = cfg.paths.base_dir / "chroma"
    cfg.ensure_dirs()

    store = DummyVectorStore()
    pipeline = IngestionPipeline(cfg, store)

    first = pipeline.ingest_path(text_file)
    second = pipeline.ingest_path(text_file)

    assert first["processed"] == 1
    assert second["skipped"] == 1


def test_ingestion_updates_changed_file(tmp_path: Path) -> None:
    text_file = tmp_path / "note.md"
    text_file.write_text("Alpha\n\nBeta", encoding="utf-8")

    cfg = MemoryConfig()
    cfg.paths.base_dir = tmp_path / ".memory"
    cfg.paths.sqlite_path = cfg.paths.base_dir / "memory.sqlite3"
    cfg.paths.chroma_dir = cfg.paths.base_dir / "chroma"
    cfg.ensure_dirs()

    store = DummyVectorStore()
    pipeline = IngestionPipeline(cfg, store)

    pipeline.ingest_path(text_file)
    text_file.write_text("Alpha\n\nBeta\n\nGamma", encoding="utf-8")
    result = pipeline.ingest_path(text_file)

    assert result["updated"] == 1
