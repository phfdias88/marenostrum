"use client";

/**
 * Mapa do Brasil colorido pelo partido vencedor em cada município.
 *
 * Melhorias visuais:
 *  - Tile tematico (CartoDB Dark / Voyager).
 *  - Top 3 municipios pulsam em dourado.
 *  - Hover mostra tooltip leve.
 *  - Click num partido na legenda destaca so esses municipios.
 *  - Chips de UF (regiao + capitais) pra zoom rapido.
 *  - Overlay com totais quando partido destacado.
 */
import { ArrowLeft, Loader2, Map as MapIcon, X } from "lucide-react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { TseWinnersMapResponse } from "@/lib/types";
import { PresentButton } from "@/components/ui/PresentButton";

const WinnersMap = dynamic(() => import("@/components/map/WinnersMap"), {
  ssr: false,
  loading: () => (
    <div className="h-full grid place-items-center text-muted-foreground">
      Carregando mapa…
    </div>
  ),
});

const numberFmt = new Intl.NumberFormat("pt-BR");

const PARTY_COLOR: Record<number, string> = {
  10: "#0050a0", 11: "#ff8c00", 12: "#c41a1a", 13: "#e30613", 14: "#0099cc",
  15: "#2d6f30", 16: "#a31a1a", 17: "#ffcd1a", 18: "#7fbc41", 19: "#16a085",
  20: "#1f5fa6", 22: "#0a2a7d", 23: "#3f51b5", 25: "#0050a0", 27: "#27ae60",
  28: "#e91e63", 30: "#ff5a00", 33: "#0d47a1", 35: "#c97312", 36: "#7b1fa2",
  40: "#d81b60", 43: "#1e8a3c", 44: "#ed9b00", 45: "#005faa", 50: "#dc143c",
  51: "#1c8537", 55: "#00a99d", 65: "#cc0000", 70: "#d35400", 77: "#673ab7",
  80: "#6b6b6b", 90: "#37474f",
};

const OPTIONS = [
  { value: "2024-11", label: "Prefeitos 2024", year: "2024", office: "11" },
  { value: "2022-1", label: "Presidente 2022", year: "2022", office: "1" },
  { value: "2022-3", label: "Governadores 2022", year: "2022", office: "3" },
];

// Chips de zoom rapido (lat, lng aproximados das capitais + Brasil).
const UF_CHIPS: { uf: string; label: string; lat: number; lng: number; zoom: number }[] = [
  { uf: "BR", label: "Brasil",     lat: -14.5, lng: -52.0, zoom: 4 },
  { uf: "SP", label: "SP",         lat: -22.5, lng: -48.5, zoom: 7 },
  { uf: "RJ", label: "RJ",         lat: -22.3, lng: -42.7, zoom: 7 },
  { uf: "MG", label: "MG",         lat: -18.5, lng: -44.5, zoom: 6 },
  { uf: "BA", label: "BA",         lat: -12.5, lng: -41.5, zoom: 6 },
  { uf: "RS", label: "RS",         lat: -30.0, lng: -53.5, zoom: 6 },
  { uf: "PR", label: "PR",         lat: -25.0, lng: -51.5, zoom: 7 },
  { uf: "PE", label: "PE",         lat:  -8.5, lng: -38.0, zoom: 7 },
];

export default function MapaPage() {
  const [sel, setSel] = useState("2024-11");
  const [data, setData] = useState<TseWinnersMapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [highlightedParty, setHighlightedParty] = useState<number | null>(null);
  const [focusReq, setFocusReq] = useState<
    { lat: number; lng: number; zoom: number; key: number } | null
  >(null);

  const opt = OPTIONS.find((o) => o.value === sel)!;

  useEffect(() => {
    setLoading(true);
    setHighlightedParty(null);
    api<TseWinnersMapResponse>(
      `/v1/tse/stats/winners-map?year=${opt.year}&office_code=${opt.office}`,
    )
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  // Legenda: conta municipios por partido (top 10)
  const legend = useMemo(() => {
    if (!data) return [];
    const counts = new Map<string, { abbr: string; number: number; n: number; votes: number }>();
    for (const p of data.points) {
      const e = counts.get(p.party_abbreviation) ?? {
        abbr: p.party_abbreviation,
        number: p.party_number,
        n: 0,
        votes: 0,
      };
      e.n++;
      e.votes += p.votes;
      counts.set(p.party_abbreviation, e);
    }
    return [...counts.values()].sort((a, b) => b.n - a.n).slice(0, 12);
  }, [data]);

  const highlightedInfo = useMemo(() => {
    if (highlightedParty == null || !data) return null;
    const items = data.points.filter((p) => p.party_number === highlightedParty);
    const totalVotes = items.reduce((s, p) => s + p.votes, 0);
    const ufSet = new Set(items.map((i) => i.state));
    return {
      abbr: items[0]?.party_abbreviation ?? "—",
      n: items.length,
      votes: totalVotes,
      ufs: ufSet.size,
    };
  }, [highlightedParty, data]);

  function jumpTo(c: typeof UF_CHIPS[number]) {
    setFocusReq({ lat: c.lat, lng: c.lng, zoom: c.zoom, key: Date.now() });
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-4 flex items-end justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
            <MapIcon className="w-5 h-5" />
          </span>
          <div>
            <h1 className="text-2xl font-bold">Mapa partidário do Brasil</h1>
            <p className="text-sm text-muted-foreground">
              Cada município pintado pela cor do partido mais votado.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <PresentButton />
          <select
            value={sel}
            onChange={(e) => setSel(e.target.value)}
            className="py-2 px-3 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            {OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      {/* Chips UF */}
      <div className="mb-3 flex items-center gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {UF_CHIPS.map((c) => (
          <button
            key={c.uf}
            onClick={() => jumpTo(c)}
            className="px-3 py-1 rounded-full bg-card border border-border text-xs hover:border-primary/60 hover:text-primary transition-colors shrink-0"
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3">
          <div className="h-[70vh] rounded-lg border border-border overflow-hidden relative">
            {loading && (
              <div className="absolute inset-0 z-[500] grid place-items-center bg-background/60">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            )}
            {data && (
              <WinnersMap
                points={data.points}
                highlightedParty={highlightedParty}
                focusRequest={focusReq}
              />
            )}

            {/* Overlay com info do partido destacado */}
            {highlightedInfo && (
              <div className="absolute top-3 left-3 z-[400] mn-glass mn-slide-in rounded-xl px-4 py-3 max-w-xs">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground">
                      Partido destacado
                    </p>
                    <p className="text-lg font-bold mt-0.5" style={{ color: PARTY_COLOR[highlightedParty!] }}>
                      {highlightedInfo.abbr}
                    </p>
                    <div className="grid grid-cols-3 gap-3 mt-2 text-center">
                      <Stat label="cidades" value={highlightedInfo.n} />
                      <Stat label="UFs" value={highlightedInfo.ufs} />
                      <Stat
                        label="votos"
                        value={highlightedInfo.votes}
                        compact
                      />
                    </div>
                  </div>
                  <button
                    onClick={() => setHighlightedParty(null)}
                    aria-label="Limpar"
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <aside className="lg:col-span-1">
          <div className="rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">
                {data ? numberFmt.format(data.points.length) : "…"} municípios
              </p>
              {highlightedParty != null && (
                <button
                  onClick={() => setHighlightedParty(null)}
                  className="text-[11px] text-primary hover:underline"
                >
                  limpar
                </button>
              )}
            </div>
            <ul className="space-y-1">
              {legend.map((l) => {
                const active = highlightedParty === l.number;
                const dim = highlightedParty != null && !active;
                return (
                  <li key={l.abbr}>
                    <button
                      onClick={() =>
                        setHighlightedParty(active ? null : l.number)
                      }
                      className={
                        "w-full flex items-center justify-between gap-2 text-sm rounded px-2 py-1 transition-all " +
                        (active
                          ? "bg-primary/15 ring-1 ring-primary/40"
                          : "hover:bg-accent/60 " + (dim ? "opacity-40" : ""))
                      }
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <span
                          className="w-3 h-3 rounded-full shrink-0"
                          style={{ background: PARTY_COLOR[l.number] ?? "#888" }}
                        />
                        <span className="font-medium truncate">{l.abbr}</span>
                      </span>
                      <span className="text-muted-foreground tabular-nums">
                        {numberFmt.format(l.n)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400 shrink-0" />
                Pontos dourados = os 3 municípios com mais votos neste pleito.
              </span>
              <br />
              Clique num partido pra destacar só os municípios dele. Use os chips
              acima do mapa pra ir direto pra uma UF.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  compact,
}: {
  label: string;
  value: number;
  compact?: boolean;
}) {
  const fmt = compact
    ? new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 })
    : numberFmt;
  return (
    <div>
      <p className="text-lg font-bold tabular-nums leading-tight">
        {fmt.format(value)}
      </p>
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
    </div>
  );
}
