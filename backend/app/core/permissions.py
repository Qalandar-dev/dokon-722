"""Permission codes. Roles store lists of these (seeded in migration 7642bc13bed8).

The backend checks permissions on every admin endpoint; the admin panel only uses
them to hide buttons.
"""

from enum import StrEnum


class Permission(StrEnum):
    DASHBOARD_VIEW = "dashboard.view"
    REPORTS_VIEW = "reports.view"
    PRODUCTS_VIEW = "products.view"
    PRODUCTS_MANAGE = "products.manage"
    CATEGORIES_MANAGE = "categories.manage"
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_MANAGE = "inventory.manage"
    ORDERS_VIEW = "orders.view"
    ORDERS_MANAGE = "orders.manage"
    ORDERS_REFUND = "orders.refund"
    CUSTOMERS_VIEW = "customers.view"
    CUSTOMERS_MANAGE = "customers.manage"
    PROMO_MANAGE = "promo.manage"
    DELIVERY_MANAGE = "delivery.manage"
    STAFF_MANAGE = "staff.manage"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_VIEW = "audit.view"
