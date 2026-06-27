"use client";

/**
 * Seletor de camada do mapa (claro / escuro / satélite). Overlay pequeno —
 * posicione com a prop className (ex: "absolute top-3 right-3 z-[500]").
 * Compartilha o estado global via useMapLayout, então qualquer ThemedTileLayer
 * na tela reflete a escolha na hora.
 */
import { Moon, Satellite, Sun } from "lucide-react";

import { useMapLayout, type MapLayout } from "@/lib/useMapLayout";
import { cn } from "@/lib/utils";

const OPTS: { v: MapLayout; icon: typeof Sun; label: string }[] = [
  { v: "light", icon: Sun, label: "Claro" },
  { v: "dark", icon: Moon, label: "Escuro" },
  { v: "satellite", icon: Satellite, label: "Satélite" },
];

export function MapLayoutSelector({ className }: { className?: string }) {
  const [layout, setLayout] = useMapLayout();
  return (
    <div
      className={cn(
        "flex gap-0.5 bg-card/90 backdrop-blur border border-border rounded-md p-0.5 shadow",
        className,
      )}
    >
      {OPTS.map(({ v, icon: Icon, label }) => (
        <button
          key={v}
          type="button"
          onClick={() => setLayout(v)}
          title={label}
          className={cn(
            "inline-flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors",
            layout === v
              ? "bg-foreground text-background"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          <Icon className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">{label}</span>
        </button>
      ))}
    </div>
  );
}
