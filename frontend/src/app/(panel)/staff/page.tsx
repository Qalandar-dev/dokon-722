"use client";

import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { useState } from "react";

import { Field } from "@/components/layout/field";
import { PageHeader } from "@/components/layout/page-header";
import { RequirePermission } from "@/components/layout/require";
import { ErrorState, LoadingRows } from "@/components/layout/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiRequest } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { useAction } from "@/lib/mutation";
import type { Role, Staff } from "@/types/api";

const empty = { email: "", full_name: "", password: "", role: "operator", is_active: true };

export default function StaffPage() {
  const { admin } = useAuth();
  const staff = useQuery({
    queryKey: ["staff"],
    queryFn: () => apiRequest<Staff[]>("/admin/staff"),
  });
  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: () => apiRequest<Role[]>("/admin/roles"),
  });
  const [editing, setEditing] = useState<Staff | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const start = (s: Staff | null) => {
    setEditing(s);
    setForm(
      s
        ? {
            email: s.email,
            full_name: s.full_name,
            password: "",
            role: s.role,
            is_active: s.is_active,
          }
        : empty,
    );
    setOpen(true);
  };
  const save = useAction(
    () =>
      editing
        ? apiRequest(`/admin/staff/${editing.id}`, {
            method: "PATCH",
            body: {
              full_name: form.full_name,
              role: form.role,
              is_active: form.is_active,
              ...(form.password ? { password: form.password } : {}),
            },
          })
        : apiRequest("/admin/staff", {
            method: "POST",
            body: {
              email: form.email,
              full_name: form.full_name,
              password: form.password,
              role: form.role,
            },
          }),
    { success: "Xodim saqlandi", invalidate: [["staff"]] },
  );
  const passwordError = form.password && form.password.length < 10 ? "Kamida 10 belgi" : undefined;
  const valid =
    form.full_name.trim() &&
    (editing || (form.email.includes("@") && form.password.length >= 10)) &&
    !passwordError;

  return (
    <RequirePermission permission="staff.manage">
      <PageHeader
        title="Xodimlar"
        description="Rol o‘zgarsa yoki parol yangilansa, xodimning barcha sessiyalari yopiladi"
        actions={
          <Button onClick={() => start(null)}>
            <Plus aria-hidden /> Yangi xodim
          </Button>
        }
      />
      {staff.isPending ? (
        <LoadingRows />
      ) : staff.error ? (
        <ErrorState error={staff.error} onRetry={() => void staff.refetch()} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Xodim</TableHead>
              <TableHead>Rol</TableHead>
              <TableHead>Oxirgi kirish</TableHead>
              <TableHead>Holati</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {staff.data.map((s) => (
              <TableRow key={s.id}>
                <TableCell>
                  {s.full_name}
                  <div className="text-muted-foreground text-xs">{s.email}</div>
                </TableCell>
                <TableCell>{s.role_title}</TableCell>
                <TableCell className="text-xs">{formatDateTime(s.last_login_at)}</TableCell>
                <TableCell>
                  <Badge variant={s.is_active ? "success" : "secondary"}>
                    {s.is_active ? "Faol" : "O‘chirilgan"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Tahrirlash"
                    onClick={() => start(s)}
                  >
                    <Pencil />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? editing.email : "Yangi xodim"}</DialogTitle>
          </DialogHeader>
          <form
            className="grid gap-3"
            onSubmit={async (e) => {
              e.preventDefault();
              if (await save.run(undefined)) setOpen(false);
            }}
          >
            {!editing ? (
              <Field id="s-email" label="Email">
                <Input
                  id="s-email"
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                />
              </Field>
            ) : null}
            <Field id="s-name" label="Ism-familiya">
              <Input
                id="s-name"
                value={form.full_name}
                onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
              />
            </Field>
            <Field id="s-role" label="Rol">
              <NativeSelect
                id="s-role"
                value={form.role}
                onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
              >
                {roles.data?.map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.title}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field
              id="s-pass"
              label={editing ? "Yangi parol (ixtiyoriy)" : "Parol"}
              error={passwordError}
              hint="Kamida 10 belgi"
            >
              <Input
                id="s-pass"
                type="password"
                autoComplete="new-password"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              />
            </Field>
            {editing && editing.id !== admin?.id ? (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                />{" "}
                Faol
              </label>
            ) : null}
            <Button
              type="submit"
              disabled={!valid || save.isPending}
              className="justify-self-start"
            >
              Saqlash
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </RequirePermission>
  );
}
