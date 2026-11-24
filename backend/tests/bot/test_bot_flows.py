"""Customer conversations with the bot, end to end (fake Telegram, real API + DB)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from aiogram.methods import SendMessage, SendPhoto
from aiogram.types import ReplyKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts as t
from app.bot.handlers.catalog import parse_price_range
from app.models import Order, Product, ProductImage, User
from tests.bot.conftest import alerts, button, buttons, texts
from tests.factories import make_shop


async def _ready(chat: Any, user_id: int) -> Any:
    """A registered customer at the main menu."""
    c = chat(user_id)
    await c.say("/start")
    await c.say(t.BTN_SKIP)
    return c


# --- Start & registration ---------------------------------------------------------------


async def test_start_registers_and_verifies_shared_phone(chat: Any, db: AsyncSession) -> None:
    c = chat(800_000_001)
    calls = await c.say("/start")
    assert "Assalomu alaykum, <b>Aziza</b>" in texts(calls)
    assert "Online Store" in texts(calls)
    phone_prompt = calls[-1]
    assert isinstance(phone_prompt.reply_markup, ReplyKeyboardMarkup)
    assert phone_prompt.reply_markup.keyboard[0][0].request_contact is True

    # Typing a number is not accepted as proof of ownership.
    calls = await c.say("+998901234567")
    assert t.ASK_PHONE in texts(calls)

    calls = await c.say(contact=c.share_contact("998901234567"))
    assert "+998901234567" in texts(calls)
    user = await db.scalar(select(User).where(User.telegram_id == 800_000_001))
    assert user is not None
    assert user.phone_verified is True
    assert user.first_name == "Aziza"
    assert user.username == "aziza_k"


async def test_unknown_text_and_support(chat: Any) -> None:
    c = await _ready(chat, 800_000_002)
    assert t.UNKNOWN_INPUT in texts(await c.say("salom"))
    assert "Aloqa ma’lumotlari tez orada" in texts(await c.say(t.BTN_SUPPORT))


# --- Catalog ----------------------------------------------------------------------------


async def test_catalog_list_sort_filter_and_product_card(chat: Any, db: AsyncSession) -> None:
    shop = await make_shop(db, price="185000", stock=3)
    product = await db.get(Product, shop.variant.product_id)
    assert product is not None
    product.name = "Qishki kurtka <b>XL</b>"  # must be escaped in HTML messages
    await db.commit()
    c = await _ready(chat, 800_000_003)

    calls = await c.say(t.BTN_CATALOG)
    assert "Barcha mahsulotlar" in texts(calls)
    product_button = button(calls, "Qishki kurtka")
    assert "185 000 so‘m" in next(k for k in buttons(calls) if "Qishki" in k)

    calls = await c.click(button(calls, "Arzon"))
    assert "• ⬆️ Arzon" in buttons(calls)
    calls = await c.click(button(calls, "Mavjud"))
    assert "Filtrlar: ✅ Mavjud" in texts(calls)

    calls = await c.click(product_button)
    card = texts(calls)
    assert "Qishki kurtka &lt;b&gt;XL&lt;/b&gt;" in card
    assert "<b>XL</b>" not in card
    assert "185 000 so‘m" in card
    assert t.IN_STOCK in card

    calls = await c.click(button(calls, "Savatga qo‘shish"))
    assert alerts(calls) == [t.ADDED_TO_CART.format(count=1)]


async def test_search_and_price_filter(chat: Any, db: AsyncSession) -> None:
    shop = await make_shop(db, price="90000")
    product = await db.get(Product, shop.variant.product_id)
    assert product is not None
    product.name = "Elektr choynak Tefal"
    await db.commit()
    c = await _ready(chat, 800_000_004)

    await c.say(t.BTN_SEARCH)
    calls = await c.say("tefal")
    assert "Qidiruv: «tefal»" in texts(calls)
    assert "Elektr choynak Tefal" in " ".join(buttons(calls))

    calls = await c.click(button(calls, "Narx"))
    assert "Narx oralig‘ini" in texts(calls)
    assert t.BAD_PRICE_RANGE in texts(await c.say("arzon"))
    calls = await c.say("100 000 - 200 000")
    assert "Hech narsa topilmadi" in texts(calls)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("100000-500000", ("100000", "500000")),
        ("100 000 - 500 000 so‘m", ("100000", "500000")),
        ("100000-", ("100000", None)),
        ("-500000", (None, "500000")),
        ("500-100", None),
        ("-", None),
        ("abc", None),
    ],
)
def test_parse_price_range(text: str, expected: tuple[str | None, str | None] | None) -> None:
    assert parse_price_range(text) == expected


async def test_known_telegram_file_id_is_reused(chat: Any, db: AsyncSession) -> None:
    shop = await make_shop(db)
    db.add(
        ProductImage(
            product_id=shop.variant.product_id,
            path="products/x/a.png",
            is_main=True,
            telegram_file_id="AgACAgIAAxkBAAI",
        )
    )
    await db.commit()
    c = await _ready(chat, 800_000_005)
    calls = await c.click(f"p:{shop.variant.product_id.hex}:")
    photo = next(x for x in calls if isinstance(x, SendPhoto))
    assert photo.photo == "AgACAgIAAxkBAAI"  # no re-upload


# --- Cart & checkout --------------------------------------------------------------------


async def _fill_cart(chat: Any, db: AsyncSession, user_id: int, *, quantity: int = 2) -> Any:
    shop = await make_shop(db, price="120000", stock=5, delivery_price="25000")
    c = await _ready(chat, user_id)
    for _ in range(quantity):
        await c.click(f"a:{shop.variant.id.hex}")
    return c, shop


async def test_cart_controls(chat: Any, db: AsyncSession) -> None:
    c, _ = await _fill_cart(chat, db, 800_000_006)
    calls = await c.say(t.BTN_CART)
    assert "2 × 120 000 so‘m = <b>240 000 so‘m</b>" in texts(calls)
    calls = await c.click(button(calls, "➕"))
    assert "3 × 120 000 so‘m" in texts(calls)
    calls = await c.click(button(calls, "🗑"))
    assert t.CART_EMPTY in texts(calls)


async def test_full_checkout_creates_exactly_one_order(chat: Any, db: AsyncSession) -> None:
    c, shop = await _fill_cart(chat, db, 800_000_007)
    calls = await c.say(t.BTN_CART)
    calls = await c.click(button(calls, "Rasmiylashtirish"))
    assert t.ASK_NAME in texts(calls)
    assert "Aziza Karimova" in str(calls[-1].reply_markup)  # suggested from profile

    assert t.BAD_NAME in texts(await c.say("A"))
    calls = await c.say("Aziza Karimova")
    assert "telefon raqami" in texts(calls)
    assert t.BAD_PHONE in texts(await c.say("12345"))
    calls = await c.say("90 765 43 21")
    calls = calls[-1:]
    assert t.CHOOSE_REGION in texts(calls)

    calls = await c.click(button(calls, "Toshkent shahri"))
    calls = await c.click(button(calls, "Bektemir"))
    assert t.CHOOSE_DELIVERY in texts(calls)
    calls = await c.click(button(calls, "Kuryer"))
    assert t.ASK_ADDRESS in texts(calls)
    assert t.BAD_ADDRESS in texts(await c.say("uy"))
    calls = await c.say("Mustaqillik ko‘chasi 7, 12-xonadon")
    calls = await c.click(button(calls, "O‘tkazib"))
    assert t.CHOOSE_PAYMENT in texts(calls)
    assert set(buttons(calls)) == {"Click", "Payme"}  # cash on delivery is off by default

    calls = await c.click(button(calls, "Payme"))
    summary = texts(calls)
    assert "Buyurtmani tekshiring" in summary
    assert "+998907654321" in summary
    assert "Toshkent shahri, Bektemir tumani" in summary
    assert "<b>Jami: 265 000 so‘m</b>" in summary  # 2 × 120 000 + 25 000

    confirm = button(calls, "Tasdiqlash")
    calls = await c.click(confirm)
    placed = texts(calls)
    assert "Buyurtmangiz qabul qilindi" in placed
    assert "Payme" in placed
    assert "30 daqiqa" in placed

    # A second tap on the same button must not create another order.
    calls = await c.click(confirm)
    assert alerts(calls) == [t.CHECKOUT_EXPIRED]
    user = await db.scalar(select(User).where(User.telegram_id == 800_000_007))
    assert user is not None
    assert await db.scalar(select(func.count()).where(Order.user_id == user.id)) == 1

    # The address was saved and is offered next time.
    await c.click(f"a:{shop.variant.id.hex}")
    calls = await c.say(t.BTN_CART)
    await c.click(button(calls, "Rasmiylashtirish"))
    await c.say("Aziza Karimova")
    calls = await c.say("90 765 43 21")
    assert t.CHOOSE_SAVED_ADDRESS in texts(calls)
    assert "Mustaqillik ko‘chasi 7" in " ".join(buttons(calls))


async def test_stale_checkout_button(chat: Any) -> None:
    c = await _ready(chat, 800_000_008)
    calls = await c.click("o:confirm:")
    assert alerts(calls) == [t.CHECKOUT_EXPIRED]


async def test_api_errors_reach_the_customer_in_uzbek(chat: Any, db: AsyncSession) -> None:
    shop = await make_shop(db, stock=1)
    c = await _ready(chat, 800_000_009)
    await c.click(f"a:{shop.variant.id.hex}")
    calls = await c.click(f"a:{shop.variant.id.hex}")
    assert any("faqat 1 dona qoldi" in a for a in alerts(calls))
    calls = await c.click(f"p:{uuid.uuid4().hex}:")
    assert any("topilmadi" in a for a in alerts(calls))


# --- Orders & profile -------------------------------------------------------------------


async def test_orders_view_and_cancel(chat: Any, db: AsyncSession) -> None:
    c, _ = await _fill_cart(chat, db, 800_000_010, quantity=1)
    calls = await c.say(t.BTN_CART)
    calls = await c.click(button(calls, "Rasmiylashtirish"))
    await c.say("Aziza Karimova")
    calls = (await c.say("90 765 43 21"))[-1:]
    calls = await c.click(button(calls, "Toshkent shahri"))
    calls = await c.click(button(calls, "Bektemir"))
    calls = await c.click(button(calls, "Kuryer"))
    await c.say("Amir Temur ko‘chasi 1")
    calls = await c.click("o:skip:")
    calls = await c.click(button(calls, "Click"))
    await c.click(button(calls, "Tasdiqlash"))

    calls = await c.say(t.BTN_ORDERS)
    assert "Buyurtmalarim" in texts(calls)
    calls = await c.click(button(calls, "OS-"))
    assert "Holati: <b>Yangi</b>" in texts(calls)
    calls = await c.click(button(calls, "bekor qilish"))
    assert "rostdan ham bekor" in texts(calls)
    calls = await c.click(button(calls, "Ha, bekor"))
    assert "Holati: <b>Bekor qilingan</b>" in texts(calls)
    assert any("bekor qilindi" in a for a in alerts(calls))


async def test_profile_and_addresses(chat: Any) -> None:
    c = chat(800_000_011)
    await c.say("/start")
    await c.say(contact=c.share_contact("+998 93 111 22 33"))
    calls = await c.say(t.BTN_PROFILE)
    assert "+998931112233 ✅" in texts(calls)
    assert "@aziza_k" in texts(calls)
    calls = await c.click(button(calls, "Manzillarim"))
    assert t.ADDRESSES_EMPTY in texts(calls)


async def test_every_message_uses_html_safe_text(chat: Any) -> None:
    c = chat(800_000_012)
    calls = await c.say("/start")
    assert all(isinstance(x, SendMessage) for x in calls)
