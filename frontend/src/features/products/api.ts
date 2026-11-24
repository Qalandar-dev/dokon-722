import { apiRequest } from "@/lib/api-client";
import type { AdminCategory, AdminProduct, AdminVariant } from "@/types/api";

export const categoriesQuery = {
  queryKey: ["categories"],
  queryFn: () => apiRequest<AdminCategory[]>("/admin/categories"),
};

/** Categories as indented options ("— Telefonlar") in tree order. */
export function categoryOptions(categories: AdminCategory[]): { id: string; label: string }[] {
  const children = new Map<string | null, AdminCategory[]>();
  for (const c of categories) {
    const list = children.get(c.parent_id) ?? [];
    list.push(c);
    children.set(c.parent_id, list);
  }
  const out: { id: string; label: string }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const c of children.get(parent) ?? []) {
      out.push({
        id: c.id,
        label: `${"— ".repeat(depth)}${c.name}${c.is_active ? "" : " (faol emas)"}`,
      });
      walk(c.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

export function updateProduct(id: string, body: Partial<AdminProduct>) {
  return apiRequest<AdminProduct>(`/admin/products/${id}`, { method: "PATCH", body });
}

export function updateVariant(id: string, body: Record<string, unknown>) {
  return apiRequest<AdminVariant>(`/admin/variants/${id}`, { method: "PATCH", body });
}
