from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import texts as t
from app.bot import views
from app.bot.api_client import StoreApi
from app.bot.callbacks import OrderCb, uuid_from_hex
from app.bot.handlers.common import edit_or_send

router = Router(name="orders")

PAGE_SIZE = 5


async def _list(user_id: int, api: StoreApi, page: int) -> tuple[str, object]:
    data = await api.orders(user_id, page=page, page_size=PAGE_SIZE)
    if not data["items"]:
        return t.ORDERS_EMPTY, None
    labels = [views.order_button(o) for o in data["items"]]
    return t.ORDERS_TITLE.format(page=data["page"], pages=data["pages"]), kb.orders(data, labels)


@router.message(F.text == t.BTN_ORDERS)
async def my_orders(message: Message, api: StoreApi) -> None:
    assert message.from_user is not None
    text, markup = await _list(message.from_user.id, api, 1)
    await message.answer(text, reply_markup=markup)  # type: ignore[arg-type]


@router.callback_query(OrderCb.filter())
async def order_action(callback: CallbackQuery, callback_data: OrderCb, api: StoreApi) -> None:
    user_id = callback.from_user.id
    if callback_data.a == "list":
        text, markup = await _list(user_id, api, callback_data.p)
        await edit_or_send(callback, text, markup)  # type: ignore[arg-type]
    elif callback_data.a == "view":
        order = await api.order(user_id, uuid_from_hex(callback_data.id))
        await edit_or_send(
            callback, views.order_card(order), kb.order_detail(order, callback_data.p)
        )
    elif callback_data.a == "cancel":
        order = await api.order(user_id, uuid_from_hex(callback_data.id))
        await edit_or_send(
            callback,
            t.CONFIRM_CANCEL.format(number=order["number"]),
            kb.confirm_cancel(order["id"], callback_data.p),
        )
    elif callback_data.a == "cancel_yes":
        order = await api.cancel_order(user_id, uuid_from_hex(callback_data.id))
        await edit_or_send(
            callback, views.order_card(order), kb.order_detail(order, callback_data.p)
        )
        await callback.answer(t.ORDER_CANCELLED.format(number=order["number"]), show_alert=True)
        return
    await callback.answer()
