"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Pagination } from "@/components/layout/pagination";
import { RequirePermission } from "@/components/layout/require";
import { EmptyState, ErrorState, LoadingRows } from "@/components/layout/states";
import { Badge } from "@/components/ui/badge";
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
import { formatDate, formatUZS } from "@/lib/format";
import type { Customer, Page } from "@/types/api";

export default function CustomersPage() {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["customers", q, sort, page],
    queryFn: () =>
      apiRequest<Page<Customer>>("/admin/customers", { query: { q, sort, page, page_size: 20 } }),
    placeholderData: (prev) => prev,
  });
  return (
    <RequirePermission permission="customers.view">
      <PageHeader title="Mijozlar" description="Telegram bot orqali ro‘yxatdan o‘tganlar" />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          className="max-w-xs"
          placeholder="Ism, telefon, @username yoki Telegram ID"
          aria-label="Qidirish"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
        <NativeSelect
          className="w-48"
          aria-label="Saralash"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="newest">Yangilari</option>
          <option value="spent">Ko‘p xarid qilganlar</option>
          <option value="orders">Ko‘p buyurtma berganlar</option>
        </NativeSelect>
      </div>
      {query.isPending ? (
        <LoadingRows />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title="Mijozlar topilmadi" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Mijoz</TableHead>
                <TableHead>Telefon</TableHead>
                <TableHead>Buyurtmalar</TableHead>
                <TableHead>Xaridlar</TableHead>
                <TableHead>Ro‘yxatdan o‘tgan</TableHead>
                <TableHead>Holati</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.items.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <Link href={`/customers/${c.id}`} className="font-medium hover:underline">
                      {[c.first_name, c.last_name].filter(Boolean).join(" ")}
                    </Link>
                    <div className="text-muted-foreground text-xs">
                      {c.username ? `@${c.username}` : `ID ${c.telegram_id}`}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {c.phone ?? "—"}
                    {c.phone_verified ? " ✓" : ""}
                  </TableCell>
                  <TableCell>{c.orders_count}</TableCell>
                  <TableCell className="whitespace-nowrap">{formatUZS(c.total_spent)}</TableCell>
                  <TableCell className="text-sm">{formatDate(c.created_at)}</TableCell>
                  <TableCell>
                    {c.is_blocked ? (
                      <Badge variant="destructive">Bloklangan</Badge>
                    ) : (
                      <Badge variant="success">Faol</Badge>
                    )}
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
