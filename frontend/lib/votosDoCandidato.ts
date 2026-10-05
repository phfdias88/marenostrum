/**
 * Total de votos de um candidato, do jeito que as telas de candidato mostram.
 *
 * A resposta de /candidates/{id}/results traz DOIS totais, e eles divergem:
 *
 *  - `total_votes` da resposta: soma do voto por município. Só anda quando uma
 *    varredura por município passa, e nunca inclui o exterior.
 *  - `candidate.total_votes`: o total oficial do candidato, que na apuração
 *    vem do placar do TSE a cada 2 minutos.
 *
 * Em eleição fechada os dois batem ao voto, então vale a soma (que é o que as
 * barras por município logo abaixo somam). Na eleição EM APURAÇÃO a soma está
 * atrasada ou incompleta — deputado federal de 2026 saía com "0 votos" na
 * página do candidato enquanto o ranking mostrava milhões —, e vale o oficial.
 */
import { ANO_EM_APURACAO } from "./elections";
import type { TseCandidate, TseCandidateResults } from "./types";

export function totalDoCandidato(
  d: TseCandidateResults,
  /** Candidato vindo de outra rota (lista), para quando a resposta não traz o total. */
  reserva?: TseCandidate,
): number {
  const oficial = d.candidate.total_votes ?? reserva?.total_votes ?? null;
  if (oficial == null) return d.total_votes;
  const emApuracao = d.candidate.election.year === ANO_EM_APURACAO;
  return emApuracao || d.results.length === 0 ? oficial : d.total_votes;
}

/** true quando o total exibido não é explicado pela lista de municípios. */
export function detalhePorMunicipioIncompleto(
  d: TseCandidateResults,
  reserva?: TseCandidate,
): boolean {
  return totalDoCandidato(d, reserva) > d.total_votes;
}
