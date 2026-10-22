from __future__ import annotations

from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from jarvis_memory.store.embeddings import Embedder


class ChromaVectorStore:
    def __init__(self, persist_directory: str, embedder: Embedder, collection_name: str = "jarvis_chunks") -> None:
        self._embedder = embedder
        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection: Collection = self._client.get_or_create_collection(name=collection_name)

    def upsert_chunks(self, ids: list[str], texts: list[str], metadatas: list[dict[str, Any]]) -> None:
        if not ids:
            return
        vectors = self._embedder.embed(texts)
        self._collection.upsert(ids=ids, documents=texts, embeddings=vectors, metadatas=metadatas)

    def delete_by_document(self, document_id: str) -> None:
        rows = self._collection.get(where={"document_id": document_id}, include=[])
        ids = rows.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)

    def query(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        where = filters or None
        qv = self._embedder.embed([query])[0]
        result = self._collection.query(
            query_embeddings=[qv],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        merged: list[dict[str, Any]] = []
        for idx, cid in enumerate(ids):
            merged.append(
                {
                    "chunk_id": cid,
                    "text": docs[idx],
                    "metadata": metas[idx],
                    "distance": dists[idx],
                    "rank": idx + 1,
                }
            )
        return merged
