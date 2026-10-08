/**
 * Exportação de DADOS BRUTOS do candidato em Excel (5 abas, do mais largo ao
 * mais fino): Resumo · Votos por município · Votos por bairro · Votos por
 * local · Votos por seção.
 *
 * Serviço isolado (separação de responsabilidades): o botão só chama
 * exportCandidateXlsx(); fetch + montagem do workbook vivem aqui.
 * A lib `xlsx` (SheetJS) entra por import dinâmico — só pesa no bundle de
 * quem realmente exporta.
 *
 * Cobertura: bairro/local dependem da votação por seção (ver
 * COBERTURA_VOTO_POR_SECAO) — sem dado, a aba sai com um aviso em vez de sumir
 * (o usuário entende que não é bug). O detalhe POR SEÇÃO é carregado à parte e
 * cobre menos que o voto por local (hoje: 2026 RJ).
 *
 * Três avisos diferentes, porque são três situações: a eleição não tem voto
 * por seção; tem, mas o detalhe por seção ainda não foi carregado; e a
 * CONSULTA falhou (aí o dado pode existir — o aviso manda exportar de novo em
 * vez de afirmar que não há).
 */
import { api } from "@/lib/api";
import { COBERTURA_VOTO_POR_SECAO } from "@/lib/elections";
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

// Um local com as seções em que o candidato teve voto: pares [seção, votos].
type SectionPlaceRow = {
  zone: number | null;
  place: string;
  neighborhood: string | null;
  municipality_name: string;
  municipality_state: string;
  votes: number;
  sections: [number, number][];
};

type BySectionResponse = {
  places_total: number;
  places_without_detail: number;
  sections_total: number;
  items: SectionPlaceRow[];
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

  // Dados de bairro (SEM limit → todos), de local e de seção, em paralelo.
  // Falha em um deles não aborta o export: fica `null`, e a aba sai com o
  // aviso de que a consulta falhou (diferente de "não há dado").
  const [nb, places, bySection] = await Promise.all([
    api<TseCandidateByNeighborhoodResponse>(
      `/v1/tse/candidates/${c.id}/by-neighborhood`,
    ).catch(() => null),
    api<PlaceRow[]>(`/v1/tse/candidates/${c.id}/by-place`).catch(() => null),
    api<BySectionResponse>(`/v1/tse/candidates/${c.id}/by-section`).catch(
      () => null,
    ),
  ]);

  const XLSX = await import("xlsx");
  const wb = XLSX.utils.book_new();
  const noSectionData = `Sem votação por seção importada para esta eleição (cobertura: ${COBERTURA_VOTO_POR_SECAO}).`;
  const fetchFailed =
    "Não foi possível consultar este dado agora. Exporte de novo em instantes.";
  const failedCell = "falha na consulta";
  const sectionPlaces = bySection?.items ?? [];

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
    ["Bairros com votos", nb ? nb.total_neighborhoods : failedCell],
    ["Locais de votação com votos", places ? places.length : failedCell],
    [
      "Seções eleitorais com votos",
      !bySection
        ? failedCell
        : sectionPlaces.length > 0
          ? bySection.sections_total
          : "s/d",
    ],
    // Só aparece quando o detalhe por seção cobre parte dos locais: sem a
    // linha, a aba por seção somaria menos que o total e pareceria erro.
    ...(bySection && sectionPlaces.length > 0 && bySection.places_without_detail > 0
      ? [["Locais sem detalhe por seção", bySection.places_without_detail]]
      : []),
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
      : XLSX.utils.aoa_to_sheet([[nb ? noSectionData : fetchFailed]]);
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
      : XLSX.utils.aoa_to_sheet([[places ? noSectionData : fetchFailed]]);
  placeSheet["!cols"] = [
    { wch: 34 }, { wch: 34 }, { wch: 22 }, { wch: 24 }, { wch: 5 },
    { wch: 10 }, { wch: 14 },
  ];
  XLSX.utils.book_append_sheet(wb, placeSheet, "Votos por local");

  // ---- Aba 5: Votos por seção eleitoral (dentro de cada local) ----
  // Locais na mesma ordem da aba anterior; dentro do local, seção crescente.
  // A Zona vai junto porque o número da seção só é único dentro dela.
  const sectionRows: (string | number)[][] = [];
  for (const p of sectionPlaces) {
    for (const [secao, votos] of p.sections) {
      sectionRows.push([
        p.municipality_name,
        p.municipality_state,
        p.zone ?? "",
        p.place,
        p.neighborhood ?? "",
        secao,
        votos,
      ]);
    }
  }
  const sectionSheet =
    sectionRows.length > 0
      ? XLSX.utils.aoa_to_sheet([
          [
            "Município", "UF", "Zona", "Local de votação", "Bairro",
            "Seção", "Votos",
          ],
          ...sectionRows,
        ])
      : XLSX.utils.aoa_to_sheet([
          [
            !bySection
              ? fetchFailed
              : bySection.places_total > 0
                ? "O detalhe por seção eleitoral ainda não foi carregado para esta eleição (o total de cada local está na aba anterior)."
                : noSectionData,
          ],
        ]);
  sectionSheet["!cols"] = [
    { wch: 24 }, { wch: 5 }, { wch: 6 }, { wch: 34 }, { wch: 22 },
    { wch: 7 }, { wch: 10 },
  ];
  XLSX.utils.book_append_sheet(wb, sectionSheet, "Votos por seção");

  XLSX.writeFile(
    wb,
    `dados-${slug(c.urn_name)}-${c.election.year}.xlsx`,
    { compression: true },
  );
}
