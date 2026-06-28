/**
 * Catálogo central de eleições e cargos disponíveis no sistema.
 *
 * Fonte única pra todos os seletores de ano/cargo das páginas de Análise.
 * Atualizar AQUI quando importar novo dataset TSE — todas as páginas herdam.
 *
 * Histórico importado (Wave 4 — 21A):
 *   2024 municipal · 2022 geral · 2020 municipal ·
 *   2018 geral · 2016 municipal · 2014 geral
 */

export type OfficeOption = { value: string; label: string };

// Cargos por tipo de pleito (códigos TSE: 11=prefeito, 13=vereador,
// 3=governador, 5=senador, 6=dep. federal, 7=dep. estadual).
const MUNICIPAL_OFFICES: OfficeOption[] = [
  { value: "11", label: "Prefeito" },
  { value: "13", label: "Vereador" },
];

const FEDERAL_OFFICES: OfficeOption[] = [
  { value: "3", label: "Governador" },
  { value: "5", label: "Senador" },
  { value: "6", label: "Deputado Federal" },
  { value: "7", label: "Deputado Estadual" },
];

/** Cargos disponíveis por ano. */
export const OFFICES_BY_YEAR: Record<string, OfficeOption[]> = {
  "2024": MUNICIPAL_OFFICES,
  "2022": FEDERAL_OFFICES,
  "2020": MUNICIPAL_OFFICES,
  "2018": FEDERAL_OFFICES,
  "2016": MUNICIPAL_OFFICES,
  "2014": FEDERAL_OFFICES,
  "2010": FEDERAL_OFFICES,
  "2006": FEDERAL_OFFICES,
  "2002": FEDERAL_OFFICES,
};

/**
 * Texto-padrão (tooltip) explicando "votos nominais" pro cliente leigo.
 * Fonte única — usado em ranking, partido, partidos, município e painel.
 */
export const VOTOS_NOMINAIS_HINT =
  "Votos dados diretamente aos candidatos (não inclui voto de legenda).";

/** Anos elegíveis pra seletor genérico (mais recente primeiro). */
export const YEAR_OPTIONS: OfficeOption[] = [
  { value: "2024", label: "2024 (Municipal)" },
  { value: "2022", label: "2022 (Federal/Estadual)" },
  { value: "2020", label: "2020 (Municipal)" },
  { value: "2018", label: "2018 (Federal/Estadual)" },
  { value: "2016", label: "2016 (Municipal)" },
  { value: "2014", label: "2014 (Federal/Estadual)" },
];

/** Apenas anos municipais (pra páginas que só fazem sentido em municipal — ex: zona/bairros). */
export const MUNICIPAL_YEAR_OPTIONS: OfficeOption[] = [
  { value: "2024", label: "2024" },
  { value: "2020", label: "2020" },
  { value: "2016", label: "2016" },
];

/** Label curto (sem o tipo entre parênteses) — pra UI compacta. */
export const YEAR_OPTIONS_SHORT: OfficeOption[] = YEAR_OPTIONS.map((y) => ({
  value: y.value,
  label: y.value,
}));
