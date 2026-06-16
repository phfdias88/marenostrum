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
import { ResultBadge } from "@/components/tse/ResultBadge";

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
  const c = results.candidate;

  // Dado de bairro vem da votação POR SEÇÃO, que hoje só temos para 2024
  // (eleição municipal). Candidatos de outros anos (senador 2018, governador
  // 2022 etc.) nunca terão recorte por bairro — então o modo nem é oferecido.
  const bairroAvailable = c.election.year === 2024;

  // Padrão BAIRRO pra candidatos municipais (prefeito=11, vereador=13) DE 2024:
  // é a granularidade que importa pra eles. Demais começam em município. Se o
  // bairro não tiver dado, cai de volta pra município (ver efeito abaixo).
  const isMunicipal = c.office_code === 11 || c.office_code === 13;
  const [mode, setMode] = useState<Mode>(
    isMunicipal && bairroAvailable ? "bairro" : "municipio",
  );
  // Marca se o usuário escolheu o modo manualmente (pra não sobrescrever o
  // fallback em cima da escolha dele).
  const [userPicked, setUserPicked] = useState(false);

  function pick(m: Mode) {
    setUserPicked(true);
    setMode(m);
  }

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
      .then((d) => {
        setNeighborhood(d);
        // Fallback: se entramos em bairro por padrão (não por escolha do
        // usuário) e não há dado de bairro, volta pra município — evita
        // abrir direto numa tela "indisponível".
        if (!userPicked && (!d || d.items.length === 0)) {
          setMode("municipio");
        }
      })
      .catch((err) => {
        setNbError(err instanceof ApiError ? err.message : "Erro");
        if (!userPicked) setMode("municipio");
      })
      .finally(() => setNbLoading(false));
  }, [mode, c.id, singleMuniId, neighborhood, userPicked]);

  return (
    <div className="fixed inset-0 bg-black/70 z-50 grid place-items-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden">
        <header className="flex items-start justify-between p-4 border-b border-border gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Distribuição de votos · {c.office_name} · {c.state}
            </p>
            <h2 className="text-lg font-bold truncate flex items-center gap-2 flex-wrap">
              <span>{c.urn_name}</span>
              <span className="text-primary font-mono">{c.number}</span>
              <span className="text-muted-foreground text-sm font-normal">
                {c.party.abbreviation}
              </span>
              <ResultBadge status={c.result_status} />
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
                onClick={() => pick("municipio")}
                icon={<MapPin className="w-3.5 h-3.5" />}
                label="Município"
              />
              <ModeBtn
                active={mode === "bairro"}
                onClick={() => pick("bairro")}
                icon={<Building2 className="w-3.5 h-3.5" />}
                label="Bairro"
                disabled={!bairroAvailable}
                title={
                  bairroAvailable
                    ? undefined
                    : "Recorte por bairro disponível apenas para as eleições de 2024"
                }
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
              year={c.election.year}
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
  disabled = false,
  title,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
        disabled
          ? "text-muted-foreground/40 cursor-not-allowed"
          : active
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
  year,
  onRetry,
}: {
  loading: boolean;
  error: string | null;
  data: TseCandidateByNeighborhoodResponse | null;
  uf: string;
  year: number;
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
    // O recorte por bairro vem da votação por seção, que hoje só temos para
    // 2024 (eleição municipal). Para candidatos de outros anos, é uma
    // limitação de cobertura — não adianta sincronizar nada.
    const only2024 = year !== 2024;
    return (
      <div className="h-full grid place-items-center p-8 text-center">
        <div className="max-w-md">
          <Building2 className="mx-auto w-10 h-10 text-muted-foreground" />
          <p className="text-lg font-semibold mt-3">
            Análise por bairro indisponível
          </p>
          {only2024 ? (
            <p className="text-sm text-muted-foreground mt-2">
              O recorte por bairro usa os dados de votação por seção, que hoje
              só estão disponíveis para as <strong>eleições municipais de
              2024</strong> (prefeito e vereador). Este candidato concorreu em{" "}
              <strong>{year}</strong>, então não há votação por bairro — apenas
              por município.
            </p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground mt-2">
                Ainda não há dados de votação por seção em <strong>{uf}</strong>{" "}
                para esta eleição. Use a visão por <strong>Município</strong> ou
                sincronize os datasets:
              </p>
              <ul className="text-xs text-muted-foreground mt-2 space-y-1">
                <li>
                  <code>locais_votacao_2024</code> (locais + bairros, Brasil)
                </li>
                <li>
                  <code>votacao_secao_2024_{uf}</code> (votos por seção em {uf})
                </li>
              </ul>
            </>
          )}
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
