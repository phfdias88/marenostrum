"use client";

/**
 * Mapa do Brasil colorido pelo partido vencedor em cada município.
 */
import { ArrowLeft, Loader2, Map as MapIcon } from "lucide-react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { TseWinnersMapResponse } from "@/lib/types";

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

export default function MapaPage() {
  const [sel, setSel] = useState("2024-11");
  const [data, setData] = useState<TseWinnersMapResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const opt = OPTIONS.find((o) => o.value === sel)!;

  useEffect(() => {
    setLoading(true);
    api<TseWinnersMapResponse>(
      `/v1/tse/stats/winners-map?year=${opt.year}&office_code=${opt.office}`,
    )
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  // Legenda: conta municipios por partido (top 8)
  const legend = useMemo(() => {
    if (!data) return [];
    const counts = new Map<string, { abbr: string; number: number; n: number }>();
    for (const p of data.points) {
      const e = counts.get(p.party_abbreviation) ?? {
        abbr: p.party_abbreviation,
        number: p.party_number,
        n: 0,
      };
      e.n++;
      counts.set(p.party_abbreviation, e);
    }
    return [...counts.values()].sort((a, b) => b.n - a.n).slice(0, 10);
  }, [data]);

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
              Cada município pintado pela cor do partido vencedor.
            </p>
          </div>
        </div>
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
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3">
          <div className="h-[70vh] rounded-lg border border-border overflow-hidden relative">
            {loading && (
              <div className="absolute inset-0 z-[500] grid place-items-center bg-background/60">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            )}
            {data && <WinnersMap points={data.points} />}
          </div>
        </div>
        <aside className="lg:col-span-1">
          <div className="rounded-lg border bg-card p-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              {data ? numberFmt.format(data.points.length) : "…"} municípios
            </p>
            <ul className="space-y-1.5">
              {legend.map((l) => (
                <li key={l.abbr} className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex items-center gap-2 min-w-0">
                    <span
                      className="w-3 h-3 rounded-full shrink-0"
                      style={{ background: PARTY_COLOR[l.number] ?? "#888" }}
                    />
                    <span className="font-medium truncate">{l.abbr}</span>
                  </span>
                  <span className="text-muted-foreground tabular-nums">{numberFmt.format(l.n)}</span>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
