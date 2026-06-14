/**
 * Agregação de dados censitários (IBGE) — a "regra da sensibilidade".
 *
 * O IBGE entrega tudo no nível mais granular (setor censitário). Ao subir de
 * nível (setor → bairro/distrito → município), a matemática depende do tipo
 * da coluna:
 *
 *  - VALOR ABSOLUTO (população, domicílios, alfabetizados, cor/raça...):
 *    soma simples.
 *  - MÉDIA/TAXA (renda média, média de moradores, taxa de alfabetização...):
 *    NUNCA somar nem tirar média simples — é MÉDIA PONDERADA pelo peso do
 *    universo da variável: Σ(média_i × peso_i) ÷ Σ(peso_i).
 *
 * O dicionário abaixo é a única fonte de verdade dessa regra. Para adicionar
 * uma variável nova (ex: renda média V06004 quando o IBGE publicar por setor
 * no Censo 2022), basta registrá-la aqui — toda a UI agrega certo.
 */

type Row = Record<string, number | string | null | undefined>;

/** Colunas de valor absoluto → soma simples. */
export const SUM_COLS = [
  "populacao",
  "domicilios",
  "area_km2",
  "alfabetizados_15mais",
  "pop_15mais",
  "raca_branca",
  "raca_preta",
  "raca_amarela",
  "raca_parda",
  "raca_indigena",
] as const;

/**
 * Colunas de média/taxa → média ponderada: Σ(valor×peso)÷Σ(peso).
 * `weight` é a coluna de peso (o universo da variável no setor).
 */
export const WEIGHTED_AVG_COLS: Record<string, { weight: string; decimals: number }> = {
  // média de moradores por domicílio — peso: domicílios
  media_moradores: { weight: "domicilios", decimals: 2 },
  // taxa de alfabetização 15+ (%) — peso: população 15+
  taxa_alfabetizacao: { weight: "pop_15mais", decimals: 1 },
  // % cor ou raça (pretos e pardos) — peso: população do setor
  pct_pretos_pardos: { weight: "populacao", decimals: 1 },
  // FUTURO (Censo 2022 ainda não publicou renda por setor): renda média
  // nominal do responsável (V06004) — peso: responsáveis pelos domicílios.
  renda_media: { weight: "responsaveis", decimals: 2 },
};

/** Derivadas de somas (recalculadas após agregar — nunca somadas). */
const DERIVED: Record<string, (acc: Record<string, number>) => number | null> = {
  densidade_hab_km2: (a) =>
    a.area_km2 > 0 ? Math.round((a.populacao / a.area_km2) * 10) / 10 : null,
};

export type AggregatedRow = {
  key: string;
  setores: number;
  sums: Record<string, number>;
  averages: Record<string, number | null>;
  derived: Record<string, number | null>;
};

/**
 * Agrega setores censitários pelo nível geográfico dado.
 *
 * @param data          linhas no nível de setor (properties do GeoJSON)
 * @param groupByLevel  chave de agrupamento: "nm_bairro" | "nm_dist" |
 *                      "cd_mun" | (qualquer coluna presente nas linhas)
 */
export function aggregateCensusData(
  data: Row[],
  groupByLevel: string,
): AggregatedRow[] {
  type Acc = {
    setores: number;
    sums: Record<string, number>;
    // média ponderada: acumula numerador (valor×peso) e denominador (peso)
    wNum: Record<string, number>;
    wDen: Record<string, number>;
  };
  const groups = new Map<string, Acc>();

  for (const row of data) {
    const key = String(row[groupByLevel] ?? "—") || "—";
    let g = groups.get(key);
    if (!g) {
      g = { setores: 0, sums: {}, wNum: {}, wDen: {} };
      groups.set(key, g);
    }
    g.setores += 1;

    for (const col of SUM_COLS) {
      const v = row[col];
      if (typeof v === "number" && Number.isFinite(v)) {
        g.sums[col] = (g.sums[col] ?? 0) + v;
      }
    }

    for (const [col, { weight }] of Object.entries(WEIGHTED_AVG_COLS)) {
      const v = row[col];
      const w = row[weight];
      // só entra na média quem tem valor E peso (setores com sigilo ficam fora
      // do numerador E do denominador — não distorcem a média do grupo)
      if (
        typeof v === "number" && Number.isFinite(v) &&
        typeof w === "number" && Number.isFinite(w) && w > 0
      ) {
        g.wNum[col] = (g.wNum[col] ?? 0) + v * w;
        g.wDen[col] = (g.wDen[col] ?? 0) + w;
      }
    }
  }

  const out: AggregatedRow[] = [];
  for (const [key, g] of groups) {
    const averages: Record<string, number | null> = {};
    for (const [col, { decimals }] of Object.entries(WEIGHTED_AVG_COLS)) {
      const den = g.wDen[col] ?? 0;
      averages[col] = den > 0
        ? Number((g.wNum[col]! / den).toFixed(decimals))
        : null;
    }
    const derived: Record<string, number | null> = {};
    for (const [col, fn] of Object.entries(DERIVED)) {
      derived[col] = fn(g.sums as Record<string, number>);
    }
    out.push({ key, setores: g.setores, sums: g.sums, averages, derived });
  }
  // maior população primeiro (ordem natural de ranking territorial)
  out.sort((a, b) => (b.sums.populacao ?? 0) - (a.sums.populacao ?? 0));
  return out;
}
