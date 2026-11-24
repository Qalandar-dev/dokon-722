import type { DeliveryStatus, OrderStatus, PaymentMethod, PaymentStatus } from "@/types/api";

export { formatUZS } from "@/lib/utils";

const dateTime = new Intl.DateTimeFormat("uz-UZ", {
  timeZone: "Asia/Tashkent",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const dateOnly = new Intl.DateTimeFormat("uz-UZ", {
  timeZone: "Asia/Tashkent",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)) : "—";
}

export function formatDate(iso: string | null | undefined): string {
  return iso ? dateOnly.format(new Date(iso)) : "—";
}

export const ORDER_STATUS: Record<OrderStatus, string> = {
  pending: "Yangi",
  confirmed: "Tasdiqlangan",
  processing: "Tayyorlanmoqda",
  shipped: "Jo‘natilgan",
  out_for_delivery: "Yetkazilmoqda",
  delivered: "Yetkazildi",
  cancelled: "Bekor qilingan",
  refunded: "Pul qaytarilgan",
};

export const PAYMENT_STATUS: Record<PaymentStatus, string> = {
  pending: "Kutilmoqda",
  processing: "Jarayonda",
  paid: "To‘langan",
  failed: "Muvaffaqiyatsiz",
  cancelled: "Bekor qilingan",
  refunded: "Qaytarilgan",
};

export const DELIVERY_STATUS: Record<DeliveryStatus, string> = {
  awaiting_dispatch: "Jo‘natish kutilmoqda",
  preparing: "Tayyorlanmoqda",
  shipped: "Jo‘natildi",
  out_for_delivery: "Kuryerda",
  delivered: "Yetkazildi",
  delivery_failed: "Yetkazib bo‘lmadi",
  returned: "Qaytarildi",
};

export const PAYMENT_METHOD: Record<PaymentMethod, string> = {
  click: "Click",
  payme: "Payme",
  cash_on_delivery: "Naqd (kuryerga)",
};

export function statusTone(
  status: OrderStatus | PaymentStatus | DeliveryStatus,
): "success" | "warning" | "destructive" | "secondary" {
  if (["delivered", "paid"].includes(status)) return "success";
  if (["cancelled", "failed", "refunded", "delivery_failed", "returned"].includes(status))
    return "destructive";
  if (["pending", "awaiting_dispatch", "processing"].includes(status)) return "warning";
  return "secondary";
}
