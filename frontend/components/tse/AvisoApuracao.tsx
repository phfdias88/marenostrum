import { ANO_EM_APURACAO } from "@/lib/elections";

const CARGOS_DE_DEPUTADO = ["6", "7", "8"];

/**
 * Aviso único de que a eleição do ano ainda está fechando.
 *
 * Existe para as telas não afirmarem mais do que o dado sustenta: enquanto o
 * TSE não fecha um cargo, "eleitos" vem incompleto, e o voto de deputado por
 * município entra depois do de presidente, governador e senador.
 *
 * Some sozinho quando ANO_EM_APURACAO vira null (lib/elections.ts) — é o único
 * lugar a mexer quando o resultado consolidado do TSE entrar.
 */
export function AvisoApuracao({
  year,
  office,
  className,
}: {
  year: string | number;
  /** Código do cargo; com deputado, o aviso inclui a ressalva do voto por cidade. */
  office?: string;
  className?: string;
}) {
  if (ANO_EM_APURACAO == null || String(year) !== String(ANO_EM_APURACAO)) return null;
  const deputado = office != null && CARGOS_DE_DEPUTADO.includes(office);
  return (
    <p className={"text-xs text-amber-600 dark:text-amber-400 " + (className ?? "")}>
      {ANO_EM_APURACAO}: apuração em andamento. A situação (eleito) só aparece
      quando o TSE fecha o cargo, e quem foi a 2º turno ainda não tem eleito.
      {deputado &&
        " O voto de deputado por município ainda está sendo carregado: totais por partido e por cidade podem estar parciais."}
    </p>
  );
}
