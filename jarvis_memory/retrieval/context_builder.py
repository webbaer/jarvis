from __future__ import annotations

from jarvis_memory.config import ContextConfig
from jarvis_memory.models import RetrievalResult
from jarvis_memory.retrieval.hybrid import HybridRetriever, RetrievalFilters
from jarvis_memory.store.fact_store import FactStore


class ContextBuilder:
    def __init__(
        self,
        fact_store: FactStore,
        retriever: HybridRetriever,
        config: ContextConfig,
    ) -> None:
        self._fact_store = fact_store
        self._retriever = retriever
        self._config = config

    def build_context(self, query: str, filters: RetrievalFilters | None = None) -> str:
        chunks = self._retriever.search(query, top_k=self._config.max_chunks, filters=filters)
        return self.format_context(chunks)

    def format_context(self, chunks: list[RetrievalResult]) -> str:
        """Render facts plus already retrieved chunks into the block sent to the LLM."""
        facts = self._fact_store.get_current_facts()[: self._config.max_facts]

        lines: list[str] = ["[FACTS]"]
        for fact in facts:
            lines.append(
                f"- {fact.subject}.{fact.attribute}: {fact.value} "
                f"(source={fact.source}, valid_from={fact.valid_from})"
            )

        lines.append("")
        lines.append("[RETRIEVED_CHUNKS]")
        for idx, chunk in enumerate(chunks, start=1):
            clean_text = " ".join(chunk.text.split())
            lines.append(
                f"[{idx}] score={chunk.score:.4f} source={chunk.source} type={chunk.doc_type}"
            )
            lines.append(clean_text)

        context = "\n".join(lines).strip()
        if len(context) <= self._config.max_chars:
            return context
        return context[: self._config.max_chars - 3] + "..."
