from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.deps import AdminContext, SessionDep, require
from app.core.permissions import Permission
from app.schemas.admin import DashboardOut
from app.services.reports import DateRange, ReportService, to_csv

router = APIRouter(prefix="/admin", tags=["admin: reports"])

ViewDashboard = Annotated[AdminContext, Depends(require(Permission.DASHBOARD_VIEW))]
ViewReports = Annotated[AdminContext, Depends(require(Permission.REPORTS_VIEW))]
Format = Annotated[Literal["json", "csv"], Query(alias="format")]


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(_: ViewDashboard, session: SessionDep) -> DashboardOut:
    return DashboardOut.build(await ReportService(session).dashboard())


def _respond(rows: list[dict[str, Any]], fmt: str, name: str, period: DateRange) -> Any:
    if fmt == "csv":
        filename = f"{name}_{period.start.isoformat()}_{period.end.isoformat()}.csv"
        return Response(
            to_csv(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return {"date_from": period.start, "date_to": period.end, "rows": rows}


@router.get("/reports/sales")
async def sales_report(
    _: ViewReports,
    session: SessionDep,
    date_from: date | None = None,
    date_to: date | None = None,
    group_by: Literal["day", "week", "month"] = "day",
    fmt: Format = "json",
) -> Any:
    period = DateRange.build(date_from, date_to)
    return _respond(await ReportService(session).sales(period, group_by), fmt, "sales", period)


@router.get("/reports/categories")
async def category_report(
    _: ViewReports,
    session: SessionDep,
    date_from: date | None = None,
    date_to: date | None = None,
    fmt: Format = "json",
) -> Any:
    period = DateRange.build(date_from, date_to)
    return _respond(await ReportService(session).by_category(period), fmt, "categories", period)


@router.get("/reports/products")
async def product_report(
    _: ViewReports,
    session: SessionDep,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    fmt: Format = "json",
) -> Any:
    period = DateRange.build(date_from, date_to)
    rows = await ReportService(session).top_products(period, limit=limit)
    return _respond(rows, fmt, "top_products", period)


@router.get("/reports/customers")
async def customer_report(
    _: ViewReports,
    session: SessionDep,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    fmt: Format = "json",
) -> Any:
    period = DateRange.build(date_from, date_to)
    rows = await ReportService(session).top_customers(period, limit=limit)
    return _respond(rows, fmt, "top_customers", period)


@router.get("/reports/payment-methods")
async def payment_method_report(
    _: ViewReports,
    session: SessionDep,
    date_from: date | None = None,
    date_to: date | None = None,
    fmt: Format = "json",
) -> Any:
    period = DateRange.build(date_from, date_to)
    rows = await ReportService(session).by_payment_method(period)
    return _respond(rows, fmt, "payment_methods", period)


@router.get("/reports/order-statuses")
async def status_report(
    _: ViewReports,
    session: SessionDep,
    date_from: date | None = None,
    date_to: date | None = None,
    fmt: Format = "json",
) -> Any:
    period = DateRange.build(date_from, date_to)
    return _respond(await ReportService(session).by_status(period), fmt, "order_statuses", period)
