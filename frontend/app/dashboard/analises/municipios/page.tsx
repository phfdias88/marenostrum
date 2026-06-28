"use client";

/**
 * Analise por Municipios.
 * - Busca + filtro UF -> lista paginada
 * - Clique no municipio -> top candidatos (com filtro cargo opcional)
 */
import { ArrowLeft, Loader2, MapPin, Search, SearchX, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type {
  Page,
  TseMunicipality,
  TseMunicipalityResults,
} from "@/lib/types";
import { TSE_OFFICES, TSE_STATES } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { StateFlag } from "@/components/tse/StateFlag";
import { FavoriteStar } from "@/components/tse/FavoriteStar";
import { CandidateListSkeleton } from "@/components/tse/Skeletons";
import { EmptyState } from "@/components/tse/EmptyState";

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
          Top candidatos por cidade · busque qualquer município do Brasil.
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

          {loading && !data ? (
            <CandidateListSkeleton rows={6} />
          ) : data?.items.length === 0 ? (
            <div className="rounded-lg border bg-card">
              <EmptyState
                icon={SearchX}
                title="Nenhum município com esses filtros"
                hint="Tente outra UF ou um nome diferente."
              />
            </div>
          ) : (
          <div className="rounded-lg border bg-card divide-y divide-border">
            {data?.items.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelected(m)}
                className="w-full text-left p-4 hover:bg-accent/50 transition-colors flex items-center gap-4"
              >
                <StateFlag uf={m.state} size="md" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{m.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {m.state} · <span title="Código TSE do município">cód. TSE {m.tse_code}</span>
                  </p>
                </div>
              </button>
            ))}
          </div>
          )}

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
        <StateFlag uf={muni.state} size="lg" className="!w-16 !h-11 shadow" />
        <div className="flex-1">
          <h2 className="text-2xl font-bold">{muni.name}</h2>
          <p className="text-sm text-muted-foreground">
            {muni.state} · <span title="Código TSE do município">cód. TSE {muni.tse_code}</span>
          </p>
          <Link
            href={`/dashboard/analises/municipio/${muni.id}`}
            className="mt-1 inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
          >
            Abrir página completa →
          </Link>
        </div>
        <FavoriteStar
          fav={{
            kind: "municipality",
            id: muni.id,
            label: muni.name,
            sub: muni.state,
            state: muni.state,
          }}
          size={22}
        />
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

      {data?.year && (
        <p className="text-xs text-muted-foreground mb-3 -mt-2">
          Mais votados na eleição de <span className="font-semibold text-foreground">{data.year}</span>
          {" "}· para outros anos, abra a página completa.
        </p>
      )}

      {loading ? (
        <CandidateListSkeleton rows={6} />
      ) : !data || data.results.length === 0 ? (
        <div className="rounded-lg border bg-card">
          <EmptyState
            icon={SearchX}
            title="Sem dados de votação pra esse filtro"
            hint="Tente outro cargo neste município."
          />
        </div>
      ) : (
        <ol className="rounded-lg border bg-card divide-y divide-border">
          {data.results.map((r, i) => (
            <li key={r.candidate.id} className="p-3 flex items-center gap-3">
              <span className="grid place-items-center w-8 h-8 rounded-full bg-muted text-muted-foreground font-bold text-xs shrink-0">
                {i + 1}
              </span>
              <CandidatePhoto
                candidateId={r.candidate.id}
                name={r.candidate.urn_name}
                partyNumber={r.candidate.party.number}
                size="md"
              />
              <div className="flex-1 min-w-0">
                <p className="font-semibold truncate flex items-center gap-2">
                  <span className="text-primary font-mono">
                    {r.candidate.number}
                  </span>
                  <span className="truncate">{r.candidate.urn_name}</span>
                  <ResultBadge status={r.candidate.result_status} size="sm" />
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
