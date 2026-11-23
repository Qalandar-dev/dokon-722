from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import AdminContext, SessionDep, require
from app.core.permissions import Permission
from app.models import AuditLog
from app.models.enums import AdminRoleName
from app.schemas.admin import (
    AdminDistrictOut,
    AdminRegionOut,
    AuditLogOut,
    DeliveryMethodIn,
    DeliveryMethodOut,
    DeliveryMethodUpdateIn,
    DeliveryRateIn,
    DeliveryRateOut,
    DeliveryRateUpdateIn,
    DistrictIn,
    DistrictUpdateIn,
    PromoIn,
    PromoOut,
    PromoUpdateIn,
    RegionUpdateIn,
    RoleOut,
    StaffIn,
    StaffOut,
    StaffUpdateIn,
    audit_out,
    district_admin_out,
    method_out,
    promo_out,
)
from app.schemas.common import Page
from app.services.admin_config import (
    DeliveryAdminService,
    PromoAdminService,
    SettingsAdminService,
    StaffService,
)
from app.services.catalog import Page as ServicePage

router = APIRouter(prefix="/admin")

ManagePromo = Annotated[AdminContext, Depends(require(Permission.PROMO_MANAGE))]
ManageDelivery = Annotated[AdminContext, Depends(require(Permission.DELIVERY_MANAGE))]
ManageStaff = Annotated[AdminContext, Depends(require(Permission.STAFF_MANAGE))]
ManageSettings = Annotated[AdminContext, Depends(require(Permission.SETTINGS_MANAGE))]
ViewAudit = Annotated[AdminContext, Depends(require(Permission.AUDIT_VIEW))]

# --- Promo codes -------------------------------------------------------------------------


@router.get("/promo-codes", response_model=Page[PromoOut], tags=["admin: promo"])
async def list_promos(
    _: ManagePromo,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=32)] = None,
    is_active: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PromoOut]:
    result = await PromoAdminService(session).list(
        query=q, is_active=is_active, page=page, page_size=page_size
    )
    return Page.build(result, promo_out)


@router.post(
    "/promo-codes",
    response_model=PromoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: promo"],
)
async def create_promo(body: PromoIn, ctx: ManagePromo, session: SessionDep) -> PromoOut:
    return promo_out(
        await PromoAdminService(session).create(body.model_dump(), admin_user_id=ctx.id)
    )


@router.get("/promo-codes/{promo_id}", response_model=PromoOut, tags=["admin: promo"])
async def get_promo(promo_id: uuid.UUID, _: ManagePromo, session: SessionDep) -> PromoOut:
    return promo_out(await PromoAdminService(session).get(promo_id))


@router.patch("/promo-codes/{promo_id}", response_model=PromoOut, tags=["admin: promo"])
async def update_promo(
    promo_id: uuid.UUID, body: PromoUpdateIn, ctx: ManagePromo, session: SessionDep
) -> PromoOut:
    promo = await PromoAdminService(session).update(
        promo_id, body.model_dump(exclude_unset=True), admin_user_id=ctx.id
    )
    return promo_out(promo)


@router.delete("/promo-codes/{promo_id}", tags=["admin: promo"])
async def delete_promo(
    promo_id: uuid.UUID, ctx: ManagePromo, session: SessionDep
) -> dict[str, bool]:
    """Deletes an unused code; a code that has been used is deactivated instead."""
    deleted = await PromoAdminService(session).delete(promo_id, admin_user_id=ctx.id)
    return {"deleted": deleted, "deactivated": not deleted}


# --- Delivery ----------------------------------------------------------------------------


@router.get("/regions", response_model=list[AdminRegionOut], tags=["admin: delivery"])
async def list_regions(_: ManageDelivery, session: SessionDep) -> list[AdminRegionOut]:
    return [AdminRegionOut.build(r, n) for r, n in await DeliveryAdminService(session).regions()]


@router.patch("/regions/{region_id}", response_model=AdminRegionOut, tags=["admin: delivery"])
async def update_region(
    region_id: int, body: RegionUpdateIn, ctx: ManageDelivery, session: SessionDep
) -> AdminRegionOut:
    service = DeliveryAdminService(session)
    await service.update_region(
        region_id, body.model_dump(exclude_unset=True), admin_user_id=ctx.id
    )
    region, count = next((r, n) for r, n in await service.regions() if r.id == region_id)
    return AdminRegionOut.build(region, count)


@router.get(
    "/regions/{region_id}/districts",
    response_model=list[AdminDistrictOut],
    tags=["admin: delivery"],
)
async def list_districts(
    region_id: int, _: ManageDelivery, session: SessionDep
) -> list[AdminDistrictOut]:
    return [district_admin_out(d) for d in await DeliveryAdminService(session).districts(region_id)]


@router.post(
    "/regions/{region_id}/districts",
    response_model=AdminDistrictOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: delivery"],
)
async def create_district(
    region_id: int, body: DistrictIn, ctx: ManageDelivery, session: SessionDep
) -> AdminDistrictOut:
    district = await DeliveryAdminService(session).create_district(
        region_id, admin_user_id=ctx.id, **body.model_dump()
    )
    return district_admin_out(district)


@router.patch("/districts/{district_id}", response_model=AdminDistrictOut, tags=["admin: delivery"])
async def update_district(
    district_id: int, body: DistrictUpdateIn, ctx: ManageDelivery, session: SessionDep
) -> AdminDistrictOut:
    district = await DeliveryAdminService(session).update_district(
        district_id, body.model_dump(exclude_unset=True), admin_user_id=ctx.id
    )
    return district_admin_out(district)


@router.get("/delivery-methods", response_model=list[DeliveryMethodOut], tags=["admin: delivery"])
async def list_methods(_: ManageDelivery, session: SessionDep) -> list[DeliveryMethodOut]:
    return [method_out(m) for m in await DeliveryAdminService(session).methods()]


@router.post(
    "/delivery-methods",
    response_model=DeliveryMethodOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: delivery"],
)
async def create_method(
    body: DeliveryMethodIn, ctx: ManageDelivery, session: SessionDep
) -> DeliveryMethodOut:
    method = await DeliveryAdminService(session).create_method(
        admin_user_id=ctx.id, **body.model_dump()
    )
    return method_out(method)


@router.patch(
    "/delivery-methods/{method_id}", response_model=DeliveryMethodOut, tags=["admin: delivery"]
)
async def update_method(
    method_id: uuid.UUID, body: DeliveryMethodUpdateIn, ctx: ManageDelivery, session: SessionDep
) -> DeliveryMethodOut:
    method = await DeliveryAdminService(session).update_method(
        method_id, body.model_dump(exclude_unset=True), admin_user_id=ctx.id
    )
    return method_out(method)


@router.get("/delivery-rates", response_model=list[DeliveryRateOut], tags=["admin: delivery"])
async def list_rates(
    _: ManageDelivery,
    session: SessionDep,
    method_id: uuid.UUID | None = None,
    region_id: int | None = None,
) -> list[DeliveryRateOut]:
    rates = await DeliveryAdminService(session).rates(method_id=method_id, region_id=region_id)
    return [DeliveryRateOut.build(r) for r in rates]


@router.post(
    "/delivery-rates",
    response_model=DeliveryRateOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: delivery"],
)
async def create_rate(
    body: DeliveryRateIn, ctx: ManageDelivery, session: SessionDep
) -> DeliveryRateOut:
    rate = await DeliveryAdminService(session).create_rate(body.model_dump(), admin_user_id=ctx.id)
    return DeliveryRateOut.build(rate)


@router.patch("/delivery-rates/{rate_id}", response_model=DeliveryRateOut, tags=["admin: delivery"])
async def update_rate(
    rate_id: uuid.UUID, body: DeliveryRateUpdateIn, ctx: ManageDelivery, session: SessionDep
) -> DeliveryRateOut:
    rate = await DeliveryAdminService(session).update_rate(
        rate_id, body.model_dump(exclude_unset=True), admin_user_id=ctx.id
    )
    return DeliveryRateOut.build(rate)


@router.delete(
    "/delivery-rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["admin: delivery"]
)
async def delete_rate(rate_id: uuid.UUID, ctx: ManageDelivery, session: SessionDep) -> Response:
    await DeliveryAdminService(session).delete_rate(rate_id, admin_user_id=ctx.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Staff -------------------------------------------------------------------------------


@router.get("/roles", response_model=list[RoleOut], tags=["admin: staff"])
async def list_roles(_: ManageStaff, session: SessionDep) -> list[RoleOut]:
    return [RoleOut.model_validate(r) for r in await StaffService(session).roles()]


@router.get("/staff", response_model=list[StaffOut], tags=["admin: staff"])
async def list_staff(_: ManageStaff, session: SessionDep) -> list[StaffOut]:
    return [StaffOut.build(a) for a in await StaffService(session).list()]


@router.post(
    "/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED, tags=["admin: staff"]
)
async def create_staff(body: StaffIn, ctx: ManageStaff, session: SessionDep) -> StaffOut:
    admin = await StaffService(session).create(
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        role=AdminRoleName(body.role),
        telegram_id=body.telegram_id,
        created_by=ctx.id,
    )
    return StaffOut.build(admin)


@router.patch("/staff/{admin_id}", response_model=StaffOut, tags=["admin: staff"])
async def update_staff(
    admin_id: uuid.UUID, body: StaffUpdateIn, ctx: ManageStaff, session: SessionDep
) -> StaffOut:
    admin = await StaffService(session).update(
        admin_id, body.model_dump(exclude_unset=True), actor_id=ctx.id
    )
    return StaffOut.build(admin)


@router.get("/audit-logs", response_model=Page[AuditLogOut], tags=["admin: staff"])
async def audit_logs(
    _: ViewAudit,
    session: SessionDep,
    admin_user_id: uuid.UUID | None = None,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[AuditLogOut]:
    stmt = select(AuditLog)
    if admin_user_id is not None:
        stmt = stmt.where(AuditLog.admin_user_id == admin_user_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page.build(ServicePage(list(rows), total, page, page_size), audit_out)


# --- Settings ----------------------------------------------------------------------------


@router.get("/settings", tags=["admin: settings"])
async def get_settings(_: ManageSettings, session: SessionDep) -> dict[str, Any]:
    return await SettingsAdminService(session).values()


@router.patch("/settings", tags=["admin: settings"])
async def update_settings(
    ctx: ManageSettings,
    session: SessionDep,
    changes: Annotated[dict[str, Any], Body(examples=[{"delivery.free_threshold": 500000}])],
) -> dict[str, Any]:
    return await SettingsAdminService(session).update(changes, admin_user_id=ctx.id)
