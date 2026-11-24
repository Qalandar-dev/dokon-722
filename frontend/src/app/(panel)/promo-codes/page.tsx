"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ConfirmButton } from "@/components/layout/confirm-dialog";
import { Field } from "@/components/layout/field";
import { PageHeader } from "@/components/layout/page-header";
import { Pagination } from "@/components/layout/pagination";
import { RequirePermission } from "@/components/layout/require";
import { EmptyState, ErrorState, LoadingRows } from "@/components/layout/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
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
import { useAction } from "@/lib/mutation";
import type { Page, Promo } from "@/types/api";

const amount = z
  .string()
  .trim()
  .regex(/^\d+(\.\d{1,2})?$/, "Raqam kiriting");
const optionalAmount = z.union([amount, z.literal("")]);
const optionalInt = z.union([
  z
    .string()
    .trim()
    .regex(/^[1-9]\d*$/, "Musbat butun son"),
  z.literal(""),
]);

const schema = z
  .object({
    code: z
      .string()
      .trim()
      .min(2, "Kamida 2 belgi")
      .max(32)
      .regex(/^[A-Za-z0-9_-]+$/, "Faqat harf, raqam, - va _"),
    description: z.string().trim().max(2000),
    discount_type: z.enum(["percent", "fixed"]),
    value: amount,
    max_discount: optionalAmount,
    min_order_amount: optionalAmount,
    starts_at: z.string(),
    ends_at: z.string(),
    usage_limit: optionalInt,
    per_user_limit: optionalInt,
    is_active: z.boolean(),
  })
  .refine((v) => v.discount_type !== "percent" || Number(v.value) <= 100, {
    message: "Foiz 100 dan oshmasin",
    path: ["value"],
  })
  .refine((v) => !v.starts_at || !v.ends_at || v.ends_at > v.starts_at, {
    message: "Tugash sanasi keyinroq bo‘lsin",
    path: ["ends_at"],
  });
type Values = z.infer<typeof schema>;

const empty: Values = {
  code: "",
  description: "",
  discount_type: "percent",
  value: "",
  max_discount: "",
  min_order_amount: "",
  starts_at: "",
  ends_at: "",
  usage_limit: "",
  per_user_limit: "",
  is_active: true,
};

const toLocalInput = (iso: string | null) => (iso ? new Date(iso).toISOString().slice(0, 16) : "");
const fromLocalInput = (value: string) => (value ? new Date(value).toISOString() : null);

export default function PromoCodesPage() {
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Promo | null>(null);
  const [open, setOpen] = useState(false);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: empty });
  const query = useQuery({
    queryKey: ["promo", page],
    queryFn: () =>
      apiRequest<Page<Promo>>("/admin/promo-codes", { query: { page, page_size: 20 } }),
  });
  useEffect(() => {
    form.reset(
      editing
        ? {
            code: editing.code,
            description: editing.description ?? "",
            discount_type: editing.discount_type,
            value: String(Number(editing.value)),
            max_discount: editing.max_discount ? String(Number(editing.max_discount)) : "",
            min_order_amount: String(Number(editing.min_order_amount)),
            starts_at: toLocalInput(editing.starts_at),
            ends_at: toLocalInput(editing.ends_at),
            usage_limit: editing.usage_limit ? String(editing.usage_limit) : "",
            per_user_limit: editing.per_user_limit ? String(editing.per_user_limit) : "",
            is_active: editing.is_active,
          }
        : empty,
    );
  }, [editing, open, form]);

  const save = useAction(
    (v: Values) => {
      const body = {
        ...v,
        description: v.description || null,
        max_discount: v.max_discount || null,
        min_order_amount: v.min_order_amount || "0",
        starts_at: fromLocalInput(v.starts_at) ?? undefined,
        ends_at: fromLocalInput(v.ends_at),
        usage_limit: v.usage_limit ? Number(v.usage_limit) : null,
        per_user_limit: v.per_user_limit ? Number(v.per_user_limit) : null,
      };
      return editing
        ? apiRequest(`/admin/promo-codes/${editing.id}`, { method: "PATCH", body })
        : apiRequest("/admin/promo-codes", { method: "POST", body });
    },
    { success: "Promokod saqlandi", invalidate: [["promo"]] },
  );
  const remove = useAction(
    async (id: string) => {
      const r = await apiRequest<{ deleted: boolean }>(`/admin/promo-codes/${id}`, {
        method: "DELETE",
      });
      toast.success(
        r.deleted ? "Promokod o‘chirildi" : "Promokod ishlatilgan, shuning uchun faolsizlantirildi",
      );
    },
    { invalidate: [["promo"]] },
  );
  const errors = form.formState.errors;

  return (
    <RequirePermission permission="promo.manage">
      <PageHeader
        title="Promokodlar"
        actions={
          <Button
            onClick={() => {
              setEditing(null);
              setOpen(true);
            }}
          >
            <Plus aria-hidden /> Yangi promokod
          </Button>
        }
      />
      {query.isPending ? (
        <LoadingRows />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title="Promokodlar yo‘q" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kod</TableHead>
                <TableHead>Chegirma</TableHead>
                <TableHead>Shartlar</TableHead>
                <TableHead>Ishlatilgan</TableHead>
                <TableHead>Muddat</TableHead>
                <TableHead>Holati</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.items.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-mono font-medium">{p.code}</TableCell>
                  <TableCell>
                    {p.discount_type === "percent" ? `${Number(p.value)}%` : formatUZS(p.value)}
                    {p.max_discount ? ` (≤ ${formatUZS(p.max_discount)})` : ""}
                  </TableCell>
                  <TableCell className="text-xs">
                    {Number(p.min_order_amount) > 0 ? `≥ ${formatUZS(p.min_order_amount)}` : "—"}
                    {p.per_user_limit ? `, mijozga ${p.per_user_limit} marta` : ""}
                  </TableCell>
                  <TableCell>
                    {p.used_count}
                    {p.usage_limit ? ` / ${p.usage_limit}` : ""}
                  </TableCell>
                  <TableCell className="text-xs">
                    {formatDate(p.starts_at)} — {p.ends_at ? formatDate(p.ends_at) : "∞"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={p.is_active ? "success" : "secondary"}>
                      {p.is_active ? "Faol" : "Nofaol"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="Tahrirlash"
                      onClick={() => {
                        setEditing(p);
                        setOpen(true);
                      }}
                    >
                      <Pencil />
                    </Button>
                    <ConfirmButton
                      variant="ghost"
                      size="icon"
                      destructive
                      title={`${p.code} o‘chirilsinmi?`}
                      description="Ishlatilgan promokod o‘chirilmaydi, faqat faolsizlantiriladi."
                      confirmLabel="O‘chirish"
                      onConfirm={() => remove.mutateAsync(p.id)}
                    >
                      <Trash2 aria-label="O‘chirish" />
                    </ConfirmButton>
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
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editing ? `Promokod ${editing.code}` : "Yangi promokod"}</DialogTitle>
          </DialogHeader>
          <form
            noValidate
            className="grid gap-4 sm:grid-cols-2"
            onSubmit={form.handleSubmit(async (v) => {
              if (await save.run(v)) setOpen(false);
            })}
          >
            <Field id="code" label="Kod" error={errors.code?.message}>
              <Input id="code" className="uppercase" {...form.register("code")} />
            </Field>
            <Field id="discount_type" label="Turi">
              <NativeSelect id="discount_type" {...form.register("discount_type")}>
                <option value="percent">Foiz (%)</option>
                <option value="fixed">Aniq summa (so‘m)</option>
              </NativeSelect>
            </Field>
            <Field id="value" label="Qiymati" error={errors.value?.message}>
              <Input id="value" inputMode="decimal" {...form.register("value")} />
            </Field>
            <Field
              id="max_discount"
              label="Eng katta chegirma (so‘m)"
              error={errors.max_discount?.message}
            >
              <Input id="max_discount" inputMode="decimal" {...form.register("max_discount")} />
            </Field>
            <Field
              id="min_order_amount"
              label="Eng kam buyurtma (so‘m)"
              error={errors.min_order_amount?.message}
            >
              <Input
                id="min_order_amount"
                inputMode="decimal"
                {...form.register("min_order_amount")}
              />
            </Field>
            <Field id="usage_limit" label="Umumiy limit" error={errors.usage_limit?.message}>
              <Input id="usage_limit" inputMode="numeric" {...form.register("usage_limit")} />
            </Field>
            <Field
              id="per_user_limit"
              label="Har bir mijozga"
              error={errors.per_user_limit?.message}
            >
              <Input id="per_user_limit" inputMode="numeric" {...form.register("per_user_limit")} />
            </Field>
            <div />
            <Field id="starts_at" label="Boshlanish">
              <Input id="starts_at" type="datetime-local" {...form.register("starts_at")} />
            </Field>
            <Field id="ends_at" label="Tugash" error={errors.ends_at?.message}>
              <Input id="ends_at" type="datetime-local" {...form.register("ends_at")} />
            </Field>
            <div className="sm:col-span-2">
              <Field id="description" label="Izoh">
                <Textarea id="description" {...form.register("description")} />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" {...form.register("is_active")} /> Faol
            </label>
            <Button
              type="submit"
              disabled={save.isPending}
              className="justify-self-start sm:col-span-2"
            >
              Saqlash
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </RequirePermission>
  );
}
