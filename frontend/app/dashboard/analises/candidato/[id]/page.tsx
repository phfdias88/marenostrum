"use client";

/**
 * Página dedicada do candidato — /dashboard/analises/candidato/{id}.
 * URL compartilhável com tudo: foto, resultado, perfil (patrimônio/finanças/
 * redes), votos por município, mapa, favoritar, exportar.
 */
import { ArrowLeft, FileDown, Loader2, Map as MapIcon, UserX } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type {
  TseCandidateByNeighborhoodResponse,
  TseCandidateResults,
  TseCandidateTrajectory,
  TseCandidateZoneVotes,
  TseOpportunityResponse,
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
  const cardRef = useRef<HTMLDivElement>(null);

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

    // Radar de oportunidades (eleitorado x votos) — esconde se sem dados
    api<TseOpportunityResponse>(`/v1/tse/candidates/${id}/opportunities`)
      .then((d) => { if (!cancelled) setOpportunities(d); })
      .catch(() => { if (!cancelled) setOpportunities(null); });

    // Trajetória eleitoral — mesma pessoa em outras eleições (2014–2024)
    api<TseCandidateTrajectory>(`/v1/tse/candidates/${id}/trajectory`)
      .then((d) => { if (!cancelled) setTrajectory(d); })
      .catch(() => { if (!cancelled) setTrajectory(null); });

    api<TseCandidateResults>(`/v1/tse/candidates/${id}/results`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    // Votos por zona (404/vazio = dataset nao sincronizado → esconde)
    api<TseCandidateZoneVotes>(`/v1/tse/candidates/${id}/by-zone`)
      .then((d) => { if (!cancelled) setZones(d); })
      .catch(() => { if (!cancelled) setZones(null); });
    // Top bairros (so existe pra capitais grandes com voting_places enriquecidos)
    api<TseCandidateByNeighborhoodResponse>(
      `/v1/tse/candidates/${id}/by-neighborhood?limit=20`,
    )
      .then((d) => { if (!cancelled) setBairros(d); })
      .catch(() => { if (!cancelled) setBairros(null); });

    // Limpa estados "abertos" ao trocar de candidato.
    setShowMap(false);

    return () => {
      cancelled = true;
    };
  }, [id]);

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

// ------------------------------------------------ radar de oportunidades

function OpportunityRadar({ data }: { data: import("@/lib/types").TseOpportunityResponse }) {
  const pctFmt = (n: number) => n.toFixed(1).replace(".", ",");
  return (
    <div className="mt-5 mn-fade-in">
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
        Radar de oportunidades · onde buscar voto
      </p>

      {/* Resumo */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="rounded-lg border bg-card p-3 text-center">
          <p className="text-lg font-bold text-primary">
            {numberFmt.format(data.total_electorate_reached)}
          </p>
          <p className="text-[11px] text-muted-foreground">Eleitorado alcançado</p>
        </div>
        <div className="rounded-lg border bg-card p-3 text-center">
          <p className="text-lg font-bold">{pctFmt(data.avg_penetration_pct)}%</p>
          <p className="text-[11px] text-muted-foreground">Penetração média</p>
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
