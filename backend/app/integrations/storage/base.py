"""Storage abstraction for uploaded files.

The database stores only the key (e.g. ``products/<id>/<uuid>.webp``). Swap the local
backend for an S3-compatible one by implementing ``Storage`` and selecting it with
``STORAGE_BACKEND``.
"""

from __future__ import annotations

from typing import Protocol


class Storage(Protocol):
    async def save(self, key: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    def url(self, key: str) -> str: ...
