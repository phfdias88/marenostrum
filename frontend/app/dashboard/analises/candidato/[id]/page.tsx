"use client";

/**
 * Página dedicada do candidato — /dashboard/analises/candidato/{id}.
 * URL compartilhável com tudo: foto, resultado, perfil (patrimônio/finanças/
 * redes), votos por município, mapa, favoritar, exportar.
 */
import {
  ArrowLeft,
  FileDown,
  Info,
  Loader2,
  Map as MapIcon,
  Shield,
  Sparkles,
  Swords,
  Target,
  TrendingUp,
  Trophy,
  UserX,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type {
  Page,
  TseAiCompare,
  TseAiReport,
  TseCandidate,
  TseCandidateByNeighborhoodResponse,
  TseCandidateResults,
  TseCandidateTrajectory,
  TseCandidateZoneVotes,
  TseElectorateProfile,
  TseOpportunityResponse,
  TsePathToVictory,
} from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { CandidateProfile } from "@/components/tse/CandidateProfile";
import { CandidateMapModal } from "@/components/tse/CandidateMapModal";
import { FavoriteStar } from "@/components/tse/FavoriteStar";
import { ExportShare } from "@/components/tse/ExportShare";
import { CandidateDetailSkeleton } from "@/components/tse/Skeletons";
import { EmptyState } from "@/components/tse/EmptyState";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { VoteBar } from "@/components/ui/VoteBar";
import { PresentButton } from "@/components/ui/PresentButton";

const numberFmt = new Intl.NumberFormat("pt-BR");

export default function CandidateDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [data, setData] = useState<TseCandidateResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [zones, setZones] = useState<TseCandidateZoneVotes | null>(null);
  const [bairros, setBairros] = useState<TseCandidateByNeighborhoodResponse | null>(null);
  const [trajectory, setTrajectory] = useState<TseCandidateTrajectory | null>(null);
  const [opportunities, setOpportunities] = useState<TseOpportunityResponse | null>(null);
  const [profile, setProfile] = useState<TseElectorateProfile | null>(null);
  const [path, setPath] = useState<TsePathToVictory | null>(null);
  // PERF: as seções abaixo da dobra (radar, território, caminho, zona, bairro)
  // só carregam quando o usuário rola ou após um curto fallback — assim o
  // primeiro render dispara só 2 chamadas (resultados + trajetória) em vez de 7.
  const [deferred, setDeferred] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  // Essenciais (acima da dobra) — disparam imediatamente.
  useEffect(() => {
    if (!id) return;
    // Reset imediato — sem isso, ao trocar de candidato A→B, voce ve
    // brevemente os dados de A enquanto B carrega. Pior: race condition
    // se o fetch de A demorar mais que o de B (A sobrescreve B no .then).
    let cancelled = false;
    setLoading(true);
    setError(false);
    setData(null);
    setZones(null);
    setBairros(null);
    setTrajectory(null);
    setOpportunities(null);
    setProfile(null);
    setPath(null);
    setDeferred(false);
    setShowMap(false);

    // Trajetória eleitoral — mesma pessoa em outras eleições (2014–2024)
    api<TseCandidateTrajectory>(`/v1/tse/candidates/${id}/trajectory`)
      .then((d) => { if (!cancelled) setTrajectory(d); })
      .catch(() => { if (!cancelled) setTrajectory(null); });

    api<TseCandidateResults>(`/v1/tse/candidates/${id}/results`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => {
      cancelled = true;
    };
  }, [id]);

  // Dispara o carregamento "deferido" ao rolar OU após 1s (fallback) —
  // garante que as seções carreguem mesmo sem rolar.
  useEffect(() => {
    if (!id) return;
    let done = false;
    const trigger = () => {
      if (done) return;
      done = true;
      setDeferred(true);
      window.removeEventListener("scroll", trigger);
    };
    window.addEventListener("scroll", trigger, { passive: true, once: true });
    const t = setTimeout(trigger, 1000);
    return () => {
      window.removeEventListener("scroll", trigger);
      clearTimeout(t);
    };
  }, [id]);

  // Seções abaixo da dobra — só quando deferido.
  useEffect(() => {
    if (!id || !deferred) return;
    let cancelled = false;
    api<TsePathToVictory>(`/v1/tse/candidates/${id}/path-to-victory`)
      .then((d) => { if (!cancelled) setPath(d); })
      .catch(() => { if (!cancelled) setPath(null); });
    api<TseOpportunityResponse>(`/v1/tse/candidates/${id}/opportunities`)
      .then((d) => { if (!cancelled) setOpportunities(d); })
      .catch(() => { if (!cancelled) setOpportunities(null); });
    api<TseElectorateProfile>(`/v1/tse/candidates/${id}/electorate-profile`)
      .then((d) => { if (!cancelled) setProfile(d); })
      .catch(() => { if (!cancelled) setProfile(null); });
    api<TseCandidateZoneVotes>(`/v1/tse/candidates/${id}/by-zone`)
      .then((d) => { if (!cancelled) setZones(d); })
      .catch(() => { if (!cancelled) setZones(null); });
    api<TseCandidateByNeighborhoodResponse>(
      `/v1/tse/candidates/${id}/by-neighborhood?limit=20`,
    )
      .then((d) => { if (!cancelled) setBairros(d); })
      .catch(() => { if (!cancelled) setBairros(null); });
    return () => {
      cancelled = true;
    };
  }, [id, deferred]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="h-5 w-40 mb-4 rounded bg-muted animate-pulse" />
        <CandidateDetailSkeleton />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-16">
        <EmptyState
          icon={UserX}
          title="Candidato não encontrado"
          hint="O candidato pode não existir ou os dados ainda não foram sincronizados."
        />
        <div className="text-center">
          <Link href="/dashboard/analises/candidato" className="text-primary hover:underline text-sm">
            ← Voltar à busca
          </Link>
        </div>
      </div>
    );
  }

  const c = data.candidate;
  const hasCoords = data.results.some(
    (r) => r.municipality.latitude != null && r.municipality.longitude != null,
  );

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 sm:py-8">
      <div className="flex items-center justify-between gap-2 mb-4 flex-wrap">
        <Link
          href="/dashboard/analises/candidato"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Buscar candidatos
        </Link>
        <div className="flex items-center gap-3" data-html2canvas-ignore>
          <PresentButton />
          <DossierDownload candidateId={c.id} urnName={c.urn_name} />
          <FavoriteStar
            fav={{
              kind: "candidate",
              id: c.id,
              label: c.urn_name,
              sub: `${c.party.abbreviation} · ${c.office_name} · ${c.state}`,
              partyNumber: c.party.number,
              state: c.state,
            }}
            size={20}
          />
          <ExportShare
            targetRef={cardRef}
            filename={`candidato-${c.urn_name}`.toLowerCase().replace(/[^a-z0-9]+/g, "-")}
          />
        </div>
      </div>

      <div ref={cardRef} className="bg-background rounded-xl">
        {/* Hero — mobile: foto menor, layout horizontal compacto */}
        <div className="relative overflow-hidden mn-glass mn-glow rounded-xl p-4 sm:p-6 flex flex-row sm:flex-row items-start gap-4 sm:gap-5">
          <div className="shrink-0">
            <CandidatePhoto
              candidateId={c.id}
              name={c.urn_name}
              partyNumber={c.party.number}
              size="lg"
              className="sm:!w-32 sm:!h-32"
            />
          </div>
          <div className="flex-1 min-w-0 text-left">
            <p className="text-[10px] sm:text-xs uppercase tracking-wider text-muted-foreground">
              {c.office_name} · {c.state} · {c.election.year}
            </p>
            <h1 className="text-lg sm:text-2xl font-bold mt-0.5 leading-tight">{c.urn_name}</h1>
            <p className="text-xs sm:text-sm text-muted-foreground truncate">{c.name}</p>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <ResultBadge status={c.result_status} />
            </div>
            <div className="mt-2 sm:mt-3 flex items-center gap-2">
              <PartyLogo number={c.party.number} abbreviation={c.party.abbreviation} size="sm" />
              <div className="text-left min-w-0">
                <p className="font-semibold text-xs sm:text-sm">
                  {c.party.abbreviation} · {c.number}
                </p>
                <p className="text-[11px] sm:text-xs text-muted-foreground truncate">
                  {c.party.name}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 mt-4">
          <div className="rounded-lg border bg-card/60 p-4 text-center">
            <p className="text-3xl font-bold text-primary tabular-nums">
              <AnimatedNumber value={data.total_votes} />
            </p>
            <p className="text-xs text-muted-foreground">Total de votos</p>
          </div>
          <div className="rounded-lg border bg-card/60 p-4 text-center">
            <p className="text-3xl font-bold tabular-nums">
              <AnimatedNumber value={data.municipalities_with_votes} />
            </p>
            <p className="text-xs text-muted-foreground">Municípios</p>
          </div>
        </div>

        {/* Perfil rico */}
        <div className="mt-4">
          <CandidateProfile
            assetsTotal={c.assets_total}
            socialLinks={c.social_links}
            revenueTotal={c.revenue_total}
            expenseTotal={c.expense_total}
          />
        </div>

        {/* Botao mapa */}
        {hasCoords && (
          <button
            data-html2canvas-ignore
            onClick={() => setShowMap(true)}
            className="mt-4 w-full inline-flex items-center justify-center gap-2 py-2.5 rounded-md border border-border bg-card hover:border-primary/60 transition-colors"
          >
            <MapIcon className="w-4 h-4" /> Ver votos no mapa
          </button>
        )}

        {/* Relatório estratégico por IA — gerado sob demanda (economiza cota) */}
        <AiReportSection candidateId={id} />

        {/* Confronto estratégico com adversário (Maré IA) */}
        <CompareSection candidateId={id} candidateName={c.urn_name} />

        {/* Trajetória eleitoral — só aparece se a pessoa tem 2+ candidaturas */}
        {trajectory && trajectory.items.length > 1 && (
          <TrajectorySection trajectory={trajectory} currentId={id} />
        )}

        {/* Radar de oportunidades — onde crescer vs redutos */}
        {opportunities &&
          (opportunities.opportunities.length > 0 ||
            opportunities.strongholds.length > 0) && (
            <OpportunityRadar data={opportunities} />
          )}

        {/* Caminho da vitória — quantos votos faltam pra vencer */}
        {path && path.scope !== "proporcional" && (
          <PathToVictorySection data={path} />
        )}

        {/* Perfil do território — de que tipo de eleitorado vem o voto */}
        {profile && profile.municipalities_covered > 0 && (
          <ElectorateProfileSection data={profile} />
        )}

        {/* Votos por municipio */}
        <div className="mt-5">
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
            Votos por município
          </p>
          <ul className="rounded-lg border bg-card divide-y divide-border max-h-[50vh] overflow-auto">
            {data.results.slice(0, 100).map((r, i) => {
              const top = data.results[0]?.votes || 1;
              return (
                <li
                  key={r.municipality.id}
                  className="px-4 py-2.5 text-sm"
                >
                  <div className="flex items-center justify-between gap-3">
                    <Link
                      href={`/dashboard/analises/municipio/${r.municipality.id}`}
                      className="truncate hover:text-primary hover:underline"
                      title="Ver análise completa do município"
                    >
                      {r.municipality.name}{" "}
                      <span className="text-muted-foreground">/{r.municipality.state}</span>
                    </Link>
                    <span className="font-mono font-semibold shrink-0 tabular-nums">
                      {numberFmt.format(r.votes)}
                    </span>
                  </div>
                  <div className="mt-1.5">
                    <VoteBar value={r.votes} max={top} rank={i + 1} />
                  </div>
                </li>
              );
            })}
          </ul>
          {data.results.length > 100 && (
            <p className="text-xs text-muted-foreground pt-2">
              + {numberFmt.format(data.results.length - 100)} outro(s) município(s)
            </p>
          )}
        </div>

        {/* Top bairros (so aparece quando ha dados — capitais sincronizadas).
            Vem ANTES de zonas: bairro e' mais granular/util pra estrategia
            de campanha que zona eleitoral. */}
        {bairros && bairros.items.length > 0 && (
          <div className="mt-5 mn-fade-in">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Top 20 bairros com mais votos
            </p>
            <ul className="rounded-lg border bg-card divide-y divide-border max-h-[50vh] overflow-auto">
              {bairros.items.map((b, i) => {
                const top = bairros.items[0]?.votes || 1;
                const pct = (b.votes / top) * 100;
                const penetration = b.electors_total > 0
                  ? (b.votes / b.electors_total) * 100
                  : 0;
                return (
                  <li key={`${b.neighborhood}-${i}`} className="px-4 py-2.5">
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="truncate flex items-center gap-2 min-w-0">
                        <span className="text-primary font-bold text-xs w-6 tabular-nums shrink-0">
                          {i + 1}º
                        </span>
                        <span className="truncate">{b.neighborhood}</span>
                      </span>
                      <span className="font-mono font-semibold shrink-0 tabular-nums">
                        {numberFmt.format(b.votes)}
                      </span>
                    </div>
                    <div className="mt-1 ml-8">
                      <VoteBar value={b.votes} max={top} rank={i + 1} />
                    </div>
                    {b.electors_total > 0 && (
                      <p className="ml-8 mt-1 text-[11px] text-muted-foreground">
                        {b.places_count} {b.places_count === 1 ? "local" : "locais"} ·{" "}
                        {penetration.toFixed(1)}% dos eleitores do bairro
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Votos por zona eleitoral — vem DEPOIS dos bairros */}
        {zones && zones.items.length > 0 && (
          <div className="mt-5 mn-fade-in">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Votos por zona eleitoral
            </p>
            <ul className="rounded-lg border bg-card divide-y divide-border max-h-[50vh] overflow-auto">
              {zones.items.map((z, i) => {
                const max = zones.items[0]?.votes || 1;
                return (
                  <li key={`${z.municipality_name}-${z.zone}-${i}`} className="px-4 py-2.5">
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="truncate">
                        Zona {z.zone}{" "}
                        <span className="text-muted-foreground">
                          · {z.municipality_name}/{z.state}
                        </span>
                      </span>
                      <span className="font-mono font-semibold shrink-0">
                        {numberFmt.format(z.votes)}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full bg-primary"
                        style={{ width: `${(z.votes / max) * 100}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>

      {showMap && (
        <CandidateMapModal results={data} onClose={() => setShowMap(false)} />
      )}
    </div>
  );
}

// ------------------------------------------------ relatório estratégico (IA)

function ScoreRing({ score }: { score: number }) {
  // Cor por faixa de viabilidade
  const color =
    score >= 70 ? "text-emerald-500" : score >= 40 ? "text-amber-500" : "text-rose-500";
  const r = 26;
  const circ = 2 * Math.PI * r;
  const dash = (Math.min(100, Math.max(0, score)) / 100) * circ;
  return (
    <div className="relative w-[68px] h-[68px] shrink-0">
      <svg viewBox="0 0 68 68" className="w-full h-full -rotate-90">
        <circle cx="34" cy="34" r={r} fill="none" strokeWidth="6" className="stroke-muted" />
        <circle
          cx="34"
          cy="34"
          r={r}
          fill="none"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`}
          className={`${color} transition-all duration-700`}
          stroke="currentColor"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={`text-lg font-bold tabular-nums ${color}`}>{score}</span>
      </div>
    </div>
  );
}

function AiBlock({
  title,
  items,
  icon,
  accent,
}: {
  title: string;
  items: string[];
  icon: ReactNode;
  accent: string;
}) {
  if (!items || items.length === 0) return null;
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <p className={`px-3 py-2 text-xs font-semibold border-b border-border flex items-center gap-1.5 ${accent}`}>
        {icon} {title}
      </p>
      <ul className="divide-y divide-border">
        {items.map((it, i) => (
          <li key={i} className="px-3 py-2 text-sm flex gap-2">
            <span className="text-muted-foreground shrink-0">•</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AiReportSection({ candidateId }: { candidateId: string }) {
  const [report, setReport] = useState<TseAiReport | null>(null);
  const [loading, setLoading] = useState(false);

  async function generate() {
    if (loading) return;
    setLoading(true);
    try {
      const d = await api<TseAiReport>(`/v1/tse/candidates/${candidateId}/ai-report`);
      setReport(d);
    } catch (e) {
      const msg =
        e instanceof Error && e.message ? e.message : "Não foi possível gerar o relatório.";
      toast.error(msg.replace(/^http \d+:?\s*/i, "") || "Não foi possível gerar o relatório.");
    } finally {
      setLoading(false);
    }
  }

  if (!report) {
    return (
      <div className="mt-5" data-html2canvas-ignore>
        <button
          onClick={generate}
          disabled={loading}
          className="w-full inline-flex items-center justify-center gap-2 py-3 rounded-lg border border-primary/40 bg-gradient-to-r from-primary/10 to-amber-500/10 hover:border-primary/70 transition-colors disabled:opacity-70 font-medium"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" /> Maré IA analisando os dados…
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4 text-primary" /> Consultar a Maré IA
            </>
          )}
        </button>
        <p className="text-[11px] text-muted-foreground mt-1.5 text-center">
          <span className="font-semibold text-foreground">Maré IA</span> · especialista em vantagem
          eleitoral. Análise sobre os dados reais de votação: diagnóstico, score de viabilidade,
          narrativas e ações prioritárias.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-5 mn-fade-in">
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
        <Sparkles className="w-3.5 h-3.5 text-primary" /> Maré IA · Especialista em Vantagem Eleitoral
      </p>

      {/* Diagnóstico + score */}
      <div className="rounded-lg border bg-card p-4 flex items-center gap-4 mb-3">
        <ScoreRing score={report.score_viabilidade} />
        <div className="min-w-0">
          <p className="text-sm">{report.diagnostico}</p>
          <p className="text-[11px] text-muted-foreground mt-1">
            <span className="font-semibold">Viabilidade {report.score_viabilidade}/100</span> ·{" "}
            {report.score_justificativa}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <AiBlock
          title="Pontos fortes"
          items={report.pontos_fortes}
          icon={<TrendingUp className="w-3.5 h-3.5" />}
          accent="bg-primary/10 text-primary"
        />
        <AiBlock
          title="Onde crescer"
          items={report.onde_crescer}
          icon={<TrendingUp className="w-3.5 h-3.5" />}
          accent="bg-emerald-500/10 text-emerald-700"
        />
        <AiBlock
          title="Narrativas de campanha"
          items={report.narrativas}
          icon={<Sparkles className="w-3.5 h-3.5" />}
          accent="bg-amber-500/10 text-amber-700"
        />
        <AiBlock
          title="Ações prioritárias"
          items={report.acoes_prioritarias}
          icon={<TrendingUp className="w-3.5 h-3.5" />}
          accent="bg-sky-500/10 text-sky-700"
        />
      </div>
      <p className="text-[11px] text-muted-foreground mt-1.5">
        Gerado pela <span className="font-semibold text-foreground">Maré IA</span> a partir dos
        dados reais do TSE. Use como apoio à decisão — valide com sua equipe.
      </p>
    </div>
  );
}

// ------------------------------------------ confronto estratégico (Maré IA)

function CompareSection({
  candidateId,
  candidateName,
}: {
  candidateId: string;
  candidateName: string;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<TseCandidate[]>([]);
  const [adversary, setAdversary] = useState<TseCandidate | null>(null);
  const [report, setReport] = useState<TseAiCompare | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 3) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      api<Page<TseCandidate>>(`/v1/tse/candidates?search=${encodeURIComponent(term)}&limit=8`)
        .then((r) => {
          if (!cancelled) setResults(r.items.filter((c) => c.id !== candidateId));
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [q, candidateId]);

  async function generate(adv: TseCandidate) {
    setAdversary(adv);
    setResults([]);
    setQ("");
    setReport(null);
    setLoading(true);
    try {
      const d = await api<TseAiCompare>(
        `/v1/tse/candidates/${candidateId}/ai-compare/${adv.id}`,
      );
      setReport(d);
    } catch (e) {
      const msg = e instanceof Error && e.message ? e.message : "Não foi possível gerar o confronto.";
      toast.error(msg.replace(/^http \d+:?\s*/i, "") || "Não foi possível gerar o confronto.");
      setAdversary(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-5" data-html2canvas-ignore>
      {!open && !report ? (
        <button
          onClick={() => setOpen(true)}
          className="w-full inline-flex items-center justify-center gap-2 py-3 rounded-lg border border-rose-500/40 bg-gradient-to-r from-rose-500/10 to-primary/10 hover:border-rose-500/70 transition-colors font-medium"
        >
          <Swords className="w-4 h-4 text-rose-500" /> Confronto com adversário (Maré IA)
        </button>
      ) : (
        <div className="rounded-lg border bg-card p-3">
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
            <Swords className="w-3.5 h-3.5 text-rose-500" /> Confronto estratégico · {candidateName} ×{" "}
            {adversary ? adversary.urn_name : "?"}
          </p>

          {!report && (
            <div className="relative">
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Buscar adversário pelo nome…"
                className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:border-primary/60 outline-none"
              />
              {results.length > 0 && (
                <ul className="absolute z-20 mt-1 w-full rounded-md border border-border bg-card shadow-lg max-h-72 overflow-auto divide-y divide-border">
                  {results.map((c) => (
                    <li key={c.id}>
                      <button
                        onClick={() => generate(c)}
                        className="w-full text-left px-3 py-2 hover:bg-accent/40 transition-colors"
                      >
                        <p className="text-sm font-medium">{c.urn_name}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {c.office_name} · {c.party.abbreviation} · {c.state} · {c.election.year}
                        </p>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {loading && (
                <p className="mt-2 text-sm text-muted-foreground inline-flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" /> Maré IA comparando os dois…
                </p>
              )}
              <p className="text-[11px] text-muted-foreground mt-1.5">
                Compara votos, redutos e perfil dos dois candidatos e indica onde atacar e defender.
              </p>
            </div>
          )}

          {report && (
            <div className="mn-fade-in">
              <div className="rounded-lg border bg-background p-3 mb-3">
                <p className="text-sm">{report.panorama}</p>
                <p className="text-[11px] text-rose-600 font-semibold mt-1">
                  Quem lidera: {report.quem_lidera}
                </p>
                {report.confronto && (
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {report.confronto.municipios_disputados.toLocaleString("pt-BR")} municípios
                    disputados em comum
                  </p>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <AiBlock
                  title="Suas vantagens"
                  items={report.minhas_vantagens}
                  icon={<TrendingUp className="w-3.5 h-3.5" />}
                  accent="bg-primary/10 text-primary"
                />
                <AiBlock
                  title="Forças do adversário"
                  items={report.vantagens_adversario}
                  icon={<Shield className="w-3.5 h-3.5" />}
                  accent="bg-muted text-muted-foreground"
                />
                <AiBlock
                  title="Onde atacar"
                  items={report.onde_atacar}
                  icon={<Swords className="w-3.5 h-3.5" />}
                  accent="bg-rose-500/10 text-rose-700"
                />
                <AiBlock
                  title="Onde defender"
                  items={report.onde_defender}
                  icon={<Shield className="w-3.5 h-3.5" />}
                  accent="bg-sky-500/10 text-sky-700"
                />
              </div>
              <div className="rounded-lg border border-primary/40 bg-primary/5 p-3 mt-3">
                <p className="text-xs font-semibold text-primary mb-0.5">Recomendação final</p>
                <p className="text-sm">{report.recomendacao_final}</p>
              </div>
              <button
                onClick={() => {
                  setReport(null);
                  setAdversary(null);
                }}
                className="mt-2 text-xs text-muted-foreground hover:text-foreground underline"
              >
                Comparar com outro adversário
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------ perfil do território (eleitorado)

function ProfileBars({
  title,
  cand,
  base,
  order,
}: {
  title: string;
  cand: Record<string, number>;
  base: Record<string, number>;
  order: string[];
}) {
  const keys = order.filter((k) => k in cand || k in base);
  const maxV = Math.max(1, ...keys.map((k) => Math.max(cand[k] ?? 0, base[k] ?? 0)));
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="text-xs font-semibold mb-2">{title}</p>
      <ul className="space-y-2">
        {keys.map((k) => {
          const cv = cand[k] ?? 0;
          const bv = base[k] ?? 0;
          const delta = Math.round((cv - bv) * 10) / 10;
          return (
            <li key={k} className="text-xs">
              <div className="flex items-center justify-between gap-2 mb-0.5">
                <span className="truncate">{k}</span>
                <span className="tabular-nums shrink-0">
                  <span className="font-semibold text-primary">{cv.toFixed(1)}%</span>
                  {Math.abs(delta) >= 0.1 && (
                    <span
                      className={`ml-1.5 ${delta > 0 ? "text-emerald-600" : "text-muted-foreground"}`}
                    >
                      {delta > 0 ? "+" : "−"}
                      {Math.abs(delta).toFixed(1)}
                    </span>
                  )}
                </span>
              </div>
              {/* barra do candidato + marcador da média estadual */}
              <div className="relative h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full"
                  style={{ width: `${(cv / maxV) * 100}%` }}
                />
                <div
                  className="absolute top-0 h-full w-0.5 bg-foreground/50"
                  style={{ left: `${(bv / maxV) * 100}%` }}
                  title={`Média ${title.toLowerCase()} no estado: ${bv.toFixed(1)}%`}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ElectorateProfileSection({ data }: { data: TseElectorateProfile }) {
  const AGE_ORDER = ["16-17", "18-24", "25-34", "35-44", "45-59", "60-69", "70+"];
  const EDU_ORDER = ["Analfabeto", "Lê e escreve", "Fundamental", "Médio", "Superior"];
  const GENDER_ORDER = ["Feminino", "Masculino"];
  return (
    <div className="mt-5 mn-fade-in">
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
        Perfil do território · de onde vem o seu voto
      </p>

      {data.highlights.length > 0 && (
        <div className="rounded-lg border bg-card p-3 mb-3">
          <p className="text-xs font-semibold mb-1.5">
            Destaques frente à média de {data.state}
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {data.highlights.map((h, i) => (
              <li
                key={i}
                className="text-[11px] px-2 py-1 rounded-full bg-primary/10 text-primary"
              >
                {h}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <ProfileBars
          title="Faixa etária"
          cand={data.by_age}
          base={data.baseline_by_age}
          order={AGE_ORDER}
        />
        <ProfileBars
          title="Escolaridade"
          cand={data.by_education}
          base={data.baseline_by_education}
          order={EDU_ORDER}
        />
        <ProfileBars
          title="Gênero"
          cand={data.by_gender}
          base={data.baseline_by_gender}
          order={GENDER_ORDER}
        />
      </div>
      <p className="text-[11px] text-muted-foreground mt-1.5">
        Perfil do eleitorado (TSE) dos municípios onde você teve votos, ponderado pela sua votação.
        A barra é o seu território; o traço marca a média de {data.state}. Cobertura:{" "}
        {data.municipalities_covered} de {data.municipalities_with_votes} municípios.
      </p>
    </div>
  );
}

// ------------------------------------------------ caminho da vitória

function PathToVictorySection({ data }: { data: TsePathToVictory }) {
  const scopeLabel =
    data.scope === "nacional" ? "no Brasil" : data.scope === "estadual" ? "no estado" : "na cidade";
  return (
    <div className="mt-5 mn-fade-in">
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
        <Target className="w-3.5 h-3.5 text-primary" /> Caminho da vitória
      </p>

      {data.is_winner ? (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-4 flex items-center gap-3">
          <Trophy className="w-8 h-8 text-emerald-500 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-emerald-700">
              Venceu a disputa {scopeLabel} 🎉
            </p>
            {data.margin != null && (
              <p className="text-xs text-muted-foreground mt-0.5">
                Margem de {numberFmt.format(data.margin)} votos sobre o 2º colocado.
              </p>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 mb-3">
            <div className="rounded-lg border bg-card p-3 text-center">
              <p className="text-lg font-bold text-primary">{numberFmt.format(data.candidate_votes)}</p>
              <p className="text-[11px] text-muted-foreground">Seus votos</p>
            </div>
            <div className="rounded-lg border bg-card p-3 text-center">
              <p className="text-lg font-bold text-rose-600">+{numberFmt.format(data.gap)}</p>
              <p className="text-[11px] text-muted-foreground">Faltam pra vencer</p>
            </div>
            <div className="rounded-lg border bg-card p-3 text-center">
              <p className="text-lg font-bold tabular-nums">{numberFmt.format(data.winner_votes)}</p>
              <p className="text-[11px] text-muted-foreground truncate" title={data.winner_name ?? ""}>
                {data.winner_name ? `${data.winner_name} (1º)` : "Vencedor"}
              </p>
            </div>
          </div>

          {data.targets.length > 0 && (
            <div className="rounded-lg border bg-card overflow-hidden">
              <p className="px-3 py-2 text-xs font-semibold bg-primary/10 text-primary border-b border-border">
                Onde buscar os {numberFmt.format(data.gap)} votos (maior folga de eleitorado)
              </p>
              <ul className="divide-y divide-border">
                {data.targets.map((t) => (
                  <li key={t.municipality_id} className="px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate">
                        {t.name}<span className="text-muted-foreground">/{t.state}</span>
                      </span>
                      {t.suggested > 0 && (
                        <span className="text-xs text-primary font-semibold shrink-0">
                          buscar ~{numberFmt.format(t.suggested)}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {numberFmt.format(t.available)} eleitores disponíveis · você tem{" "}
                      {t.penetration_pct.toFixed(1).replace(".", ",")}%
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-[11px] text-muted-foreground mt-1.5">
            Meta = votos do 1º colocado + 1. A distribuição é proporcional à folga de eleitorado
            (eleitorado − seus votos) por município. Use como referência de esforço.
          </p>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------ radar de oportunidades

function OpportunityRadar({ data }: { data: import("@/lib/types").TseOpportunityResponse }) {
  const pctFmt = (n: number) => n.toFixed(1).replace(".", ",");
  return (
    <div className="mt-5 mn-fade-in">
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
        Radar de oportunidades · onde buscar voto
      </p>

      {/* Resumo */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <div className="rounded-lg border bg-card p-3 text-center">
          <p className="text-lg font-bold text-primary">
            {numberFmt.format(data.total_electorate_reached)}
          </p>
          <p
            className="text-[11px] text-muted-foreground inline-flex items-center justify-center gap-1 cursor-help"
            title="Soma do eleitorado dos municípios onde você teve pelo menos 1 voto — é o seu ALCANCE territorial, NÃO os votos conquistados."
          >
            Eleitorado alcançado <Info className="w-3 h-3" />
          </p>
        </div>
        <div className="rounded-lg border bg-card p-3 text-center">
          <p className="text-lg font-bold text-amber-500">
            {numberFmt.format(Math.max(0, data.total_electorate_reached - data.total_votes))}
          </p>
          <p
            className="text-[11px] text-muted-foreground inline-flex items-center justify-center gap-1 cursor-help"
            title="Eleitores dos municípios onde você concorreu que NÃO votaram em você (eleitorado alcançado − seus votos). É o potencial ainda não conquistado no seu território."
          >
            Eleitorado que não alcançou <Info className="w-3 h-3" />
          </p>
        </div>
        <div className="rounded-lg border bg-card p-3 text-center">
          <p className="text-lg font-bold">{pctFmt(data.avg_penetration_pct)}%</p>
          <p
            className="text-[11px] text-muted-foreground inline-flex items-center justify-center gap-1 cursor-help"
            title="Média, por município, de (seus votos ÷ eleitorado do município). Mede o quanto você penetrou no eleitorado de cada lugar onde concorreu."
          >
            Penetração média <Info className="w-3 h-3" />
          </p>
        </div>
        <div className="rounded-lg border bg-card p-3 text-center">
          <p className="text-lg font-bold text-emerald-600">
            {numberFmt.format(
              data.opportunities.reduce((s, o) => s + o.available, 0),
            )}
          </p>
          <p className="text-[11px] text-muted-foreground">Eleitores a conquistar</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Onde crescer */}
        {data.opportunities.length > 0 && (
          <div className="rounded-lg border bg-card overflow-hidden">
            <p className="px-3 py-2 text-xs font-semibold bg-emerald-500/10 text-emerald-700 border-b border-border">
              ▲ Onde crescer (eleitorado grande, baixa penetração)
            </p>
            <ul className="divide-y divide-border">
              {data.opportunities.map((o) => (
                <li key={o.municipality_id} className="px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate">
                      {o.name}<span className="text-muted-foreground">/{o.state}</span>
                    </span>
                    <span className="text-xs text-emerald-600 font-semibold shrink-0">
                      +{numberFmt.format(o.available)} disp.
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {numberFmt.format(o.electorate)} eleitores · você tem {pctFmt(o.penetration_pct)}%
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Redutos */}
        {data.strongholds.length > 0 && (
          <div className="rounded-lg border bg-card overflow-hidden">
            <p className="px-3 py-2 text-xs font-semibold bg-primary/10 text-primary border-b border-border">
              ★ Seus redutos (maior penetração — consolidar)
            </p>
            <ul className="divide-y divide-border">
              {data.strongholds.map((s) => (
                <li key={s.municipality_id} className="px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate">
                      {s.name}<span className="text-muted-foreground">/{s.state}</span>
                    </span>
                    <span className="text-xs text-primary font-semibold shrink-0">
                      {pctFmt(s.penetration_pct)}%
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {numberFmt.format(s.votes)} votos de {numberFmt.format(s.electorate)} eleitores
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground mt-1.5">
        Cruzamento dos seus votos com o eleitorado registrado por município.
        Penetração = votos ÷ eleitorado.
      </p>
    </div>
  );
}

// ------------------------------------------------------------ trajetória

function TrajectorySection({
  trajectory,
  currentId,
}: {
  trajectory: TseCandidateTrajectory;
  currentId: string;
}) {
  const elected = (s: string | null) => (s ?? "").toUpperCase().startsWith("ELEITO");
  return (
    <div className="mt-5 mn-fade-in">
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
        Trajetória eleitoral · {trajectory.items.length} candidaturas
      </p>
      <ol className="relative rounded-lg border bg-card divide-y divide-border overflow-hidden">
        {trajectory.items.map((t) => {
          const isCurrent = t.candidate_id === currentId;
          const won = elected(t.result_status);
          const inner = (
            <>
              <span className="text-base font-bold tabular-nums w-12 shrink-0 text-primary">
                {t.year}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {t.office_name}{" "}
                  <span className="text-muted-foreground font-normal">
                    · {t.party_abbreviation} · {t.state}
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">
                  nº {t.number}
                  {t.total_votes != null && (
                    <> · {numberFmt.format(t.total_votes)} votos</>
                  )}
                </p>
              </div>
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0 ${
                  won
                    ? "bg-emerald-500/20 text-emerald-600"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {t.result_status
                  ? won
                    ? "ELEITO"
                    : "NÃO ELEITO"
                  : "—"}
              </span>
            </>
          );
          // O candidato atual não vira link (já estamos nele); os outros sim.
          return (
            <li key={t.candidate_id}>
              {isCurrent ? (
                <div className="px-4 py-2.5 flex items-center gap-3 bg-primary/5 border-l-2 border-primary">
                  {inner}
                </div>
              ) : (
                <Link
                  href={`/dashboard/analises/candidato/${t.candidate_id}`}
                  className="px-4 py-2.5 flex items-center gap-3 hover:bg-accent/40 transition-colors"
                >
                  {inner}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
      <p className="text-[11px] text-muted-foreground mt-1.5">
        Mesma pessoa (nome civil) nas eleições de 2014 a 2024. Clique num ano para abrir.
      </p>
    </div>
  );
}

// ----------------------------------------------------------------- pdf

function DossierDownload({ candidateId, urnName }: { candidateId: string; urnName: string }) {
  const [loading, setLoading] = useState(false);

  async function download() {
    if (loading) return;
    setLoading(true);
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";
      const token = getToken();
      const res = await fetch(`${base}/v1/tse/candidates/${candidateId}/dossier.pdf`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) throw new Error(`http ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const safe = urnName.toLowerCase().replace(/[^a-z0-9]+/g, "-");
      const a = document.createElement("a");
      a.href = url;
      a.download = `dossie-${safe}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Não foi possível gerar o dossiê PDF.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={download}
      disabled={loading}
      title="Baixar dossiê PDF do candidato"
      aria-label="Baixar dossie PDF"
      className="inline-flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-md border border-border bg-card text-sm hover:border-primary/60 hover:bg-accent/40 transition-colors disabled:opacity-60"
    >
      {loading ? (
        <Loader2 className="w-4 h-4 animate-spin" />
      ) : (
        <FileDown className="w-4 h-4" />
      )}
      <span className="hidden sm:inline">Dossiê PDF</span>
    </button>
  );
}
