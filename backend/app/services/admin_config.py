"""Staff-managed configuration: promo codes, delivery, staff accounts, store settings."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.money import money
from app.core.security import hash_password
from app.models import (
    AdminUser,
    DeliveryMethod,
    DeliveryRate,
    District,
    PromoCode,
    PromoCodeRedemption,
    Region,
    Role,
    StoreSetting,
)
from app.models.enums import AdminRoleName, DeliveryMethodKind, DiscountType, DistrictKind
from app.services.audit import diff, record_audit
from app.services.auth import revoke_all_sessions
from app.services.catalog import Page
from app.services.promo import normalize_code

MIN_PASSWORD_LENGTH = 10


def _audit_json(values: dict[str, Any]) -> dict[str, Any]:
    return {
        k: str(v) if isinstance(v, Decimal | datetime | uuid.UUID) else v for k, v in values.items()
    }


# --- Promo codes ----------------------------------------------------------------------


class PromoAdminService:
    FIELDS = (
        "code",
        "description",
        "discount_type",
        "value",
        "max_discount",
        "min_order_amount",
        "starts_at",
        "ends_at",
        "usage_limit",
        "per_user_limit",
        "is_active",
    )

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, promo_id: uuid.UUID) -> PromoCode:
        promo = await self.session.get(PromoCode, promo_id, populate_existing=True)
        if promo is None:
            raise NotFoundError("Promokod topilmadi.")
        return promo

    async def list(
        self, *, query: str | None, is_active: bool | None, page: int, page_size: int
    ) -> Page[PromoCode]:
        stmt = select(PromoCode)
        if query:
            stmt = stmt.where(PromoCode.code.ilike(f"%{normalize_code(query)}%"))
        if is_active is not None:
            stmt = stmt.where(PromoCode.is_active == is_active)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = await self.session.scalars(
            stmt.order_by(PromoCode.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return Page(items=list(items), total=total, page=page, page_size=page_size)

    @staticmethod
    def _validate(values: dict[str, Any]) -> None:
        code = values["code"]
        if not code or len(code) > 32 or not code.replace("-", "").replace("_", "").isalnum():
            raise BusinessRuleError(
                "Promokod faqat harf, raqam, «-» va «_» dan iborat bo‘lsin (32 belgigacha).",
                code="invalid_promo_code",
            )
        if values["value"] is None or values["value"] <= 0:
            raise BusinessRuleError("Chegirma miqdori musbat bo‘lsin.", code="invalid_value")
        if values["discount_type"] is DiscountType.PERCENT and values["value"] > 100:
            raise BusinessRuleError("Foiz 100 dan oshmasin.", code="invalid_value")
        if (
            values.get("ends_at")
            and values.get("starts_at")
            and values["ends_at"] <= values["starts_at"]
        ):
            raise BusinessRuleError(
                "Tugash sanasi boshlanishidan keyin bo‘lsin.", code="invalid_period"
            )

    async def create(self, values: dict[str, Any], *, admin_user_id: uuid.UUID) -> PromoCode:
        values = {k: v for k, v in values.items() if k in self.FIELDS}
        values["code"] = normalize_code(values["code"])
        values.setdefault("min_order_amount", Decimal("0"))
        self._validate({**values, "starts_at": values.get("starts_at")})
        if await self.session.scalar(select(PromoCode.id).where(PromoCode.code == values["code"])):
            raise ConflictError("Bunday promokod allaqachon mavjud.", code="duplicate_promo_code")
        if values.get("starts_at") is None:
            values.pop("starts_at", None)
        promo = PromoCode(**values)
        self.session.add(promo)
        await self.session.flush()
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="promo.create",
            entity_type="promo_code",
            entity_id=promo.id,
            changes=_audit_json(values),
        )
        await self.session.commit()
        return await self.get(promo.id)

    async def update(
        self, promo_id: uuid.UUID, changes: dict[str, Any], *, admin_user_id: uuid.UUID
    ) -> PromoCode:
        promo = await self.get(promo_id)
        before = {k: getattr(promo, k) for k in self.FIELDS}
        if "code" in changes:
            changes["code"] = normalize_code(changes["code"])
            if changes["code"] != promo.code and await self.session.scalar(
                select(PromoCode.id).where(PromoCode.code == changes["code"])
            ):
                raise ConflictError(
                    "Bunday promokod allaqachon mavjud.", code="duplicate_promo_code"
                )
        merged = {**before, **{k: v for k, v in changes.items() if k in self.FIELDS}}
        self._validate(merged)
        for k in self.FIELDS:
            if k in changes:
                setattr(promo, k, changes[k])
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="promo.update",
            entity_type="promo_code",
            entity_id=promo.id,
            changes=diff(before, {k: getattr(promo, k) for k in self.FIELDS}),
        )
        await self.session.commit()
        return await self.get(promo.id)

    async def delete(self, promo_id: uuid.UUID, *, admin_user_id: uuid.UUID) -> bool:
        """Delete an unused code; a code that was used is only deactivated (history).
        Returns True if it was deleted."""
        promo = await self.get(promo_id)
        used = await self.session.scalar(
            select(func.count()).where(PromoCodeRedemption.promo_code_id == promo.id)
        )
        if used:
            promo.is_active = False
            action = "promo.deactivate"
        else:
            await self.session.delete(promo)
            action = "promo.delete"
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action=action,
            entity_type="promo_code",
            entity_id=promo_id,
            changes={"code": promo.code},
        )
        await self.session.commit()
        return not used


# --- Delivery configuration -----------------------------------------------------------


class DeliveryAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def regions(self) -> list[tuple[Region, int]]:
        counts = (
            select(District.region_id, func.count().label("n"))
            .group_by(District.region_id)
            .subquery()
        )
        rows = await self.session.execute(
            select(Region, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.region_id == Region.id)
            .order_by(Region.sort_order, Region.name)
        )
        return [(r, int(n)) for r, n in rows]

    async def update_region(
        self, region_id: int, changes: dict[str, Any], *, admin_user_id: uuid.UUID
    ) -> Region:
        region = await self.session.get(Region, region_id)
        if region is None:
            raise NotFoundError("Hudud topilmadi.")
        keys = ("name", "sort_order", "is_active")
        before = {k: getattr(region, k) for k in keys}
        for k in keys:
            if k in changes:
                setattr(region, k, changes[k])
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="region.update",
            entity_type="region",
            entity_id=region.id,
            changes=diff(before, {k: getattr(region, k) for k in keys}),
        )
        await self.session.commit()
        return region

    async def districts(self, region_id: int, *, include_inactive: bool = True) -> list[District]:
        if await self.session.get(Region, region_id) is None:
            raise NotFoundError("Hudud topilmadi.")
        stmt = select(District).where(District.region_id == region_id)
        if not include_inactive:
            stmt = stmt.where(District.is_active)
        return list(await self.session.scalars(stmt.order_by(District.sort_order, District.name)))

    async def create_district(
        self,
        region_id: int,
        *,
        name: str,
        kind: DistrictKind,
        sort_order: int,
        admin_user_id: uuid.UUID,
    ) -> District:
        region = await self.session.get(Region, region_id)
        if region is None:
            raise NotFoundError("Hudud topilmadi.")
        name = " ".join(name.split())[:100]
        if not name:
            raise BusinessRuleError("Nomini kiriting.", code="name_required")
        if await self.session.scalar(
            select(District.id).where(District.region_id == region_id, District.name == name)
        ):
            raise ConflictError("Bu hududda bunday tuman/shahar bor.", code="duplicate_district")
        count = (
            await self.session.scalar(select(func.count()).where(District.region_id == region_id))
            or 0
        )
        district = District(
            region_id=region_id,
            name=name,
            kind=kind,
            sort_order=sort_order,
            code=f"{region.code}-X{count + 1:02d}-{uuid.uuid4().hex[:4]}",
        )
        self.session.add(district)
        await self.session.flush()
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="district.create",
            entity_type="district",
            entity_id=district.id,
            changes={"name": name},
        )
        await self.session.commit()
        return district

    async def update_district(
        self, district_id: int, changes: dict[str, Any], *, admin_user_id: uuid.UUID
    ) -> District:
        district = await self.session.get(District, district_id)
        if district is None:
            raise NotFoundError("Tuman/shahar topilmadi.")
        keys = ("name", "kind", "sort_order", "is_active")
        before = {k: getattr(district, k) for k in keys}
        for k in keys:
            if k in changes:
                setattr(district, k, changes[k])
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="district.update",
            entity_type="district",
            entity_id=district.id,
            changes=diff(before, {k: getattr(district, k) for k in keys}),
        )
        await self.session.commit()
        return district

    async def methods(self) -> list[DeliveryMethod]:
        return list(
            await self.session.scalars(select(DeliveryMethod).order_by(DeliveryMethod.sort_order))
        )

    async def create_method(
        self,
        *,
        code: str,
        kind: DeliveryMethodKind,
        name: str,
        description: str | None,
        sort_order: int,
        is_active: bool,
        admin_user_id: uuid.UUID,
    ) -> DeliveryMethod:
        code = code.strip().lower()
        if not code or not code.replace("_", "").isalnum():
            raise BusinessRuleError(
                "Kod faqat lotin harf, raqam va «_» dan iborat bo‘lsin.", code="invalid_code"
            )
        if await self.session.scalar(select(DeliveryMethod.id).where(DeliveryMethod.code == code)):
            raise ConflictError("Bunday kodli usul bor.", code="duplicate_method")
        method = DeliveryMethod(
            code=code,
            kind=kind,
            name=name.strip()[:100],
            description=(description or "").strip() or None,
            sort_order=sort_order,
            is_active=is_active,
        )
        self.session.add(method)
        await self.session.flush()
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="delivery_method.create",
            entity_type="delivery_method",
            entity_id=method.id,
            changes={"code": code},
        )
        await self.session.commit()
        return method

    async def update_method(
        self, method_id: uuid.UUID, changes: dict[str, Any], *, admin_user_id: uuid.UUID
    ) -> DeliveryMethod:
        method = await self.session.get(DeliveryMethod, method_id)
        if method is None:
            raise NotFoundError("Yetkazib berish usuli topilmadi.")
        keys = ("name", "description", "kind", "sort_order", "is_active")
        before = {k: getattr(method, k) for k in keys}
        for k in keys:
            if k in changes:
                setattr(method, k, changes[k])
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="delivery_method.update",
            entity_type="delivery_method",
            entity_id=method.id,
            changes=diff(before, {k: getattr(method, k) for k in keys}),
        )
        await self.session.commit()
        return method

    async def rates(
        self, *, method_id: uuid.UUID | None, region_id: int | None
    ) -> list[DeliveryRate]:
        stmt = select(DeliveryRate).options(
            selectinload(DeliveryRate.method),
            selectinload(DeliveryRate.region),
            selectinload(DeliveryRate.district),
        )
        if method_id is not None:
            stmt = stmt.where(DeliveryRate.method_id == method_id)
        if region_id is not None:
            stmt = stmt.where(DeliveryRate.region_id == region_id)
        return list(
            await self.session.scalars(
                stmt.order_by(DeliveryRate.region_id, DeliveryRate.district_id)
            )
        )

    async def _get_rate(self, rate_id: uuid.UUID) -> DeliveryRate:
        rate = await self.session.scalar(
            select(DeliveryRate)
            .where(DeliveryRate.id == rate_id)
            .options(
                selectinload(DeliveryRate.method),
                selectinload(DeliveryRate.region),
                selectinload(DeliveryRate.district),
            )
            .execution_options(populate_existing=True)
        )
        if rate is None:
            raise NotFoundError("Tarif topilmadi.")
        return rate

    @staticmethod
    def _validate_rate(values: dict[str, Any]) -> None:
        if values["price"] < 0:
            raise BusinessRuleError("Narx manfiy bo‘lmasin.", code="invalid_price")
        if values.get("free_threshold") is not None and values["free_threshold"] <= 0:
            raise BusinessRuleError(
                "Bepul yetkazish chegarasi musbat bo‘lsin.", code="invalid_threshold"
            )
        if not 0 <= values["eta_min_days"] <= values["eta_max_days"]:
            raise BusinessRuleError("Yetkazish muddati noto‘g‘ri.", code="invalid_eta")

    async def create_rate(
        self, values: dict[str, Any], *, admin_user_id: uuid.UUID
    ) -> DeliveryRate:
        if await self.session.get(DeliveryMethod, values["method_id"]) is None:
            raise NotFoundError("Yetkazib berish usuli topilmadi.")
        if await self.session.get(Region, values["region_id"]) is None:
            raise NotFoundError("Hudud topilmadi.")
        if values.get("district_id") is not None:
            district = await self.session.get(District, values["district_id"])
            if district is None or district.region_id != values["region_id"]:
                raise BusinessRuleError(
                    "Tuman tanlangan hududga tegishli emas.", code="district_mismatch"
                )
        values.setdefault("eta_min_days", 1)
        values.setdefault("eta_max_days", 3)
        self._validate_rate(values)
        exists = await self.session.scalar(
            select(DeliveryRate.id).where(
                DeliveryRate.method_id == values["method_id"],
                DeliveryRate.region_id == values["region_id"],
                DeliveryRate.district_id.is_(None)
                if values.get("district_id") is None
                else DeliveryRate.district_id == values["district_id"],
            )
        )
        if exists:
            raise ConflictError(
                "Bu hudud uchun tarif allaqachon bor. Uni tahrirlang.", code="duplicate_rate"
            )
        values["price"] = money(values["price"])
        rate = DeliveryRate(**values)
        self.session.add(rate)
        await self.session.flush()
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="delivery_rate.create",
            entity_type="delivery_rate",
            entity_id=rate.id,
            changes=_audit_json(values),
        )
        await self.session.commit()
        return await self._get_rate(rate.id)

    async def update_rate(
        self, rate_id: uuid.UUID, changes: dict[str, Any], *, admin_user_id: uuid.UUID
    ) -> DeliveryRate:
        rate = await self._get_rate(rate_id)
        keys = (
            "price",
            "free_threshold",
            "eta_min_days",
            "eta_max_days",
            "pickup_address",
            "is_active",
        )
        before = {k: getattr(rate, k) for k in keys}
        merged = {**before, **{k: v for k, v in changes.items() if k in keys}}
        self._validate_rate(merged)
        for k in keys:
            if k in changes:
                setattr(rate, k, changes[k])
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="delivery_rate.update",
            entity_type="delivery_rate",
            entity_id=rate.id,
            changes=diff(before, {k: getattr(rate, k) for k in keys}),
        )
        await self.session.commit()
        return await self._get_rate(rate.id)

    async def delete_rate(self, rate_id: uuid.UUID, *, admin_user_id: uuid.UUID) -> None:
        rate = await self._get_rate(rate_id)
        await self.session.delete(rate)
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="delivery_rate.delete",
            entity_type="delivery_rate",
            entity_id=rate_id,
        )
        await self.session.commit()


# --- Staff ----------------------------------------------------------------------------


class StaffService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def roles(self) -> list[Role]:
        return list(await self.session.scalars(select(Role).order_by(Role.id)))

    async def _role(self, name: AdminRoleName) -> Role:
        role = await self.session.scalar(select(Role).where(Role.name == name.value))
        if role is None:
            raise NotFoundError("Rol topilmadi.")
        return role

    async def get(self, admin_id: uuid.UUID) -> AdminUser:
        admin = await self.session.get(AdminUser, admin_id, populate_existing=True)
        if admin is None:
            raise NotFoundError("Xodim topilmadi.")
        return admin

    async def list(self) -> list[AdminUser]:
        return list(await self.session.scalars(select(AdminUser).order_by(AdminUser.created_at)))

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise BusinessRuleError(
                f"Parol kamida {MIN_PASSWORD_LENGTH} belgidan iborat bo‘lsin.", code="weak_password"
            )

    async def create(
        self,
        *,
        email: str,
        full_name: str,
        password: str,
        role: AdminRoleName,
        telegram_id: int | None = None,
        created_by: uuid.UUID | None,
    ) -> AdminUser:
        email = email.strip().lower()
        if "@" not in email:
            raise BusinessRuleError("Email noto‘g‘ri.", code="invalid_email")
        self._check_password(password)
        if await self.session.scalar(
            select(AdminUser.id).where(func.lower(AdminUser.email) == email)
        ):
            raise ConflictError("Bu email bilan xodim allaqachon bor.", code="duplicate_email")
        admin = AdminUser(
            email=email,
            full_name=full_name.strip()[:128] or email,
            password_hash=hash_password(password),
            role_id=(await self._role(role)).id,
            telegram_id=telegram_id,
        )
        self.session.add(admin)
        await self.session.flush()
        record_audit(
            self.session,
            admin_user_id=created_by,
            action="staff.create",
            entity_type="admin_user",
            entity_id=admin.id,
            changes={"email": email, "role": role.value},
        )
        await self.session.commit()
        return await self.get(admin.id)

    async def _active_super_admins(self) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(AdminUser)
                .join(Role, Role.id == AdminUser.role_id)
                .where(Role.name == AdminRoleName.SUPER_ADMIN.value, AdminUser.is_active)
            )
            or 0
        )

    async def update(
        self, admin_id: uuid.UUID, changes: dict[str, Any], *, actor_id: uuid.UUID
    ) -> AdminUser:
        admin = await self.get(admin_id)
        was_super = admin.role.name == AdminRoleName.SUPER_ADMIN.value
        audit: dict[str, Any] = {}
        revoke = False
        if "role" in changes and changes["role"] is not None:
            new_role = await self._role(AdminRoleName(changes["role"]))
            if (
                was_super
                and new_role.name != AdminRoleName.SUPER_ADMIN.value
                and admin.is_active
                and await self._active_super_admins() <= 1
            ):
                raise BusinessRuleError(
                    "Oxirgi bosh administratorning rolini o‘zgartirib bo‘lmaydi.",
                    code="last_super_admin",
                )
            audit["role"] = {"from": admin.role.name, "to": new_role.name}
            admin.role_id = new_role.id
            revoke = True
        if (
            "is_active" in changes
            and changes["is_active"] is not None
            and changes["is_active"] != admin.is_active
        ):
            if not changes["is_active"]:
                if admin.id == actor_id:
                    raise BusinessRuleError(
                        "O‘zingizni faolsizlantira olmaysiz.", code="self_deactivate"
                    )
                if was_super and await self._active_super_admins() <= 1:
                    raise BusinessRuleError(
                        "Oxirgi bosh administratorni o‘chirib bo‘lmaydi.", code="last_super_admin"
                    )
                revoke = True
            audit["is_active"] = {"from": admin.is_active, "to": changes["is_active"]}
            admin.is_active = changes["is_active"]
        if changes.get("full_name"):
            admin.full_name = str(changes["full_name"]).strip()[:128]
            audit["full_name"] = admin.full_name
        if "telegram_id" in changes:
            admin.telegram_id = changes["telegram_id"]
            audit["telegram_id"] = changes["telegram_id"]
        if changes.get("password"):
            self._check_password(changes["password"])
            admin.password_hash = hash_password(changes["password"])
            audit["password"] = "changed"  # noqa: S105 - audit marker, not a secret
            revoke = True
        if revoke:
            await revoke_all_sessions(self.session, admin.id)
        record_audit(
            self.session,
            admin_user_id=actor_id,
            action="staff.update",
            entity_type="admin_user",
            entity_id=admin.id,
            changes=audit,
        )
        await self.session.commit()
        return await self.get(admin.id)


# --- Store settings -------------------------------------------------------------------


def _optional_money(value: Any) -> Any:
    if value is None or value == "":
        return None
    amount = Decimal(str(value))
    if amount <= 0:
        raise ValueError
    return int(amount)


def _non_negative_int(value: Any) -> int:
    n = int(value)
    if n < 0:
        raise ValueError
    return n


def _optional_text(max_len: int):  # type: ignore[no-untyped-def]
    def parse(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if len(text) > max_len:
            raise ValueError
        return text or None

    return parse


def _required_text(max_len: int):  # type: ignore[no-untyped-def]
    def parse(value: Any) -> str:
        text = _optional_text(max_len)(value)
        if not text:
            raise ValueError
        return text

    return parse


def _telegram_username(value: Any) -> str | None:
    text = _optional_text(64)(value)
    if text is None:
        return None
    text = text.lstrip("@")
    if not (5 <= len(text) <= 32 and text.replace("_", "").isalnum()):
        raise ValueError
    return text


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError


SETTING_PARSERS = {
    "store.name": _required_text(100),
    "store.phone": _optional_text(32),
    "store.address": _optional_text(255),
    "store.support_telegram": _telegram_username,
    "store.currency_display": _required_text(16),
    "delivery.free_threshold": _optional_money,
    "inventory.low_stock_threshold": _non_negative_int,
    "payments.click_enabled": _bool,
    "payments.payme_enabled": _bool,
    "payments.cash_on_delivery_enabled": _bool,
    "notifications.new_order_to_staff": _bool,
    "notifications.low_stock_to_staff": _bool,
}

PUBLIC_SETTINGS = (
    "store.name",
    "store.phone",
    "store.address",
    "store.support_telegram",
    "store.currency_display",
)


class SettingsAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def all(self) -> list[StoreSetting]:
        return list(await self.session.scalars(select(StoreSetting).order_by(StoreSetting.key)))

    async def values(self, keys: tuple[str, ...] | None = None) -> dict[str, Any]:
        stmt = select(StoreSetting)
        if keys:
            stmt = stmt.where(StoreSetting.key.in_(keys))
        return {s.key: s.value.get("value") for s in await self.session.scalars(stmt)}

    async def update(self, changes: dict[str, Any], *, admin_user_id: uuid.UUID) -> dict[str, Any]:
        unknown = set(changes) - set(SETTING_PARSERS)
        if unknown:
            raise BusinessRuleError(
                "Noma’lum sozlama.", code="unknown_setting", details={"keys": sorted(unknown)}
            )
        parsed: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for key, value in changes.items():
            try:
                parsed[key] = SETTING_PARSERS[key](value)
            except (ValueError, TypeError, ArithmeticError):
                errors[key] = "Qiymat noto‘g‘ri."
        if errors:
            raise BusinessRuleError(
                "Sozlamalarda xato bor.", code="invalid_settings", details=errors
            )
        rows = {
            s.key: s
            for s in await self.session.scalars(
                select(StoreSetting).where(StoreSetting.key.in_(parsed))
            )
        }
        audit: dict[str, Any] = {}
        for key, value in parsed.items():
            row = rows.get(key)
            if row is None:
                row = StoreSetting(key=key, value={"value": value})
                self.session.add(row)
                audit[key] = {"from": None, "to": value}
            else:
                audit[key] = {"from": row.value.get("value"), "to": value}
                row.value = {"value": value}
            row.updated_by_admin_id = admin_user_id
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="settings.update",
            entity_type="store_settings",
            changes=audit,
        )
        await self.session.commit()
        return await self.values()
