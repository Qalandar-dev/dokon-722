"""Domain enumerations shared by models, schemas and services.

Allowed transitions between statuses are defined in the service layer (Phase 4),
not here.
"""

from enum import StrEnum


class AdminRoleName(StrEnum):
    SUPER_ADMIN = "super_admin"
    MANAGER = "manager"
    OPERATOR = "operator"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class DeliveryStatus(StrEnum):
    AWAITING_DISPATCH = "awaiting_dispatch"
    PREPARING = "preparing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    RETURNED = "returned"


class PaymentMethod(StrEnum):
    CLICK = "click"
    PAYME = "payme"
    # Cash/card to the courier. Present in the schema; enabled only via store settings.
    CASH_ON_DELIVERY = "cash_on_delivery"


class PaymentProvider(StrEnum):
    CLICK = "click"
    PAYME = "payme"
    CASH = "cash"
    MOCK = "mock"


class DeliveryMethodKind(StrEnum):
    COURIER = "courier"
    PICKUP = "pickup"
    POSTAL = "postal"


class DistrictKind(StrEnum):
    DISTRICT = "district"  # tuman
    CITY = "city"  # shahar


class InventoryMovementType(StrEnum):
    RESTOCK = "restock"
    ADJUSTMENT = "adjustment"
    RESERVE = "reserve"
    RELEASE = "release"
    SALE = "sale"
    RETURN = "return"


class DiscountType(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


class StatusField(StrEnum):
    STATUS = "status"
    PAYMENT_STATUS = "payment_status"
    DELIVERY_STATUS = "delivery_status"


class ActorType(StrEnum):
    ADMIN = "admin"
    CUSTOMER = "customer"
    SYSTEM = "system"
    PROVIDER = "provider"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
