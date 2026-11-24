import { Badge } from "@/components/ui/badge";
import { DELIVERY_STATUS, ORDER_STATUS, PAYMENT_STATUS, statusTone } from "@/lib/format";
import type { DeliveryStatus, OrderStatus, PaymentStatus } from "@/types/api";

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return <Badge variant={statusTone(status)}>{ORDER_STATUS[status]}</Badge>;
}
export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  return <Badge variant={statusTone(status)}>{PAYMENT_STATUS[status]}</Badge>;
}
export function DeliveryStatusBadge({ status }: { status: DeliveryStatus }) {
  return <Badge variant={statusTone(status)}>{DELIVERY_STATUS[status]}</Badge>;
}
