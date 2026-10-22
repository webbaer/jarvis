from pathlib import Path

import pytest

from jarvis_memory.config import MemoryConfig, PathsConfig


@pytest.fixture
def memory_config(tmp_path: Path) -> MemoryConfig:
    config = MemoryConfig()
    config.paths = PathsConfig.under(tmp_path / ".memory")
    config.paths.eval_dataset_path = tmp_path / "eval.yaml"
    config.chunking.max_chars = 200
    config.chunking.overlap_chars = 40
    config.chunking.min_chunk_chars = 30
    return config


@pytest.fixture
def api_client(memory_config: MemoryConfig):
    from fastapi.testclient import TestClient

    from api.main import create_app

    with TestClient(create_app(memory_config)) as client:
        yield client
