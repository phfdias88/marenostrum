"use client";

/**
 * Bottom nav bar mobile (md:hidden) — padrao de app nativo.
 *
 * 5 atalhos principais com icone + label. Item ativo ganha cor primary e
 * uma linha dourada superior. Safe-area inset pra iPhone com notch/home bar.
 * O scroll horizontal antigo do header foi escondido em telas pequenas.
 */
import {
  BarChart3,
  ClipboardList,
  Layers,
  LayoutDashboard,
  LineChart,
  MapPinned,
  MoreHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

type Tab = { href: string; label: string; icon: LucideIcon; flag?: "analytics" | "panel" | "map" };

// 4 atalhos principais + "Mais" no slot 5 (vai pra /dashboard com lista
// completa). Conservador pro polegar — 5 it slot e o limite do padrao iOS.
// `flag` = área configurável pelo owner (some da barra se desligada).
const TABS: Tab[] = [
  { href: "/dashboard", label: "Início", icon: LayoutDashboard },
  { href: "/dashboard/analises", label: "Análises", icon: BarChart3, flag: "analytics" },
  { href: "/dashboard/analytics", label: "Painel", icon: LineChart, flag: "panel" },
  { href: "/dashboard/contacts", label: "Contatos", icon: Users },
  { href: "/dashboard/map", label: "Mapa", icon: MapPinned, flag: "map" },
];

// Módulo Censo (IBGE) — só entra na barra se o owner liberou pro usuário.
const CENSO_TAB: Tab = { href: "/dashboard/censo", label: "Censo", icon: Layers };

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
  const visible = TABS.filter((t) => !t.flag || !access || access[t.flag]);
  const tabs = censusEnabled ? [...visible, CENSO_TAB] : visible;

  return (
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
        style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}
      >
        {tabs.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href ||
            (href !== "/dashboard" && pathname.startsWith(href));
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
      </ul>
    </nav>
  );
}
