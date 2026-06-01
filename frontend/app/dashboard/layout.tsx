"use client";

/**
 * Shell padrao de todas as paginas autenticadas (/dashboard/*).
 * Header com nav + logout, content area centralizada.
 */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { BottomNav } from "@/components/nav/BottomNav";
import { RouteProgress } from "@/components/ui/RouteProgress";

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
  const [scrolled, setScrolled] = useState(false);
  const lastY = useRef(0);

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

  // Sticky header shrink + direcao do scroll pra auto-hide.
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    let lastDirChange = 0;
    function onScroll() {
      const y = window.scrollY;
      const dy = y - lastY.current;

      // Shrink quando passa de 12px
      const next = y > 12;
      if (next !== (lastY.current > 12)) setScrolled(next);

      // Auto-hide: scrolla pra baixo > 8px -> esconde, pra cima > 8px -> mostra.
      // Pequeno threshold pra nao flicker em jitter.
      if (Math.abs(dy) > 8) {
        if (dy > 0 && y > 80) {
          // descendo + ja passou do header
          if (!hidden) setHidden(true);
        } else if (dy < 0) {
          if (hidden) setHidden(false);
        }
        lastDirChange = y;
      }
      lastY.current = y;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hidden]);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <RouteProgress />
      <header
        data-dash-header
        data-scrolled={scrolled ? "true" : "false"}
        data-hidden={hidden ? "true" : "false"}
        className={cn(
          "border-b bg-card/70 backdrop-blur-md sticky top-0 z-30 supports-[backdrop-filter]:bg-card/55 transition-[transform,box-shadow] duration-200 will-change-transform",
          scrolled && "shadow-md shadow-black/10",
          hidden && "md:translate-y-0 -translate-y-full",
        )}
      >
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

            {/* Nav inline só no desktop (lg+). shrink-0 evita encolher
                e roubar largura da busca quando layout aperta. */}
            <nav className="hidden lg:flex items-center gap-1 shrink-0">
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

            {/* Busca global — desktop. flex-1 cresce no espaco livre entre
                nav e bloco direito; min-w-0 permite encolher em telas
                medias sem virar 0 (a placeholder some mas o input segue
                clicavel). Tem max-w pra nao ficar gigante em ultrawide. */}
            <div className="hidden md:block flex-1 min-w-[180px] max-w-md ml-auto mr-2">
              <GlobalSearch />
            </div>

            <div className="flex items-center gap-2 text-sm shrink-0">
              {me && (
                <Link
                  href="/dashboard/configuracoes"
                  title="Configurações"
                  className="hidden md:inline text-muted-foreground max-w-[180px] truncate hover:text-foreground"
                >
                  <span className="text-foreground font-medium">{me.tenant_name}</span>
                </Link>
              )}
              <ThemeToggle />
              <Button variant="ghost" size="sm" onClick={logout}>
                Sair
              </Button>
            </div>
          </div>

          {/* Busca global — mobile (some quando scrolla pra dar espaco) */}
          <div className="md:hidden pb-2">
            <div data-mobile-search>
              <GlobalSearch />
            </div>
          </div>

          {/* Nav com scroll horizontal — so em tablets (md-lg). No mobile
              quem manda e o BottomNav, fica mais limpo. */}
          <nav className="hidden md:flex lg:hidden items-center gap-1 overflow-x-auto pb-2 -mx-1 px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
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

      {/* pb pro BottomNav nao cobrir conteudo no mobile */}
      <main className="flex-1 pb-[calc(64px+env(safe-area-inset-bottom))] md:pb-0">
        {children}
      </main>

      <BottomNav hidden={hidden} />
    </div>
  );
}
