"use client";

/**
 * Página dedicada do candidato — /dashboard/analises/candidato/{id}.
 * URL compartilhável com tudo: foto, resultado, perfil (patrimônio/finanças/
 * redes), votos por município, mapa, favoritar, exportar.
 */
import { ArrowLeft, Map as MapIcon, UserX } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { TseCandidateResults, TseCandidateZoneVotes } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { CandidateProfile } from "@/components/tse/CandidateProfile";
import { CandidateMapModal } from "@/components/tse/CandidateMapModal";
import { FavoriteStar } from "@/components/tse/FavoriteStar";
import { ExportShare } from "@/components/tse/ExportShare";
import { CandidateDetailSkeleton } from "@/components/tse/Skeletons";
import { EmptyState } from "@/components/tse/EmptyState";

const numberFmt = new Intl.NumberFormat("pt-BR");

export default function CandidateDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [data, setData] = useState<TseCandidateResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [zones, setZones] = useState<TseCandidateZoneVotes | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(false);
    api<TseCandidateResults>(`/v1/tse/candidates/${id}/results`)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
    // Votos por zona (404/vazio = dataset de zona não sincronizado → esconde)
    api<TseCandidateZoneVotes>(`/v1/tse/candidates/${id}/by-zone`)
      .then(setZones)
      .catch(() => setZones(null));
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
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-4">
        <Link
          href="/dashboard/analises/candidato"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Buscar candidatos
        </Link>
        <div className="flex items-center gap-3" data-html2canvas-ignore>
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
        {/* Hero */}
        <div className="rounded-xl border bg-card p-6 flex flex-col sm:flex-row items-center sm:items-start gap-5">
          <CandidatePhoto
            candidateId={c.id}
            name={c.urn_name}
            partyNumber={c.party.number}
            size="xl"
          />
          <div className="flex-1 min-w-0 text-center sm:text-left">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              {c.office_name} · {c.state} · {c.election.year}
            </p>
            <h1 className="text-2xl font-bold mt-0.5">{c.urn_name}</h1>
            <p className="text-sm text-muted-foreground">{c.name}</p>
            <div className="mt-2 flex items-center gap-2 justify-center sm:justify-start">
              <ResultBadge status={c.result_status} />
            </div>
            <div className="mt-3 flex items-center gap-2 justify-center sm:justify-start">
              <PartyLogo number={c.party.number} abbreviation={c.party.abbreviation} size="sm" />
              <div className="text-left">
                <p className="font-semibold text-sm">
                  {c.party.abbreviation} · {c.number}
                </p>
                <p className="text-xs text-muted-foreground truncate max-w-[220px]">
                  {c.party.name}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 mt-4">
          <div className="rounded-lg border bg-card/60 p-4 text-center">
            <p className="text-3xl font-bold text-primary">
              {numberFmt.format(data.total_votes)}
            </p>
            <p className="text-xs text-muted-foreground">Total de votos</p>
          </div>
          <div className="rounded-lg border bg-card/60 p-4 text-center">
            <p className="text-3xl font-bold">
              {numberFmt.format(data.municipalities_with_votes)}
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

        {/* Votos por municipio */}
        <div className="mt-5">
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
            Votos por município
          </p>
          <ul className="rounded-lg border bg-card divide-y divide-border max-h-[50vh] overflow-auto">
            {data.results.slice(0, 100).map((r) => (
              <li
                key={r.municipality.id}
                className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm"
              >
                <span className="truncate">
                  {r.municipality.name}{" "}
                  <span className="text-muted-foreground">/{r.municipality.state}</span>
                </span>
                <span className="font-mono font-semibold shrink-0">
                  {numberFmt.format(r.votes)}
                </span>
              </li>
            ))}
          </ul>
          {data.results.length > 100 && (
            <p className="text-xs text-muted-foreground pt-2">
              + {numberFmt.format(data.results.length - 100)} outro(s) município(s)
            </p>
          )}
        </div>

        {/* Votos por zona eleitoral */}
        {zones && zones.items.length > 0 && (
          <div className="mt-5">
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
