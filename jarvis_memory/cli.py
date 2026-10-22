from __future__ import annotations

import argparse
from pathlib import Path

from jarvis_memory.app import create_runtime, create_services
from jarvis_memory.config import MemoryConfig
from jarvis_memory.eval.evaluate import evaluate, load_eval_cases
from jarvis_memory.ingestion.pipeline import IngestionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jarvis Memory CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest files or a folder")
    ingest.add_argument("path", type=Path)

    query = sub.add_parser("query", help="Build context for a question")
    query.add_argument("text", type=str)
    query.add_argument("--top-k", type=int, default=6)

    add_fact = sub.add_parser("add-fact", help="Add or supersede a fact")
    add_fact.add_argument("--subject", required=True)
    add_fact.add_argument("--attribute", required=True)
    add_fact.add_argument("--value", required=True)
    add_fact.add_argument("--source", required=True)

    fact_history = sub.add_parser("fact-history", help="Show fact history")
    fact_history.add_argument("--subject", required=True)
    fact_history.add_argument("--attribute", required=True)

    eval_cmd = sub.add_parser("eval", help="Evaluate retrieval quality")
    eval_cmd.add_argument("--dataset", type=Path, default=None)
    eval_cmd.add_argument("--k", type=int, default=6)

    return parser


def cmd_ingest(path: Path) -> None:
    config = MemoryConfig()
    _, vector_store = create_runtime(config)
    pipeline = IngestionPipeline(config, vector_store)
    stats = pipeline.ingest_path(path)
    print(f"processed={stats['processed']} updated={stats['updated']} skipped={stats['skipped']}")


def cmd_query(text: str, top_k: int) -> None:
    config = MemoryConfig()
    config.context.max_chunks = top_k
    _, _, _, context_builder = create_services(config)
    print(context_builder.build_context(text))


def cmd_add_fact(subject: str, attribute: str, value: str, source: str) -> None:
    config = MemoryConfig()
    _, fact_store, _, _ = create_services(config)
    fact_id = fact_store.add_fact(subject=subject, attribute=attribute, value=value, source=source)
    print(f"fact_id={fact_id}")


def cmd_fact_history(subject: str, attribute: str) -> None:
    config = MemoryConfig()
    _, fact_store, _, _ = create_services(config)
    rows = fact_store.get_fact_history(subject, attribute)
    for row in rows:
        print(
            f"id={row.id} value={row.value} status={row.status} "
            f"valid_from={row.valid_from} valid_to={row.valid_to}"
        )


def cmd_eval(dataset: Path | None, k: int) -> None:
    config = MemoryConfig()
    _, _, retriever, _ = create_services(config)
    ds_path = dataset or config.paths.eval_dataset_path
    cases = load_eval_cases(ds_path)
    metrics = evaluate(retriever, cases, k=k)
    print(f"cases={metrics.cases}")
    print(f"recall@{k}={metrics.recall_at_k:.4f}")
    print(f"mrr={metrics.mrr:.4f}")


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "ingest":
        cmd_ingest(args.path)
    elif args.command == "query":
        cmd_query(args.text, args.top_k)
    elif args.command == "add-fact":
        cmd_add_fact(args.subject, args.attribute, args.value, args.source)
    elif args.command == "fact-history":
        cmd_fact_history(args.subject, args.attribute)
    elif args.command == "eval":
        cmd_eval(args.dataset, args.k)


if __name__ == "__main__":
    main()
