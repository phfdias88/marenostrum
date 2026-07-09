"use client";

/**
 * Bottom nav bar mobile (md:hidden) — padrao de app nativo.
 *
 * 4 atalhos principais + "Mais" no slot 5, que abre um bottom-sheet com as
 * seções que não couberam na barra (Agenda, Demandas, Mapa, Censo, Equipe,
 * Configurações). Sem isso, Agenda não tinha NENHUM caminho de navegação no
 * mobile e Demandas dependia de um KPI card do dashboard.
 *
 * Item ativo ganha cor primary e uma linha dourada superior. Safe-area inset
 * pra iPhone com notch/home bar. 5 slots é o limite do padrão iOS.
 */
import {
  BarChart3,
  CalendarClock,
  ClipboardList,
  Layers,
  LayoutDashboard,
  LineChart,
  MapPinned,
  MoreHorizontal,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

type Tab = { href: string; label: string; icon: LucideIcon; flag?: "analytics" | "panel" | "map" };

// 4 atalhos principais — o slot 5 é o botão "Mais".
// `flag` = área configurável pelo owner (some da barra se desligada).
const TABS: Tab[] = [
  { href: "/dashboard", label: "Início", icon: LayoutDashboard },
  { href: "/dashboard/analises", label: "Análises", icon: BarChart3, flag: "analytics" },
  { href: "/dashboard/analytics", label: "Painel", icon: LineChart, flag: "panel" },
  { href: "/dashboard/contacts", label: "Contatos", icon: Users },
];

// Itens do sheet "Mais" — tudo que existe no nav do dashboard mas não coube
// nos 4 slots. Equipe mora dentro de Configurações (cartão "Equipe"), por
// isso as duas entradas apontam pra mesma rota.
type MoreItem = {
  href: string;
  label: string;
  sub: string;
  icon: LucideIcon;
  flag?: "map";
  census?: boolean;
};

const MORE_ITEMS: MoreItem[] = [
  { href: "/dashboard/agenda", label: "Agenda", sub: "Eventos e compromissos", icon: CalendarClock },
  { href: "/dashboard/demandas", label: "Demandas", sub: "Pedidos da população", icon: ClipboardList },
  { href: "/dashboard/map", label: "Mapa da Campanha", sub: "Contatos e demandas no território", icon: MapPinned, flag: "map" },
  { href: "/dashboard/censo", label: "Censo", sub: "Dados IBGE por bairro", icon: Layers, census: true },
  { href: "/dashboard/configuracoes", label: "Equipe", sub: "Membros e papéis", icon: Users },
  { href: "/dashboard/configuracoes", label: "Configurações", sub: "Conta e campanha", icon: Settings },
];

export function BottomNav({
  hidden = false,
  censusEnabled = false,
  access,
}: {
  hidden?: boolean;
  censusEnabled?: boolean;
  // Acesso por área já resolvido pelo layout (owner || flag). Ausente = libera.
  access?: { analytics: boolean; panel: boolean; map: boolean };
}) {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);

  const tabs = TABS.filter((t) => !t.flag || !access || access[t.flag]);
  const moreItems = MORE_ITEMS.filter((m) => {
    if (m.census && !censusEnabled) return false;
    if (m.flag && access && !access[m.flag]) return false;
    return true;
  });

  // Fecha o sheet ao navegar (troca de rota) — cobre back/forward também.
  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  // Esc fecha + trava scroll do body enquanto o sheet está aberto.
  useEffect(() => {
    if (!moreOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMoreOpen(false);
    }
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [moreOpen]);

  function isActive(href: string) {
    return pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
  }

  // "Mais" acende quando a rota atual é uma das que moram no sheet.
  const moreActive = moreItems.some((m) => isActive(m.href));

  return (
    <>
      <nav
        data-bottom-nav
        data-hidden={hidden ? "true" : "false"}
        className={
          "md:hidden fixed bottom-0 left-0 right-0 z-40 bg-card/90 backdrop-blur-md border-t border-border transition-transform duration-200 will-change-transform " +
          (hidden ? "translate-y-full" : "translate-y-0")
        }
        style={{ paddingBottom: "max(env(safe-area-inset-bottom), 0.25rem)" }}
      >
        <ul
          className="grid"
          style={{ gridTemplateColumns: `repeat(${tabs.length + 1}, minmax(0, 1fr))` }}
        >
          {tabs.map(({ href, label, icon: Icon }) => {
            const active = isActive(href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={cn(
                    "flex flex-col items-center gap-0.5 py-2 transition-colors min-h-[56px] relative",
                    active
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {active && (
                    <span className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full bg-primary" />
                  )}
                  <Icon className="h-5 w-5" />
                  <span className="text-[10px] font-medium leading-none">
                    {label}
                  </span>
                </Link>
              </li>
            );
          })}
          <li>
            <button
              type="button"
              onClick={() => setMoreOpen(true)}
              aria-label="Mais opções"
              aria-expanded={moreOpen}
              className={cn(
                "w-full flex flex-col items-center gap-0.5 py-2 transition-colors min-h-[56px] relative",
                moreActive || moreOpen
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {moreActive && (
                <span className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full bg-primary" />
              )}
              <MoreHorizontal className="h-5 w-5" />
              <span className="text-[10px] font-medium leading-none">Mais</span>
            </button>
          </li>
        </ul>
      </nav>

      {/* === BOTTOM SHEET "MAIS" === */}
      {moreOpen && (
        <div className="md:hidden fixed inset-0 z-50">
          {/* Backdrop — toque fora fecha */}
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-in fade-in-0 duration-200"
            onClick={() => setMoreOpen(false)}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Mais opções"
            className="absolute inset-x-0 bottom-0 rounded-t-2xl border-t border-border bg-card shadow-2xl animate-in slide-in-from-bottom duration-200"
            style={{ paddingBottom: "max(env(safe-area-inset-bottom), 0.5rem)" }}
          >
            {/* Grabber — affordance de sheet nativo */}
            <div className="pt-2.5 pb-1 grid place-items-center">
              <span className="w-10 h-1 rounded-full bg-muted-foreground/30" />
            </div>
            <p className="px-5 pb-1 text-xs uppercase tracking-wider text-muted-foreground">
              Mais opções
            </p>
            <ul className="pb-1">
              {moreItems.map(({ href, label, sub, icon: Icon }) => {
                // Equipe e Configurações compartilham a rota — só a entrada
                // "Configurações" acende nela (evita 2 itens ativos).
                const active = isActive(href) && label !== "Equipe";
                return (
                  <li key={label}>
                    <Link
                      href={href}
                      onClick={() => setMoreOpen(false)}
                      className={cn(
                        "flex items-center gap-3 px-5 py-3 min-h-[56px] transition-colors",
                        active
                          ? "text-primary bg-accent/40"
                          : "text-foreground hover:bg-accent/50",
                      )}
                    >
                      <span
                        className={cn(
                          "grid place-items-center w-9 h-9 rounded-lg shrink-0",
                          active ? "bg-primary/15 text-primary" : "bg-accent/60 text-muted-foreground",
                        )}
                      >
                        <Icon className="h-5 w-5" />
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="block text-sm font-medium leading-tight">{label}</span>
                        <span className="block text-xs text-muted-foreground leading-tight mt-0.5">
                          {sub}
                        </span>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
