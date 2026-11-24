"""Shopping cart. Prices are always read live from the catalog, never stored in the cart."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    AppError,
    BusinessRuleError,
    InsufficientStockError,
    NotFoundError,
)
from app.core.money import ZERO, money
from app.models import Cart, CartItem, Product, ProductVariant, PromoCode
from app.repositories.products import ProductRepository
from app.services.promo import PromoService

MAX_LINE_QUANTITY = 999
MAX_CART_LINES = 50


@dataclass(frozen=True, slots=True)
class CartLine:
    item_id: uuid.UUID
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    variant_name: str
    sku: str
    attributes: dict[str, object]
    original_unit_price: Decimal
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    available: int
    # False when the product was deactivated or there is not enough stock for this quantity.
    is_purchasable: bool


@dataclass(frozen=True, slots=True)
class CartSummary:
    cart_id: uuid.UUID
    lines: list[CartLine]
    subtotal: Decimal  # purchasable lines only
    discount: Decimal
    promo_code: str | None
    promo_error: str | None  # why an applied code currently gives no discount
    total_quantity: int

    @property
    def total(self) -> Decimal:
        return self.subtotal - self.discount

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def has_problems(self) -> bool:
        return any(not line.is_purchasable for line in self.lines)


def _line(item: CartItem) -> CartLine:
    variant = item.variant
    product: Product = variant.product
    available = variant.inventory.available if variant.inventory else 0
    visible = variant.is_active and product.is_active and product.deleted_at is None
    unit = money(variant.effective_price)
    return CartLine(
        item_id=item.id,
        variant_id=variant.id,
        product_id=product.id,
        product_name=product.name,
        variant_name=variant.name,
        sku=variant.sku,
        attributes=dict(variant.attributes),
        original_unit_price=money(variant.price),
        unit_price=unit,
        quantity=item.quantity,
        line_total=unit * item.quantity,
        available=max(available, 0),
        is_purchasable=visible and available >= item.quantity,
    )


class CartService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.products = ProductRepository(session)

    async def _get_or_create(self, user_id: uuid.UUID, *, lock: bool = False) -> Cart:
        stmt = (
            select(Cart)
            .where(Cart.user_id == user_id)
            .options(
                selectinload(Cart.items)
                .selectinload(CartItem.variant)
                .selectinload(ProductVariant.product),
                selectinload(Cart.items)
                .selectinload(CartItem.variant)
                .selectinload(ProductVariant.inventory),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update(of=Cart)
        cart = await self.session.scalar(stmt)
        if cart is None:
            cart = Cart(user_id=user_id)
            self.session.add(cart)
            await self.session.flush()
            await self.session.refresh(cart, ["items"])
        return cart

    async def _find_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> CartItem:
        item = await self.session.scalar(
            select(CartItem)
            .join(Cart, Cart.id == CartItem.cart_id)
            .where(CartItem.id == item_id, Cart.user_id == user_id)
        )
        if item is None:
            raise NotFoundError("Savatda bunday mahsulot yo‘q.")
        return item

    async def _check_quantity(self, variant_id: uuid.UUID, quantity: int) -> None:
        if not 1 <= quantity <= MAX_LINE_QUANTITY:
            raise BusinessRuleError(
                f"Miqdor 1 dan {MAX_LINE_QUANTITY} gacha bo‘lishi kerak.", code="invalid_quantity"
            )
        variant = await self.products.get_purchasable_variant(variant_id)
        if variant is None:
            raise NotFoundError("Mahsulot topilmadi yoki sotuvda emas.")
        available = variant.inventory.available if variant.inventory else 0
        if available < quantity:
            name = variant.product.name
            raise InsufficientStockError(
                f"«{name}» tugagan."
                if available <= 0
                else f"«{name}» dan faqat {available} dona qoldi.",
                details={"variant_id": str(variant_id), "available": max(available, 0)},
            )

    async def add_item(
        self, user_id: uuid.UUID, variant_id: uuid.UUID, quantity: int = 1
    ) -> CartSummary:
        cart = await self._get_or_create(user_id, lock=True)
        existing = next((i for i in cart.items if i.variant_id == variant_id), None)
        new_quantity = (existing.quantity if existing else 0) + quantity
        if existing is None and len(cart.items) >= MAX_CART_LINES:
            raise BusinessRuleError("Savat to‘lgan.", code="cart_full")
        await self._check_quantity(variant_id, new_quantity)
        if existing:
            existing.quantity = new_quantity
        else:
            self.session.add(CartItem(cart_id=cart.id, variant_id=variant_id, quantity=quantity))
        await self.session.commit()
        return await self.summary(user_id)

    async def set_quantity(
        self, user_id: uuid.UUID, item_id: uuid.UUID, quantity: int
    ) -> CartSummary:
        item = await self._find_item(user_id, item_id)
        if quantity == 0:
            await self.session.delete(item)
        else:
            await self._check_quantity(item.variant_id, quantity)
            item.quantity = quantity
        await self.session.commit()
        return await self.summary(user_id)

    async def remove_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> CartSummary:
        return await self.set_quantity(user_id, item_id, 0)

    async def clear(self, user_id: uuid.UUID) -> None:
        await self.clear_in_transaction(user_id)
        await self.session.commit()

    async def clear_in_transaction(self, user_id: uuid.UUID) -> None:
        """Empty the cart as part of the caller's transaction (used by checkout)."""
        await self.session.execute(
            delete(CartItem).where(
                CartItem.cart_id.in_(select(Cart.id).where(Cart.user_id == user_id))
            )
        )
        await self.session.execute(
            update(Cart).where(Cart.user_id == user_id).values(promo_code_id=None)
        )

    async def apply_promo(self, user_id: uuid.UUID, code: str) -> CartSummary:
        cart = await self._get_or_create(user_id)
        promos = PromoService(self.session)
        promo = await promos.find(code)
        lines = [_line(i) for i in cart.items]
        subtotal = sum((ln.line_total for ln in lines if ln.is_purchasable), ZERO)
        if subtotal <= ZERO:
            raise BusinessRuleError("Avval savatga mahsulot qo‘shing.", code="cart_empty")
        await promos.evaluate(promo, user_id=user_id, subtotal=subtotal)  # raises if unusable
        cart.promo_code_id = promo.id
        await self.session.commit()
        return await self.summary(user_id)

    async def remove_promo(self, user_id: uuid.UUID) -> CartSummary:
        cart = await self._get_or_create(user_id)
        cart.promo_code_id = None
        await self.session.commit()
        return await self.summary(user_id)

    async def summary(self, user_id: uuid.UUID, *, lock: bool = False) -> CartSummary:
        cart = await self._get_or_create(user_id, lock=lock)
        lines = [_line(i) for i in cart.items]
        subtotal = sum((ln.line_total for ln in lines if ln.is_purchasable), ZERO)

        discount, promo_code, promo_error = ZERO, None, None
        if cart.promo_code_id is not None:
            promo = await self.session.get(PromoCode, cart.promo_code_id)
            if promo is not None:
                promo_code = promo.code
                try:
                    discount = await PromoService(self.session).evaluate(
                        promo, user_id=user_id, subtotal=subtotal
                    )
                except AppError as exc:
                    promo_error = exc.message
        return CartSummary(
            cart_id=cart.id,
            lines=lines,
            subtotal=subtotal,
            discount=discount,
            promo_code=promo_code,
            promo_error=promo_error,
            total_quantity=sum(ln.quantity for ln in lines),
        )
