"""Inline-button callback payloads. Telegram limits them to 64 bytes, so ids are UUID hex
(32 chars) and field names are short. List filters live in FSM data, not here."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class CategoryCb(CallbackData, prefix="c"):
    id: str  # category hex id, or "" for the root


class ListCb(CallbackData, prefix="l"):
    """Product list navigation/filters; the list definition itself is in FSM data."""

    a: str  # page | sort | stock | disc | price | reset
    v: str = ""


class ProductCb(CallbackData, prefix="p"):
    id: str  # product hex
    v: str = ""  # selected variant hex


class AddCb(CallbackData, prefix="a"):
    v: str  # variant hex


class PhotosCb(CallbackData, prefix="ph"):
    id: str  # product hex


class CartCb(CallbackData, prefix="k"):
    a: str  # view | inc | dec | del | clear | promo | unpromo | checkout
    i: str = ""  # cart item hex


class CheckoutCb(CallbackData, prefix="o"):
    a: str  # addr | newaddr | region | district | method | pay | confirm | restart | cancel | skip
    v: str = ""


class OrderCb(CallbackData, prefix="r"):
    a: str  # list | view | cancel | cancel_yes
    id: str = ""
    p: int = 1


class ProfileCb(CallbackData, prefix="u"):
    a: str  # phone | addresses | deladdr
    id: str = ""


def hexid(value: str) -> str:
    """UUID string → 32-char hex (fits in callback data)."""
    return value.replace("-", "")


def uuid_from_hex(value: str) -> str:
    v = value.replace("-", "")
    return f"{v[:8]}-{v[8:12]}-{v[12:16]}-{v[16:20]}-{v[20:]}"
