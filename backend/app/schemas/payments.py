from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import Payment
from app.models.enums import PaymentProvider, PaymentStatus
from app.schemas.common import InputSchema, Money


class PaymentStartIn(InputSchema):
    order_id: uuid.UUID


class PaymentOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    provider: PaymentProvider
    amount: Money
    status: PaymentStatus
    is_simulated: bool
    failure_reason: str | None
    created_at: datetime
    paid_at: datetime | None

    @classmethod
    def build(cls, p: Payment) -> PaymentOut:
        return cls(**{f: getattr(p, f) for f in cls.model_fields})


class PaymentStartOut(BaseModel):
    payment: PaymentOut
    checkout_url: str
