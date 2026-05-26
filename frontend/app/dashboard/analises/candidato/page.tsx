"use client";

/**
 * Analise de Candidato (estilo Politique).
 *
 * Layout:
 *  - Filtros: UF, Cargo, Busca (debounced 300ms)
 *  - Lista paginada de candidatos
 *  - Clique abre painel lateral com votos por municipio (top + total)
 */
import { ArrowLeft, Loader2, Map as MapIcon, Search, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type {
  Page,
  TseCandidate,
  TseCandidateResults,
} from "@/lib/types";
import { TSE_OFFICES, TSE_STATES } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { CandidateMapModal } from "@/components/tse/CandidateMapModal";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { CandidateProfile } from "@/components/tse/CandidateProfile";

const PAGE_SIZE = 20;
const numberFmt = new Intl.NumberFormat("pt-BR");

// Debounce simples — evita disparar fetch a cada keystroke
function useDebounce<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export default function CandidatoAnalysisPage() {
  const [state, setState] = useState<string>("MG");
  const [office, setOffice] = useState<string>("11"); // prefeito
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 300);

  const [page, setPage] = useState(0);
  const [data, setData] = useState<Page<TseCandidate> | null>(null);
  const [loading, setLoading] = useState(false);

  const [selected, setSelected] = useState<TseCandidate | null>(null);
  const [details, setDetails] = useState<TseCandidateResults | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [showMap, setShowMap] = useState(false);

  // Reset page quando filtros mudam
  useEffect(() => setPage(0), [state, office, debouncedSearch]);

  // Fetch lista
  useEffect(() => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });
    if (state) params.set("state", state);
    if (office) params.set("office_code", office);
    if (debouncedSearch.trim()) params.set("search", debouncedSearch.trim());

    setLoading(true);
    api<Page<TseCandidate>>(`/v1/tse/candidates?${params.toString()}`)
      .then(setData)
      .catch((err) => {
        const msg = err instanceof ApiError ? err.message : "Erro";
        console.error("[candidato]", msg);
        setData({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 });
      })
      .finally(() => setLoading(false));
  }, [state, office, debouncedSearch, page]);

  // Fetch detalhe (votos por municipio)
  useEffect(() => {
    if (!selected) {
      setDetails(null);
      return;
    }
    setDetailsLoading(true);
    api<TseCandidateResults>(`/v1/tse/candidates/${selected.id}/results`)
      .then(setDetails)
      .catch(() => setDetails(null))
      .finally(() => setDetailsLoading(false));
  }, [selected]);

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Breadcrumb */}
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Análises
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-bold">Análise de Candidato</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Busque qualquer candidato registrado no TSE 2024.
        </p>
      </header>

      {/* Filtros */}
      <section className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-6">
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
          className="md:col-span-3"
        />
        <div className="md:col-span-7">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">
            Buscar
          </label>
          <div className="relative mt-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Nome, nome de urna ou apelido…"
              className="w-full pl-9 pr-9 py-2 rounded-md bg-card border border-border
                         focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                aria-label="Limpar busca"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </section>

      {/* Grid: lista | detalhe */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Lista */}
        <div className="lg:col-span-2 space-y-3">
          <div className="text-sm text-muted-foreground">
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="w-3 h-3 animate-spin" /> carregando…
              </span>
            ) : (
              <>
                {numberFmt.format(total)} candidato(s) encontrado(s)
              </>
            )}
          </div>

          <div className="rounded-lg border bg-card divide-y divide-border">
            {data?.items.length === 0 && !loading && (
              <div className="p-10 text-center text-sm text-muted-foreground">
                Nenhum candidato com esses filtros.
              </div>
            )}
            {data?.items.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelected(c)}
                className={`w-full text-left p-4 hover:bg-accent/50 transition-colors flex items-center gap-4
                            ${selected?.id === c.id ? "bg-accent/60" : ""}`}
              >
                <CandidatePhoto
                  candidateId={c.id}
                  name={c.urn_name}
                  partyNumber={c.party.number}
                  size="md"
                />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate flex items-center gap-2">
                    <span className="text-primary font-mono">{c.number}</span>
                    <span className="truncate">{c.urn_name}</span>
                    <ResultBadge status={c.result_status} size="sm" />
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {c.name} · {c.party.abbreviation}
                  </p>
                </div>
                <div className="text-right text-xs shrink-0">
                  <p className="font-medium">{c.office_name}</p>
                  <p className="text-muted-foreground">{c.state}</p>
                </div>
              </button>
            ))}
          </div>

          {/* Paginação */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2 text-sm">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0 || loading}
              >
                ← Anterior
              </Button>
              <span className="text-muted-foreground">
                Página {page + 1} de {numberFmt.format(totalPages)}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={page + 1 >= totalPages || loading}
              >
                Próxima →
              </Button>
            </div>
          )}
        </div>

        {/* Detalhe */}
        <aside className="lg:col-span-1">
          {!selected ? (
            <div className="rounded-lg border bg-card/40 p-8 text-center text-sm text-muted-foreground sticky top-6">
              Clique num candidato pra ver os votos por município.
            </div>
          ) : (
            <CandidateDetail
              candidate={selected}
              details={details}
              loading={detailsLoading}
              onOpenMap={() => setShowMap(true)}
              onClose={() => setSelected(null)}
            />
          )}
        </aside>
      </section>

      {/* Modal mapa */}
      {showMap && details && (
        <CandidateMapModal
          results={details}
          onClose={() => setShowMap(false)}
        />
      )}
    </div>
  );
}

// -------------------------------------------------------------- detail panel

function CandidateDetail({
  candidate,
  details,
  loading,
  onClose,
  onOpenMap,
}: {
  candidate: TseCandidate;
  details: TseCandidateResults | null;
  loading: boolean;
  onClose: () => void;
  onOpenMap: () => void;
}) {
  return (
    <div className="rounded-lg border bg-card p-5 sticky top-6 space-y-4">
      <button
        onClick={onClose}
        className="absolute top-3 right-3 text-muted-foreground hover:text-foreground p-1 z-10"
        aria-label="Fechar"
      >
        <X className="w-4 h-4" />
      </button>

      <div className="flex flex-col items-center text-center">
        <CandidatePhoto
          candidateId={candidate.id}
          name={candidate.urn_name}
          partyNumber={candidate.party.number}
          size="xl"
        />
        <p className="text-xs uppercase tracking-wider text-muted-foreground mt-3">
          {candidate.office_name} · {candidate.state}
        </p>
        <h2 className="text-lg font-bold mt-0.5">{candidate.urn_name}</h2>
        <p className="text-xs text-muted-foreground">{candidate.name}</p>
        <div className="mt-2">
          <ResultBadge status={candidate.result_status} />
        </div>
      </div>

      <div className="flex items-center justify-center gap-2 text-sm">
        <span className="grid place-items-center w-9 h-9 rounded-md bg-primary/15 text-primary font-bold">
          {candidate.number}
        </span>
        <div className="text-left">
          <p className="font-medium">{candidate.party.abbreviation}</p>
          <p className="text-xs text-muted-foreground truncate max-w-[180px]">
            {candidate.party.name}
          </p>
        </div>
      </div>

      {candidate.situation && !candidate.situation.startsWith("#") && (
        <p className="text-xs">
          <span className="text-muted-foreground">Situação: </span>
          <span className="font-medium">{candidate.situation}</span>
        </p>
      )}

      {/* Patrimonio + redes vem do /results (details), nao da lista */}
      <CandidateProfile
        assetsTotal={details?.candidate.assets_total ?? null}
        socialLinks={details?.candidate.social_links ?? null}
      />

      <hr className="border-border" />

      {loading ? (
        <div className="py-8 text-center">
          <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
        </div>
      ) : !details ? (
        <p className="text-sm text-muted-foreground">Sem dados de votação.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 text-center">
            <div className="rounded-md bg-card/60 border border-border p-3">
              <p className="text-2xl font-bold text-primary">
                {numberFmt.format(details.total_votes)}
              </p>
              <p className="text-xs text-muted-foreground">Total de votos</p>
            </div>
            <div className="rounded-md bg-card/60 border border-border p-3">
              <p className="text-2xl font-bold">
                {numberFmt.format(details.municipalities_with_votes)}
              </p>
              <p className="text-xs text-muted-foreground">Municípios</p>
            </div>
          </div>

          <Button
            variant="outline"
            className="w-full"
            onClick={onOpenMap}
            disabled={
              !details.results.some(
                (r) =>
                  r.municipality.latitude != null &&
                  r.municipality.longitude != null,
              )
            }
          >
            <MapIcon className="w-4 h-4" />
            Ver no mapa
          </Button>

          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Top municípios
            </p>
            <ul className="space-y-1.5 max-h-80 overflow-auto pr-1">
              {details.results.slice(0, 30).map((r) => (
                <li
                  key={r.municipality.id}
                  className="flex items-center justify-between gap-3 text-sm py-1.5 border-b border-border/40 last:border-0"
                >
                  <span className="truncate">
                    {r.municipality.name}{" "}
                    <span className="text-muted-foreground">/{r.municipality.state}</span>
                  </span>
                  <span className="font-mono font-medium shrink-0">
                    {numberFmt.format(r.votes)}
                  </span>
                </li>
              ))}
            </ul>
            {details.results.length > 30 && (
              <p className="text-xs text-muted-foreground pt-2">
                + {details.results.length - 30} outro(s) município(s) com votos
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// -------------------------------------------------------------- subcomponent

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
        className="w-full mt-1 py-2 px-3 rounded-md bg-card border border-border
                   focus:outline-none focus:ring-2 focus:ring-primary/30"
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
