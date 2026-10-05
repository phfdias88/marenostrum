"use client";

/**
 * Seletor de camada do mapa (claro / escuro / ruas / satélite).
 *
 * NÃO precisa ser colocado à mão: o ThemedTileLayer já desenha um destes no
 * canto de todo mapa. Compartilha o estado global via useMapLayout, então a
 * escolha vale para todos os mapas e fica guardada no navegador.
 */
import { Map as MapIcon, Moon, Satellite, Sun } from "lucide-react";

import { useMapLayout, type MapLayout } from "@/lib/useMapLayout";
import { cn } from "@/lib/utils";

const OPTS: { v: MapLayout; icon: typeof Sun; label: string }[] = [
  { v: "light", icon: Sun, label: "Claro" },
  { v: "dark", icon: Moon, label: "Escuro" },
  // Ruas: o único com nome de rua e de bairro forte — é o que serve para se
  // localizar numa cidade. Os cinzas são fundo neutro para o dado aparecer.
  { v: "streets", icon: MapIcon, label: "Ruas" },
  { v: "satellite", icon: Satellite, label: "Satélite" },
];

type Props = {
  className?: string;
  /** Só os ícones, sem o nome. Para o canto do mapa, onde o espaço é do dado. */
  compacto?: boolean;
};

export function MapLayoutSelector({ className, compacto = false }: Props) {
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
          title={`Mapa: ${label}`}
          aria-label={`Mapa: ${label}`}
          aria-pressed={layout === v}
          className={cn(
            "inline-flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors",
            layout === v
              ? "bg-foreground text-background"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          <Icon className="w-3.5 h-3.5" />
          {!compacto && <span className="hidden sm:inline">{label}</span>}
        </button>
      ))}
    </div>
  );
}
