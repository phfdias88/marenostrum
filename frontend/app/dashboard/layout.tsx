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
  CalendarClock,
  ClipboardList,
  LayoutDashboard,
  Layers,
  LineChart,
  MapPinned,
  Settings,
  Users,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { clearAuth, refreshTokenCookie } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GlobalSearch } from "@/components/tse/GlobalSearch";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { BottomNav } from "@/components/nav/BottomNav";
import { RouteProgress } from "@/components/ui/RouteProgress";

type Me = {
  full_name: string;
  tenant_name: string;
  role?: string;
  census_enabled?: boolean;
  // Acesso por área (configurável pelo owner). Default amplo no backend.
  analytics_enabled?: boolean;
  panel_enabled?: boolean;
  map_enabled?: boolean;
  demands_enabled?: boolean;
  agenda_enabled?: boolean;
  // Sessão deslizante: /me devolve um token novo quando o atual passa
  // da metade da validade — trocamos o cookie sem o usuário perceber.
  refreshed_token?: string | null;
  refreshed_expires_in?: number | null;
};

// `flag` = chave do acesso configurável pelo owner (some do menu se desligado
// pra quem não é owner). Itens sem flag aparecem pra todos.
const NAV: { href: string; label: string; icon: typeof LayoutDashboard; flag?: keyof Me }[] = [
  { href: "/dashboard", label: "Visão geral", icon: LayoutDashboard },
  { href: "/dashboard/analises", label: "Análises", icon: BarChart3, flag: "analytics_enabled" },
  { href: "/dashboard/analytics", label: "Painel", icon: LineChart, flag: "panel_enabled" },
  { href: "/dashboard/contacts", label: "Contatos", icon: Users },
  { href: "/dashboard/demandas", label: "Demandas", icon: ClipboardList, flag: "demands_enabled" },
  { href: "/dashboard/agenda", label: "Agenda", icon: CalendarClock, flag: "agenda_enabled" },
  { href: "/dashboard/map", label: "Mapa da Campanha", icon: MapPinned, flag: "map_enabled" },
];

// Item do módulo Censo — só aparece se o owner liberou (me.census_enabled).
const CENSO_NAV = { href: "/dashboard/censo", label: "Censo", icon: Layers };

// Áreas que somem do menu / bloqueiam a rota quando o owner desliga (exceto
// pro próprio owner). Censo é gated só pelo flag (igual já era).
const AREA_GUARD: { prefix: string; flag: keyof Me; ownerBypass: boolean }[] = [
  { prefix: "/dashboard/analises", flag: "analytics_enabled", ownerBypass: true },
  { prefix: "/dashboard/analytics", flag: "panel_enabled", ownerBypass: true },
  { prefix: "/dashboard/demandas", flag: "demands_enabled", ownerBypass: true },
  { prefix: "/dashboard/agenda", flag: "agenda_enabled", ownerBypass: true },
  { prefix: "/dashboard/map", flag: "map_enabled", ownerBypass: true },
  { prefix: "/dashboard/censo", flag: "census_enabled", ownerBypass: false },
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
      .then((m) => {
        // Liderança (acesso restrito) não tem dashboard — manda pro formulário.
        if (m.role === "volunteer") {
          router.replace("/cadastro");
          return;
        }
        setMe(m);
        if (m.refreshed_token && m.refreshed_expires_in) {
          refreshTokenCookie(m.refreshed_token, m.refreshed_expires_in);
        }
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearAuth();
          router.replace("/login");
        }
      });
  }, [router]);

  // Guard de área: se o owner desligou o acesso desta seção pro usuário,
  // tira ele da rota (o backend também responde 403 nos dados privados).
  useEffect(() => {
    if (!me) return;
    const isOwner = me.role === "owner";
    for (const { prefix, flag, ownerBypass } of AREA_GUARD) {
      const allowed = (ownerBypass && isOwner) || me[flag] !== false;
      if (pathname.startsWith(prefix) && !allowed) {
        router.replace("/dashboard");
        return;
      }
    }
  }, [me, pathname, router]);

  // Prefetch das rotas do menu quando o browser estiver ocioso — o primeiro
  // clique em qualquer seção fica instantâneo (bundle da rota ja' baixado).
  // requestIdleCallback evita competir com o render inicial; fallback p/ Safari.
  useEffect(() => {
    const ric =
      (window as unknown as {
        requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number;
      }).requestIdleCallback ?? ((cb: () => void) => window.setTimeout(cb, 1200));
    const id = ric(() => {
      for (const { href } of NAV) {
        if (href !== pathname) router.prefetch(href);
      }
    }, { timeout: 3000 });
    return () => {
      const cic = (window as unknown as {
        cancelIdleCallback?: (h: number) => void;
      }).cancelIdleCallback;
      if (cic) cic(id as number);
    };
  }, [router, pathname]);

  // Sticky header shrink + direcao do scroll pra auto-hide.
  // Throttle via requestAnimationFrame: o handler de scroll roda em TODO
  // evento (mesmo passive), mas so' processamos 1x por frame (~16ms) e
  // usamos functional setState pra registrar o listener UMA vez (sem
  // re-registrar a cada mudanca de estado). React faz bail-out quando o
  // valor nao muda, entao nao ha re-render desnecessario.
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    let ticking = false;
    function process() {
      ticking = false;
      const y = window.scrollY;
      const dy = y - lastY.current;

      // Shrink quando passa de 12px (functional → bail-out automatico)
      setScrolled((prev) => {
        const next = y > 12;
        return prev === next ? prev : next;
      });

      // Auto-hide: desce >8px e ja passou do header → esconde; sobe → mostra.
      if (Math.abs(dy) > 8) {
        if (dy > 0 && y > 80) setHidden((h) => (h ? h : true));
        else if (dy < 0) setHidden((h) => (h ? false : h));
      }
      lastY.current = y;
    }
    function onScroll() {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(process);
      }
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  // Menu: filtra as áreas que o owner desligou pra este usuário (owner vê tudo)
  // e acrescenta o módulo Censo só se liberado.
  const isOwner = me?.role === "owner";
  const navItems = [
    ...NAV.filter((n) => !n.flag || isOwner || me?.[n.flag] !== false),
    ...(me?.census_enabled ? [CENSO_NAV] : []),
  ];

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
              {/* Logo horizontal oficial — variante por tema (texto branco no
                  dark, grafite no light; o M dourado é o mesmo) */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo-wordmark.png"
                alt="MareNostrum"
                className="h-7 sm:h-8 w-auto object-contain hidden dark:block"
              />
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo-wordmark-light.png"
                alt="MareNostrum"
                className="h-7 sm:h-8 w-auto object-contain dark:hidden"
              />
            </Link>

            {/* Nav inline só no desktop (lg+). O container é max-w-7xl
                (1280px), então com o item Censo os 8 rótulos NUNCA cabem
                junto da busca — em qualquer monitor. Por isso: só ícones
                (tooltip no hover) e o item ATIVO mantém o rótulo. */}
            <nav className="hidden lg:flex items-center gap-1 shrink-0">
              {navItems.map(({ href, label, icon: Icon }) => {
                const active =
                  pathname === href ||
                  (href !== "/dashboard" && pathname.startsWith(href));
                return (
                  <Link
                    key={href}
                    href={href}
                    title={label}
                    className={cn(
                      "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors whitespace-nowrap",
                      active
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent/60",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className={active ? "inline" : "hidden"}>{label}</span>
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
              {/* Acesso às Configurações no MOBILE (no desktop o nome da campanha
                  já leva lá). Sem isso, o celular não tinha como abrir o painel
                  de Equipe/papéis. */}
              {me && (
                <Link
                  href="/dashboard/configuracoes"
                  title="Configurações"
                  aria-label="Configurações"
                  className="md:hidden p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/60"
                >
                  <Settings className="h-5 w-5" />
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
            {navItems.map(({ href, label, icon: Icon }) => {
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

      <BottomNav
        hidden={hidden}
        censusEnabled={!!me?.census_enabled}
        access={{
          analytics: isOwner || me?.analytics_enabled !== false,
          panel: isOwner || me?.panel_enabled !== false,
          map: isOwner || me?.map_enabled !== false,
        }}
      />
    </div>
  );
}
