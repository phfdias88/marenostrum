"""Eleicao em apuracao.

Enquanto houver uma, o dado do TSE deixa de ser "historico e imutavel" — muda a
cada dois minutos — e as regras de cache pensadas para o historico passam a
mostrar numero velho. O caso que revelou isto: a tela da bancada exibia 22
senadores eleitos quando o banco ja tinha 30, porque o navegador reaproveitava
por ate 24 horas a resposta antiga (stale-while-revalidate).

Trocar para None quando o resultado consolidado do TSE for importado. O
frontend tem a constante gemea em `frontend/lib/elections.ts` (ANO_EM_APURACAO),
que desliga os avisos de apuracao parcial nas telas.
"""

ANO_EM_APURACAO: int | None = 2026

# Cache-Control das respostas de /tse.
#
# Historico: 5 minutos frescos e ate 24h servindo a copia antiga enquanto
# revalida — navegacao instantanea, e o dado nao muda mesmo.
CACHE_HISTORICO = "public, max-age=300, stale-while-revalidate=86400"
# Apuracao: 1 minuto e SEM stale-while-revalidate. Com ele, quem volta a uma
# tela ve primeiro o numero de horas atras; so a visita seguinte traz o novo.
CACHE_NA_APURACAO = "public, max-age=60"


def cache_do_tse() -> str:
    return CACHE_HISTORICO if ANO_EM_APURACAO is None else CACHE_NA_APURACAO
