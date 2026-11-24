from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import texts as t
from app.bot import views
from app.bot.api_client import StoreApi
from app.bot.callbacks import CartCb, uuid_from_hex
from app.bot.handlers.checkout import start_checkout
from app.bot.handlers.common import edit_or_send, show_main_menu
from app.bot.states import CartInput

router = Router(name="cart")


def _markup(cart: dict) -> object:  # type: ignore[type-arg]
    return kb.cart(cart) if cart["lines"] else None


@router.message(F.text == t.BTN_CART)
async def show_cart(message: Message, api: StoreApi) -> None:
    assert message.from_user is not None
    cart = await api.cart(message.from_user.id)
    await message.answer(views.cart_text(cart), reply_markup=_markup(cart))  # type: ignore[arg-type]


@router.callback_query(CartCb.filter())
async def cart_action(
    callback: CallbackQuery, callback_data: CartCb, api: StoreApi, state: FSMContext
) -> None:
    user_id = callback.from_user.id
    action = callback_data.a
    if action == "checkout":
        await callback.answer()
        assert isinstance(callback.message, Message)
        await start_checkout(callback.message, user_id, api, state)
        return
    if action == "promo":
        await state.set_state(CartInput.promo)
        await callback.message.answer(t.ASK_PROMO, reply_markup=kb.cancel_only())  # type: ignore[union-attr]
        await callback.answer()
        return

    cart = await api.cart(user_id)
    if action in {"inc", "dec", "del"}:
        line = next(
            (ln for ln in cart["lines"] if ln["item_id"].replace("-", "") == callback_data.i), None
        )
        if line is None:
            await callback.answer(t.STALE_ACTION, show_alert=True)
        else:
            quantity = {"inc": line["quantity"] + 1, "dec": line["quantity"] - 1, "del": 0}[action]
            cart = await api.set_cart_quantity(user_id, uuid_from_hex(callback_data.i), quantity)
    elif action == "clear":
        await api.clear_cart(user_id)
        cart = await api.cart(user_id)
        await callback.answer(t.CART_CLEARED)
    elif action == "unpromo":
        cart = await api.remove_promo(user_id)
    if action == "view" and isinstance(callback.message, Message) and callback.message.photo:
        await callback.message.answer(views.cart_text(cart), reply_markup=_markup(cart))  # type: ignore[arg-type]
    else:
        await edit_or_send(callback, views.cart_text(cart), _markup(cart))  # type: ignore[arg-type]
    await callback.answer()


@router.message(CartInput.promo, F.text)
async def promo_code(message: Message, api: StoreApi, state: FSMContext) -> None:
    assert message.from_user is not None
    await state.set_state(None)
    cart = await api.apply_promo(message.from_user.id, (message.text or "").strip()[:32])
    await show_main_menu(message, t.PROMO_APPLIED)
    await message.answer(views.cart_text(cart), reply_markup=_markup(cart))  # type: ignore[arg-type]
