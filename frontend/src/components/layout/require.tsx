"use client";

import type { ReactNode } from "react";

import { useAuth } from "@/lib/auth";
import type { Permission } from "@/types/api";

/** Page-level guard. The API enforces permissions too; this only avoids a useless page. */
export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const { can } = useAuth();
  if (!can(permission)) {
    return (
      <div role="alert" className="rounded-lg border p-6 text-sm">
        Bu bo‘limni ko‘rish uchun ruxsatingiz yo‘q.
      </div>
    );
  }
  return <>{children}</>;
}
