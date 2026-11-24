from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.money import ZERO
from app.core.phone import normalize_uz_phone
from app.models import Address, Order, User
from app.models.enums import PaymentStatus
from app.services.audit import record_audit
from app.services.catalog import Page
from app.services.delivery import DeliveryService

MAX_ADDRESSES = 10


@dataclass(frozen=True, slots=True)
class TelegramProfile:
    telegram_id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


@dataclass(frozen=True, slots=True)
class CustomerStats:
    user: User
    orders_count: int
    total_spent: Decimal
    last_order_at: datetime | None


@dataclass(frozen=True, slots=True)
class AddressInput:
    district_id: int
    recipient_name: str
    recipient_phone: str
    address_line: str
    landmark: str | None = None
    instructions: str | None = None
    is_default: bool = False


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Telegram identity -------------------------------------------------------

    async def by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.session.scalar(select(User).where(User.telegram_id == telegram_id))

    async def register(self, profile: TelegramProfile) -> tuple[User, bool]:
        """Create the customer, or refresh their Telegram profile data. Returns (user, created)."""
        user = await self.by_telegram_id(profile.telegram_id)
        created = user is None
        if user is None:
            user = User(telegram_id=profile.telegram_id, first_name=profile.first_name[:128])
            self.session.add(user)
        user.first_name = profile.first_name[:128] or user.first_name
        user.last_name = (profile.last_name or "")[:128] or None
        user.username = (profile.username or "")[:64] or None
        user.last_seen_at = utcnow()
        await self.session.commit()
        return user, created

    async def set_phone_from_contact(
        self, user: User, *, phone: str, contact_user_id: int | None
    ) -> User:
        """Store a phone shared via Telegram's "share contact" button.

        It is marked verified only if the shared contact is the user's own account
        (Telegram sets ``contact.user_id``); a forwarded contact of someone else is not.
        """
        user.phone = normalize_uz_phone(phone)
        user.phone_verified = contact_user_id is not None and contact_user_id == user.telegram_id
        await self.session.commit()
        return user

    # --- Addresses ----------------------------------------------------------------

    async def addresses(self, user_id: uuid.UUID) -> list[Address]:
        return list(
            await self.session.scalars(
                select(Address)
                .where(Address.user_id == user_id)
                .order_by(Address.is_default.desc(), Address.created_at.desc())
            )
        )

    async def _owned_address(self, user_id: uuid.UUID, address_id: uuid.UUID) -> Address:
        address = await self.session.get(Address, address_id)
        if address is None or address.user_id != user_id:
            raise NotFoundError("Manzil topilmadi.")
        return address

    async def _validate(self, data: AddressInput) -> tuple[str, str, str]:
        await DeliveryService(self.session).location(data.district_id)
        name = " ".join(data.recipient_name.split())[:128]
        line = " ".join(data.address_line.split())[:255]
        if not name:
            raise BusinessRuleError(
                "Qabul qiluvchining ismini kiriting.", code="recipient_required"
            )
        if not line:
            raise BusinessRuleError("Manzilni kiriting.", code="address_required")
        return name, line, normalize_uz_phone(data.recipient_phone)

    async def _clear_default(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Address).where(Address.user_id == user_id).values(is_default=False)
        )

    async def add_address(self, user_id: uuid.UUID, data: AddressInput) -> Address:
        existing = await self.addresses(user_id)
        if len(existing) >= MAX_ADDRESSES:
            raise BusinessRuleError(
                f"{MAX_ADDRESSES} tadan ortiq manzil saqlab bo‘lmaydi.", code="too_many_addresses"
            )
        name, line, phone = await self._validate(data)
        make_default = data.is_default or not existing
        if make_default:
            await self._clear_default(user_id)
        address = Address(
            user_id=user_id,
            district_id=data.district_id,
            recipient_name=name,
            recipient_phone=phone,
            address_line=line,
            landmark=(data.landmark or "").strip()[:255] or None,
            instructions=(data.instructions or "").strip()[:1000] or None,
            is_default=make_default,
        )
        self.session.add(address)
        await self.session.commit()
        return address

    async def update_address(
        self, user_id: uuid.UUID, address_id: uuid.UUID, data: AddressInput
    ) -> Address:
        address = await self._owned_address(user_id, address_id)
        name, line, phone = await self._validate(data)
        if data.is_default and not address.is_default:
            await self._clear_default(user_id)
        address.district_id = data.district_id
        address.recipient_name = name
        address.recipient_phone = phone
        address.address_line = line
        address.landmark = (data.landmark or "").strip()[:255] or None
        address.instructions = (data.instructions or "").strip()[:1000] or None
        address.is_default = data.is_default or address.is_default
        await self.session.commit()
        await self.session.refresh(address)
        return address

    async def delete_address(self, user_id: uuid.UUID, address_id: uuid.UUID) -> None:
        address = await self._owned_address(user_id, address_id)
        was_default = address.is_default
        await self.session.delete(address)
        await self.session.flush()
        if was_default:
            newest = await self.session.scalar(
                select(Address)
                .where(Address.user_id == user_id)
                .order_by(Address.created_at.desc())
                .limit(1)
            )
            if newest is not None:
                newest.is_default = True
        await self.session.commit()

    # --- Admin ----------------------------------------------------------------------

    def _stats_query(self):  # type: ignore[no-untyped-def]
        paid = Order.payment_status == PaymentStatus.PAID
        return (
            select(
                User,
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.total).filter(paid), ZERO).label("total_spent"),
                func.max(Order.created_at).label("last_order_at"),
            )
            .outerjoin(Order, Order.user_id == User.id)
            .group_by(User.id)
        )

    async def list_for_admin(
        self,
        *,
        query: str | None = None,
        blocked: bool | None = None,
        sort: str = "newest",
        page: int = 1,
        page_size: int = 20,
    ) -> Page[CustomerStats]:
        stmt = self._stats_query()
        if query and (q := query.strip()):
            like = f"%{q}%"
            conditions = [
                User.first_name.ilike(like),
                User.last_name.ilike(like),
                User.username.ilike(like.lstrip("@")),
                User.phone.ilike(f"%{''.join(ch for ch in q if ch.isdigit()) or q}%"),
            ]
            if q.isdigit():
                conditions.append(User.telegram_id == int(q))
            stmt = stmt.where(or_(*conditions))
        if blocked is not None:
            stmt = stmt.where(User.is_blocked == blocked)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        order_by = {
            "newest": [User.created_at.desc()],
            "spent": [
                func.coalesce(
                    func.sum(Order.total).filter(Order.payment_status == PaymentStatus.PAID), 0
                ).desc()
            ],
            "orders": [func.count(Order.id).desc()],
        }.get(sort, [User.created_at.desc()])
        rows = await self.session.execute(
            stmt.order_by(*order_by, User.id).offset((page - 1) * page_size).limit(page_size)
        )
        items = [CustomerStats(r[0], r.orders_count, r.total_spent, r.last_order_at) for r in rows]
        return Page(items=items, total=total, page=page, page_size=page_size)

    async def stats_for(self, user_id: uuid.UUID) -> CustomerStats:
        row = (await self.session.execute(self._stats_query().where(User.id == user_id))).first()
        if row is None:
            raise NotFoundError("Mijoz topilmadi.")
        return CustomerStats(row[0], row.orders_count, row.total_spent, row.last_order_at)

    async def set_blocked(
        self, user_id: uuid.UUID, blocked: bool, *, admin_user_id: uuid.UUID
    ) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("Mijoz topilmadi.")
        before = user.is_blocked
        user.is_blocked = blocked
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="customer.block" if blocked else "customer.unblock",
            entity_type="user",
            entity_id=user.id,
            changes={"is_blocked": {"from": before, "to": blocked}},
        )
        await self.session.commit()
        return user
