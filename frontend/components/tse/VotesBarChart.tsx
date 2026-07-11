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

// Truncagem: corta com reticências; SEM sublinha, preserva o sufixo
// "(Município)" (desambiguador de homônimos em labels compostos legados).
function truncate(raw: string, maxChars: number, preserveSuffix: boolean): string {
  if (raw.length <= maxChars) return raw;
  if (preserveSuffix) {
    const m = raw.match(/^(.*?)\s*(\([^()]*\))$/);
    if (m) {
      const suffix = " " + m[2];
      const keep = Math.max(4, maxChars - suffix.length - 1);
      return m[1].slice(0, keep) + "…" + suffix;
    }
  }
  return raw.slice(0, maxChars - 1) + "…";
}

// Tick do eixo Y com RANKING: "1º Bangu". O rank é TEXTO (top-3 em ouro) — a
// cor da BARRA segue a entidade, nunca o rank (regra de dataviz: filtro que
// muda posições não pode "repintar" quem sobrou).
// Com `sub` vira DUAS linhas: nome em cima (inteiro, sem disputar espaço com
// o contexto) e município/bairro embaixo, menor e apagado — fim do
// "Camp… (Rio de Janeiro)" que escondia justamente o nome do bairro.
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
  sub,
}: TickProps & { maxChars: number; sub?: string }) {
  const raw = String(payload?.value ?? "");
  const label = truncate(raw, maxChars, !sub);
  // Linha 2 é menor (9.5px) → cabem mais caracteres na mesma largura.
  const subTxt = sub ? truncate(sub, Math.floor(maxChars * 1.35), false) : null;
  const top3 = index < 3;
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        x={0}
        y={0}
        dy={subTxt ? -1.5 : 4}
        textAnchor="end"
        fontSize={12}
      >
        <tspan
          fontSize={9.5}
          fontWeight={700}
          fill={top3 ? "hsl(var(--primary))" : "hsl(var(--muted-foreground))"}
          opacity={top3 ? 1 : 0.65}
        >
          {index + 1}º
        </tspan>
        <tspan dx={4} fill="hsl(var(--foreground))" opacity={0.95} fontWeight={600}>
          {label}
        </tspan>
      </text>
      {subTxt && (
        <text
          x={0}
          y={0}
          dy={11.5}
          textAnchor="end"
          fontSize={9.5}
          fill="hsl(var(--muted-foreground))"
          opacity={0.9}
        >
          {subTxt}
        </text>
      )}
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

  // Altura proporcional ao nº de barras, com piso. Tick de 2 linhas (nome +
  // contexto) pede ~40px por linha; sem sublabel, 30px bastam.
  const hasSub = useMemo(() => filtered.some((i) => i.sublabel), [filtered]);
  const rowH = hasSub ? 40 : 30;
  const height = Math.max(200, filtered.length * rowH + 36);

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
              barCategoryGap={7}
            >
              {/* Degradê de RELEVO ao longo da barra: base mais ESCURA → ponta
                  mais CLARA e vibrante (sensação de volume, polish do PO).
                  color-mix escurece/clareia a cor do tema; o stopColor de
                  atributo fica como FALLBACK (browsers sem color-mix ignoram
                  o style e usam o atributo). Uniforme em todas as barras: a
                  cor segue a ENTIDADE, não o rank. */}
              <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="1" y2="0">
                  <stop
                    offset="0%"
                    stopColor="hsl(var(--primary))"
                    stopOpacity={0.85}
                    style={{
                      stopColor:
                        "color-mix(in srgb, hsl(var(--primary)) 65%, black)",
                    }}
                  />
                  <stop offset="55%" stopColor="hsl(var(--primary))" />
                  <stop
                    offset="100%"
                    stopColor="hsl(var(--primary))"
                    style={{
                      stopColor:
                        "color-mix(in srgb, hsl(var(--primary)) 78%, white)",
                    }}
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
                // Tick custom: "1º Bangu" + linha 2 com o contexto (município/
                // bairro) — o nome não disputa mais espaço com o sufixo.
                tick={(p: unknown) => {
                  const tp = p as TickProps;
                  return (
                    <RankedTick
                      {...tp}
                      maxChars={Math.max(10, Math.floor((yAxisWidth - 26) / 7))}
                      sub={filtered[tp.index ?? 0]?.sublabel}
                    />
                  );
                }}
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
                // Espessura FIXA com tick de 2 linhas: a banda de 40px vira
                // barra de 18px + respiro (sem isso a barra engorda junto).
                barSize={hasSub ? 18 : undefined}
                // Trilho discreto atrás da barra: dá régua visual do 100% e
                // descola as barras curtas do fundo.
                background={{
                  fill: "hsl(var(--muted-foreground))",
                  fillOpacity: 0.06,
                  radius: 6,
                }}
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
                      // a selecionada vira ouro sólido + contorno. A sombra
                      // (drop-shadow) descola a barra do fundo — profundidade.
                      fill={selected ? "hsl(var(--primary))" : `url(#${gid})`}
                      stroke={selected ? "hsl(var(--primary))" : undefined}
                      strokeWidth={selected ? 1.5 : 0}
                      style={{
                        filter: selected
                          ? "drop-shadow(0 2px 4px rgb(0 0 0 / 0.4))"
                          : "drop-shadow(0 1px 2px rgb(0 0 0 / 0.28))",
                      }}
                    />
                  );
                })}
                {showValues && (
                  <LabelList
                    dataKey="value"
                    position="right"
                    formatter={(v: unknown) => compactFmt.format(Number(v))}
                    className="fill-foreground"
                    fontSize={11}
                    fontWeight={600}
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
