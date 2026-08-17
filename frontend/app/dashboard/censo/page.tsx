"use client";

/**
 * Dados Censitários (IBGE Censo 2022) — visão estadual com drill-down.
 * Estado (municípios coroplético) → clique no município → setores censitários
 * → clique no setor → dados do Censo. Hoje: RJ inteiro.
 */
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, BookOpen, Building2, ChevronDown, Download, Flame, Layers, Loader2, Lock, MapPin, MapPinned, Search, Sparkles, Trophy, Users } from "lucide-react";

import { api } from "@/lib/api";
import { aggregateCensusData } from "@/lib/censusAggregate";
import type { CensusIndicator } from "@/components/map/CensusMap";
import { INDICATOR_FMT, INDICATOR_TOOLTIP, indicatorShortLabel } from "@/lib/census-indicators";

const CensusMap = dynamic(
  () => import("@/components/map/CensusMap").then((m) => m.CensusMap),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full flex items-center justify-center text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> carregando mapa…
      </div>
    ),
  },
);

const numberFmt = new Intl.NumberFormat("pt-BR");

// Normaliza nome p/ busca: minúsculo, sem acento/pontuação, e expande as
// abreviações que o IBGE usa nos bairros (N. S. → Nossa Senhora, Jd → Jardim…).
const SEARCH_ABBR: [RegExp, string][] = [
  [/ n s /g, " nossa senhora "],
  [/ n sra /g, " nossa senhora "],
  [/ sta /g, " santa "],
  [/ sto /g, " santo "],
  [/ jd /g, " jardim "],
  [/ vl /g, " vila "],
  [/ pq /g, " parque "],
  [/ pe /g, " padre "],
  [/ dr /g, " doutor "],
  [/ eng /g, " engenheiro "],
  [/ pres /g, " presidente "],
];
function searchKey(s: string): string {
  let x = ` ${(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim()} `;
  for (const [re, rep] of SEARCH_ABBR) x = x.replace(re, rep);
  return x.replace(/\s+/g, " ").trim();
}
const slug = (s: string) =>
  (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

// Expande abreviações do IBGE só para EXIBIÇÃO (mantém o dado original intacto).
const DISPLAY_ABBR: [RegExp, string][] = [
  [/\bN\.?\s*S\.?\s+/g, "Nossa Senhora "],
  [/\bN\.?\s*Sra\.?\s+/g, "Nossa Senhora "],
  [/\bSta\.?\s+/g, "Santa "],
  [/\bSto\.?\s+/g, "Santo "],
  [/\bJd\.?\s+/g, "Jardim "],
  [/\bVl\.?\s+/g, "Vila "],
  [/\bPq\.?\s+/g, "Parque "],
  [/\bPe\.?\s+/g, "Padre "],
];
const prettyName = (s: string) => {
  let x = String(s ?? "");
  for (const [re, rep] of DISPLAY_ABBR) x = x.replace(re, rep);
  return x;
};

/**
 * Nome da área "de bairro" de um setor — a cadeia bairro → subdistrito →
 * distrito, num lugar só.
 *
 * Estava repetida em cinco pontos (ranking, dissolve, seleção, agregação) e
 * qualquer divergência entre eles faz o polígono desenhado receber o número de
 * outro grupo — o tipo de erro que ninguém percebe olhando a tela.
 *
 * O subdistrito no meio é o que torna o Distrito Federal utilizável: as 33
 * Regiões Administrativas (Ceilândia, Taguatinga, Gama) vivem nesse campo,
 * com nm_bairro vazio e nm_dist sempre "Brasília". O backend (/census/malha)
 * usa exatamente a mesma ordem.
 */
const areaNome = (p: Record<string, number | string | null>): string =>
  String(p.nm_bairro || p.nm_subdist || p.nm_dist || "—");

type FC = {
  type: "FeatureCollection";
  features: Array<{ type: "Feature"; geometry: unknown; properties: Record<string, number | string | null> }>;
};

// As 27 UFs. Até a carga nacional (ago/2026) só existiam quatro aqui, e a
// tela mostrava o código cru ("29") para qualquer outra — o seletor listava
// "Bahia" como "29". A lista de UFs exibidas continua vindo do banco (só
// aparece quem tem dado carregado); este dicionário é só o nome.
const UF_NOMES: Record<string, string> = {
  "11": "Rondônia", "12": "Acre", "13": "Amazonas", "14": "Roraima",
  "15": "Pará", "16": "Amapá", "17": "Tocantins",
  "21": "Maranhão", "22": "Piauí", "23": "Ceará", "24": "Rio Grande do Norte",
  "25": "Paraíba", "26": "Pernambuco", "27": "Alagoas", "28": "Sergipe",
  "29": "Bahia",
  "31": "Minas Gerais", "32": "Espírito Santo", "33": "Rio de Janeiro",
  "35": "São Paulo",
  "41": "Paraná", "42": "Santa Catarina", "43": "Rio Grande do Sul",
  "50": "Mato Grosso do Sul", "51": "Mato Grosso", "52": "Goiás",
  "53": "Distrito Federal",
};

// Dicionários do Censo (config estática — o conjunto de variáveis é fixo e vem
// das colunas ingeridas; trocar de dicionário troca as variáveis exibidas).
// `disabled` marca variáveis cujo DADO ainda não existe por setor (ex.: renda,
// que o Censo 2022 só publica por município) — aparece, mas explicando.
type CensusVar = {
  key: CensusIndicator;
  label: string;
  disabled?: boolean;
  note?: string;
};
const DICTIONARIES: { key: string; label: string; vars: CensusVar[] }[] = [
  {
    key: "dominios",
    label: "Domínios",
    vars: [
      { key: "populacao", label: "População" },
      { key: "densidade_hab_km2", label: "Densidade" },
      { key: "domicilios", label: "Domicílios" },
      { key: "media_moradores", label: "Moradores/domic." },
    ],
  },
  {
    key: "educacao",
    label: "Educação",
    vars: [{ key: "taxa_alfabetizacao", label: "Alfabetização 15+" }],
  },
  {
    key: "cor_raca",
    label: "Cor ou raça",
    // Categorias INDIVIDUAIS do Censo 2022 (pedido do PO), + o agregado
    // pretos+pardos mantido por conveniência.
    vars: [
      { key: "pct_branca", label: "Branca" },
      { key: "pct_preta", label: "Preta" },
      { key: "pct_parda", label: "Parda" },
      { key: "pct_amarela", label: "Amarela" },
      { key: "pct_indigena", label: "Indígena" },
      { key: "pct_pretos_pardos", label: "Pretos e pardos" },
    ],
  },
  {
    key: "sexo_idade",
    label: "Sexo & idade",
    vars: [
      { key: "pct_feminino", label: "Mulheres" },
      { key: "pct_60mais", label: "60 anos ou mais" },
    ],
  },
  {
    key: "renda",
    label: "Renda & economia",
    vars: [
      {
        // NÃO é `disabled`. A nota antiga dizia que "o IBGE não publica renda
        // por setor" — publica: é o agregado Rendimento do Responsável (V06004),
        // já carregado por setor (migration 055 + ingest_census_renda_setor.py).
        // O backend entrega `renda_media` no payload do setor e a agregação por
        // bairro pondera pelo nº de responsáveis. Estava tudo pronto e travado
        // só por este campo — o sócio reportou "não tem os dados de renda".
        key: "renda_media",
        label: "Renda média",
        note: "Rendimento médio mensal dos responsáveis pelo domicílio (Censo 2022). Por bairro, é a média ponderada pelo número de responsáveis de cada setor.",
      },
      {
        key: "pib_per_capita",
        label: "PIB per capita",
        disabled: true,
        note: "PIB municipal (IBGE 2023) por habitante. Disponível na visão estadual.",
      },
    ],
  },
  {
    key: "social",
    label: "Assistência social",
    vars: [
      {
        key: "pct_bolsa_familia",
        label: "Bolsa Família",
        disabled: true,
        note: "Bolsa Família / CadÚnico (MDS) é por MUNICÍPIO. Veja na visão estadual: o mapa colore cada município pela % de domicílios atendidos.",
      },
      {
        key: "pct_cadunico",
        label: "CadÚnico",
        disabled: true,
        note: "Inscritos no CadÚnico (MDS) por município. Disponível na visão estadual.",
      },
    ],
  },
  {
    key: "desenvolvimento",
    label: "Desenvolvimento",
    vars: [
      {
        key: "idhm",
        label: "IDHM",
        disabled: true,
        note: "IDHM (Atlas Brasil/PNUD, Censo 2010 — última versão municipal). Por município, na visão estadual.",
      },
      {
        key: "ideb_anos_iniciais",
        label: "IDEB (iniciais)",
        disabled: true,
        note: "IDEB anos iniciais (INEP 2023, rede pública). Por município, na visão estadual.",
      },
      {
        key: "ideb_anos_finais",
        label: "IDEB (finais)",
        disabled: true,
        note: "IDEB anos finais (INEP 2023, rede pública). Por município, na visão estadual.",
      },
    ],
  },
  {
    key: "saneamento",
    label: "Saneamento",
    vars: [
      {
        key: "pct_esgoto_adequado",
        label: "Esgoto adequado",
        disabled: true,
        note: "% de domicílios com esgoto adequado (Censo 2022). Por município, na visão estadual.",
      },
      {
        key: "pct_agua_rede",
        label: "Água por rede",
        disabled: true,
        note: "% de domicílios com água da rede geral (Censo 2022). Por município, na visão estadual.",
      },
      {
        key: "pct_lixo_coletado",
        label: "Lixo coletado",
        disabled: true,
        note: "% de domicílios com lixo coletado (Censo 2022). Por município, na visão estadual.",
      },
    ],
  },
];

// Lista plana (compatibilidade com os usos antigos: seletor do estado etc.).
const INDICATORS: { key: CensusIndicator; label: string }[] = DICTIONARIES
  .flatMap((d) => d.vars)
  .filter((v) => !v.disabled)
  .map((v) => ({ key: v.key, label: v.label }));

// Explicações (tooltip nativo) dos botões de indicador da visão ESTADUAL —
// cada fonte/ano é própria, não é tudo "Censo 2022".
const STATE_INDICATOR_HINTS: Partial<Record<CensusIndicator, string>> = {
  renda_media: "Renda média domiciliar (IBGE/Atlas, base 2010), em R$ por mês",
  idhm: "Desenvolvimento humano municipal (0 a 1, maior é melhor) — Atlas/PNUD, base 2010",
  ideb_anos_iniciais: "Qualidade da educação básica (0 a 10) — INEP 2023",
  pct_cadunico: "% de domicílios no Cadastro Único — MDS",
  pib_per_capita: "Riqueza do município dividida pelos habitantes (IBGE 2023), em R$/ano por pessoa",
};

export type Malha = "setor" | "distrito" | "bairro";

// Versão dos dados do censo. A resposta tem Cache-Control de 7 dias (perf), então
// o NAVEGADOR cacheia. Ao adicionar/atualizar indicadores (renda, PIB, IDHM,
// IDEB, saneamento, CadÚnico...), BUMP isto pra furar o cache do browser e os
// novos campos aparecerem na hora, sem esperar 7 dias.
// 2026-08-15: carga nacional. Sem virar esta chave, o navegador de quem já
// usou a tela continua servindo do próprio cache a lista antiga de 4 UFs —
// era o que fazia "só aparecer o Rio" mesmo com o país inteiro no banco.
const CENSUS_V = "2026-08-15";

// Limite de setores pro DEFAULT em mosaico. Até este nº de setores o município
// abre direto no mosaico (render síncrono cabe em ~300-450ms, mascarado pelo
// spinner de "Carregando N setores"); acima, o default cai pro bairro dissolvido
// pra não travar o browser (setor continua opt-in). ~15-20 capitais ficam acima
// (BH/Recife ~4-6k, Rio ~10.7k, SP ~26k); todo o resto ganha o mosaico por padrão.
const SETOR_MAX_FEATURES = 3000;

export default function CensoPage() {
  const [ufGeo, setUfGeo] = useState<FC | null>(null);
  const [setores, setSetores] = useState<FC | null>(null);
  const [view, setView] = useState<"estado" | "municipio">("estado");
  const [muniProps, setMuniProps] = useState<Record<string, number | string | null> | null>(null);
  // Overlay de contornos (setores dissolvidos por bairro/distrito no backend).
  const [showContours, setShowContours] = useState(false);
  const [contourBairro, setContourBairro] = useState<FC | null>(null);
  const [contourDistrito, setContourDistrito] = useState<FC | null>(null);
  const [contoursLoading, setContoursLoading] = useState(false);
  // Busca os contornos dissolvidos (backend/shapely) quando o overlay liga,
  // por município. Cacheável pelo nginx; o browser não paga o dissolve.
  useEffect(() => {
    if (!showContours || view !== "municipio" || !muniProps?.cd_mun) return;
    const cd = String(muniProps.cd_mun);
    let cancelled = false;
    setContoursLoading(true);
    Promise.all([
      api<FC>(`/v1/census/malha?cd_mun=${cd}&level=bairro&v=${CENSUS_V}`),
      api<FC>(`/v1/census/malha?cd_mun=${cd}&level=distrito&v=${CENSUS_V}`),
    ])
      .then(([b, d]) => {
        if (!cancelled) {
          setContourBairro(b);
          setContourDistrito(d);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setContourBairro(null);
          setContourDistrito(null);
        }
      })
      .finally(() => {
        if (!cancelled) setContoursLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showContours, view, muniProps?.cd_mun]);
  const [indicator, setIndicator] = useState<CensusIndicator>("populacao");
  // Malha (nível geográfico) da visão de município: setor (cru), distrito ou
  // bairro (cada setor colorido pelo agregado da área-pai). Dicionário ativo
  // no seletor de variáveis.
  // Estado da malha. O default do STATE é "bairro", mas o EFETIVO (effMalha) é
  // ADAPTATIVO enquanto o usuário não escolhe na mão: cidade pequena/média abre
  // no MOSAICO de setor (bordas finas, cores vivas); só megacidade (> ~3k
  // setores → trava o browser) cai no bairro dissolvido. Setor acima do limite
  // continua opt-in explícito (mascarado pelo spinner).
  const [malha, setMalha] = useState<Malha>("bairro");
  // Marca se o usuário escolheu a malha MANUALMENTE (clique no seletor ou
  // deep-link ?malha=). Enquanto false, o default segue o adaptativo acima.
  const userPickedMalha = useRef(false);
  // Toggle do painel de detalhe: mostra a composição (cor/raça, sexo/idade) em
  // PORCENTAGEM ou em NÚMERO ABSOLUTO de pessoas (pedido do PO).
  const [valueMode, setValueMode] = useState<"pct" | "abs">("pct");
  // Geometria DISSOLVIDA (contornos de bairro/distrito) — poucos polígonos.
  // Usada como fill do mapa quando a malha ≠ setor, no lugar de recolorir os
  // 13k setores (que travava). O dissolve roda no backend (shapely) e é cacheado.
  const [malhaGeo, setMalhaGeo] = useState<FC | null>(null);
  const [malhaLoading, setMalhaLoading] = useState(false);
  // Série mensal CadÚnico/Bolsa Família (MDS) do município aberto.
  const [mdsSeries, setMdsSeries] = useState<
    { anomes: string; pbf_valor: number | null; pbf_familias: number | null }[] | null
  >(null);
  const [selectedDict, setSelectedDict] = useState<string>("dominios");
  const [sel, setSel] = useState<Record<string, number | string | null> | null>(null);
  const [loading, setLoading] = useState(true);
  const [muniQuery, setMuniQuery] = useState("");
  const [bairroQuery, setBairroQuery] = useState("");
  const [aiInsight, setAiInsight] = useState<{
    content: { perfil?: string; leitura_estrategica?: string; publicos?: string[]; recomendacoes?: string[] };
    cached?: boolean;
  } | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  // Comparador de municípios (visão estadual) — usa só o uf-overview (instantâneo)
  const [cmpA, setCmpA] = useState<string | null>(null);
  const [cmpB, setCmpB] = useState<string | null>(null);
  const [cmpQA, setCmpQA] = useState("");
  const [cmpQB, setCmpQB] = useState("");
  const [focusIds, setFocusIds] = useState<string[]>([]);
  const [selArea, setSelArea] = useState<{
    nome: string; kind: string; pop: number; dom: number; setores: number;
    area: number; dens: number | null; media: number | null;
    alfab: number | null; pp: number | null;
    // Cor/raça DESAGREGADA (Censo 2022, pedido do PO) — % ponderada + nº absoluto.
    branca: number | null; preta: number | null; parda: number | null;
    amarela: number | null; indigena: number | null;
    nBranca: number | null; nPreta: number | null; nParda: number | null;
    nAmarela: number | null; nIndigena: number | null;
    // Sexo/idade — % + nº absoluto.
    pctFem: number | null; nFem: number | null;
    pct60: number | null; n60: number | null;
    // Alfabetizados 15+ (nº absoluto) — pra o toggle %↔nº da alfabetização.
    nAlfab: number | null;
    // Somas brutas do bairro (idade_*, dom_agua_*, sexo_*...) — fonte única pro
    // painel calcular homens, pirâmide etária (11 faixas) e saneamento (%↔nº).
    sums: Record<string, number>;
  } | null>(null);
  // null = verificando; true/false = liberado pelo admin?
  const [allowed, setAllowed] = useState<boolean | null>(null);

  const [uf, setUf] = useState("33");
  const [ufsDisponiveis, setUfsDisponiveis] = useState<string[]>(["33"]);

  // Deep-link da busca global: /dashboard/censo?mun=3304557&area=Santa%20Cruz
  // abre direto o município e destaca o bairro. Lemos via window.location
  // (não useSearchParams) pra não exigir Suspense no prerender estático.
  const pendingNav = useRef<{ mun: string; area: string | null } | null>(null);
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const mun = sp.get("mun");
    if (mun && /^\d{7}$/.test(mun)) {
      pendingNav.current = { mun, area: sp.get("area") };
      setUf(mun.slice(0, 2));
    }
  }, []);

  // Etapa 1 do deep-link: estado carregado → abre o município pedido.
  useEffect(() => {
    const p = pendingNav.current;
    if (!p || !ufGeo) return;
    const f = ufGeo.features.find((x) => String(x.properties.cd_mun) === p.mun);
    if (!f) { pendingNav.current = null; return; }
    openMunicipio(f.properties);
    if (!p.area) pendingNav.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ufGeo]);

  // Etapa 2: setores carregados → destaca o bairro/distrito pedido.
  useEffect(() => {
    const p = pendingNav.current;
    if (!p || !p.area || !setores) return;
    pendingNav.current = null;
    openArea(p.area);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setores]);

  // Gate: o módulo Censo precisa estar liberado pelo admin (census_enabled).
  useEffect(() => {
    api<{ census_enabled?: boolean }>("/v1/auth/me")
      .then((m) => setAllowed(!!m.census_enabled))
      .catch(() => setAllowed(false));
  }, []);

  // UFs com censo carregado (deriva dos municípios disponíveis).
  useEffect(() => {
    if (allowed !== true) return;
    api<{ cd_mun: string }[]>(`/v1/census/municipalities?v=${CENSUS_V}`)
      .then((ms) => {
        const ufs = [...new Set(ms.map((m) => String(m.cd_mun).slice(0, 2)))].sort();
        if (ufs.length) setUfsDisponiveis(ufs);
      })
      .catch(() => undefined);
  }, [allowed]);

  // Visão estadual (municípios) — só busca se liberado; refaz ao trocar UF.
  useEffect(() => {
    if (allowed !== true) return;
    setLoading(true);
    setUfGeo(null);
    setCmpA(null); setCmpB(null); setCmpQA(""); setCmpQB("");
    api<FC>(`/v1/census/uf-overview?uf=${uf}&v=${CENSUS_V}`)
      .then(setUfGeo)
      .catch(() => setUfGeo(null))
      .finally(() => setLoading(false));
  }, [allowed, uf]);

  function openMunicipio(props: Record<string, number | string | null>) {
    setMuniProps(props);
    setView("municipio");
    // indicadores só-município (renda, PIB, social, IDHM, IDEB, saneamento):
    // ao entrar no setor volta pra população.
    if (muniOnly.includes(indicator)) {
      setIndicator("populacao"); setSelectedDict("dominios");
    }
    setSel(null);
    setSelArea(null);
    setSetores(null);
    setFocusIds([]);
    setBairroQuery("");
    setAiInsight(null);
    setAiError(null);
    setLoading(true);
    api<FC>(`/v1/census/setores?cd_mun=${props.cd_mun}&v=${CENSUS_V}`)
      .then(setSetores)
      .catch(() => setSetores(null))
      .finally(() => setLoading(false));
  }

  function backToEstado() {
    setView("estado");
    setSetores(null);
    setMuniProps(null);
    setSel(null);
    setSelArea(null);
    setFocusIds([]);
    setBairroQuery("");
    setAiInsight(null);
    setAiError(null);
  }

  // ---- Estado do mapa na URL (compartilhável + sobrevive ao F5) -----------
  // Antes, F5 voltava sempre pra visão estadual default — impossível mandar
  // um link do município/indicador pro colega. replaceState (não router) pra
  // não re-renderizar; leitura 1x no mount + quando o ufGeo carrega.
  const pendingUrlMun = useRef<string | null>(null);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const pUf = q.get("uf");
    if (pUf && /^\d{2}$/.test(pUf)) setUf(pUf);
    const pInd = q.get("ind");
    if (pInd) {
      setIndicator(pInd as CensusIndicator);
      const dict = INDICATORS.find((i) => i.key === pInd);
      if (dict && (dict as { dict?: string }).dict) setSelectedDict((dict as { dict?: string }).dict!);
    }
    const pMalha = q.get("malha");
    if (pMalha === "setor" || pMalha === "distrito" || pMalha === "bairro") {
      userPickedMalha.current = true;
      setMalha(pMalha);
    }
    pendingUrlMun.current = q.get("mun");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Quando o estado carrega e há ?mun= pendente, abre o município do link.
  useEffect(() => {
    if (!ufGeo || !pendingUrlMun.current) return;
    const f = ufGeo.features.find(
      (x) => String(x.properties.cd_mun) === pendingUrlMun.current,
    );
    pendingUrlMun.current = null;
    if (f) openMunicipio(f.properties);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ufGeo]);
  // Espelha o estado atual na URL (sem navegação).
  useEffect(() => {
    if (allowed !== true) return;
    const q = new URLSearchParams();
    q.set("uf", uf);
    if (view === "municipio" && muniProps?.cd_mun) q.set("mun", String(muniProps.cd_mun));
    if (indicator !== "populacao") q.set("ind", indicator);
    if (malha !== "bairro") q.set("malha", malha);
    window.history.replaceState(null, "", `?${q.toString()}`);
  }, [allowed, uf, view, muniProps?.cd_mun, indicator, malha]);

  function askMareIa(force = false) {
    if (!muniProps || aiLoading) return;
    setAiLoading(true);
    setAiError(null);
    api<{ content: NonNullable<typeof aiInsight>["content"]; cached?: boolean }>(
      `/v1/census/ai-insight?cd_mun=${muniProps.cd_mun}${force ? "&force=true" : ""}`,
      { skipCache: true },
    )
      .then(setAiInsight)
      .catch(() => setAiError("A Maré IA está sobrecarregada agora. Tente de novo em instantes."))
      .finally(() => setAiLoading(false));
  }

  // Clique num setor no mapa → detalhe do setor (destaca só ele).
  function onSetorClick(props: Record<string, number | string | null>) {
    setSel(props);
    setSelArea(null);
    setFocusIds([String(props.cd_setor)]);
  }

  // Seleciona um BAIRRO/distrito inteiro (busca ou ranking): destaca todos os
  // setores dele no mapa e mostra o total no painel.
  function openArea(nome: string) {
    if (!setores) return;
    const feats = setores.features.filter(
      (f) => areaNome(f.properties) === nome,
    );
    if (!feats.length) return;
    // Agregação oficial via lib/censusAggregate: absolutos somados; as
    // taxas saem das somas (= média ponderada exata, sem drift de
    // arredondamento por setor).
    const [g] = aggregateCensusData(
      feats.map((f) => ({ ...f.properties, __area: nome })),
      "__area",
    );
    const pop = g.sums.populacao ?? 0;
    const dom = g.sums.domicilios ?? 0;
    const alfa = g.sums.alfabetizados_15mais ?? 0;
    const p15 = g.sums.pop_15mais ?? 0;
    const pp = (g.sums.raca_preta ?? 0) + (g.sums.raca_parda ?? 0);
    // % por categoria de cor/raça — MESMA base do "pretos e pardos" (contagem
    // absoluta ÷ população), pra os números baterem entre si (preta+parda=pp) e
    // somarem ~100%. 0% é valor legítimo (ex.: indígena) → só vira "—" sem pop.
    const racaPct = (n: number | undefined) =>
      pop > 0 ? Number((((n ?? 0) / pop) * 100).toFixed(1)) : null;
    const masc = g.sums.sexo_masculino ?? 0;
    const fem = g.sums.sexo_feminino ?? 0;
    const i60 = g.sums.idade_60mais ?? 0;
    setSelArea({
      nome,
      kind: feats[0].properties.nm_bairro ? "Bairro" : "Distrito",
      pop, dom, setores: g.setores, area: g.sums.area_km2 ?? 0,
      dens: g.derived.densidade_hab_km2 != null
        ? Math.round(g.derived.densidade_hab_km2) : null,
      media: dom > 0 ? Number((pop / dom).toFixed(2)) : null,
      alfab: p15 > 0 ? Number(((alfa / p15) * 100).toFixed(1)) : null,
      pp: pop > 0 && pp > 0 ? Number(((pp / pop) * 100).toFixed(1)) : null,
      branca: racaPct(g.sums.raca_branca),
      preta: racaPct(g.sums.raca_preta),
      parda: racaPct(g.sums.raca_parda),
      amarela: racaPct(g.sums.raca_amarela),
      indigena: racaPct(g.sums.raca_indigena),
      nBranca: g.sums.raca_branca ?? null,
      nPreta: g.sums.raca_preta ?? null,
      nParda: g.sums.raca_parda ?? null,
      nAmarela: g.sums.raca_amarela ?? null,
      nIndigena: g.sums.raca_indigena ?? null,
      pctFem: masc + fem > 0 ? Number(((fem / (masc + fem)) * 100).toFixed(1)) : null,
      nFem: masc + fem > 0 ? fem : null,
      pct60: pop > 0 ? Number(((i60 / pop) * 100).toFixed(1)) : null,
      n60: pop > 0 ? i60 : null,
      nAlfab: p15 > 0 ? alfa : null,
      sums: g.sums,
    });
    setSel(null);
    // Malha dissolvida NÃO tem setores no mapa (1 polígono por bairro): foca pelo
    // NOME (o CensusMap registra o polígono dissolvido por nome) pra o mapa VOAR
    // até o bairro na busca. Em modo setor, foca os setores do bairro.
    setFocusIds(effMalha === "setor" ? feats.map((f) => String(f.properties.cd_setor)) : [nome]);
    setBairroQuery("");
  }

  // Clique no mapa (dentro do município): setor → detalhe do setor; polígono de
  // área dissolvida (bairro/distrito, sem cd_setor) → seleciona a área inteira.
  function onMapSelect(props: Record<string, number | string | null>) {
    if (props.cd_setor != null) onSetorClick(props);
    else openArea(String(props.nome ?? props.nm_mun ?? "—"));
  }

  // ---- Navegação hierárquica: Setor → Bairro/Distrito → Município → Estado.
  // A "pilha" é derivada dos estados (sel ⊂ selArea ⊂ município ⊂ estado),
  // então breadcrumb, painel e destaque do mapa nunca dessincronizam.
  function clearToMunicipio() {
    setSel(null);
    setSelArea(null);
    setFocusIds([]);
  }

  function navUp() {
    if (sel) {
      // setor → sobe pro bairro/distrito dele (se mapeado), senão pro município
      const areaDoSetor = sel.nm_bairro || sel.nm_subdist ? areaNome(sel) : "";
      if (areaDoSetor && areaDoSetor !== "—") openArea(areaDoSetor);
      else clearToMunicipio();
      return;
    }
    if (selArea) {
      clearToMunicipio();
      return;
    }
    backToEstado();
  }

  // Esc = subir um nível (Setor → Bairro → Município → Estado).
  // Ignora quando o foco está num campo de texto — Esc ali é "limpar busca".
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape" || view !== "municipio") return;
      const el = document.activeElement;
      if (el instanceof HTMLElement && ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)) return;
      navUp();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // navUp é função declarada no render; as deps cobrem tudo que ela lê.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, sel, selArea, setores]);

  // Totais do estado (somatório das features de município)
  const ufTotals = ufGeo?.features.reduce(
    (a, f) => ({
      pop: a.pop + Number(f.properties.populacao ?? 0),
      dom: a.dom + Number(f.properties.domicilios ?? 0),
      setores: a.setores + Number(f.properties.setores ?? 0),
    }),
    { pop: 0, dom: 0, setores: 0 },
  );

  const mapData = view === "estado" ? ufGeo : setores;
  // Estado não tem densidade (sem área por município) — cai pra População.
  // Visão estadual (coroplético por município) ganha a RENDA, que só existe
  // nesse nível (IBGE não publica renda por setor).
  const stateIndicators = [
    ...INDICATORS.filter((i) => i.key !== "densidade_hab_km2"),
    { key: "renda_media" as CensusIndicator, label: "Renda média" },
    { key: "pib_per_capita" as CensusIndicator, label: "PIB per capita" },
    { key: "pct_bolsa_familia" as CensusIndicator, label: "Bolsa Família" },
    { key: "pct_cadunico" as CensusIndicator, label: "CadÚnico" },
    { key: "idhm" as CensusIndicator, label: "IDHM" },
    { key: "ideb_anos_iniciais" as CensusIndicator, label: "IDEB" },
    { key: "pct_esgoto_adequado" as CensusIndicator, label: "Esgoto" },
  ];
  // Indicadores que só existem por MUNICÍPIO (não por setor) — ao entrar no
  // município (drill pra setor) caem pra população.
  // renda_media SAIU desta lista: o Censo 2022 publicou renda do responsável
  // POR SETOR (ingest_census_renda_setor.py) — a renda agora sobrevive ao
  // drill-down (setor cinza = sem dado/sigilo, igual aos outros indicadores).
  const muniOnly = [
    "pib_per_capita", "pct_bolsa_familia", "pct_cadunico",
    "idhm", "ideb_anos_iniciais", "ideb_anos_finais",
    "pct_esgoto_adequado", "pct_agua_rede", "pct_lixo_coletado",
  ];
  const mapIndicator: CensusIndicator =
    view === "estado" && indicator === "densidade_hab_km2" ? "populacao"
      : view === "municipio" && muniOnly.includes(indicator) ? "populacao"
        : indicator;

  // Busca tolerante: tira acento/pontuação e expande abreviações do IBGE
  // (ex.: "N. S. das Graças" <-> "Nossa Senhora das Graças", "Jd" -> "Jardim").
  const matchName = (name: string, query: string) => {
    const n = searchKey(name);
    const q = searchKey(query);
    if (!q) return false;
    return n.includes(q) || q.split(" ").every((t) => t && n.includes(t));
  };
  const muniMatches =
    view === "estado" && muniQuery.trim().length >= 2
      ? (ufGeo?.features ?? [])
          .filter((f) => matchName(String(f.properties.nm_mun ?? ""), muniQuery))
          .slice(0, 8)
      : [];

  // Top municípios do estado (visão estadual) — ranqueia pelo MESMO indicador
  // mostrado no mapa (renda, IDEB, esgoto…), não fixo em população, pra a lista
  // acompanhar o que o usuário escolheu. Tira os sem dado (val 0/nulo).
  const topMunicipios = (ufGeo?.features ?? [])
    .map((f) => ({
      nome: String(f.properties.nm_mun ?? ""),
      cd: String(f.properties.cd_mun ?? ""),
      val: Number(f.properties[mapIndicator] ?? 0),
      props: f.properties,
    }))
    .filter((m) => m.val > 0)
    .sort((a, b) => b.val - a.val)
    .slice(0, 10);

  // Agregação por bairro (se houver) ou distrito: pop, domicílios, área, setores.
  // Subdistrito conta como "bairro" pro seletor: é o recorte intermediário
  // real em Brasília e em cidades como Contagem, onde nm_bairro vem vazio.
  const hasBairros = !!setores?.features.some(
    (f) => f.properties.nm_bairro || f.properties.nm_subdist,
  );
  // A malha "bairro" só faz sentido se o município tiver bairros mapeados —
  // senão cai pra distrito (Seropédica, p.ex., só tem distrito). Cascata
  // defensiva: bairro → distrito → setor, validando que o nível existe.
  const hasDistritos = !!setores?.features.some(
    (f) => f.properties.nm_dist && String(f.properties.nm_dist).trim() !== "",
  );
  // Default ADAPTATIVO: enquanto o usuário não escolhe a malha na mão, cidades
  // pequenas/médias (<= SETOR_MAX_FEATURES setores) abrem no MOSAICO de setores
  // (bordas finas, cores vivas, alta variância); só as megacidades acima do
  // limite caem no fallback dissolvido pra não travar o browser. setores.features
  // já está em mãos no render — não precisa de query. setores=null (carregando)
  // → autoDefault "bairro", igual ao comportamento seguro atual até chegar o dado.
  const autoDefaultMalha: Malha =
    setores && setores.features.length <= SETOR_MAX_FEATURES ? "setor" : "bairro";
  const baseMalha: Malha = userPickedMalha.current ? malha : autoDefaultMalha;
  const effMalha: Malha =
    baseMalha === "bairro" && !hasBairros
      ? hasDistritos
        ? "distrito"
        : "setor"
      : baseMalha === "distrito" && !hasDistritos
        ? "setor"
        : baseMalha;
  // Coluna de agrupamento da área conforme a malha escolhida. O SUBDISTRITO
  // entra entre bairro e distrito — é onde o IBGE guarda as 33 Regiões
  // Administrativas do DF (Ceilândia, Taguatinga), que sem isso caíam todas
  // num grupo só chamado "Brasília". MESMA cadeia do backend (/census/malha),
  // senão os polígonos dissolvidos não casam com este agregado.
  const areaGroupOf = (p: Record<string, number | string | null>) =>
    effMalha === "distrito"
      ? String(p.nm_dist || "—")
      : areaNome(p);
  const areaKind = effMalha === "distrito" || !hasBairros ? "Distritos" : "Bairros";

  // O ranking lateral lista SETOR só quando o setor tem um nome de bairro que
  // signifique algo pra quem lê. Em 83,9% dos municípios do país o IBGE não
  // mapeia bairro (4.677 de 5.572): ali o rótulo virava "Maricá · setor 219",
  // que não diz nada — enquanto os distritos reais (Itaipuaçu, Inoã, Ponta
  // Negra) ficavam de fora. Sem bairro, o ranking mostra as áreas com nome; o
  // MAPA continua no detalhe do setor, que é onde a granularidade importa.
  const rankearPorSetor = effMalha === "setor" && hasBairros;

  // Busca a geometria DISSOLVIDA da malha atual (bairro/distrito) — cacheada no
  // backend (shapely). Só quando estamos num município e a malha ≠ setor.
  useEffect(() => {
    if (view !== "municipio" || effMalha === "setor" || !muniProps?.cd_mun) {
      setMalhaGeo(null);
      setMalhaLoading(false);
      return;
    }
    const cd = String(muniProps.cd_mun);
    let cancelled = false;
    setMalhaGeo(null);
    setMalhaLoading(true);
    api<FC>(`/v1/census/malha?cd_mun=${cd}&level=${effMalha}&v=${CENSUS_V}`)
      .then((fc) => { if (!cancelled) setMalhaGeo(fc); })
      .catch(() => { if (!cancelled) setMalhaGeo(null); })
      .finally(() => { if (!cancelled) setMalhaLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, effMalha, muniProps?.cd_mun]);

  // Série mensal MDS (Bolsa Família/CadÚnico) do município aberto — payload
  // pequeno (dezenas de linhas); falha vira null e a seção some.
  useEffect(() => {
    if (view !== "municipio" || !muniProps?.cd_mun) {
      setMdsSeries(null);
      return;
    }
    let cancelled = false;
    api<{ items: { anomes: string; pbf_valor: number | null; pbf_familias: number | null }[] }>(
      `/v1/census/mds-series?cd_mun=${muniProps.cd_mun}&v=${CENSUS_V}`,
    )
      .then((r) => { if (!cancelled) setMdsSeries(r.items ?? null); })
      .catch(() => { if (!cancelled) setMdsSeries(null); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, muniProps?.cd_mun]);

  // useMemo: sem ele esta IIFE reagregava os ~13k setores A CADA render da
  // página — inclusive a cada tecla digitada na busca de bairro. Idem para
  // destaques/topSetores/areaIndex abaixo.
  const areasAgg = useMemo(() => {
    if (view !== "municipio" || !setores) return [];
    // "Regra da sensibilidade" centralizada em lib/censusAggregate:
    // absolutos somam; médias/taxas são ponderadas — nunca somadas.
    const rows = setores.features.map((f) => ({
      ...f.properties,
      area_key: areaGroupOf(f.properties),
    }));
    return aggregateCensusData(rows, "area_key").map((g) => ({
      nome: g.key,
      pop: g.sums.populacao ?? 0,
      dom: g.sums.domicilios ?? 0,
      area: g.sums.area_km2 ?? 0,
      setores: g.setores,
      alfab: (g.sums.pop_15mais ?? 0) > 0
        ? Number((((g.sums.alfabetizados_15mais ?? 0) / g.sums.pop_15mais!) * 100).toFixed(1))
        : null,
      // Valor do indicador ATUAL do mapa (mesma agregação que colore os
      // polígonos) — pra o ranking acompanhar o indicador, não fixar em pop.
      val:
        mapIndicator === "domicilios" ? (g.sums.domicilios ?? 0)
          : mapIndicator === "densidade_hab_km2" ? (g.derived.densidade_hab_km2 ?? 0)
            : mapIndicator === "media_moradores" ? (g.averages.media_moradores ?? 0)
              : mapIndicator === "taxa_alfabetizacao" ? (g.averages.taxa_alfabetizacao ?? 0)
                : mapIndicator === "pct_pretos_pardos" ? (g.averages.pct_pretos_pardos ?? 0)
                  : mapIndicator === "pct_feminino" ? (g.averages.pct_feminino ?? 0)
                    : mapIndicator === "pct_60mais" ? (g.averages.pct_60mais ?? 0)
                      : mapIndicator === "renda_media" ? (g.averages.renda_media ?? 0)
                        // Cor/raça individual (pct_branca/preta/parda/amarela/indigena):
                        // média ponderada por população, lida direto de g.averages.
                        : mapIndicator.startsWith("pct_")
                          ? ((g.averages as Record<string, number | undefined>)[mapIndicator] ?? 0)
                          : (g.sums.populacao ?? 0),
    }));
    // areaGroupOf depende só de effMalha (função declarada no render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, setores, effMalha, mapIndicator]);
  // Ranking de áreas pelo MESMO indicador do mapa (não fixo em população).
  const topAreas = useMemo(
    () =>
      [...areasAgg]
        .filter((a) => (a.val ?? 0) > 0)
        .sort((a, b) => (b.val ?? 0) - (a.val ?? 0))
        .slice(0, 12),
    [areasAgg],
  );
  // Em modo SETOR o ranking lista os próprios setores pelo indicador do mapa
  // (antes: fixo em população). Setor não tem nome, então rotulamos com o
  // bairro/distrito-pai + o final do código.
  const topSetores = useMemo(
    () =>
      view === "municipio" && setores && effMalha === "setor"
        ? [...setores.features]
            .map((f) => ({ props: f.properties, val: Number(f.properties[mapIndicator] ?? 0) }))
            .filter((s) => s.val > 0)
            .sort((a, b) => b.val - a.val)
            .slice(0, 12)
        : [],
    [view, setores, effMalha, mapIndicator],
  );

  // Agregação por área (nome do bairro/distrito → indicadores). MESMA regra de
  // sensibilidade do lib/censusAggregate (absolutos somam; taxas ponderadas).
  // Reusada pra colorir os polígonos DISSOLVIDOS — sem duplicar fórmula no back.
  const areaAggByName = useMemo(() => {
    const m = new Map<string, Record<string, number | null>>();
    if (view !== "municipio" || effMalha === "setor" || !setores) return m;
    // Cadeia idêntica à do areaGroupOf e à do backend — divergir aqui faria o
    // polígono dissolvido receber o número de outro grupo.
    const groupOf = (p: Record<string, number | string | null>) =>
      effMalha === "distrito"
        ? String(p.nm_dist || "—")
        : areaNome(p);
    const rows = setores.features.map((f) => ({
      ...f.properties,
      area_key: groupOf(f.properties),
    }));
    for (const g of aggregateCensusData(rows, "area_key")) {
      m.set(g.key, {
        populacao: g.sums.populacao ?? null,
        domicilios: g.sums.domicilios ?? null,
        densidade_hab_km2: g.derived.densidade_hab_km2 ?? null,
        media_moradores: g.averages.media_moradores ?? null,
        taxa_alfabetizacao: g.averages.taxa_alfabetizacao ?? null,
        pct_pretos_pardos: g.averages.pct_pretos_pardos ?? null,
        pct_branca: g.averages.pct_branca ?? null,
        pct_preta: g.averages.pct_preta ?? null,
        pct_parda: g.averages.pct_parda ?? null,
        pct_amarela: g.averages.pct_amarela ?? null,
        pct_indigena: g.averages.pct_indigena ?? null,
        pct_feminino: g.averages.pct_feminino ?? null,
        pct_60mais: g.averages.pct_60mais ?? null,
        renda_media: g.averages.renda_media ?? null,
      });
    }
    return m;
  }, [view, effMalha, setores]);

  // Malha bairro/distrito: os POUCOS polígonos dissolvidos (do /census/malha)
  // preenchidos com o agregado da área — em vez de recolorir 13k setores (que
  // travava o browser). `nome` vira nm_mun p/ o tooltip do CensusMap.
  const dissolvedData = useMemo<FC | null>(() => {
    if (view !== "municipio" || effMalha === "setor" || !malhaGeo) return null;
    // Bairro → distrito(s), a partir dos setores já em memória. Os contornos
    // viraram decoração (pointer-events none, fix do clique roubado), então o
    // DISTRITO precisa aparecer no tooltip da própria camada base.
    const distByBairro = new Map<string, Set<string>>();
    if (effMalha === "bairro" && setores) {
      for (const f of setores.features) {
        const p = f.properties;
        const key = areaNome(p);
        const d = String(p.nm_dist ?? "").trim();
        if (!d) continue;
        let set = distByBairro.get(key);
        if (!set) distByBairro.set(key, (set = new Set()));
        set.add(d);
      }
    }
    return {
      type: "FeatureCollection",
      features: malhaGeo.features.map((f) => {
        const nome = String((f.properties as Record<string, unknown> | null)?.nome ?? "—");
        const dists = distByBairro.get(nome);
        return {
          ...f,
          properties: {
            ...f.properties,
            ...(areaAggByName.get(nome) ?? {}),
            nm_mun: nome,
            // Só quando agrega informação (evita "Centro · Distrito: Centro").
            nm_dist:
              dists && dists.size > 0 && !(dists.size === 1 && dists.has(nome))
                ? [...dists].join(" · ")
                : null,
          },
        };
      }),
    };
  }, [view, effMalha, malhaGeo, areaAggByName, setores]);

  // O que vai pro mapa: malha dissolvida (bairro/distrito) ou setor cru. Enquanto
  // a malha carrega, shownData=null → a UI mostra loading (sem freeze); se falhar,
  // cai pros setores (mapData) pra não ficar preso.
  const shownData =
    view === "municipio" && effMalha !== "setor"
      ? dissolvedData ?? (malhaLoading ? null : mapData)
      : mapData;

  // Município cujo desenho de setor ainda não foi carregado (fora de
  // SP/MG/RJ/ES). A resposta chegou e veio vazia — sem distinguir isso de
  // "ainda buscando", os rankings ficavam em "Carregando…" para sempre.
  const semMalhaDeSetor =
    view === "municipio" && !!setores && setores.features.length === 0;

  // Destaques automáticos do município (insights prontos pra campanha).
  const destaques = useMemo(() => {
    if (view !== "municipio" || !setores || areasAgg.length === 0) return null;
    const maisPopuloso = areasAgg[0];
    const candidatos = areasAgg.filter((a) => a.area > 0.05 && a.pop > 0);
    const maisDenso = candidatos.length
      ? candidatos.reduce((best, a) => (a.pop / a.area > best.pop / best.area ? a : best))
      : null;
    let popUrbana = 0, popTotal = 0;
    for (const f of setores.features) {
      const p = Number(f.properties.populacao ?? 0);
      popTotal += p;
      if (String(f.properties.situacao ?? "") === "Urbana") popUrbana += p;
    }
    // Menor alfabetização: só áreas com população relevante (≥ 1.000 hab),
    // senão um vilarejo de 50 pessoas distorce o destaque.
    const comAlfab = areasAgg.filter((a) => a.alfab != null && a.pop >= 1000);
    const menorAlfab = comAlfab.length
      ? comAlfab.reduce((worst, a) => (a.alfab! < worst.alfab! ? a : worst))
      : null;
    return {
      maisPopuloso,
      maisDenso,
      menorAlfab,
      pctUrbana: popTotal > 0 ? Math.round((popUrbana / popTotal) * 100) : null,
    };
  }, [view, setores, areasAgg]);

  // Índice de busca de bairro/distrito (no município): cada nome aponta para o
  // setor mais populoso daquele bairro — clicar dá zoom nele.
  const areaIndex = useMemo(() => {
    if (view !== "municipio" || !setores) return [];
    const m = new Map<string, { props: Record<string, number | string | null>; pop: number }>();
    for (const f of setores.features) {
      const nome = areaNome(f.properties);
      const pop = Number(f.properties.populacao ?? 0);
      const cur = m.get(nome);
      if (!cur || pop > cur.pop) m.set(nome, { props: f.properties, pop });
    }
    return [...m.entries()].map(([nome, v]) => ({ nome, props: v.props }))
      .sort((a, b) => a.nome.localeCompare(b.nome));
  }, [view, setores]);
  const areaMatches = bairroQuery.trim().length >= 1
    ? areaIndex.filter((a) => matchName(a.nome, bairroQuery)).slice(0, 8)
    : [];

  function downloadCsv(lines: string[], filename: string) {
    const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function exportCsv() {
    if (!setores || !muniProps) return;
    const cols = ["cd_setor", "nm_dist", "nm_bairro", "situacao", "populacao",
      "domicilios", "densidade_hab_km2", "media_moradores",
      "taxa_alfabetizacao",
      // Cor/raça: 5 categorias individuais + combinado (compat) — pedido do PO.
      "pct_branca", "pct_preta", "pct_parda", "pct_amarela", "pct_indigena",
      "pct_pretos_pardos", "area_km2"];
    const lines = [cols.join(";")];
    for (const f of setores.features) {
      lines.push(cols.map((c) => {
        const v = f.properties[c];
        return v == null ? "" : String(v).replace(/[;\n]/g, " ");
      }).join(";"));
    }
    downloadCsv(lines, `censo-${slug(String(muniProps.nm_mun))}-setores.csv`);
  }

  function exportCsvEstado() {
    if (!ufGeo) return;
    const cols = ["cd_mun", "nm_mun", "populacao", "domicilios", "setores",
      "media_moradores", "taxa_alfabetizacao",
      // Cor/raça: 5 categorias individuais + combinado (compat) — pedido do PO.
      "pct_branca", "pct_preta", "pct_parda", "pct_amarela", "pct_indigena",
      "pct_pretos_pardos", "pct_urbana",
      "renda_media", "renda_mediana", "pct_bolsa_familia", "pct_cadunico",
      "cadunico_familias", "pbf_familias", "pib_per_capita", "idhm",
      "ideb_anos_iniciais", "ideb_anos_finais", "pct_esgoto_adequado",
      "pct_agua_rede", "pct_lixo_coletado"];
    const lines = [cols.join(";")];
    for (const f of [...ufGeo.features].sort((a, b) =>
      String(a.properties.nm_mun).localeCompare(String(b.properties.nm_mun)))) {
      lines.push(cols.map((c) => {
        const v = f.properties[c];
        return v == null ? "" : String(v).replace(/[;\n]/g, " ");
      }).join(";"));
    }
    downloadCsv(lines, `censo-${slug(UF_NOMES[uf] ?? uf)}-municipios.csv`);
  }

  // Verificando liberação
  if (allowed === null) {
    return (
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-16 flex items-center justify-center text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> carregando…
      </div>
    );
  }

  // Não liberado pelo admin
  if (allowed === false) {
    return (
      <div className="max-w-md mx-auto px-4 sm:px-6 py-16 text-center">
        <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mx-auto mb-4">
          <MapPinned className="w-7 h-7 text-muted-foreground" />
        </div>
        <h1 className="text-xl font-bold">Módulo de Dados Censitários</h1>
        <p className="text-sm text-muted-foreground mt-2">
          Este módulo (dados do IBGE por setor censitário) ainda não está
          liberado para a sua conta. Fale com o administrador do sistema para
          ativá-lo.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 sm:py-8">
      <div className="relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-primary/15 via-card to-card p-5 mn-glow">
        <div className="flex items-start gap-4">
          <div className="shrink-0 w-12 h-12 rounded-xl bg-primary/20 flex items-center justify-center">
            <MapPinned className="w-6 h-6 text-primary" />
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-primary mb-0.5">
              Inteligência Censitária e Socioeconômica · IBGE, INEP, PNUD e MDS
            </p>
            <h1 className="text-2xl font-bold leading-tight">Dados do Censo · {UF_NOMES[uf] ?? uf}</h1>
            <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
              {view === "estado" ? (
                <>Clique num município para abrir os setores censitários (a menor unidade do IBGE).
                Cobertura 100% via distrito: nem todo município tem bairro, mas todos têm distrito.</>
              ) : (
                <>Setores censitários com drill-down por distrito e bairro. Clique num setor para os dados.</>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* Barra de contexto / breadcrumb */}
      <div className="flex items-center gap-3 mt-4 flex-wrap">
        {view === "municipio" && (
          <button
            onClick={backToEstado}
            className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
          >
            <ArrowLeft className="w-4 h-4" /> Voltar ao estado
          </button>
        )}
        <span className="text-sm font-semibold">
          {view === "estado" ? `${UF_NOMES[uf] ?? uf} · ${ufGeo?.features.length ?? "…"} municípios` : String(muniProps?.nm_mun ?? "")}
        </span>

        {/* Indicadores + CSV (visão estadual). No celular a fila de pills
            quebrava em 3-4 linhas e empurrava o mapa pra baixo → abaixo de sm
            vira uma faixa horizontal rolável (mn-scroll) com sangria até a
            borda da página (-mx-4/px-4 casam com o px-4 do container). */}
        {view === "estado" && (
          <div className="flex items-center gap-1.5 flex-nowrap overflow-x-auto mn-scroll w-[calc(100%+2rem)] -mx-4 px-4 pb-1 sm:w-auto sm:mx-0 sm:ml-auto sm:px-0 sm:pb-0 sm:flex-wrap sm:overflow-visible">
            {ufsDisponiveis.length > 1 && (
              <select
                value={uf}
                onChange={(e) => setUf(e.target.value)}
                className="shrink-0 py-1.5 px-2 rounded-md border border-border bg-card text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
                title="Trocar estado"
              >
                {ufsDisponiveis.map((u) => (
                  <option key={u} value={u}>{UF_NOMES[u] ?? u}</option>
                ))}
              </select>
            )}
            {stateIndicators.map((i) => (
              <button
                key={i.key}
                onClick={() => setIndicator(i.key)}
                title={STATE_INDICATOR_HINTS[i.key]}
                className={`shrink-0 py-1.5 px-2.5 rounded-md border text-xs transition-colors ${
                  mapIndicator === i.key
                    ? "border-primary bg-primary/10 text-primary font-semibold"
                    : "border-border bg-card hover:border-primary/50"
                }`}
              >
                {i.label}
              </button>
            ))}
            <button
              onClick={exportCsvEstado}
              disabled={!ufGeo}
              title={`Baixar os ${ufGeo?.features.length ?? ""} municípios em CSV`}
              className="shrink-0 py-1.5 px-2.5 rounded-md border border-border bg-card hover:border-primary/60 text-xs inline-flex items-center gap-1.5 disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" /> CSV
            </button>
          </div>
        )}

        {/* Busca de município (visão estadual) */}
        {view === "estado" && (
          <div className="relative w-full sm:w-72">
            <input
              value={muniQuery}
              onChange={(e) => setMuniQuery(e.target.value)}
              placeholder="Buscar município…"
              className="w-full py-1.5 px-3 rounded-md bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            {muniMatches.length > 0 && (
              <ul className="absolute z-[500] mt-1 w-full rounded-md border border-border bg-card shadow-lg max-h-64 overflow-auto divide-y divide-border">
                {muniMatches.map((f) => (
                  <li key={String(f.properties.cd_mun)}>
                    <button
                      onClick={() => { openMunicipio(f.properties); setMuniQuery(""); }}
                      className="w-full text-left px-3 py-2 hover:bg-accent/40 transition-colors text-sm"
                    >
                      <span className="font-medium">{String(f.properties.nm_mun)}</span>
                      <span className="text-[11px] text-muted-foreground ml-2">
                        {numberFmt.format(Number(f.properties.populacao ?? 0))} hab
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Malha + dicionário/variáveis + export (visão município) */}
        {view === "municipio" && (
          <div className="flex flex-col gap-1.5 ml-auto items-end">
            {/* Malha (nível geográfico) */}
            <div className="flex gap-1.5 items-center flex-wrap justify-end">
              <span className="text-[11px] text-muted-foreground mr-0.5">Malha:</span>
              {(["setor", "distrito", "bairro"] as Malha[]).map((m) => {
                const disabled = m === "bairro" && !hasBairros;
                return (
                  <button
                    key={m}
                    onClick={() => { if (!disabled) { userPickedMalha.current = true; setMalha(m); } }}
                    disabled={disabled}
                    title={
                      disabled
                        ? "Este município não tem bairros mapeados no Censo — use Distrito."
                        : `Colorir o mapa por ${m}`
                    }
                    className={`py-1 px-2.5 rounded-md border text-xs capitalize transition-colors ${
                      effMalha === m
                        ? "border-primary bg-primary/10 text-primary font-semibold"
                        : disabled
                          ? "border-border bg-card opacity-40 cursor-not-allowed"
                          : "border-border bg-card hover:border-primary/50"
                    }`}
                  >
                    {m}
                  </button>
                );
              })}
              <button
                onClick={exportCsv}
                disabled={!setores}
                title="Baixar os setores deste município em CSV"
                className="py-1 px-2.5 rounded-md border border-border bg-card hover:border-primary/60 text-xs inline-flex items-center gap-1.5 disabled:opacity-50"
              >
                <Download className="w-3.5 h-3.5" /> CSV
              </button>
            </div>
            {/* Dicionário + variáveis (a lista de variáveis muda com o dicionário) */}
            <div className="flex gap-1.5 items-center flex-wrap justify-end">
              <select
                value={selectedDict}
                onChange={(e) => {
                  setSelectedDict(e.target.value);
                  const d = DICTIONARIES.find((x) => x.key === e.target.value);
                  const first = d?.vars.find((v) => !v.disabled);
                  if (first) setIndicator(first.key);
                }}
                title="Dicionário de variáveis"
                className="py-1 px-2 rounded-md border border-border bg-card text-xs focus:outline-none focus:border-primary/60"
              >
                {DICTIONARIES.map((d) => (
                  <option key={d.key} value={d.key}>
                    {d.label}
                  </option>
                ))}
              </select>
              {(DICTIONARIES.find((d) => d.key === selectedDict)?.vars ?? []).map((v) => (
                <button
                  key={v.label}
                  onClick={() => !v.disabled && setIndicator(v.key)}
                  disabled={v.disabled}
                  title={INDICATOR_TOOLTIP[v.key] ?? v.note ?? `Colorir por ${v.label}`}
                  className={`py-1 px-2.5 rounded-md border text-xs transition-colors ${
                    v.disabled
                      ? "border-dashed border-border bg-card opacity-50 cursor-help"
                      : indicator === v.key
                        ? "border-primary bg-primary/10 text-primary font-semibold"
                        : "border-border bg-card hover:border-primary/50"
                  }`}
                >
                  {v.label}
                  {v.disabled && <Lock className="w-3.5 h-3.5 inline ml-1 text-primary/80" aria-hidden="true" />}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Busca de bairro/distrito (visão município) */}
      {view === "municipio" && (
        <div className="relative mt-3 w-full sm:w-96">
          <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={bairroQuery}
            onChange={(e) => setBairroQuery(e.target.value)}
            placeholder={`Buscar bairro ou distrito em ${muniProps?.nm_mun ?? ""}…`}
            className="w-full py-2 pl-9 pr-3 rounded-lg bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          {areaMatches.length > 0 && (
            <ul className="absolute z-[500] mt-1 w-full rounded-lg border border-border bg-card shadow-xl max-h-64 overflow-auto divide-y divide-border">
              {areaMatches.map((a) => (
                <li key={a.nome}>
                  <button
                    onClick={() => openArea(a.nome)}
                    className="w-full text-left px-3 py-2 hover:bg-accent/40 transition-colors text-sm flex items-center justify-between gap-2"
                  >
                    <span className="truncate">{prettyName(a.nome)}</span>
                    <span className="text-[11px] text-muted-foreground shrink-0">
                      {a.props.nm_bairro ? "bairro" : "distrito"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Destaques automáticos (visão município) */}
      {view === "municipio" && destaques && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => openArea(destaques.maisPopuloso.nome)}
            className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/[0.07] hover:bg-primary/15 px-3 py-1.5 text-xs transition-colors"
            title="Clique para destacar no mapa"
          >
            <Trophy className="w-3.5 h-3.5 inline text-primary/80" aria-hidden="true" />
            <span className="text-muted-foreground">{hasBairros ? "Bairro" : "Distrito"} mais populoso:</span>
            <span className="font-semibold">{prettyName(destaques.maisPopuloso.nome)}</span>
            <span className="text-primary font-bold tabular-nums">{numberFmt.format(destaques.maisPopuloso.pop)}</span>
          </button>
          {destaques.maisDenso && (
            <button
              onClick={() => openArea(destaques.maisDenso!.nome)}
              className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/[0.07] hover:bg-primary/15 px-3 py-1.5 text-xs transition-colors"
              title="Clique para destacar no mapa"
            >
              <Flame className="w-3.5 h-3.5 inline text-primary/80" aria-hidden="true" />
              <span className="text-muted-foreground">Mais denso:</span>
              <span className="font-semibold">{prettyName(destaques.maisDenso.nome)}</span>
              <span className="text-primary font-bold tabular-nums">
                {numberFmt.format(Math.round(destaques.maisDenso.pop / destaques.maisDenso.area))} hab/km²
              </span>
            </button>
          )}
          {destaques.menorAlfab && (
            <button
              onClick={() => openArea(destaques.menorAlfab!.nome)}
              className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/[0.07] hover:bg-primary/15 px-3 py-1.5 text-xs transition-colors"
              title="Área prioritária para ação social — clique para destacar no mapa"
            >
              <BookOpen className="w-3.5 h-3.5 inline text-primary/80" aria-hidden="true" />
              <span className="text-muted-foreground">Menor alfabetização:</span>
              <span className="font-semibold">{prettyName(destaques.menorAlfab.nome)}</span>
              <span className="text-primary font-bold tabular-nums">
                {String(destaques.menorAlfab.alfab).replace(".", ",")}%
              </span>
            </button>
          )}
          {destaques.pctUrbana != null && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs">
              <Building2 className="w-3.5 h-3.5 inline text-primary/80" aria-hidden="true" />
              <span className="text-muted-foreground">População urbana:</span>
              <span className="font-bold tabular-nums">{destaques.pctUrbana}%</span>
            </span>
          )}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
        {view === "estado" && ufTotals ? (
          <>
            <Stat icon={<Users className="w-4 h-4" />} label={`População ${UF_NOMES[uf] ?? uf}`} value={numberFmt.format(ufTotals.pop)} />
            <Stat icon={<Building2 className="w-4 h-4" />} label="Domicílios" value={numberFmt.format(ufTotals.dom)} />
            <Stat icon={<Layers className="w-4 h-4" />} label="Setores" value={numberFmt.format(ufTotals.setores)} />
            <Stat icon={<MapPin className="w-4 h-4" />} label="Municípios" value={String(ufGeo?.features.length ?? 0)} />
          </>
        ) : muniProps ? (
          <>
            <Stat icon={<Users className="w-4 h-4" />} label="População" value={numberFmt.format(Number(muniProps.populacao ?? 0))} />
            <Stat icon={<Building2 className="w-4 h-4" />} label="Domicílios" value={numberFmt.format(Number(muniProps.domicilios ?? 0))} />
            <Stat icon={<Layers className="w-4 h-4" />} label="Setores" value={numberFmt.format(Number(muniProps.setores ?? 0))} />
            <Stat icon={<MapPin className="w-4 h-4" />} label="Município" value={String(muniProps.nm_mun ?? "")} />
          </>
        ) : null}
      </div>

      {/* Dica de uso — linguagem simples */}
      <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground flex items-center gap-2 flex-wrap">
        <span className="text-primary font-semibold">Como usar:</span>
        {view === "estado" ? (
          <span>passe o mouse para ver os números de cada município · <b>clique</b> para abrir os setores dele.</span>
        ) : (
          <span>cada área é um setor censitário · passe o mouse para ver os números · <b>clique</b> para os detalhes no painel ao lado.</span>
        )}
      </div>

      {/* Mapa + painel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-3">
        <div className="lg:col-span-2 rounded-2xl overflow-hidden border border-border/60 ring-1 ring-white/5 shadow-2xl shadow-black/40 relative h-[52vh] sm:h-[58vh] lg:h-[62vh]">
          {view === "municipio" && !loading && shownData && (
            <div className="absolute top-2 left-2 z-[500] rounded-lg bg-black/75 backdrop-blur-md border border-white/10 px-2.5 py-1.5 text-[11px] text-white shadow-lg">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showContours}
                  onChange={(e) => setShowContours(e.target.checked)}
                  className="accent-sky-400"
                />
                <span className="inline-flex items-center gap-1">
                  Contornos de bairro/distrito
                  {contoursLoading && <Loader2 className="w-3 h-3 animate-spin" />}
                </span>
              </label>
              {showContours && (
                <div className="mt-1 flex items-center gap-2 text-[10px] text-white/70">
                  <span className="inline-flex items-center gap-1">
                    <span className="w-3 h-0.5 bg-sky-400 inline-block" /> bairro
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="w-3 border-t-2 border-dashed border-amber-400 inline-block" /> distrito
                  </span>
                </div>
              )}
            </div>
          )}
          {loading || !shownData ? (
            <div className="h-full w-full flex flex-col items-center justify-center text-muted-foreground gap-2 px-6 text-center">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <p className="text-sm">
                {view === "municipio" && muniProps?.setores
                  ? `Carregando ${numberFmt.format(Number(muniProps.setores))} setores de ${muniProps.nm_mun}…`
                  : "Carregando o mapa do estado…"}
              </p>
              {view === "municipio" && Number(muniProps?.setores ?? 0) > 5000 && (
                <p className="text-[11px] opacity-70">
                  Cidade grande: pode levar alguns segundos no primeiro carregamento.
                </p>
              )}
            </div>
          ) : shownData.features.length === 0 ? (
            // Município sem malha de SETOR (carga nacional trouxe os números do
            // país, mas o desenho dos setores só existe em SP/MG/RJ/ES). Sem
            // este ramo o mapa ficava no enquadramento anterior e exibia OUTRA
            // região — clicar num município da Bahia mostrava a serra do Rio.
            <div className="h-full w-full flex flex-col items-center justify-center gap-2 px-8 text-center">
              <MapPin className="w-7 h-7 text-muted-foreground/60" />
              <p className="text-sm font-medium">
                Mapa por setor ainda não disponível em {muniProps?.nm_mun ?? "este município"}
              </p>
              <p className="text-xs text-muted-foreground max-w-sm">
                Os números do Censo abaixo estão completos. O desenho dos setores
                censitários está carregado hoje em São Paulo, Minas Gerais,
                Rio de Janeiro e Espírito Santo.
              </p>
              <button
                onClick={backToEstado}
                className="mt-1 text-xs px-3 py-1.5 rounded-md border border-border hover:border-primary/60 hover:bg-accent/40 transition-colors"
              >
                Voltar ao mapa do estado
              </button>
            </div>
          ) : (
            <CensusMap
              data={shownData}
              indicator={mapIndicator}
              onSelect={view === "estado" ? openMunicipio : onMapSelect}
              focusIds={view === "municipio" ? focusIds : null}
              dataVersion={view === "municipio" ? effMalha : "estado"}
              bairroContours={view === "municipio" && showContours ? contourBairro : null}
              distritoContours={view === "municipio" && showContours ? contourDistrito : null}
            />
          )}
        </div>

        <div className="rounded-2xl border border-border/60 bg-gradient-to-b from-card to-background/30 ring-1 ring-white/[0.03] shadow-xl shadow-black/20 p-4">
          {view === "estado" ? (
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5" /> Top 10 municípios · {indicatorShortLabel(mapIndicator)}
              </p>
              {topMunicipios.length === 0 ? (
                <p className="text-sm text-muted-foreground py-6 text-center">
                  Sem dados deste indicador para os municípios desta UF.
                </p>
              ) : (
                <ul className="space-y-2">
                  {topMunicipios.map((m, i) => {
                    const max = topMunicipios[0]?.val || 1;
                    return (
                      <li key={m.cd}>
                        <button
                          onClick={() => openMunicipio(m.props)}
                          className="w-full text-left group"
                        >
                          <div className="flex items-center justify-between gap-2 text-sm">
                            <span className="truncate group-hover:text-primary transition-colors">
                              <span className="text-primary font-bold text-xs mr-1.5">{i + 1}º</span>
                              {m.nome}
                            </span>
                            <span className="font-mono text-xs shrink-0 tabular-nums">{INDICATOR_FMT[mapIndicator](m.val)}</span>
                          </div>
                          <div className="mt-1.5 h-2 rounded-full bg-muted/50 overflow-hidden ring-1 ring-white/[0.03]">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-amber-300 via-primary to-amber-500 shadow-[0_0_10px_rgba(232,200,121,0.4)] transition-[width] duration-500"
                              style={{ width: `${(m.val / max) * 100}%` }}
                            />
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              <p className="text-[11px] text-muted-foreground mt-3 pt-3 border-t border-border">
                Clique num município (aqui ou no mapa) para abrir os setores.
              </p>
            </div>
          ) : selArea ? (
            <div className="mn-fade-in">
              {/* Trilha geográfica clicável: Estado › Município › Bairro */}
              <nav aria-label="Navegação geográfica" className="flex items-center gap-1 flex-wrap text-[11px] text-muted-foreground mb-2">
                <button onClick={backToEstado} className="hover:text-primary hover:underline transition-colors">
                  {UF_NOMES[uf] ?? uf}
                </button>
                <span className="opacity-50">›</span>
                <button onClick={clearToMunicipio} className="hover:text-primary hover:underline transition-colors">
                  {String(muniProps?.nm_mun ?? "")}
                </button>
                <span className="opacity-50">›</span>
                <span className="text-foreground font-medium truncate max-w-[150px]">{prettyName(selArea.nome)}</span>
              </nav>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-primary/15 text-primary uppercase tracking-wide">
                  {selArea.kind}
                </span>
                <button
                  onClick={navUp}
                  className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-primary transition-colors"
                >
                  <ArrowLeft className="w-3 h-3" /> Voltar
                </button>
              </div>
              <p className="text-lg font-bold leading-tight mt-1">{prettyName(selArea.nome)}</p>
              <p className="text-[11px] text-muted-foreground">{muniProps?.nm_mun} · {selArea.setores} setores</p>
              <div className="grid grid-cols-2 gap-2 mt-3">
                <div className="rounded-xl border border-primary/20 bg-gradient-to-br from-primary/10 to-transparent p-3 text-center ring-1 ring-primary/10">
                  <p className="text-2xl font-bold text-primary tabular-nums tracking-tight">{numberFmt.format(selArea.pop)}</p>
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">habitantes</p>
                </div>
                <div className="rounded-xl border border-border/70 bg-gradient-to-br from-card to-background/40 p-3 text-center ring-1 ring-white/[0.03]">
                  <p className="text-2xl font-bold tabular-nums tracking-tight">{numberFmt.format(selArea.dom)}</p>
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">domicílios</p>
                </div>
              </div>
              <DetalheIndicadores
                mode={valueMode}
                onMode={setValueMode}
                v={(() => {
                  const ex = demogExtras(selArea.sums, selArea.pop);
                  return {
                    dens: selArea.dens, media: selArea.media, alfab: selArea.alfab, area: selArea.area,
                    raca: [
                      { label: "Branca", pct: selArea.branca, n: selArea.nBranca },
                      { label: "Preta", pct: selArea.preta, n: selArea.nPreta },
                      { label: "Parda", pct: selArea.parda, n: selArea.nParda },
                      { label: "Amarela", pct: selArea.amarela, n: selArea.nAmarela },
                      { label: "Indígena", pct: selArea.indigena, n: selArea.nIndigena },
                    ],
                    mulheres: { pct: selArea.pctFem, n: selArea.nFem },
                    idoso: { pct: selArea.pct60, n: selArea.n60 },
                    homens: ex.homens,
                    alfabN: selArea.nAlfab,
                    faixas: ex.faixas,
                    saneamento: ex.saneamento,
                  };
                })()}
              />
              <p className="text-[11px] text-muted-foreground mt-3 pt-3 border-t border-border">
                Destacado no mapa. Clique num setor para o detalhe individual.
              </p>
            </div>
          ) : sel ? (
            <div className="mn-fade-in">
              {/* Trilha geográfica clicável: Estado › Município › Bairro › Setor */}
              <nav aria-label="Navegação geográfica" className="flex items-center gap-1 flex-wrap text-[11px] text-muted-foreground mb-2">
                <button onClick={backToEstado} className="hover:text-primary hover:underline transition-colors">
                  {UF_NOMES[uf] ?? uf}
                </button>
                <span className="opacity-50">›</span>
                <button onClick={clearToMunicipio} className="hover:text-primary hover:underline transition-colors">
                  {String(muniProps?.nm_mun ?? "")}
                </button>
                {(() => {
                  const areaDoSetor = sel.nm_bairro || sel.nm_subdist ? areaNome(sel) : "";
                  return areaDoSetor && areaDoSetor !== "—" ? (
                    <>
                      <span className="opacity-50">›</span>
                      <button
                        onClick={() => openArea(areaDoSetor)}
                        className="hover:text-primary hover:underline transition-colors truncate max-w-[120px]"
                      >
                        {prettyName(areaDoSetor)}
                      </button>
                    </>
                  ) : null;
                })()}
                <span className="opacity-50">›</span>
                <span className="text-foreground font-medium">Setor</span>
              </nav>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-primary/15 text-primary uppercase tracking-wide">
                  Setor censitário
                </span>
                {sel.situacao ? (
                  <span className="text-[10px] text-muted-foreground">{String(sel.situacao)}</span>
                ) : null}
                <button
                  onClick={navUp}
                  className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground hover:text-primary transition-colors"
                >
                  <ArrowLeft className="w-3 h-3" /> Voltar
                </button>
              </div>
              <p className="text-base font-bold leading-tight">
                {prettyName(String(sel.nm_dist ?? "—"))}
                {sel.nm_bairro ? <span className="text-muted-foreground font-normal"> · {prettyName(String(sel.nm_bairro))}</span> : null}
              </p>
              <p className="font-mono text-[11px] text-muted-foreground mt-0.5">{String(sel.cd_setor)}</p>

              <div className="grid grid-cols-2 gap-2 mt-3">
                <div className="rounded-xl border border-primary/20 bg-gradient-to-br from-primary/10 to-transparent p-3 text-center ring-1 ring-primary/10">
                  <p className="text-2xl font-bold text-primary tabular-nums tracking-tight">{numberFmt.format(Number(sel.populacao ?? 0))}</p>
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">habitantes</p>
                </div>
                <div className="rounded-xl border border-border/70 bg-gradient-to-br from-card to-background/40 p-3 text-center ring-1 ring-white/[0.03]">
                  <p className="text-2xl font-bold tabular-nums tracking-tight">{numberFmt.format(Number(sel.domicilios ?? 0))}</p>
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">domicílios</p>
                </div>
              </div>

              {Number(sel.populacao ?? 0) === 0 && (
                <p className="mt-2 text-[11px] text-muted-foreground bg-muted/40 rounded-md px-2 py-1.5">
                  Setor sem população residente: costuma ser área não residencial
                  (parque, indústria, área militar, porto etc.).
                </p>
              )}

              <DetalheIndicadores
                mode={valueMode}
                onMode={setValueMode}
                v={(() => {
                  const ex = demogExtras(sel, Number(sel.populacao ?? 0));
                  return {
                    dens: sel.densidade_hab_km2, media: sel.media_moradores,
                    alfab: sel.taxa_alfabetizacao, area: sel.area_km2,
                    raca: [
                      { label: "Branca", pct: sel.pct_branca, n: sel.raca_branca },
                      { label: "Preta", pct: sel.pct_preta, n: sel.raca_preta },
                      { label: "Parda", pct: sel.pct_parda, n: sel.raca_parda },
                      { label: "Amarela", pct: sel.pct_amarela, n: sel.raca_amarela },
                      { label: "Indígena", pct: sel.pct_indigena, n: sel.raca_indigena },
                    ],
                    mulheres: { pct: sel.pct_feminino, n: sel.sexo_feminino },
                    idoso: { pct: sel.pct_60mais, n: sel.idade_60mais },
                    homens: ex.homens,
                    alfabN: sel.alfabetizados_15mais,
                    faixas: ex.faixas,
                    saneamento: ex.saneamento,
                  };
                })()}
              />
            </div>
          ) : (
            <div>
              <nav aria-label="Navegação geográfica" className="flex items-center gap-1 flex-wrap text-[11px] text-muted-foreground mb-2">
                <button onClick={backToEstado} className="hover:text-primary hover:underline transition-colors">
                  {UF_NOMES[uf] ?? uf}
                </button>
                <span className="opacity-50">›</span>
                <span className="text-foreground font-medium">{String(muniProps?.nm_mun ?? "")}</span>
              </nav>
              <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5" /> {rankearPorSetor ? "Setores" : areaKind} por {indicatorShortLabel(mapIndicator)}
              </p>
              {rankearPorSetor ? (
                topSetores.length > 0 ? (
                  <ul className="space-y-2">
                    {topSetores.map((s, i) => {
                      const max = topSetores[0]?.val || 1;
                      const parent = prettyName(areaNome(s.props).replace("—", ""));
                      const code = String(s.props.cd_setor ?? "").slice(-3);
                      return (
                        <li key={String(s.props.cd_setor)}>
                          <button onClick={() => onSetorClick(s.props)} className="w-full text-left group">
                            <div className="flex items-center justify-between gap-2 text-sm">
                              <span className="truncate group-hover:text-primary transition-colors">
                                <span className="text-primary font-bold text-xs mr-1.5">{i + 1}º</span>
                                {parent ? `${parent} · setor ${code}` : `Setor ${code}`}
                              </span>
                              <span className="font-mono text-xs shrink-0 tabular-nums">
                                {INDICATOR_FMT[mapIndicator](s.val)}
                              </span>
                            </div>
                            <div className="mt-1.5 h-2 rounded-full bg-muted/50 overflow-hidden ring-1 ring-white/[0.03]">
                              <div
                                className="h-full rounded-full bg-gradient-to-r from-amber-300 via-primary to-amber-500 shadow-[0_0_10px_rgba(232,200,121,0.4)] transition-[width] duration-500"
                                style={{ width: `${(s.val / max) * 100}%` }}
                              />
                            </div>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">
                  {semMalhaDeSetor
                    ? "Ranking por setor indisponível neste estado — os números do município estão logo abaixo."
                    : "Carregando…"}
                </p>
                )
              ) : topAreas.length > 0 ? (
                <ul className="space-y-2">
                  {topAreas.map((d, i) => {
                    const max = topAreas[0]?.val || 1;
                    return (
                      <li key={d.nome}>
                        <button onClick={() => openArea(d.nome)} className="w-full text-left group">
                          <div className="flex items-center justify-between gap-2 text-sm">
                            <span className="truncate group-hover:text-primary transition-colors">
                              <span className="text-primary font-bold text-xs mr-1.5">{i + 1}º</span>
                              {prettyName(d.nome)}
                            </span>
                            <span className="font-mono text-xs shrink-0 tabular-nums">
                              {INDICATOR_FMT[mapIndicator](d.val)}
                            </span>
                          </div>
                          <div className="mt-1.5 h-2 rounded-full bg-muted/50 overflow-hidden ring-1 ring-white/[0.03]">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-amber-300 via-primary to-amber-500 shadow-[0_0_10px_rgba(232,200,121,0.4)] transition-[width] duration-500"
                              style={{ width: `${(d.val / max) * 100}%` }}
                            />
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-0.5">{d.setores} setores</p>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {semMalhaDeSetor
                    ? "Ranking por setor indisponível neste estado — os números do município estão logo abaixo."
                    : "Carregando…"}
                </p>
              )}
              {/* Distribuição etária (Censo 2022) — o dado já viaja no payload
                  do uf-overview (faixa_etaria por município); antes a UI só
                  usava o recorte 60+. Barras nativas (estilo "barras de força"
                  do app) — zero dependência nova. */}
              {(() => {
                const fx = muniProps?.faixa_etaria as Record<string, number | null> | null | undefined;
                if (!fx) return null;
                const FAIXAS: [string, string][] = [
                  ["0_4", "0–4"], ["5_9", "5–9"], ["10_14", "10–14"],
                  ["15_19", "15–19"], ["20_24", "20–24"], ["25_29", "25–29"],
                  ["30_39", "30–39"], ["40_49", "40–49"], ["50_59", "50–59"],
                  ["60_69", "60–69"], ["70_mais", "70+"],
                ];
                const vals = FAIXAS.map(([k, label]) => ({ label, v: Number(fx[k] ?? 0) }));
                const total = vals.reduce((s, x) => s + x.v, 0);
                if (total <= 0) return null;
                const max = Math.max(...vals.map((x) => x.v));
                return (
                  <div className="mt-4 pt-3 border-t border-border">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
                      Distribuição etária · Censo 2022
                    </p>
                    <ul className="space-y-1">
                      {vals.map((x) => (
                        <li key={x.label} className="flex items-center gap-2 text-[11px]">
                          <span className="w-10 shrink-0 text-muted-foreground tabular-nums">{x.label}</span>
                          <div className="flex-1 h-2 rounded-full bg-muted/50 overflow-hidden ring-1 ring-white/[0.03]">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-amber-300 via-primary to-amber-500"
                              style={{ width: `${(x.v / max) * 100}%` }}
                            />
                          </div>
                          <span className="w-12 shrink-0 text-right font-mono tabular-nums text-muted-foreground">
                            {((x.v / total) * 100).toFixed(1)}%
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })()}
              {/* Bolsa Família — série mensal do MDS (valor repassado). Antes o
                  app só mostrava o % do mês mais recente; a série e o VALOR
                  (argumento de palanque: "R$ X mi entram na cidade por mês")
                  ficavam invisíveis. */}
              {(() => {
                const serie = (mdsSeries ?? []).filter((x) => x.pbf_valor != null).slice(-24);
                if (serie.length === 0) return null;
                const last = serie[serie.length - 1];
                const maxV = Math.max(...serie.map((x) => x.pbf_valor ?? 0));
                const fmtMes = (am: string) => `${am.slice(4)}/${am.slice(2, 4)}`;
                const fmtMi = (v: number) =>
                  v >= 1e6 ? `R$ ${(v / 1e6).toFixed(1).replace(".", ",")} mi` : `R$ ${Math.round(v / 1e3)} mil`;
                return (
                  <div className="mt-4 pt-3 border-t border-border">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
                      Bolsa Família · repasse mensal (MDS)
                    </p>
                    <p className="text-lg font-bold text-emerald-700 dark:text-emerald-400">
                      {fmtMi(last.pbf_valor!)}
                      <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">
                        em {fmtMes(last.anomes)}
                        {last.pbf_familias != null &&
                          ` · ${numberFmt.format(last.pbf_familias)} famílias`}
                      </span>
                    </p>
                    {serie.length > 1 && (
                      <div className="mt-1.5 flex items-end gap-[2px] h-9" title="Série mensal do valor repassado">
                        {serie.map((x) => (
                          <div
                            key={x.anomes}
                            className="flex-1 rounded-sm bg-emerald-600/70 dark:bg-emerald-400/60 min-h-[2px]"
                            style={{ height: `${Math.max(4, ((x.pbf_valor ?? 0) / maxV) * 100)}%` }}
                            title={`${fmtMes(x.anomes)} · ${fmtMi(x.pbf_valor!)}`}
                          />
                        ))}
                      </div>
                    )}
                    {serie.length <= 2 && (
                      <p className="text-[10px] text-muted-foreground mt-1">
                        Série completa após o backfill mensal do MDS.
                      </p>
                    )}
                  </div>
                );
              })()}
              <p className="text-[11px] text-muted-foreground mt-3 pt-3 border-t border-border">
                Clique num setor no mapa para ver os dados detalhados.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Comparador de municípios (visão estadual) */}
      {view === "estado" && ufGeo && (
        <div className="mt-4 rounded-2xl border border-border/60 bg-gradient-to-b from-card to-background/30 ring-1 ring-white/[0.03] p-5">
          <p className="font-semibold flex items-center gap-2 mb-3">
            <Layers className="w-4 h-4 text-primary" /> Comparar municípios
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {([["A", cmpA, setCmpA, cmpQA, setCmpQA], ["B", cmpB, setCmpB, cmpQB, setCmpQB]] as const).map(
              ([lbl, val, setVal, q, setQ]) => {
                const muni = ufGeo.features.find((f) => String(f.properties.cd_mun) === val);
                const matches = q.trim().length >= 2
                  ? ufGeo.features.filter((f) => matchName(String(f.properties.nm_mun ?? ""), q)).slice(0, 6)
                  : [];
                return (
                  <div key={lbl} className="relative">
                    <label className="text-[11px] uppercase tracking-wider text-muted-foreground">Município {lbl}</label>
                    {muni ? (
                      <div className="mt-1 flex items-center justify-between gap-2 rounded-lg border border-primary/30 bg-primary/[0.06] px-3 py-2">
                        <span className="font-semibold text-sm truncate">{String(muni.properties.nm_mun)}</span>
                        <button onClick={() => { setVal(null); setQ(""); }} className="text-xs text-muted-foreground hover:text-foreground shrink-0">trocar</button>
                      </div>
                    ) : (
                      <>
                        <input
                          value={q}
                          onChange={(e) => setQ(e.target.value)}
                          placeholder="Buscar município…"
                          className="w-full mt-1 py-2 px-3 rounded-lg bg-background border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                        />
                        {matches.length > 0 && (
                          <ul className="absolute z-[500] mt-1 w-full rounded-lg border border-border bg-card shadow-xl max-h-56 overflow-auto divide-y divide-border">
                            {matches.map((f) => (
                              <li key={String(f.properties.cd_mun)}>
                                <button
                                  onClick={() => { setVal(String(f.properties.cd_mun)); setQ(""); }}
                                  className="w-full text-left px-3 py-2 hover:bg-accent/40 text-sm"
                                >
                                  {String(f.properties.nm_mun)}
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </>
                    )}
                  </div>
                );
              },
            )}
          </div>

          {cmpA && cmpB && (() => {
            const fa = ufGeo.features.find((f) => String(f.properties.cd_mun) === cmpA)?.properties;
            const fb = ufGeo.features.find((f) => String(f.properties.cd_mun) === cmpB)?.properties;
            if (!fa || !fb) return null;
            const pctFmt = (v: number) => `${String(v).replace(".", ",")}%`;
            type CmpRow = [string, number | null, number | null, (v: number) => string];
            // Indicadores agrupados por tema (antes era uma tabela plana única).
            // Mesmos dados do uf-overview; muda só a apresentação: barras
            // espelhadas a partir do centro, proporcionais ao max(A, B).
            const grupos: { label: string; rows: CmpRow[] }[] = [
              {
                label: "Perfil",
                rows: [
                  ["População", Number(fa.populacao ?? 0), Number(fb.populacao ?? 0), (v) => numberFmt.format(v)],
                  ["Domicílios", Number(fa.domicilios ?? 0), Number(fb.domicilios ?? 0), (v) => numberFmt.format(v)],
                  ["Setores censitários", Number(fa.setores ?? 0), Number(fb.setores ?? 0), (v) => numberFmt.format(v)],
                  ["Moradores/domicílio", fa.media_moradores as number | null, fb.media_moradores as number | null, (v) => String(v).replace(".", ",")],
                  ["População urbana (%)", fa.pct_urbana as number | null, fb.pct_urbana as number | null, pctFmt],
                  ["IDHM (2010)", fa.idhm as number | null, fb.idhm as number | null, (v) => v.toFixed(3).replace(".", ",")],
                ],
              },
              {
                // Cor/raça DESDOBRADA nas 5 categorias individuais do Censo 2022
                // (pedido do PO — mesma regra do painel de clique do bairro).
                // O uf-overview devolve os pct_* por município desde o ef41945.
                label: "Cor ou raça",
                rows: [
                  ["Branca (%)", fa.pct_branca as number | null, fb.pct_branca as number | null, pctFmt],
                  ["Preta (%)", fa.pct_preta as number | null, fb.pct_preta as number | null, pctFmt],
                  ["Parda (%)", fa.pct_parda as number | null, fb.pct_parda as number | null, pctFmt],
                  ["Amarela (%)", fa.pct_amarela as number | null, fb.pct_amarela as number | null, pctFmt],
                  ["Indígena (%)", fa.pct_indigena as number | null, fb.pct_indigena as number | null, pctFmt],
                ],
              },
              {
                label: "Renda",
                rows: [
                  ["Renda média domiciliar (R$)", fa.renda_media as number | null, fb.renda_media as number | null, (v) => `R$ ${numberFmt.format(Math.round(v))}`],
                  ["Renda mediana domiciliar (R$)", fa.renda_mediana as number | null, fb.renda_mediana as number | null, (v) => `R$ ${numberFmt.format(Math.round(v))}`],
                  ["Bolsa Família (% domicílios)", fa.pct_bolsa_familia as number | null, fb.pct_bolsa_familia as number | null, pctFmt],
                  ["CadÚnico (% domicílios)", fa.pct_cadunico as number | null, fb.pct_cadunico as number | null, pctFmt],
                  ["PIB per capita (R$)", fa.pib_per_capita as number | null, fb.pib_per_capita as number | null, (v) => `R$ ${numberFmt.format(Math.round(v))}`],
                ],
              },
              {
                label: "Educação",
                rows: [
                  ["Alfabetização 15+ (%)", fa.taxa_alfabetizacao as number | null, fb.taxa_alfabetizacao as number | null, pctFmt],
                  ["IDEB anos iniciais (2023)", fa.ideb_anos_iniciais as number | null, fb.ideb_anos_iniciais as number | null, (v) => v.toFixed(1).replace(".", ",")],
                  ["IDEB anos finais (2023)", fa.ideb_anos_finais as number | null, fb.ideb_anos_finais as number | null, (v) => v.toFixed(1).replace(".", ",")],
                ],
              },
              {
                label: "Saneamento",
                rows: [
                  ["Esgoto adequado (% domic.)", fa.pct_esgoto_adequado as number | null, fb.pct_esgoto_adequado as number | null, pctFmt],
                  ["Água por rede (% domic.)", fa.pct_agua_rede as number | null, fb.pct_agua_rede as number | null, pctFmt],
                  ["Lixo coletado (% domic.)", fa.pct_lixo_coletado as number | null, fb.pct_lixo_coletado as number | null, pctFmt],
                ],
              },
            ];
            return (
              <div className="mt-4 mn-fade-in">
                {/* Cabeçalho A × B (os nomes saíram do thead da tabela antiga) */}
                <div className="flex items-center justify-between gap-2 pb-2 border-b border-border">
                  <span className="font-semibold text-sm truncate">{String(fa.nm_mun)}</span>
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground shrink-0">comparativo</span>
                  <span className="font-semibold text-sm truncate text-right">{String(fb.nm_mun)}</span>
                </div>
                {grupos.map((g) => (
                  <div key={g.label} className="mt-4 first:mt-3">
                    <p className="uppercase text-[11px] tracking-wider text-muted-foreground mb-2">{g.label}</p>
                    <div className="space-y-2.5">
                      {g.rows.map(([label, va, vb, fmtV]) => {
                        const aWins = va != null && vb != null && va > vb;
                        const bWins = va != null && vb != null && vb > va;
                        const max = Math.max(va ?? 0, vb ?? 0);
                        // Largura proporcional ao maior dos dois (piso de 2% pra
                        // um valor pequeno não sumir por completo). Null → 0.
                        const wA = va != null && max > 0 ? Math.max(2, (va / max) * 100) : 0;
                        const wB = vb != null && max > 0 ? Math.max(2, (vb / max) * 100) : 0;
                        // Delta % do vencedor sobre o perdedor (chip discreto).
                        const lo = Math.min(va ?? 0, vb ?? 0);
                        const delta = (aWins || bWins) && lo > 0 ? Math.round(((max - lo) / lo) * 100) : null;
                        const chip = delta != null && delta > 0 ? (
                          <span className="inline-block mt-0.5 text-[10px] leading-none px-1 py-0.5 rounded bg-primary/10 text-primary tabular-nums">
                            +{delta}%
                          </span>
                        ) : null;
                        return (
                          <div key={label}>
                            <p className="text-center text-[11px] text-muted-foreground">{label}</p>
                            <div className="mt-1 flex items-center gap-2">
                              <div className="w-20 sm:w-24 shrink-0 text-right">
                                <span className={`block text-xs tabular-nums ${va == null ? "text-muted-foreground" : aWins ? "font-semibold" : ""}`}>
                                  {va != null ? fmtV(va) : "s/ dado"}
                                </span>
                                {aWins && chip}
                              </div>
                              {/* Barras espelhadas a partir do centro: A cresce
                                  pra esquerda, B pra direita; o vencedor leva o
                                  gradiente dourado, o outro fica neutro. */}
                              <div className="flex-1 min-w-0 flex items-center">
                                <div className="flex-1 flex justify-end">
                                  <div
                                    className={`h-2 rounded-l-full ${aWins ? "bg-gradient-to-l from-primary/60 to-primary" : "bg-muted/50"}`}
                                    style={{ width: `${wA}%` }}
                                  />
                                </div>
                                <div className="w-px h-3 bg-border shrink-0" />
                                <div className="flex-1">
                                  <div
                                    className={`h-2 rounded-r-full ${bWins ? "bg-gradient-to-r from-primary/60 to-primary" : "bg-muted/50"}`}
                                    style={{ width: `${wB}%` }}
                                  />
                                </div>
                              </div>
                              <div className="w-20 sm:w-24 shrink-0 text-left">
                                <span className={`block text-xs tabular-nums ${vb == null ? "text-muted-foreground" : bWins ? "font-semibold" : ""}`}>
                                  {vb != null ? fmtV(vb) : "s/ dado"}
                                </span>
                                {bWins && chip}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
                <p className="text-[11px] text-muted-foreground mt-4 pt-3 border-t border-border">Barra dourada: o maior valor de cada indicador. Fontes · População e perfil: Censo IBGE 2022 · Renda: base 2010 · PIB: IBGE 2023 · IDHM: Atlas/PNUD (2010) · IDEB: INEP 2023 · Bolsa Família/CadÚnico: MDS.</p>
              </div>
            );
          })()}
        </div>
      )}

      {/* Maré IA · Leitura estratégica do território */}
      {view === "municipio" && (
        <div className="mt-4 rounded-2xl border border-primary/25 bg-gradient-to-br from-primary/[0.08] via-card to-card ring-1 ring-primary/10 p-5">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="font-semibold flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-primary" />
              Maré IA · Leitura estratégica de {String(muniProps?.nm_mun ?? "")}
            </p>
            {!aiInsight && (
              <button
                onClick={() => askMareIa(false)}
                disabled={aiLoading}
                className="py-2 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 disabled:opacity-60 inline-flex items-center gap-2"
              >
                {aiLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                {aiLoading ? "Analisando o território…" : "Consultar a Maré IA"}
              </button>
            )}
          </div>
          {aiError && <p className="text-sm text-rose-400 mt-3">{aiError}</p>}
          {aiInsight?.content && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 mn-fade-in">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-primary font-semibold mb-1">Perfil do território</p>
                <p className="text-sm leading-relaxed">{aiInsight.content.perfil}</p>
                <p className="text-[11px] uppercase tracking-wider text-primary font-semibold mt-4 mb-1">Leitura estratégica</p>
                <p className="text-sm leading-relaxed">{aiInsight.content.leitura_estrategica}</p>
              </div>
              <div>
                {!!aiInsight.content.publicos?.length && (
                  <>
                    <p className="text-[11px] uppercase tracking-wider text-primary font-semibold mb-1">Públicos prioritários</p>
                    <ul className="text-sm space-y-1">
                      {aiInsight.content.publicos.map((p, i) => (
                        <li key={i} className="flex gap-2"><span className="text-primary">•</span><span>{p}</span></li>
                      ))}
                    </ul>
                  </>
                )}
                {!!aiInsight.content.recomendacoes?.length && (
                  <>
                    <p className="text-[11px] uppercase tracking-wider text-primary font-semibold mt-4 mb-1">Recomendações</p>
                    <ul className="text-sm space-y-1">
                      {aiInsight.content.recomendacoes.map((r, i) => (
                        <li key={i} className="flex gap-2"><span className="text-primary">→</span><span>{r}</span></li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
              <p className="md:col-span-2 text-[11px] text-muted-foreground border-t border-border pt-2">
                Gerado pela Maré IA a partir de dados do IBGE, INEP, PNUD e MDS. Use como apoio à decisão e valide no território.
              </p>
            </div>
          )}
        </div>
      )}

      <p className="text-[11px] text-muted-foreground mt-3">
        Fontes: <span className="text-foreground">População e perfil: Censo IBGE 2022</span> (Agregados por
        Setores Censitários, release mai/2026) · Renda: base 2010 · PIB: IBGE 2023 · IDHM: Atlas/PNUD (2010) ·
        IDEB: INEP 2023 · Bolsa Família/CadÚnico: MDS.
        Cobertura: <span className="text-foreground">{ufGeo?.features.length ?? "…"} municípios de {UF_NOMES[uf] ?? uf}</span>.
        Áreas em cinza são setores sem população residente (parque, indústria, área militar etc.),
        não falta de dado. Cores em 6 faixas de igual tamanho (mais escuro = maior).
      </p>
    </div>
  );
}

function Stat({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/70 bg-gradient-to-br from-card to-background/40 p-3.5 flex items-center gap-3 ring-1 ring-white/[0.03] hover:ring-primary/25 hover:border-primary/30 transition-all duration-200">
      <div className="shrink-0 w-10 h-10 rounded-xl bg-gradient-to-br from-primary/30 to-primary/[0.06] text-primary flex items-center justify-center ring-1 ring-primary/20">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground truncate">{label}</p>
        <p className="text-xl font-bold tabular-nums leading-tight tracking-tight truncate">{value}</p>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-right">{value}</span>
    </div>
  );
}

// ---- Extras demográficos (Censo 2022): homens, pirâmide etária (11 faixas) e
// saneamento (água/esgoto/lixo). A fonte é a MESMA em setor (props cruas) e em
// bairro (somas agregadas) — as colunas têm o mesmo nome (idade_*, dom_*,
// sexo_*), então um único derivador serve os dois caminhos.
const FAIXA_DEFS: [string, string][] = [
  ["idade_0_4", "0 a 4"], ["idade_5_9", "5 a 9"], ["idade_10_14", "10 a 14"],
  ["idade_15_19", "15 a 19"], ["idade_20_24", "20 a 24"], ["idade_25_29", "25 a 29"],
  ["idade_30_39", "30 a 39"], ["idade_40_49", "40 a 49"], ["idade_50_59", "50 a 59"],
  ["idade_60_69", "60 a 69"], ["idade_70_mais", "70 ou mais"],
];

type CompCell = { pct: number | null; n: number | null };
type DemogExtras = {
  homens: CompCell;
  faixas: { label: string; pct: number | null; n: number | null }[] | null;
  saneamento: { agua: CompCell; esgoto: CompCell; lixo: CompCell } | null;
};

/**
 * Deriva homens / pirâmide etária / saneamento a partir de um registro com as
 * colunas do Censo (setor cru OU somas do bairro). Percentuais:
 *  - homens = masc ÷ (masc+fem)   (base sexo, casa com o % de mulheres)
 *  - faixa etária = faixa ÷ população
 *  - saneamento = parte ÷ total de domicílios da variável (não a população).
 */
function demogExtras(src: Record<string, unknown> | null | undefined, pop: number): DemogExtras {
  const num = (k: string): number | null => {
    const x = src?.[k];
    if (typeof x === "number" && Number.isFinite(x)) return x;
    if (typeof x === "string" && x !== "" && Number.isFinite(Number(x))) return Number(x);
    return null;
  };
  const pctOf = (n: number | null, base: number): number | null =>
    n != null && base > 0 ? Number(((n / base) * 100).toFixed(1)) : null;

  const masc = num("sexo_masculino");
  const fem = num("sexo_feminino");
  const sx = (masc ?? 0) + (fem ?? 0);

  const faixas = FAIXA_DEFS.map(([k, label]) => {
    const n = num(k);
    return { label, n, pct: pctOf(n, pop) };
  });
  const hasFaixas = faixas.some((f) => f.n != null);

  const san = (parteK: string, totalK: string): CompCell => {
    const p = num(parteK);
    const t = num(totalK);
    return { pct: pctOf(p, t ?? 0), n: p };
  };
  const agua = san("dom_agua_rede", "dom_agua_total");
  const esgoto = san("dom_esgoto_adequado", "dom_esgoto_total");
  const lixo = san("dom_lixo_coletado", "dom_lixo_total");
  const hasSan = [agua, esgoto, lixo].some((s) => s.pct != null);

  return {
    homens: { pct: pctOf(masc, sx), n: masc },
    faixas: hasFaixas ? faixas : null,
    saneamento: hasSan ? { agua, esgoto, lixo } : null,
  };
}

// Detalhe do bairro/setor: TODOS os indicadores do Censo 2022 que existem no
// nível de setor (densidade, moradores, alfabetização, área) + composição de
// cor/raça (5 categorias individuais) e sexo/idade. Um toggle %↔nº alterna a
// composição entre porcentagem e NÚMERO ABSOLUTO de pessoas (pedido do PO).
// Aceita number OU string (setor vem do JSON; área agregada já vem calculada).
type DNum = number | string | null | undefined;
function DetalheIndicadores({
  v, mode, onMode,
}: {
  v: {
    dens: DNum; media: DNum; alfab: DNum; area: DNum;
    raca: { label: string; pct: DNum; n: DNum }[];
    mulheres: { pct: DNum; n: DNum };
    idoso: { pct: DNum; n: DNum };
    // Extras Censo 2022 (opcionais — só aparecem quando há dado).
    homens?: { pct: DNum; n: DNum };
    alfabN?: DNum;
    faixas?: { label: string; pct: number | null; n: number | null }[] | null;
    saneamento?: {
      agua: { pct: number | null; n: number | null };
      esgoto: { pct: number | null; n: number | null };
      lixo: { pct: number | null; n: number | null };
    } | null;
  };
  mode: "pct" | "abs";
  onMode: (m: "pct" | "abs") => void;
}) {
  const fmt = new Intl.NumberFormat("pt-BR");
  const asPct = (x: DNum) => (x == null ? "—" : `${String(x).replace(".", ",")}%`);
  const asAbs = (x: DNum) => (x == null ? "—" : fmt.format(Math.round(Number(x))));
  const cell = (o: { pct: DNum; n: DNum }) => (mode === "abs" ? asAbs(o.n) : asPct(o.pct));
  const pctOf = (x: DNum) => (x == null ? null : Number(x));
  // Sexo/idade como lista — mesmo tratamento visual da composição de cor/raça.
  // Homens entram quando há dado (área e setor), lado a lado com Mulheres.
  const sexoRows = [
    ...(v.homens ? [{ label: "Homens", ...v.homens }] : []),
    { label: "Mulheres", ...v.mulheres },
    { label: "60 anos ou mais", ...v.idoso },
  ];
  // Dominante do grupo = maior % (rótulo em destaque pra leitura rápida).
  const racaMax = Math.max(0, ...v.raca.map((r) => pctOf(r.pct) ?? 0));
  const sexoMax = Math.max(0, ...sexoRows.map((r) => pctOf(r.pct) ?? 0));
  const faixaMax = Math.max(0, ...(v.faixas ?? []).map((f) => f.pct ?? 0));
  const saneRows = v.saneamento
    ? [
        { label: "Água na rede", ...v.saneamento.agua },
        { label: "Esgoto adequado", ...v.saneamento.esgoto },
        { label: "Lixo coletado", ...v.saneamento.lixo },
      ]
    : [];
  const saneMax = Math.max(0, ...saneRows.map((r) => pctOf(r.pct) ?? 0));
  // Linha de categoria + mini-barra proporcional ao %. A barra SEMPRE lê o pct,
  // mesmo no modo nº: a composição visual não muda com o toggle, só o rótulo.
  // Sem dado (null) → sem barra.
  const compRow = (r: { label: string; pct: DNum; n: DNum }, max: number) => {
    const p = pctOf(r.pct);
    const dominante = p != null && p > 0 && p >= max;
    return (
      <div key={r.label}>
        <div className="flex items-center justify-between gap-2">
          <span className={dominante ? "font-semibold" : "text-muted-foreground"}>{r.label}</span>
          <span className="font-medium text-right tabular-nums">{cell(r)}</span>
        </div>
        {p != null && (
          <div className="mt-1 h-1.5 rounded-full bg-muted/40 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary"
              style={{ width: `${Math.min(100, Math.max(0, p))}%` }}
            />
          </div>
        )}
      </div>
    );
  };
  return (
    <div className="mt-3 space-y-2 text-sm">
      <Row label="Densidade" value={v.dens == null ? "—" : `${fmt.format(Math.round(Number(v.dens)))} hab/km²`} />
      <Row label="Moradores/domicílio" value={v.media == null ? "—" : String(v.media).replace(".", ",")} />
      <Row
        label="Alfabetização 15+"
        value={
          mode === "abs" && v.alfabN != null
            ? `${asAbs(v.alfabN)} pessoas`
            : v.alfab == null
              ? "—"
              : `${String(v.alfab).replace(".", ",")}%`
        }
      />
      <Row label="Área" value={v.area == null ? "—" : `${Number(v.area).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} km²`} />

      <div className="pt-2 mt-1 border-t border-border/60 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Composição da população</span>
          {/* Toggle %  ·  nº — alterna cor/raça e sexo/idade entre porcentagem
              e número absoluto de pessoas. */}
          <div className="inline-flex rounded-md border border-border overflow-hidden text-[11px] leading-none">
            {(["pct", "abs"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => onMode(m)}
                title={m === "pct" ? "Mostrar em porcentagem" : "Mostrar em número de pessoas"}
                className={`px-2.5 py-1 transition-colors ${
                  mode === m
                    ? "bg-primary/20 text-primary font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {m === "pct" ? "%" : "nº"}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="text-muted-foreground mb-1">Cor ou raça</p>
          <div className="space-y-2 pl-2.5 border-l-2 border-primary/20">
            {v.raca.map((r) => compRow(r, racaMax))}
          </div>
        </div>

        <div>
          <p className="text-muted-foreground mb-1">Sexo e idade</p>
          <div className="space-y-2 pl-2.5 border-l-2 border-primary/20">
            {sexoRows.map((r) => compRow(r, sexoMax))}
          </div>
        </div>

        {/* Pirâmide etária completa (11 faixas) — recolhida por padrão pra não
            poluir o painel (pedido do PO). Respeita o toggle %↔nº. */}
        {v.faixas && v.faixas.length > 0 && (
          <details className="group">
            <summary className="flex items-center justify-between cursor-pointer list-none text-muted-foreground hover:text-foreground transition-colors">
              <span>Faixas etárias</span>
              <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:rotate-180" />
            </summary>
            <div className="space-y-2 pl-2.5 border-l-2 border-primary/20 mt-2">
              {v.faixas.map((r) => compRow(r, faixaMax))}
            </div>
          </details>
        )}

        {/* Saneamento (água/esgoto/lixo) — % sobre o total de domicílios da
            variável. Recolhido por padrão. Respeita o toggle %↔nº. */}
        {saneRows.length > 0 && (
          <details className="group">
            <summary className="flex items-center justify-between cursor-pointer list-none text-muted-foreground hover:text-foreground transition-colors">
              <span>Saneamento</span>
              <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:rotate-180" />
            </summary>
            <div className="space-y-2 pl-2.5 border-l-2 border-primary/20 mt-2">
              {saneRows.map((r) => compRow(r, saneMax))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
