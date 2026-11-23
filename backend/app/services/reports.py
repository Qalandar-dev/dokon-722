"""Dashboard figures and sales reports, computed from the database.

Revenue = ``orders.total`` of orders whose payment status is ``paid`` (refunded orders
drop out automatically), dated by ``paid_at``. Calendar days, weeks (Monday start)
and months are in the store's timezone (Asia/Tashkent).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.exceptions import BusinessRuleError
from app.core.money import ZERO
from app.models import Category, Order, OrderItem, Product, User
from app.models.enums import OrderStatus, PaymentStatus
from app.services.inventory import InventoryService, LowStockItem

Grouping = Literal["day", "week", "month"]
MAX_REPORT_DAYS = 366


def store_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def _local_midnight_utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=store_tz()).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date  # inclusive, store-local
    end: date  # inclusive, store-local

    @property
    def start_utc(self) -> datetime:
        return _local_midnight_utc(self.start)

    @property
    def end_utc(self) -> datetime:
        return _local_midnight_utc(self.end + timedelta(days=1))

    @classmethod
    def build(cls, start: date | None, end: date | None) -> DateRange:
        today = utcnow().astimezone(store_tz()).date()
        end = end or today
        start = start or end - timedelta(days=29)
        if start > end:
            raise BusinessRuleError("Boshlanish sanasi tugashidan keyin.", code="invalid_range")
        if (end - start).days > MAX_REPORT_DAYS:
            raise BusinessRuleError("Hisobot davri 1 yildan oshmasin.", code="range_too_long")
        return cls(start, end)


@dataclass(frozen=True, slots=True)
class RevenueStat:
    revenue: Decimal
    orders: int


@dataclass(frozen=True, slots=True)
class Dashboard:
    revenue_total: Decimal
    revenue_today: RevenueStat
    revenue_week: RevenueStat
    revenue_month: RevenueStat
    orders_total: int
    orders_pending: int
    orders_in_progress: int
    orders_completed: int
    orders_cancelled: int
    customers_total: int
    customers_new_month: int
    low_stock: list[LowStockItem]
    best_sellers: list[dict[str, Any]]
    sales_chart: list[dict[str, Any]]


PAID = Order.payment_status == PaymentStatus.PAID


def _local(column: Any) -> Any:
    return func.timezone(get_settings().timezone, column)


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _revenue_between(self, start: datetime, end: datetime) -> RevenueStat:
        row = (
            await self.session.execute(
                select(func.coalesce(func.sum(Order.total), ZERO), func.count(Order.id)).where(
                    PAID, Order.paid_at >= start, Order.paid_at < end
                )
            )
        ).one()
        return RevenueStat(Decimal(row[0]), int(row[1]))

    async def _count(self, stmt: Select) -> int:  # type: ignore[type-arg]
        return int(await self.session.scalar(stmt) or 0)

    async def dashboard(self) -> Dashboard:
        now_local = utcnow().astimezone(store_tz())
        today = now_local.date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        tomorrow_utc = _local_midnight_utc(today + timedelta(days=1))

        total = await self.session.scalar(
            select(func.coalesce(func.sum(Order.total), ZERO)).where(PAID)
        )
        status_counts = dict(
            (
                await self.session.execute(
                    select(Order.status, func.count()).group_by(Order.status)
                )
            ).all()
        )
        in_progress = sum(
            status_counts.get(s, 0)
            for s in (
                OrderStatus.CONFIRMED,
                OrderStatus.PROCESSING,
                OrderStatus.SHIPPED,
                OrderStatus.OUT_FOR_DELIVERY,
            )
        )
        chart_range = DateRange(today - timedelta(days=29), today)
        return Dashboard(
            revenue_total=Decimal(total or 0),
            revenue_today=await self._revenue_between(_local_midnight_utc(today), tomorrow_utc),
            revenue_week=await self._revenue_between(_local_midnight_utc(week_start), tomorrow_utc),
            revenue_month=await self._revenue_between(
                _local_midnight_utc(month_start), tomorrow_utc
            ),
            orders_total=sum(status_counts.values()),
            orders_pending=status_counts.get(OrderStatus.PENDING, 0),
            orders_in_progress=in_progress,
            orders_completed=status_counts.get(OrderStatus.DELIVERED, 0),
            orders_cancelled=status_counts.get(OrderStatus.CANCELLED, 0),
            customers_total=await self._count(select(func.count()).select_from(User)),
            customers_new_month=await self._count(
                select(func.count()).where(User.created_at >= _local_midnight_utc(month_start))
            ),
            low_stock=await InventoryService(self.session).low_stock(limit=10),
            best_sellers=await self.top_products(chart_range, limit=5),
            sales_chart=await self.sales(chart_range, "day"),
        )

    async def sales(self, period: DateRange, grouping: Grouping = "day") -> list[dict[str, Any]]:
        """Revenue per day/week/month, with empty periods filled with zeros."""
        bucket = func.date_trunc(grouping, _local(Order.paid_at)).label("bucket")
        rows = await self.session.execute(
            select(bucket, func.count(Order.id), func.sum(Order.total))
            .where(PAID, Order.paid_at >= period.start_utc, Order.paid_at < period.end_utc)
            .group_by(bucket)
        )
        found = {r[0].date(): (int(r[1]), Decimal(r[2])) for r in rows}

        def bucket_start(d: date) -> date:
            if grouping == "week":
                return d - timedelta(days=d.weekday())
            if grouping == "month":
                return d.replace(day=1)
            return d

        result, seen = [], set()
        d = period.start
        while d <= period.end:
            key = bucket_start(d)
            if key not in seen:
                seen.add(key)
                orders, revenue = found.get(key, (0, ZERO))
                result.append(
                    {
                        "period": key.isoformat(),
                        "orders": orders,
                        "revenue": revenue,
                        "average_order": (revenue / orders).quantize(Decimal("0.01"))
                        if orders
                        else ZERO,
                    }
                )
            d += timedelta(days=1)
        return result

    def _paid_items(self, period: DateRange) -> Select:  # type: ignore[type-arg]
        return (
            select(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .where(PAID, Order.paid_at >= period.start_utc, Order.paid_at < period.end_utc)
        )

    async def top_products(self, period: DateRange, limit: int = 20) -> list[dict[str, Any]]:
        units = func.sum(OrderItem.quantity).label("units")
        revenue = func.sum(OrderItem.line_total).label("revenue")
        rows = await self.session.execute(
            select(OrderItem.product_id, func.max(OrderItem.product_name), units, revenue)
            .join(Order, Order.id == OrderItem.order_id)
            .where(PAID, Order.paid_at >= period.start_utc, Order.paid_at < period.end_utc)
            .group_by(OrderItem.product_id)
            .order_by(units.desc(), revenue.desc())
            .limit(limit)
        )
        return [
            {
                "product_id": str(r[0]) if r[0] else None,
                "product_name": r[1],
                "units": int(r[2]),
                "revenue": Decimal(r[3]),
            }
            for r in rows
        ]

    async def by_category(self, period: DateRange) -> list[dict[str, Any]]:
        revenue = func.sum(OrderItem.line_total).label("revenue")
        name = func.coalesce(Category.name, "Nomaʼlum").label("category")
        rows = await self.session.execute(
            select(name, func.sum(OrderItem.quantity), revenue)
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(Product, Product.id == OrderItem.product_id)
            .outerjoin(Category, Category.id == Product.category_id)
            .where(PAID, Order.paid_at >= period.start_utc, Order.paid_at < period.end_utc)
            .group_by(name)
            .order_by(revenue.desc())
        )
        return [{"category": r[0], "units": int(r[1]), "revenue": Decimal(r[2])} for r in rows]

    async def top_customers(self, period: DateRange, limit: int = 20) -> list[dict[str, Any]]:
        revenue = func.sum(Order.total).label("revenue")
        rows = await self.session.execute(
            select(
                User.id, User.first_name, User.last_name, User.phone, func.count(Order.id), revenue
            )
            .join(Order, Order.user_id == User.id)
            .where(PAID, Order.paid_at >= period.start_utc, Order.paid_at < period.end_utc)
            .group_by(User.id)
            .order_by(revenue.desc())
            .limit(limit)
        )
        return [
            {
                "user_id": str(r[0]),
                "name": " ".join(x for x in (r[1], r[2]) if x),
                "phone": r[3],
                "orders": int(r[4]),
                "revenue": Decimal(r[5]),
            }
            for r in rows
        ]

    async def by_payment_method(self, period: DateRange) -> list[dict[str, Any]]:
        rows = await self.session.execute(
            select(Order.payment_method, func.count(Order.id), func.sum(Order.total))
            .where(PAID, Order.paid_at >= period.start_utc, Order.paid_at < period.end_utc)
            .group_by(Order.payment_method)
            .order_by(func.sum(Order.total).desc())
        )
        return [
            {"payment_method": r[0].value, "orders": int(r[1]), "revenue": Decimal(r[2])}
            for r in rows
        ]

    async def by_status(self, period: DateRange) -> list[dict[str, Any]]:
        """Orders *placed* in the period, by current status."""
        rows = await self.session.execute(
            select(Order.status, func.count(Order.id), func.sum(Order.total))
            .where(Order.created_at >= period.start_utc, Order.created_at < period.end_utc)
            .group_by(Order.status)
        )
        return [{"status": r[0].value, "orders": int(r[1]), "amount": Decimal(r[2])} for r in rows]


def to_csv(rows: list[dict[str, Any]]) -> str:
    """CSV with a UTF-8 BOM so Excel shows Uzbek letters correctly."""
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return "﻿" + buffer.getvalue()
