"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { Field } from "@/components/layout/field";
import { PageHeader } from "@/components/layout/page-header";
import { RequirePermission } from "@/components/layout/require";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { categoriesQuery, categoryOptions } from "@/features/products/api";
import { VariantFields } from "@/features/products/variant-fields";
import { emptyVariant, variantPayload, variantSchema } from "@/features/products/variant-schema";
import { apiRequest } from "@/lib/api-client";
import { useAction } from "@/lib/mutation";
import type { AdminProduct } from "@/types/api";

const schema = z.object({
  name: z.string().trim().min(1, "Nomini kiriting").max(200),
  category_id: z.string().min(1, "Kategoriyani tanlang"),
  brand: z.string().trim().max(100),
  description: z.string().trim().max(10000),
  is_active: z.boolean(),
  is_featured: z.boolean(),
  variants: z.array(variantSchema).min(1),
});
type Values = z.infer<typeof schema>;

export default function NewProductPage() {
  const router = useRouter();
  const categories = useQuery(categoriesQuery);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      category_id: "",
      brand: "",
      description: "",
      is_active: true,
      is_featured: false,
      variants: [{ ...emptyVariant, is_default: true }],
    },
  });
  const variants = useFieldArray({ control: form.control, name: "variants" });
  const create = useAction(
    (v: Values) =>
      apiRequest<AdminProduct>("/admin/products", {
        method: "POST",
        body: {
          name: v.name,
          category_id: v.category_id,
          brand: v.brand || null,
          description: v.description || null,
          is_active: v.is_active,
          is_featured: v.is_featured,
          variants: v.variants.map(variantPayload),
        },
      }),
    { success: "Mahsulot yaratildi", invalidate: [["products"]] },
  );
  const errors = form.formState.errors;

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const product = await create.mutateAsync(values);
      router.push(`/products/${product.id}`);
    } catch {
      // Shown as a toast by useAction.
    }
  });

  return (
    <RequirePermission permission="products.manage">
      <PageHeader title="Yangi mahsulot" description="Rasmlarni saqlagandan keyin qo‘shasiz" />
      <form onSubmit={onSubmit} className="grid gap-6" noValidate>
        <Card>
          <CardHeader>
            <CardTitle>Asosiy ma’lumotlar</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field id="name" label="Nomi" error={errors.name?.message}>
              <Input id="name" {...form.register("name")} aria-invalid={!!errors.name} />
            </Field>
            <Field id="category_id" label="Kategoriya" error={errors.category_id?.message}>
              <NativeSelect
                id="category_id"
                {...form.register("category_id")}
                aria-invalid={!!errors.category_id}
              >
                <option value="">Tanlang…</option>
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
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Variantlar (o‘lcham, rang…)</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-6">
            {variants.fields.map((field, index) => (
              <div key={field.id} className="grid gap-3 rounded-lg border p-4">
                <VariantFields
                  prefix={`variants.${index}`}
                  register={form.register}
                  errors={errors.variants?.[index]}
                />
                {variants.fields.length > 1 ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="justify-self-start"
                    onClick={() => variants.remove(index)}
                  >
                    <Trash2 aria-hidden /> Variantni olib tashlash
                  </Button>
                ) : null}
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              className="justify-self-start"
              onClick={() => variants.append({ ...emptyVariant })}
            >
              <Plus aria-hidden /> Variant qo‘shish
            </Button>
          </CardContent>
        </Card>
        <div className="flex gap-2">
          <Button type="submit" disabled={form.formState.isSubmitting}>
            Saqlash
          </Button>
          <Button type="button" variant="outline" onClick={() => router.back()}>
            Bekor qilish
          </Button>
        </div>
      </form>
    </RequirePermission>
  );
}
