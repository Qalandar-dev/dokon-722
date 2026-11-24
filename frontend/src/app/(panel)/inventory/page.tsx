"use client";

import { useQuery } from "@tanstack/react-query";
import { History, SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import { Field } from "@/components/layout/field";
import { PageHeader } from "@/components/layout/page-header";
import { Pagination } from "@/components/layout/pagination";
import { RequirePermission } from "@/components/layout/require";
import { EmptyState, ErrorState, LoadingRows } from "@/components/layout/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
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
import { formatDateTime } from "@/lib/format";
import { useAction } from "@/lib/mutation";
import type { Movement, Page, StockRow } from "@/types/api";

const MOVEMENT: Record<string, string> = {
  restock: "Kirim",
  adjustment: "Tuzatish",
  reserve: "Band qilindi",
  release: "Band bekor",
  sale: "Sotildi",
  return: "Qaytdi",
};

function MovementsDialog({ row, onClose }: { row: StockRow | null; onClose: () => void }) {
  const query = useQuery({
    queryKey: ["movements", row?.variant_id],
    queryFn: () =>
      apiRequest<Page<Movement>>(`/admin/inventory/${row!.variant_id}/movements`, {
        query: { page_size: 50 },
      }),
    enabled: !!row,
  });
  return (
    <Dialog open={!!row} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Harakatlar tarixi</DialogTitle>
          <DialogDescription>
            {row?.product_name} · {row?.sku}
          </DialogDescription>
        </DialogHeader>
        {query.isPending ? (
          <LoadingRows rows={3} />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sana</TableHead>
                <TableHead>Turi</TableHead>
                <TableHead>O‘zgarish</TableHead>
                <TableHead>Keyin</TableHead>
                <TableHead>Sabab</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.items.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="text-xs whitespace-nowrap">
                    {formatDateTime(m.created_at)}
                  </TableCell>
                  <TableCell>{MOVEMENT[m.type] ?? m.type}</TableCell>
                  <TableCell className="text-xs">
                    {m.on_hand_delta
                      ? `qoldiq ${m.on_hand_delta > 0 ? "+" : ""}${m.on_hand_delta}`
                      : ""}
                    {m.reserved_delta
                      ? ` band ${m.reserved_delta > 0 ? "+" : ""}${m.reserved_delta}`
                      : ""}
                  </TableCell>
                  <TableCell className="text-xs">
                    {m.on_hand_after} / {m.reserved_after}
                  </TableCell>
                  <TableCell className="text-xs">
                    {m.reason ?? (m.order_id ? "Buyurtma" : "—")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function InventoryPage() {
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [adjusting, setAdjusting] = useState<StockRow | null>(null);
  const [history, setHistory] = useState<StockRow | null>(null);
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");
  const query = useQuery({
    queryKey: ["inventory", q, lowOnly, page],
    queryFn: () =>
      apiRequest<Page<StockRow>>("/admin/inventory", {
        query: { q, low_only: lowOnly || undefined, page, page_size: 50 },
      }),
    placeholderData: (prev) => prev,
  });
  const adjust = useAction(
    () =>
      apiRequest(`/admin/inventory/${adjusting!.variant_id}/adjust`, {
        method: "POST",
        body: { delta: Number(delta), reason },
      }),
    { success: "Qoldiq yangilandi", invalidate: [["inventory"], ["products"], ["dashboard"]] },
  );
  const deltaValid = /^-?\d+$/.test(delta.trim()) && Number(delta) !== 0;

  return (
    <RequirePermission permission="inventory.view">
      <PageHeader
        title="Ombor"
        description="Qoldiq = jismoniy mavjud; band = to‘lanmagan buyurtmalar uchun ushlab turilgan"
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          placeholder="Nomi yoki SKU"
          aria-label="Qidirish"
          className="max-w-xs"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={lowOnly}
            onChange={(e) => {
              setLowOnly(e.target.checked);
              setPage(1);
            }}
          />{" "}
          Faqat kam qolganlar
        </label>
      </div>
      {query.isPending ? (
        <LoadingRows />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title="Hech narsa topilmadi" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Mahsulot</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead>Qoldiq</TableHead>
                <TableHead>Band</TableHead>
                <TableHead>Sotish mumkin</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.items.map((r) => (
                <TableRow key={r.variant_id}>
                  <TableCell>
                    {r.product_name}
                    {r.variant_name ? (
                      <span className="text-muted-foreground"> ({r.variant_name})</span>
                    ) : null}
                    {!r.is_active ? (
                      <Badge variant="secondary" className="ml-2">
                        Nofaol
                      </Badge>
                    ) : null}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{r.sku}</TableCell>
                  <TableCell>{r.on_hand}</TableCell>
                  <TableCell>{r.reserved}</TableCell>
                  <TableCell>
                    <Badge
                      variant={r.available <= 0 ? "destructive" : r.is_low ? "warning" : "success"}
                    >
                      {r.available}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="Tarix"
                      onClick={() => setHistory(r)}
                    >
                      <History />
                    </Button>
                    {can("inventory.manage") ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setAdjusting(r);
                          setDelta("");
                          setReason("");
                        }}
                      >
                        <SlidersHorizontal aria-hidden /> O‘zgartirish
                      </Button>
                    ) : null}
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
      <Dialog open={!!adjusting} onOpenChange={(o) => !o && setAdjusting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Qoldiqni o‘zgartirish</DialogTitle>
            <DialogDescription>
              {adjusting?.product_name} · {adjusting?.sku} · hozir {adjusting?.on_hand} dona (
              {adjusting?.reserved} band)
            </DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={async (e) => {
              e.preventDefault();
              if (await adjust.run(undefined)) setAdjusting(null);
            }}
          >
            <Field
              id="delta"
              label="O‘zgarish"
              hint="Kirim uchun musbat (20), hisobdan chiqarish uchun manfiy (-3)"
              error={delta && !deltaValid ? "Butun son kiriting (0 emas)" : undefined}
            >
              <Input
                id="delta"
                inputMode="numeric"
                value={delta}
                onChange={(e) => setDelta(e.target.value)}
              />
            </Field>
            <Field id="reason" label="Sabab">
              <Input
                id="reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Yangi partiya, inventarizatsiya, shikastlangan…"
              />
            </Field>
            <Button
              type="submit"
              disabled={!deltaValid || !reason.trim() || adjust.isPending}
              className="justify-self-start"
            >
              Saqlash
            </Button>
          </form>
        </DialogContent>
      </Dialog>
      <MovementsDialog row={history} onClose={() => setHistory(null)} />
    </RequirePermission>
  );
}
