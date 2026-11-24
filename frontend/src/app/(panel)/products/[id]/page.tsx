"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ImagePlus, Pencil, Plus, Star, Trash2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ConfirmButton } from "@/components/layout/confirm-dialog";
import { Field } from "@/components/layout/field";
import { PageHeader } from "@/components/layout/page-header";
import { RequirePermission } from "@/components/layout/require";
import { ErrorState, LoadingRows } from "@/components/layout/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import {
  categoriesQuery,
  categoryOptions,
  updateProduct,
  updateVariant,
} from "@/features/products/api";
import { VariantFields } from "@/features/products/variant-fields";
import {
  emptyVariant,
  formatAttributes,
  variantPayload,
  variantSchema,
  type VariantForm,
} from "@/features/products/variant-schema";
import { apiRequest } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { formatUZS } from "@/lib/format";
import { useAction } from "@/lib/mutation";
import type { AdminProduct, AdminVariant } from "@/types/api";

const productSchema = z.object({
  name: z.string().trim().min(1, "Nomini kiriting").max(200),
  category_id: z.string().min(1),
  brand: z.string().trim().max(100),
  description: z.string().trim().max(10000),
  is_active: z.boolean(),
  is_featured: z.boolean(),
});
type ProductValues = z.infer<typeof productSchema>;

function VariantDialog({
  productId,
  variant,
  open,
  onOpenChange,
  invalidate,
}: {
  productId: string;
  variant: AdminVariant | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  invalidate: string[][];
}) {
  const form = useForm<VariantForm>({
    resolver: zodResolver(variantSchema),
    defaultValues: emptyVariant,
  });
  useEffect(() => {
    form.reset(
      variant
        ? {
            sku: variant.sku,
            name: variant.name,
            attributes: formatAttributes(variant.attributes),
            price: String(Number(variant.price)),
            discount_price: variant.discount_price ? String(Number(variant.discount_price)) : "",
            initial_stock: 0,
            ikpu_code: variant.ikpu_code ?? "",
            is_default: variant.is_default,
          }
        : emptyVariant,
    );
  }, [variant, open, form]);
  const save = useAction(
    (v: VariantForm) => {
      const payload = variantPayload(v);
      if (variant) {
        // Stock of an existing variant changes only through inventory adjustments.
        const { initial_stock, ...changes } = payload;
        void initial_stock;
        return updateVariant(variant.id, changes);
      }
      return apiRequest(`/admin/products/${productId}/variants`, { method: "POST", body: payload });
    },
    { success: "Variant saqlandi", invalidate },
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{variant ? `Variant: ${variant.sku}` : "Yangi variant"}</DialogTitle>
        </DialogHeader>
        <form
          noValidate
          className="grid gap-4"
          onSubmit={form.handleSubmit(async (v) => {
            if (await save.run(v)) onOpenChange(false);
          })}
        >
          <VariantFields
            prefix=""
            register={form.register}
            errors={form.formState.errors}
            showStock={!variant}
          />
          <Button type="submit" disabled={save.isPending} className="justify-self-start">
            Saqlash
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { can } = useAuth();
  const manage = can("products.manage");
  const key = ["products", id];
  const invalidate = [key, ["products"]];
  const query = useQuery({
    queryKey: key,
    queryFn: () => apiRequest<AdminProduct>(`/admin/products/${id}`),
  });
  const categories = useQuery(categoriesQuery);
  const form = useForm<ProductValues>({ resolver: zodResolver(productSchema) });
  const fileInput = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<AdminVariant | null>(null);
  const [variantOpen, setVariantOpen] = useState(false);

  useEffect(() => {
    const p = query.data;
    if (p) {
      form.reset({
        name: p.name,
        category_id: p.category_id,
        brand: p.brand ?? "",
        description: p.description ?? "",
        is_active: p.is_active,
        is_featured: p.is_featured,
      });
    }
  }, [query.data, form]);

  const save = useAction(
    (v: ProductValues) =>
      updateProduct(id, { ...v, brand: v.brand || null, description: v.description || null }),
    { success: "Saqlandi", invalidate },
  );
  const upload = useAction(
    (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return apiRequest(`/admin/products/${id}/images`, { method: "POST", body });
    },
    { success: "Rasm yuklandi", invalidate },
  );
  const setMain = useAction(
    (imageId: string) =>
      apiRequest(`/admin/product-images/${imageId}`, { method: "PATCH", body: { is_main: true } }),
    { invalidate },
  );
  const removeImage = useAction(
    (imageId: string) => apiRequest(`/admin/product-images/${imageId}`, { method: "DELETE" }),
    { success: "Rasm o‘chirildi", invalidate },
  );
  const toggleVariant = useAction(
    (v: AdminVariant) => updateVariant(v.id, { is_active: !v.is_active }),
    { success: "Variant yangilandi", invalidate },
  );
  const remove = useAction(() => apiRequest(`/admin/products/${id}`, { method: "DELETE" }), {
    success: "Mahsulot o‘chirildi",
    invalidate: [["products"]],
  });

  if (query.isPending) return <LoadingRows rows={8} />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const p = query.data;
  const errors = form.formState.errors;

  return (
    <RequirePermission permission="products.view">
      <PageHeader
        title={p.name}
        description={`Sotilgan: ${p.sold_count} dona`}
        actions={
          manage ? (
            <ConfirmButton
              destructive
              variant="destructive"
              title="Mahsulot o‘chirilsinmi?"
              description="Mahsulot katalogdan yashiriladi. Eski buyurtmalardagi ma’lumotlar saqlanib qoladi."
              confirmLabel="O‘chirish"
              onConfirm={async () => {
                await remove.mutateAsync(undefined);
                router.push("/products");
              }}
            >
              <Trash2 aria-hidden /> O‘chirish
            </ConfirmButton>
          ) : null
        }
      />
      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Asosiy ma’lumotlar</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              noValidate
              className="grid gap-4 sm:grid-cols-2"
              onSubmit={form.handleSubmit((v) => save.mutate(v))}
            >
              <fieldset disabled={!manage} className="contents">
                <Field id="name" label="Nomi" error={errors.name?.message}>
                  <Input id="name" {...form.register("name")} />
                </Field>
                <Field id="category_id" label="Kategoriya">
                  <NativeSelect id="category_id" {...form.register("category_id")}>
                    {categoryOptions(categories.data ?? []).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field id="brand" label="Brend">
                  <Input id="brand" {...form.register("brand")} />
                </Field>
                <div className="flex items-end gap-6 pb-2 text-sm">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" {...form.register("is_active")} /> Sotuvda
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" {...form.register("is_featured")} /> Tavsiya etilgan
                  </label>
                </div>
                <div className="sm:col-span-2">
                  <Field id="description" label="Tavsif">
                    <Textarea id="description" rows={5} {...form.register("description")} />
                  </Field>
                </div>
                {manage ? (
                  <Button type="submit" disabled={save.isPending} className="justify-self-start">
                    Saqlash
                  </Button>
                ) : null}
              </fieldset>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Rasmlar</CardTitle>
            {manage ? (
              <>
                <input
                  ref={fileInput}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  aria-label="Rasm tanlash"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) upload.mutate(file);
                    e.target.value = "";
                  }}
                />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={upload.isPending}
                  onClick={() => fileInput.current?.click()}
                >
                  <ImagePlus aria-hidden /> Rasm yuklash
                </Button>
              </>
            ) : null}
          </CardHeader>
          <CardContent>
            {p.images.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Rasm yo‘q. JPG, PNG yoki WEBP, 5 MB gacha.
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
                {p.images.map((img) => (
                  <div key={img.id} className="relative overflow-hidden rounded-lg border">
                    {/* eslint-disable-next-line @next/next/no-img-element -- user uploads served by Nginx */}
                    <img
                      src={img.url}
                      alt={img.alt_text ?? ""}
                      className="aspect-square w-full object-cover"
                    />
                    {img.is_main ? <Badge className="absolute top-1 left-1">Asosiy</Badge> : null}
                    {manage ? (
                      <div className="absolute right-1 bottom-1 flex gap-1">
                        {!img.is_main ? (
                          <Button
                            size="icon"
                            variant="secondary"
                            aria-label="Asosiy qilish"
                            onClick={() => setMain.mutate(img.id)}
                          >
                            <Star />
                          </Button>
                        ) : null}
                        <Button
                          size="icon"
                          variant="destructive"
                          aria-label="Rasmni o‘chirish"
                          onClick={() => removeImage.mutate(img.id)}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Variantlar</CardTitle>
            {manage ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setEditing(null);
                  setVariantOpen(true);
                }}
              >
                <Plus aria-hidden /> Variant qo‘shish
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead>Nomi</TableHead>
                  <TableHead>Narx</TableHead>
                  <TableHead>Qoldiq</TableHead>
                  <TableHead>Band</TableHead>
                  <TableHead>Holati</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {p.variants.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell className="font-mono text-xs">
                      {v.sku}
                      {v.is_default ? " ★" : ""}
                    </TableCell>
                    <TableCell>{v.name || formatAttributes(v.attributes) || "—"}</TableCell>
                    <TableCell className="whitespace-nowrap">
                      {v.discount_price ? (
                        <>
                          {formatUZS(v.discount_price)}{" "}
                          <s className="text-muted-foreground text-xs">{formatUZS(v.price)}</s>
                        </>
                      ) : (
                        formatUZS(v.price)
                      )}
                    </TableCell>
                    <TableCell className={v.available <= 0 ? "text-destructive font-medium" : ""}>
                      {v.on_hand}
                    </TableCell>
                    <TableCell>{v.reserved}</TableCell>
                    <TableCell>
                      <Badge variant={v.is_active ? "success" : "secondary"}>
                        {v.is_active ? "Faol" : "Nofaol"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      {manage ? (
                        <>
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label="Tahrirlash"
                            onClick={() => {
                              setEditing(v);
                              setVariantOpen(true);
                            }}
                          >
                            <Pencil />
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => toggleVariant.mutate(v)}>
                            {v.is_active ? "O‘chirish" : "Yoqish"}
                          </Button>
                        </>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="text-muted-foreground mt-2 text-xs">
              Qoldiqni «Ombor» bo‘limida o‘zgartiring (har bir o‘zgarish sababi bilan yoziladi).
            </p>
          </CardContent>
        </Card>
      </div>
      <VariantDialog
        productId={id}
        variant={editing}
        open={variantOpen}
        onOpenChange={setVariantOpen}
        invalidate={invalidate}
      />
    </RequirePermission>
  );
}
