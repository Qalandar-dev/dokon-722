"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Pagination } from "@/components/layout/pagination";
import { RequirePermission } from "@/components/layout/require";
import { EmptyState, ErrorState, LoadingRows } from "@/components/layout/states";
import { NativeSelect } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiRequest } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import type { AuditEntry, Page, Staff } from "@/types/api";

export default function AuditLogPage() {
  const [adminId, setAdminId] = useState("");
  const [page, setPage] = useState(1);
  const staff = useQuery({
    queryKey: ["staff"],
    queryFn: () => apiRequest<Staff[]>("/admin/staff"),
  });
  const query = useQuery({
    queryKey: ["audit", adminId, page],
    queryFn: () =>
      apiRequest<Page<AuditEntry>>("/admin/audit-logs", {
        query: { admin_user_id: adminId, page, page_size: 50 },
      }),
    placeholderData: (prev) => prev,
  });
  const names = new Map(staff.data?.map((s) => [s.id, s.full_name]));
  return (
    <RequirePermission permission="audit.view">
      <PageHeader
        title="Amallar jurnali"
        description="Xodimlar bajargan barcha muhim o‘zgarishlar"
      />
      <NativeSelect
        className="mb-4 w-64"
        aria-label="Xodim"
        value={adminId}
        onChange={(e) => {
          setAdminId(e.target.value);
          setPage(1);
        }}
      >
        <option value="">Barcha xodimlar</option>
        {staff.data?.map((s) => (
          <option key={s.id} value={s.id}>
            {s.full_name}
          </option>
        ))}
      </NativeSelect>
      {query.isPending ? (
        <LoadingRows />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title="Yozuvlar yo‘q" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sana</TableHead>
                <TableHead>Xodim</TableHead>
                <TableHead>Amal</TableHead>
                <TableHead>Obyekt</TableHead>
                <TableHead>O‘zgarishlar</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.items.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="text-xs whitespace-nowrap">
                    {formatDateTime(a.created_at)}
                  </TableCell>
                  <TableCell className="text-sm">
                    {a.admin_user_id ? (names.get(a.admin_user_id) ?? "—") : "Tizim"}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{a.action}</TableCell>
                  <TableCell className="text-xs">
                    {a.entity_type}
                    {a.entity_id ? ` · ${a.entity_id.slice(0, 8)}` : ""}
                  </TableCell>
                  <TableCell
                    className="max-w-md truncate font-mono text-xs"
                    title={JSON.stringify(a.changes)}
                  >
                    {a.changes ? JSON.stringify(a.changes) : "—"}
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
    </RequirePermission>
  );
}
