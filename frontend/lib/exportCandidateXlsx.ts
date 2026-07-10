/**
 * Exportação de DADOS BRUTOS do candidato em Excel (4 abas):
 *   Resumo · Votos por município · Votos por bairro · Votos por local.
 *
 * Serviço isolado (separação de responsabilidades): o botão só chama
 * exportCandidateXlsx(); fetch + montagem do workbook vivem aqui.
 * A lib `xlsx` (SheetJS) entra por import dinâmico — só pesa no bundle de
 * quem realmente exporta.
 *
 * Cobertura: bairro/local dependem da votação por seção (2018/2020/2022 RJ,
 * 2024 Brasil) — sem dado, a aba sai com um aviso em vez de sumir (o usuário
 * entende que não é bug).
 */
import { api } from "@/lib/api";
import type {
  TseCandidateByNeighborhoodResponse,
  TseCandidateResults,
} from "@/lib/types";

type PlaceRow = {
  place: string;
  address: string | null;
  neighborhood: string | null;
  electors_total: number | null;
  municipality_name: string;
  municipality_state: string;
  votes: number;
};

function slug(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export async function exportCandidateXlsx(
  results: TseCandidateResults,
): Promise<void> {
  const c = results.candidate;

  // Dados de bairro (SEM limit → todos) e de local, em paralelo. Falha em um
  // deles não aborta o export: a aba sai com o aviso de indisponibilidade.
  const [nb, places] = await Promise.all([
    api<TseCandidateByNeighborhoodResponse>(
      `/v1/tse/candidates/${c.id}/by-neighborhood`,
    ).catch(() => null),
    api<PlaceRow[]>(`/v1/tse/candidates/${c.id}/by-place`).catch(() => null),
  ]);

  const XLSX = await import("xlsx");
  const wb = XLSX.utils.book_new();
  const noSectionData =
    "Sem votação por seção importada para esta eleição (cobertura: 2018/2020/2022 RJ e 2024 Brasil).";

  // ---- Aba 1: Resumo ----
  const resumo = XLSX.utils.aoa_to_sheet([
    ["Candidato", c.urn_name],
    ["Nome civil", c.name],
    ["Cargo", c.office_name],
    ["Partido", c.party.abbreviation],
    ["UF", c.state],
    ["Eleição", c.election.year],
    ["Situação", c.result_status ?? ""],
    ["Total de votos", results.total_votes],
    ["Municípios com votos", results.municipalities_with_votes],
    ["Bairros com votos", nb?.total_neighborhoods ?? "s/d"],
    ["Locais de votação com votos", places?.length ?? "s/d"],
    [],
    ["Fonte", "TSE (dados abertos) · MareNostrum EleitoAI"],
  ]);
  resumo["!cols"] = [{ wch: 26 }, { wch: 40 }];
  XLSX.utils.book_append_sheet(wb, resumo, "Resumo");

  // ---- Aba 2: Votos por município ----
  const totalVotes = results.total_votes || 1;
  const muniSheet = XLSX.utils.json_to_sheet(
    results.results.map((r) => ({
      "Município": r.municipality.name,
      UF: r.municipality.state,
      Votos: r.votes,
      "% do total": Number(((r.votes / totalVotes) * 100).toFixed(2)),
    })),
  );
  muniSheet["!cols"] = [{ wch: 28 }, { wch: 5 }, { wch: 10 }, { wch: 10 }];
  XLSX.utils.book_append_sheet(wb, muniSheet, "Votos por município");

  // ---- Aba 3: Votos por bairro ----
  const nbItems = nb?.items ?? [];
  const bairroSheet =
    nbItems.length > 0
      ? XLSX.utils.json_to_sheet(
          nbItems.map((i) => ({
            Bairro: i.neighborhood,
            "Município": i.municipality_name ?? "",
            UF: i.municipality_state ?? "",
            Votos: i.votes,
            "Locais de votação": i.places_count,
            "Eleitores aptos": i.electors_total || "",
            "Penetração %": i.penetration_pct ?? "",
          })),
        )
      : XLSX.utils.aoa_to_sheet([[noSectionData]]);
  bairroSheet["!cols"] = [
    { wch: 26 }, { wch: 24 }, { wch: 5 }, { wch: 10 }, { wch: 16 },
    { wch: 14 }, { wch: 12 },
  ];
  XLSX.utils.book_append_sheet(wb, bairroSheet, "Votos por bairro");

  // ---- Aba 4: Votos por local de votação ----
  const placeSheet =
    places && places.length > 0
      ? XLSX.utils.json_to_sheet(
          places.map((p) => ({
            "Local de votação": p.place,
            "Endereço": p.address ?? "",
            Bairro: p.neighborhood ?? "",
            "Município": p.municipality_name,
            UF: p.municipality_state,
            Votos: p.votes,
            "Eleitores aptos": p.electors_total || "",
          })),
        )
      : XLSX.utils.aoa_to_sheet([[noSectionData]]);
  placeSheet["!cols"] = [
    { wch: 34 }, { wch: 34 }, { wch: 22 }, { wch: 24 }, { wch: 5 },
    { wch: 10 }, { wch: 14 },
  ];
  XLSX.utils.book_append_sheet(wb, placeSheet, "Votos por local");

  XLSX.writeFile(
    wb,
    `dados-${slug(c.urn_name)}-${c.election.year}.xlsx`,
    { compression: true },
  );
}
