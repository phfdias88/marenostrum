"use client";

/**
 * Analise por Bairro (campanha propria).
 *
 * IMPORTANTE: usa dados PROPRIOS do tenant (voting_places importados via CSV),
 * NAO dados oficiais do TSE. O TSE so publica votacao a nivel municipal no
 * dataset que importamos — bairros e sub-municipal e exige outro dataset
 * (votacao_secao) que ainda nao integramos.
 *
 * Layout:
 *  - Coluna esquerda: filtros (busca por nome) + lista de bairros ranqueada
 *  - Coluna direita: mapa heatmap centralizado no bairro clicado
 */
import { ArrowLeft, Loader2, MapPin, Search, X } from "lucide-react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type {
  HeatmapResponse,
  NeighborhoodStats,
  NeighborhoodStatsResponse,
} from "@/lib/types";

const NeighborhoodMap = dynamic(
  () => import("@/components/map/NeighborhoodMap"),
  { ssr: false, loading: () => <MapPlaceholder /> },
);

const numberFmt = new Intl.NumberFormat("pt-BR");

export default function BairrosPage() {
  const [data, setData] = useState<NeighborhoodStatsResponse | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<NeighborhoodStats | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api<NeighborhoodStatsResponse>("/v1/voting-places/by-neighborhood"),
      api<HeatmapResponse>("/v1/voting-places/heatmap"),
    ])
      .then(([nb, hm]) => {
        setData(nb);
        setHeatmap(hm);
      })
      .catch(() => {
        setData({ items: [], total_neighborhoods: 0, total_votes: 0 });
        setHeatmap({ points: [], total_places: 0, total_votes: 0, max_votes: 0 });
      })
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    if (!q) return data.items;
    return data.items.filter((n) =>
      n.neighborhood.toLowerCase().includes(q),
    );
  }, [data, search]);

  const maxVotes = data?.items[0]?.total_votes ?? 1;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">Análise por Bairro</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Votos da <strong>sua campanha</strong> agrupados por bairro
            (importados via{" "}
            <span className="text-foreground">Locais de Votação</span>).
            Clique num bairro pra focar o mapa.
          </p>
        </div>
        {data && data.total_neighborhoods > 0 && (
          <div className="flex gap-3">
            <Stat label="Bairros" value={data.total_neighborhoods} />
            <Stat label="Votos totais" value={data.total_votes} />
          </div>
        )}
      </header>

      {/* Empty state */}
      {!loading && data && data.total_neighborhoods === 0 && (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40 mb-6">
          <MapPin className="mx-auto h-10 w-10 text-muted-foreground" />
          <p className="text-lg font-semibold mt-3">
            Nenhum local de votação importado
          </p>
          <p className="text-sm text-muted-foreground mt-1 mb-4 max-w-md mx-auto">
            Pra ver a análise por bairro, importe primeiro a planilha de Locais
            de Votação (com colunas Bairro, Latitude, Longitude e Votos).
          </p>
          <Link
            href="/dashboard/map"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 text-sm"
          >
            Ir para o mapa
          </Link>
        </div>
      )}

      {/* Layout: lista + mapa */}
      {(loading || (data && data.total_neighborhoods > 0)) && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* Lista (esquerda) */}
          <aside className="lg:col-span-2 space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar bairro…"
                className="w-full pl-9 pr-9 py-2 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label="Limpar"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            <div className="text-xs text-muted-foreground px-1">
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="w-3 h-3 animate-spin" /> carregando…
                </span>
              ) : (
                `${numberFmt.format(filtered.length)} bairro(s)`
              )}
            </div>

            <ul className="rounded-lg border bg-card divide-y divide-border max-h-[70vh] overflow-auto">
              {filtered.length === 0 && !loading && (
                <li className="p-8 text-center text-sm text-muted-foreground">
                  Nenhum bairro com esse filtro.
                </li>
              )}
              {filtered.map((n, i) => {
                const pct = (n.total_votes / maxVotes) * 100;
                const active = selected?.neighborhood === n.neighborhood;
                return (
                  <li key={n.neighborhood}>
                    <button
                      onClick={() => setSelected(n)}
                      disabled={n.avg_lat == null}
                      className={`w-full text-left p-3 flex items-center gap-3 transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                        active ? "bg-accent/60" : "hover:bg-accent/40"
                      }`}
                    >
                      <span className="grid place-items-center w-7 h-7 rounded-full bg-muted text-muted-foreground text-xs font-bold shrink-0">
                        {i + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold truncate text-sm">
                          {n.neighborhood}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {numberFmt.format(n.total_places)} local(is){" "}
                          {n.avg_lat == null && (
                            <span className="text-amber-500">
                              · sem coords
                            </span>
                          )}
                        </p>
                        <div className="mt-1.5 h-1 rounded-full bg-muted overflow-hidden">
                          <div
                            className="h-full bg-primary transition-all"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                      <span className="font-mono font-bold tabular-nums text-sm shrink-0">
                        {numberFmt.format(n.total_votes)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          {/* Mapa (direita) */}
          <main className="lg:col-span-3">
            <div className="h-[70vh] min-h-[400px] rounded-lg border border-border overflow-hidden">
              <NeighborhoodMap
                heatmap={heatmap}
                focus={
                  selected && selected.avg_lat != null && selected.avg_lng != null
                    ? { lat: selected.avg_lat, lng: selected.avg_lng }
                    : null
                }
              />
            </div>
            {selected && (
              <p className="text-xs text-muted-foreground mt-2 px-1">
                Focado em <strong>{selected.neighborhood}</strong> ·{" "}
                {numberFmt.format(selected.total_votes)} votos em{" "}
                {numberFmt.format(selected.total_places)} local(is).
              </p>
            )}
          </main>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border bg-card/60 px-3 py-2 min-w-[100px]">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="text-xl font-bold mt-0.5">{numberFmt.format(value)}</p>
    </div>
  );
}

function MapPlaceholder() {
  return (
    <div className="h-full w-full grid place-items-center text-muted-foreground bg-card/40">
      Carregando mapa…
    </div>
  );
}
