from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.services.catalog import Page as ServicePage

# Money in JSON is always a string with exactly two decimals ("1250000.00"): exact,
# and the same shape whether the value came from the database or from a calculation.
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: f"{v.quantize(Decimal('0.01'))}", return_type=str, when_used="json"),
]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InputSchema(BaseModel):
    """Request bodies: unknown fields are rejected, strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, page: ServicePage[Any], convert: Callable[[Any], T]) -> Page[T]:
        return cls(
            items=[convert(item) for item in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
            pages=page.pages,
        )


class Message(BaseModel):
    message: str
