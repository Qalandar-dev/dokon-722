from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminContext, SessionDep, require
from app.core.permissions import Permission
from app.models.enums import DeliveryStatus, OrderStatus, PaymentMethod, PaymentStatus
from app.schemas.admin import AdminCustomerOut, CustomerUpdateIn
from app.schemas.common import Page
from app.schemas.orders import (
    AdminOrderListItemOut,
    AdminOrderOut,
    CancelIn,
    DeliveryStatusChangeIn,
    InternalNoteIn,
    RefundIn,
    StatusChangeIn,
)
from app.services.customers import CustomerService
from app.services.orders import Actor, OrderService
from app.services.reports import DateRange

router = APIRouter(prefix="/admin", tags=["admin: orders"])

ViewOrders = Annotated[AdminContext, Depends(require(Permission.ORDERS_VIEW))]
ManageOrders = Annotated[AdminContext, Depends(require(Permission.ORDERS_MANAGE))]
RefundOrders = Annotated[AdminContext, Depends(require(Permission.ORDERS_REFUND))]
ViewCustomers = Annotated[AdminContext, Depends(require(Permission.CUSTOMERS_VIEW))]
ManageCustomers = Annotated[AdminContext, Depends(require(Permission.CUSTOMERS_MANAGE))]


@router.get("/orders", response_model=Page[AdminOrderListItemOut])
async def list_orders(
    _: ViewOrders,
    session: SessionDep,
    status: OrderStatus | None = None,
    payment_status: PaymentStatus | None = None,
    delivery_status: DeliveryStatus | None = None,
    payment_method: PaymentMethod | None = None,
    region_id: int | None = None,
    customer_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Number, name or phone")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: Annotated[str, Query(pattern="^-?(created_at|total)$")] = "-created_at",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AdminOrderListItemOut]:
    period = DateRange.build(date_from, date_to) if date_from or date_to else None
    result = await OrderService(session).list_for_admin(
        status=status,
        payment_status=payment_status,
        delivery_status=delivery_status,
        payment_method=payment_method,
        region_id=region_id,
        user_id=customer_id,
        query=q,
        created_from=period.start_utc if period else None,
        created_to=period.end_utc if period else None,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page.build(result, AdminOrderListItemOut.build)


@router.get("/orders/{order_id}", response_model=AdminOrderOut)
async def get_order(order_id: uuid.UUID, _: ViewOrders, session: SessionDep) -> AdminOrderOut:
    return AdminOrderOut.build(await OrderService(session).get(order_id))


@router.post("/orders/{order_id}/confirm", response_model=AdminOrderOut)
async def confirm_order(
    order_id: uuid.UUID, ctx: ManageOrders, session: SessionDep
) -> AdminOrderOut:
    return AdminOrderOut.build(await OrderService(session).confirm(order_id, admin_user_id=ctx.id))


@router.post("/orders/{order_id}/status", response_model=AdminOrderOut)
async def change_status(
    order_id: uuid.UUID, body: StatusChangeIn, ctx: ManageOrders, session: SessionDep
) -> AdminOrderOut:
    order = await OrderService(session).change_status(
        order_id, body.status, admin_user_id=ctx.id, comment=body.comment
    )
    return AdminOrderOut.build(order)


@router.post("/orders/{order_id}/delivery-status", response_model=AdminOrderOut)
async def change_delivery_status(
    order_id: uuid.UUID, body: DeliveryStatusChangeIn, ctx: ManageOrders, session: SessionDep
) -> AdminOrderOut:
    order = await OrderService(session).change_delivery_status(
        order_id, body.delivery_status, admin_user_id=ctx.id, comment=body.comment
    )
    return AdminOrderOut.build(order)


@router.post("/orders/{order_id}/cancel", response_model=AdminOrderOut)
async def cancel_order(
    order_id: uuid.UUID, body: CancelIn, ctx: ManageOrders, session: SessionDep
) -> AdminOrderOut:
    order = await OrderService(session).cancel(
        order_id, actor=Actor.admin(ctx.id), reason=body.reason
    )
    return AdminOrderOut.build(order)


@router.post("/orders/{order_id}/refund", response_model=AdminOrderOut)
async def refund_order(
    order_id: uuid.UUID, body: RefundIn, ctx: RefundOrders, session: SessionDep
) -> AdminOrderOut:
    order = await OrderService(session).record_refund(
        order_id, admin_user_id=ctx.id, restock=body.restock, reason=body.reason
    )
    return AdminOrderOut.build(order)


@router.patch("/orders/{order_id}/note", response_model=AdminOrderOut)
async def set_note(
    order_id: uuid.UUID, body: InternalNoteIn, ctx: ManageOrders, session: SessionDep
) -> AdminOrderOut:
    order = await OrderService(session).set_internal_note(
        order_id, body.internal_note, admin_user_id=ctx.id
    )
    return AdminOrderOut.build(order)


# --- Customers ---------------------------------------------------------------------------


@router.get("/customers", response_model=Page[AdminCustomerOut], tags=["admin: customers"])
async def list_customers(
    _: ViewCustomers,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    blocked: bool | None = None,
    sort: Annotated[str, Query(pattern="^(newest|spent|orders)$")] = "newest",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AdminCustomerOut]:
    result = await CustomerService(session).list_for_admin(
        query=q, blocked=blocked, sort=sort, page=page, page_size=page_size
    )
    return Page.build(result, AdminCustomerOut.build)


@router.get("/customers/{customer_id}", response_model=AdminCustomerOut, tags=["admin: customers"])
async def get_customer(
    customer_id: uuid.UUID, _: ViewCustomers, session: SessionDep
) -> AdminCustomerOut:
    return AdminCustomerOut.build(await CustomerService(session).stats_for(customer_id))


@router.patch(
    "/customers/{customer_id}", response_model=AdminCustomerOut, tags=["admin: customers"]
)
async def update_customer(
    customer_id: uuid.UUID, body: CustomerUpdateIn, ctx: ManageCustomers, session: SessionDep
) -> AdminCustomerOut:
    service = CustomerService(session)
    await service.set_blocked(customer_id, body.is_blocked, admin_user_id=ctx.id)
    return AdminCustomerOut.build(await service.stats_for(customer_id))
