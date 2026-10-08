"""
Voto por SECAO: do zip do TSE ate tse_section_votes (votes + sections).

POR QUE NAO E O JOB DA API. `_process_votacao_secao` (utils/tse_sync.py) soma
tudo num dicionario dentro do processo da API antes de gravar. No RJ de 2026
sao 1,8 mi de pares candidato x local — perto de 1 GB num container de 768 MB,
e ele nem guarda a secao. Aqui a memoria e constante: as linhas cruas vao para
uma tabela de preparo por COPY e quem soma e o Postgres, em disco. (Mesma ideia
de scripts/corrigir_locais_zona.py, que ja fazia isso para o reparo da zona.)

DUAS METADES, que podem rodar em maquinas diferentes:

  1. `extrair` — zip do TSE -> arquivo .tsv.gz com
     (SQ_CANDIDATO, CD_MUNICIPIO, NR_ZONA, NR_LOCAL_VOTACAO, NR_SECAO, QT_VOTOS).
     So biblioteca padrao; nao importa nada da aplicacao. Ler o CSV (2,5 GB no
     RJ) e o que custa CPU, e a API tem 0,4 vCPU: da para fazer fora do
     servidor e subir so o resultado (35 MB).
  2. `preparar` + `copiar_*` + `casamento` + `gravar` + `conferir` — Postgres.

SO O 1o TURNO. `gravar` escreve em tse_section_votes, que e a tabela do 1o
turno; o 2o mora em tse_runoff_section_votes (migration 066) e ainda nao tem
carga por aqui. Depois de 25/10 o zip de cada UF traz os DOIS turnos: carregar
o 2o por este caminho trocaria o voto do 1o turno dos finalistas pelo do 2o.
O leitor aceita `turno=` (e funcao pura), mas o script so extrai o 1o.

REGRAS (as mesmas do importador, para o numero nao mudar de uma carga a outra):
  - so o turno pedido (o mesmo SQ aparece nos dois; somar dobraria o voto);
  - so linha com SQ_CANDIDATO (branco, nulo e legenda vem com -1);
  - o local e (ano, municipio, ZONA, numero). Linha cujo local nao existe com
    zona NAO entra: o numero da secao so e unico dentro da zona, e num local
    antigo (zona nula, varios locais fundidos) a secao 12 de uma zona se
    misturaria com a 12 de outra.
"""
from __future__ import annotations

import csv
import gzip
import io
import zipfile
from pathlib import Path
from typing import Callable, Iterable, Iterator

# (sq, cd_municipio, zona, local, secao, votos)
Linha = tuple[int, int, int, int, int, int]

PREPARO = "stg_votacao_secao"
_COLUNAS = "sq, cd_mun, zona, local_code, secao, votos"


# ------------------------------------------------------------------ extracao


def _csvs_do_zip(zf: zipfile.ZipFile) -> list[str]:
    # Em 2026 o TSE passou a empacotar um CSV por UF MAIS um `_BRASIL` com a
    # soma de todos; ler os dois dobra. Mesmo criterio de
    # tse_sync._sem_duplicata_nacional (copiado para este modulo nao arrastar
    # a aplicacao inteira quando roda fora do servidor).
    nomes = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    nacionais = [n for n in nomes if "_brasil" in n.lower()]
    return nacionais if nacionais and len(nomes) > len(nacionais) else nomes


def _inteiro(valor: str) -> int | None:
    try:
        return int(valor.strip())
    except (AttributeError, ValueError):
        return None


def linhas_do_zip(zip_path: Path, *, turno: int = 1) -> Iterator[Linha]:
    """Uma tupla por linha de candidato do CSV, sem somar nada."""
    with zipfile.ZipFile(zip_path) as zf:
        for nome in _csvs_do_zip(zf):
            with zf.open(nome) as bruto:
                leitor = csv.reader(
                    io.TextIOWrapper(bruto, encoding="latin-1", newline=""),
                    delimiter=";", quotechar='"',
                )
                col = {c.strip().upper(): n for n, c in enumerate(next(leitor))}
                i_turno = col.get("NR_TURNO")
                campos = [col[c] for c in (
                    "SQ_CANDIDATO", "CD_MUNICIPIO", "NR_ZONA",
                    "NR_LOCAL_VOTACAO", "NR_SECAO", "QT_VOTOS",
                )]
                largura = max(campos + [i_turno or 0]) + 1
                for row in leitor:
                    if len(row) < largura:      # linha em branco no fim do arquivo
                        continue
                    if i_turno is not None and (_inteiro(row[i_turno]) or 1) != turno:
                        continue
                    sq, mun, zona, local, secao, votos = (_inteiro(row[i]) for i in campos)
                    if not sq or sq < 0 or not mun or not zona or not local or not secao:
                        continue
                    if votos is None or votos < 0:
                        continue
                    yield sq, mun, zona, local, secao, votos


def extrair(zip_path: Path, destino: Path, *, turno: int = 1) -> dict[str, int]:
    """Grava as linhas no formato de texto do COPY (tabulacao), comprimido.

    O arquivo sai pronto para `copiar_arquivo`, que so repassa os bytes.
    """
    linhas = votos = 0
    candidatos: set[int] = set()
    with gzip.open(destino, "wt", encoding="ascii", newline="") as saida:
        for linha in linhas_do_zip(zip_path, turno=turno):
            saida.write("%d\t%d\t%d\t%d\t%d\t%d\n" % linha)
            linhas += 1
            votos += linha[5]
            candidatos.add(linha[0])
    return {"linhas": linhas, "votos": votos, "candidatos": len(candidatos)}


# ------------------------------------------------------------------ Postgres
#
# Tudo abaixo recebe um CURSOR do psycopg (conexao crua): o COPY nao passa
# pela sessao do SQLAlchemy.


def travar(cur) -> bool:
    """Uma carga por vez. Falso = ja ha outra rodando.

    A tabela de preparo tem nome fixo: sem a trava, a segunda rodada apagaria
    a tabela da primeira no meio do trabalho (e o `descartar` da primeira
    apagaria a da segunda). A trava e da SESSAO: solta sozinha quando a
    conexao fecha, inclusive se o processo morrer.
    """
    cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (PREPARO,))
    return bool(cur.fetchone()[0])


def destravar(cur) -> None:
    # Explicito: `close()` numa conexao do pool so a devolve ao pool, e a
    # trava de sessao continuaria presa nela enquanto o processo vivesse.
    cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (PREPARO,))


def preparar(cur) -> None:
    cur.execute(f"DROP TABLE IF EXISTS {PREPARO}")
    # UNLOGGED: e descartavel, e sem WAL a copia custa a metade.
    cur.execute(
        f"CREATE UNLOGGED TABLE {PREPARO} ("
        " sq bigint NOT NULL, cd_mun integer NOT NULL, zona integer NOT NULL,"
        " local_code integer NOT NULL, secao integer NOT NULL, votos integer NOT NULL)"
    )


def descartar(cur) -> None:
    cur.execute(f"DROP TABLE IF EXISTS {PREPARO}")


def copiar_linhas(
    cur, linhas: Iterable[Linha], *, avisar: Callable[[int], None] | None = None,
) -> int:
    n = 0
    with cur.copy(f"COPY {PREPARO} ({_COLUNAS}) FROM STDIN") as cp:
        for linha in linhas:
            cp.write_row(linha)
            n += 1
            if avisar and n % 1_000_000 == 0:
                avisar(n)
    cur.execute(f"ANALYZE {PREPARO}")
    return n


def copiar_arquivo(cur, arquivo: Path) -> int:
    """Repassa o .tsv.gz de `extrair` direto para o COPY (sem interpretar)."""
    with gzip.open(arquivo, "rb") as f, cur.copy(
        f"COPY {PREPARO} ({_COLUNAS}) FROM STDIN"
    ) as cp:
        while bloco := f.read(1 << 20):
            cp.write(bloco)
    cur.execute(f"ANALYZE {PREPARO}")
    cur.execute(f"SELECT count(*) FROM {PREPARO}")
    return cur.fetchone()[0]


# Candidato de 2026 daquela UF (ou nacional: presidente vota em toda UF) e o
# local COM zona. LEFT JOIN no casamento (para contar o que sobra), JOIN na
# gravacao (para so entrar o que casou).
_LIGACOES = """
    {j} JOIN (tse_candidates c JOIN tse_elections e
                ON e.id = c.election_id AND e.year = %(ano)s)
           ON c.sq_candidato = s.sq AND c.state IN (%(uf)s, 'BR')
    {j} JOIN tse_municipalities m ON m.tse_code = s.cd_mun AND m.state = %(uf)s
    {j} JOIN tse_voting_places vp
           ON vp.year = %(ano)s AND vp.municipality_id = m.id
          AND vp.zone = s.zona AND vp.local_code = s.local_code
"""


def casamento(cur, *, uf: str, ano: int) -> dict[str, int]:
    """Quanto do que subiu acha candidato, municipio e local no banco."""
    cur.execute(
        f"""
        SELECT count(*)                                AS linhas,
               coalesce(sum(s.votos), 0)               AS votos,
               count(*) FILTER (WHERE c.id IS NULL)    AS sem_candidato,
               count(*) FILTER (WHERE m.id IS NULL)    AS sem_municipio,
               count(*) FILTER (WHERE m.id IS NOT NULL AND vp.id IS NULL) AS sem_local,
               count(*) FILTER (WHERE c.id IS NOT NULL AND vp.id IS NOT NULL) AS casam,
               coalesce(sum(s.votos) FILTER (
                   WHERE c.id IS NOT NULL AND vp.id IS NOT NULL), 0) AS votos_que_casam
        FROM {PREPARO} s
        {_LIGACOES.format(j="LEFT")}
        """,
        {"uf": uf, "ano": ano},
    )
    nomes = [d.name for d in cur.description]
    return dict(zip(nomes, (int(v) for v in cur.fetchone())))


_SQL_GRAVAR = f"""
INSERT INTO tse_section_votes AS sv
    (id, candidate_id, voting_place_id, votes, sections, created_at, updated_at)
SELECT gen_random_uuid(), a.candidate_id, a.voting_place_id,
       a.votos, a.secoes, now(), now()
FROM (
    SELECT c.id AS candidate_id, vp.id AS voting_place_id,
           sum(s.votos)::integer AS votos,
           jsonb_object_agg(s.secao::text, s.votos)
               FILTER (WHERE s.votos > 0) AS secoes
    FROM (
        SELECT sq, cd_mun, zona, local_code, secao, sum(votos)::integer AS votos
        FROM {PREPARO}
        GROUP BY sq, cd_mun, zona, local_code, secao
    ) s
    {_LIGACOES.format(j="")}
    GROUP BY c.id, vp.id
) a
ON CONFLICT (candidate_id, voting_place_id) DO UPDATE
   SET votes = EXCLUDED.votes, sections = EXCLUDED.sections, updated_at = now()
 WHERE sv.votes IS DISTINCT FROM EXCLUDED.votes
    OR sv.sections IS DISTINCT FROM EXCLUDED.sections
"""


def gravar(cur, *, uf: str, ano: int) -> int:
    """Soma por (candidato, local), monta o detalhe por secao e grava.

    Dois niveis de soma: primeiro por secao, depois por local. O primeiro e
    seguro contra linha repetida no arquivo — sem ele, a secao repetida
    contaria duas vezes em `votes` e uma so em `sections`.

    Rodar de novo com o mesmo arquivo nao escreve nada (o WHERE do upsert).
    Devolve quantas linhas foram inseridas ou alteradas.

    NAO apaga par (candidato, local) que exista no banco e nao esteja no
    arquivo: ele fica com o voto antigo e sem detalhe, e `conferir` o conta em
    `pares_com_voto_sem_detalhe`. Destino fixo: a tabela do 1o TURNO.
    """
    cur.execute(_SQL_GRAVAR, {"uf": uf, "ano": ano})
    return cur.rowcount


def plano_de_gravar(cur, *, uf: str, ano: int) -> list[str]:
    """O plano do Postgres para `gravar`, SEM executar (EXPLAIN puro).

    Serve ao ensaio: prova que o comando e valido naquele banco e mostra
    quantas linhas o planejador espera, antes de qualquer escrita.
    """
    cur.execute("EXPLAIN " + _SQL_GRAVAR, {"uf": uf, "ano": ano})
    return [linha[0] for linha in cur.fetchall()]


def conferir(cur, *, uf: str, ano: int) -> dict[str, int]:
    """A prova depois da carga, lida do que ficou GRAVADO.

    - `detalhe_nao_fecha`: linhas em que a soma das secoes difere de `votes`
      (tem de ser zero);
    - `pares_com_voto_sem_detalhe`: par com voto e sem secao — sobra de uma
      carga anterior que o arquivo de agora nao trouxe, ou carga pelo job da
      API (tem de ser zero depois de uma carga por aqui);
    - `candidatos_diferentes`: candidatos DA UF em que a soma por local difere
      do total oficial (tem de ser zero). Ficam fora dessa conta, e aparecem
      contados: quem nao tem total oficial (`candidatos_sem_total`) e o
      candidato nacional (`candidatos_nacionais` — presidente: o total dele e
      do pais, a soma aqui e de uma UF).
    """
    escopo = """
        FROM tse_section_votes sv
        JOIN tse_voting_places vp ON vp.id = sv.voting_place_id AND vp.year = %(ano)s
        JOIN tse_municipalities m ON m.id = vp.municipality_id AND m.state = %(uf)s
    """
    p = {"uf": uf, "ano": ano}
    cur.execute(
        f"""
        SELECT count(*)                                         AS pares,
               count(*) FILTER (WHERE sv.sections IS NOT NULL)  AS pares_com_detalhe,
               count(*) FILTER (WHERE sv.sections IS NULL AND sv.votes > 0)
                                                                AS pares_com_voto_sem_detalhe,
               count(DISTINCT sv.voting_place_id)               AS locais,
               coalesce(sum(sv.votes), 0)                       AS votos,
               coalesce(sum((SELECT count(*) FROM jsonb_object_keys(sv.sections))), 0)
                                                                AS linhas_de_secao,
               count(*) FILTER (WHERE sv.sections IS NOT NULL AND sv.votes <> (
                   SELECT coalesce(sum(j.v::integer), 0)
                   FROM jsonb_each_text(sv.sections) AS j(k, v)))  AS detalhe_nao_fecha
        {escopo}
        """,
        p,
    )
    nomes = [d.name for d in cur.description]
    saida = dict(zip(nomes, (int(v) for v in cur.fetchone())))

    cur.execute(
        f"""
        WITH por_candidato AS (
            SELECT sv.candidate_id, sum(sv.votes) AS soma
            {escopo}
            GROUP BY sv.candidate_id
        )
        SELECT count(*)                                              AS candidatos,
               count(*) FILTER (WHERE c.total_votes IS NULL)         AS candidatos_sem_total,
               count(*) FILTER (WHERE c.state <> %(uf)s)             AS candidatos_nacionais,
               count(*) FILTER (WHERE c.total_votes IS NOT NULL
                                  AND c.state = %(uf)s
                                  AND p.soma <> c.total_votes)       AS candidatos_diferentes
        FROM por_candidato p JOIN tse_candidates c ON c.id = p.candidate_id
        """,
        p,
    )
    nomes = [d.name for d in cur.description]
    saida.update(zip(nomes, (int(v) for v in cur.fetchone())))
    return saida
