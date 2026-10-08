#!/usr/bin/env python3
"""
Carrega o voto por SECAO de uma UF (bairro, local e a aba "por secao" da
planilha), sem passar pelo job da API.

O job da API (`votacao_secao_<ano>_<UF>`) soma o arquivo inteiro na memoria do
processo que atende o site e nao guarda a secao. Este script deixa o Postgres
somar (memoria constante) e preenche tse_section_votes.votes E .sections.
As regras estao em app/services/votacao_secao.py.

SO O 1o TURNO. O destino e a tabela do 1o turno; o zip publicado depois do 2o
turno traz os dois, e daqui so sai o 1o (o 2o mora em tse_runoff_section_votes
e ainda nao tem carga por este caminho).

1) EXTRAIR — em qualquer maquina que tenha o zip (le o CSV inteiro; no RJ sao
   2,5 GB e um minuto de CPU, melhor fora do servidor):

    python backend/scripts/carregar_votacao_secao.py extrair \\
        --zip votacao_secao_2026_RJ.zip --saida secoes_2026_RJ.tsv.gz

   ANTES: conferir que o zip e o certo. A CDN do TSE ja serviu duas versoes do
   mesmo arquivo no mesmo dia (RJ 2026: 130 MB e 290 MB).

2) SUBIR o .tsv.gz para o volume tse_drop do container da API.

3) ENSAIAR — sem --aplicar nada e gravado em tse_section_votes; so mostra
   quanto do arquivo acha candidato, municipio e local no banco:

    docker compose exec -T -e PYTHONPATH=/app api python - carregar \\
        --uf RJ --ano 2026 --arquivo /var/marenostrum/tse_drop/secoes_2026_RJ.tsv.gz \\
        < backend/scripts/carregar_votacao_secao.py

4) PARA VALER (destacado do terminal; no RJ leva uns 15 minutos):

    nohup docker compose exec -T -e PYTHONPATH=/app api python - carregar \\
        --uf RJ --ano 2026 --arquivo /var/marenostrum/tse_drop/secoes_2026_RJ.tsv.gz \\
        --aplicar < backend/scripts/carregar_votacao_secao.py \\
        > ~/carregar-secao-RJ.log 2>&1 &

   Recusa gravar se alguma linha do arquivo nao casar com o banco (candidato,
   municipio ou local faltando), a menos de --mesmo-assim. Ao fim confere o que
   ficou gravado: a soma das secoes de cada linha tem de ser o voto do local, a
   soma por local de cada candidato tem de ser o total oficial, e nao pode
   sobrar par com voto e sem detalhe.
   Pode rodar de novo: so regrava o que mudou.

DEPOIS (o script nao alcanca estes caches):
    POST /api/v1/tse/ingest/cache-clear
    docker compose exec -T nginx sh -c 'rm -rf /var/cache/nginx/tse/*'

Tambem aceita --zip no lugar de --arquivo (le o zip dentro do container: mais
simples, e bem mais lento). `conferir` repete so a prova, sem arquivo.

NAO rodar junto com sync do TSE, backup ou captura da apuracao. Duas cargas ao
mesmo tempo nao rodam: a segunda sai avisando.
Sai com codigo 1 se a conferencia acusar diferenca, 2 se recusar a gravar.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    # Rodando pelo caminho do arquivo, o Python so enxerga backend/scripts.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
except NameError:
    # Pelo STDIN (`python - ...`, como no servidor) nao existe __file__; la o
    # PYTHONPATH=/app ja resolve.
    pass

from app.services import votacao_secao as vs  # noqa: E402


def _n(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def _conexao():
    # So aqui a aplicacao e importada: `extrair` roda sem banco e sem .env.
    from app.core.database import engine

    conexao = engine.raw_connection()
    with conexao.cursor() as cur:
        # A soma le milhoes de linhas e o upsert leva minutos; o SET vale para
        # esta conexao, que e a mesma do comeco ao fim.
        cur.execute("SET statement_timeout = 0")
        cur.execute("SET lock_timeout = '10s'")
    conexao.commit()
    return conexao


def _mostrar_prova(prova: dict[str, int]) -> bool:
    print(f"  pares candidato x local: {_n(prova['pares'])} "
          f"({_n(prova['pares_com_detalhe'])} com detalhe por secao) "
          f"em {_n(prova['locais'])} locais", flush=True)
    print(f"  votos: {_n(prova['votos'])} | linhas de secao: {_n(prova['linhas_de_secao'])}")
    print(f"  pares com voto e SEM detalhe: {_n(prova['pares_com_voto_sem_detalhe'])}")
    print(f"  linhas em que a soma das secoes difere do voto do local: "
          f"{_n(prova['detalhe_nao_fecha'])}")
    print(f"  candidatos: {_n(prova['candidatos'])} | soma por local diferente do "
          f"total oficial: {_n(prova['candidatos_diferentes'])}")
    print(f"  fora dessa comparacao: {_n(prova['candidatos_sem_total'])} sem total "
          f"oficial, {_n(prova['candidatos_nacionais'])} nacionais (presidente)")
    confere = (
        prova["detalhe_nao_fecha"] == 0
        and prova["candidatos_diferentes"] == 0
        # Par com voto e sem secao = sobra de carga antiga que o arquivo de
        # agora nao trouxe (o voto dele pode estar velho) ou carga pelo job.
        and prova["pares_com_voto_sem_detalhe"] == 0
    )
    print("CONFERE" if confere else "NAO CONFERE", flush=True)
    return confere


def _extrair(args) -> int:
    t = time.perf_counter()
    r = vs.extrair(args.zip, args.saida)
    print(f"{args.saida}: {_n(r['linhas'])} linhas, {_n(r['votos'])} votos, "
          f"{_n(r['candidatos'])} candidatos ({time.perf_counter() - t:.0f}s)")
    return 0


def _carregar(args) -> int:
    conexao = _conexao()
    travada = False
    try:
        with conexao.cursor() as cur:
            travada = vs.travar(cur)
            conexao.commit()
            if not travada:
                print("RECUSADO: ja ha outra carga de voto por secao rodando.",
                      file=sys.stderr)
                return 2

            t = time.perf_counter()
            vs.preparar(cur)
            if args.arquivo:
                copiadas = vs.copiar_arquivo(cur, args.arquivo)
            else:
                copiadas = vs.copiar_linhas(
                    cur, vs.linhas_do_zip(args.zip),
                    avisar=lambda n: print(f"  {_n(n)} linhas copiadas", flush=True),
                )
            conexao.commit()
            print(f"preparo: {_n(copiadas)} linhas ({time.perf_counter() - t:.0f}s)", flush=True)

            c = vs.casamento(cur, uf=args.uf, ano=args.ano)
            print(f"  casam {_n(c['casam'])} de {_n(c['linhas'])} linhas "
                  f"({_n(c['votos_que_casam'])} de {_n(c['votos'])} votos)")
            print(f"  sem candidato {_n(c['sem_candidato'])} | sem municipio "
                  f"{_n(c['sem_municipio'])} | sem local com zona {_n(c['sem_local'])}",
                  flush=True)
            sobra = c["linhas"] - c["casam"]

            if not args.aplicar:
                # So o plano (EXPLAIN nao executa): prova que o comando de
                # gravacao e aceito por este banco e mostra o tamanho esperado.
                plano = vs.plano_de_gravar(cur, uf=args.uf, ano=args.ano)
                conexao.rollback()
                # Inteiro: e aqui que se ve, antes de gravar, se o planejador
                # escolheu um laco aninhado sobre milhoes de linhas.
                print("  plano da gravacao (nao executado):")
                for linha in plano:
                    print("    " + linha)
                print("ENSAIO: nada gravado em tse_section_votes (use --aplicar).")
                return 0
            if c["casam"] == 0:
                print("ERRO: nenhuma linha casa — UF/ano errados, ou faltam os "
                      "locais de votacao daquele ano.", file=sys.stderr)
                return 2
            if sobra and not args.mesmo_assim:
                print(f"RECUSADO: {_n(sobra)} linhas do arquivo nao casam com o banco. "
                      "Veja o que falta acima; --mesmo-assim grava so o que casa.",
                      file=sys.stderr)
                return 2

            t = time.perf_counter()
            gravadas = vs.gravar(cur, uf=args.uf, ano=args.ano)
            conexao.commit()
            print(f"gravadas ou alteradas: {_n(gravadas)} linhas "
                  f"({time.perf_counter() - t:.0f}s)", flush=True)
            cur.execute("ANALYZE tse_section_votes")
            conexao.commit()

            confere = _mostrar_prova(vs.conferir(cur, uf=args.uf, ano=args.ano))
            print("Falta limpar o cache da API (POST /tse/ingest/cache-clear) e o "
                  "do nginx (rm -rf /var/cache/nginx/tse/*).")
            return 0 if confere else 1
    finally:
        # A tabela de preparo nao sobrevive a rodada, de pe ou caida — mas so
        # quem pegou a trava mexe nela: a de outra rodada nao e desta.
        try:
            conexao.rollback()
            if travada:
                with conexao.cursor() as cur:
                    vs.descartar(cur)
                    vs.destravar(cur)
                conexao.commit()
        except Exception as erro:  # noqa: BLE001
            # Nao deixa a faxina trocar o resultado da carga (ja commitada) por
            # um traceback: a tabela e UNLOGGED e a proxima rodada a recria.
            print(f"aviso: nao consegui apagar a tabela de preparo ({erro})",
                  file=sys.stderr)
        finally:
            conexao.close()


def _conferir(args) -> int:
    conexao = _conexao()
    try:
        with conexao.cursor() as cur:
            return 0 if _mostrar_prova(vs.conferir(cur, uf=args.uf, ano=args.ano)) else 1
    finally:
        conexao.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Voto por secao de uma UF (1o turno), somado no Postgres.")
    sub = p.add_subparsers(dest="comando", required=True)

    e = sub.add_parser("extrair", help="zip do TSE -> .tsv.gz (nao usa o banco)")
    e.add_argument("--zip", type=Path, required=True)
    e.add_argument("--saida", type=Path, required=True)
    e.set_defaults(rodar=_extrair)

    c = sub.add_parser("carregar", help="arquivo -> tse_section_votes (ensaio sem --aplicar)")
    c.add_argument("--uf", required=True, type=str.upper)
    c.add_argument("--ano", required=True, type=int)
    origem = c.add_mutually_exclusive_group(required=True)
    origem.add_argument("--arquivo", type=Path, help=".tsv.gz gerado por `extrair`")
    origem.add_argument("--zip", type=Path, help="zip do TSE (le aqui mesmo, mais lento)")
    c.add_argument("--aplicar", action="store_true", help="grava (sem isto, so ensaia)")
    c.add_argument("--mesmo-assim", action="store_true",
                   help="grava o que casa mesmo havendo linha sem par no banco")
    c.set_defaults(rodar=_carregar)

    v = sub.add_parser("conferir", help="repete a prova no que esta gravado")
    v.add_argument("--uf", required=True, type=str.upper)
    v.add_argument("--ano", required=True, type=int)
    v.set_defaults(rodar=_conferir)

    args = p.parse_args()
    return args.rodar(args)


if __name__ == "__main__":
    sys.exit(main())
