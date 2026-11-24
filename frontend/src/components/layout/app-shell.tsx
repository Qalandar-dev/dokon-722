"use client";

import {
  BarChart3,
  Boxes,
  FolderTree,
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  ScrollText,
  Settings,
  ShoppingCart,
  Ticket,
  Truck,
  UserCog,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type { Permission } from "@/types/api";

export const NAV: { href: string; label: string; icon: typeof Package; permission: Permission }[] =
  [
    { href: "/", label: "Bosh sahifa", icon: LayoutDashboard, permission: "dashboard.view" },
    { href: "/orders", label: "Buyurtmalar", icon: ShoppingCart, permission: "orders.view" },
    { href: "/products", label: "Mahsulotlar", icon: Package, permission: "products.view" },
    { href: "/categories", label: "Kategoriyalar", icon: FolderTree, permission: "products.view" },
    { href: "/inventory", label: "Ombor", icon: Boxes, permission: "inventory.view" },
    { href: "/customers", label: "Mijozlar", icon: Users, permission: "customers.view" },
    { href: "/promo-codes", label: "Promokodlar", icon: Ticket, permission: "promo.manage" },
    { href: "/delivery", label: "Yetkazib berish", icon: Truck, permission: "delivery.manage" },
    { href: "/reports", label: "Hisobotlar", icon: BarChart3, permission: "reports.view" },
    { href: "/staff", label: "Xodimlar", icon: UserCog, permission: "staff.manage" },
    { href: "/audit-log", label: "Amallar jurnali", icon: ScrollText, permission: "audit.view" },
    { href: "/settings", label: "Sozlamalar", icon: Settings, permission: "settings.manage" },
  ];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { can } = useAuth();
  return (
    <nav className="grid gap-1" aria-label="Asosiy menyu">
      {NAV.filter((item) => can(item.permission)).map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
              active ? "bg-primary text-primary-foreground" : "hover:bg-accent",
            )}
          >
            <Icon className="size-4" aria-hidden /> {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { admin, logout } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-screen">
      <aside className="bg-card hidden w-60 shrink-0 border-r p-4 lg:block">
        <p className="mb-6 px-3 text-lg font-semibold">Online Store</p>
        <NavLinks />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-background/95 sticky top-0 z-30 flex h-14 items-center gap-3 border-b px-4">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Menyuni ochish"
            onClick={() => setOpen(true)}
          >
            <Menu />
          </Button>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="hidden text-right sm:block">
              <span className="block font-medium">{admin?.full_name}</span>
              <span className="text-muted-foreground block text-xs">{admin?.role_title}</span>
            </span>
            <Button variant="outline" size="sm" onClick={() => void logout()}>
              <LogOut aria-hidden /> Chiqish
            </Button>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="top-0 left-0 h-full max-h-screen w-64 translate-x-0 translate-y-0 rounded-none">
          <DialogTitle>Online Store</DialogTitle>
          <NavLinks onNavigate={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
