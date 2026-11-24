"""All customer-facing bot text (Uzbek, Latin) and message formatting.

Messages use Telegram HTML; every value that comes from data (names, addresses,
descriptions) goes through ``esc`` so it cannot break or inject markup.
"""

from __future__ import annotations

import html
from decimal import Decimal
from typing import Any

# --- Main menu buttons (reply keyboard) ------------------------------------------------
BTN_CATALOG = "🛍 Katalog"
BTN_CATEGORIES = "📂 Kategoriyalar"
BTN_SEARCH = "🔎 Qidiruv"
BTN_CART = "🛒 Savat"
BTN_ORDERS = "📦 Buyurtmalarim"
BTN_PROFILE = "👤 Profil"
BTN_SUPPORT = "☎️ Aloqa"
BTN_SHARE_PHONE = "📱 Telefon raqamni yuborish"
BTN_SKIP = "Keyinroq"
BTN_CANCEL = "❌ Bekor qilish"
BTN_BACK_TO_MENU = "🏠 Bosh menyu"

MENU_BUTTONS = (
    BTN_CATALOG, BTN_CATEGORIES, BTN_SEARCH, BTN_CART, BTN_ORDERS, BTN_PROFILE, BTN_SUPPORT,
)  # fmt: skip

# --- General ---------------------------------------------------------------------------
WELCOME = (
    "Assalomu alaykum, <b>{name}</b>! 👋\n\n"
    "<b>{store}</b> do‘koniga xush kelibsiz. Bu yerda mahsulotlarni ko‘rib chiqish, "
    "buyurtma berish va uning holatini kuzatish mumkin.\n\n"
    "Quyidagi menyudan foydalaning 👇"
)
ASK_PHONE = (
    "Buyurtmalar bo‘yicha siz bilan bog‘lanishimiz uchun telefon raqamingizni yuboring.\n"
    "Pastdagi «📱 Telefon raqamni yuborish» tugmasini bosing."
)
PHONE_SAVED = "✅ Telefon raqamingiz saqlandi: {phone}"
PHONE_SKIPPED = "Mayli. Raqamni buyurtma berishda kiritishingiz mumkin."
MAIN_MENU = "Bosh menyu 👇"
UNKNOWN_INPUT = "Tushunmadim 🙂 Iltimos, menyudagi tugmalardan foydalaning."
ERROR_GENERIC = "Kutilmagan xatolik yuz berdi. Iltimos, birozdan so‘ng qayta urinib ko‘ring."
STALE_ACTION = "Bu tugma eskirgan. Iltimos, qaytadan boshlang."
TOO_FAST = "Biroz sekinroq 🙂"
CANCELLED = "Bekor qilindi."

# --- Catalog ---------------------------------------------------------------------------
CATEGORIES_TITLE = "📂 <b>Kategoriyalar</b>\n\nKerakli bo‘limni tanlang:"
CATEGORIES_EMPTY = "Hozircha kategoriyalar yo‘q."
SUBCATEGORIES_TITLE = "📂 <b>{name}</b>\n\nBo‘limni tanlang:"
ALL_IN_CATEGORY = "📦 Barcha mahsulotlar"
PRODUCTS_TITLE = "🛍 <b>{title}</b>\nTopildi: {total} ta mahsulot · {page}/{pages}-sahifa"
PRODUCTS_FILTERS = "Filtrlar: {filters}"
PRODUCTS_EMPTY = "Hech narsa topilmadi. Filtrlarni o‘zgartirib ko‘ring."
CATALOG_ALL = "Barcha mahsulotlar"
SEARCH_RESULTS = "Qidiruv: «{query}»"
SORT_LABELS = {"newest": "🆕 Yangi", "price_asc": "⬆️ Arzon", "price_desc": "⬇️ Qimmat",
               "popular": "🔥 Ommabop"}  # fmt: skip
FILTER_IN_STOCK = "✅ Mavjud"
FILTER_DISCOUNTED = "🏷 Chegirma"
FILTER_PRICE = "💰 Narx"
FILTER_RESET = "♻️ Tozalash"
ASK_PRICE_RANGE = (
    "💰 Narx oralig‘ini yuboring, masalan:\n<code>100000-500000</code>\n\n"
    "Faqat eng kam narx uchun: <code>100000-</code>, faqat eng yuqori: <code>-500000</code>"
)
BAD_PRICE_RANGE = "Narx oralig‘ini tushunmadim. Namuna: <code>100000-500000</code>"
ASK_SEARCH = "🔎 Mahsulot nomi yoki artikulini (SKU) yozing:"
SEARCH_TOO_SHORT = "Kamida 2 ta belgi yozing."
PREV, NEXT = "◀️", "▶️"
BACK = "⬅️ Orqaga"

PRODUCT_CARD = "<b>{name}</b>{brand}\n\n{price}\n{stock}{variants}{description}"
IN_STOCK = "✅ Mavjud"
OUT_OF_STOCK = "❌ Hozircha mavjud emas"
CHOOSE_VARIANT = "\n\nVariantni tanlang 👇"
ADD_TO_CART = "🛒 Savatga qo‘shish"
ADDED_TO_CART = "✅ Savatga qo‘shildi. Savatda: {count} ta mahsulot."
GO_TO_CART = "🛒 Savatga o‘tish"
MORE_PHOTOS = "🖼 Barcha rasmlar"
SOLD_OUT_ALERT = "Afsuski, bu variant tugagan."

# --- Cart ------------------------------------------------------------------------------
CART_EMPTY = "🛒 Savatingiz bo‘sh.\n\nMahsulot qo‘shish uchun «🛍 Katalog» bo‘limiga o‘ting."
CART_TITLE = "🛒 <b>Savat</b>\n"
CART_LINE = "{n}. {name}\n    {qty} × {price} = <b>{total}</b>{warn}"
CART_LINE_WARN = "\n    ⚠️ {reason}"
CART_LINE_UNAVAILABLE = "sotuvda yo‘q"
CART_LINE_SHORT = "faqat {available} dona qoldi"
CART_SUBTOTAL = "Mahsulotlar: {amount}"
CART_DISCOUNT = "Chegirma ({code}): −{amount}"
CART_PROMO_PROBLEM = "Promokod {code}: {error}"
CART_TOTAL = "<b>Jami: {amount}</b>\n<i>Yetkazib berish narxi manzil tanlangach hisoblanadi.</i>"
CART_HAS_PROBLEMS = (
    "⚠️ Savatdagi ba’zi mahsulotlar sotuvda yo‘q. Ularni o‘chiring yoki miqdorini kamaytiring."
)
BTN_PROMO = "🎟 Promokod"
BTN_REMOVE_PROMO = "🎟 Promokodni olib tashlash"
BTN_CLEAR_CART = "🗑 Tozalash"
BTN_CHECKOUT = "✅ Rasmiylashtirish"
ASK_PROMO = "🎟 Promokodni yozing:"
PROMO_APPLIED = "✅ Promokod qo‘llandi."
CART_CLEARED = "Savat tozalandi."

# --- Checkout --------------------------------------------------------------------------
ASK_NAME = "👤 Qabul qiluvchining ism-familiyasini yozing:"
ASK_RECIPIENT_PHONE = (
    "📞 Qabul qiluvchining telefon raqami.\n"
    "Tugmani bosing yoki raqamni yozing (masalan, <code>+998 90 123 45 67</code>):"
)
BAD_PHONE = "Telefon raqami noto‘g‘ri. Namuna: <code>+998 90 123 45 67</code>"
BAD_NAME = "Ism-familiyani to‘g‘ri yozing (2–128 belgi)."
CHOOSE_SAVED_ADDRESS = "📍 Saqlangan manzilni tanlang yoki yangisini kiriting:"
NEW_ADDRESS = "➕ Yangi manzil"
CHOOSE_REGION = "📍 Viloyatni tanlang:"
CHOOSE_DISTRICT = "📍 <b>{region}</b>\nTuman yoki shaharni tanlang:"
CHOOSE_DELIVERY = "🚚 Yetkazib berish usulini tanlang:"
NO_DELIVERY = (
    "😔 Afsuski, bu hududga hozircha yetkazib berilmaydi.\n"
    "Boshqa manzilni tanlang yoki «☎️ Aloqa» orqali biz bilan bog‘laning."
)
DELIVERY_OPTION = "{name} — {price} ({eta})"
FREE = "bepul"
ETA_DAYS = "{min}–{max} kun"
ETA_DAY = "{n} kun"
ETA_TODAY = "shu kuni"
ASK_ADDRESS = "🏠 Manzilni yozing (ko‘cha, uy, xonadon):"
BAD_ADDRESS = "Manzilni to‘liqroq yozing (kamida 5 belgi)."
ASK_LANDMARK = "🧭 Mo‘ljal yoki kuryer uchun izoh (masalan, «Makro yonida, 3-qavat»).\nYo‘q bo‘lsa, «O‘tkazib yuborish» ni bosing."
BTN_SKIP_STEP = "⏭ O‘tkazib yuborish"
CHOOSE_PAYMENT = "💳 To‘lov usulini tanlang:"
NO_PAYMENT_METHODS = "To‘lov usullari hozircha mavjud emas. Iltimos, keyinroq urinib ko‘ring."
PAYMENT_LABELS = {"click": "Click", "payme": "Payme", "cash_on_delivery": "💵 Naqd (kuryerga)"}
SUMMARY_TITLE = "🧾 <b>Buyurtmani tekshiring</b>\n"
SUMMARY_RECIPIENT = "👤 {name}, {phone}"
SUMMARY_ADDRESS = "📍 {region}, {district}\n🏠 {address}{landmark}"
SUMMARY_DELIVERY = "🚚 {method} — {price} ({eta})"
SUMMARY_PAYMENT = "💳 {payment}"
SUMMARY_TOTALS = (
    "Mahsulotlar: {subtotal}{discount}\nYetkazib berish: {delivery}\n<b>Jami: {total}</b>"
)
BTN_CONFIRM = "✅ Tasdiqlash"
BTN_RESTART = "✏️ O‘zgartirish"
ORDER_PLACED = "🎉 <b>Buyurtmangiz qabul qilindi!</b>\n\n"
PAY_PROMPT = (
    "💳 To‘lov uchun quyidagi tugmani bosing ({payment}). Mahsulotlar siz uchun "
    "{minutes} daqiqa band qilib turiladi. To‘lov tasdiqlangach, holat «📦 Buyurtmalarim» "
    "bo‘limida yangilanadi."
)
PAY_SIMULATED = "⚠️ Sinov rejimi: bu haqiqiy to‘lov emas, pul yechilmaydi."
BTN_PAY = "💳 To‘lash"
BTN_PAY_SIMULATED = "💳 To‘lash (SINOV)"
PAYMENT_UNAVAILABLE = (
    "💳 Onlayn to‘lov hozircha ishlamayapti: {reason}\nBuyurtmangiz {minutes} daqiqa saqlanadi."
)
CASH_PAYMENT_NOTE = "💵 To‘lovni buyurtmani olganingizda kuryerga qilasiz. Tez orada operatorimiz siz bilan bog‘lanadi."
CHECKOUT_EXPIRED = "Rasmiylashtirish sessiyasi eskirgan. Iltimos, savatdan qaytadan boshlang."

# --- Orders ----------------------------------------------------------------------------
ORDERS_EMPTY = "📦 Sizda hali buyurtmalar yo‘q."
ORDERS_TITLE = "📦 <b>Buyurtmalarim</b> · {page}/{pages}-sahifa"
ORDER_BUTTON = "{number} · {status} · {total}"
ORDER_CARD = (
    "📦 <b>Buyurtma {number}</b>\n"
    "🗓 {date}\n\n"
    "Holati: <b>{status}</b>\n"
    "To‘lov: {payment_status} ({payment_method})\n"
    "Yetkazib berish: {delivery_status}\n\n"
    "{items}\n\n"
    "Mahsulotlar: {subtotal}{discount}\n"
    "Yetkazib berish: {delivery_fee}\n"
    "<b>Jami: {total}</b>\n\n"
    "👤 {recipient}, {phone}\n"
    "📍 {region}, {district}, {address}\n"
    "🚚 {method}{eta}"
)
ORDER_ITEM = "• {name} — {qty} × {price}"
BTN_CANCEL_ORDER = "❌ Buyurtmani bekor qilish"
CONFIRM_CANCEL = "Buyurtma {number} ni rostdan ham bekor qilmoqchimisiz?"
BTN_YES_CANCEL = "Ha, bekor qilish"
BTN_NO = "Yo‘q"
ORDER_CANCELLED = "Buyurtma {number} bekor qilindi."
BTN_ORDERS_LIST = "📦 Barcha buyurtmalar"

# --- Profile & support -----------------------------------------------------------------
PROFILE = (
    "👤 <b>Profil</b>\n\n"
    "Ism: {name}\n"
    "Telefon: {phone}\n"
    "Telegram: {username}\n"
    "Ro‘yxatdan o‘tgan: {date}"
)
PHONE_VERIFIED = " ✅"
NOT_SET = "kiritilmagan"
BTN_UPDATE_PHONE = "📱 Telefonni yangilash"
BTN_ADDRESSES = "📍 Manzillarim"
ADDRESSES_TITLE = "📍 <b>Saqlangan manzillar</b>"
ADDRESSES_EMPTY = "Saqlangan manzillar yo‘q. Ular buyurtma berganingizda avtomatik saqlanadi."
ADDRESS_LINE = "{n}. {address} ({recipient}, {phone}){default}"
ADDRESS_DEFAULT = " ⭐"
ADDRESS_DELETED = "Manzil o‘chirildi."
SUPPORT = "☎️ <b>{store}</b>\n\n{lines}"
SUPPORT_PHONE = "📞 Telefon: {phone}"
SUPPORT_TELEGRAM = "💬 Telegram: @{username}"
SUPPORT_ADDRESS = "📍 Manzil: {address}"
SUPPORT_NONE = "Aloqa ma’lumotlari tez orada qo‘shiladi."


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def som(amount: str | Decimal | int) -> str:
    """``"1250000.00"`` → ``"1 250 000 so‘m"``."""
    value = int(Decimal(str(amount)).quantize(Decimal(1)))
    return f"{value:,}".replace(",", " ") + " so‘m"


def price_line(price: str, discount_price: str | None = None) -> str:
    if discount_price is not None:
        return f"💰 <b>{som(discount_price)}</b>  <s>{som(price)}</s>"
    return f"💰 <b>{som(price)}</b>"


def eta(min_days: int | None, max_days: int | None) -> str:
    if min_days is None or max_days is None:
        return ""
    if max_days == 0:
        return ETA_TODAY
    if min_days == max_days:
        return ETA_DAY.format(n=max_days)
    return ETA_DAYS.format(min=min_days, max=max_days)


def variant_label(variant: dict[str, Any]) -> str:
    if variant.get("name"):
        return str(variant["name"])
    attrs = variant.get("attributes") or {}
    return " / ".join(str(v) for v in attrs.values()) or str(variant.get("sku", ""))


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
