"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ConfirmButton } from "@/components/layout/confirm-dialog";
import { PageHeader } from "@/components/layout/page-header";
import { RequirePermission } from "@/components/layout/require";
import { ErrorState, LoadingRows } from "@/components/layout/states";
import {
  DeliveryStatusBadge,
  OrderStatusBadge,
  PaymentStatusBadge,
} from "@/components/layout/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiRequest } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import {
  DELIVERY_STATUS,
  formatDateTime,
  formatUZS,
  ORDER_STATUS,
  PAYMENT_METHOD,
  PAYMENT_STATUS,
} from "@/lib/format";
import { useAction } from "@/lib/mutation";
import type { AdminOrder, DeliveryStatus, OrderStatus, PaymentStatus } from "@/types/api";

// Mirrors the backend rules so only sensible buttons are shown; the API still decides.
const NEXT_STATUS: Partial<Record<OrderStatus, OrderStatus[]>> = {
  confirmed: ["processing", "shipped"],
  processing: ["shipped"],
  shipped: ["out_for_delivery", "delivered"],
  out_for_delivery: ["delivered"],
};
const NEXT_DELIVERY: Partial<Record<DeliveryStatus, DeliveryStatus[]>> = {
  awaiting_dispatch: ["preparing", "shipped"],
  preparing: ["shipped"],
  shipped: ["out_for_delivery", "delivered", "delivery_failed"],
  out_for_delivery: ["delivered", "delivery_failed"],
  delivery_failed: ["out_for_delivery", "returned"],
};
const FIELD_LABELS = {
  status: "Holat",
  payment_status: "To‘lov",
  delivery_status: "Yetkazish",
} as const;
const ACTORS = {
  admin: "Xodim",
  customer: "Mijoz",
  system: "Tizim",
  provider: "To‘lov tizimi",
} as const;

function label(field: keyof typeof FIELD_LABELS, value: string | null): string {
  if (!value) return "—";
  const map = {
    status: ORDER_STATUS,
    payment_status: PAYMENT_STATUS,
    delivery_status: DELIVERY_STATUS,
  }[field];
  return (map as Record<string, string>)[value] ?? value;
}

function NoteEditor({
  initial,
  editable,
  saving,
  onSave,
}: {
  initial: string;
  editable: boolean;
  saving: boolean;
  onSave: (note: string) => void;
}) {
  const [note, setNote] = useState(initial);
  return (
    <div className="grid gap-2">
      <Textarea
        aria-label="Ichki izoh"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        disabled={!editable}
      />
      {editable ? (
        <Button
          size="sm"
          variant="outline"
          className="justify-self-start"
          disabled={saving || note === initial}
          onClick={() => onSave(note)}
        >
          Saqlash
        </Button>
      ) : null}
    </div>
  );
}

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const key = ["orders", id];
  const query = useQuery({
    queryKey: key,
    queryFn: () => apiRequest<AdminOrder>(`/admin/orders/${id}`),
  });
  const [cancelReason, setCancelReason] = useState("");
  const [refund, setRefund] = useState({ reason: "", restock: true });

  const post = (path: string, body?: unknown) =>
    apiRequest<AdminOrder>(`/admin/orders/${id}${path}`, { method: "POST", body });
  const opts = (success: string) => ({ success, invalidate: [key, ["orders"], ["dashboard"]] });
  const confirm = useAction(() => post("/confirm"), opts("Buyurtma tasdiqlandi"));
  const status = useAction(
    (s: OrderStatus) => post("/status", { status: s }),
    opts("Holat yangilandi"),
  );
  const delivery = useAction(
    (s: DeliveryStatus) => post("/delivery-status", { delivery_status: s }),
    opts("Yetkazish holati yangilandi"),
  );
  const cancel = useAction(
    () => post("/cancel", { reason: cancelReason || null }),
    opts("Buyurtma bekor qilindi"),
  );
  const doRefund = useAction(() => post("/refund", refund), opts("Pul qaytarilgani qayd etildi"));
  const saveNote = useAction(
    (note: string) =>
      apiRequest<AdminOrder>(`/admin/orders/${id}/note`, {
        method: "PATCH",
        body: { internal_note: note },
      }),
    opts("Izoh saqlandi"),
  );

  if (query.isPending) return <LoadingRows rows={8} />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const o = query.data;
  const manage = can("orders.manage");
  const busy = confirm.isPending || status.isPending || delivery.isPending;

  return (
    <RequirePermission permission="orders.view">
      <PageHeader
        title={`Buyurtma ${o.number}`}
        description={formatDateTime(o.created_at)}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <OrderStatusBadge status={o.status} />
            <PaymentStatusBadge status={o.payment_status as PaymentStatus} />
            <DeliveryStatusBadge status={o.delivery_status} />
          </div>
        }
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="grid gap-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Mahsulotlar</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Mahsulot</TableHead>
                    <TableHead>SKU</TableHead>
                    <TableHead>Narx</TableHead>
                    <TableHead>Soni</TableHead>
                    <TableHead>Jami</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {o.items.map((i) => (
                    <TableRow key={i.id}>
                      <TableCell>
                        {i.product_name}
                        {i.variant_name ? (
                          <span className="text-muted-foreground"> ({i.variant_name})</span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-xs">{i.sku}</TableCell>
                      <TableCell className="whitespace-nowrap">{formatUZS(i.unit_price)}</TableCell>
                      <TableCell>{i.quantity}</TableCell>
                      <TableCell className="whitespace-nowrap">{formatUZS(i.line_total)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <dl className="mt-4 grid grid-cols-2 gap-1 text-sm sm:ml-auto sm:max-w-xs">
                <dt className="text-muted-foreground">Mahsulotlar</dt>
                <dd className="text-right">{formatUZS(o.subtotal)}</dd>
                <dt className="text-muted-foreground">
                  Chegirma{o.promo_code ? ` (${o.promo_code})` : ""}
                </dt>
                <dd className="text-right">−{formatUZS(o.discount_total)}</dd>
                <dt className="text-muted-foreground">Yetkazib berish</dt>
                <dd className="text-right">{formatUZS(o.delivery_fee)}</dd>
                <dt className="font-semibold">Jami</dt>
                <dd className="text-right font-semibold">{formatUZS(o.total)}</dd>
              </dl>
            </CardContent>
          </Card>

          {manage ? (
            <Card>
              <CardHeader>
                <CardTitle>Amallar</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4">
                <div className="flex flex-wrap gap-2">
                  {o.status === "pending" ? (
                    <Button disabled={busy} onClick={() => confirm.mutate(undefined)}>
                      Tasdiqlash
                    </Button>
                  ) : null}
                  {(NEXT_STATUS[o.status] ?? []).map((s) => (
                    <Button
                      key={s}
                      variant="outline"
                      disabled={busy}
                      onClick={() => status.mutate(s)}
                    >
                      → {ORDER_STATUS[s]}
                    </Button>
                  ))}
                </div>
                {o.status !== "pending" && o.status !== "cancelled" && o.status !== "refunded" ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-muted-foreground text-sm">Yetkazish:</span>
                    {(NEXT_DELIVERY[o.delivery_status] ?? []).map((s) => (
                      <Button
                        key={s}
                        size="sm"
                        variant="secondary"
                        disabled={busy}
                        onClick={() => delivery.mutate(s)}
                      >
                        → {DELIVERY_STATUS[s]}
                      </Button>
                    ))}
                  </div>
                ) : null}
                {["pending", "confirmed", "processing"].includes(o.status) ? (
                  <div className="flex flex-wrap items-end gap-2">
                    <div className="grid gap-1.5">
                      <Label htmlFor="cancel-reason">Bekor qilish sababi</Label>
                      <Input
                        id="cancel-reason"
                        value={cancelReason}
                        onChange={(e) => setCancelReason(e.target.value)}
                        className="w-64"
                      />
                    </div>
                    <ConfirmButton
                      destructive
                      variant="destructive"
                      title={`${o.number} bekor qilinsinmi?`}
                      description="Band qilingan mahsulotlar omborga qaytariladi. To‘langan bo‘lsa, pulni qaytarishni alohida qayd eting."
                      confirmLabel="Bekor qilish"
                      onConfirm={() => cancel.mutateAsync(undefined)}
                    >
                      Buyurtmani bekor qilish
                    </ConfirmButton>
                  </div>
                ) : null}
                {can("orders.refund") &&
                o.payment_status === "paid" &&
                ["delivered", "cancelled"].includes(o.status) ? (
                  <div className="flex flex-wrap items-end gap-2">
                    <div className="grid gap-1.5">
                      <Label htmlFor="refund-reason">Qaytarish sababi</Label>
                      <Input
                        id="refund-reason"
                        value={refund.reason}
                        onChange={(e) => setRefund((r) => ({ ...r, reason: e.target.value }))}
                        className="w-64"
                      />
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={refund.restock}
                        onChange={(e) => setRefund((r) => ({ ...r, restock: e.target.checked }))}
                      />
                      Mahsulot omborga qaytdi
                    </label>
                    <ConfirmButton
                      destructive
                      title="Pul qaytarilganini qayd etish"
                      description="Click/Payme orqali pulni qaytarish to‘lov integratsiyasi ulanganidan keyin avtomatlashadi. Hozircha bu faqat holatni yozib qo‘yadi."
                      disabled={!refund.reason.trim()}
                      onConfirm={() => doRefund.mutateAsync(undefined)}
                    >
                      Pul qaytarildi
                    </ConfirmButton>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle>Tarix</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="grid gap-2 text-sm">
                {o.history.map((h, i) => (
                  <li key={i} className="flex flex-wrap gap-x-2">
                    <span className="text-muted-foreground w-36">
                      {formatDateTime(h.created_at)}
                    </span>
                    <span>
                      {FIELD_LABELS[h.field]}: {label(h.field, h.from_value)} →{" "}
                      <b>{label(h.field, h.to_value)}</b>
                    </span>
                    <span className="text-muted-foreground">
                      ({ACTORS[h.actor_type]}
                      {h.comment ? `: ${h.comment}` : ""})
                    </span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>

        <div className="grid content-start gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Yetkazib berish</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-1 text-sm">
              <p className="font-medium">{o.recipient_name}</p>
              <p>{o.recipient_phone}</p>
              <p>
                {o.region_name}, {o.district_name}
              </p>
              <p>{o.address_line}</p>
              {o.landmark ? <p className="text-muted-foreground">Mo‘ljal: {o.landmark}</p> : null}
              {o.delivery_instructions ? (
                <p className="text-muted-foreground">Izoh: {o.delivery_instructions}</p>
              ) : null}
              <p className="mt-2">{o.delivery_method_name}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>To‘lov</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-1 text-sm">
              <p>Usul: {PAYMENT_METHOD[o.payment_method]}</p>
              <p>Holat: {PAYMENT_STATUS[o.payment_status as PaymentStatus]}</p>
              <p>To‘langan: {formatDateTime(o.paid_at)}</p>
              {o.reservation_expires_at ? (
                <p className="text-muted-foreground">
                  Band qilish muddati: {formatDateTime(o.reservation_expires_at)}
                </p>
              ) : null}
            </CardContent>
          </Card>
          {o.customer_note ? (
            <Card>
              <CardHeader>
                <CardTitle>Mijoz izohi</CardTitle>
              </CardHeader>
              <CardContent className="text-sm">{o.customer_note}</CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>Ichki izoh</CardTitle>
            </CardHeader>
            <CardContent>
              {/* Re-mounts when the saved note changes, so it never shows stale text. */}
              <NoteEditor
                key={o.internal_note ?? ""}
                initial={o.internal_note ?? ""}
                editable={manage}
                saving={saveNote.isPending}
                onSave={(note) => saveNote.mutate(note)}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </RequirePermission>
  );
}
