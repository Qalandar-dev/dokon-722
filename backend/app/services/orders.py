"""Checkout and order lifecycle.

Every public method is one database transaction: it either commits all of its
effects (order rows, stock movements, promo use, status history, audit) or none.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    PromoCodeError,
)
from app.core.money import ZERO
from app.core.phone import normalize_uz_phone
from app.models import Cart, Order, OrderItem, OrderStatusHistory, Product, User
from app.models.enums import (
    ActorType,
    DeliveryStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    StatusField,
    StockState,
)
from app.services import order_status as rules
from app.services.audit import record_audit
from app.services.cart import CartService, CartSummary
from app.services.catalog import Page
from app.services.delivery import DeliveryQuote, DeliveryService, Location
from app.services.inventory import InventoryService, StockLine
from app.services.promo import PromoService
from app.services.store_settings import StoreSettingsService

ONLINE_METHODS = frozenset({PaymentMethod.CLICK, PaymentMethod.PAYME})


@dataclass(frozen=True, slots=True)
class CheckoutRequest:
    user_id: uuid.UUID
    idempotency_key: str
    recipient_name: str
    recipient_phone: str
    district_id: int
    address_line: str
    delivery_method_id: uuid.UUID
    payment_method: PaymentMethod
    landmark: str | None = None
    delivery_instructions: str | None = None
    customer_note: str | None = None


@dataclass(frozen=True, slots=True)
class CheckoutPreview:
    cart: CartSummary
    location: Location
    delivery: DeliveryQuote
    subtotal: Decimal
    discount: Decimal
    delivery_fee: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True)
class Actor:
    type: ActorType
    admin_user_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None

    @classmethod
    def admin(cls, admin_user_id: uuid.UUID) -> Actor:
        return cls(ActorType.ADMIN, admin_user_id=admin_user_id)

    @classmethod
    def customer(cls, user_id: uuid.UUID) -> Actor:
        return cls(ActorType.CUSTOMER, user_id=user_id)

    @classmethod
    def system(cls) -> Actor:
        return cls(ActorType.SYSTEM)

    @classmethod
    def provider(cls) -> Actor:
        return cls(ActorType.PROVIDER)


def _clean(value: str | None, *, max_len: int) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value[:max_len] or None


def _stock_lines(order: Order) -> list[StockLine]:
    return [StockLine(i.variant_id, i.quantity) for i in order.items if i.variant_id is not None]


class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.inventory = InventoryService(session)
        self.promos = PromoService(session)

    # --- Queries ---------------------------------------------------------------

    async def _load(self, order_id: uuid.UUID, *, lock: bool = False) -> Order:
        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items), selectinload(Order.history))
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update(of=Order)
        order = await self.session.scalar(stmt)
        if order is None:
            raise NotFoundError("Buyurtma topilmadi.")
        return order

    async def get(self, order_id: uuid.UUID) -> Order:
        return await self._load(order_id)

    async def get_for_user(self, order_id: uuid.UUID, user_id: uuid.UUID) -> Order:
        order = await self._load(order_id)
        if order.user_id != user_id:  # same error as "missing": don't reveal other orders
            raise NotFoundError("Buyurtma topilmadi.")
        return order

    async def list_for_user(
        self, user_id: uuid.UUID, *, page: int = 1, page_size: int = 10
    ) -> Page[Order]:
        base = select(Order).where(Order.user_id == user_id)
        total = await self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        orders = (
            await self.session.scalars(
                base.options(selectinload(Order.items))
                .order_by(Order.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return Page(items=list(orders), total=total, page=page, page_size=page_size)

    # --- Checkout --------------------------------------------------------------

    async def preview(
        self,
        user_id: uuid.UUID,
        *,
        district_id: int,
        delivery_method_id: uuid.UUID,
        lock_cart: bool = False,
    ) -> CheckoutPreview:
        """Exactly what the customer will pay. ``place_order`` uses the same calculation."""
        cart = await CartService(self.session).summary(user_id, lock=lock_cart)
        if cart.is_empty:
            raise BusinessRuleError("Savat boʻsh.", code="cart_empty")
        if cart.has_problems:
            raise BusinessRuleError(
                "Savatdagi baʼzi mahsulotlar tugagan yoki sotuvdan olingan. Savatni yangilang.",
                code="cart_has_unavailable_items",
                details={
                    "items": [
                        {"item_id": str(ln.item_id), "available": ln.available}
                        for ln in cart.lines
                        if not ln.is_purchasable
                    ]
                },
            )
        if cart.promo_error:
            raise PromoCodeError(cart.promo_error)
        delivery_service = DeliveryService(self.session)
        location = await delivery_service.location(district_id)
        after_discount = cart.subtotal - cart.discount
        quote = await delivery_service.quote(delivery_method_id, district_id, after_discount)
        return CheckoutPreview(
            cart=cart,
            location=location,
            delivery=quote,
            subtotal=cart.subtotal,
            discount=cart.discount,
            delivery_fee=quote.price,
            total=after_discount + quote.price,
        )

    async def _by_idempotency_key(self, user_id: uuid.UUID, key: str) -> Order | None:
        order_id = await self.session.scalar(
            select(Order.id).where(Order.user_id == user_id, Order.idempotency_key == key)
        )
        return await self._load(order_id) if order_id else None

    async def place_order(self, req: CheckoutRequest, *, now: datetime | None = None) -> Order:
        """Create an order from the customer's cart.

        Idempotent: repeating the call with the same ``idempotency_key`` (double tap,
        network retry, concurrent duplicate) returns the order created the first time.
        """
        now = now or utcnow()
        key = req.idempotency_key.strip()
        if not 8 <= len(key) <= 64:
            raise BusinessRuleError("Soʻrov kaliti notoʻgʻri.", code="invalid_idempotency_key")
        if (existing := await self._by_idempotency_key(req.user_id, key)) is not None:
            return existing

        user = await self.session.get(User, req.user_id)
        if user is None:
            raise NotFoundError("Mijoz topilmadi.")
        if user.is_blocked:
            raise PermissionDeniedError(
                "Hisobingiz bloklangan. Qoʻllab-quvvatlash bilan bogʻlaning."
            )
        if not await StoreSettingsService(self.session).payment_method_enabled(req.payment_method):
            raise BusinessRuleError(
                "Bu toʻlov usuli hozircha mavjud emas.", code="payment_method_unavailable"
            )
        recipient_name = _clean(req.recipient_name, max_len=128)
        address_line = _clean(req.address_line, max_len=255)
        if not recipient_name:
            raise BusinessRuleError(
                "Qabul qiluvchining ismini kiriting.", code="recipient_required"
            )
        if not address_line:
            raise BusinessRuleError("Manzilni kiriting.", code="address_required")
        phone = normalize_uz_phone(req.recipient_phone)

        # Lock the customer's cart row: checkouts of the same cart run one at a time.
        # A duplicate request that waited here must see the order the first one created,
        # so the idempotency key is checked again under the lock.
        await self._lock_cart(req.user_id)
        existing_id = await self.session.scalar(
            select(Order.id).where(Order.user_id == req.user_id, Order.idempotency_key == key)
        )
        if existing_id is not None:
            await self.session.rollback()  # release the cart lock before reading
            return await self._load(existing_id)
        p = await self.preview(
            req.user_id,
            district_id=req.district_id,
            delivery_method_id=req.delivery_method_id,
        )
        cart_promo_id = await self._cart_promo_id(req.user_id)

        order = Order(
            user_id=req.user_id,
            payment_method=req.payment_method,
            subtotal=p.subtotal,
            discount_total=p.discount,
            delivery_fee=p.delivery_fee,
            total=p.total,
            recipient_name=recipient_name,
            recipient_phone=phone,
            region_id=p.location.region_id,
            district_id=p.location.district_id,
            region_name=p.location.region_name,
            district_name=p.location.district_name,
            address_line=address_line,
            landmark=_clean(req.landmark, max_len=255),
            delivery_instructions=_clean(req.delivery_instructions, max_len=1000),
            delivery_method_id=p.delivery.method_id,
            delivery_method_name=p.delivery.method_name,
            delivery_eta_min_days=p.delivery.eta_min_days,
            delivery_eta_max_days=p.delivery.eta_max_days,
            pickup_address=p.delivery.pickup_address,
            promo_code_id=cart_promo_id if p.discount > ZERO else None,
            promo_code=p.cart.promo_code if p.discount > ZERO else None,
            idempotency_key=key,
            customer_note=_clean(req.customer_note, max_len=1000),
            stock_state=StockState.RESERVED,
            reservation_expires_at=(
                now + timedelta(minutes=get_settings().order_reservation_ttl_minutes)
                if req.payment_method in ONLINE_METHODS
                else None
            ),
        )
        self.session.add(order)
        try:
            await self.session.flush()
        except IntegrityError:
            # A concurrent request with the same key won the race.
            await self.session.rollback()
            existing = await self._by_idempotency_key(req.user_id, key)
            if existing is None:
                raise
            return existing

        for line in p.cart.lines:
            self.session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=line.product_id,
                    variant_id=line.variant_id,
                    product_name=line.product_name,
                    variant_name=line.variant_name,
                    sku=line.sku,
                    attributes=line.attributes,
                    original_unit_price=line.original_unit_price,
                    unit_price=line.unit_price,
                    quantity=line.quantity,
                    line_total=line.line_total,
                )
            )
        await self.inventory.reserve(
            [StockLine(ln.variant_id, ln.quantity) for ln in p.cart.lines], order_id=order.id
        )
        if order.promo_code_id is not None:
            redeemed = await self.promos.redeem(
                order.promo_code_id,
                user_id=req.user_id,
                order_id=order.id,
                subtotal=p.subtotal,
                now=now,
            )
            if redeemed != p.discount:  # pragma: no cover - same rules, same inputs
                raise PromoCodeError("Promokod shartlari oʻzgardi. Savatni qayta tekshiring.")

        self._history(
            order, StatusField.STATUS, None, OrderStatus.PENDING, Actor.customer(req.user_id)
        )
        await CartService(self.session).clear_in_transaction(req.user_id)
        await self.session.commit()
        return await self._load(order.id)

    async def _lock_cart(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            pg_insert(Cart)
            .values(id=uuid.uuid4(), user_id=user_id)
            .on_conflict_do_nothing(index_elements=[Cart.user_id])
        )
        await self.session.execute(select(Cart.id).where(Cart.user_id == user_id).with_for_update())

    async def _cart_promo_id(self, user_id: uuid.UUID) -> uuid.UUID | None:
        return await self.session.scalar(select(Cart.promo_code_id).where(Cart.user_id == user_id))

    # --- Status changes --------------------------------------------------------

    def _history(
        self,
        order: Order,
        field: StatusField,
        from_value: str | None,
        to_value: str,
        actor: Actor,
        comment: str | None = None,
    ) -> None:
        self.session.add(
            OrderStatusHistory(
                order_id=order.id,
                field=field,
                from_value=from_value,
                to_value=to_value,
                actor_type=actor.type,
                admin_user_id=actor.admin_user_id,
                comment=comment,
            )
        )

    def _set_status(
        self, order: Order, target: OrderStatus, actor: Actor, comment: str | None, now: datetime
    ) -> None:
        rules.ensure_order_transition(order.status, target)
        self._history(order, StatusField.STATUS, order.status, target, actor, comment)
        order.status = target
        stamp = {
            OrderStatus.CONFIRMED: "confirmed_at",
            OrderStatus.SHIPPED: "shipped_at",
            OrderStatus.DELIVERED: "delivered_at",
            OrderStatus.CANCELLED: "cancelled_at",
        }.get(target)
        if stamp and getattr(order, stamp) is None:
            setattr(order, stamp, now)

    def _set_payment_status(
        self, order: Order, target: PaymentStatus, actor: Actor, comment: str | None = None
    ) -> None:
        rules.ensure_payment_transition(order.payment_status, target)
        self._history(
            order, StatusField.PAYMENT_STATUS, order.payment_status, target, actor, comment
        )
        order.payment_status = target

    def _set_delivery_status(
        self, order: Order, target: DeliveryStatus, actor: Actor, comment: str | None = None
    ) -> None:
        rules.ensure_delivery_transition(order.delivery_status, target)
        self._history(
            order, StatusField.DELIVERY_STATUS, order.delivery_status, target, actor, comment
        )
        order.delivery_status = target

    async def _sell(self, order: Order) -> None:
        """Reservation → sale, and count the units for "popular products"."""
        if order.stock_state is not StockState.RESERVED:
            raise ConflictError("Buyurtma zaxirasi allaqachon yopilgan.", code="stock_not_reserved")
        await self.inventory.commit_sale(_stock_lines(order), order_id=order.id)
        order.stock_state = StockState.SOLD
        order.reservation_expires_at = None
        await self._bump_sold_count(order, +1)

    async def _bump_sold_count(self, order: Order, sign: int) -> None:
        per_product: dict[uuid.UUID, int] = {}
        for item in order.items:
            if item.product_id is not None:
                per_product[item.product_id] = per_product.get(item.product_id, 0) + item.quantity
        for product_id, qty in sorted(per_product.items(), key=lambda kv: kv[0].bytes):
            await self.session.execute(
                update(Product)
                .where(Product.id == product_id)
                .values(sold_count=func.greatest(Product.sold_count + sign * qty, 0))
            )

    async def confirm_payment(
        self, order_id: uuid.UUID, *, actor: Actor | None = None, now: datetime | None = None
    ) -> Order:
        """Mark an online order as paid. Only call after the provider confirmed the payment
        on the server side (Phase 9). Repeated calls are harmless."""
        now = now or utcnow()
        actor = actor or Actor.provider()
        order = await self._load(order_id, lock=True)
        if order.payment_status is PaymentStatus.PAID:
            return order
        if order.status is not OrderStatus.PENDING or order.stock_state is not StockState.RESERVED:
            raise BusinessRuleError(
                "Bu buyurtma uchun toʻlov qabul qilib boʻlmaydi.",
                code="order_not_payable",
                details={"status": order.status.value},
            )
        self._set_payment_status(order, PaymentStatus.PAID, actor)
        order.paid_at = now
        await self._sell(order)
        await self.session.commit()
        return await self._load(order.id)

    async def confirm(
        self, order_id: uuid.UUID, *, admin_user_id: uuid.UUID, now: datetime | None = None
    ) -> Order:
        """Staff accepts the order. Online orders must be paid first; for cash orders the
        reservation becomes a sale now."""
        now = now or utcnow()
        actor = Actor.admin(admin_user_id)
        order = await self._load(order_id, lock=True)
        if (
            rules.requires_payment_before_confirm(order.payment_method)
            and order.payment_status is not PaymentStatus.PAID
        ):
            raise BusinessRuleError(
                "Toʻlov hali qabul qilinmagan. Onlayn buyurtma toʻlovdan keyin tasdiqlanadi.",
                code="payment_required",
            )
        self._set_status(order, OrderStatus.CONFIRMED, actor, None, now)
        if order.stock_state is StockState.RESERVED:
            await self._sell(order)
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="order.confirm",
            entity_type="order",
            entity_id=order.id,
        )
        await self.session.commit()
        return await self._load(order.id)

    async def change_status(
        self,
        order_id: uuid.UUID,
        target: OrderStatus,
        *,
        admin_user_id: uuid.UUID,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> Order:
        """Move an order forward (processing / shipped / out_for_delivery / delivered).
        Confirmation, cancellation and refunds have their own methods."""
        if target in {OrderStatus.CONFIRMED, OrderStatus.CANCELLED, OrderStatus.REFUNDED}:
            raise BusinessRuleError(
                "Bu amal uchun alohida tugmadan foydalaning.", code="use_dedicated_action"
            )
        now = now or utcnow()
        actor = Actor.admin(admin_user_id)
        order = await self._load(order_id, lock=True)
        before = order.status
        self._set_status(order, target, actor, comment, now)
        # Keep delivery status in step when it can move there.
        delivery_target = rules.ORDER_TO_DELIVERY.get(target)
        if (
            delivery_target is not None
            and delivery_target is not order.delivery_status
            and delivery_target in rules.DELIVERY_TRANSITIONS[order.delivery_status]
        ):
            self._set_delivery_status(order, delivery_target, actor, comment)
        if target is OrderStatus.DELIVERED:
            await self._on_delivered(order, actor, now)
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="order.status",
            entity_type="order",
            entity_id=order.id,
            changes={"status": {"from": before.value, "to": target.value}},
        )
        await self.session.commit()
        return await self._load(order.id)

    async def change_delivery_status(
        self,
        order_id: uuid.UUID,
        target: DeliveryStatus,
        *,
        admin_user_id: uuid.UUID,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> Order:
        now = now or utcnow()
        actor = Actor.admin(admin_user_id)
        order = await self._load(order_id, lock=True)
        if order.status in {OrderStatus.PENDING, OrderStatus.CANCELLED, OrderStatus.REFUNDED}:
            raise BusinessRuleError("Avval buyurtmani tasdiqlang.", code="order_not_in_fulfilment")
        before = order.delivery_status
        self._set_delivery_status(order, target, actor, comment)
        order_target = rules.DELIVERY_TO_ORDER.get(target)
        if order_target is not None and order_target is not order.status:
            self._set_status(order, order_target, actor, comment, now)
            if order_target is OrderStatus.DELIVERED:
                await self._on_delivered(order, actor, now)
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="order.delivery_status",
            entity_type="order",
            entity_id=order.id,
            changes={"delivery_status": {"from": before.value, "to": target.value}},
        )
        await self.session.commit()
        return await self._load(order.id)

    async def _on_delivered(self, order: Order, actor: Actor, now: datetime) -> None:
        # Cash collected by the courier on delivery.
        if (
            order.payment_method is PaymentMethod.CASH_ON_DELIVERY
            and order.payment_status is not PaymentStatus.PAID
        ):
            self._set_payment_status(order, PaymentStatus.PAID, actor, "Naqd toʻlov qabul qilindi")
            order.paid_at = now

    async def cancel(
        self,
        order_id: uuid.UUID,
        *,
        actor: Actor,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> Order:
        """Cancel an order and give its stock and promo use back.

        Customers may cancel while the order is new or confirmed and not yet paid;
        a paid order needs staff (cancellation + refund).
        """
        now = now or utcnow()
        order = await self._load(order_id, lock=True)
        if actor.type is ActorType.CUSTOMER:
            if order.user_id != actor.user_id:
                raise NotFoundError("Buyurtma topilmadi.")
            if order.status not in rules.CUSTOMER_CANCELLABLE:
                raise BusinessRuleError(
                    "Buyurtma joʻnatishga tayyorlanmoqda, uni endi bekor qilib boʻlmaydi. "
                    "Qoʻllab-quvvatlash bilan bogʻlaning.",
                    code="cancel_not_allowed",
                )
            if order.payment_status is PaymentStatus.PAID:
                raise BusinessRuleError(
                    "Toʻlangan buyurtmani bekor qilish uchun qoʻllab-quvvatlash bilan bogʻlaning.",
                    code="cancel_requires_support",
                )
        elif order.status not in rules.STAFF_CANCELLABLE:
            raise BusinessRuleError(
                "Joʻnatilgan buyurtmani bekor qilib boʻlmaydi; qaytarish (refund) dan foydalaning.",
                code="cancel_not_allowed",
            )

        reason = _clean(reason, max_len=255)
        self._set_status(order, OrderStatus.CANCELLED, actor, reason, now)
        order.cancel_reason = reason
        if order.payment_status in {
            PaymentStatus.PENDING,
            PaymentStatus.PROCESSING,
            PaymentStatus.FAILED,
        }:
            self._set_payment_status(order, PaymentStatus.CANCELLED, actor)

        if order.stock_state is StockState.RESERVED:
            await self.inventory.release(_stock_lines(order), order_id=order.id)
            order.stock_state = StockState.RELEASED
        elif order.stock_state is StockState.SOLD:  # nothing has left the warehouse yet
            await self.inventory.return_to_stock(
                _stock_lines(order),
                order_id=order.id,
                admin_user_id=actor.admin_user_id,
                reason="Buyurtma bekor qilindi",
            )
            order.stock_state = StockState.RETURNED
            await self._bump_sold_count(order, -1)
        order.reservation_expires_at = None
        await self.promos.release(order.id)

        if actor.type is ActorType.ADMIN:
            record_audit(
                self.session,
                admin_user_id=actor.admin_user_id,
                action="order.cancel",
                entity_type="order",
                entity_id=order.id,
                changes={"reason": reason},
            )
        await self.session.commit()
        return await self._load(order.id)

    async def record_refund(
        self,
        order_id: uuid.UUID,
        *,
        admin_user_id: uuid.UUID,
        restock: bool,
        reason: str,
        now: datetime | None = None,
    ) -> Order:
        """Record that the customer's money was returned.

        This changes statuses only. For Click/Payme the money is returned through the
        provider (Phase 9), which must succeed before this is called.
        """
        now = now or utcnow()
        actor = Actor.admin(admin_user_id)
        reason_clean = _clean(reason, max_len=255)
        if not reason_clean:
            raise BusinessRuleError("Qaytarish sababini kiriting.", code="reason_required")
        order = await self._load(order_id, lock=True)
        if order.payment_status is not PaymentStatus.PAID:
            raise BusinessRuleError(
                "Faqat toʻlangan buyurtma uchun pul qaytariladi.", code="refund_not_paid"
            )
        self._set_status(order, OrderStatus.REFUNDED, actor, reason_clean, now)
        self._set_payment_status(order, PaymentStatus.REFUNDED, actor, reason_clean)
        if order.delivery_status is DeliveryStatus.DELIVERY_FAILED:
            self._set_delivery_status(order, DeliveryStatus.RETURNED, actor, reason_clean)
        if restock and order.stock_state is StockState.SOLD:
            await self.inventory.return_to_stock(
                _stock_lines(order),
                order_id=order.id,
                admin_user_id=admin_user_id,
                reason=reason_clean,
            )
            order.stock_state = StockState.RETURNED
            await self._bump_sold_count(order, -1)
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="order.refund",
            entity_type="order",
            entity_id=order.id,
            changes={"reason": reason_clean, "restock": restock, "amount": str(order.total)},
        )
        await self.session.commit()
        return await self._load(order.id)

    async def set_internal_note(
        self, order_id: uuid.UUID, note: str | None, *, admin_user_id: uuid.UUID
    ) -> Order:
        order = await self._load(order_id, lock=True)
        before = order.internal_note
        order.internal_note = (note or "").strip()[:4000] or None
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="order.note",
            entity_type="order",
            entity_id=order.id,
            changes={"internal_note": {"from": before, "to": order.internal_note}},
        )
        await self.session.commit()
        return await self._load(order.id)

    async def expire_unpaid(self, *, now: datetime | None = None, batch: int = 100) -> int:
        """Cancel online orders whose payment window has passed. Run by the worker.

        Each order is locked with ``SKIP LOCKED`` and re-checked under the lock, so an
        order that a payment callback is handling right now is left alone, and several
        workers can run at once.
        """
        now = now or utcnow()
        expired_condition = (
            Order.reservation_expires_at.is_not(None),
            Order.reservation_expires_at < now,
            Order.status == OrderStatus.PENDING,
            Order.payment_status.in_(
                [PaymentStatus.PENDING, PaymentStatus.FAILED, PaymentStatus.CANCELLED]
            ),
        )
        candidates = list(
            await self.session.scalars(
                select(Order.id)
                .where(*expired_condition)
                .order_by(Order.reservation_expires_at)
                .limit(batch)
            )
        )
        await self.session.rollback()  # end the read-only transaction
        expired = 0
        for order_id in candidates:
            locked = await self.session.scalar(
                select(Order.id)
                .where(Order.id == order_id, *expired_condition)
                .with_for_update(skip_locked=True)
            )
            if locked is None:
                await self.session.rollback()
                continue
            await self.cancel(
                order_id, actor=Actor.system(), reason="Toʻlov muddati tugadi", now=now
            )
            expired += 1
        return expired
