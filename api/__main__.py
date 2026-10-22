from __future__ import annotations

import uvicorn

from jarvis_memory.config import MemoryConfig


def main() -> None:
    server = MemoryConfig.from_env().server
    uvicorn.run("api.main:create_app", factory=True, host=server.host, port=server.port)


if __name__ == "__main__":
    main()
