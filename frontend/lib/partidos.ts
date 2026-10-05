/**
 * Desempenho de partido somado por LINHAGEM, não por número.
 *
 * As telas de partido são endereçadas pelo número que o partido usa HOJE. Só
 * que número troca de dono (o 14 foi PTB até 2022 e hoje é do Missão) e
 * partido se funde (PTB + Patriota = PRD). Casar o item do ano pelo número
 * punha os eleitos do PTB sob o nome Missão, e deixava o PRD zerado em 2022
 * enquanto o gráfico de evolução logo abaixo mostrava PTB + Patriota.
 *
 * O backend diz, em cada item, a que número de hoje aquele partido pertence
 * (`lineage_number`); aqui só se soma por ele.
 */
import type { TsePartyPerformanceItem } from "./types";

export type TotaisDoPartido = {
  elected_count: number;
  total_votes: number;
  candidates_count: number;
};

export function somarPorLinhagem(
  items: TsePartyPerformanceItem[],
): Map<number, TotaisDoPartido> {
  const m = new Map<number, TotaisDoPartido>();
  for (const i of items) {
    const numero = i.lineage_number ?? i.party.number;
    const t = m.get(numero) ?? { elected_count: 0, total_votes: 0, candidates_count: 0 };
    t.elected_count += i.elected_count;
    t.total_votes += i.total_votes;
    t.candidates_count += i.candidates_count;
    m.set(numero, t);
  }
  return m;
}
