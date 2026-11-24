"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ConfirmButton } from "@/components/layout/confirm-dialog";
import { PageHeader } from "@/components/layout/page-header";
import { RequirePermission } from "@/components/layout/require";
import { ErrorState, LoadingRows } from "@/components/layout/states";
import { OrderStatusBadge } from "@/components/layout/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { formatDate, formatDateTime, formatUZS } from "@/lib/format";
import { useAction } from "@/lib/mutation";
import type { Customer, OrderListItem, Page } from "@/types/api";

export default function CustomerPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const customer = useQuery({
    queryKey: ["customers", id],
    queryFn: () => apiRequest<Customer>(`/admin/customers/${id}`),
  });
  const orders = useQuery({
    queryKey: ["orders", { customer_id: id }],
    queryFn: () =>
      apiRequest<Page<OrderListItem>>("/admin/orders", {
        query: { customer_id: id, page_size: 50 },
      }),
    enabled: can("orders.view"),
  });
  const block = useAction(
    (blocked: boolean) =>
      apiRequest(`/admin/customers/${id}`, { method: "PATCH", body: { is_blocked: blocked } }),
    { success: "Saqlandi", invalidate: [["customers"]] },
  );
  if (customer.isPending) return <LoadingRows />;
  if (customer.error)
    return <ErrorState error={customer.error} onRetry={() => void customer.refetch()} />;
  const c = customer.data;
  return (
    <RequirePermission permission="customers.view">
      <PageHeader
        title={[c.first_name, c.last_name].filter(Boolean).join(" ")}
        description={c.username ? `@${c.username}` : `Telegram ID ${c.telegram_id}`}
        actions={
          can("customers.manage") ? (
            <ConfirmButton
              destructive={!c.is_blocked}
              title={c.is_blocked ? "Blokdan chiqarilsinmi?" : "Mijoz bloklansinmi?"}
              description={
                c.is_blocked ? undefined : "Bloklangan mijoz bot orqali buyurtma bera olmaydi."
              }
              onConfirm={() => block.mutateAsync(!c.is_blocked)}
            >
              {c.is_blocked ? "Blokdan chiqarish" : "Bloklash"}
            </ConfirmButton>
          ) : null
        }
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <Card className="gap-1 py-4">
          <CardContent className="px-4 text-sm">
            Telefon
            <p className="text-lg font-semibold">
              {c.phone ?? "—"}
              {c.phone_verified ? " ✓" : ""}
            </p>
          </CardContent>
        </Card>
        <Card className="gap-1 py-4">
          <CardContent className="px-4 text-sm">
            Buyurtmalar<p className="text-lg font-semibold">{c.orders_count}</p>
          </CardContent>
        </Card>
        <Card className="gap-1 py-4">
          <CardContent className="px-4 text-sm">
            Jami xarid<p className="text-lg font-semibold">{formatUZS(c.total_spent)}</p>
          </CardContent>
        </Card>
        <Card className="gap-1 py-4">
          <CardContent className="px-4 text-sm">
            Ro‘yxatdan o‘tgan<p className="text-lg font-semibold">{formatDate(c.created_at)}</p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Buyurtmalar tarixi</CardTitle>
        </CardHeader>
        <CardContent>
          {!can("orders.view") ? null : orders.isPending ? (
            <LoadingRows rows={3} />
          ) : orders.error ? (
            <ErrorState error={orders.error} />
          ) : orders.data.items.length === 0 ? (
            <p className="text-muted-foreground text-sm">Buyurtmalar yo‘q.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Raqam</TableHead>
                  <TableHead>Summa</TableHead>
                  <TableHead>Holati</TableHead>
                  <TableHead>Sana</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.data.items.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell>
                      <Link href={`/orders/${o.id}`} className="hover:underline">
                        {o.number}
                      </Link>
                    </TableCell>
                    <TableCell>{formatUZS(o.total)}</TableCell>
                    <TableCell>
                      <OrderStatusBadge status={o.status} />
                    </TableCell>
                    <TableCell className="text-xs">{formatDateTime(o.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </RequirePermission>
  );
}
