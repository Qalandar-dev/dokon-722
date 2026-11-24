"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Spinner } from "@/components/layout/states";
import { useAuth } from "@/lib/auth";

/** Every page in this group requires a signed-in admin. */
export default function PanelLayout({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Sessiya tekshirilmoqda…" />
      </div>
    );
  }
  return <AppShell>{children}</AppShell>;
}
