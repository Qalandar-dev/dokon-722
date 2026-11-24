import { describe, expect, it } from "vitest";

import {
  emptyVariant,
  formatAttributes,
  parseAttributes,
  variantPayload,
  variantSchema,
} from "./variant-schema";

describe("variant form", () => {
  it("parses and formats attributes", () => {
    const attrs = parseAttributes("o‘lcham: M; rang: qora ; bo‘sh:; :x");
    expect(attrs).toEqual({ "o‘lcham": "M", rang: "qora" });
    expect(formatAttributes(attrs)).toBe("o‘lcham: M; rang: qora");
  });

  it("rejects a discount that is not below the price", () => {
    const result = variantSchema.safeParse({
      ...emptyVariant,
      sku: "A1",
      price: "100000",
      discount_price: "100000",
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path).toEqual(["discount_price"]);
  });

  it("rejects non-numeric prices and builds the API payload", () => {
    expect(variantSchema.safeParse({ ...emptyVariant, sku: "A1", price: "yuz ming" }).success).toBe(
      false,
    );
    const ok = variantSchema.parse({
      ...emptyVariant,
      sku: "A1",
      price: "150000",
      attributes: "rang: oq",
      initial_stock: 4,
    });
    expect(variantPayload(ok)).toMatchObject({
      sku: "A1",
      price: "150000",
      discount_price: null,
      attributes: { rang: "oq" },
      initial_stock: 4,
    });
  });
});
