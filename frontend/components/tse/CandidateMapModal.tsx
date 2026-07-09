"use client";

/**
 * Modal fullscreen com a DISTRIBUIÇÃO DE VOTOS de um candidato.
 *
 * Layout SPLIT-SCREEN (requisito do PO):
 *  - Desktop: mapa à esquerda + gráfico de barras HORIZONTAIS à direita.
 *  - Mobile: empilhados (mapa em cima, gráfico abaixo, com scroll).
 *
 * Modos:
 *  - 'municipio': bolhas por município (sempre disponível).
 *    Gráfico: eixo Y = município, eixo X = votos.
 *  - 'bairro': bolhas por bairro (votação por seção — cobertura por ano×UF).
 *    Gráfico: eixo Y = "Bairro (Município)" — desambigua homônimos.
 *
 * FILTROS GLOBAIS (sincronizados): município, bairro e local de votação.
 * O estado vive AQUI e alimenta TANTO o mapa QUANTO o gráfico — digitar em
 * qualquer filtro reage nos dois imediatamente. O filtro de local exige um
 * município em foco (o dado de locais é por município) e, quando ativo,
 * também restringe os bairros aos que têm local casando com a busca.
 */
import {
  Building2,
  Landmark,
  Loader2,
  MapPin,
  MousePointerClick,
  Search,
  X,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type {
  TseCandidateByNeighborhoodResponse,
  TseCandidateResults,
} from "@/lib/types";
import type { VotingPlacePoint } from "@/components/map/CandidateNeighborhoodMap";
import type { VotesBarItem } from "@/components/tse/VotesBarChart";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { MapLayoutSelector } from "@/components/map/MapLayoutSelector";

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

// Recharts é pesado → só no client (recomendação do próprio componente).
const VotesBarChart = dynamic(
  () => import("@/components/tse/VotesBarChart").then((m) => m.VotesBarChart),
  { ssr: false, loading: () => <ChartPlaceholder /> },
);

const numberFmt = new Intl.NumberFormat("pt-BR");

// Busca sem acento/caixa — mesma normalização em todos os filtros.
function norm(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

// "BANGU" → "Bangu", "ENGENHO DE DENTRO" → "Engenho de Dentro". O TSE manda
// tudo em CAIXA ALTA — no eixo do gráfico fica gritado e ocupa mais espaço.
const TC_KEEP = new Set(["de", "da", "do", "das", "dos", "e"]);
function titleCase(s: string): string {
  return s
    .toLowerCase()
    .split(/\s+/)
    .map((w, i) =>
      i > 0 && TC_KEEP.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1),
    )
    .join(" ");
}

/** Ponto pro mapa voar ao clicar numa barra — `n` re-dispara no mesmo alvo. */
type MapFocus = { lat: number; lng: number; zoom: number; n: number };

type Props = {
  results: TseCandidateResults;
  onClose: () => void;
};

type Mode = "municipio" | "bairro";

export function CandidateMapModal({ results, onClose }: Props) {
  const c = results.candidate;

  // O recorte por bairro vem da votação POR SEÇÃO. A cobertura NÃO é só 2024:
  // já temos 2024 (Brasil, prefeito/vereador) e 2018/2020/2022 (RJ, todos os
  // cargos). Como a disponibilidade depende de (ano × UF × cargo), SEMPRE
  // oferecemos o modo e deixamos o backend responder; vazio → aviso + fallback.
  const bairroAvailable = true;

  // Padrão BAIRRO pra candidatos municipais (prefeito=11, vereador=13):
  // é a granularidade que importa pra eles. Demais começam em município.
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
    // Troca de modo zera a seleção/voo (a barra selecionada era da outra visão).
    setSelKey(null);
    setFocusPt(null);
    // Voltar pra município limpa os filtros que só valem no modo bairro —
    // senão ficam visíveis-porém-inertes e o total "no filtro" mente.
    if (m === "municipio") {
      setFBairro("");
      setFLocal("");
    }
  }

  // ------------------------------------------------------------------
  // FILTROS GLOBAIS — estado compartilhado entre mapa e gráfico.
  // ------------------------------------------------------------------
  const [fMuni, setFMuni] = useState("");
  const [fBairro, setFBairro] = useState("");
  const [fLocal, setFLocal] = useState("");

  // Sincronia GRÁFICO → MAPA: barra clicada fica destacada e o mapa voa até o
  // bairro/município dela (pedido do PO: "responsivo quando clicar").
  const [selKey, setSelKey] = useState<string | null>(null);
  const [focusPt, setFocusPt] = useState<MapFocus | null>(null);
  const mapPaneRef = useRef<HTMLDivElement | null>(null);

  // Digitar bairro com o modal em modo município → troca pro modo bairro.
  // NÃO marca userPicked: se a UF×ano não tiver dado de seção, o fallback
  // automático ainda devolve o usuário pro município (sem beco sem saída).
  // nbKnownEmpty evita re-entrar no vazio a cada tecla depois do fallback.
  useEffect(() => {
    const nbKnownEmpty = neighborhood !== null && neighborhood.items.length === 0;
    if (fBairro.trim() && mode !== "bairro" && bairroAvailable && !nbKnownEmpty) {
      setMode("bairro");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fBairro]);

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
        // usuário) e não há dado de bairro, volta pra município.
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

  // ---- Visão MUNICÍPIO filtrada (mapa + gráfico usam a MESMA lista) ----
  const filteredMuniResults = useMemo(() => {
    if (!fMuni.trim()) return results;
    const n = norm(fMuni);
    return {
      ...results,
      results: results.results.filter((r) =>
        norm(r.municipality.name).includes(n),
      ),
    };
  }, [results, fMuni]);

  // Município EM FOCO (pro filtro de locais): match único da busca, ou o
  // único município do candidato.
  const focusMuni = useMemo(() => {
    if (results.results.length === 1) return results.results[0].municipality;
    if (!fMuni.trim()) return null;
    const matches = filteredMuniResults.results;
    return matches.length === 1 ? matches[0].municipality : null;
  }, [results, filteredMuniResults, fMuni]);

  // ---- Camada de LOCAIS DE VOTAÇÃO (modo bairro, município em foco) ----
  const [places, setPlaces] = useState<VotingPlacePoint[] | null>(null);
  const [placesError, setPlacesError] = useState(false);
  // O texto do filtro de local pertence ao município em foco — mudou/perdeu
  // o foco, limpa (senão a busca antiga vira filtro fantasma no novo município).
  const focusMuniId = focusMuni?.id ?? null;
  useEffect(() => {
    setFLocal("");
  }, [focusMuniId]);
  useEffect(() => {
    if (mode !== "bairro" || !focusMuni) {
      setPlaces(null);
      setPlacesError(false);
      return;
    }
    let cancelled = false;
    // Limpa os locais do município ANTERIOR já na troca de foco A→B — senão o
    // narrowing do fLocal roda 1 render com locais da cidade errada.
    setPlaces(null);
    setPlacesError(false);
    // year do candidato: os locais são year-aware (2018/2020/2022/2024).
    api<VotingPlacePoint[]>(
      `/v1/tse/voting-places/map?municipality_id=${focusMuni.id}&year=${c.election.year}`,
    )
      .then((d) => {
        if (cancelled) return;
        // Herda o município no ponto → tooltip "Local (Município)" desambigua
        // escolas homônimas (requisito do PO).
        setPlaces(d.map((p) => ({ ...p, municipality: focusMuni.name })));
      })
      .catch(() => {
        if (!cancelled) {
          setPlaces(null);
          setPlacesError(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, focusMuni, c.election.year]);

  const filteredPlaces = useMemo(() => {
    if (!places) return undefined;
    if (!fLocal.trim()) return places;
    const n = norm(fLocal);
    return places.filter((p) => norm(p.name).includes(n));
  }, [places, fLocal]);

  // ---- Visão BAIRRO filtrada (município + bairro + local) ----
  const filteredNbItems = useMemo(() => {
    let items = neighborhood?.items ?? [];
    if (fMuni.trim()) {
      const n = norm(fMuni);
      items = items.filter((i) => norm(i.municipality_name ?? "").includes(n));
    }
    if (fBairro.trim()) {
      // Busca TOKENIZADA na relação composta "Bairro (Município)" — cada
      // palavra precisa casar: "centro juiz" acha "Centro (Juiz de Fora)".
      const tokens = norm(fBairro).split(/\s+/);
      items = items.filter((i) => {
        const composite = norm(`${i.neighborhood} (${i.municipality_name ?? ""})`);
        return tokens.every((t) => composite.includes(t));
      });
    }
    // Filtro de LOCAL: restringe aos bairros que têm local casando (o dado de
    // locais é do município em foco — bairros de outros municípios saem).
    if (fLocal.trim() && filteredPlaces) {
      const nbSet = new Set(
        // Espelha o COALESCE do backend: local sem bairro entra no bucket
        // "(Sem bairro)" — senão esse grupo nunca casa no narrowing.
        filteredPlaces.map((p) => norm(p.neighborhood?.trim() || "(Sem bairro)")),
      );
      const focusName = focusMuni ? norm(focusMuni.name) : null;
      items = items.filter(
        (i) =>
          nbSet.has(norm(i.neighborhood)) &&
          (focusName === null || norm(i.municipality_name ?? "") === focusName),
      );
    }
    return items;
  }, [neighborhood, fMuni, fBairro, fLocal, filteredPlaces, focusMuni]);

  const filteredNbData = useMemo<TseCandidateByNeighborhoodResponse | null>(
    () => (neighborhood ? { ...neighborhood, items: filteredNbItems } : null),
    [neighborhood, filteredNbItems],
  );

  // Candidato de UM município só (prefeito/vereador): repetir "(Rio de
  // Janeiro)" em toda barra é ruído — o sufixo de homônimo só entra quando há
  // MAIS de um município em jogo (deputado etc.). O tooltip sempre mostra.
  const singleMuni = results.results.length === 1;

  // ---- Itens do gráfico (derivados das MESMAS listas do mapa) ----
  const chartItems = useMemo<VotesBarItem[]>(() => {
    if (mode === "municipio") {
      return filteredMuniResults.results.map((r) => ({
        key: r.municipality.id,
        label: titleCase(r.municipality.name),
        sublabel: r.municipality.state,
        value: r.votes,
      }));
    }
    return filteredNbItems.map((i) => ({
      key: `${i.municipality_id ?? ""}-${i.neighborhood}`,
      // Relação composta no EIXO — "Centro (Juiz de Fora)" (requisito do PO)
      // — exceto candidato de 1 município (sufixo vira ruído repetido).
      label:
        i.municipality_name && !singleMuni
          ? `${titleCase(i.neighborhood)} (${titleCase(i.municipality_name)})`
          : titleCase(i.neighborhood),
      sublabel: i.municipality_name
        ? `${titleCase(i.municipality_name)}/${i.municipality_state ?? ""}`
        : undefined,
      value: i.votes,
    }));
  }, [mode, filteredMuniResults, filteredNbItems, singleMuni]);

  // Clique na barra → destaca + voa até o alvo no mapa. No mobile (gráfico
  // abaixo do mapa) ainda rola a tela de volta pro mapa.
  function onBarClick(item: VotesBarItem) {
    setSelKey(item.key);
    let pt: Omit<MapFocus, "n"> | null = null;
    if (mode === "municipio") {
      const r = filteredMuniResults.results.find(
        (x) => x.municipality.id === item.key,
      );
      if (r?.municipality.latitude != null && r.municipality.longitude != null) {
        pt = { lat: r.municipality.latitude, lng: r.municipality.longitude, zoom: 11 };
      }
    } else {
      const it = filteredNbItems.find(
        (x) => `${x.municipality_id ?? ""}-${x.neighborhood}` === item.key,
      );
      if (it?.avg_lat != null && it.avg_lng != null) {
        pt = { lat: it.avg_lat, lng: it.avg_lng, zoom: 14 };
      }
    }
    if (pt) setFocusPt((p) => ({ ...pt, n: (p?.n ?? 0) + 1 }));
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      mapPaneRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // Local só é filtrável com locais CARREGADOS — antes disso a busca seria
  // silenciosamente inerte (o total diria "filtrado" sem filtrar nada).
  const localDisabled = mode !== "bairro" || !focusMuni || places === null;
  const localPlaceholder =
    mode !== "bairro" || !focusMuni
      ? "Local de votação (foque 1 município)…"
      : places === null
        ? placesError
          ? "Locais de votação indisponíveis"
          : "Carregando locais de votação…"
        : `Buscar local de votação em ${focusMuni.name}…`;

  return (
    <div className="fixed inset-0 bg-black/70 z-50 grid place-items-center p-2 sm:p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-7xl h-[92vh] sm:h-[88vh] flex flex-col overflow-hidden">
        <header className="flex items-start justify-between p-3 sm:p-4 border-b border-border gap-3">
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
              />
            </div>
            <MapLayoutSelector />
            <button
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground p-2 hover:bg-accent rounded-md"
              aria-label="Fechar"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Barra de FILTROS SINCRONIZADOS — reage no mapa E no gráfico. */}
        <div className="px-3 sm:px-4 py-2 border-b border-border grid grid-cols-1 sm:grid-cols-3 gap-2 bg-background/40">
          <FilterInput
            icon={<MapPin className="w-3.5 h-3.5" />}
            value={fMuni}
            onChange={setFMuni}
            placeholder="Buscar município…"
          />
          <FilterInput
            icon={<Building2 className="w-3.5 h-3.5" />}
            value={fBairro}
            onChange={setFBairro}
            placeholder="Buscar bairro (município)…"
            title="Filtra os bairros — a busca casa também com o município do bairro"
          />
          <FilterInput
            icon={<Landmark className="w-3.5 h-3.5" />}
            value={fLocal}
            onChange={setFLocal}
            placeholder={localPlaceholder}
            disabled={localDisabled}
            title={
              localDisabled
                ? "Os locais de votação são por município: use o modo Bairro e filtre um único município (ou candidato de 1 cidade)."
                : undefined
            }
          />
        </div>

        {/* SPLIT-SCREEN: mapa + gráfico (lado a lado no desktop, empilhados no
            mobile). No mobile o CONTAINER rola (mapa fixo em 42vh + gráfico em
            altura natural — sem isso o gráfico era CORTADO pelo overflow-hidden
            do card, inalcançável). No lg+ o aside rola por conta própria. */}
        <div className="flex-1 min-h-0 flex flex-col lg:flex-row overflow-y-auto lg:overflow-visible">
          <div
            ref={mapPaneRef}
            className="flex-1 min-h-[42vh] shrink-0 lg:shrink lg:min-h-0 relative"
          >
            {mode === "municipio" && (
              <>
                <CandidateVoteMap results={filteredMuniResults} focus={focusPt} />
                {/* Filtro zerou a lista → aviso NO MAPA (senão fica um viewport
                    velho sem explicação). pointer-events-none preserva o pan. */}
                {results.results.length > 0 &&
                  filteredMuniResults.results.length === 0 && (
                    <div className="absolute inset-0 z-[500] grid place-items-center bg-background/60 pointer-events-none">
                      <p className="text-sm text-muted-foreground max-w-sm px-4 text-center">
                        Nenhum município casa com o filtro atual. Limpe ou
                        ajuste a busca acima.
                      </p>
                    </div>
                  )}
              </>
            )}
            {mode === "bairro" && (
              <BairroView
                loading={nbLoading}
                error={nbError}
                data={filteredNbData}
                emptyIsFilter={
                  (neighborhood?.items.length ?? 0) > 0 &&
                  filteredNbItems.length === 0
                }
                uf={c.state}
                year={c.election.year}
                votingPlaces={filteredPlaces}
                focus={focusPt}
                onRetry={() => {
                  setNeighborhood(null);
                }}
              />
            )}
          </div>

          <aside className="lg:w-[400px] xl:w-[440px] shrink-0 border-t lg:border-t-0 lg:border-l border-border overflow-y-auto p-3 sm:p-4 bg-background/30">
            {/* Cabeçalho "hero": título + total dourado + chip de contagem. */}
            <div className="mb-3">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">
                {mode === "municipio"
                  ? "Votos por município"
                  : singleMuni
                    ? `Votos por bairro — ${titleCase(results.results[0].municipality.name)}`
                    : "Votos por bairro (município)"}
              </p>
              <div className="mt-1 flex items-baseline gap-2 flex-wrap">
                <span className="text-2xl font-bold text-primary tabular-nums tracking-tight">
                  {numberFmt.format(
                    chartItems.reduce((s, i) => s + i.value, 0),
                  )}
                </span>
                <span className="text-xs text-muted-foreground">
                  votos no filtro
                </span>
                <span className="ml-auto text-[11px] px-2 py-0.5 rounded-full border border-border bg-card text-muted-foreground tabular-nums">
                  {numberFmt.format(chartItems.length)}{" "}
                  {mode === "municipio"
                    ? chartItems.length === 1
                      ? "município"
                      : "municípios"
                    : chartItems.length === 1
                      ? "bairro"
                      : "bairros"}
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground mt-1.5 flex items-center gap-1.5">
                <MousePointerClick className="w-3.5 h-3.5 text-primary/70" />
                Clique numa barra para voar até ela no mapa.
              </p>
            </div>
            <VotesBarChart
              items={chartItems}
              hideSearch
              showValues
              onItemClick={onBarClick}
              selectedKey={selKey}
              topN={30}
              yAxisWidth={mode === "bairro" && !singleMuni ? 168 : 128}
              emptyText={
                mode === "bairro" && nbLoading
                  ? "Carregando bairros…"
                  : mode === "bairro" && nbError
                    ? "Erro ao carregar os bairros — use “Tentar novamente” no mapa."
                    : "Nada encontrado para esse filtro."
              }
            />
          </aside>
        </div>
      </div>
    </div>
  );
}

function FilterInput({
  icon,
  value,
  onChange,
  placeholder,
  disabled = false,
  title,
}: {
  icon: React.ReactNode;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <div className="relative" title={title}>
      <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground">
        {icon}
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full pl-8 pr-8 py-1.5 rounded-md bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-50 disabled:cursor-not-allowed"
      />
      {value ? (
        <button
          onClick={() => onChange("")}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          aria-label="Limpar filtro"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      ) : (
        <Search className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/50" />
      )}
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
  emptyIsFilter,
  uf,
  year,
  votingPlaces,
  focus,
  onRetry,
}: {
  loading: boolean;
  error: string | null;
  data: TseCandidateByNeighborhoodResponse | null;
  /** true = há dados, mas o FILTRO zerou a lista (mensagem diferente). */
  emptyIsFilter: boolean;
  uf: string;
  year: number;
  votingPlaces?: VotingPlacePoint[];
  /** Voo gráfico→mapa (clique na barra). */
  focus?: MapFocus | null;
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
    if (emptyIsFilter) {
      return (
        <div className="h-full grid place-items-center p-8 text-center">
          <p className="text-sm text-muted-foreground max-w-sm">
            Nenhum bairro casa com os filtros atuais. Limpe ou ajuste a busca
            de município/bairro/local acima.
          </p>
        </div>
      );
    }
    // Vazio = a votação por seção dessa eleição (ano × UF × cargo) ainda não
    // foi importada. NÃO é "só 2024": 2018/2020/2022 (RJ) e 2024 (Brasil) têm
    // dado; demais UFs/anos é questão de importar os datasets.
    return (
      <div className="h-full grid place-items-center p-8 text-center">
        <div className="max-w-md">
          <Building2 className="mx-auto w-10 h-10 text-muted-foreground" />
          <p className="text-lg font-semibold mt-3">
            Análise por bairro indisponível
          </p>
          <p className="text-sm text-muted-foreground mt-2">
            Ainda não há votação por seção/bairro para esta eleição
            (<strong>{uf} · {year}</strong>). O recorte por bairro depende de os
            dados de locais de votação e votos por seção dessa UF e ano terem
            sido importados. Use a visão por <strong>Município</strong>.
          </p>
        </div>
      </div>
    );
  }
  return (
    <CandidateNeighborhoodMap
      data={data}
      votingPlaces={votingPlaces}
      focus={focus}
    />
  );
}

function MapPlaceholder() {
  return (
    <div className="h-full w-full grid place-items-center text-muted-foreground">
      Carregando mapa…
    </div>
  );
}

function ChartPlaceholder() {
  return (
    <div className="h-40 grid place-items-center text-sm text-muted-foreground">
      Carregando gráfico…
    </div>
  );
}
