from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.integrations.storage.base import Storage
from app.integrations.storage.local import LocalStorage


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalStorage(settings)
    raise RuntimeError(f"Unknown STORAGE_BACKEND: {settings.storage_backend}")
