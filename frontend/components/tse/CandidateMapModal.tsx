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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type {
  TseCandidateByNeighborhoodResponse,
  TseCandidateResults,
} from "@/lib/types";
import type {
  PlacesControl,
  VotingPlacePoint,
} from "@/components/map/CandidateNeighborhoodMap";
import type { VotesBarItem } from "@/components/tse/VotesBarChart";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
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

  // ---- Camada de LOCAIS DE VOTAÇÃO (modo bairro) ----
  // Visibilidade DESACOPLADA dos filtros (pedido do PO): o usuário liga/desliga
  // a camada num toggle no próprio mapa; os filtros só definem QUAL município.
  const [showPlaces, setShowPlaces] = useState(true);
  const [places, setPlaces] = useState<VotingPlacePoint[] | null>(null);
  const [placesError, setPlacesError] = useState(false);

  // Itens de bairro filtrados por MUNICÍPIO + BAIRRO (SEM o passo de local —
  // esse passo depende dos locais, que dependem do município derivado DAQUI).
  const nbItemsPreLocal = useMemo(() => {
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
    return items;
  }, [neighborhood, fMuni, fBairro]);

  // Município EFETIVO da camada de locais: o foco do filtro de município OU o
  // ÚNICO município presente nos bairros filtrados — filtrar um bairro
  // ("Centro (Mesquita)") já libera os locais, independente do filtro de
  // município (pedido do PO: locais não dependem de bairro selecionado).
  const placesMuni = useMemo(() => {
    if (focusMuni) return { id: focusMuni.id, name: focusMuni.name };
    const ids = new Set(
      nbItemsPreLocal.map((i) => i.municipality_id ?? "").filter(Boolean),
    );
    if (ids.size !== 1) return null;
    const it = nbItemsPreLocal.find((i) => i.municipality_id);
    return it?.municipality_id && it.municipality_name
      ? { id: it.municipality_id, name: it.municipality_name }
      : null;
  }, [focusMuni, nbItemsPreLocal]);
  // Strings estáveis pros deps de efeito (o objeto placesMuni muda de
  // identidade a cada render de filtro — usá-lo em deps refaria o fetch).
  const placesMuniId = placesMuni?.id ?? null;
  const placesMuniName = placesMuni?.name ?? null;

  // O texto do filtro de local pertence ao município em foco: limpa SÓ quando
  // o foco troca pra OUTRO município. placesMuniId=null é estado TRANSITÓRIO
  // de digitação (fBairro no meio do caminho) — apagar aí descartava o texto
  // do usuário sem necessidade.
  const lastPlacesMuniRef = useRef<string | null>(null);
  useEffect(() => {
    if (placesMuniId === null) return;
    if (
      lastPlacesMuniRef.current !== null &&
      lastPlacesMuniRef.current !== placesMuniId
    ) {
      setFLocal("");
    }
    lastPlacesMuniRef.current = placesMuniId;
  }, [placesMuniId]);

  // Fetch com CACHE por município (ref): desligar/religar a camada NÃO
  // re-baixa os até ~3000 locais (VPS 1 vCPU) — igual à página de Bairros.
  // Estado transitório (id null) também preserva o cache.
  const lastFetchedMuniRef = useRef<string | null>(null);
  useEffect(() => {
    if (mode !== "bairro" || !placesMuniId || !showPlaces) return;
    if (lastFetchedMuniRef.current === placesMuniId) return; // cache válido
    let cancelled = false;
    // Troca A→B: zera antes do fetch (senão o narrowing do fLocal roda 1
    // render com locais da cidade errada).
    setPlaces(null);
    setPlacesError(false);
    // year do candidato: os locais são year-aware (2018/2020/2022/2024).
    // FALLBACK: ano sem locais importados (ex.: 2014/2016) devolvia lista
    // VAZIA e a camada "não aparecia" — cai pra base 2024 (a mais completa;
    // escolas mudam pouco, serve de referência geográfica).
    api<VotingPlacePoint[]>(
      `/v1/tse/voting-places/map?municipality_id=${placesMuniId}&year=${c.election.year}`,
    )
      .then((d) =>
        d.length === 0 && c.election.year !== 2024
          ? api<VotingPlacePoint[]>(
              `/v1/tse/voting-places/map?municipality_id=${placesMuniId}&year=2024`,
            )
          : d,
      )
      .then((d) => {
        if (cancelled) return;
        lastFetchedMuniRef.current = placesMuniId;
        // Herda o município no ponto → tooltip "Local (Município)" desambigua
        // escolas homônimas (requisito do PO).
        setPlaces(d.map((p) => ({ ...p, municipality: placesMuniName })));
      })
      .catch(() => {
        if (!cancelled) {
          setPlaces(null);
          setPlacesError(true);
          lastFetchedMuniRef.current = null; // religar a camada tenta de novo
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, placesMuniId, placesMuniName, showPlaces, c.election.year]);

  const filteredPlaces = useMemo(() => {
    if (!places) return undefined;
    if (!fLocal.trim()) return places;
    const n = norm(fLocal);
    return places.filter((p) => norm(p.name).includes(n));
  }, [places, fLocal]);

  // ---- Visão BAIRRO filtrada (município + bairro + local) ----
  const filteredNbItems = useMemo(() => {
    let items = nbItemsPreLocal;
    // Filtro de LOCAL: restringe aos bairros que têm local casando. Exige
    // placesMuniId (itens de UM município) — no estado transitório de digitação
    // o cache de locais pode ser de outro município e narraria errado.
    if (fLocal.trim() && filteredPlaces && placesMuniId) {
      const nbSet = new Set(
        // Espelha o COALESCE do backend: local sem bairro entra no bucket
        // "(Sem bairro)" — senão esse grupo nunca casa no narrowing.
        filteredPlaces.map((p) => norm(p.neighborhood?.trim() || "(Sem bairro)")),
      );
      items = items.filter((i) => nbSet.has(norm(i.neighborhood)));
    }
    return items;
  }, [nbItemsPreLocal, fLocal, filteredPlaces]);

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
  // Detalhe da barra SELECIONADA (card no topo do painel): traz números que o
  // endpoint já manda e o gráfico não mostra (locais, eleitores, penetração).
  const selDetail = useMemo(() => {
    if (!selKey) return null;
    if (mode === "municipio") {
      const r = filteredMuniResults.results.find(
        (x) => x.municipality.id === selKey,
      );
      if (!r) return null;
      return {
        title: `${titleCase(r.municipality.name)}/${r.municipality.state}`,
        votes: r.votes,
        share:
          results.total_votes > 0
            ? (r.votes / results.total_votes) * 100
            : null,
        extra: null as string | null,
      };
    }
    const it = filteredNbItems.find(
      (x) => `${x.municipality_id ?? ""}-${x.neighborhood}` === selKey,
    );
    if (!it) return null;
    const parts: string[] = [
      `${numberFmt.format(it.places_count)} ${it.places_count === 1 ? "local de votação" : "locais de votação"}`,
    ];
    if (it.electors_total > 0)
      parts.push(`${numberFmt.format(it.electors_total)} eleitores aptos`);
    if (it.penetration_pct != null)
      parts.push(
        `${String(it.penetration_pct).replace(".", ",")}% de penetração`,
      );
    return {
      title: it.municipality_name
        ? `${titleCase(it.neighborhood)} (${titleCase(it.municipality_name)})`
        : titleCase(it.neighborhood),
      votes: it.votes,
      share:
        (neighborhood?.total_votes ?? 0) > 0
          ? (it.votes / (neighborhood as TseCandidateByNeighborhoodResponse).total_votes) * 100
          : null,
      extra: parts.join(" · "),
    };
  }, [selKey, mode, filteredMuniResults, filteredNbItems, neighborhood, results]);

  // Local só é filtrável com a camada LIGADA e locais carregados — antes
  // disso a busca seria silenciosamente inerte.
  const localDisabled =
    mode !== "bairro" || !placesMuniId || !showPlaces || places === null;
  const localPlaceholder =
    mode !== "bairro" || !placesMuniId
      ? "Local de votação (filtre 1 município)…"
      : !showPlaces
        ? "Ative os locais de votação no mapa…"
        : places === null
          ? placesError
            ? "Locais de votação indisponíveis"
            : "Carregando locais de votação…"
          : `Buscar local de votação em ${placesMuniName}…`;

  // Toggle da camada de locais — renderizado DENTRO do mapa (barra de
  // controle), estado aqui na página. useCallback/useMemo: identidade estável
  // pra não re-renderizar o mapa a cada tecla dos filtros.
  const togglePlaces = useCallback(() => {
    // Desligar a camada MATA o filtro de local — senão o texto fica visível
    // porém inerte e o gráfico/total expandem contradizendo o input.
    setFLocal("");
    setShowPlaces((v) => !v);
  }, []);
  const placesControl = useMemo(
    () => ({
      active: showPlaces && !!placesMuniId && !placesError,
      disabled: mode !== "bairro" || !placesMuniId,
      loading: showPlaces && !!placesMuniId && places === null && !placesError,
      error: showPlaces && !!placesMuniId && placesError,
      onToggle: togglePlaces,
    }),
    [showPlaces, placesMuniId, places, placesError, togglePlaces, mode],
  );

  return (
    <div className="fixed inset-0 bg-black/70 z-50 grid place-items-center p-2 sm:p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-7xl h-[92dvh] sm:h-[88vh] flex flex-col overflow-hidden">
        {/* Mobile: título + X na 1ª linha e controles (Município/Bairro + tema)
            numa linha própria (w-full força o wrap) — na mesma linha eles
            esmagavam o título numa coluna de ~80px. Desktop: tudo numa linha. */}
        <header className="flex flex-wrap items-start p-3 sm:p-4 border-b border-border gap-x-3 gap-y-2">
          {/* Foto oficial do TSE dá cara de dossiê ao cabeçalho (fallback:
              iniciais na cor do partido). Escondida em telas muito estreitas. */}
          <CandidatePhoto
            candidateId={c.id}
            name={c.urn_name}
            partyNumber={c.party.number}
            size="md"
            className="hidden sm:block ring-2 ring-primary/25 rounded-full"
          />
          <div className="min-w-0 flex-1 order-1">
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

          <button
            onClick={onClose}
            className="order-2 sm:order-4 text-muted-foreground hover:text-foreground p-2 hover:bg-accent rounded-md"
            aria-label="Fechar"
          >
            <X className="w-5 h-5" />
          </button>

          <div className="flex items-center gap-2 flex-wrap order-3 w-full sm:w-auto sm:order-2 sm:ml-auto">
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
            title="Filtra os bairros. A busca casa também com o município do bairro."
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
                votingPlaces={showPlaces ? filteredPlaces : undefined}
                placesControl={placesControl}
                focus={focusPt}
                onRetry={() => {
                  setNeighborhood(null);
                }}
              />
            )}
          </div>

          <aside className="lg:w-[400px] xl:w-[440px] shrink-0 border-t lg:border-t-0 lg:border-l border-border overflow-y-auto mn-scroll p-3 sm:p-4 bg-background/30">
            {/* Cabeçalho "hero" CENTRALIZADO (polish do PO): título uppercase
                discreto, número gigante em dourado, subtítulo, chip e dica. */}
            <div className="mb-4 flex flex-col items-center justify-center text-center">
              <p className="text-sm uppercase tracking-widest text-muted-foreground">
                {mode === "municipio"
                  ? "Votos por município"
                  : singleMuni
                    ? `Votos por bairro · ${titleCase(results.results[0].municipality.name)}`
                    : "Votos por bairro (município)"}
              </p>
              <p className="mt-1 text-3xl xl:text-4xl font-bold text-primary tabular-nums tracking-tight leading-none">
                {numberFmt.format(chartItems.reduce((s, i) => s + i.value, 0))}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                votos no filtro
              </p>
              <span className="mt-2 text-[11px] px-2.5 py-0.5 rounded-full border border-primary/20 bg-primary/5 text-muted-foreground tabular-nums">
                {numberFmt.format(chartItems.length)}{" "}
                {mode === "municipio"
                  ? chartItems.length === 1
                    ? "município"
                    : "municípios"
                  : chartItems.length === 1
                    ? "bairro"
                    : "bairros"}
              </span>
              <p className="text-[11px] text-muted-foreground mt-2 flex items-center justify-center gap-1.5">
                <MousePointerClick className="w-3.5 h-3.5 text-primary/70" />
                Clique numa barra para voar até ela no mapa.
              </p>
            </div>

            {/* Card da barra selecionada: nome, votos, fatia do total e os
                extras do bairro (locais, eleitores aptos, penetração). */}
            {selDetail && (
              <div className="mb-3 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 mn-fade-in">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold truncate">
                    {selDetail.title}
                  </p>
                  <button
                    onClick={() => {
                      setSelKey(null);
                      setFocusPt(null);
                    }}
                    className="text-muted-foreground hover:text-foreground shrink-0"
                    aria-label="Limpar seleção"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
                <p className="text-lg font-bold text-primary tabular-nums leading-tight">
                  {numberFmt.format(selDetail.votes)}{" "}
                  <span className="text-xs font-normal text-muted-foreground">
                    votos
                    {selDetail.share != null
                      ? ` · ${selDetail.share.toFixed(1).replace(".", ",")}% do total do candidato`
                      : ""}
                  </span>
                </p>
                {selDetail.extra && (
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {selDetail.extra}
                  </p>
                )}
              </div>
            )}
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
                    ? "Erro ao carregar os bairros. Use “Tentar novamente” no mapa."
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
  placesControl,
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
  /** Toggle da camada de locais na barra do mapa. */
  placesControl?: PlacesControl;
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
      placesControl={placesControl}
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
