"use client";

import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** A button that asks for confirmation before running a (destructive) action. */
export function ConfirmButton({
  children,
  title,
  description,
  confirmLabel = "Tasdiqlash",
  destructive = false,
  disabled,
  onConfirm,
  variant = "outline",
  size = "sm",
}: {
  children: ReactNode;
  title: string;
  description?: string;
  confirmLabel?: string;
  destructive?: boolean;
  disabled?: boolean;
  onConfirm: () => Promise<unknown>;
  variant?: "outline" | "destructive" | "default" | "ghost";
  size?: "sm" | "default" | "icon";
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <Button variant={variant} size={size} disabled={disabled} onClick={() => setOpen(true)}>
        {children}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description ? <DialogDescription>{description}</DialogDescription> : null}
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              Bekor qilish
            </Button>
            <Button
              variant={destructive ? "destructive" : "default"}
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await onConfirm();
                  setOpen(false);
                } catch {
                  // The action already showed the error; keep the dialog open to retry.
                } finally {
                  setBusy(false);
                }
              }}
            >
              {confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
