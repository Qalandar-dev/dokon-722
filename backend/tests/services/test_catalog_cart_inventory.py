import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleError,
    InsufficientStockError,
    NotFoundError,
    PromoCodeError,
)
from app.models import Inventory, InventoryMovement, Product, ProductVariant, PromoCode
from app.models.enums import DiscountType, InventoryMovementType
from app.repositories.products import ProductFilters, ProductSort
from app.services.cart import CartService
from app.services.catalog import CatalogService
from app.services.inventory import InventoryService, StockLine
from tests.factories import make_category, make_order, make_user, make_variant


async def _product(
    db: AsyncSession,
    name: str,
    *,
    category_id: uuid.UUID,
    price: str,
    stock: int = 5,
    discount: str | None = None,
    sold: int = 0,
) -> Product:
    product = Product(
        category_id=category_id, name=name, slug=f"{uuid.uuid4().hex}", sold_count=sold
    )
    db.add(product)
    await db.flush()
    await make_variant(
        db,
        product=product,
        price=price,
        stock=stock,
        discount_price=Decimal(discount) if discount else None,
    )
    return product


# --- Catalog ---------------------------------------------------------------------------


async def test_category_filter_includes_subcategories(db: AsyncSession) -> None:
    clothes = await make_category(db, name="Kiyim")
    men = await make_category(db, name="Erkaklar", parent_id=clothes.id)
    other = await make_category(db, name="Elektronika")
    shirt = await _product(db, "Ko‘ylak", category_id=men.id, price="150000")
    await _product(db, "Telefon", category_id=other.id, price="3000000")

    page = await CatalogService(db).list_products(ProductFilters(category_id=clothes.id))
    assert [c.product.id for c in page.items] == [shirt.id]
    assert page.total == 1


async def test_search_by_name_and_exact_sku(db: AsyncSession) -> None:
    cat = await make_category(db)
    phone = await _product(db, "Samsung Galaxy A55 smartfon", category_id=cat.id, price="4500000")
    await _product(db, "Choynak", category_id=cat.id, price="90000")
    service = CatalogService(db)

    by_name = await service.list_products(ProductFilters(category_id=cat.id, query="galaxy"))
    assert [c.product.id for c in by_name.items] == [phone.id]

    sku = (
        await db.scalar(select(ProductVariant.sku).where(ProductVariant.product_id == phone.id))
    ) or ""
    by_sku = await service.list_products(ProductFilters(category_id=cat.id, query=sku.lower()))
    assert [c.product.id for c in by_sku.items] == [phone.id]

    # LIKE wildcards in user input are treated literally.
    nothing = await service.list_products(ProductFilters(category_id=cat.id, query="%"))
    assert nothing.total == 0


async def test_filters_and_sorting(db: AsyncSession) -> None:
    cat = await make_category(db)
    cheap = await _product(db, "Arzon", category_id=cat.id, price="50000", sold=1)
    sale = await _product(
        db, "Chegirmada", category_id=cat.id, price="200000", discount="120000", sold=9
    )
    empty = await _product(db, "Tugagan", category_id=cat.id, price="80000", stock=0)
    service = CatalogService(db)

    def ids(page) -> list[uuid.UUID]:  # type: ignore[no-untyped-def]
        return [c.product.id for c in page.items]

    by_price = await service.list_products(
        ProductFilters(category_id=cat.id), sort=ProductSort.PRICE_ASC
    )
    # In-stock first; out-of-stock last regardless of price.
    assert ids(by_price) == [cheap.id, sale.id, empty.id]
    card = next(c for c in by_price.items if c.product.id == sale.id)
    assert card.min_price == Decimal("120000.00")
    assert card.has_discount

    popular = await service.list_products(
        ProductFilters(category_id=cat.id), sort=ProductSort.POPULAR
    )
    assert ids(popular)[0] == sale.id

    assert ids(
        await service.list_products(ProductFilters(category_id=cat.id, discounted=True))
    ) == [sale.id]
    assert empty.id not in ids(
        await service.list_products(ProductFilters(category_id=cat.id, in_stock=True))
    )
    in_range = await service.list_products(
        ProductFilters(category_id=cat.id, min_price=Decimal("60000"), max_price=Decimal("150000"))
    )
    assert set(ids(in_range)) == {sale.id, empty.id}


async def test_hidden_products_and_pagination(db: AsyncSession) -> None:
    cat = await make_category(db)
    visible = await _product(db, "Ko‘rinadi", category_id=cat.id, price="1000")
    inactive = await _product(db, "Faol emas", category_id=cat.id, price="1000")
    inactive.is_active = False
    await db.flush()
    service = CatalogService(db)

    page = await service.list_products(ProductFilters(category_id=cat.id), page_size=1)
    assert page.total == 1
    assert page.pages == 1
    assert page.items[0].product.id == visible.id
    with pytest.raises(NotFoundError):
        await service.get_product(inactive.id)
    with pytest.raises(BusinessRuleError):
        await service.list_products(page=0)
    with pytest.raises(BusinessRuleError):
        await service.list_products(ProductFilters(min_price=Decimal(10), max_price=Decimal(1)))


async def test_category_tree_hides_inactive_branches(db: AsyncSession) -> None:
    root = await make_category(db, name="Uy-ro‘zg‘or")
    child = await make_category(db, name="Oshxona", parent_id=root.id)
    hidden = await make_category(db, name="Yashirin", is_active=False)
    await make_category(db, name="Yashirin bola", parent_id=hidden.id)

    tree = await CatalogService(db).category_tree()
    node = next(n for n in tree if n.id == root.id)
    assert [c.id for c in node.children] == [child.id]
    flat = {n.name for n in tree} | {c.name for n in tree for c in n.children}
    assert "Yashirin" not in flat
    assert "Yashirin bola" not in flat


# --- Cart ------------------------------------------------------------------------------


async def test_add_merge_update_remove(db: AsyncSession) -> None:
    user = await make_user(db)
    variant = await make_variant(db, price="70000", stock=5)
    cart = CartService(db)

    await cart.add_item(user.id, variant.id, 1)
    summary = await cart.add_item(user.id, variant.id, 2)  # same variant merges
    assert len(summary.lines) == 1
    assert summary.lines[0].quantity == 3
    assert summary.subtotal == Decimal("210000.00")

    item_id = summary.lines[0].item_id
    summary = await cart.set_quantity(user.id, item_id, 5)
    assert summary.total_quantity == 5
    with pytest.raises(InsufficientStockError, match="faqat 5 dona"):
        await cart.set_quantity(user.id, item_id, 6)

    summary = await cart.remove_item(user.id, item_id)
    assert summary.is_empty


async def test_cart_rejects_unavailable_products(db: AsyncSession) -> None:
    user = await make_user(db)
    sold_out = await make_variant(db, stock=0)
    cart = CartService(db)
    with pytest.raises(InsufficientStockError, match="tugagan"):
        await cart.add_item(user.id, sold_out.id)
    with pytest.raises(NotFoundError):
        await cart.add_item(user.id, uuid.uuid4())
    with pytest.raises(BusinessRuleError):
        await cart.add_item(user.id, sold_out.id, 0)


async def test_cart_flags_lines_that_became_unavailable(db: AsyncSession) -> None:
    user = await make_user(db)
    variant = await make_variant(db, price="10000", stock=3)
    cart = CartService(db)
    await cart.add_item(user.id, variant.id, 3)
    await db.execute(update(Inventory).where(Inventory.variant_id == variant.id).values(on_hand=1))
    await db.commit()

    summary = await cart.summary(user.id)
    assert summary.has_problems
    assert summary.lines[0].available == 1
    assert summary.subtotal == Decimal("0")  # unavailable lines don't count


async def test_promo_in_cart(db: AsyncSession) -> None:
    user = await make_user(db)
    variant = await make_variant(db, price="100000", stock=5)
    db.add(
        PromoCode(
            code="KUZ10",
            discount_type=DiscountType.PERCENT,
            value=Decimal(10),
            min_order_amount=Decimal("150000"),
        )
    )
    await db.flush()
    cart = CartService(db)
    summary = await cart.add_item(user.id, variant.id, 1)

    with pytest.raises(PromoCodeError) as exc:
        await cart.apply_promo(user.id, "kuz10")
    assert exc.value.code == "promo_min_order"

    await cart.set_quantity(user.id, summary.lines[0].item_id, 2)
    summary = await cart.apply_promo(user.id, "kuz10")
    assert summary.discount == Decimal("20000.00")
    assert summary.total == Decimal("180000.00")

    # Dropping below the minimum keeps the code but explains why there is no discount.
    summary = await cart.set_quantity(user.id, summary.lines[0].item_id, 1)
    assert summary.discount == Decimal("0")
    assert summary.promo_code == "KUZ10"
    assert summary.promo_error is not None


# --- Inventory -------------------------------------------------------------------------


async def _level(db: AsyncSession, variant_id: uuid.UUID) -> tuple[int, int]:
    inv = await db.get(Inventory, variant_id, populate_existing=True)
    assert inv is not None
    return inv.on_hand, inv.reserved


async def test_reserve_sell_release_cycle(db: AsyncSession) -> None:
    variant = await make_variant(db, stock=5)
    order = await make_order(db)
    inv = InventoryService(db)

    await inv.reserve([StockLine(variant.id, 2), StockLine(variant.id, 1)], order_id=order.id)
    assert await _level(db, variant.id) == (5, 3)
    await inv.commit_sale([StockLine(variant.id, 2)], order_id=order.id)
    assert await _level(db, variant.id) == (3, 1)
    await inv.release([StockLine(variant.id, 1)], order_id=order.id)
    assert await _level(db, variant.id) == (3, 0)

    types = list(
        await db.scalars(
            select(InventoryMovement.type)
            .where(InventoryMovement.variant_id == variant.id)
            .order_by(InventoryMovement.created_at, InventoryMovement.id)
        )
    )
    assert sorted(types) == sorted(
        [InventoryMovementType.RESERVE, InventoryMovementType.SALE, InventoryMovementType.RELEASE]
    )


async def test_reserve_is_all_or_nothing_message(db: AsyncSession) -> None:
    variant = await make_variant(db, stock=2)
    order = await make_order(db)
    with pytest.raises(InsufficientStockError) as exc:
        await InventoryService(db).reserve([StockLine(variant.id, 3)], order_id=order.id)
    assert exc.value.details["available"] == 2
    assert "faqat 2 dona" in exc.value.message


async def test_adjust_cannot_go_below_reserved(db: AsyncSession) -> None:
    variant = await make_variant(db, stock=5)
    order = await make_order(db)
    inv = InventoryService(db)
    await inv.reserve([StockLine(variant.id, 4)], order_id=order.id)

    with pytest.raises(BusinessRuleError) as exc:
        await inv.adjust(variant.id, delta=-2, reason="Inventarizatsiya", admin_user_id=None)
    assert exc.value.code == "below_reserved"

    level = await inv.adjust(variant.id, delta=10, reason="Yangi partiya", admin_user_id=None)
    assert (level.on_hand, level.reserved) == (15, 4)
    with pytest.raises(BusinessRuleError):
        await inv.adjust(variant.id, delta=1, reason="  ", admin_user_id=None)


async def test_low_stock_report(db: AsyncSession) -> None:
    low = await make_variant(db, stock=2)
    plenty = await make_variant(db, stock=50)
    custom = await make_variant(db, stock=20)
    await db.execute(
        update(Inventory).where(Inventory.variant_id == custom.id).values(low_stock_threshold=25)
    )
    ids = {item.variant_id for item in await InventoryService(db).low_stock()}
    assert low.id in ids
    assert custom.id in ids
    assert plenty.id not in ids
