"use client";

/**
 * Ranking nacional — candidatos mais votados (por ano/cargo/UF).
 * Usa /tse/stats/top-candidates (ordena por total_votes pré-computado).
 */
import { ArrowLeft, Download, SearchX, Trophy } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { downloadCsv } from "@/lib/csv";
import type { TseTopCandidatesResponse } from "@/lib/types";
import { TSE_STATES } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { StateFlag } from "@/components/tse/StateFlag";
import { CandidateListSkeleton } from "@/components/tse/Skeletons";
import { EmptyState } from "@/components/tse/EmptyState";
import { YEAR_OPTIONS, VOTOS_NOMINAIS_HINT } from "@/lib/elections";

const numberFmt = new Intl.NumberFormat("pt-BR");

// Ranking usa ordem propria (vereador/dep primeiro = mais disputado) +
// inclui Presidente nos anos gerais. Cargos: 13=ver, 11=pref, 6=depfed,
// 7=depest, 5=sen, 3=gov, 1=pres.
const MUNI = [
  { value: "13", label: "Vereador" },
  { value: "11", label: "Prefeito" },
];
const FED = [
  { value: "6", label: "Deputado Federal" },
  { value: "7", label: "Deputado Estadual" },
  { value: "5", label: "Senador" },
  { value: "3", label: "Governador" },
  { value: "1", label: "Presidente" },
];
const OFFICES_BY_YEAR: Record<string, { value: string; label: string }[]> = {
  "2024": MUNI,
  "2022": FED,
  "2020": MUNI,
  "2018": FED,
  "2016": MUNI,
  "2014": FED,
};

export default function RankingPage() {
  const [year, setYear] = useState("2024");
  const [office, setOffice] = useState("13");
  const [state, setState] = useState("");
  const [electedOnly, setElectedOnly] = useState(false);
  const [data, setData] = useState<TseTopCandidatesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams({ year, office_code: office, limit: "50" });
    if (state) p.set("state", state);
    if (electedOnly) p.set("elected_only", "true");
    api<TseTopCandidatesResponse>(`/v1/tse/stats/top-candidates?${p.toString()}`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [year, office, state, electedOnly]);

  const max = Math.max(1, ...(data?.items ?? []).map((i) => i.total_votes));

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
          <Trophy className="w-5 h-5" />
        </span>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">Ranking nacional</h1>
          <p className="text-sm text-muted-foreground">
            Os mais votados — {OFFICES_BY_YEAR[year].find((o) => o.value === office)?.label ?? "todos os cargos"} · {state || "Brasil (todas)"} · {year}
          </p>
        </div>
        <button
          onClick={() => {
            if (!data || data.items.length === 0) return;
            const rows = data.items.map((it, i) => ({
              rank: i + 1,
              urna: it.candidate.urn_name,
              nome: it.candidate.name,
              numero: it.candidate.number,
              partido: it.candidate.party.abbreviation,
              cargo: it.candidate.office_name,
              uf: it.candidate.state,
              votos: it.total_votes,
              situacao: it.candidate.result_status ?? "",
            }));
            downloadCsv(
              `ranking-${year}-${office}-${state || "br"}${electedOnly ? "-eleitos" : ""}`,
              [
                { key: "rank", label: "#" },
                { key: "urna", label: "Nome de urna" },
                { key: "nome", label: "Nome" },
                { key: "numero", label: "Número" },
                { key: "partido", label: "Partido" },
                { key: "cargo", label: "Cargo" },
                { key: "uf", label: "UF" },
                { key: "votos", label: "Votos" },
                { key: "situacao", label: "Situação" },
              ],
              rows,
            );
          }}
          disabled={!data || data.items.length === 0}
          className="inline-flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-md border border-border bg-card text-sm hover:border-primary/60 transition-colors disabled:opacity-50 shrink-0"
          aria-label="Exportar ranking em CSV"
          title="Exportar CSV"
        >
          <Download className="w-4 h-4" />
          <span className="hidden sm:inline">CSV</span>
        </button>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-12 gap-3 mb-5">
        <Select
          label="Ano"
          value={year}
          onChange={(v) => {
            setYear(v);
            setOffice(OFFICES_BY_YEAR[v][0].value);
          }}
          options={YEAR_OPTIONS}
          className="md:col-span-3"
        />
        <Select
          label="Cargo"
          value={office}
          onChange={setOffice}
          options={OFFICES_BY_YEAR[year]}
          className="md:col-span-4"
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
        <div className="md:col-span-3 flex items-end">
          <label className="flex items-center gap-2 text-sm cursor-pointer py-2">
            <input
              type="checkbox"
              checked={electedOnly}
              onChange={(e) => setElectedOnly(e.target.checked)}
              className="accent-primary w-4 h-4"
            />
            Só eleitos
          </label>
        </div>
      </section>

      {loading ? (
        <CandidateListSkeleton rows={8} />
      ) : !data || data.items.length === 0 ? (
        <div className="rounded-lg border bg-card">
          <EmptyState
            icon={SearchX}
            title="Sem dados para esse filtro"
            hint="Tente outro ano, cargo ou UF."
          />
        </div>
      ) : (
        <ol className="rounded-lg border bg-card divide-y divide-border">
          {data.items.map((r, i) => {
            const pct = (r.total_votes / max) * 100;
            const medal = i === 0 ? "text-amber-400" : i === 1 ? "text-slate-300" : i === 2 ? "text-amber-700" : "text-muted-foreground";
            return (
              <li key={r.candidate.id}>
                <Link
                  href={`/dashboard/analises/candidato/${r.candidate.id}`}
                  className="p-3 flex items-center gap-3 hover:bg-accent/50 transition-colors"
                >
                <span className={`w-7 text-center font-bold ${medal}`}>{i + 1}</span>
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
                  <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <StateFlag uf={r.candidate.state} size="sm" />
                    {r.candidate.party.abbreviation} · {r.candidate.number}
                  </p>
                  <div className="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
                  </div>
                </div>
                <span className="font-mono font-bold tabular-nums shrink-0">
                  {numberFmt.format(r.total_votes)}
                </span>
                </Link>
              </li>
            );
          })}
        </ol>
      )}
      <p className="text-xs text-muted-foreground text-center pt-4">
        Fonte: TSE ·{" "}
        <span title={VOTOS_NOMINAIS_HINT}>
          votos nominais
        </span>{" "}
        somados
      </p>
    </div>
  );
}

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
      <label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</label>
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
