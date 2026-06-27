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
  TsePartyEvolution,
  TsePartyMembership,
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

const _MUNI = [
  { value: "11", label: "Prefeito" },
  { value: "13", label: "Vereador" },
];
const _FED = [
  { value: "3", label: "Governador" },
  { value: "5", label: "Senador" },
  { value: "6", label: "Deputado Federal" },
  { value: "7", label: "Deputado Estadual" },
  { value: "1", label: "Presidente" },
];
const OFFICES_BY_YEAR: Record<string, { value: string; label: string }[]> = {
  "2024": _MUNI,
  "2022": _FED,
  "2020": _MUNI,
  "2018": _FED,
  "2016": _MUNI,
  "2014": _FED,
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
  const [evolution, setEvolution] = useState<TsePartyEvolution | null>(null);
  const [membership, setMembership] = useState<TsePartyMembership | null>(null);

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

  // Evolução do partido ao longo das eleições (não depende dos filtros)
  useEffect(() => {
    let cancelled = false;
    setEvolution(null);
    api<TsePartyEvolution>(`/v1/tse/parties/${num}/evolution`)
      .then((d) => { if (!cancelled) setEvolution(d); })
      .catch(() => { if (!cancelled) setEvolution(null); });
    return () => { cancelled = true; };
  }, [num]);

  // Filiados do partido (snapshot mensal). Filtra pela UF selecionada.
  useEffect(() => {
    let cancelled = false;
    setMembership(null);
    const p = new URLSearchParams();
    if (state) p.set("uf", state);
    const qs = p.toString();
    api<TsePartyMembership>(`/v1/tse/parties/${num}/membership${qs ? `?${qs}` : ""}`)
      .then((d) => { if (!cancelled) setMembership(d); })
      .catch(() => { if (!cancelled) setMembership(null); });
    return () => { cancelled = true; };
  }, [num, state]);

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
            options={Object.keys(OFFICES_BY_YEAR).map((y) => ({
              value: y,
              label: `${y} (${["2024", "2020", "2016"].includes(y) ? "Municipal" : "Federal/Estadual"})`,
            }))}
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

        {/* Evolução do partido ao longo das eleições */}
        {evolution && evolution.items.length > 1 && (
          <PartyEvolution evolution={evolution} />
        )}

        {/* Filiados do partido (TSE perfil_filiacao_partidaria) */}
        {membership && membership.total_filiados > 0 && (
          <div className="mt-6">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" /> Filiados{state ? ` em ${state}` : " no Brasil"} ·{" "}
              <strong className="text-foreground font-mono">{numberFmt.format(membership.total_filiados)}</strong>
            </p>
            <div className="rounded-lg border bg-card p-4 space-y-2">
              {membership.municipios.slice(0, 10).map((m) => {
                const max = membership.municipios[0]?.filiados ?? 1;
                return (
                  <div key={`${m.uf}-${m.municipio}`}>
                    <div className="flex items-center justify-between gap-2 text-sm mb-0.5">
                      <span className="truncate">{m.municipio} <span className="text-muted-foreground text-xs">{m.uf}</span></span>
                      <span className="font-mono tabular-nums">{numberFmt.format(m.filiados)}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div className="h-full bg-primary rounded-full" style={{ width: `${(m.filiados / max) * 100}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
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

// ------------------------------------------------------- evolução do partido

function PartyEvolution({ evolution }: { evolution: TsePartyEvolution }) {
  const fmt = new Intl.NumberFormat("pt-BR");
  const maxElected = Math.max(1, ...evolution.items.map((i) => i.elected_count));
  const isMuni = (y: number) => [2024, 2020, 2016].includes(y);
  const first = evolution.items[0];
  const last = evolution.items[evolution.items.length - 1];

  // Tendência HONESTA: compara a última eleição com a anterior do MESMO tipo
  // (municipal×municipal ou geral×geral) — senão 2014 federal vs 2024
  // municipal daria número sem sentido.
  const sameType = evolution.items.filter((i) => isMuni(i.year) === isMuni(last.year));
  const prevSame = sameType.length >= 2 ? sameType[sameType.length - 2] : null;
  const delta = prevSame ? last.elected_count - prevSame.elected_count : 0;
  const tipo = isMuni(last.year) ? "municipais" : "gerais";

  return (
    <div className="mt-6">
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
        Evolução do partido · {first.year}–{last.year}
      </p>
      <div className="rounded-lg border bg-card p-4 space-y-2.5">
        {evolution.items.map((it) => {
          const pct = (it.elected_count / maxElected) * 100;
          const muni = [2024, 2020, 2016].includes(it.year);
          return (
            <div key={it.year}>
              <div className="flex items-center justify-between gap-2 text-sm mb-0.5">
                <span className="flex items-center gap-2">
                  <span className="font-bold tabular-nums text-primary w-12">{it.year}</span>
                  <span className="text-[10px] text-muted-foreground uppercase">
                    {muni ? "Municipal" : "Geral"}
                  </span>
                </span>
                <span className="text-sm">
                  <strong className="font-mono tabular-nums">{fmt.format(it.elected_count)}</strong>{" "}
                  <span className="text-muted-foreground text-xs">eleitos</span>
                  <span className="text-muted-foreground text-xs">
                    {" "}· {fmt.format(it.candidates_count)} cand.
                  </span>
                </span>
              </div>
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
        {prevSame && (
          <p className="text-xs text-muted-foreground pt-1">
            {delta > 0 ? (
              <span className="text-emerald-600">
                ▲ Cresceu {fmt.format(delta)} eleitos nas eleições {tipo} ({prevSame.year}→{last.year}).
              </span>
            ) : delta < 0 ? (
              <span className="text-rose-500">
                ▼ Caiu {fmt.format(Math.abs(delta))} eleitos nas eleições {tipo} ({prevSame.year}→{last.year}).
              </span>
            ) : (
              <span>Estável nas eleições {tipo} ({prevSame.year}→{last.year}).</span>
            )}
          </p>
        )}
      </div>
    </div>
  );
}
