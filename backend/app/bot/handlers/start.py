"""/start, phone registration, support, cancel, and the fallback handler."""

from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot import keyboards as kb
from app.bot import texts as t
from app.bot import views
from app.bot.api_client import StoreApi
from app.bot.handlers.common import show_main_menu
from app.bot.states import Registration

router = Router(name="start")
fallback_router = Router(name="fallback")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, api: StoreApi) -> None:
    await state.clear()
    user = message.from_user
    assert user is not None
    store = await api.store()
    profile = await api.profile(user.id)
    await message.answer(
        t.WELCOME.format(name=t.esc(user.first_name), store=t.esc(store["name"])),
        reply_markup=kb.main_menu(),
    )
    if not profile.get("phone"):
        await state.set_state(Registration.phone)
        await message.answer(t.ASK_PHONE, reply_markup=kb.share_phone(allow_skip=True))


@router.message(Registration.phone, F.contact)
async def phone_contact(message: Message, state: FSMContext, api: StoreApi) -> None:
    assert message.from_user is not None
    assert message.contact is not None
    profile = await api.set_phone(
        message.from_user.id, message.contact.phone_number, message.contact.user_id
    )
    await state.clear()
    await show_main_menu(message, t.PHONE_SAVED.format(phone=t.esc(profile["phone"])))


@router.message(Registration.phone, F.text == t.BTN_SKIP)
async def phone_skip(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_main_menu(message, t.PHONE_SKIPPED)


@router.message(Registration.phone)
async def phone_other(message: Message) -> None:
    # Typed numbers are not accepted here: only Telegram's contact sharing proves ownership.
    await message.answer(t.ASK_PHONE, reply_markup=kb.share_phone(allow_skip=True))


@router.message(F.text == t.BTN_CANCEL)
@router.message(Command("cancel", "menu"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_main_menu(message)


@router.message(F.text == t.BTN_SUPPORT)
@router.message(Command("help"))
async def support(message: Message, api: StoreApi) -> None:
    await message.answer(views.support_text(await api.store()))


@fallback_router.message(StateFilter(None))
async def unknown(message: Message, **_: Any) -> None:
    await show_main_menu(message, t.UNKNOWN_INPUT)
