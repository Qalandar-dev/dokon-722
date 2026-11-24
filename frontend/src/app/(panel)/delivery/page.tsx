"use client";

import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { ConfirmButton } from "@/components/layout/confirm-dialog";
import { Field } from "@/components/layout/field";
import { PageHeader } from "@/components/layout/page-header";
import { RequirePermission } from "@/components/layout/require";
import { EmptyState, ErrorState, LoadingRows } from "@/components/layout/states";
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
import { formatUZS } from "@/lib/format";
import { useAction } from "@/lib/mutation";
import { cn } from "@/lib/utils";
import type { DeliveryMethod, DeliveryRate, District, Region } from "@/types/api";

const KIND: Record<DeliveryMethod["kind"], string> = {
  courier: "Kuryer",
  pickup: "Olib ketish",
  postal: "Pochta",
};
const regionsQuery = {
  queryKey: ["regions"],
  queryFn: () => apiRequest<Region[]>("/admin/regions"),
};
const methodsQuery = {
  queryKey: ["methods"],
  queryFn: () => apiRequest<DeliveryMethod[]>("/admin/delivery-methods"),
};

function useDistricts(regionId: number | null) {
  return useQuery({
    queryKey: ["districts", regionId],
    queryFn: () => apiRequest<District[]>(`/admin/regions/${regionId}/districts`),
    enabled: regionId !== null,
  });
}

// --- Rates --------------------------------------------------------------------------------

interface RateForm {
  method_id: string;
  region_id: string;
  district_id: string;
  price: string;
  free_threshold: string;
  eta_min_days: string;
  eta_max_days: string;
  pickup_address: string;
  is_active: boolean;
}
const emptyRate: RateForm = {
  method_id: "",
  region_id: "",
  district_id: "",
  price: "",
  free_threshold: "",
  eta_min_days: "1",
  eta_max_days: "3",
  pickup_address: "",
  is_active: true,
};
const isAmount = (v: string) => /^\d+(\.\d{1,2})?$/.test(v.trim());

function RatesTab() {
  const regions = useQuery(regionsQuery);
  const methods = useQuery(methodsQuery);
  const [filter, setFilter] = useState({ method_id: "", region_id: "" });
  const rates = useQuery({
    queryKey: ["rates", filter],
    queryFn: () => apiRequest<DeliveryRate[]>("/admin/delivery-rates", { query: filter }),
  });
  const [editing, setEditing] = useState<DeliveryRate | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<RateForm>(emptyRate);
  const districts = useDistricts(form.region_id ? Number(form.region_id) : null);
  const set = (key: keyof RateForm) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const startEdit = (r: DeliveryRate | null) => {
    setEditing(r);
    setForm(
      r
        ? {
            method_id: r.method_id,
            region_id: String(r.region_id),
            district_id: r.district_id ? String(r.district_id) : "",
            price: String(Number(r.price)),
            free_threshold: r.free_threshold ? String(Number(r.free_threshold)) : "",
            eta_min_days: String(r.eta_min_days),
            eta_max_days: String(r.eta_max_days),
            pickup_address: r.pickup_address ?? "",
            is_active: r.is_active,
          }
        : { ...emptyRate, method_id: filter.method_id, region_id: filter.region_id },
    );
    setOpen(true);
  };
  const valid =
    form.method_id &&
    form.region_id &&
    isAmount(form.price) &&
    (!form.free_threshold || isAmount(form.free_threshold)) &&
    Number(form.eta_min_days) >= 0 &&
    Number(form.eta_max_days) >= Number(form.eta_min_days);
  const save = useAction(
    () => {
      const common = {
        price: form.price,
        free_threshold: form.free_threshold || null,
        eta_min_days: Number(form.eta_min_days),
        eta_max_days: Number(form.eta_max_days),
        pickup_address: form.pickup_address || null,
        is_active: form.is_active,
      };
      return editing
        ? apiRequest(`/admin/delivery-rates/${editing.id}`, { method: "PATCH", body: common })
        : apiRequest("/admin/delivery-rates", {
            method: "POST",
            body: {
              ...common,
              method_id: form.method_id,
              region_id: Number(form.region_id),
              district_id: form.district_id ? Number(form.district_id) : null,
            },
          });
    },
    { success: "Tarif saqlandi", invalidate: [["rates"]] },
  );
  const remove = useAction(
    (id: string) => apiRequest(`/admin/delivery-rates/${id}`, { method: "DELETE" }),
    { success: "Tarif o‘chirildi", invalidate: [["rates"]] },
  );

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <NativeSelect
          className="w-56"
          aria-label="Usul"
          value={filter.method_id}
          onChange={(e) => setFilter((f) => ({ ...f, method_id: e.target.value }))}
        >
          <option value="">Barcha usullar</option>
          {methods.data?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          className="w-56"
          aria-label="Hudud"
          value={filter.region_id}
          onChange={(e) => setFilter((f) => ({ ...f, region_id: e.target.value }))}
        >
          <option value="">Barcha hududlar</option>
          {regions.data?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </NativeSelect>
        <Button className="ml-auto" onClick={() => startEdit(null)}>
          <Plus aria-hidden /> Tarif qo‘shish
        </Button>
      </div>
      <p className="text-muted-foreground mb-3 text-sm">
        Tuman uchun alohida tarif bo‘lsa, u viloyat tarifidan ustun turadi. Tarifi yo‘q hududga bu
        usul bilan yetkazilmaydi.
      </p>
      {rates.isPending ? (
        <LoadingRows />
      ) : rates.error ? (
        <ErrorState error={rates.error} onRetry={() => void rates.refetch()} />
      ) : rates.data.length === 0 ? (
        <EmptyState title="Tariflar yo‘q">
          Mijozlar bot orqali buyurtma berishi uchun kamida bitta tarif qo‘shing.
        </EmptyState>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Usul</TableHead>
              <TableHead>Hudud</TableHead>
              <TableHead>Narx</TableHead>
              <TableHead>Bepul (dan)</TableHead>
              <TableHead>Muddat</TableHead>
              <TableHead>Holati</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rates.data.map((r) => (
              <TableRow key={r.id}>
                <TableCell>{r.method_name}</TableCell>
                <TableCell>
                  {r.region_name}
                  {r.district_name ? (
                    <span className="text-muted-foreground"> · {r.district_name}</span>
                  ) : (
                    <span className="text-muted-foreground"> · butun hudud</span>
                  )}
                </TableCell>
                <TableCell>{formatUZS(r.price)}</TableCell>
                <TableCell>{r.free_threshold ? formatUZS(r.free_threshold) : "—"}</TableCell>
                <TableCell>
                  {r.eta_min_days}–{r.eta_max_days} kun
                </TableCell>
                <TableCell>
                  <Badge variant={r.is_active ? "success" : "secondary"}>
                    {r.is_active ? "Faol" : "Nofaol"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Tahrirlash"
                    onClick={() => startEdit(r)}
                  >
                    <Pencil />
                  </Button>
                  <ConfirmButton
                    variant="ghost"
                    size="icon"
                    destructive
                    title="Tarif o‘chirilsinmi?"
                    confirmLabel="O‘chirish"
                    onConfirm={() => remove.mutateAsync(r.id)}
                  >
                    <Trash2 aria-label="O‘chirish" />
                  </ConfirmButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Tarifni tahrirlash" : "Yangi tarif"}</DialogTitle>
          </DialogHeader>
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={async (e) => {
              e.preventDefault();
              if (await save.run(undefined)) setOpen(false);
            }}
          >
            <Field id="r-method" label="Usul">
              <NativeSelect
                id="r-method"
                value={form.method_id}
                onChange={set("method_id")}
                disabled={!!editing}
              >
                <option value="">Tanlang…</option>
                {methods.data?.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="r-region" label="Hudud">
              <NativeSelect
                id="r-region"
                value={form.region_id}
                onChange={(e) =>
                  setForm((f) => ({ ...f, region_id: e.target.value, district_id: "" }))
                }
                disabled={!!editing}
              >
                <option value="">Tanlang…</option>
                {regions.data?.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <div className="sm:col-span-2">
              <Field
                id="r-district"
                label="Tuman / shahar"
                hint="Bo‘sh qoldirilsa — butun hudud uchun"
              >
                <NativeSelect
                  id="r-district"
                  value={form.district_id}
                  onChange={set("district_id")}
                  disabled={!!editing || !form.region_id}
                >
                  <option value="">Butun hudud</option>
                  {districts.data?.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            </div>
            <Field
              id="r-price"
              label="Narx (so‘m)"
              error={form.price && !isAmount(form.price) ? "Raqam kiriting" : undefined}
            >
              <Input id="r-price" inputMode="decimal" value={form.price} onChange={set("price")} />
            </Field>
            <Field
              id="r-free"
              label="Bepul yetkazish (so‘mdan)"
              hint="Bo‘sh — umumiy sozlama ishlatiladi"
            >
              <Input
                id="r-free"
                inputMode="decimal"
                value={form.free_threshold}
                onChange={set("free_threshold")}
              />
            </Field>
            <Field id="r-min" label="Eng kam muddat (kun)">
              <Input
                id="r-min"
                type="number"
                min={0}
                value={form.eta_min_days}
                onChange={set("eta_min_days")}
              />
            </Field>
            <Field id="r-max" label="Eng ko‘p muddat (kun)">
              <Input
                id="r-max"
                type="number"
                min={0}
                value={form.eta_max_days}
                onChange={set("eta_max_days")}
              />
            </Field>
            <div className="sm:col-span-2">
              <Field
                id="r-pickup"
                label="Olib ketish manzili"
                hint="Faqat «olib ketish» usuli uchun"
              >
                <Input id="r-pickup" value={form.pickup_address} onChange={set("pickup_address")} />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              />{" "}
              Faol
            </label>
            <Button
              type="submit"
              disabled={!valid || save.isPending}
              className="justify-self-start sm:col-span-2"
            >
              Saqlash
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

// --- Methods ------------------------------------------------------------------------------

function MethodsTab() {
  const methods = useQuery(methodsQuery);
  const [editing, setEditing] = useState<DeliveryMethod | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    code: "",
    kind: "courier",
    name: "",
    sort_order: "0",
    is_active: true,
  });
  const save = useAction(
    () =>
      editing
        ? apiRequest(`/admin/delivery-methods/${editing.id}`, {
            method: "PATCH",
            body: {
              kind: form.kind,
              name: form.name,
              sort_order: Number(form.sort_order),
              is_active: form.is_active,
            },
          })
        : apiRequest("/admin/delivery-methods", {
            method: "POST",
            body: { ...form, sort_order: Number(form.sort_order) },
          }),
    { success: "Usul saqlandi", invalidate: [["methods"]] },
  );
  const start = (m: DeliveryMethod | null) => {
    setEditing(m);
    setForm(
      m
        ? {
            code: m.code,
            kind: m.kind,
            name: m.name,
            sort_order: String(m.sort_order),
            is_active: m.is_active,
          }
        : { code: "", kind: "courier", name: "", sort_order: "0", is_active: true },
    );
    setOpen(true);
  };
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => start(null)}>
          <Plus aria-hidden /> Usul qo‘shish
        </Button>
      </div>
      {methods.isPending ? (
        <LoadingRows />
      ) : methods.error ? (
        <ErrorState error={methods.error} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nomi</TableHead>
              <TableHead>Kod</TableHead>
              <TableHead>Turi</TableHead>
              <TableHead>Holati</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {methods.data.map((m) => (
              <TableRow key={m.id}>
                <TableCell>{m.name}</TableCell>
                <TableCell className="font-mono text-xs">{m.code}</TableCell>
                <TableCell>{KIND[m.kind]}</TableCell>
                <TableCell>
                  <Badge variant={m.is_active ? "success" : "secondary"}>
                    {m.is_active ? "Faol" : "Nofaol"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Tahrirlash"
                    onClick={() => start(m)}
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
            <DialogTitle>{editing ? "Usulni tahrirlash" : "Yangi usul"}</DialogTitle>
          </DialogHeader>
          <form
            className="grid gap-3"
            onSubmit={async (e) => {
              e.preventDefault();
              if (await save.run(undefined)) setOpen(false);
            }}
          >
            <Field id="m-name" label="Nomi">
              <Input
                id="m-name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </Field>
            <Field id="m-code" label="Kod" hint="Lotin harflar, masalan: express">
              <Input
                id="m-code"
                value={form.code}
                disabled={!!editing}
                onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
              />
            </Field>
            <Field id="m-kind" label="Turi">
              <NativeSelect
                id="m-kind"
                value={form.kind}
                onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}
              >
                {Object.entries(KIND).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="m-sort" label="Tartib">
              <Input
                id="m-sort"
                type="number"
                value={form.sort_order}
                onChange={(e) => setForm((f) => ({ ...f, sort_order: e.target.value }))}
              />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              />{" "}
              Faol
            </label>
            <Button
              type="submit"
              disabled={!form.name.trim() || !form.code.trim() || save.isPending}
              className="justify-self-start"
            >
              Saqlash
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

// --- Regions ------------------------------------------------------------------------------

function RegionsTab() {
  const regions = useQuery(regionsQuery);
  const [selected, setSelected] = useState<number | null>(null);
  const districts = useDistricts(selected);
  const [newDistrict, setNewDistrict] = useState({ name: "", kind: "district" });
  const toggleRegion = useAction(
    (r: Region) =>
      apiRequest(`/admin/regions/${r.id}`, { method: "PATCH", body: { is_active: !r.is_active } }),
    { invalidate: [["regions"]] },
  );
  const toggleDistrict = useAction(
    (d: District) =>
      apiRequest(`/admin/districts/${d.id}`, {
        method: "PATCH",
        body: { is_active: !d.is_active },
      }),
    { invalidate: [["districts", selected]] },
  );
  const addDistrict = useAction(
    () =>
      apiRequest(`/admin/regions/${selected}/districts`, {
        method: "POST",
        body: { ...newDistrict, sort_order: 999 },
      }),
    { success: "Qo‘shildi", invalidate: [["districts", selected], ["regions"]] },
  );
  if (regions.isPending) return <LoadingRows />;
  if (regions.error) return <ErrorState error={regions.error} />;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Hudud</TableHead>
            <TableHead>Tumanlar</TableHead>
            <TableHead>Holati</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {regions.data.map((r) => (
            <TableRow
              key={r.id}
              className={cn("cursor-pointer", selected === r.id && "bg-muted")}
              onClick={() => setSelected(r.id)}
            >
              <TableCell>{r.name}</TableCell>
              <TableCell>{r.districts_count}</TableCell>
              <TableCell>
                <Button
                  size="sm"
                  variant={r.is_active ? "outline" : "secondary"}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleRegion.mutate(r);
                  }}
                >
                  {r.is_active ? "Faol" : "O‘chirilgan"}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div>
        {selected === null ? (
          <EmptyState title="Tuman va shaharlarni ko‘rish uchun hududni tanlang" />
        ) : districts.isPending ? (
          <LoadingRows />
        ) : districts.error ? (
          <ErrorState error={districts.error} />
        ) : (
          <div className="grid gap-3">
            <form
              className="flex flex-wrap gap-2"
              onSubmit={async (e) => {
                e.preventDefault();
                if (await addDistrict.run(undefined))
                  setNewDistrict({ name: "", kind: "district" });
              }}
            >
              <Input
                className="max-w-56"
                placeholder="Yangi tuman/shahar"
                aria-label="Yangi tuman nomi"
                value={newDistrict.name}
                onChange={(e) => setNewDistrict((d) => ({ ...d, name: e.target.value }))}
              />
              <NativeSelect
                className="w-32"
                aria-label="Turi"
                value={newDistrict.kind}
                onChange={(e) => setNewDistrict((d) => ({ ...d, kind: e.target.value }))}
              >
                <option value="district">Tuman</option>
                <option value="city">Shahar</option>
              </NativeSelect>
              <Button type="submit" variant="outline" disabled={!newDistrict.name.trim()}>
                <Plus aria-hidden /> Qo‘shish
              </Button>
            </form>
            <Table>
              <TableBody>
                {districts.data.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell>{d.name}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant={d.is_active ? "outline" : "secondary"}
                        onClick={() => toggleDistrict.mutate(d)}
                      >
                        {d.is_active ? "Faol" : "O‘chirilgan"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}

const TABS = [
  { key: "rates", label: "Tariflar", Component: RatesTab },
  { key: "methods", label: "Usullar", Component: MethodsTab },
  { key: "regions", label: "Hududlar", Component: RegionsTab },
] as const;

export default function DeliveryPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("rates");
  const Active = TABS.find((t) => t.key === tab)!.Component;
  return (
    <RequirePermission permission="delivery.manage">
      <PageHeader
        title="Yetkazib berish"
        description="O‘zbekiston bo‘ylab narxlar, usullar va hududlar"
      />
      <div role="tablist" className="mb-4 flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "-mb-px border-b-2 px-4 py-2 text-sm",
              tab === t.key
                ? "border-primary font-medium"
                : "text-muted-foreground border-transparent",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <Active />
    </RequirePermission>
  );
}
