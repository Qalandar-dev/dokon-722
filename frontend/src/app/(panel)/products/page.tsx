"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Pagination } from "@/components/layout/pagination";
import { RequirePermission } from "@/components/layout/require";
import { EmptyState, ErrorState, LoadingRows } from "@/components/layout/states";
import { Badge } from "@/components/ui/badge";
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
import { categoriesQuery, categoryOptions } from "@/features/products/api";
import { apiRequest } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { formatUZS } from "@/lib/format";
import type { AdminProduct, Page } from "@/types/api";

export default function ProductsPage() {
  const { can } = useAuth();
  const [filters, setFilters] = useState({
    q: "",
    category_id: "",
    is_active: "",
    low_stock: false,
  });
  const [page, setPage] = useState(1);
  const categories = useQuery(categoriesQuery);
  const query = useQuery({
    queryKey: ["products", filters, page],
    queryFn: () =>
      apiRequest<Page<AdminProduct>>("/admin/products", {
        query: { ...filters, low_stock: filters.low_stock || undefined, page, page_size: 20 },
      }),
    placeholderData: (prev) => prev,
  });
  const update = (patch: Partial<typeof filters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  return (
    <RequirePermission permission="products.view">
      <PageHeader
        title="Mahsulotlar"
        actions={
          can("products.manage") ? (
            <Button asChild>
              <Link href="/products/new">
                <Plus aria-hidden /> Yangi mahsulot
              </Link>
            </Button>
          ) : null
        }
      />
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Input
          placeholder="Nomi yoki SKU"
          aria-label="Qidirish"
          value={filters.q}
          onChange={(e) => update({ q: e.target.value })}
        />
        <NativeSelect
          aria-label="Kategoriya"
          value={filters.category_id}
          onChange={(e) => update({ category_id: e.target.value })}
        >
          <option value="">Barcha kategoriyalar</option>
          {categoryOptions(categories.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Holati"
          value={filters.is_active}
          onChange={(e) => update({ is_active: e.target.value })}
        >
          <option value="">Faol va nofaol</option>
          <option value="true">Faqat faol</option>
          <option value="false">Faqat nofaol</option>
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={filters.low_stock}
            onChange={(e) => update({ low_stock: e.target.checked })}
          />
          Faqat kam qolganlar
        </label>
      </div>
      {query.isPending ? (
        <LoadingRows />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title="Mahsulotlar topilmadi" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-14"></TableHead>
                <TableHead>Nomi</TableHead>
                <TableHead>Kategoriya</TableHead>
                <TableHead>Narx</TableHead>
                <TableHead>Qoldiq</TableHead>
                <TableHead>Holati</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.items.map((p) => {
                const prices = p.variants.map((v) => Number(v.discount_price ?? v.price));
                const stock = p.variants.reduce((sum, v) => sum + v.available, 0);
                return (
                  <TableRow key={p.id}>
                    <TableCell>
                      {p.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element -- user uploads served by Nginx
                        <img src={p.image_url} alt="" className="size-10 rounded object-cover" />
                      ) : (
                        <div className="bg-muted size-10 rounded" />
                      )}
                    </TableCell>
                    <TableCell>
                      <Link href={`/products/${p.id}`} className="font-medium hover:underline">
                        {p.name}
                      </Link>
                      <div className="text-muted-foreground text-xs">
                        {p.variants.map((v) => v.sku).join(", ")}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{p.category_name}</TableCell>
                    <TableCell className="whitespace-nowrap">
                      {prices.length ? formatUZS(Math.min(...prices)) : "—"}
                    </TableCell>
                    <TableCell className={stock <= 0 ? "text-destructive font-medium" : ""}>
                      {stock}
                    </TableCell>
                    <TableCell>
                      <Badge variant={p.is_active ? "success" : "secondary"}>
                        {p.is_active ? "Faol" : "Nofaol"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                );
              })}
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
