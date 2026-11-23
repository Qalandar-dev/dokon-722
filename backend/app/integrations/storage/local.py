from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import Settings


class LocalStorage:
    """Files under ``MEDIA_ROOT`` served at ``MEDIA_URL`` (by Nginx in Docker)."""

    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.media_root).resolve()
        self.base_url = settings.media_url.rstrip("/")

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):  # never write outside MEDIA_ROOT
            raise ValueError("Invalid storage key")
        return path

    async def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)

        await asyncio.to_thread(_write)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    def url(self, key: str) -> str:
        return f"{self.base_url}/{key}"
