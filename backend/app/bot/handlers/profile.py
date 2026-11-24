from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import texts as t
from app.bot import views
from app.bot.api_client import StoreApi
from app.bot.callbacks import ProfileCb, uuid_from_hex
from app.bot.handlers.common import edit_or_send
from app.bot.states import Registration

router = Router(name="profile")


def _addresses_text(items: list[dict]) -> str:  # type: ignore[type-arg]
    if not items:
        return t.ADDRESSES_EMPTY
    lines = [t.ADDRESSES_TITLE, ""]
    for n, a in enumerate(items, start=1):
        lines.append(
            t.ADDRESS_LINE.format(
                n=n,
                address=t.esc(a["address_line"]),
                recipient=t.esc(a["recipient_name"]),
                phone=t.esc(a["recipient_phone"]),
                default=t.ADDRESS_DEFAULT if a["is_default"] else "",
            )
        )
    return "\n".join(lines)


@router.message(F.text == t.BTN_PROFILE)
async def profile(message: Message, api: StoreApi) -> None:
    assert message.from_user is not None
    data = await api.profile(message.from_user.id)
    await message.answer(views.profile_text(data), reply_markup=kb.profile())


@router.callback_query(ProfileCb.filter())
async def profile_action(
    callback: CallbackQuery, callback_data: ProfileCb, api: StoreApi, state: FSMContext
) -> None:
    user_id = callback.from_user.id
    if callback_data.a == "phone":
        await state.set_state(Registration.phone)
        await callback.message.answer(t.ASK_PHONE, reply_markup=kb.share_phone(allow_skip=True))  # type: ignore[union-attr]
    elif callback_data.a == "addresses":
        items = await api.addresses(user_id)
        await edit_or_send(callback, _addresses_text(items), kb.addresses(items) if items else None)
    elif callback_data.a == "deladdr":
        await api.delete_address(user_id, uuid_from_hex(callback_data.id))
        items = await api.addresses(user_id)
        await edit_or_send(callback, _addresses_text(items), kb.addresses(items) if items else None)
        await callback.answer(t.ADDRESS_DELETED)
        return
    await callback.answer()
