"use client";

/**
 * Página dedicada do partido — /dashboard/analises/partido/{number}.
 * URL compartilhável: logo, nome, desempenho (eleitos/votos/candidatos) por
 * ano+cargo, ranking nacional do partido e top candidatos do partido.
 */
import { ArrowLeft, SearchX, Users } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import type {
  TseParty,
  TsePartyPerformanceResponse,
  TseTopCandidatesResponse,
} from "@/lib/types";
import { TSE_STATES } from "@/lib/types";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { StateFlag } from "@/components/tse/StateFlag";
import { FavoriteStar } from "@/components/tse/FavoriteStar";
import { ExportShare } from "@/components/tse/ExportShare";
import { CandidateListSkeleton } from "@/components/tse/Skeletons";
import { EmptyState } from "@/components/tse/EmptyState";

const numberFmt = new Intl.NumberFormat("pt-BR");

const OFFICES_BY_YEAR: Record<string, { value: string; label: string }[]> = {
  "2024": [
    { value: "11", label: "Prefeito" },
    { value: "13", label: "Vereador" },
  ],
  "2022": [
    { value: "3", label: "Governador" },
    { value: "5", label: "Senador" },
    { value: "6", label: "Deputado Federal" },
    { value: "7", label: "Deputado Estadual" },
    { value: "1", label: "Presidente" },
  ],
};

export default function PartyDetailPage() {
  const params = useParams<{ number: string }>();
  const num = Number(params.number);

  const [party, setParty] = useState<TseParty | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [year, setYear] = useState("2024");
  const [office, setOffice] = useState("11");
  const [state, setState] = useState("");

  const [perf, setPerf] = useState<TsePartyPerformanceResponse | null>(null);
  const [perfLoading, setPerfLoading] = useState(true);
  const [top, setTop] = useState<TseTopCandidatesResponse | null>(null);
  const [topLoading, setTopLoading] = useState(true);

  const cardRef = useRef<HTMLDivElement>(null);

  // Acha o partido pelo número
  useEffect(() => {
    let cancelled = false;
    setParty(null);
    setNotFound(false);
    api<TseParty[]>("/v1/tse/parties")
      .then((list) => {
        if (cancelled) return;
        const p = list.find((x) => x.number === num) ?? null;
        setParty(p);
        if (!p) setNotFound(true);
      })
      .catch(() => { if (!cancelled) setNotFound(true); });
    return () => { cancelled = true; };
  }, [num]);

  // Desempenho do partido (ano + cargo + UF)
  useEffect(() => {
    let cancelled = false;
    setPerfLoading(true);
    const p = new URLSearchParams({ year, office_code: office });
    if (state) p.set("state", state);
    api<TsePartyPerformanceResponse>(`/v1/tse/stats/party-performance?${p.toString()}`)
      .then((d) => { if (!cancelled) setPerf(d); })
      .catch(() => { if (!cancelled) setPerf(null); })
      .finally(() => { if (!cancelled) setPerfLoading(false); });
    return () => { cancelled = true; };
  }, [year, office, state]);

  // Top candidatos do partido
  useEffect(() => {
    let cancelled = false;
    setTopLoading(true);
    setTop(null);
    const p = new URLSearchParams({
      year,
      office_code: office,
      party_number: String(num),
      limit: "20",
    });
    if (state) p.set("state", state);
    api<TseTopCandidatesResponse>(`/v1/tse/stats/top-candidates?${p.toString()}`)
      .then((d) => { if (!cancelled) setTop(d); })
      .catch(() => { if (!cancelled) setTop(null); })
      .finally(() => { if (!cancelled) setTopLoading(false); });
    return () => { cancelled = true; };
  }, [num, year, office, state]);

  // Stats deste partido + ranking nacional
  const { mine, rank } = useMemo(() => {
    const ranked = (perf?.items ?? [])
      .filter((i) => i.elected_count > 0 || i.total_votes > 0)
      .sort((a, b) => b.elected_count - a.elected_count || b.total_votes - a.total_votes);
    const idx = ranked.findIndex((i) => i.party.number === num);
    return { mine: idx >= 0 ? ranked[idx] : null, rank: idx >= 0 ? idx + 1 : null };
  }, [perf, num]);

  const maxVotes = top?.items[0]?.total_votes ?? 1;

  if (notFound) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-16">
        <EmptyState icon={SearchX} title="Partido não encontrado" />
        <div className="text-center">
          <Link href="/dashboard/analises/partidos" className="text-primary hover:underline text-sm">
            ← Voltar aos partidos
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-4">
        <Link
          href="/dashboard/analises/partidos"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Partidos
        </Link>
        {party && (
          <div className="flex items-center gap-3" data-html2canvas-ignore>
            <FavoriteStar
              fav={{
                kind: "party",
                id: String(party.number),
                label: party.abbreviation,
                sub: party.name,
                partyNumber: party.number,
              }}
              size={20}
            />
            <ExportShare targetRef={cardRef} filename={`partido-${party.abbreviation}`.toLowerCase()} />
          </div>
        )}
      </div>

      <div ref={cardRef} className="bg-background rounded-xl">
        {/* Hero */}
        <div className="rounded-xl border bg-card p-6 flex items-center gap-5">
          <PartyLogo
            number={num}
            abbreviation={party?.abbreviation ?? "?"}
            size="lg"
          />
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Partido nº {num}
            </p>
            <h1 className="text-2xl font-bold">{party?.abbreviation ?? "…"}</h1>
            <p className="text-sm text-muted-foreground">{party?.name ?? ""}</p>
          </div>
        </div>

        {/* Filtros */}
        <section className="grid grid-cols-2 md:grid-cols-12 gap-3 mt-4" data-html2canvas-ignore>
          <Select
            label="Ano"
            value={year}
            onChange={(v) => {
              setYear(v);
              setOffice(OFFICES_BY_YEAR[v][0].value);
            }}
            options={[
              { value: "2024", label: "2024 (Municipal)" },
              { value: "2022", label: "2022 (Federal/Estadual)" },
            ]}
            className="md:col-span-4"
          />
          <Select
            label="Cargo"
            value={office}
            onChange={setOffice}
            options={OFFICES_BY_YEAR[year]}
            className="md:col-span-5"
          />
          <Select
            label="UF"
            value={state}
            onChange={setState}
            options={[
              { value: "", label: "Brasil" },
              ...TSE_STATES.map((s) => ({ value: s, label: s })),
            ]}
            className="md:col-span-3"
          />
        </section>

        {/* Stats do partido */}
        <div className="grid grid-cols-3 gap-3 mt-4">
          <Stat
            label="Eleitos"
            value={perfLoading ? null : mine?.elected_count ?? 0}
            accent="text-primary"
          />
          <Stat
            label="Votos nominais"
            value={perfLoading ? null : mine?.total_votes ?? 0}
          />
          <Stat
            label="Candidatos"
            value={perfLoading ? null : mine?.candidates_count ?? 0}
          />
        </div>
        {!perfLoading && rank && (
          <p className="text-xs text-muted-foreground mt-2">
            🏆 {rank}º partido em eleitos no Brasil para esse cargo/ano.
          </p>
        )}

        {/* Top candidatos */}
        <div className="mt-6">
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5" /> Candidatos mais votados do partido
          </p>
          {topLoading ? (
            <CandidateListSkeleton rows={6} />
          ) : !top || top.items.length === 0 ? (
            <div className="rounded-lg border bg-card">
              <EmptyState
                icon={SearchX}
                title="Sem candidatos com votos para esse filtro"
                hint="Tente outro ano, cargo ou UF."
              />
            </div>
          ) : (
            <ol className="rounded-lg border bg-card divide-y divide-border">
              {top.items.map((r, i) => (
                <li key={r.candidate.id}>
                  <Link
                    href={`/dashboard/analises/candidato/${r.candidate.id}`}
                    className="p-3 flex items-center gap-3 hover:bg-accent/50 transition-colors"
                  >
                    <span className="w-6 text-center font-bold text-muted-foreground">
                      {i + 1}
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
                      <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                        <StateFlag uf={r.candidate.state} size="sm" />
                        {r.candidate.office_name} · {r.candidate.number}
                      </p>
                      <div className="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full bg-primary"
                          style={{ width: `${(r.total_votes / maxVotes) * 100}%` }}
                        />
                      </div>
                    </div>
                    <span className="font-mono font-bold tabular-nums shrink-0">
                      {numberFmt.format(r.total_votes)}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | null;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border bg-card/60 p-4 text-center">
      {value === null ? (
        <div className="h-8 w-16 mx-auto rounded bg-muted animate-pulse" />
      ) : (
        <p className={`text-2xl font-bold ${accent ?? ""}`}>
          {numberFmt.format(value)}
        </p>
      )}
      <p className="text-xs text-muted-foreground mt-1">{label}</p>
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
