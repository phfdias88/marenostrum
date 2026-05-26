"use client";

/**
 * Shell padrao de todas as paginas autenticadas (/dashboard/*).
 * Header com nav + logout, content area centralizada.
 */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  ClipboardList,
  LayoutDashboard,
  LineChart,
  MapPinned,
  Users,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { clearAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GlobalSearch } from "@/components/tse/GlobalSearch";

type Me = { full_name: string; tenant_name: string };

const NAV = [
  { href: "/dashboard", label: "Visão geral", icon: LayoutDashboard },
  { href: "/dashboard/analises", label: "Análises", icon: BarChart3 },
  { href: "/dashboard/analytics", label: "Painel", icon: LineChart },
  { href: "/dashboard/contacts", label: "Contatos", icon: Users },
  { href: "/dashboard/demandas", label: "Demandas", icon: ClipboardList },
  { href: "/dashboard/map", label: "Mapa da Campanha", icon: MapPinned },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("/v1/auth/me")
      .then(setMe)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearAuth();
          router.replace("/login");
        }
      });
  }, [router]);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="border-b bg-card sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          {/* Linha 1: marca + usuário/sair */}
          <div className="h-14 flex items-center justify-between gap-3">
            <Link href="/dashboard" className="flex items-center shrink-0">
              {/* Logo horizontal oficial (M + MARENOSTRUM) */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo-wordmark.png"
                alt="MareNostrum"
                className="h-7 sm:h-8 w-auto object-contain"
              />
            </Link>

            {/* Nav inline só no desktop (lg+) */}
            <nav className="hidden lg:flex items-center gap-1 flex-1 justify-center">
              {NAV.map(({ href, label, icon: Icon }) => {
                const active =
                  pathname === href ||
                  (href !== "/dashboard" && pathname.startsWith(href));
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors whitespace-nowrap",
                      active
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent/60",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </Link>
                );
              })}
            </nav>

            {/* Busca global — desktop */}
            <div className="hidden md:block w-56 lg:w-64 ml-auto mr-2">
              <GlobalSearch />
            </div>

            <div className="flex items-center gap-2 text-sm shrink-0">
              {me && (
                <span className="hidden md:inline text-muted-foreground max-w-[180px] truncate">
                  <span className="text-foreground font-medium">{me.tenant_name}</span>
                </span>
              )}
              <Button variant="ghost" size="sm" onClick={logout}>
                Sair
              </Button>
            </div>
          </div>

          {/* Busca global — mobile */}
          <div className="md:hidden pb-2">
            <GlobalSearch />
          </div>

          {/* Nav com scroll horizontal no mobile/tablet (até lg) */}
          <nav className="lg:hidden flex items-center gap-1 overflow-x-auto pb-2 -mx-1 px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active =
                pathname === href ||
                (href !== "/dashboard" && pathname.startsWith(href));
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors whitespace-nowrap shrink-0",
                    active
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent/60",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="flex-1">{children}</main>
    </div>
  );
}
