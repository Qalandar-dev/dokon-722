"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ImagePlus, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ConfirmButton } from "@/components/layout/confirm-dialog";
import { Field } from "@/components/layout/field";
import { PageHeader } from "@/components/layout/page-header";
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
import { categoriesQuery, categoryOptions } from "@/features/products/api";
import { apiRequest } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { useAction } from "@/lib/mutation";
import type { AdminCategory } from "@/types/api";

const schema = z.object({
  name: z.string().trim().min(1, "Nomini kiriting").max(128),
  parent_id: z.string(),
  description: z.string().trim().max(2000),
  sort_order: z.number({ error: "Son kiriting" }).int(),
  is_active: z.boolean(),
});
type Values = z.infer<typeof schema>;
const empty: Values = { name: "", parent_id: "", description: "", sort_order: 0, is_active: true };

function depthOf(c: AdminCategory, all: AdminCategory[]): number {
  let depth = 0;
  let parent = c.parent_id;
  while (parent && depth < 10) {
    depth += 1;
    parent = all.find((x) => x.id === parent)?.parent_id ?? null;
  }
  return depth;
}

export default function CategoriesPage() {
  const { can } = useAuth();
  const manage = can("categories.manage");
  const query = useQuery(categoriesQuery);
  const [editing, setEditing] = useState<AdminCategory | null>(null);
  const [open, setOpen] = useState(false);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: empty });
  const invalidate = [["categories"]];

  useEffect(() => {
    form.reset(
      editing
        ? {
            name: editing.name,
            parent_id: editing.parent_id ?? "",
            description: editing.description ?? "",
            sort_order: editing.sort_order,
            is_active: editing.is_active,
          }
        : empty,
    );
  }, [editing, open, form]);

  const save = useAction(
    (v: Values) => {
      const body = { ...v, parent_id: v.parent_id || null, description: v.description || null };
      return editing
        ? apiRequest(`/admin/categories/${editing.id}`, { method: "PATCH", body })
        : apiRequest("/admin/categories", { method: "POST", body });
    },
    { success: "Kategoriya saqlandi", invalidate },
  );
  const remove = useAction(
    (id: string) => apiRequest(`/admin/categories/${id}`, { method: "DELETE" }),
    {
      success: "Kategoriya o‘chirildi",
      invalidate,
    },
  );
  const upload = useAction(
    ({ id, file }: { id: string; file: File }) => {
      const body = new FormData();
      body.append("file", file);
      return apiRequest(`/admin/categories/${id}/image`, { method: "POST", body });
    },
    { success: "Rasm yuklandi", invalidate },
  );

  const all = query.data ?? [];
  const ordered = categoryOptions(all).map((o) => all.find((c) => c.id === o.id)!);
  const parentChoices = categoryOptions(all).filter((o) => o.id !== editing?.id);

  return (
    <RequirePermission permission="products.view">
      <PageHeader
        title="Kategoriyalar"
        description="Ichki kategoriyalar bilan daraxt ko‘rinishida"
        actions={
          manage ? (
            <Button
              onClick={() => {
                setEditing(null);
                setOpen(true);
              }}
            >
              <Plus aria-hidden /> Yangi kategoriya
            </Button>
          ) : null
        }
      />
      {query.isPending ? (
        <LoadingRows />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : all.length === 0 ? (
        <EmptyState title="Kategoriyalar yo‘q" />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nomi</TableHead>
              <TableHead>Mahsulotlar</TableHead>
              <TableHead>Tartib</TableHead>
              <TableHead>Holati</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ordered.map((c) => (
              <TableRow key={c.id}>
                <TableCell>
                  <span
                    style={{ paddingLeft: `${depthOf(c, all) * 1.25}rem` }}
                    className="flex items-center gap-2"
                  >
                    {c.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element -- user uploads served by Nginx
                      <img src={c.image_url} alt="" className="size-7 rounded object-cover" />
                    ) : null}
                    {c.name}
                  </span>
                </TableCell>
                <TableCell>{c.products_count}</TableCell>
                <TableCell>{c.sort_order}</TableCell>
                <TableCell>
                  <Badge variant={c.is_active ? "success" : "secondary"}>
                    {c.is_active ? "Faol" : "Nofaol"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {manage ? (
                    <>
                      <label
                        className="hover:bg-accent inline-flex size-9 cursor-pointer items-center justify-center rounded-md"
                        aria-label="Rasm yuklash"
                      >
                        <ImagePlus className="size-4" aria-hidden />
                        <input
                          type="file"
                          accept="image/jpeg,image/png,image/webp"
                          className="sr-only"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) upload.mutate({ id: c.id, file });
                            e.target.value = "";
                          }}
                        />
                      </label>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Tahrirlash"
                        onClick={() => {
                          setEditing(c);
                          setOpen(true);
                        }}
                      >
                        <Pencil />
                      </Button>
                      <ConfirmButton
                        variant="ghost"
                        size="icon"
                        destructive
                        title={`«${c.name}» o‘chirilsinmi?`}
                        description="Mahsulotlari yoki ichki kategoriyalari bo‘lsa o‘chirilmaydi — avval ularni ko‘chiring yoki kategoriyani faolsizlantiring."
                        confirmLabel="O‘chirish"
                        onConfirm={() => remove.mutateAsync(c.id)}
                      >
                        <Trash2 aria-label="O‘chirish" />
                      </ConfirmButton>
                    </>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Kategoriyani tahrirlash" : "Yangi kategoriya"}</DialogTitle>
          </DialogHeader>
          <form
            noValidate
            className="grid gap-4"
            onSubmit={form.handleSubmit(async (v) => {
              if (await save.run(v)) setOpen(false);
            })}
          >
            <Field id="cat-name" label="Nomi" error={form.formState.errors.name?.message}>
              <Input id="cat-name" {...form.register("name")} />
            </Field>
            <Field id="cat-parent" label="Yuqori kategoriya">
              <NativeSelect id="cat-parent" {...form.register("parent_id")}>
                <option value="">— (asosiy)</option>
                {parentChoices.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="cat-desc" label="Tavsif">
              <Textarea id="cat-desc" {...form.register("description")} />
            </Field>
            <Field id="cat-sort" label="Tartib raqami" hint="Kichik raqam yuqorida turadi">
              <Input
                id="cat-sort"
                type="number"
                {...form.register("sort_order", { valueAsNumber: true })}
              />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" {...form.register("is_active")} /> Faol
            </label>
            <Button type="submit" disabled={save.isPending} className="justify-self-start">
              Saqlash
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </RequirePermission>
  );
}
