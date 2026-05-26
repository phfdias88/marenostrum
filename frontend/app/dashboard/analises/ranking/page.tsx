"use client";

/**
 * Ranking nacional — candidatos mais votados (por ano/cargo/UF).
 * Usa /tse/stats/top-candidates (ordena por total_votes pré-computado).
 */
import { ArrowLeft, Loader2, Trophy } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { TseTopCandidatesResponse } from "@/lib/types";
import { TSE_STATES } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { StateFlag } from "@/components/tse/StateFlag";

const numberFmt = new Intl.NumberFormat("pt-BR");

const OFFICES_BY_YEAR: Record<string, { value: string; label: string }[]> = {
  "2024": [
    { value: "13", label: "Vereador" },
    { value: "11", label: "Prefeito" },
  ],
  "2022": [
    { value: "6", label: "Deputado Federal" },
    { value: "7", label: "Deputado Estadual" },
    { value: "5", label: "Senador" },
    { value: "3", label: "Governador" },
    { value: "1", label: "Presidente" },
  ],
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
        <div>
          <h1 className="text-2xl font-bold">Ranking nacional</h1>
          <p className="text-sm text-muted-foreground">
            Os 50 candidatos mais votados por cargo.
          </p>
        </div>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-12 gap-3 mb-5">
        <Select
          label="Ano"
          value={year}
          onChange={(v) => {
            setYear(v);
            setOffice(OFFICES_BY_YEAR[v][0].value);
          }}
          options={[
            { value: "2024", label: "2024" },
            { value: "2022", label: "2022" },
          ]}
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
            { value: "", label: "Brasil" },
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
        <div className="py-16 text-center">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-10">
          Sem dados para esse filtro.
        </p>
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
        Fonte: TSE · votos nominais somados
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
