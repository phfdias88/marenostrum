"use client";

/**
 * Analise por Eleicao.
 * - Lista das eleicoes importadas (ordinaria 2024, 2o turno, suplementares)
 * - Clique em uma -> stats agregados + drill pra busca de candidatos
 */
import { ArrowLeft, FileBarChart, Loader2, Vote } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type {
  Page,
  TseCandidate,
  TseElection,
  TseElectionStats,
} from "@/lib/types";

const numberFmt = new Intl.NumberFormat("pt-BR");

export default function EleicoesAnalysisPage() {
  const [elections, setElections] = useState<TseElection[] | null>(null);
  const [selected, setSelected] = useState<TseElection | null>(null);

  useEffect(() => {
    api<TseElection[]>("/v1/tse/elections")
      .then((arr) => {
        // Ordena: principais (com mais texto) primeiro, depois suplementares
        arr.sort((a, b) => {
          if (a.year !== b.year) return b.year - a.year;
          if (a.round !== b.round) return a.round - b.round;
          // Eleicao ordinaria antes de suplementar
          const isOrd = (e: TseElection) =>
            (e.type_name ?? "").toLowerCase().includes("ordin");
          if (isOrd(a) && !isOrd(b)) return -1;
          if (!isOrd(a) && isOrd(b)) return 1;
          return a.name.localeCompare(b.name);
        });
        setElections(arr);
      })
      .catch(() => setElections([]));
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-bold">Análise por Eleição</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {elections === null
            ? "Carregando…"
            : `${elections.length} eleição(ões) importada(s) do TSE.`}
        </p>
      </header>

      {selected ? (
        <ElectionDrill election={selected} onBack={() => setSelected(null)} />
      ) : elections === null ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-20 rounded-lg border bg-card/60 animate-pulse"
            />
          ))}
        </div>
      ) : (
        <ul className="rounded-lg border bg-card divide-y divide-border">
          {elections.map((e) => {
            const isOrd = (e.type_name ?? "").toLowerCase().includes("ordin");
            return (
              <button
                key={e.id}
                onClick={() => setSelected(e)}
                className="w-full text-left p-4 hover:bg-accent/50 transition-colors flex items-center gap-4"
              >
                <span
                  className={`grid place-items-center w-10 h-10 rounded-md shrink-0 ${
                    isOrd
                      ? "bg-primary/20 text-primary"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  <Vote className="w-5 h-5" />
                </span>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{e.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {e.year} · {e.round}º turno · cod TSE {e.tse_code} ·{" "}
                    {e.type_name}
                  </p>
                </div>
              </button>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// -------------------------------------------------------------- drill

function ElectionDrill({
  election,
  onBack,
}: {
  election: TseElection;
  onBack: () => void;
}) {
  const [stats, setStats] = useState<TseElectionStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  const [topCandidates, setTopCandidates] = useState<TseCandidate[]>([]);
  const [topLoading, setTopLoading] = useState(true);

  useEffect(() => {
    setStatsLoading(true);
    api<TseElectionStats>(`/v1/tse/elections/${election.id}/stats`)
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));

    setTopLoading(true);
    api<Page<TseCandidate>>(
      `/v1/tse/candidates?election_id=${election.id}&limit=20`,
    )
      .then((p) => setTopCandidates(p.items))
      .catch(() => setTopCandidates([]))
      .finally(() => setTopLoading(false));
  }, [election.id]);

  return (
    <div>
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Todas as eleições
      </button>

      <div className="flex items-start gap-4 mb-6">
        <span className="grid place-items-center w-16 h-16 rounded-lg bg-primary/15 text-primary">
          <FileBarChart className="w-7 h-7" />
        </span>
        <div>
          <h2 className="text-2xl font-bold">{election.name}</h2>
          <p className="text-sm text-muted-foreground">
            {election.year} · {election.round}º turno · {election.type_name}
          </p>
        </div>
      </div>

      {/* Stats cards */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-8">
        {statsLoading ? (
          <>
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-24 rounded-lg border bg-card/60 animate-pulse"
              />
            ))}
          </>
        ) : !stats ? (
          <p className="col-span-3 text-sm text-muted-foreground">
            Erro ao carregar sumário.
          </p>
        ) : (
          <>
            <Stat label="Candidatos" value={stats.candidates_count} />
            <Stat
              label="Municípios"
              value={stats.municipalities_count}
              hint="com votos apurados"
            />
            <Stat
              label="Total de votos"
              value={stats.total_votes}
              hint="soma de todos os candidatos"
            />
          </>
        )}
      </section>

      {/* Lista candidatos (preview) */}
      <h3 className="text-sm uppercase tracking-wider text-muted-foreground mb-2">
        Candidatos dessa eleição (primeiros 20)
      </h3>
      <div className="rounded-lg border bg-card divide-y divide-border">
        {topLoading ? (
          <div className="p-10 text-center">
            <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
          </div>
        ) : topCandidates.length === 0 ? (
          <p className="p-10 text-center text-sm text-muted-foreground">
            Sem candidatos.
          </p>
        ) : (
          topCandidates.map((c) => (
            <div key={c.id} className="p-3 flex items-center gap-3">
              <span className="grid place-items-center w-9 h-9 rounded-md bg-primary/10 text-primary font-bold text-sm shrink-0">
                {c.number}
              </span>
              <div className="flex-1 min-w-0">
                <p className="font-semibold truncate">{c.urn_name}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {c.party.abbreviation} · {c.office_name} · {c.state}
                </p>
              </div>
            </div>
          ))
        )}
      </div>

      <p className="text-xs text-muted-foreground mt-3 text-center">
        Use{" "}
        <Link
          href="/dashboard/analises/candidato"
          className="text-primary hover:underline"
        >
          Análise de Candidato
        </Link>{" "}
        pra busca avançada.
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border bg-card/60 px-4 py-3">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="text-3xl font-bold mt-1 text-primary">
        {numberFmt.format(value)}
      </p>
      {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
    </div>
  );
}
