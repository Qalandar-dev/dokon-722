"""Image upload validation. The file's real type is detected from its first bytes;
the client-supplied name and Content-Type are not trusted."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.exceptions import BusinessRuleError


@dataclass(frozen=True, slots=True)
class ImageType:
    extension: str
    content_type: str


def detect_image_type(data: bytes) -> ImageType | None:
    if data.startswith(b"\xff\xd8\xff"):
        return ImageType("jpg", "image/jpeg")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ImageType("png", "image/png")
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ImageType("webp", "image/webp")
    return None


def validate_image(data: bytes, *, max_bytes: int) -> ImageType:
    if not data:
        raise BusinessRuleError("Fayl bo‘sh.", code="empty_file")
    if len(data) > max_bytes:
        raise BusinessRuleError(
            f"Fayl hajmi {max_bytes // (1024 * 1024)} MB dan oshmasligi kerak.",
            code="file_too_large",
        )
    image_type = detect_image_type(data)
    if image_type is None:
        raise BusinessRuleError(
            "Faqat JPG, PNG yoki WEBP rasm yuklash mumkin.", code="unsupported_file_type"
        )
    return image_type


def image_key(folder: str, owner_id: uuid.UUID, image_type: ImageType) -> str:
    return f"{folder}/{owner_id}/{uuid.uuid4().hex}.{image_type.extension}"
