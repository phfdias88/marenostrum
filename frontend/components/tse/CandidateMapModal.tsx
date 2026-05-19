"use client";

/**
 * Modal fullscreen com mapa de votacao de um candidato.
 * Toggle entre 2 modos:
 *  - 'municipio': bolhas por municipio (sempre disponivel)
 *  - 'bairro':    bolhas por bairro (requer locais_votacao + votacao_secao
 *                 da UF do candidato importados)
 */
import { Building2, Loader2, MapPin, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type {
  TseCandidateByNeighborhoodResponse,
  TseCandidateResults,
} from "@/lib/types";

const CandidateVoteMap = dynamic(
  () => import("@/components/map/CandidateVoteMap"),
  {
    ssr: false,
    loading: () => <MapPlaceholder />,
  },
);

const CandidateNeighborhoodMap = dynamic(
  () => import("@/components/map/CandidateNeighborhoodMap"),
  {
    ssr: false,
    loading: () => <MapPlaceholder />,
  },
);

const numberFmt = new Intl.NumberFormat("pt-BR");

type Props = {
  results: TseCandidateResults;
  onClose: () => void;
};

type Mode = "municipio" | "bairro";

export function CandidateMapModal({ results, onClose }: Props) {
  const [mode, setMode] = useState<Mode>("municipio");
  const c = results.candidate;

  // Quando o candidato tem voto em apenas 1 municipio, ja seleciona ele
  // automaticamente como filtro pro bairro view.
  const singleMuniId =
    results.results.length === 1 ? results.results[0].municipality.id : null;

  const [neighborhood, setNeighborhood] =
    useState<TseCandidateByNeighborhoodResponse | null>(null);
  const [nbLoading, setNbLoading] = useState(false);
  const [nbError, setNbError] = useState<string | null>(null);

  // Carrega dados de bairro quando muda pra esse modo
  useEffect(() => {
    if (mode !== "bairro" || neighborhood !== null) return;
    setNbLoading(true);
    setNbError(null);
    const params = new URLSearchParams();
    if (singleMuniId) params.set("municipality_id", singleMuniId);
    api<TseCandidateByNeighborhoodResponse>(
      `/v1/tse/candidates/${c.id}/by-neighborhood${params.size ? "?" + params.toString() : ""}`,
    )
      .then(setNeighborhood)
      .catch((err) =>
        setNbError(err instanceof ApiError ? err.message : "Erro"),
      )
      .finally(() => setNbLoading(false));
  }, [mode, c.id, singleMuniId, neighborhood]);

  return (
    <div className="fixed inset-0 bg-black/70 z-50 grid place-items-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden">
        <header className="flex items-start justify-between p-4 border-b border-border gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Distribuição de votos · {c.office_name} · {c.state}
            </p>
            <h2 className="text-lg font-bold truncate">
              {c.urn_name}{" "}
              <span className="text-primary font-mono ml-2">{c.number}</span>{" "}
              <span className="text-muted-foreground text-sm font-normal">
                {c.party.abbreviation}
              </span>
            </h2>
            <p className="text-xs text-muted-foreground mt-1">
              <strong className="text-foreground">
                {numberFmt.format(results.total_votes)}
              </strong>{" "}
              votos em{" "}
              <strong className="text-foreground">
                {numberFmt.format(results.municipalities_with_votes)}
              </strong>{" "}
              município(s)
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* Toggle */}
            <div className="flex gap-1 bg-background border border-border rounded-md p-0.5">
              <ModeBtn
                active={mode === "municipio"}
                onClick={() => setMode("municipio")}
                icon={<MapPin className="w-3.5 h-3.5" />}
                label="Município"
              />
              <ModeBtn
                active={mode === "bairro"}
                onClick={() => setMode("bairro")}
                icon={<Building2 className="w-3.5 h-3.5" />}
                label="Bairro"
              />
            </div>
            <button
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground p-2 hover:bg-accent rounded-md"
              aria-label="Fechar"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </header>

        <div className="flex-1 min-h-0">
          {mode === "municipio" && <CandidateVoteMap results={results} />}
          {mode === "bairro" && (
            <BairroView
              loading={nbLoading}
              error={nbError}
              data={neighborhood}
              uf={c.state}
              onRetry={() => {
                setNeighborhood(null);
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function ModeBtn({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
        active
          ? "bg-foreground text-background"
          : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function BairroView({
  loading,
  error,
  data,
  uf,
  onRetry,
}: {
  loading: boolean;
  error: string | null;
  data: TseCandidateByNeighborhoodResponse | null;
  uf: string;
  onRetry: () => void;
}) {
  if (loading) {
    return (
      <div className="h-full grid place-items-center text-muted-foreground">
        <div className="flex items-center gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          Carregando bairros…
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="h-full grid place-items-center p-8 text-center">
        <div>
          <p className="text-sm text-red-400">{error}</p>
          <button
            onClick={onRetry}
            className="mt-3 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90"
          >
            Tentar novamente
          </button>
        </div>
      </div>
    );
  }
  if (!data || data.items.length === 0) {
    return (
      <div className="h-full grid place-items-center p-8 text-center">
        <div className="max-w-md">
          <Building2 className="mx-auto w-10 h-10 text-muted-foreground" />
          <p className="text-lg font-semibold mt-3">Dados de bairro indisponíveis</p>
          <p className="text-sm text-muted-foreground mt-2">
            Pra ver votos por bairro, o backend precisa ter sincronizado os
            datasets:
          </p>
          <ul className="text-xs text-muted-foreground mt-2 space-y-1">
            <li>
              <code>locais_votacao_2024</code> (locais + bairros, Brasil)
            </li>
            <li>
              <code>votacao_secao_2024_{uf}</code> (votos por seção em {uf})
            </li>
          </ul>
          <p className="text-xs text-muted-foreground mt-3">
            Use Análises → Sincronizar TSE pra disparar.
          </p>
        </div>
      </div>
    );
  }
  return <CandidateNeighborhoodMap data={data} />;
}

function MapPlaceholder() {
  return (
    <div className="h-full w-full grid place-items-center text-muted-foreground">
      Carregando mapa…
    </div>
  );
}
