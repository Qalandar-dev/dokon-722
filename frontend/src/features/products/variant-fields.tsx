"use client";

import type { FieldErrors, UseFormRegister } from "react-hook-form";

import { Field } from "@/components/layout/field";
import { Input } from "@/components/ui/input";

import type { VariantForm } from "./variant-schema";

/** Inputs for one variant; `prefix` is the react-hook-form path ("variants.0" or ""). */
export function VariantFields({
  prefix,
  register,
  errors,
  showStock = true,
}: {
  prefix: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- shared by two form shapes
  register: UseFormRegister<any>;
  errors?: FieldErrors<VariantForm>;
  showStock?: boolean;
}) {
  const p = (name: keyof VariantForm) => (prefix ? `${prefix}.${name}` : name);
  const id = (name: string) => `${prefix || "v"}-${name}`.replace(/\./g, "-");
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Field id={id("sku")} label="SKU (artikul)" error={errors?.sku?.message}>
        <Input id={id("sku")} {...register(p("sku"))} aria-invalid={!!errors?.sku} />
      </Field>
      <Field id={id("name")} label="Variant nomi" hint="Masalan: M / Qora">
        <Input id={id("name")} {...register(p("name"))} />
      </Field>
      <Field id={id("price")} label="Narx (so‘m)" error={errors?.price?.message}>
        <Input
          id={id("price")}
          inputMode="decimal"
          {...register(p("price"))}
          aria-invalid={!!errors?.price}
        />
      </Field>
      <Field
        id={id("discount_price")}
        label="Chegirma narxi"
        error={errors?.discount_price?.message}
      >
        <Input
          id={id("discount_price")}
          inputMode="decimal"
          {...register(p("discount_price"))}
          aria-invalid={!!errors?.discount_price}
        />
      </Field>
      <Field id={id("attributes")} label="Xususiyatlar" hint="o‘lcham: M; rang: qora">
        <Input id={id("attributes")} {...register(p("attributes"))} />
      </Field>
      {showStock ? (
        <Field
          id={id("initial_stock")}
          label="Boshlang‘ich qoldiq"
          error={errors?.initial_stock?.message}
        >
          <Input
            id={id("initial_stock")}
            type="number"
            min={0}
            {...register(p("initial_stock"), { valueAsNumber: true })}
          />
        </Field>
      ) : null}
      <Field id={id("ikpu_code")} label="IKPU kodi" hint="Ixtiyoriy (soliq cheki uchun)">
        <Input id={id("ikpu_code")} {...register(p("ikpu_code"))} />
      </Field>
      <label className="flex items-center gap-2 self-end pb-2 text-sm">
        <input type="checkbox" {...register(p("is_default"))} /> Asosiy variant
      </label>
    </div>
  );
}
