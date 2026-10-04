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
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.services import tse_live as live
from app.utils.tse_sync import ALL_UFS, CACHE_DIR, DATASETS, download_zip

ANO = 2026
ESTADO = CACHE_DIR / "_ao_vivo_status.json"

# Cargo -> em que arquivo o TOTAL do candidato esta. Presidente e nacional;
# os demais sao por UF.
CARGO_NACIONAL = 1

# Quantos downloads ao mesmo tempo. A primeira passada, sequencial, levou 10,6
# minutos para 688 arquivos — quase tudo espera de rede. Oito em paralelo
# derruba isso sem virar martelada no TSE em dia de eleicao.
PARALELOS = 8


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
    """Total e situacao de cada candidato, pelo arquivo de nivel UF ou BR."""
    alvos: list[tuple[str, int, str]] = []          # (uf, cargo, url)
    for el in eleicoes:
        for cargo in el["cargos"]:
            areas = ["br"] if cargo == CARGO_NACIONAL else [u.lower() for u in ALL_UFS]
            for uf in areas:
                if uf != "br" and not cargo_existe_na_uf(cargo, uf):
                    continue
                alvos.append(
                    (uf, cargo, live.url_do_arquivo(ANO, el["codigo"], uf, cargo)))

    dados = baixar_varios(cliente, [a[2] for a in alvos])

    ok = falhou = atualizados = 0
    andamento_por_uf: dict[str, dict] = {}
    for (uf, cargo, _url), dado in zip(alvos, dados):
        if dado is None:
            falhou += 1
            continue
        ok += 1
        and_ = live.andamento(dado)
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


def passo_municipios(db, cliente, eleicoes, candidatos, ufs) -> dict:
    """Voto por municipio. Um arquivo por municipio por cargo."""
    ok = falhou = gravados = sem_candidato = 0
    for uf in ufs:
        munis = list(live.mapa_de_municipios(db, uf).items())
        for el in eleicoes:
            for cargo in el["cargos"]:
                if not cargo_existe_na_uf(cargo, uf):
                    continue
                urls = [live.url_do_arquivo(ANO, el["codigo"], uf, cargo, cod)
                        for cod, _mid in munis]
                for (_cod, mid), dado in zip(munis, baixar_varios(cliente, urls)):
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
                db.commit()
                print(f"  {uf} eleicao {el['codigo']} cargo {cargo}: "
                      f"{ok} arquivos, {gravados} linhas", flush=True)
    return {"arquivos_ok": ok, "arquivos_sem_resposta": falhou,
            "linhas_gravadas": gravados, "votos_sem_candidato": sem_candidato}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--candidatos", action="store_true")
    p.add_argument("--totais", action="store_true")
    p.add_argument("--municipios", default="", help="UFs separadas por virgula")
    p.add_argument("--data", default="04/10/2026", help="data do pleito no TSE")
    p.add_argument("--forcar", action="store_true",
                   help="grava mesmo se a carga consolidada ja entrou")
    args = p.parse_args()

    inicio = time.time()
    db = SessionLocal()
    db.execute(select(func.set_config("statement_timeout", "0", True)))
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
        with live.trava_do_ano(ANO, esperar=False) as livre,                 httpx.Client(timeout=30, headers=live.CABECALHOS,
                             follow_redirects=True) as cliente:
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
                ufs = [u.strip().upper() for u in args.municipios.split(",") if u.strip()]
                saida["municipios"] = passo_municipios(
                    db, cliente, eleicoes, candidatos, ufs)

    saida["segundos"] = round(time.time() - inicio, 1)
    try:
        ESTADO.write_text(json.dumps(saida, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    except OSError as exc:
        print(f"AVISO: nao gravei o status ({exc})", file=sys.stderr)

    resumo = {k: v for k, v in saida.items() if k != "eleicoes"}
    if "totais" in resumo:
        resumo["totais"] = {k: v for k, v in resumo["totais"].items() if k != "andamento"}
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
