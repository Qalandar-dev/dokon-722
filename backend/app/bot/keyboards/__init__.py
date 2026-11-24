"""Keyboard builders. Pure functions: data in, markup out."""

from __future__ import annotations

from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot import texts as t
from app.bot.callbacks import (
    AddCb,
    CartCb,
    CategoryCb,
    CheckoutCb,
    ListCb,
    OrderCb,
    PhotosCb,
    ProductCb,
    ProfileCb,
    hexid,
)


def main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [t.BTN_CATALOG, t.BTN_CATEGORIES],
        [t.BTN_SEARCH, t.BTN_CART],
        [t.BTN_ORDERS, t.BTN_PROFILE],
        [t.BTN_SUPPORT],
    ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=x) for x in row] for row in rows], resize_keyboard=True
    )


def share_phone(*, allow_skip: bool, saved_phone: str | None = None) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=t.BTN_SHARE_PHONE, request_contact=True)]]
    if saved_phone:
        rows.append([KeyboardButton(text=saved_phone)])
    rows.append([KeyboardButton(text=t.BTN_SKIP if allow_skip else t.BTN_CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def text_choices(*options: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=o)] for o in options if o]
        + [[KeyboardButton(text=t.BTN_CANCEL)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def cancel_only() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t.BTN_CANCEL)]], resize_keyboard=True)


# --- Catalog ---------------------------------------------------------------------------


def categories(
    nodes: list[dict[str, Any]], *, parent: dict[str, Any] | None
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if parent is not None:
        kb.button(text=t.ALL_IN_CATEGORY, callback_data=ListCb(a="cat", v=hexid(parent["id"])))
    for node in nodes:
        kb.button(text=node["name"], callback_data=CategoryCb(id=hexid(node["id"])))
    if parent is not None:
        kb.button(text=t.BACK, callback_data=CategoryCb(id=""))
    kb.adjust(*([1] if parent else []), *([2] * ((len(nodes) + 1) // 2)), 1)
    return kb.as_markup()


def product_list(page: dict[str, Any], state: dict[str, Any]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in page["items"]:
        mark = "" if item["in_stock"] else "❌ "
        sale = "🏷 " if item["has_discount"] else ""
        kb.row(
            InlineKeyboardButton(
                text=f"{mark}{sale}{t.truncate(item['name'], 40)} — {t.som(item['min_price'])}",
                callback_data=ProductCb(id=hexid(item["id"])).pack(),
            )
        )
    nav = []
    if page["page"] > 1:
        nav.append(
            InlineKeyboardButton(
                text=t.PREV, callback_data=ListCb(a="page", v=str(page["page"] - 1)).pack()
            )
        )
    if page["page"] < page["pages"]:
        nav.append(
            InlineKeyboardButton(
                text=t.NEXT, callback_data=ListCb(a="page", v=str(page["page"] + 1)).pack()
            )
        )
    if nav:
        kb.row(*nav)
    kb.row(
        *[
            InlineKeyboardButton(
                text=("• " if state.get("sort", "newest") == key else "") + label,
                callback_data=ListCb(a="sort", v=key).pack(),
            )
            for key, label in t.SORT_LABELS.items()
        ]
    )
    kb.row(
        InlineKeyboardButton(
            text=("☑️ " if state.get("in_stock") else "") + t.FILTER_IN_STOCK,
            callback_data=ListCb(a="stock").pack(),
        ),
        InlineKeyboardButton(
            text=("☑️ " if state.get("discounted") else "") + t.FILTER_DISCOUNTED,
            callback_data=ListCb(a="disc").pack(),
        ),
        InlineKeyboardButton(text=t.FILTER_PRICE, callback_data=ListCb(a="price").pack()),
    )
    if (
        state.get("in_stock")
        or state.get("discounted")
        or state.get("min_price")
        or state.get("max_price")
    ):
        kb.row(InlineKeyboardButton(text=t.FILTER_RESET, callback_data=ListCb(a="reset").pack()))
    return kb.as_markup()


def product(prod: dict[str, Any], selected: dict[str, Any] | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    variants = prod["variants"]
    if len(variants) > 1:
        for v in variants:
            mark = "✅ " if selected and v["id"] == selected["id"] else ""
            stock = "" if v["available"] > 0 else " ❌"
            kb.row(
                InlineKeyboardButton(
                    text=f"{mark}{t.variant_label(v)} — {t.som(v['effective_price'])}{stock}",
                    callback_data=ProductCb(id=hexid(prod["id"]), v=hexid(v["id"])).pack(),
                )
            )
    if selected is not None and selected["available"] > 0:
        kb.row(
            InlineKeyboardButton(
                text=t.ADD_TO_CART, callback_data=AddCb(v=hexid(selected["id"])).pack()
            )
        )
    if len(prod["images"]) > 1:
        kb.row(
            InlineKeyboardButton(
                text=t.MORE_PHOTOS, callback_data=PhotosCb(id=hexid(prod["id"])).pack()
            )
        )
    kb.row(InlineKeyboardButton(text=t.GO_TO_CART, callback_data=CartCb(a="view").pack()))
    return kb.as_markup()


def after_add() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t.GO_TO_CART, callback_data=CartCb(a="view"))
    return kb.as_markup()


# --- Cart ------------------------------------------------------------------------------


def cart(cart_data: dict[str, Any]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for n, line in enumerate(cart_data["lines"], start=1):
        item = hexid(line["item_id"])
        kb.row(
            InlineKeyboardButton(text="➖", callback_data=CartCb(a="dec", i=item).pack()),
            InlineKeyboardButton(
                text=f"{n}. {line['quantity']} ta", callback_data=CartCb(a="view").pack()
            ),
            InlineKeyboardButton(text="➕", callback_data=CartCb(a="inc", i=item).pack()),
            InlineKeyboardButton(text="🗑", callback_data=CartCb(a="del", i=item).pack()),
        )
    if cart_data.get("promo_code"):
        kb.row(
            InlineKeyboardButton(text=t.BTN_REMOVE_PROMO, callback_data=CartCb(a="unpromo").pack())
        )
    else:
        kb.row(InlineKeyboardButton(text=t.BTN_PROMO, callback_data=CartCb(a="promo").pack()))
    kb.row(
        InlineKeyboardButton(text=t.BTN_CLEAR_CART, callback_data=CartCb(a="clear").pack()),
        InlineKeyboardButton(text=t.BTN_CHECKOUT, callback_data=CartCb(a="checkout").pack()),
    )
    return kb.as_markup()


# --- Checkout --------------------------------------------------------------------------


def saved_addresses(addresses: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for a in addresses[:8]:
        kb.row(
            InlineKeyboardButton(
                text=t.truncate(a["address_line"], 50),
                callback_data=CheckoutCb(a="addr", v=hexid(a["id"])).pack(),
            )
        )
    kb.row(InlineKeyboardButton(text=t.NEW_ADDRESS, callback_data=CheckoutCb(a="newaddr").pack()))
    return kb.as_markup()


def regions(items: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in items:
        kb.button(text=r["name"], callback_data=CheckoutCb(a="region", v=str(r["id"])))
    kb.adjust(2)
    return kb.as_markup()


def districts(items: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in items:
        kb.button(text=d["name"], callback_data=CheckoutCb(a="district", v=str(d["id"])))
    kb.button(text=t.BACK, callback_data=CheckoutCb(a="newaddr"))
    kb.adjust(*([2] * ((len(items) + 1) // 2)), 1)
    return kb.as_markup()


def delivery_methods(quotes: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for q in quotes:
        price = t.FREE if q["free_applied"] or float(q["price"]) == 0 else t.som(q["price"])
        label = t.DELIVERY_OPTION.format(
            name=q["method_name"], price=price, eta=t.eta(q["eta_min_days"], q["eta_max_days"])
        )
        kb.row(
            InlineKeyboardButton(
                text=label, callback_data=CheckoutCb(a="method", v=hexid(q["method_id"])).pack()
            )
        )
    kb.row(InlineKeyboardButton(text=t.BACK, callback_data=CheckoutCb(a="newaddr").pack()))
    return kb.as_markup()


def skip_step() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t.BTN_SKIP_STEP, callback_data=CheckoutCb(a="skip"))
    return kb.as_markup()


def payment_methods(methods: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for m in methods:
        kb.button(text=t.PAYMENT_LABELS.get(m, m), callback_data=CheckoutCb(a="pay", v=m))
    kb.adjust(2)
    return kb.as_markup()


def confirm_order() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=t.BTN_CONFIRM, callback_data=CheckoutCb(a="confirm").pack()))
    kb.row(
        InlineKeyboardButton(text=t.BTN_RESTART, callback_data=CheckoutCb(a="restart").pack()),
        InlineKeyboardButton(text=t.BTN_CANCEL, callback_data=CheckoutCb(a="cancel").pack()),
    )
    return kb.as_markup()


# --- Orders & profile ------------------------------------------------------------------


def orders(page: dict[str, Any], labels: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for order, label in zip(page["items"], labels, strict=True):
        kb.row(
            InlineKeyboardButton(
                text=label,
                callback_data=OrderCb(a="view", id=hexid(order["id"]), p=page["page"]).pack(),
            )
        )
    nav = []
    if page["page"] > 1:
        nav.append(
            InlineKeyboardButton(
                text=t.PREV, callback_data=OrderCb(a="list", p=page["page"] - 1).pack()
            )
        )
    if page["page"] < page["pages"]:
        nav.append(
            InlineKeyboardButton(
                text=t.NEXT, callback_data=OrderCb(a="list", p=page["page"] + 1).pack()
            )
        )
    if nav:
        kb.row(*nav)
    return kb.as_markup()


def order_detail(order: dict[str, Any], page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if order["can_cancel"]:
        kb.row(
            InlineKeyboardButton(
                text=t.BTN_CANCEL_ORDER,
                callback_data=OrderCb(a="cancel", id=hexid(order["id"]), p=page).pack(),
            )
        )
    kb.row(
        InlineKeyboardButton(text=t.BTN_ORDERS_LIST, callback_data=OrderCb(a="list", p=page).pack())
    )
    return kb.as_markup()


def confirm_cancel(order_id: str, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=t.BTN_YES_CANCEL,
            callback_data=OrderCb(a="cancel_yes", id=hexid(order_id), p=page).pack(),
        ),
        InlineKeyboardButton(
            text=t.BTN_NO, callback_data=OrderCb(a="view", id=hexid(order_id), p=page).pack()
        ),
    )
    return kb.as_markup()


def profile() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t.BTN_UPDATE_PHONE, callback_data=ProfileCb(a="phone"))
    kb.button(text=t.BTN_ADDRESSES, callback_data=ProfileCb(a="addresses"))
    kb.adjust(1)
    return kb.as_markup()


def addresses(items: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for n, a in enumerate(items, start=1):
        kb.button(text=f"🗑 {n}", callback_data=ProfileCb(a="deladdr", id=hexid(a["id"])))
    kb.adjust(4)
    return kb.as_markup()
