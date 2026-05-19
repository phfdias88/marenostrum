"use client";

/**
 * Analise por Municipios.
 * - Busca + filtro UF -> lista paginada
 * - Clique no municipio -> top candidatos (com filtro cargo opcional)
 */
import { ArrowLeft, Loader2, MapPin, Search, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type {
  Page,
  TseMunicipality,
  TseMunicipalityResults,
} from "@/lib/types";
import { TSE_OFFICES, TSE_STATES } from "@/lib/types";

const PAGE_SIZE = 25;
const numberFmt = new Intl.NumberFormat("pt-BR");

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

export default function MunicipiosAnalysisPage() {
  const [state, setState] = useState("");
  const [search, setSearch] = useState("");
  const debounced = useDebounce(search, 300);

  const [page, setPage] = useState(0);
  const [data, setData] = useState<Page<TseMunicipality> | null>(null);
  const [loading, setLoading] = useState(true);

  const [selected, setSelected] = useState<TseMunicipality | null>(null);

  useEffect(() => setPage(0), [state, debounced]);

  useEffect(() => {
    const p = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });
    if (state) p.set("state", state);
    if (debounced.trim()) p.set("search", debounced.trim());
    setLoading(true);
    api<Page<TseMunicipality>>(`/v1/tse/municipalities?${p.toString()}`)
      .then(setData)
      .catch(() => setData({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 }))
      .finally(() => setLoading(false));
  }, [state, debounced, page]);

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-bold">Análise por Município</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Top candidatos por cidade — 5.568 municípios do Brasil.
        </p>
      </header>

      {selected ? (
        <MunicipalityDrill muni={selected} onBack={() => setSelected(null)} />
      ) : (
        <>
          {/* Filtros */}
          <section className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-5">
            <Select
              label="UF"
              value={state}
              onChange={setState}
              options={[
                { value: "", label: "Todas" },
                ...TSE_STATES.map((s) => ({ value: s, label: s })),
              ]}
              className="md:col-span-2"
            />
            <div className="md:col-span-10">
              <label className="text-xs uppercase tracking-wider text-muted-foreground">
                Buscar
              </label>
              <div className="relative mt-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Nome do município…"
                  className="w-full pl-9 pr-9 py-2 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
                {search && (
                  <button
                    onClick={() => setSearch("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          </section>

          <div className="text-sm text-muted-foreground mb-2">
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="w-3 h-3 animate-spin" /> carregando…
              </span>
            ) : (
              `${numberFmt.format(total)} município(s)`
            )}
          </div>

          <div className="rounded-lg border bg-card divide-y divide-border">
            {data?.items.length === 0 && !loading && (
              <div className="p-10 text-center text-sm text-muted-foreground">
                Nenhum município com esses filtros.
              </div>
            )}
            {data?.items.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelected(m)}
                className="w-full text-left p-4 hover:bg-accent/50 transition-colors flex items-center gap-4"
              >
                <MapPin className="w-5 h-5 text-primary shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{m.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {m.state} · TSE {m.tse_code}
                  </p>
                </div>
              </button>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-3 text-sm">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0 || loading}
                className="text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                ← Anterior
              </button>
              <span className="text-muted-foreground">
                Página {page + 1} de {numberFmt.format(totalPages)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page + 1 >= totalPages || loading}
                className="text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                Próxima →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ----------------------------------------------------------------- drill

function MunicipalityDrill({
  muni,
  onBack,
}: {
  muni: TseMunicipality;
  onBack: () => void;
}) {
  const [office, setOffice] = useState("11");
  const [data, setData] = useState<TseMunicipalityResults | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const p = new URLSearchParams({ limit: "30" });
    if (office) p.set("office_code", office);
    setLoading(true);
    api<TseMunicipalityResults>(
      `/v1/tse/municipalities/${muni.id}/top-candidates?${p.toString()}`,
    )
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [muni.id, office]);

  const maxVotes = data?.results[0]?.votes ?? 1;

  return (
    <div>
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Todos os municípios
      </button>

      <div className="flex items-center gap-4 mb-6">
        <span className="grid place-items-center w-16 h-16 rounded-lg bg-primary/15 text-primary">
          <MapPin className="w-7 h-7" />
        </span>
        <div>
          <h2 className="text-2xl font-bold">{muni.name}</h2>
          <p className="text-sm text-muted-foreground">
            {muni.state} · TSE {muni.tse_code}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-5">
        <Select
          label="Cargo"
          value={office}
          onChange={setOffice}
          options={[
            { value: "", label: "Todos" },
            ...Object.entries(TSE_OFFICES).map(([k, v]) => ({
              value: k,
              label: v,
            })),
          ]}
        />
      </div>

      {loading ? (
        <div className="py-12 text-center">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
        </div>
      ) : !data || data.results.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          Sem dados de votação pra esse filtro.
        </p>
      ) : (
        <ol className="rounded-lg border bg-card divide-y divide-border">
          {data.results.map((r, i) => (
            <li key={r.candidate.id} className="p-3 flex items-center gap-3">
              <span className="grid place-items-center w-8 h-8 rounded-full bg-muted text-muted-foreground font-bold text-xs shrink-0">
                {i + 1}
              </span>
              <span className="grid place-items-center w-10 h-10 rounded-md bg-primary/15 text-primary font-bold text-sm shrink-0">
                {r.candidate.number}
              </span>
              <div className="flex-1 min-w-0">
                <p className="font-semibold truncate">
                  {r.candidate.urn_name}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {r.candidate.party.abbreviation} · {r.candidate.office_name}
                </p>
                <div className="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${(r.votes / maxVotes) * 100}%` }}
                  />
                </div>
              </div>
              <span className="font-mono font-bold tabular-nums shrink-0">
                {numberFmt.format(r.votes)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// -------------------------------------------------------------- select

function Select({
  label,
  value,
  onChange,
  options,
  className,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-1 py-2 px-3 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
