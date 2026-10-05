#!/usr/bin/env python3
"""
Captura os resultados AO VIVO do TSE durante a apuracao.

Le do canal de divulgacao (resultados.tse.jus.br, JSON) — o mesmo que alimenta a
pagina de resultados do TSE — e grava nas tabelas que o resto do sistema ja usa.
O zip consolidado do portal de dados so e preenchido dias depois; ver a
explicacao completa em app/services/tse_live.py.

PODE RODAR QUANTAS VEZES QUISER. Cada passada substitui os numeros pelo
acumulado mais recente; nada e somado.

USO (dentro do container da API, PYTHONPATH=/app):

  # 1. uma vez, antes do resultado: cria os candidatos a partir do registro
  python apuracao_ao_vivo.py --candidatos

  # 2. a cada passada da noite
  python apuracao_ao_vivo.py --totais                 # total por candidato, Brasil
  python apuracao_ao_vivo.py --municipios RJ          # voto por municipio do RJ
  python apuracao_ao_vivo.py --totais --municipios RJ # os dois

ORDEM DE PRIORIDADE se o tempo apertar: --totais e barato (cerca de 140
arquivos) e ja diz quem esta eleito no pais inteiro. --municipios e o detalhe
territorial e custa um arquivo por municipio por cargo.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import func, select, text

from app.core.database import SessionLocal
from app.services import comparecimento
from app.services import tse_live as live
from app.utils.tse_sync import ALL_UFS, CACHE_DIR, DATASETS, download_zip

ANO = 2026
ESTADO = CACHE_DIR / "_ao_vivo_status.json"


@contextmanager
def trava_compartilhada(ano: int):
    """Trava que as capturas ao vivo dividem entre si e a carga consolidada nao.

    Os totais (32s) e os municipios (4,5 min) gravam em tabelas diferentes e
    podem rodar juntos. Com a trava exclusiva os totais eram pulados enquanto a
    passada de municipios rodava, e o placar ficava ate 12 minutos atrasado —
    medido na noite do 1o turno, com a apuracao ja correndo.

    A carga consolidada pega a MESMA chave em modo exclusivo
    (tse_live.trava_do_ano), entao continua nunca escrevendo junto com a gente:
    no Postgres, trava compartilhada e trava exclusiva se excluem.
    """
    from app.core.database import engine

    if engine.dialect.name != "postgresql":
        yield True
        return
    chave = 7_400_000 + ano                      # mesma chave de tse_live
    conn = engine.connect()
    pegou = False
    try:
        pegou = bool(conn.execute(
            text("SELECT pg_try_advisory_lock_shared(:k)"), {"k": chave}).scalar())
        yield pegou
    finally:
        if pegou:
            conn.execute(text("SELECT pg_advisory_unlock_shared(:k)"), {"k": chave})
        conn.close()


def gravar_status(novo: dict) -> None:
    """Junta o resultado desta passada ao que ja estava gravado.

    Totais e municipios rodam em cadencias diferentes. Se cada um sobrescrevesse
    o arquivo inteiro, quem consulta o andamento veria ora um, ora outro.
    """
    atual: dict = {}
    try:
        atual = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    for chave in ("totais", "municipios", "candidatos", "eleicoes"):
        if chave in novo:
            atual[chave] = novo[chave]
            atual[f"{chave}_em"] = novo["quando"]
    atual["quando"] = novo["quando"]
    atual["data"] = novo["data"]
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ESTADO)            # troca atomica: quem le nunca ve arquivo pela metade

# Cargo -> em que arquivo o TOTAL do candidato esta. Presidente e nacional;
# os demais sao por UF.
CARGO_NACIONAL = 1

# Quantos downloads ao mesmo tempo. A primeira passada, sequencial, levou 10,6
# minutos para 688 arquivos — quase tudo espera de rede. Oito em paralelo
# derruba isso sem virar martelada no TSE em dia de eleicao.
PARALELOS = 8
# Municipios baixados e gravados por vez na varredura (ver passo_municipios).
LOTE_DE_MUNICIPIOS = 40


def cargo_existe_na_uf(cargo: int, uf: str) -> bool:
    """Deputado distrital (8) so existe no DF; estadual (7), em todo lugar MENOS
    la. Pedir a combinacao impossivel e um 404 garantido — 119 requisicoes
    jogadas fora por passada."""
    uf = uf.upper()
    if cargo == 8:
        return uf == "DF"
    if cargo == 7:
        return uf != "DF"
    return True


def baixar_varios(cliente: httpx.Client, urls: list[str]) -> list[dict | None]:
    """Baixa em paralelo, devolve na MESMA ordem das urls. So a rede e paralela;
    quem grava no banco continua sendo uma thread so."""
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=PARALELOS) as pool:
        return list(pool.map(lambda u: live.baixar(cliente, u), urls))


def descobrir_eleicoes(cliente: httpx.Client, data: str) -> list[dict]:
    """Eleicoes ordinarias do pleito daquela data, lidas do proprio TSE.

    Ler do config em vez de fixar 6257/6259 no codigo faz o 2o turno funcionar
    sem mexer em nada: no dia 25/10 o pleito e outro e os codigos tambem.
    """
    cfg = live.baixar(cliente, f"{live.BASE}/comum/config/ele-c.json")
    if not cfg:
        raise SystemExit("ERRO: nao consegui ler o config de eleicoes do TSE.")
    achadas = []
    for pleito in cfg.get("pl", []):
        if pleito.get("dt") != data:
            continue
        for e in pleito.get("e", []):
            # tp 8 = federal, tp 1 = estadual. O resto e suplementar, consulta
            # popular ou municipal avulsa, que nao nos interessa aqui.
            if str(e.get("tp")) not in ("1", "8"):
                continue
            cargos = sorted({
                int(c["cd"]) for a in e.get("abr", []) for c in a.get("cp", [])
                if str(c.get("cd", "")).isdigit()
            })
            achadas.append({
                "codigo": int(e["cd"]), "nome": e.get("nm", ""),
                "cargos": [c for c in cargos if c in live.CARGOS_COM_VOTO],
            })
    return achadas


def passo_candidatos(db) -> dict:
    meta = DATASETS[f"consulta_cand_{ANO}"]
    destino = CACHE_DIR / f"consulta_cand_{ANO}.zip"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    download_zip(meta["url"], destino, max_mb=meta.get("max_mb"))
    return live.importar_candidatos_do_registro(db, destino, ano=ANO)


def passo_totais(db, cliente, eleicoes, candidatos) -> dict:
    """Total e situacao de cada candidato, pelo arquivo de nivel UF ou BR.

    Do mesmo arquivo sai o comparecimento (abstencao, brancos, nulos e quanto
    da apuracao ja entrou), gravado em tse_turnout.
    """
    # (uf, cargo, url, vale_para_o_total_do_candidato)
    alvos: list[tuple[str, int, str, bool]] = []
    for el in eleicoes:
        for cargo in el["cargos"]:
            nacional = cargo == CARGO_NACIONAL
            areas = ["br"] if nacional else [u.lower() for u in ALL_UFS]
            for uf in areas:
                if uf != "br" and not cargo_existe_na_uf(cargo, uf):
                    continue
                alvos.append(
                    (uf, cargo, live.url_do_arquivo(ANO, el["codigo"], uf, cargo), True))
            if nacional:
                # Presidente por UF: SO para o comparecimento. O voto do
                # candidato ali e o da UF — gravar como total faria o placar
                # nacional mostrar a votacao de um estado so.
                for uf in ALL_UFS:
                    alvos.append((
                        uf.lower(), cargo,
                        live.url_do_arquivo(ANO, el["codigo"], uf.lower(), cargo),
                        False,
                    ))

    dados = baixar_varios(cliente, [a[2] for a in alvos])

    ok = falhou = atualizados = 0
    andamento_por_uf: dict[str, dict] = {}
    for (uf, cargo, _url, vale_total), dado in zip(alvos, dados):
        if dado is None:
            falhou += 1
            continue
        ok += 1
        and_ = live.andamento(dado)
        numeros = comparecimento.do_feed(dado)
        if numeros is not None:
            comparecimento.gravar(
                db, ano=ANO, turno=and_["turno"], cargo=cargo, uf=uf,
                numeros=numeros,
            )
        if not vale_total:
            continue
        atualizados += live.gravar_totais_do_candidato(
            db, candidatos_por_sq=candidatos, turno=and_["turno"],
            candidatos=live.extrair_candidatos(dado),
        )
        andamento_por_uf.setdefault(uf.upper(), {})[str(cargo)] = {
            "pct_secoes": and_["pct_secoes"], "gerado_em": and_["gerado_em"],
        }
    db.commit()
    return {"arquivos_ok": ok, "arquivos_sem_resposta": falhou,
            "candidatos_atualizados": atualizados, "andamento": andamento_por_uf}


def passo_municipios(db, cliente, eleicoes, candidatos, ufs, so_cargos=None) -> dict:
    """Voto por municipio. Um arquivo por municipio por cargo.

    `so_cargos` restringe aos cargos pedidos. Existe porque o custo e muito
    desigual: presidente, governador e senador sao arquivos de poucos KB e uma
    duzia de candidatos — da para varrer os 5.570 municipios do pais. Deputado
    traz a lista inteira da UF em CADA municipio (mais de mil nomes), e o Brasil
    todo passaria de dez milhoes de linhas.
    """
    ok = falhou = gravados = sem_candidato = 0
    for uf in ufs:
        munis = list(live.mapa_de_municipios(db, uf).items())
        for el in eleicoes:
            for cargo in el["cargos"]:
                if so_cargos and cargo not in so_cargos:
                    continue
                if not cargo_existe_na_uf(cargo, uf):
                    continue
                # Em LOTES, e nao a UF inteira de uma vez. O arquivo de deputado
                # traz a lista completa da UF em cada municipio (~1 MB ja
                # lido): os 853 de MG juntos passam de 1 GB, e o container da
                # API tem 768 MB — a varredura derrubaria a propria API.
                for i in range(0, len(munis), LOTE_DE_MUNICIPIOS):
                    lote = munis[i : i + LOTE_DE_MUNICIPIOS]
                    urls = [live.url_do_arquivo(ANO, el["codigo"], uf, cargo, cod)
                            for cod, _mid in lote]
                    for (_cod, mid), dado in zip(lote, baixar_varios(cliente, urls)):
                        if dado is None:
                            falhou += 1
                            continue
                        ok += 1
                        g, p = live.gravar_votos_do_municipio(
                            db, candidatos_por_sq=candidatos, municipio_id=mid,
                            turno=live.andamento(dado)["turno"],
                            candidatos=live.extrair_candidatos(dado),
                        )
                        gravados += g
                        sem_candidato += p
                    # Commit por lote: solta as travas de linha cedo (o cron do
                    # RJ grava as mesmas linhas) e nao deixa um milhao de
                    # linhas pendurado numa transacao so.
                    db.commit()
                print(f"  {uf} eleicao {el['codigo']} cargo {cargo}: "
                      f"{ok} arquivos, {gravados} linhas", flush=True)
    return {"arquivos_ok": ok, "arquivos_sem_resposta": falhou,
            "linhas_gravadas": gravados, "votos_sem_candidato": sem_candidato}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--candidatos", action="store_true")
    p.add_argument("--totais", action="store_true")
    p.add_argument("--municipios", default="",
                   help="UFs separadas por virgula, ou TODAS")
    p.add_argument("--cargos", default="",
                   help="so estes cargos na passada de municipios, ex: 1,3,5")
    p.add_argument("--data", default="04/10/2026", help="data do pleito no TSE")
    p.add_argument("--forcar", action="store_true",
                   help="grava mesmo se a carga consolidada ja entrou")
    args = p.parse_args()

    inicio = time.time()
    db = SessionLocal()
    # is_local=False: vale para a SESSAO. Com True valia so ate o primeiro
    # commit, e do segundo cargo em diante a varredura rodava sob o timeout do
    # servidor — uma espera por trava de linha bastava para derrubar a passada.
    db.execute(select(func.set_config("statement_timeout", "0", False)))
    db.commit()
    saida: dict = {"quando": datetime.now(timezone.utc).isoformat(), "data": args.data}

    if args.candidatos:
        saida["candidatos"] = passo_candidatos(db)

    if args.totais or args.municipios:
        motivo = live.consolidado_ja_entrou(db, ANO)
        if motivo and not args.forcar:
            print(f"PULADO: {motivo}. O numero oficial manda; a captura ao vivo "
                  f"nao escreve por cima. (--forcar para ignorar)")
            return 0
        candidatos = live.mapa_de_candidatos(db, ANO)
        if not candidatos:
            print("ERRO: nenhum candidato de 2026 no banco. Rode --candidatos antes.",
                  file=sys.stderr)
            return 2
        cliente_http = httpx.Client(
            timeout=30, headers=live.CABECALHOS, follow_redirects=True)
        with trava_compartilhada(ANO) as livre, cliente_http as cliente:
            if not livre:
                print("PULADO: a carga consolidada esta gravando agora. "
                      "Tento de novo na proxima passada.")
                return 0
            eleicoes = descobrir_eleicoes(cliente, args.data)
            if not eleicoes:
                print(f"ERRO: o TSE nao lista eleicao ordinaria em {args.data}.",
                      file=sys.stderr)
                return 2
            saida["eleicoes"] = eleicoes
            if args.totais:
                saida["totais"] = passo_totais(db, cliente, eleicoes, candidatos)
            if args.municipios:
                if args.municipios.strip().upper() == "TODAS":
                    ufs = list(ALL_UFS)
                else:
                    ufs = [u.strip().upper() for u in args.municipios.split(",")
                           if u.strip()]
                so_cargos = {int(c) for c in args.cargos.split(",") if c.strip().isdigit()}
                saida["municipios"] = passo_municipios(
                    db, cliente, eleicoes, candidatos, ufs, so_cargos or None)

    saida["segundos"] = round(time.time() - inicio, 1)
    try:
        gravar_status(saida)
    except OSError as exc:
        print(f"AVISO: nao gravei o status ({exc})", file=sys.stderr)

    resumo = {k: v for k, v in saida.items() if k != "eleicoes"}
    if "totais" in resumo:
        resumo["totais"] = {k: v for k, v in resumo["totais"].items() if k != "andamento"}
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
