"use client";

/**
 * VotesBarChart — gráfico de barras HORIZONTAL de votos (Recharts), temático.
 *
 * Reutilizável nos dois cenários pedidos:
 *  - Cenário A (Município): label = município, sublabel = UF.
 *  - Cenário B (Bairro):    label = bairro,    sublabel = município (desambigua
 *    homônimos — o backend agora devolve o município por item).
 *
 * Traz um input de busca acima do gráfico (filtra por label + sublabel) e
 * limita a `topN` barras para legibilidade. Cores via CSS vars do tema
 * (`hsl(var(--primary))` etc.), então alterna claro/escuro automaticamente.
 *
 * É pesado (Recharts) → importe com next/dynamic({ ssr: false }) onde usar.
 */
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type VotesBarItem = {
  key: string;
  label: string;
  sublabel?: string;
  value: number;
};

const fmt = new Intl.NumberFormat("pt-BR");

export function VotesBarChart({
  items,
  searchPlaceholder = "Buscar…",
  topN = 25,
  emptyText = "Nada encontrado para essa busca.",
  unit = "votos",
  hideSearch = false,
  yAxisWidth = 128,
}: {
  items: VotesBarItem[];
  searchPlaceholder?: string;
  topN?: number;
  emptyText?: string;
  unit?: string;
  /** Esconde a busca interna — use quando a página tem filtros GLOBAIS
   *  próprios (ex.: modal split-screen) e a busca aqui seria redundante. */
  hideSearch?: boolean;
  /** Largura do eixo Y — aumente p/ rótulos compostos "Bairro (Município)". */
  yAxisWidth?: number;
}) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const base = needle
      ? items.filter(
          (i) =>
            i.label.toLowerCase().includes(needle) ||
            (i.sublabel ?? "").toLowerCase().includes(needle),
        )
      : items;
    return base.slice(0, topN);
  }, [items, q, topN]);

  // Altura proporcional ao nº de barras (cada barra ~26px), com piso.
  const height = Math.max(200, filtered.length * 26 + 32);

  return (
    <div>
      {!hideSearch && (
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={searchPlaceholder}
            className="w-full pl-9 py-2 rounded-md bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground py-10 text-center">{emptyText}</p>
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={filtered}
              layout="vertical"
              margin={{ left: 4, right: 16, top: 4, bottom: 4 }}
              barCategoryGap={4}
            >
              <CartesianGrid
                horizontal={false}
                stroke="hsl(var(--border))"
                strokeOpacity={0.45}
              />
              <XAxis
                type="number"
                tickFormatter={(v) => fmt.format(Number(v))}
                stroke="hsl(var(--muted-foreground))"
                fontSize={11}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                type="category"
                dataKey="label"
                width={yAxisWidth}
                stroke="hsl(var(--muted-foreground))"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                interval={0}
                // Truncagem proporcional à largura (~7px por caractere).
                // Rótulo composto "Bairro (Município)": trunca o BAIRRO e
                // preserva o "(Município)" — é o desambiguador de homônimos.
                tickFormatter={(v: string) => {
                  const max = Math.max(12, Math.floor(yAxisWidth / 7));
                  if (v.length <= max) return v;
                  const m = v.match(/^(.*?)\s*(\([^()]*\))$/);
                  if (m) {
                    const suffix = " " + m[2];
                    const keep = Math.max(4, max - suffix.length - 1);
                    return m[1].slice(0, keep) + "…" + suffix;
                  }
                  return v.slice(0, max - 1) + "…";
                }}
              />
              <Tooltip
                cursor={{ fill: "hsl(var(--muted-foreground))", fillOpacity: 0.08 }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload as VotesBarItem;
                  return (
                    <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-lg">
                      <p className="font-semibold">{p.label}</p>
                      {p.sublabel ? (
                        <p className="text-muted-foreground">{p.sublabel}</p>
                      ) : null}
                      <p className="mt-1 font-mono font-bold text-primary">
                        {fmt.format(p.value)} {unit}
                      </p>
                    </div>
                  );
                }}
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                {filtered.map((_, i) => (
                  <Cell
                    key={i}
                    fill="hsl(var(--primary))"
                    // leve degradê: barras do topo mais fortes. Piso de 0.7
                    // pra ultima barra nao "apagar" no tema claro.
                    fillOpacity={Math.max(
                      0.7,
                      1 - (i / Math.max(filtered.length, 1)) * 0.55,
                    )}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {!q && items.length > topN && (
        <p className="text-[11px] text-muted-foreground mt-2">
          Mostrando os {topN} maiores de {fmt.format(items.length)}.{" "}
          {hideSearch
            ? "Use os filtros acima para localizar os demais."
            : "Use a busca para localizar os demais."}
        </p>
      )}
    </div>
  );
}
