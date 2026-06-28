"use client";

/**
 * Analise de Candidato (estilo Politique).
 *
 * Layout:
 *  - Filtros: UF, Cargo, Busca (debounced 300ms)
 *  - Lista paginada de candidatos
 *  - Clique abre painel lateral com votos por municipio (top + total)
 */
import { ArrowLeft, CheckCircle2, Download, Loader2, Map as MapIcon, Search, SearchX, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type {
  Page,
  TseCandidate,
  TseCandidateResults,
  TseMunicipality,
} from "@/lib/types";
import { TSE_OFFICES, TSE_STATES } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { CandidateMapModal } from "@/components/tse/CandidateMapModal";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { CandidateProfile } from "@/components/tse/CandidateProfile";
import { FavoriteStar } from "@/components/tse/FavoriteStar";
import { CandidateListSkeleton } from "@/components/tse/Skeletons";
import { EmptyState } from "@/components/tse/EmptyState";
import { downloadCsv } from "@/lib/csv";
import { OUTCOME_LABEL, classifyResult } from "@/lib/types";

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
  const [year, setYear] = useState<string>(""); // "" = todos os anos
  const [state, setState] = useState<string>(""); // "" = todas as UFs
  const [office, setOffice] = useState<string>("11"); // prefeito
  const [search, setSearch] = useState("");
  const [electedOnly, setElectedOnly] = useState(false);
  const [muniSearch, setMuniSearch] = useState("");
  const muniDebounced = useDebounce(muniSearch, 300);
  const [muniResults, setMuniResults] = useState<TseMunicipality[]>([]);
  const [selectedMuni, setSelectedMuni] = useState<TseMunicipality | null>(null);
  const debouncedSearch = useDebounce(search, 300);

  // Cargos municipais (11,12,13) só existem em anos municipais; os demais (1-10),
  // em anos gerais. Ao trocar o ano, se o cargo selecionado não couber no novo
  // pleito, volta pra "Todos" — senão a lista viria vazia (ex.: 2002 + Prefeito).
  function handleYearChange(newYear: string) {
    setYear(newYear);
    if (!newYear || !office) return;
    const muniYear = ["2024", "2020", "2016", "2012", "2008", "2004"].includes(newYear);
    const muniOffice = ["11", "12", "13"].includes(office);
    if (muniYear !== muniOffice) setOffice("");
  }

  // Busca municipios pra filtro
  useEffect(() => {
    if (selectedMuni) return;
    const q = muniDebounced.trim();
    if (q.length < 2) { setMuniResults([]); return; }
    const p = new URLSearchParams({ limit: "10", search: q });
    if (state) p.set("state", state);
    api<Page<TseMunicipality>>(`/v1/tse/municipalities?${p.toString()}`)
      .then((r) => setMuniResults(r.items))
      .catch(() => setMuniResults([]));
  }, [muniDebounced, state, selectedMuni]);

  const [page, setPage] = useState(0);
  const [data, setData] = useState<Page<TseCandidate> | null>(null);
  const [loading, setLoading] = useState(false);

  const [selected, setSelected] = useState<TseCandidate | null>(null);
  const [details, setDetails] = useState<TseCandidateResults | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Exporta a lista filtrada (até 1000) em CSV pro Excel
  async function exportCsv() {
    setExporting(true);
    try {
      const params = new URLSearchParams({ limit: "1000", offset: "0" });
      if (year) params.set("year", year);
      if (state) params.set("state", state);
      if (office) params.set("office_code", office);
      if (debouncedSearch.trim()) params.set("search", debouncedSearch.trim());
      // Mesma unificação por pessoa que a lista exibida (ver fetch abaixo).
      if (debouncedSearch.trim() || office || year || state) {
        params.set("group_person", "true");
      }
      const res = await api<Page<TseCandidate>>(
        `/v1/tse/candidates?${params.toString()}`,
      );
      const rows = res.items.map((c) => ({
        numero: c.number,
        urna: c.urn_name,
        nome: c.name,
        partido: c.party.abbreviation,
        cargo: c.office_name,
        uf: c.state,
        resultado: OUTCOME_LABEL[classifyResult(c.result_status)],
      }));
      downloadCsv(
        `candidatos-${state || "br"}-${office || "todos"}`,
        [
          { key: "numero", label: "Número" },
          { key: "urna", label: "Nome de urna" },
          { key: "nome", label: "Nome" },
          { key: "partido", label: "Partido" },
          { key: "cargo", label: "Cargo" },
          { key: "uf", label: "UF" },
          { key: "resultado", label: "Resultado" },
        ],
        rows,
      );
    } catch {
      /* silencioso — botão volta ao normal */
    } finally {
      setExporting(false);
    }
  }

  // Reset page quando filtros mudam
  useEffect(() => setPage(0), [year, state, office, debouncedSearch, electedOnly, selectedMuni]);

  // Fetch lista
  useEffect(() => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });
    if (year) params.set("year", year);
    if (state) params.set("state", state);
    if (office) params.set("office_code", office);
    if (debouncedSearch.trim()) params.set("search", debouncedSearch.trim());
    if (electedOnly) params.set("elected_only", "true");
    if (selectedMuni) params.set("municipality_id", selectedMuni.id);
    // Unifica candidaturas da MESMA pessoa (Aarão 2016/2020/2024 = 1 linha, com
    // badge "N candidaturas"). Pula só quando NENHUM filtro está ativo
    // (cargo/ano/UF/busca/cidade vazios) — aí a janela rodaria na tabela inteira
    // (~60s). Com qualquer filtro fica rápido (cargo ~3s, +UF/ano sub-segundo) e
    // o nginx ainda cacheia a resposta.
    if (debouncedSearch.trim() || office || year || state || selectedMuni) {
      params.set("group_person", "true");
    }

    setLoading(true);
    api<Page<TseCandidate>>(`/v1/tse/candidates?${params.toString()}`)
      .then(setData)
      .catch((err) => {
        const msg = err instanceof ApiError ? err.message : "Erro";
        console.error("[candidato]", msg);
        setData({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 });
      })
      .finally(() => setLoading(false));
  }, [year, state, office, debouncedSearch, page, electedOnly, selectedMuni]);

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

  // Deep-link: ?focus={id} (vindo dos Favoritos) abre o candidato direto.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("focus");
    if (!id) return;
    api<TseCandidateResults>(`/v1/tse/candidates/${id}/results`)
      .then((r) => {
        setSelected(r.candidate);
        setDetails(r);
      })
      .catch(() => {});
  }, []);

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
          Busque qualquer candidato registrado no TSE — candidaturas de 2002 a 2024.
        </p>
      </header>

      {/* Filtros */}
      <section className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-6">
        <Select
          label="Ano"
          value={year}
          onChange={handleYearChange}
          options={[
            { value: "", label: "Todos" },
            { value: "2024", label: "2024" },
            { value: "2022", label: "2022" },
            { value: "2020", label: "2020" },
            { value: "2018", label: "2018" },
            { value: "2016", label: "2016" },
            { value: "2014", label: "2014" },
            { value: "2010", label: "2010" },
            { value: "2006", label: "2006" },
            { value: "2002", label: "2002" },
          ]}
          className="md:col-span-2"
        />
        <Select
          label="UF"
          value={state}
          onChange={setState}
          options={[
            { value: "", label: "Brasil (todas)" },
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
        <div className="md:col-span-5">
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
        {/* Chips de filtro rapido */}
        <div className="md:col-span-12 flex items-center gap-2 -mt-1 flex-wrap">
          <button
            onClick={() => setElectedOnly((v) => !v)}
            data-no-mobile-touch
            className={
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors " +
              (electedOnly
                ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/40"
                : "bg-card text-muted-foreground border-border hover:border-emerald-500/40 hover:text-emerald-400")
            }
            aria-pressed={electedOnly}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            Só eleitos
          </button>

          {/* Filtro por cidade */}
          {selectedMuni ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border bg-primary/15 text-primary border-primary/40">
              <MapIcon className="w-3.5 h-3.5" />
              {selectedMuni.name}/{selectedMuni.state}
              <button
                onClick={() => { setSelectedMuni(null); setMuniSearch(""); }}
                className="ml-1 hover:text-foreground"
                aria-label="Remover filtro cidade"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ) : (
            <div className="relative">
              <input
                value={muniSearch}
                onChange={(e) => setMuniSearch(e.target.value)}
                placeholder="Filtrar por cidade…"
                className="pl-3 pr-3 py-1.5 rounded-full text-xs bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30 w-44"
              />
              {muniResults.length > 0 && (
                <div className="absolute z-20 top-full left-0 mt-1 rounded-lg border bg-card shadow-xl divide-y divide-border min-w-[14rem] max-h-48 overflow-auto">
                  {muniResults.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => { setSelectedMuni(m); setMuniResults([]); setMuniSearch(""); }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-accent/50 flex items-center justify-between"
                    >
                      <span>{m.name}</span>
                      <span className="text-xs text-muted-foreground">{m.state}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Grid: lista | detalhe */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Lista */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="w-3 h-3 animate-spin" /> carregando…
                </span>
              ) : total === 1 ? (
                "1 candidato encontrado"
              ) : (
                `${numberFmt.format(total)} candidatos encontrados`
              )}
            </span>
            {!loading && total > 0 && (
              <button
                onClick={exportCsv}
                disabled={exporting}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border bg-card hover:border-primary/60 text-xs transition-colors disabled:opacity-50 shrink-0"
                title="Baixar CSV (até 1000 candidatos do filtro atual)"
              >
                {exporting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Download className="w-3.5 h-3.5" />
                )}
                Exportar CSV
              </button>
            )}
          </div>

          {loading && !data ? (
            <CandidateListSkeleton rows={6} />
          ) : data?.items.length === 0 ? (
            <div className="rounded-lg border bg-card">
              <EmptyState
                icon={SearchX}
                title="Nenhum candidato com esses filtros"
                hint="Tente outra UF, cargo ou termo de busca."
              />
            </div>
          ) : (
          <div className="rounded-lg border bg-card divide-y divide-border">
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
                  <p className="text-muted-foreground">
                    {c.state}
                    {c.primary_municipality_name ? ` · ${c.primary_municipality_name}` : ""}
                    {" · "}{c.election.year}
                  </p>
                  {c.candidacy_count != null && c.candidacy_count > 1 && (
                    <span
                      className="inline-block mt-0.5 rounded-full bg-primary/10 text-primary px-1.5 py-0.5 text-[10px] font-medium"
                      title={`Concorreu em ${c.candidacy_count} eleições — clique para ver a trajetória`}
                    >
                      {c.candidacy_count} candidaturas
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
          )}

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
      <div className="absolute top-3 right-3 flex items-center gap-2 z-10">
        <FavoriteStar
          fav={{
            kind: "candidate",
            id: candidate.id,
            label: candidate.urn_name,
            sub: `${candidate.party.abbreviation} · ${candidate.office_name} · ${candidate.state}`,
            partyNumber: candidate.party.number,
            state: candidate.state,
          }}
        />
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground p-1"
          aria-label="Fechar"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

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
        <Link
          href={`/dashboard/analises/candidato/${candidate.id}`}
          className="mt-3 inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
        >
          Abrir página completa →
        </Link>
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

      {/* Patrimonio + redes + financas vem do /results (details) */}
      <CandidateProfile
        assetsTotal={details?.candidate.assets_total ?? null}
        socialLinks={details?.candidate.social_links ?? null}
        revenueTotal={details?.candidate.revenue_total ?? null}
        expenseTotal={details?.candidate.expense_total ?? null}
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
