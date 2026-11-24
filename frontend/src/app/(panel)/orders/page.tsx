"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Pagination } from "@/components/layout/pagination";
import { RequirePermission } from "@/components/layout/require";
import { EmptyState, ErrorState, LoadingRows } from "@/components/layout/states";
import { OrderStatusBadge, PaymentStatusBadge } from "@/components/layout/status-badge";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiRequest } from "@/lib/api-client";
import {
  formatDateTime,
  formatUZS,
  ORDER_STATUS,
  PAYMENT_METHOD,
  PAYMENT_STATUS,
} from "@/lib/format";
import type { OrderListItem, Page } from "@/types/api";

export default function OrdersPage() {
  const [filters, setFilters] = useState({
    q: "",
    status: "",
    payment_status: "",
    payment_method: "",
    date_from: "",
    date_to: "",
  });
  const [page, setPage] = useState(1);
  const set = (key: keyof typeof filters) => (e: { target: { value: string } }) => {
    setFilters((f) => ({ ...f, [key]: e.target.value }));
    setPage(1);
  };
  const query = useQuery({
    queryKey: ["orders", filters, page],
    queryFn: () =>
      apiRequest<Page<OrderListItem>>("/admin/orders", {
        query: { ...filters, page, page_size: 20 },
      }),
    placeholderData: (prev) => prev,
  });

  return (
    <RequirePermission permission="orders.view">
      <PageHeader title="Buyurtmalar" description="Barcha buyurtmalar, eng yangilari birinchi" />
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
        <Input
          placeholder="Raqam, ism yoki telefon"
          aria-label="Qidirish"
          value={filters.q}
          onChange={set("q")}
          className="lg:col-span-2"
        />
        <NativeSelect aria-label="Holati" value={filters.status} onChange={set("status")}>
          <option value="">Barcha holatlar</option>
          {Object.entries(ORDER_STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="To‘lov holati"
          value={filters.payment_status}
          onChange={set("payment_status")}
        >
          <option value="">To‘lov: barchasi</option>
          {Object.entries(PAYMENT_STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
        <Input
          type="date"
          aria-label="Sanadan"
          value={filters.date_from}
          onChange={set("date_from")}
        />
        <Input
          type="date"
          aria-label="Sanagacha"
          value={filters.date_to}
          onChange={set("date_to")}
        />
      </div>
      {query.isPending ? (
        <LoadingRows />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title="Buyurtmalar topilmadi" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Raqam</TableHead>
                <TableHead>Mijoz</TableHead>
                <TableHead>Hudud</TableHead>
                <TableHead>Summa</TableHead>
                <TableHead>To‘lov</TableHead>
                <TableHead>Holati</TableHead>
                <TableHead>Sana</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.items.map((o) => (
                <TableRow key={o.id}>
                  <TableCell>
                    <Link
                      href={`/orders/${o.id}`}
                      className="font-medium underline-offset-4 hover:underline"
                    >
                      {o.number}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <div>{o.recipient_name}</div>
                    <div className="text-muted-foreground text-xs">{o.recipient_phone}</div>
                  </TableCell>
                  <TableCell className="text-xs">
                    {o.region_name}
                    <div className="text-muted-foreground">{o.district_name}</div>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{formatUZS(o.total)}</TableCell>
                  <TableCell>
                    <div className="text-xs">{PAYMENT_METHOD[o.payment_method]}</div>
                    <PaymentStatusBadge status={o.payment_status} />
                  </TableCell>
                  <TableCell>
                    <OrderStatusBadge status={o.status} />
                  </TableCell>
                  <TableCell className="text-xs whitespace-nowrap">
                    {formatDateTime(o.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pagination
            page={query.data.page}
            pages={query.data.pages}
            total={query.data.total}
            onChange={setPage}
          />
        </>
      )}
    </RequirePermission>
  );
}
