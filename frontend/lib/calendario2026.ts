/**
 * Calendário Eleitoral 2026 — datas-chave do TSE.
 *
 * BASE: Resolução TSE 23.610/2019 (modificada por 23.671/2021 + 23.675/2021)
 * + paralelos com 2022/2024. Algumas datas exatas só são publicadas
 * na Resolução do ciclo (sai ~6 meses antes); marcadas com `tentative: true`
 * quando estimadas. Atualizar ao publicar a Res. 2026.
 *
 * Cargos em 2026: Presidente, Governador, Senador, Dep. Federal,
 * Dep. Estadual/Distrital. Eleições gerais — 1º turno 04/10/2026.
 */

export type CalendarPhase = "pre-campanha" | "campanha" | "pos-campanha";

export type CalendarItem = {
  /** ISO YYYY-MM-DD */
  date: string;
  title: string;
  description: string;
  phase: CalendarPhase;
  /** True se a data ainda não foi formalmente publicada (estimativa). */
  tentative?: boolean;
  /** Slug pra agrupar no checklist (mesmo slug = mesma "tarefa"). */
  slug: string;
};

export const CALENDARIO_2026: CalendarItem[] = [
  // ----- PRÉ-CAMPANHA -----
  {
    date: "2026-04-04",
    title: "Convenções partidárias começam",
    description:
      "Período de realização das convenções pra escolha de candidatos e formação de coligações (até 05/08). Lei 9.504/97, art. 8º.",
    phase: "pre-campanha",
    slug: "convencoes-inicio",
  },
  {
    date: "2026-08-05",
    title: "Fim das convenções partidárias",
    description: "Último dia para realizar convenções e definir candidaturas.",
    phase: "pre-campanha",
    slug: "convencoes-fim",
  },
  {
    date: "2026-08-15",
    title: "Prazo final para registro de candidatura no TSE",
    description:
      "Pedido de Registro de Candidatura (RRC). Sem isso o candidato não consta na urna.",
    phase: "pre-campanha",
    slug: "rrc-deadline",
  },

  // ----- CAMPANHA -----
  {
    date: "2026-08-16",
    title: "Início da propaganda eleitoral",
    description:
      "A partir desta data pode-se fazer propaganda de rua, comício, showmício (ressalvas), mídia paga em alguns canais, etc.",
    phase: "campanha",
    slug: "propaganda-inicio",
  },
  {
    date: "2026-08-26",
    title: "Início da propaganda em rádio e TV",
    description: "Horário eleitoral gratuito começa 45 dias antes do 1º turno.",
    phase: "campanha",
    tentative: true,
    slug: "ge-radio-tv",
  },
  {
    date: "2026-09-09",
    title: "Debates obrigatórios em emissoras de rádio/TV",
    description:
      "Partir desta data emissoras com mais de 20 anos de outorga ficam obrigadas a transmitir debates entre presidenciáveis.",
    phase: "campanha",
    tentative: true,
    slug: "debates",
  },
  {
    date: "2026-10-04",
    title: "1º TURNO — Eleição",
    description:
      "Votação em todo o Brasil das 8h às 17h. Cargos: Presidente, Governador, Senador, Dep. Federal, Dep. Estadual/Distrital.",
    phase: "campanha",
    slug: "1o-turno",
  },
  {
    date: "2026-10-25",
    title: "2º TURNO — Eleição (onde houver)",
    description:
      "Votação em municípios com 2º turno (presidente + governador onde nenhum atingir maioria absoluta no 1º turno).",
    phase: "campanha",
    slug: "2o-turno",
  },

  // ----- PÓS-CAMPANHA -----
  {
    date: "2026-11-04",
    title: "Prazo final para prestação de contas final",
    description:
      "30 dias após o pleito. Comitês financeiros e candidatos eleitos/não-eleitos devem prestar contas no SPCE (TSE).",
    phase: "pos-campanha",
    slug: "prestacao-contas",
  },
  {
    date: "2026-12-19",
    title: "Diplomação dos eleitos (até esta data)",
    description:
      "TREs/TSE diplomam eleitos até 19/12 (Resolução TSE). Sem diplomação não há posse.",
    phase: "pos-campanha",
    tentative: true,
    slug: "diplomacao",
  },
  {
    date: "2027-01-01",
    title: "Posse — Presidente, Governadores e Parlamentares",
    description:
      "01/01 posse do Presidente (Brasília) + Governadores. 01/02 posse de Senadores/Deputados Federais. Estaduais variam por UF.",
    phase: "pos-campanha",
    slug: "posse",
  },
];
