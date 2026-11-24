"""Uzbek texts for worker-sent notifications. Values are HTML-escaped."""

from __future__ import annotations

from typing import Any

from app.bot.texts import esc, som

PAYMENT_LABELS = {"click": "Click", "payme": "Payme", "cash_on_delivery": "naqd (kuryerga)"}

_CUSTOMER = {
    "order.placed": "🧾 Buyurtmangiz <b>{number}</b> qabul qilindi. Jami: {total}.",
    "order.paid": "✅ <b>{number}</b> buyurtma uchun to‘lov qabul qilindi ({total}). Rahmat!",
    "order.confirmed": "👍 Buyurtmangiz <b>{number}</b> tasdiqlandi va tayyorlanmoqda.",
    "order.shipped": "🚚 Buyurtmangiz <b>{number}</b> jo‘natildi ({delivery}).",
    "order.out_for_delivery": "🛵 Buyurtmangiz <b>{number}</b> kuryerda — tez orada yetkaziladi.",
    "order.delivered": "🎉 Buyurtmangiz <b>{number}</b> yetkazildi. Xaridingiz uchun rahmat!",
    "order.delivery_failed": "⚠️ <b>{number}</b> buyurtmani yetkazib bo‘lmadi. Kuryer siz bilan qayta bog‘lanadi.",
    "order.cancelled": "❌ Buyurtma <b>{number}</b> bekor qilindi.{reason}",
    "order.refunded": "💸 <b>{number}</b> buyurtma bo‘yicha {total} qaytarildi.",
}


def render(event: str, payload: dict[str, Any]) -> str | None:
    if event in _CUSTOMER:
        reason = f"\nSabab: {esc(payload['comment'])}" if payload.get("comment") else ""
        return _CUSTOMER[event].format(
            number=esc(payload.get("number", "")),
            total=som(payload.get("total", "0")),
            delivery=esc(payload.get("delivery_method") or ""),
            reason=reason,
        )
    if event == "staff.new_order":
        return (
            f"🆕 Yangi buyurtma <b>{esc(payload['number'])}</b>\n"
            f"💰 {som(payload['total'])} · {PAYMENT_LABELS.get(payload['payment_method'], payload['payment_method'])}\n"
            f"👤 {esc(payload.get('recipient', ''))}, {esc(payload.get('phone', ''))}\n"
            f"📍 {esc(payload.get('region', ''))}, {esc(payload.get('district', ''))}\n"
            f"📦 {payload.get('items', 0)} dona · {esc(payload.get('delivery_method', ''))}"
        )
    if event == "staff.low_stock":
        lines = [
            f"• {esc(i['name'])} ({esc(i['sku'])}) — {i['available']} dona"
            for i in payload["items"]
        ]
        more = payload.get("more", 0)
        return (
            "📉 <b>Kam qolgan mahsulotlar</b>\n"
            + "\n".join(lines)
            + (f"\n… va yana {more} ta" if more else "")
        )
    if event == "staff.daily_report":
        top = "\n".join(
            f"{n}. {esc(p['product_name'])} — {p['units']} dona"
            for n, p in enumerate(payload["top"], 1)
        )
        return (
            f"📊 <b>Kunlik hisobot · {esc(payload['date'])}</b>\n"
            f"Tushum: {som(payload['revenue'])} ({payload['paid_orders']} ta to‘langan)\n"
            f"Yangi buyurtmalar: {payload['new_orders']} · Bekor: {payload['cancelled']}"
            + (f"\n\nEng ko‘p sotilgan:\n{top}" if top else "")
        )
    return None
