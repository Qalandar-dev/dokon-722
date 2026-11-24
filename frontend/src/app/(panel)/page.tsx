"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PageHeader } from "@/components/layout/page-header";
import { RequirePermission } from "@/components/layout/require";
import { ErrorState, LoadingRows } from "@/components/layout/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SystemStatus } from "@/features/system/system-status";
import { apiRequest } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { formatUZS } from "@/lib/format";
import type { Dashboard } from "@/types/api";

function Stat({ title, value, hint }: { title: string; value: string; hint?: string }) {
  return (
    <Card className="gap-2 py-4">
      <CardHeader className="px-4">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
      {hint ? (
        <CardContent className="text-muted-foreground px-4 text-xs">{hint}</CardContent>
      ) : null}
    </Card>
  );
}

function compact(value: number): string {
  return new Intl.NumberFormat("uz-UZ", { notation: "compact", maximumFractionDigits: 1 }).format(
    value,
  );
}

function DashboardView() {
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiRequest<Dashboard>("/admin/dashboard"),
    refetchInterval: 60_000,
  });
  if (isPending) return <LoadingRows rows={8} />;
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />;

  const chart = data.sales_chart.map((p) => ({
    day: p.period.slice(5).split("-").reverse().join("."),
    revenue: Number(p.revenue),
    orders: p.orders,
  }));
  return (
    <div className="grid gap-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          title="Bugungi tushum"
          value={formatUZS(data.revenue_today.revenue)}
          hint={`${data.revenue_today.orders} ta to‘langan buyurtma`}
        />
        <Stat
          title="Shu hafta"
          value={formatUZS(data.revenue_week.revenue)}
          hint={`${data.revenue_week.orders} ta buyurtma`}
        />
        <Stat
          title="Shu oy"
          value={formatUZS(data.revenue_month.revenue)}
          hint={`${data.revenue_month.orders} ta buyurtma`}
        />
        <Stat title="Jami tushum" value={formatUZS(data.revenue_total)} />
        <Stat
          title="Yangi buyurtmalar"
          value={String(data.orders_pending)}
          hint="Tasdiqlash kutilmoqda"
        />
        <Stat
          title="Jarayonda"
          value={String(data.orders_in_progress)}
          hint="Tasdiqlangan → yetkazilmoqda"
        />
        <Stat
          title="Yetkazilgan / bekor"
          value={`${data.orders_completed} / ${data.orders_cancelled}`}
          hint={`Jami buyurtmalar: ${data.orders_total}`}
        />
        <Stat
          title="Mijozlar"
          value={String(data.customers_total)}
          hint={`Shu oy yangi: ${data.customers_new_month}`}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>So‘nggi 30 kunlik tushum</CardTitle>
          <CardDescription>Faqat to‘langan buyurtmalar, Toshkent vaqti bo‘yicha</CardDescription>
        </CardHeader>
        <CardContent className="relative h-72">
          {chart.every((p) => p.revenue === 0) ? (
            <p className="text-muted-foreground absolute inset-0 flex items-center justify-center text-sm">
              Bu davrda to‘langan buyurtmalar hali yo‘q
            </p>
          ) : null}
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="day" fontSize={12} interval="preserveStartEnd" />
              <YAxis fontSize={12} tickFormatter={compact} width={48} />
              <Tooltip
                formatter={(value) => [formatUZS(Number(value)), "Tushum"]}
                labelFormatter={(label) => `Sana: ${label}`}
              />
              <Bar dataKey="revenue" fill="var(--primary)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Eng ko‘p sotilganlar (30 kun)</CardTitle>
          </CardHeader>
          <CardContent>
            {data.best_sellers.length === 0 ? (
              <p className="text-muted-foreground text-sm">Hali sotuvlar yo‘q.</p>
            ) : (
              <ol className="grid gap-2 text-sm">
                {data.best_sellers.map((p, i) => (
                  <li key={`${p.product_id}-${i}`} className="flex justify-between gap-2">
                    <span>
                      {i + 1}. {p.product_name}
                    </span>
                    <span className="text-muted-foreground whitespace-nowrap">
                      {p.units} dona · {formatUZS(p.revenue)}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Kam qolgan mahsulotlar</CardTitle>
            <CardDescription>
              <Link href="/inventory" className="underline">
                Omborga o‘tish
              </Link>
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data.low_stock.length === 0 ? (
              <p className="text-muted-foreground text-sm">Hammasi yetarli.</p>
            ) : (
              <ul className="grid gap-2 text-sm">
                {data.low_stock.map((s) => (
                  <li key={s.variant_id} className="flex justify-between gap-2">
                    <span>
                      {s.product_name}
                      {s.variant_name ? ` (${s.variant_name})` : ""}{" "}
                      <span className="text-muted-foreground">· {s.sku}</span>
                    </span>
                    <span className={s.available <= 0 ? "text-destructive font-medium" : ""}>
                      {s.available} dona
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { can } = useAuth();
  if (!can("dashboard.view")) {
    // Operators have no dashboard; send them to their main work.
    return (
      <div className="grid gap-4">
        <PageHeader title="Xush kelibsiz" description="Buyurtmalar bo‘limidan ishni boshlang." />
        <Link href="/orders" className="underline">
          Buyurtmalarga o‘tish
        </Link>
      </div>
    );
  }
  return (
    <RequirePermission permission="dashboard.view">
      <PageHeader
        title="Bosh sahifa"
        description="Do‘kon ko‘rsatkichlari"
        actions={<SystemStatus compact />}
      />
      <DashboardView />
    </RequirePermission>
  );
}
