"""ORM models. Every model module must be imported here so Alembic sees it."""

from app.models.admin import AdminSession, AdminUser, Role
from app.models.cart import Cart, CartItem
from app.models.catalog import Category, Product, ProductImage, ProductVariant, Review
from app.models.customer import Address, User
from app.models.delivery import DeliveryMethod, DeliveryRate, District, Region
from app.models.inventory import Inventory, InventoryMovement
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.payment import Payment, PaymentTransaction
from app.models.promo import PromoCode, PromoCodeRedemption
from app.models.system import AuditLog, Notification, StoreSetting

__all__ = [
    "Address",
    "AdminSession",
    "AdminUser",
    "AuditLog",
    "Cart",
    "CartItem",
    "Category",
    "DeliveryMethod",
    "DeliveryRate",
    "District",
    "Inventory",
    "InventoryMovement",
    "Notification",
    "Order",
    "OrderItem",
    "OrderStatusHistory",
    "Payment",
    "PaymentTransaction",
    "Product",
    "ProductImage",
    "ProductVariant",
    "PromoCode",
    "PromoCodeRedemption",
    "Region",
    "Review",
    "Role",
    "StoreSetting",
    "User",
]
