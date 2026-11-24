import pytest

from app.core.exceptions import InvalidTransitionError
from app.models.enums import DeliveryStatus, OrderStatus, PaymentMethod, PaymentStatus
from app.services import order_status as rules

O, P, D = OrderStatus, PaymentStatus, DeliveryStatus  # noqa: E741


def test_every_status_has_rules_and_labels() -> None:
    assert set(rules.ORDER_TRANSITIONS) == set(OrderStatus)
    assert set(rules.PAYMENT_TRANSITIONS) == set(PaymentStatus)
    assert set(rules.DELIVERY_TRANSITIONS) == set(DeliveryStatus)
    assert set(rules.ORDER_STATUS_LABELS) == set(OrderStatus)
    assert set(rules.PAYMENT_STATUS_LABELS) == set(PaymentStatus)
    assert set(rules.DELIVERY_STATUS_LABELS) == set(DeliveryStatus)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (O.PENDING, O.CONFIRMED),
        (O.CONFIRMED, O.PROCESSING),
        (O.PROCESSING, O.SHIPPED),
        (O.SHIPPED, O.OUT_FOR_DELIVERY),
        (O.OUT_FOR_DELIVERY, O.DELIVERED),
        (O.DELIVERED, O.REFUNDED),
        (O.PENDING, O.CANCELLED),
        (O.PROCESSING, O.CANCELLED),
    ],
)
def test_allowed_order_transitions(current: OrderStatus, target: OrderStatus) -> None:
    rules.ensure_order_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (O.PENDING, O.DELIVERED),  # cannot skip fulfilment
        (O.SHIPPED, O.PENDING),  # no going back once shipped
        (O.DELIVERED, O.PENDING),
        (O.CANCELLED, O.CONFIRMED),  # no resurrection
        (O.REFUNDED, O.DELIVERED),  # terminal
    ],
)
def test_forbidden_order_transitions(current: OrderStatus, target: OrderStatus) -> None:
    with pytest.raises(InvalidTransitionError) as exc:
        rules.ensure_order_transition(current, target)
    assert exc.value.details == {"from": current.value, "to": target.value}


def test_paid_can_only_become_refunded() -> None:
    assert rules.PAYMENT_TRANSITIONS[P.PAID] == {P.REFUNDED}
    with pytest.raises(InvalidTransitionError):
        rules.ensure_payment_transition(P.PAID, P.FAILED)


def test_failed_payment_can_be_retried() -> None:
    rules.ensure_payment_transition(P.FAILED, P.PROCESSING)
    rules.ensure_payment_transition(P.FAILED, P.PAID)


def test_failed_delivery_can_be_retried_or_returned() -> None:
    rules.ensure_delivery_transition(D.DELIVERY_FAILED, D.OUT_FOR_DELIVERY)
    rules.ensure_delivery_transition(D.DELIVERY_FAILED, D.RETURNED)
    with pytest.raises(InvalidTransitionError):
        rules.ensure_delivery_transition(D.DELIVERED, D.SHIPPED)


def test_status_mappings_are_consistent() -> None:
    for delivery, order in rules.DELIVERY_TO_ORDER.items():
        assert rules.ORDER_TO_DELIVERY[order] is delivery


def test_online_orders_need_payment_before_confirmation() -> None:
    assert rules.requires_payment_before_confirm(PaymentMethod.CLICK)
    assert rules.requires_payment_before_confirm(PaymentMethod.PAYME)
    assert not rules.requires_payment_before_confirm(PaymentMethod.CASH_ON_DELIVERY)


def test_error_message_is_uzbek() -> None:
    with pytest.raises(InvalidTransitionError, match="Yetkazildi"):
        rules.ensure_order_transition(O.DELIVERED, O.CANCELLED)


def test_shipped_orders_are_not_staff_cancellable() -> None:
    """The table allows shipped → cancelled only for returned parcels; a direct staff
    cancellation of a shipped order is refused by OrderService.cancel."""
    assert O.SHIPPED not in rules.STAFF_CANCELLABLE
    assert O.OUT_FOR_DELIVERY not in rules.STAFF_CANCELLABLE
