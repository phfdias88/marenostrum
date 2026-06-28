/**
 * Tipos, formatação e rótulos dos indicadores do mapa censitário/socioeconômico.
 *
 * Módulo SEM dependência de Leaflet — por isso pode ser importado tanto pelo
 * CensusMap (client, ssr:false) quanto pela página /dashboard/censo (SSR) sem
 * quebrar. Fonte única de FMT/LABEL pra mapa, legenda e ranking lateral.
 */

export type CensusIndicator =
  | "populacao"
  | "densidade_hab_km2"
  | "domicilios"
  | "media_moradores"
  | "taxa_alfabetizacao"
  | "pct_pretos_pardos"
  | "renda_media"
  | "pct_bolsa_familia"
  | "pct_cadunico"
  | "pib_per_capita"
  | "idhm"
  | "ideb_anos_iniciais"
  | "ideb_anos_finais"
  | "pct_agua_rede"
  | "pct_esgoto_adequado"
  | "pct_lixo_coletado";

const numFmt = new Intl.NumberFormat("pt-BR");

/** Formata o valor de um indicador pra exibição (com unidade). */
export const INDICATOR_FMT: Record<CensusIndicator, (v: number) => string> = {
  populacao: (v) => `${numFmt.format(Math.round(v))} hab`,
  domicilios: (v) => `${numFmt.format(Math.round(v))} domic.`,
  densidade_hab_km2: (v) => `${numFmt.format(Math.round(v))} hab/km²`,
  media_moradores: (v) => `${v.toFixed(2).replace(".", ",")} /domic.`,
  taxa_alfabetizacao: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pct_pretos_pardos: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  renda_media: (v) => `R$ ${numFmt.format(Math.round(v))}`,
  pct_bolsa_familia: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pct_cadunico: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pib_per_capita: (v) => `R$ ${numFmt.format(Math.round(v))}`,
  idhm: (v) => v.toFixed(3).replace(".", ","),
  ideb_anos_iniciais: (v) => v.toFixed(1).replace(".", ","),
  ideb_anos_finais: (v) => v.toFixed(1).replace(".", ","),
  pct_agua_rede: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pct_esgoto_adequado: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pct_lixo_coletado: (v) => `${v.toFixed(1).replace(".", ",")}%`,
};

/** Rótulo completo do indicador (com unidade/ano entre parênteses). */
export const INDICATOR_LABEL: Record<CensusIndicator, string> = {
  populacao: "População",
  domicilios: "Domicílios",
  densidade_hab_km2: "Densidade (hab/km²)",
  media_moradores: "Moradores / domicílio",
  taxa_alfabetizacao: "Alfabetização 15+ (%)",
  pct_pretos_pardos: "Cor ou raça — pretos e pardos (%)",
  renda_media: "Renda média domiciliar (R$, 2010)",
  pct_bolsa_familia: "Bolsa Família (% domicílios)",
  pct_cadunico: "CadÚnico (% domicílios)",
  pib_per_capita: "PIB per capita (R$, 2023)",
  idhm: "IDHM (2010)",
  ideb_anos_iniciais: "IDEB anos iniciais (2023)",
  ideb_anos_finais: "IDEB anos finais (2023)",
  pct_agua_rede: "Água por rede (% domic.)",
  pct_esgoto_adequado: "Esgoto adequado (% domic.)",
  pct_lixo_coletado: "Lixo coletado (% domic.)",
};

/** Rótulo curto (sem o trecho entre parênteses) — pra cabeçalhos compactos. */
export function indicatorShortLabel(key: CensusIndicator): string {
  return INDICATOR_LABEL[key].replace(/\s*\([^)]*\)\s*$/, "").trim();
}
