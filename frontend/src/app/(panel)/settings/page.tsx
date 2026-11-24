"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Field } from "@/components/layout/field";
import { PageHeader } from "@/components/layout/page-header";
import { RequirePermission } from "@/components/layout/require";
import { ErrorState, LoadingRows } from "@/components/layout/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api-client";
import { useAction } from "@/lib/mutation";

type Settings = Record<string, string | number | boolean | null>;

const TEXT_FIELDS: [string, string, string?][] = [
  ["store.name", "Do‘kon nomi"],
  ["store.phone", "Aloqa telefoni", "+998 …"],
  ["store.support_telegram", "Qo‘llab-quvvatlash Telegram", "@username"],
  ["store.address", "Manzil"],
  ["store.currency_display", "Valyuta belgisi", "so‘m"],
  ["delivery.free_threshold", "Bepul yetkazish chegarasi (so‘m)", "Bo‘sh — o‘chirilgan"],
  ["inventory.low_stock_threshold", "Kam qoldiq chegarasi (dona)"],
];
const TOGGLES: [string, string][] = [
  ["payments.click_enabled", "Click orqali to‘lov"],
  ["payments.payme_enabled", "Payme orqali to‘lov"],
  ["payments.cash_on_delivery_enabled", "Yetkazib berishda naqd to‘lov"],
  ["notifications.new_order_to_staff", "Yangi buyurtma haqida xodimlarga xabar"],
  ["notifications.low_stock_to_staff", "Kam qoldiq haqida xodimlarga xabar"],
];
const NUMERIC = new Set(["delivery.free_threshold", "inventory.low_stock_threshold"]);

function display(value: Settings[string] | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function SettingsForm({ initial }: { initial: Settings }) {
  const [values, setValues] = useState<Settings>(initial);
  const save = useAction(
    () => {
      const body: Settings = {};
      for (const [key] of TEXT_FIELDS) {
        const text = display(values[key]).trim();
        body[key] = NUMERIC.has(key) ? (text === "" ? null : Number(text)) : text || null;
      }
      for (const [key] of TOGGLES) body[key] = Boolean(values[key]);
      return apiRequest<Settings>("/admin/settings", { method: "PATCH", body });
    },
    { success: "Sozlamalar saqlandi", invalidate: [["settings"]] },
  );
  return (
    <form
      className="grid gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Card>
        <CardHeader>
          <CardTitle>Do‘kon</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {TEXT_FIELDS.map(([key, label, placeholder]) => (
            <Field key={key} id={key} label={label}>
              <Input
                id={key}
                placeholder={placeholder}
                inputMode={NUMERIC.has(key) ? "numeric" : undefined}
                value={display(values[key])}
                onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
              />
            </Field>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>To‘lov va xabarnomalar</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          {TOGGLES.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={Boolean(values[key])}
                onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.checked }))}
              />{" "}
              {label}
            </label>
          ))}
        </CardContent>
      </Card>
      <Button type="submit" disabled={save.isPending} className="justify-self-start">
        Saqlash
      </Button>
    </form>
  );
}

export default function SettingsPage() {
  const query = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiRequest<Settings>("/admin/settings"),
  });
  return (
    <RequirePermission permission="settings.manage">
      <PageHeader title="Sozlamalar" />
      {query.isPending ? (
        <LoadingRows />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        // Re-mount the form when fresh data arrives instead of syncing state in an effect.
        <SettingsForm key={query.dataUpdatedAt} initial={query.data} />
      )}
    </RequirePermission>
  );
}
