"""Render API data as message text. Pure functions, no I/O."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.bot import texts as t
from app.core.config import get_settings

CAPTION_LIMIT = 1024


def local_time(iso: str) -> str:
    moment = datetime.fromisoformat(iso).astimezone(ZoneInfo(get_settings().timezone))
    return moment.strftime("%d.%m.%Y %H:%M")


def default_variant(product: dict[str, Any]) -> dict[str, Any]:
    variants = product["variants"]
    in_stock = [v for v in variants if v["available"] > 0]
    preferred = [v for v in (in_stock or variants) if v["is_default"]]
    return (preferred or in_stock or variants)[0]


def product_card(product: dict[str, Any], selected: dict[str, Any] | None) -> str:
    variant = selected or default_variant(product)
    multi = len(product["variants"]) > 1
    brand = f"\n<i>{t.esc(product['brand'])}</i>" if product.get("brand") else ""
    price = t.price_line(variant["price"], variant.get("discount_price"))
    if multi:
        price = f"{t.esc(t.variant_label(variant))}: {price}"
    stock = t.IN_STOCK if variant["available"] > 0 else t.OUT_OF_STOCK
    hint = t.CHOOSE_VARIANT if multi and selected is None else ""
    head = t.PRODUCT_CARD.format(
        name=t.esc(product["name"]),
        brand=brand,
        price=price,
        stock=stock,
        variants=hint,
        description="",
    )
    description = product.get("description") or ""
    room = CAPTION_LIMIT - len(head) - 4
    if description and room > 40:
        head += "\n\n" + t.esc(t.truncate(description, room))
    return head


def product_list_title(state: dict[str, Any], page: dict[str, Any]) -> str:
    text = t.PRODUCTS_TITLE.format(
        title=t.esc(state.get("title") or t.CATALOG_ALL),
        total=page["total"],
        page=page["page"],
        pages=page["pages"],
    )
    filters = []
    if state.get("in_stock"):
        filters.append(t.FILTER_IN_STOCK)
    if state.get("discounted"):
        filters.append(t.FILTER_DISCOUNTED)
    if state.get("min_price") or state.get("max_price"):
        lo = t.som(state["min_price"]) if state.get("min_price") else "…"
        hi = t.som(state["max_price"]) if state.get("max_price") else "…"
        filters.append(f"{lo} – {hi}")
    if filters:
        text += "\n" + t.PRODUCTS_FILTERS.format(filters=", ".join(filters))
    if not page["items"]:
        text += "\n\n" + t.PRODUCTS_EMPTY
    return text


def cart_text(cart: dict[str, Any]) -> str:
    if not cart["lines"]:
        return t.CART_EMPTY
    lines = [t.CART_TITLE]
    for n, line in enumerate(cart["lines"], start=1):
        name = line["product_name"] + (f" ({line['variant_name']})" if line["variant_name"] else "")
        warn = ""
        if not line["is_purchasable"]:
            reason = (
                t.CART_LINE_SHORT.format(available=line["available"])
                if line["available"] > 0
                else t.CART_LINE_UNAVAILABLE
            )
            warn = t.CART_LINE_WARN.format(reason=reason)
        lines.append(
            t.CART_LINE.format(
                n=n,
                name=t.esc(name),
                qty=line["quantity"],
                price=t.som(line["unit_price"]),
                total=t.som(line["line_total"]),
                warn=warn,
            )
        )
    lines.append("")
    lines.append(t.CART_SUBTOTAL.format(amount=t.som(cart["subtotal"])))
    if Decimal(cart["discount"]) > 0:
        lines.append(
            t.CART_DISCOUNT.format(code=t.esc(cart["promo_code"]), amount=t.som(cart["discount"]))
        )
    elif cart.get("promo_code") and cart.get("promo_error"):
        lines.append(
            t.CART_PROMO_PROBLEM.format(
                code=t.esc(cart["promo_code"]), error=t.esc(cart["promo_error"])
            )
        )
    lines.append(t.CART_TOTAL.format(amount=t.som(cart["total"])))
    if cart["has_problems"]:
        lines.append("\n" + t.CART_HAS_PROBLEMS)
    return "\n".join(lines)


def checkout_summary(data: dict[str, Any], preview: dict[str, Any]) -> str:
    landmark = f"\n🧭 {t.esc(data['landmark'])}" if data.get("landmark") else ""
    delivery = preview["delivery"]
    discount = (
        f"\nChegirma: −{t.som(preview['discount'])}" if Decimal(preview["discount"]) > 0 else ""
    )
    fee = t.FREE if Decimal(preview["delivery_fee"]) == 0 else t.som(preview["delivery_fee"])
    items = [
        t.ORDER_ITEM.format(
            name=t.esc(
                line["product_name"]
                + (f" ({line['variant_name']})" if line["variant_name"] else "")
            ),
            qty=line["quantity"],
            price=t.som(line["unit_price"]),
        )
        for line in preview["cart"]["lines"]
    ]
    return "\n".join(
        [
            t.SUMMARY_TITLE,
            *items,
            "",
            t.SUMMARY_RECIPIENT.format(
                name=t.esc(data["recipient_name"]), phone=t.esc(data["recipient_phone"])
            ),
            t.SUMMARY_ADDRESS.format(
                region=t.esc(preview["region_name"]),
                district=t.esc(preview["district_name"]),
                address=t.esc(data["address_line"]),
                landmark=landmark,
            ),
            t.SUMMARY_DELIVERY.format(
                method=t.esc(delivery["method_name"]),
                price=fee,
                eta=t.eta(delivery["eta_min_days"], delivery["eta_max_days"]),
            ),
            t.SUMMARY_PAYMENT.format(
                payment=t.PAYMENT_LABELS.get(data["payment_method"], data["payment_method"])
            ),
            "",
            t.SUMMARY_TOTALS.format(
                subtotal=t.som(preview["subtotal"]),
                discount=discount,
                delivery=fee,
                total=t.som(preview["total"]),
            ),
        ]
    )


def order_card(order: dict[str, Any]) -> str:
    items = "\n".join(
        t.ORDER_ITEM.format(
            name=t.esc(
                i["product_name"] + (f" ({i['variant_name']})" if i["variant_name"] else "")
            ),
            qty=i["quantity"],
            price=t.som(i["unit_price"]),
        )
        for i in order["items"]
    )
    discount = (
        f"\nChegirma ({t.esc(order['promo_code'] or '')}): −{t.som(order['discount_total'])}"
        if Decimal(order["discount_total"]) > 0
        else ""
    )
    eta = t.eta(order.get("delivery_eta_min_days"), order.get("delivery_eta_max_days"))
    text = t.ORDER_CARD.format(
        number=order["number"],
        date=local_time(order["created_at"]),
        status=order["labels"]["status"],
        payment_status=order["labels"]["payment_status"],
        payment_method=t.PAYMENT_LABELS.get(order["payment_method"], order["payment_method"]),
        delivery_status=order["labels"]["delivery_status"],
        items=items,
        subtotal=t.som(order["subtotal"]),
        discount=discount,
        delivery_fee=t.FREE
        if Decimal(order["delivery_fee"]) == 0
        else t.som(order["delivery_fee"]),
        total=t.som(order["total"]),
        recipient=t.esc(order["recipient_name"]),
        phone=t.esc(order["recipient_phone"]),
        region=t.esc(order["region_name"]),
        district=t.esc(order["district_name"]),
        address=t.esc(order["address_line"]),
        method=t.esc(order["delivery_method_name"]),
        eta=f" ({eta})" if eta else "",
    )
    if order.get("cancel_reason") and order["status"] == "cancelled":
        text += f"\n\nSabab: {t.esc(order['cancel_reason'])}"
    return text


def order_button(order: dict[str, Any]) -> str:
    return t.ORDER_BUTTON.format(
        number=order["number"], status=order["labels"]["status"], total=t.som(order["total"])
    )


def profile_text(profile: dict[str, Any]) -> str:
    name = " ".join(x for x in (profile["first_name"], profile.get("last_name")) if x)
    phone = (
        t.esc(profile["phone"]) + (t.PHONE_VERIFIED if profile["phone_verified"] else "")
        if profile.get("phone")
        else t.NOT_SET
    )
    return t.PROFILE.format(
        name=t.esc(name),
        phone=phone,
        username=f"@{t.esc(profile['username'])}" if profile.get("username") else t.NOT_SET,
        date=local_time(profile["created_at"]).split(" ")[0],
    )


def support_text(store: dict[str, Any]) -> str:
    lines = []
    if store.get("phone"):
        lines.append(t.SUPPORT_PHONE.format(phone=t.esc(store["phone"])))
    if store.get("support_telegram"):
        lines.append(t.SUPPORT_TELEGRAM.format(username=t.esc(store["support_telegram"])))
    if store.get("address"):
        lines.append(t.SUPPORT_ADDRESS.format(address=t.esc(store["address"])))
    return t.SUPPORT.format(store=t.esc(store["name"]), lines="\n".join(lines) or t.SUPPORT_NONE)
