from __future__ import annotations

from jarvis_memory.config import MemoryConfig
from jarvis_memory.retrieval.context_builder import ContextBuilder
from jarvis_memory.retrieval.hybrid import HybridRetriever
from jarvis_memory.retrieval.keyword_retriever import KeywordRetriever
from jarvis_memory.retrieval.vector_retriever import VectorRetriever
from jarvis_memory.store.db import connect, initialize
from jarvis_memory.store.embeddings import (
    LocalHashEmbedder,
    OllamaEmbedder,
    SentenceTransformerEmbedder,
)
from jarvis_memory.store.fact_store import FactStore
from jarvis_memory.store.vector_store import ChromaVectorStore


def create_embedder(config: MemoryConfig):
    if config.embedding.provider == "ollama":
        return OllamaEmbedder(config.embedding.ollama_url, config.embedding.ollama_model)
    if config.embedding.provider == "sentence_transformers":
        try:
            return SentenceTransformerEmbedder(config.embedding.model_name)
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Run: pip install -e '.[embeddings]'"
            ) from exc
    return LocalHashEmbedder()


def create_runtime(config: MemoryConfig):
    config.ensure_dirs()
    conn = connect(config.paths.sqlite_path)
    initialize(conn)
    embedder = create_embedder(config)
    vector_store = ChromaVectorStore(str(config.paths.chroma_dir), embedder)
    return conn, vector_store


def create_services(config: MemoryConfig):
    conn, vector_store = create_runtime(config)
    fact_store = FactStore(conn)
    vector_retriever = VectorRetriever(conn, vector_store)
    keyword_retriever = KeywordRetriever(conn)
    hybrid = HybridRetriever(vector_retriever, keyword_retriever, config.retrieval)
    context_builder = ContextBuilder(fact_store, hybrid, config.context)
    return conn, fact_store, hybrid, context_builder
