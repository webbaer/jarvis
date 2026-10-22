from jarvis_memory.ingestion.chunker import ChunkingParams, split_into_chunks


def test_chunking_respects_overlap_and_size() -> None:
    text = "\n\n".join([f"Absatz {i} " + ("x" * 120) for i in range(8)])
    params = ChunkingParams(max_chars=320, overlap_chars=50, min_chunk_chars=80)

    chunks = split_into_chunks(text, params)

    assert len(chunks) >= 2
    assert all(len(chunk) <= 400 for chunk in chunks)
    assert chunks[1][:30] in chunks[0][-80:]


def test_chunking_empty_text() -> None:
    chunks = split_into_chunks("", ChunkingParams(max_chars=300, overlap_chars=50, min_chunk_chars=50))
    assert chunks == []
