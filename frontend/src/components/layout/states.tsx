"use client";

import { AlertTriangle, Inbox, Loader2, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";

export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Yuklanmoqda">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function Spinner({ label = "Yuklanmoqda…" }: { label?: string }) {
  return (
    <p role="status" className="text-muted-foreground flex items-center gap-2 text-sm">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
    </p>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-lg border border-dashed p-10 text-center">
      <Inbox className="size-8" aria-hidden />
      <p className="text-foreground font-medium">{title}</p>
      {children}
    </div>
  );
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Noma’lum xatolik yuz berdi.";
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="border-destructive/30 bg-destructive/5 flex flex-col items-start gap-3 rounded-lg border p-4"
    >
      <p className="text-destructive flex items-center gap-2 text-sm">
        <AlertTriangle className="size-4" aria-hidden /> {errorMessage(error)}
      </p>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw aria-hidden /> Qayta urinish
        </Button>
      ) : null}
    </div>
  );
}
