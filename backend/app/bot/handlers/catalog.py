"""Categories, product lists (sort, filters, price range, search), product cards."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import texts as t
from app.bot import views
from app.bot.api_client import StoreApi
from app.bot.callbacks import AddCb, CategoryCb, ListCb, PhotosCb, ProductCb, uuid_from_hex
from app.bot.handlers.common import (
    edit_or_send,
    photo_source,
    remember_file_id,
    send_album,
    show_main_menu,
)
from app.bot.states import Browse

router = Router(name="catalog")

PAGE_SIZE = 8
LIST_KEY = "list"


def _find(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    for node in nodes:
        if node["id"].replace("-", "") == node_id:
            return node
        if (found := _find(node["children"], node_id)) is not None:
            return found
    return None


# --- Categories --------------------------------------------------------------------------


@router.message(F.text == t.BTN_CATEGORIES)
async def categories(message: Message, api: StoreApi) -> None:
    tree = await api.categories()
    if not tree:
        await message.answer(t.CATEGORIES_EMPTY)
        return
    await message.answer(t.CATEGORIES_TITLE, reply_markup=kb.categories(tree, parent=None))


@router.callback_query(CategoryCb.filter())
async def category(
    callback: CallbackQuery, callback_data: CategoryCb, api: StoreApi, state: FSMContext
) -> None:
    tree = await api.categories()
    if not callback_data.id:
        await edit_or_send(callback, t.CATEGORIES_TITLE, kb.categories(tree, parent=None))
    else:
        node = _find(tree, callback_data.id)
        if node is None:
            await callback.answer(t.STALE_ACTION, show_alert=True)
            return
        if node["children"]:
            await edit_or_send(
                callback,
                t.SUBCATEGORIES_TITLE.format(name=t.esc(node["name"])),
                kb.categories(node["children"], parent=node),
            )
        else:
            await _start_list(callback, api, state, title=node["name"], category_id=node["id"])
    await callback.answer()


# --- Product lists -----------------------------------------------------------------------


async def _list_state(state: FSMContext) -> dict[str, Any]:
    return dict((await state.get_data()).get(LIST_KEY) or {})


async def _render_list(
    target: Message | CallbackQuery, api: StoreApi, listing: dict[str, Any]
) -> None:
    page = await api.products(
        category_id=listing.get("category_id"),
        q=listing.get("q"),
        sort=listing.get("sort", "newest"),
        in_stock=listing.get("in_stock") or None,
        discounted=listing.get("discounted") or None,
        min_price=listing.get("min_price"),
        max_price=listing.get("max_price"),
        page=listing.get("page", 1),
        page_size=PAGE_SIZE,
    )
    text = views.product_list_title(listing, page)
    markup = kb.product_list(page, listing)
    if isinstance(target, CallbackQuery):
        await edit_or_send(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


async def _start_list(
    target: Message | CallbackQuery,
    api: StoreApi,
    state: FSMContext,
    *,
    title: str,
    category_id: str | None = None,
    query: str | None = None,
) -> None:
    listing = {"title": title, "category_id": category_id, "q": query, "sort": "newest", "page": 1}
    await state.update_data({LIST_KEY: listing})
    await _render_list(target, api, listing)


@router.message(F.text == t.BTN_CATALOG)
async def catalog(message: Message, api: StoreApi, state: FSMContext) -> None:
    await _start_list(message, api, state, title=t.CATALOG_ALL)


@router.callback_query(ListCb.filter())
async def list_action(
    callback: CallbackQuery, callback_data: ListCb, api: StoreApi, state: FSMContext
) -> None:
    listing = await _list_state(state)
    action, value = callback_data.a, callback_data.v
    if action == "cat":
        tree = await api.categories()
        node = _find(tree, value)
        if node is None:
            await callback.answer(t.STALE_ACTION, show_alert=True)
            return
        await _start_list(callback, api, state, title=node["name"], category_id=node["id"])
        await callback.answer()
        return
    if not listing:
        await callback.answer(t.STALE_ACTION, show_alert=True)
        return
    if action == "price":
        await state.set_state(Browse.price_range)
        await callback.message.answer(t.ASK_PRICE_RANGE, reply_markup=kb.cancel_only())  # type: ignore[union-attr]
        await callback.answer()
        return
    if action == "page":
        listing["page"] = max(1, int(value or 1))
    elif action == "sort" and value in t.SORT_LABELS:
        listing.update(sort=value, page=1)
    elif action == "stock":
        listing.update(in_stock=not listing.get("in_stock"), page=1)
    elif action == "disc":
        listing.update(discounted=not listing.get("discounted"), page=1)
    elif action == "reset":
        listing.update(in_stock=False, discounted=False, min_price=None, max_price=None, page=1)
    await state.update_data({LIST_KEY: listing})
    await _render_list(callback, api, listing)
    await callback.answer()


_PRICE_RE = re.compile(r"^\s*([\d\s]*)\s*-\s*([\d\s]*)\s*$")


def parse_price_range(text: str) -> tuple[str | None, str | None] | None:
    match = _PRICE_RE.match(text.replace("so‘m", "").replace("som", ""))
    if not match:
        return None
    try:
        lo, hi = (Decimal(g.replace(" ", "")) if g.strip() else None for g in match.groups())
    except InvalidOperation:
        return None
    if (lo is None and hi is None) or (lo is not None and hi is not None and lo > hi):
        return None
    return (str(lo) if lo is not None else None, str(hi) if hi is not None else None)


@router.message(Browse.price_range, F.text)
async def price_range(message: Message, api: StoreApi, state: FSMContext) -> None:
    parsed = parse_price_range(message.text or "")
    if parsed is None:
        await message.answer(t.BAD_PRICE_RANGE)
        return
    listing = await _list_state(state)
    listing.update(min_price=parsed[0], max_price=parsed[1], page=1)
    await state.set_state(None)
    await state.update_data({LIST_KEY: listing})
    await show_main_menu(message, "✅")
    await _render_list(message, api, listing)


@router.message(F.text == t.BTN_SEARCH)
async def search_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Browse.search_query)
    await message.answer(t.ASK_SEARCH, reply_markup=kb.cancel_only())


@router.message(Browse.search_query, F.text)
async def search(message: Message, api: StoreApi, state: FSMContext) -> None:
    query = " ".join((message.text or "").split())[:100]
    if len(query) < 2:
        await message.answer(t.SEARCH_TOO_SHORT)
        return
    await state.set_state(None)
    await show_main_menu(message, "🔎")
    await _start_list(message, api, state, title=t.SEARCH_RESULTS.format(query=query), query=query)


# --- Product card ------------------------------------------------------------------------


@router.callback_query(ProductCb.filter())
async def product(
    callback: CallbackQuery,
    callback_data: ProductCb,
    api: StoreApi,
    media_base_url: str | None,
) -> None:
    prod = await api.product(uuid_from_hex(callback_data.id))
    selected = None
    if callback_data.v:
        selected = next(
            (v for v in prod["variants"] if v["id"].replace("-", "") == callback_data.v), None
        )
        if selected is not None and selected["available"] <= 0:
            await callback.answer(t.SOLD_OUT_ALERT, show_alert=True)
    elif len(prod["variants"]) == 1:
        selected = prod["variants"][0]
    caption = views.product_card(prod, selected)
    markup = kb.product(prod, selected)
    message = callback.message
    assert isinstance(message, Message)

    # Choosing a variant on the same card: edit it in place.
    if callback_data.v and (message.photo or message.text):
        if message.photo:
            await message.edit_caption(caption=caption, reply_markup=markup)
        else:
            await edit_or_send(callback, caption, markup)
        await callback.answer()
        return

    images = sorted(prod["images"], key=lambda i: (not i["is_main"], i["sort_order"]))
    if images:
        sent = await message.answer_photo(
            await photo_source(api, images[0], media_base_url), caption=caption, reply_markup=markup
        )
        await remember_file_id(api, images[0], sent)
    else:
        await message.answer(caption, reply_markup=markup)
    await callback.answer()


@router.callback_query(PhotosCb.filter())
async def photos(
    callback: CallbackQuery, callback_data: PhotosCb, api: StoreApi, media_base_url: str | None
) -> None:
    prod = await api.product(uuid_from_hex(callback_data.id))
    assert isinstance(callback.message, Message)
    await send_album(callback.message, api, prod["images"], media_base_url)
    await callback.answer()


@router.callback_query(AddCb.filter())
async def add_to_cart(callback: CallbackQuery, callback_data: AddCb, api: StoreApi) -> None:
    cart = await api.add_to_cart(callback.from_user.id, uuid_from_hex(callback_data.v), 1)
    await callback.answer(t.ADDED_TO_CART.format(count=cart["total_quantity"]))
