"use client";

/**
 * Análise de Eleição (estilo Politique).
 *
 * Fluxo:
 *  1. Seleciona UF + Município (busca) + Cargo
 *  2. Mostra ranking de candidatos com votos, %, e status (ELEITO/etc)
 *
 * Reusa GET /tse/municipalities (busca) + /municipalities/{id}/top-candidates
 * (que agora retorna total_votes pra calcular %).
 */
import { ArrowLeft, Loader2, Search, Vote, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

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

const numberFmt = new Intl.NumberFormat("pt-BR");
const pctFmt = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

// Cargos disponiveis por ano (2024 = municipal; 2022 = federal/estadual)
const OFFICES_BY_YEAR: Record<string, { value: string; label: string }[]> = {
  "2024": [
    { value: "11", label: "Prefeito" },
    { value: "13", label: "Vereador" },
  ],
  "2022": [
    { value: "1", label: "Presidente" },
    { value: "3", label: "Governador" },
    { value: "5", label: "Senador" },
    { value: "6", label: "Deputado Federal" },
    { value: "7", label: "Deputado Estadual" },
    { value: "8", label: "Deputado Distrital" },
  ],
};
const YEAR_OPTIONS = [
  { value: "2024", label: "2024 (Municipal)" },
  { value: "2022", label: "2022 (Federal/Estadual)" },
];

export default function EleicaoAnalysisPage() {
  const [year, setYear] = useState("2024");
  const [state, setState] = useState("MG");
  const [office, setOffice] = useState("11");
  const [muniSearch, setMuniSearch] = useState("");
  const debounced = useDebounce(muniSearch, 300);

  const officeOptions = OFFICES_BY_YEAR[year];

  const [munis, setMunis] = useState<TseMunicipality[]>([]);
  const [muniLoading, setMuniLoading] = useState(false);
  const [selectedMuni, setSelectedMuni] = useState<TseMunicipality | null>(null);

  const [results, setResults] = useState<TseMunicipalityResults | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);

  // Busca municipios conforme digita (so quando ainda nao selecionou)
  useEffect(() => {
    if (selectedMuni) return;
    const q = debounced.trim();
    if (q.length < 2) {
      setMunis([]);
      return;
    }
    setMuniLoading(true);
    const params = new URLSearchParams({ limit: "30", search: q });
    if (state) params.set("state", state);
    api<Page<TseMunicipality>>(`/v1/tse/municipalities?${params.toString()}`)
      .then((p) => setMunis(p.items))
      .catch(() => setMunis([]))
      .finally(() => setMuniLoading(false));
  }, [debounced, state, selectedMuni]);

  // Carrega resultados quando muni + cargo selecionados
  useEffect(() => {
    if (!selectedMuni) {
      setResults(null);
      return;
    }
    setResultsLoading(true);
    const params = new URLSearchParams({ limit: "500", year });
    if (office) params.set("office_code", office);
    api<TseMunicipalityResults>(
      `/v1/tse/municipalities/${selectedMuni.id}/top-candidates?${params.toString()}`,
    )
      .then(setResults)
      .catch(() => setResults(null))
      .finally(() => setResultsLoading(false));
  }, [selectedMuni, office, year]);

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-6 flex items-center gap-3">
        <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
          <Vote className="w-5 h-5" />
        </span>
        <div>
          <h1 className="text-2xl font-bold">Análise de Eleição</h1>
          <p className="text-sm text-muted-foreground">
            Resultado por cidade e cargo — 2024 (municipal) e 2022 (federal/estadual).
          </p>
        </div>
      </header>

      {/* Seletores */}
      <section className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-6">
        <Select
          label="Ano"
          value={year}
          onChange={(v) => {
            setYear(v);
            // Reseta cargo pro primeiro do ano escolhido
            setOffice(OFFICES_BY_YEAR[v][0].value);
            setSelectedMuni(null);
            setMuniSearch("");
          }}
          options={YEAR_OPTIONS}
          className="md:col-span-3"
        />
        <Select
          label="UF"
          value={state}
          onChange={(v) => {
            setState(v);
            setSelectedMuni(null);
            setMuniSearch("");
          }}
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
          options={officeOptions}
          className="md:col-span-3"
        />
        <div className="md:col-span-4">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">
            Município
          </label>
          {selectedMuni ? (
            <div className="mt-1 flex items-center justify-between gap-2 py-2 px-3 rounded-md bg-card border border-primary/40">
              <span className="font-semibold">
                {selectedMuni.name}{" "}
                <span className="text-muted-foreground font-normal">
                  /{selectedMuni.state}
                </span>
              </span>
              <button
                onClick={() => {
                  setSelectedMuni(null);
                  setMuniSearch("");
                  setResults(null);
                }}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Trocar município"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="relative mt-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={muniSearch}
                onChange={(e) => setMuniSearch(e.target.value)}
                placeholder="Buscar município…"
                className="w-full pl-9 py-2 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          )}
        </div>
      </section>

      {/* Dropdown de municípios */}
      {!selectedMuni && (muniLoading || munis.length > 0) && (
        <div className="rounded-lg border bg-card divide-y divide-border mb-6 max-h-72 overflow-auto">
          {muniLoading && (
            <div className="p-4 text-center text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
              buscando…
            </div>
          )}
          {munis.map((m) => (
            <button
              key={m.id}
              onClick={() => {
                setSelectedMuni(m);
                setMunis([]);
              }}
              className="w-full text-left p-3 hover:bg-accent/50 transition-colors flex items-center justify-between"
            >
              <span className="font-medium flex items-center gap-2">
                <StateFlag uf={m.state} size="sm" />
                {m.name}
              </span>
              <span className="text-xs text-muted-foreground">{m.state}</span>
            </button>
          ))}
        </div>
      )}

      {!selectedMuni && muniSearch.trim().length < 2 && (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
          <Search className="mx-auto h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground mt-3">
            Aqui você busca uma <strong>cidade</strong> e vê o resultado dela.
            Ex: digite <span className="text-foreground">São Paulo</span>,{" "}
            <span className="text-foreground">Juiz de Fora</span>…
          </p>
          <p className="text-xs text-muted-foreground mt-2">
            Procurando um candidato pelo nome? Use{" "}
            <Link
              href="/dashboard/analises/candidato"
              className="text-primary hover:underline"
            >
              Análise de Candidato
            </Link>
            .
          </p>
        </div>
      )}

      {/* Busca de cidade sem resultado */}
      {!selectedMuni &&
        !muniLoading &&
        muniSearch.trim().length >= 2 &&
        munis.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-8 text-center bg-card/40">
            <p className="text-sm text-foreground font-medium">
              Nenhuma cidade chamada “{muniSearch}”.
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              Esse campo busca <strong>cidades</strong>, não candidatos. Pra
              ver um candidato específico (ex: Bolsonaro, Lula), use{" "}
              <Link
                href="/dashboard/analises/candidato"
                className="text-primary hover:underline"
              >
                Análise de Candidato
              </Link>
              .
            </p>
          </div>
        )}

      {/* Resultados */}
      {selectedMuni && (
        <ResultsPanel
          muni={selectedMuni}
          office={office}
          year={year}
          results={results}
          loading={resultsLoading}
        />
      )}

      <footer className="text-xs text-muted-foreground text-center pt-6">
        Fonte: Tribunal Superior Eleitoral (TSE)
      </footer>
    </div>
  );
}

// ----------------------------------------------------------------- results

function ResultsPanel({
  muni,
  office,
  year,
  results,
  loading,
}: {
  muni: TseMunicipality;
  office: string;
  year: string;
  results: TseMunicipalityResults | null;
  loading: boolean;
}) {
  // Procura o label do cargo em qualquer ano (flat lookup)
  const officeName =
    results?.office_name ??
    Object.values(OFFICES_BY_YEAR)
      .flat()
      .find((o) => o.value === office)?.label ??
    "";

  if (loading) {
    return (
      <div className="py-16 text-center">
        <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
      </div>
    );
  }
  if (!results || results.results.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
        <p className="text-sm text-muted-foreground">
          Sem resultados pra {officeName} em {muni.name}.
        </p>
      </div>
    );
  }

  const total = results.total_votes || 1;

  return (
    <div>
      {/* Header resultado */}
      <div className="rounded-xl border bg-card p-4 mb-4 flex items-center gap-4">
        <StateFlag uf={muni.state} size="lg" className="!w-14 !h-10 shadow shrink-0" />
        <div>
          <p className="text-xs uppercase tracking-wider text-primary font-semibold flex items-center gap-2">
            <Vote className="w-4 h-4" /> Resultado da eleição
          </p>
          <h2 className="text-lg font-bold mt-1">
            {year === "2022"
              ? "Eleições Gerais 2022"
              : "Eleições Municipais 2024"}
          </h2>
          <p className="text-sm text-muted-foreground">
            {officeName} · {muni.name}/{muni.state}
          </p>
        </div>
      </div>

      {/* Stats: total de votos válidos (nominais) */}
      <div className="grid grid-cols-2 gap-3 mb-5">
        <div className="rounded-lg border bg-card/60 px-4 py-3">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            Votos nominais
          </p>
          <p className="text-2xl font-bold mt-0.5 text-primary">
            {numberFmt.format(results.total_votes)}
          </p>
        </div>
        <div className="rounded-lg border bg-card/60 px-4 py-3">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            Candidatos
          </p>
          <p className="text-2xl font-bold mt-0.5">
            {numberFmt.format(results.total_results)}
          </p>
        </div>
      </div>

      {/* Ranking */}
      <div className="rounded-lg border bg-card divide-y divide-border">
        <div className="flex items-center gap-3 px-4 py-2 text-xs uppercase tracking-wider text-muted-foreground">
          <span className="w-8">#</span>
          <span className="flex-1">Classificação</span>
          <span className="w-20 text-right">Votos</span>
          <span className="w-14 text-right">%</span>
        </div>
        {results.results.map((r, i) => {
          const pct = (r.votes / total) * 100;
          return (
            <div
              key={r.candidate.id}
              className="flex items-center gap-3 px-4 py-2.5"
            >
              <span className="w-8 font-bold text-primary tabular-nums">
                {i + 1}º
              </span>
              <CandidatePhoto
                candidateId={r.candidate.id}
                name={r.candidate.urn_name}
                partyNumber={r.candidate.party.number}
                size="sm"
              />
              <div className="flex-1 min-w-0">
                <p className="font-semibold truncate flex items-center gap-2">
                  <span className="truncate">{r.candidate.urn_name}</span>
                  <ResultBadge status={r.candidate.result_status} size="sm" />
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {r.candidate.party.abbreviation} · {r.candidate.number}
                </p>
              </div>
              <span className="w-20 text-right font-mono font-bold tabular-nums">
                {numberFmt.format(r.votes)}
              </span>
              <span className="w-14 text-right text-sm text-muted-foreground tabular-nums">
                {pctFmt.format(pct)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- select

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
