"use client";

import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { RequirePermission } from "@/components/layout/require";
import { EmptyState, ErrorState, LoadingRows, errorMessage } from "@/components/layout/states";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiRequest, downloadFile } from "@/lib/api-client";
import { formatUZS, ORDER_STATUS, PAYMENT_METHOD } from "@/lib/format";
import type { OrderStatus, PaymentMethod } from "@/types/api";

const REPORTS = {
  sales: {
    label: "Sotuvlar",
    columns: {
      period: "Davr",
      orders: "Buyurtmalar",
      revenue: "Tushum",
      average_order: "O‘rtacha chek",
    },
  },
  categories: {
    label: "Kategoriyalar",
    columns: { category: "Kategoriya", units: "Dona", revenue: "Tushum" },
  },
  products: {
    label: "Top mahsulotlar",
    columns: { product_name: "Mahsulot", units: "Dona", revenue: "Tushum" },
  },
  customers: {
    label: "Top mijozlar",
    columns: { name: "Mijoz", phone: "Telefon", orders: "Buyurtmalar", revenue: "Tushum" },
  },
  "payment-methods": {
    label: "To‘lov usullari",
    columns: { payment_method: "Usul", orders: "Buyurtmalar", revenue: "Tushum" },
  },
  "order-statuses": {
    label: "Buyurtma holatlari",
    columns: { status: "Holat", orders: "Buyurtmalar", amount: "Summa" },
  },
} as const;
type ReportKey = keyof typeof REPORTS;
const MONEY = new Set(["revenue", "average_order", "amount"]);

function cell(column: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (MONEY.has(column)) return formatUZS(String(value));
  if (column === "payment_method") return PAYMENT_METHOD[value as PaymentMethod] ?? String(value);
  if (column === "status") return ORDER_STATUS[value as OrderStatus] ?? String(value);
  return String(value);
}

export default function ReportsPage() {
  const [report, setReport] = useState<ReportKey>("sales");
  // Lazy initialiser: the clock is read once on mount, not during every render.
  const [range, setRange] = useState(() => {
    const now = Date.now();
    return {
      date_from: new Date(now - 29 * 864e5).toISOString().slice(0, 10),
      date_to: new Date(now).toISOString().slice(0, 10),
      group_by: "day",
    };
  });
  const params = {
    date_from: range.date_from,
    date_to: range.date_to,
    ...(report === "sales" ? { group_by: range.group_by } : {}),
  };
  const query = useQuery({
    queryKey: ["report", report, params],
    queryFn: () =>
      apiRequest<{ rows: Record<string, unknown>[] }>(`/admin/reports/${report}`, {
        query: params,
      }),
  });
  const columns = REPORTS[report].columns;
  return (
    <RequirePermission permission="reports.view">
      <PageHeader
        title="Hisobotlar"
        description="Tushum — to‘langan buyurtmalar, to‘lov sanasi bo‘yicha (Toshkent vaqti)"
        actions={
          <Button
            variant="outline"
            onClick={() =>
              downloadFile(`/admin/reports/${report}`, { ...params, format: "csv" }).catch((e) =>
                toast.error(errorMessage(e)),
              )
            }
          >
            <Download aria-hidden /> CSV yuklab olish
          </Button>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <NativeSelect
          className="w-52"
          aria-label="Hisobot"
          value={report}
          onChange={(e) => setReport(e.target.value as ReportKey)}
        >
          {Object.entries(REPORTS).map(([k, r]) => (
            <option key={k} value={k}>
              {r.label}
            </option>
          ))}
        </NativeSelect>
        <Input
          type="date"
          className="w-40"
          aria-label="Sanadan"
          value={range.date_from}
          onChange={(e) => setRange((r) => ({ ...r, date_from: e.target.value }))}
        />
        <Input
          type="date"
          className="w-40"
          aria-label="Sanagacha"
          value={range.date_to}
          onChange={(e) => setRange((r) => ({ ...r, date_to: e.target.value }))}
        />
        {report === "sales" ? (
          <NativeSelect
            className="w-36"
            aria-label="Guruhlash"
            value={range.group_by}
            onChange={(e) => setRange((r) => ({ ...r, group_by: e.target.value }))}
          >
            <option value="day">Kunlik</option>
            <option value="week">Haftalik</option>
            <option value="month">Oylik</option>
          </NativeSelect>
        ) : null}
      </div>
      {query.isPending ? (
        <LoadingRows />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.rows.length === 0 ? (
        <EmptyState title="Bu davrda ma’lumot yo‘q" />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              {Object.values(columns).map((c) => (
                <TableHead key={c}>{c}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.rows.map((row, i) => (
              <TableRow key={i}>
                {Object.keys(columns).map((c) => (
                  <TableCell key={c}>{cell(c, row[c])}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </RequirePermission>
  );
}
