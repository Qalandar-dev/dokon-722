"""Checkout dialogue (FSM). Every price shown comes from the API's checkout preview;
the order is created with one idempotency key per summary, so repeated taps on
"Tasdiqlash" can never create two orders."""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import texts as t
from app.bot import views
from app.bot.api_client import ApiError, StoreApi
from app.bot.callbacks import CheckoutCb
from app.bot.handlers.common import edit_or_send, show_main_menu
from app.bot.states import Checkout
from app.core.exceptions import BusinessRuleError
from app.core.phone import normalize_uz_phone

router = Router(name="checkout")

KEY = "checkout"


async def _data(state: FSMContext) -> dict[str, Any]:
    return dict((await state.get_data()).get(KEY) or {})


async def _save(state: FSMContext, **values: Any) -> dict[str, Any]:
    data = await _data(state)
    data.update(values)
    await state.update_data({KEY: data})
    return data


async def start_checkout(message: Message, user_id: int, api: StoreApi, state: FSMContext) -> None:
    cart = await api.cart(user_id)
    if not cart["lines"]:
        await message.answer(t.CART_EMPTY)
        return
    if cart["has_problems"]:
        await message.answer(t.CART_HAS_PROBLEMS)
        return
    profile = await api.profile(user_id)
    name = " ".join(x for x in (profile["first_name"], profile.get("last_name")) if x)
    await state.set_state(Checkout.name)
    await state.update_data(
        {KEY: {"profile_phone": profile.get("phone"), "cart_total": cart["total"]}}
    )
    await message.answer(t.ASK_NAME, reply_markup=kb.text_choices(name))


@router.message(Checkout.name, F.text)
async def step_name(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split())
    if not 2 <= len(name) <= 128:
        await message.answer(t.BAD_NAME)
        return
    data = await _save(state, recipient_name=name)
    await state.set_state(Checkout.phone)
    await message.answer(
        t.ASK_RECIPIENT_PHONE,
        reply_markup=kb.share_phone(allow_skip=False, saved_phone=data.get("profile_phone")),
    )


@router.message(Checkout.phone, F.contact | F.text)
async def step_phone(message: Message, state: FSMContext, api: StoreApi) -> None:
    assert message.from_user is not None
    raw = message.contact.phone_number if message.contact else (message.text or "")
    try:
        phone = normalize_uz_phone(raw)
    except BusinessRuleError:
        await message.answer(t.BAD_PHONE)
        return
    if message.contact and message.contact.user_id == message.from_user.id:
        with contextlib.suppress(ApiError):  # keep the verified number on the profile too
            await api.set_phone(message.from_user.id, phone, message.contact.user_id)
    await _save(state, recipient_phone=phone)
    await show_main_menu(message, "✅")
    addresses = await api.addresses(message.from_user.id)
    if addresses:
        await state.set_state(Checkout.address_choice)
        await message.answer(t.CHOOSE_SAVED_ADDRESS, reply_markup=kb.saved_addresses(addresses))
    else:
        await _ask_region(message, api, state)


async def _ask_region(
    message: Message, api: StoreApi, state: FSMContext, callback: CallbackQuery | None = None
) -> None:
    await state.set_state(Checkout.region)
    markup = kb.regions(await api.regions())
    if callback is not None:
        await edit_or_send(callback, t.CHOOSE_REGION, markup)
    else:
        await message.answer(t.CHOOSE_REGION, reply_markup=markup)


@router.callback_query(Checkout.address_choice, CheckoutCb.filter(F.a == "addr"))
async def step_saved_address(
    callback: CallbackQuery, callback_data: CheckoutCb, state: FSMContext, api: StoreApi
) -> None:
    addresses = await api.addresses(callback.from_user.id)
    chosen = next((a for a in addresses if a["id"].replace("-", "") == callback_data.v), None)
    if chosen is None:
        await callback.answer(t.STALE_ACTION, show_alert=True)
        return
    await _save(
        state,
        district_id=chosen["district_id"],
        address_line=chosen["address_line"],
        landmark=chosen.get("landmark"),
        saved_address=True,
    )
    await _ask_delivery(callback, state, api)


@router.callback_query(
    StateFilter(Checkout.address_choice, Checkout.district, Checkout.method),
    CheckoutCb.filter(F.a == "newaddr"),
)
async def step_new_address(callback: CallbackQuery, state: FSMContext, api: StoreApi) -> None:
    await _save(state, saved_address=False, address_line=None, landmark=None)
    assert isinstance(callback.message, Message)
    await _ask_region(callback.message, api, state, callback)
    await callback.answer()


@router.callback_query(Checkout.region, CheckoutCb.filter(F.a == "region"))
async def step_region(
    callback: CallbackQuery, callback_data: CheckoutCb, state: FSMContext, api: StoreApi
) -> None:
    region_id = int(callback_data.v)
    regions = {r["id"]: r for r in await api.regions()}
    districts = await api.districts(region_id)
    await state.set_state(Checkout.district)
    await edit_or_send(
        callback,
        t.CHOOSE_DISTRICT.format(region=t.esc(regions.get(region_id, {}).get("name", ""))),
        kb.districts(districts),
    )
    await callback.answer()


@router.callback_query(Checkout.district, CheckoutCb.filter(F.a == "district"))
async def step_district(
    callback: CallbackQuery, callback_data: CheckoutCb, state: FSMContext, api: StoreApi
) -> None:
    await _save(state, district_id=int(callback_data.v))
    await _ask_delivery(callback, state, api)


async def _ask_delivery(callback: CallbackQuery, state: FSMContext, api: StoreApi) -> None:
    data = await _data(state)
    cart = await api.cart(callback.from_user.id)
    quotes = await api.delivery_quotes(data["district_id"], cart["total"])
    await _save(state, quotes={q["method_id"].replace("-", ""): q for q in quotes})
    await state.set_state(Checkout.method)
    if not quotes:
        await state.set_state(Checkout.region)
        await edit_or_send(callback, t.NO_DELIVERY, kb.regions(await api.regions()))
    else:
        await edit_or_send(callback, t.CHOOSE_DELIVERY, kb.delivery_methods(quotes))
    await callback.answer()


@router.callback_query(Checkout.method, CheckoutCb.filter(F.a == "method"))
async def step_method(
    callback: CallbackQuery, callback_data: CheckoutCb, state: FSMContext, api: StoreApi
) -> None:
    data = await _data(state)
    quote = data.get("quotes", {}).get(callback_data.v)
    if quote is None:
        await callback.answer(t.STALE_ACTION, show_alert=True)
        return
    data = await _save(state, method_id=quote["method_id"])
    assert isinstance(callback.message, Message)
    if quote["method_kind"] == "pickup":
        await _save(
            state,
            address_line=quote.get("pickup_address") or quote["method_name"],
            landmark=None,
            saved_address=True,
        )
        await _ask_payment(callback.message, state, api, callback)
    elif data.get("address_line"):
        await _ask_payment(callback.message, state, api, callback)
    else:
        await state.set_state(Checkout.address)
        await edit_or_send(callback, t.ASK_ADDRESS)
    await callback.answer()


@router.message(Checkout.address, F.text)
async def step_address(message: Message, state: FSMContext) -> None:
    address = " ".join((message.text or "").split())
    if len(address) < 5:
        await message.answer(t.BAD_ADDRESS)
        return
    await _save(state, address_line=address[:255])
    await state.set_state(Checkout.landmark)
    await message.answer(t.ASK_LANDMARK, reply_markup=kb.skip_step())


@router.message(Checkout.landmark, F.text)
async def step_landmark(message: Message, state: FSMContext, api: StoreApi) -> None:
    await _save(state, landmark=" ".join((message.text or "").split())[:255] or None)
    await _ask_payment(message, state, api)


@router.callback_query(Checkout.landmark, CheckoutCb.filter(F.a == "skip"))
async def step_landmark_skip(callback: CallbackQuery, state: FSMContext, api: StoreApi) -> None:
    await _save(state, landmark=None)
    assert isinstance(callback.message, Message)
    await _ask_payment(callback.message, state, api, callback)
    await callback.answer()


async def _ask_payment(
    message: Message, state: FSMContext, api: StoreApi, callback: CallbackQuery | None = None
) -> None:
    methods = (await api.store())["payment_methods"]
    if not methods:
        await state.clear()
        await message.answer(t.NO_PAYMENT_METHODS, reply_markup=kb.main_menu())
        return
    await state.set_state(Checkout.payment)
    if callback is not None:
        await edit_or_send(callback, t.CHOOSE_PAYMENT, kb.payment_methods(methods))
    else:
        await message.answer(t.CHOOSE_PAYMENT, reply_markup=kb.payment_methods(methods))


@router.callback_query(Checkout.payment, CheckoutCb.filter(F.a == "pay"))
async def step_payment(
    callback: CallbackQuery, callback_data: CheckoutCb, state: FSMContext, api: StoreApi
) -> None:
    data = await _save(state, payment_method=callback_data.v)
    preview = await api.checkout_preview(
        callback.from_user.id, data["district_id"], data["method_id"]
    )
    # One key per summary shown: retries and double taps reuse it.
    await _save(state, idempotency_key=uuid.uuid4().hex)
    await state.set_state(Checkout.confirm)
    await edit_or_send(callback, views.checkout_summary(data, preview), kb.confirm_order())
    await callback.answer()


@router.callback_query(Checkout.confirm, CheckoutCb.filter(F.a == "confirm"))
async def step_confirm(callback: CallbackQuery, state: FSMContext, api: StoreApi) -> None:
    data = await _data(state)
    user_id = callback.from_user.id
    order = await api.create_order(
        user_id,
        {
            "recipient_name": data["recipient_name"],
            "recipient_phone": data["recipient_phone"],
            "district_id": data["district_id"],
            "address_line": data["address_line"],
            "landmark": data.get("landmark"),
            "delivery_method_id": data["method_id"],
            "payment_method": data["payment_method"],
        },
        idempotency_key=data["idempotency_key"],
    )
    await state.clear()
    if not data.get("saved_address"):
        with contextlib.suppress(ApiError):  # convenience only; never blocks the order
            await api.add_address(
                user_id,
                {
                    "district_id": data["district_id"],
                    "recipient_name": data["recipient_name"],
                    "recipient_phone": data["recipient_phone"],
                    "address_line": data["address_line"],
                    "landmark": data.get("landmark"),
                },
            )
    if order["payment_method"] == "cash_on_delivery":
        note = t.CASH_PAYMENT_NOTE
    else:
        store = await api.store()
        note = t.ONLINE_PAYMENT_PENDING.format(
            payment=t.PAYMENT_LABELS.get(order["payment_method"], order["payment_method"]),
            minutes=store["reservation_minutes"],
        )
    await edit_or_send(callback, t.ORDER_PLACED + views.order_card(order) + "\n\n" + note)
    await callback.answer()


@router.callback_query(Checkout.confirm, CheckoutCb.filter(F.a == "restart"))
async def step_restart(callback: CallbackQuery, state: FSMContext, api: StoreApi) -> None:
    await callback.answer()
    assert isinstance(callback.message, Message)
    await start_checkout(callback.message, callback.from_user.id, api, state)


@router.callback_query(CheckoutCb.filter(F.a == "cancel"))
async def step_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(callback, t.CANCELLED)
    assert isinstance(callback.message, Message)
    await show_main_menu(callback.message)
    await callback.answer()


@router.callback_query(CheckoutCb.filter())
async def stale(callback: CallbackQuery) -> None:
    """A checkout button from an old or finished dialogue."""
    await callback.answer(t.CHECKOUT_EXPIRED, show_alert=True)
