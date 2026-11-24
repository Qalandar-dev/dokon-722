import { z } from "zod";

const money = z
  .string()
  .trim()
  .regex(/^\d+(\.\d{1,2})?$/, "Narxni raqam bilan yozing");

export const variantSchema = z
  .object({
    sku: z.string().trim().min(1, "SKU kiriting").max(64),
    name: z.string().trim().max(120),
    attributes: z.string().trim().max(500),
    price: money,
    discount_price: z.union([money, z.literal("")]),
    initial_stock: z.number({ error: "Son kiriting" }).int().min(0, "Manfiy bo‘lmasin"),
    ikpu_code: z.string().trim().max(32),
    is_default: z.boolean(),
  })
  .refine((v) => !v.discount_price || Number(v.discount_price) < Number(v.price), {
    message: "Chegirma narxi asosiy narxdan kichik bo‘lsin",
    path: ["discount_price"],
  });

export type VariantForm = z.infer<typeof variantSchema>;

export const emptyVariant: VariantForm = {
  sku: "",
  name: "",
  attributes: "",
  price: "",
  discount_price: "",
  initial_stock: 0,
  ikpu_code: "",
  is_default: false,
};

/** "o‘lcham: M; rang: qora" → {"o‘lcham": "M", "rang": "qora"} */
export function parseAttributes(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of text.split(";")) {
    const [key, ...rest] = part.split(":");
    const k = key?.trim();
    const v = rest.join(":").trim();
    if (k && v) out[k] = v;
  }
  return out;
}

export function formatAttributes(attrs: Record<string, string>): string {
  return Object.entries(attrs)
    .map(([k, v]) => `${k}: ${v}`)
    .join("; ");
}

export function variantPayload(v: VariantForm) {
  return {
    sku: v.sku,
    name: v.name,
    attributes: parseAttributes(v.attributes),
    price: v.price,
    discount_price: v.discount_price || null,
    ikpu_code: v.ikpu_code || null,
    is_default: v.is_default,
    initial_stock: v.initial_stock,
  };
}
