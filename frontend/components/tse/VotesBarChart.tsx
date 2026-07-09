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
import { useId, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
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
// "72,6 mil" no fim da barra — número cheio fica no tooltip.
const compactFmt = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  maximumFractionDigits: 1,
});

// Tick do eixo Y com RANKING: "1º Bangu". O rank é TEXTO (top-3 em ouro) — a
// cor da BARRA segue a entidade, nunca o rank (regra de dataviz: filtro que
// muda posições não pode "repintar" quem sobrou).
type TickProps = {
  x?: number;
  y?: number;
  index?: number;
  payload?: { value?: string | number };
};
function RankedTick({
  x = 0,
  y = 0,
  index = 0,
  payload,
  maxChars,
}: TickProps & { maxChars: number }) {
  const raw = String(payload?.value ?? "");
  let label = raw;
  if (raw.length > maxChars) {
    // Preserva o sufixo "(Município)" — desambiguador de homônimos.
    const m = raw.match(/^(.*?)\s*(\([^()]*\))$/);
    if (m) {
      const suffix = " " + m[2];
      const keep = Math.max(4, maxChars - suffix.length - 1);
      label = m[1].slice(0, keep) + "…" + suffix;
    } else {
      label = raw.slice(0, maxChars - 1) + "…";
    }
  }
  const top3 = index < 3;
  return (
    <g transform={`translate(${x},${y})`}>
      <text x={0} y={0} dy={3.5} textAnchor="end" fontSize={11}>
        <tspan
          fontSize={9}
          fontWeight={700}
          fill={top3 ? "hsl(var(--primary))" : "hsl(var(--muted-foreground))"}
          opacity={top3 ? 1 : 0.65}
        >
          {index + 1}º
        </tspan>
        <tspan dx={4} fill="hsl(var(--foreground))" opacity={0.92}>
          {label}
        </tspan>
      </text>
    </g>
  );
}

export function VotesBarChart({
  items,
  searchPlaceholder = "Buscar…",
  topN = 25,
  emptyText = "Nada encontrado para essa busca.",
  unit = "votos",
  hideSearch = false,
  yAxisWidth = 128,
  showValues = false,
  onItemClick,
  selectedKey = null,
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
  /** Mostra o valor compacto ("72,6 mil") no fim de cada barra. */
  showValues?: boolean;
  /** Clique na barra (sincronizar com mapa etc.). Liga cursor pointer. */
  onItemClick?: (item: VotesBarItem) => void;
  /** Barra destacada (selecionada) — a key do item. */
  selectedKey?: string | null;
}) {
  const [q, setQ] = useState("");
  // id do gradiente SVG (único por instância; useId traz ":" que quebra url()).
  const gid = useId().replace(/[^a-zA-Z0-9]/g, "");
  // Total do CONJUNTO recebido (contexto do filtro) — usado no "% do filtro".
  const total = useMemo(() => items.reduce((s, i) => s + i.value, 0), [items]);

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
              margin={{ left: 4, right: showValues ? 52 : 16, top: 4, bottom: 4 }}
              barCategoryGap={4}
            >
              {/* Degradê dourado AO LONGO da barra (base suave → ponta cheia).
                  Uniforme em todas as barras: a cor segue a ENTIDADE, não o
                  rank — filtrar não "repinta" quem ficou. */}
              <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="1" y2="0">
                  <stop
                    offset="0%"
                    stopColor="hsl(var(--primary))"
                    stopOpacity={0.45}
                  />
                  <stop
                    offset="100%"
                    stopColor="hsl(var(--primary))"
                    stopOpacity={0.95}
                  />
                </linearGradient>
              </defs>
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
                // Tick custom: "1º Bangu" (rank + nome; truncagem proporcional
                // à largura, preservando o sufixo "(Município)").
                tick={(p: unknown) => (
                  <RankedTick
                    {...(p as TickProps)}
                    maxChars={Math.max(10, Math.floor(yAxisWidth / 7) - 3)}
                  />
                )}
              />
              <Tooltip
                cursor={{ fill: "hsl(var(--muted-foreground))", fillOpacity: 0.08 }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload as VotesBarItem;
                  const share = total > 0 ? (p.value / total) * 100 : null;
                  return (
                    <div className="rounded-md border border-primary/25 bg-card px-3 py-2 text-xs shadow-lg">
                      <p className="font-semibold">{p.label}</p>
                      {p.sublabel ? (
                        <p className="text-muted-foreground">{p.sublabel}</p>
                      ) : null}
                      <p className="mt-1 font-mono font-bold text-primary">
                        {fmt.format(p.value)} {unit}
                      </p>
                      {share != null && (
                        <p className="text-muted-foreground">
                          {share.toFixed(1).replace(".", ",")}% do total listado
                        </p>
                      )}
                    </div>
                  );
                }}
              />
              <Bar
                dataKey="value"
                radius={[0, 6, 6, 0]}
                isAnimationActive={false}
                cursor={onItemClick ? "pointer" : undefined}
                onClick={
                  onItemClick
                    ? (d: unknown) => {
                        // Recharts entrega o payload do item clicado.
                        const p =
                          (d as { payload?: VotesBarItem })?.payload ??
                          (d as VotesBarItem);
                        if (p && typeof p.key === "string") onItemClick(p);
                      }
                    : undefined
                }
              >
                {filtered.map((it) => {
                  const selected = selectedKey != null && it.key === selectedKey;
                  return (
                    <Cell
                      key={it.key}
                      // Todas com o MESMO degradê (cor segue a entidade);
                      // a selecionada vira ouro sólido + contorno.
                      fill={selected ? "hsl(var(--primary))" : `url(#${gid})`}
                      stroke={selected ? "hsl(var(--primary))" : undefined}
                      strokeWidth={selected ? 1.5 : 0}
                    />
                  );
                })}
                {showValues && (
                  <LabelList
                    dataKey="value"
                    position="right"
                    formatter={(v: unknown) => compactFmt.format(Number(v))}
                    className="fill-muted-foreground"
                    fontSize={10}
                  />
                )}
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
