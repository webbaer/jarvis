from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ChunkingParams:
    max_chars: int
    overlap_chars: int
    min_chunk_chars: int


def split_into_chunks(text: str, params: ChunkingParams) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current and current_len + 2 + para_len > params.max_chars:
            chunks.append("\n\n".join(current))
            carry = _overlap_tail(chunks[-1], params.overlap_chars)
            current = [carry] if carry else []
            current_len = len(carry)

        current.append(para)
        current_len += para_len + (2 if len(current) > 1 else 0)

    if current:
        chunks.append("\n\n".join(current))

    merged: list[str] = []
    for chunk in chunks:
        if not merged:
            merged.append(chunk)
            continue
        if len(chunk) < params.min_chunk_chars:
            merged[-1] = f"{merged[-1]}\n\n{chunk}".strip()
        else:
            merged.append(chunk)
    return merged


def detect_overlap(previous: str, current: str, overlap_chars: int) -> int:
    """Length of the prefix of `current` that was carried over from `previous`."""
    carry = _overlap_tail(previous, overlap_chars)
    if carry and current.startswith(carry):
        return len(carry)
    return 0


def _overlap_tail(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or len(text) <= overlap_chars:
        return text if len(text) <= overlap_chars else ""
    return text[-overlap_chars:]
