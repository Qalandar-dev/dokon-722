"""Customer endpoints, called by the Telegram bot on behalf of a customer.

Authentication: ``X-Bot-Secret`` (shared secret, internal network only) plus
``X-Telegram-User-Id`` identifying the customer.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import CustomerDep, SessionDep, bot_auth
from app.core.exceptions import NotFoundError
from app.models import ProductImage
from app.schemas.catalog import (
    AddCartItemIn,
    CartOut,
    PromoCodeIn,
    TelegramFileIdIn,
    UpdateCartItemIn,
)
from app.schemas.common import Page
from app.schemas.orders import (
    AddressIn,
    AddressOut,
    CancelIn,
    CheckoutPreviewIn,
    CheckoutPreviewOut,
    OrderCreateIn,
    OrderOut,
    OrderSummaryOut,
    PhoneIn,
    ProfileOut,
    RegisterIn,
    RegisterOut,
    address_out,
    profile_out,
)
from app.services.cart import CartService
from app.services.customers import AddressInput, CustomerService, TelegramProfile
from app.services.orders import Actor, CheckoutRequest, OrderService

router = APIRouter(tags=["customer (bot)"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=64,
        description="Unique per checkout attempt; repeating it returns the same order.",
    ),
]


@router.post(
    "/customers/register",
    response_model=RegisterOut,
    dependencies=[Depends(bot_auth)],
)
async def register(body: RegisterIn, session: SessionDep, response: Response) -> RegisterOut:
    user, created = await CustomerService(session).register(
        TelegramProfile(
            telegram_id=body.telegram_id,
            first_name=body.first_name,
            last_name=body.last_name,
            username=body.username,
            language_code=body.language_code,
        )
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return RegisterOut(profile=profile_out(user), created=created)


@router.post("/customers/phone", response_model=ProfileOut)
async def set_phone(body: PhoneIn, user: CustomerDep, session: SessionDep) -> ProfileOut:
    updated = await CustomerService(session).set_phone_from_contact(
        user, phone=body.phone, contact_user_id=body.contact_user_id
    )
    return profile_out(updated)


@router.get("/profile", response_model=ProfileOut)
async def profile(user: CustomerDep) -> ProfileOut:
    return profile_out(user)


# --- Addresses ---------------------------------------------------------------------------


@router.get("/addresses", response_model=list[AddressOut])
async def list_addresses(user: CustomerDep, session: SessionDep) -> list[AddressOut]:
    return [address_out(a) for a in await CustomerService(session).addresses(user.id)]


def _address_input(body: AddressIn) -> AddressInput:
    return AddressInput(**body.model_dump())


@router.post("/addresses", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
async def add_address(body: AddressIn, user: CustomerDep, session: SessionDep) -> AddressOut:
    return address_out(await CustomerService(session).add_address(user.id, _address_input(body)))


@router.patch("/addresses/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: uuid.UUID, body: AddressIn, user: CustomerDep, session: SessionDep
) -> AddressOut:
    address = await CustomerService(session).update_address(
        user.id, address_id, _address_input(body)
    )
    return address_out(address)


@router.delete("/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(address_id: uuid.UUID, user: CustomerDep, session: SessionDep) -> None:
    await CustomerService(session).delete_address(user.id, address_id)


# --- Cart --------------------------------------------------------------------------------


@router.get("/cart", response_model=CartOut)
async def get_cart(user: CustomerDep, session: SessionDep) -> CartOut:
    return CartOut.build(await CartService(session).summary(user.id))


@router.post("/cart/items", response_model=CartOut)
async def add_to_cart(body: AddCartItemIn, user: CustomerDep, session: SessionDep) -> CartOut:
    return CartOut.build(
        await CartService(session).add_item(user.id, body.variant_id, body.quantity)
    )


@router.patch("/cart/items/{item_id}", response_model=CartOut)
async def update_cart_item(
    item_id: uuid.UUID, body: UpdateCartItemIn, user: CustomerDep, session: SessionDep
) -> CartOut:
    return CartOut.build(await CartService(session).set_quantity(user.id, item_id, body.quantity))


@router.delete("/cart/items/{item_id}", response_model=CartOut)
async def remove_cart_item(item_id: uuid.UUID, user: CustomerDep, session: SessionDep) -> CartOut:
    return CartOut.build(await CartService(session).remove_item(user.id, item_id))


@router.delete("/cart", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(user: CustomerDep, session: SessionDep) -> None:
    await CartService(session).clear(user.id)


@router.post("/cart/promo", response_model=CartOut)
async def apply_promo(body: PromoCodeIn, user: CustomerDep, session: SessionDep) -> CartOut:
    return CartOut.build(await CartService(session).apply_promo(user.id, body.code))


@router.delete("/cart/promo", response_model=CartOut)
async def remove_promo(user: CustomerDep, session: SessionDep) -> CartOut:
    return CartOut.build(await CartService(session).remove_promo(user.id))


# --- Checkout & orders -------------------------------------------------------------------


@router.post("/checkout/preview", response_model=CheckoutPreviewOut)
async def checkout_preview(
    body: CheckoutPreviewIn, user: CustomerDep, session: SessionDep
) -> CheckoutPreviewOut:
    preview = await OrderService(session).preview(
        user.id, district_id=body.district_id, delivery_method_id=body.delivery_method_id
    )
    return CheckoutPreviewOut.build(preview)


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: OrderCreateIn,
    user: CustomerDep,
    session: SessionDep,
    idempotency_key: IdempotencyKey,
) -> OrderOut:
    order = await OrderService(session).place_order(
        CheckoutRequest(user_id=user.id, idempotency_key=idempotency_key, **body.model_dump())
    )
    return OrderOut.build(order)


@router.get("/orders", response_model=Page[OrderSummaryOut])
async def list_orders(
    user: CustomerDep,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Page[OrderSummaryOut]:
    result = await OrderService(session).list_for_user(user.id, page=page, page_size=page_size)
    return Page.build(result, OrderSummaryOut.build)


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, user: CustomerDep, session: SessionDep) -> OrderOut:
    return OrderOut.build(await OrderService(session).get_for_user(order_id, user.id))


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: uuid.UUID, body: CancelIn, user: CustomerDep, session: SessionDep
) -> OrderOut:
    order = await OrderService(session).cancel(
        order_id, actor=Actor.customer(user.id), reason=body.reason or "Mijoz bekor qildi"
    )
    return OrderOut.build(order)


# --- Bot helpers ------------------------------------------------------------------------


@router.put(
    "/bot/product-images/{image_id}/telegram-file-id",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(bot_auth)],
)
async def save_telegram_file_id(
    image_id: uuid.UUID, body: TelegramFileIdIn, session: SessionDep
) -> None:
    """Remember Telegram's file id after the bot uploaded an image once."""
    image = await session.get(ProductImage, image_id)
    if image is None:
        raise NotFoundError("Rasm topilmadi.")
    image.telegram_file_id = body.telegram_file_id
    await session.commit()
