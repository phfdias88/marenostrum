#!/usr/bin/env python3
"""
Malha de SETORES censitarios por UF — o desenho do drill-down.

CONTEXTO: a carga nacional (ago/2026) trouxe os indicadores dos 468 mil
setores do pais, mas sem geometria; e `ingest_census_malha_municipios.py`
trouxe o contorno dos 5.570 municipios. Falta o nivel mais fino, que so
existia em SP/MG/RJ/ES porque foi carregado a mao, arquivo por arquivo.

POR QUE E POR UF, E NAO TUDO DE UMA VEZ: aqui pesa. As 4 UFs iniciais ocupam
251 MB de geometria; o zip do IBGE vai de 2,4 MB (DF) a 80 MB (SP). Com o
disco da VPS em ~75%, carregar o pais inteiro nao cabe sem planejamento — a
UF entra sob demanda, quando um cliente precisa daquele estado.

O DF foi o caso que motivou o script: e a unica UF com UM municipio, entao a
visao estadual mostra um poligono so e TODO o valor esta no setor (Ceilandia,
Taguatinga, Plano Piloto). Sem malha de setor, a tela do DF nao serve pra nada.

O QUE FAZ: baixa o shapefile da UF, le com pyshp e da UPDATE na geometria dos
setores que JA existem. Nao cria linha nem toca em indicador — se o setor nao
estiver no banco, ele e contado como "sem correspondencia" e ignorado (rode o
ingest_census_data.py --dataset basico antes).

USO:
    docker compose cp backend/scripts/ingest_census_malha_setores.py api:/tmp/
    docker compose exec -T -e PYTHONPATH=/app api \\
        python /tmp/ingest_census_malha_setores.py --uf DF

    # varias, e simulando pra ver o custo antes:
    ... --uf DF --uf GO --dry-run

DEPOIS: limpar o cache `mn_census` do nginx.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.request
import zipfile

import shapefile  # pyshp
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
)
log = structlog.get_logger("census.malha_setores")

BASE = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/"
    "setores/shp/UF/"
)

# 5 casas decimais ~ 1 metro. Alem disso e ruido que so engorda o GeoJSON que
# trafega ate o navegador (mesmo criterio dos outros scripts de malha).
CASAS = 5


def _arredondar(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(obj[0]), CASAS), round(float(obj[1]), CASAS)]
        return [_arredondar(x) for x in obj]
    return obj


def _baixar(uf: str, tmp_dir: str = "/tmp") -> str:
    """Baixa o zip da UF (reaproveita o que ja estiver em disco)."""
    nome = f"{uf}_setores_CD2022.zip"
    destino = os.path.join(tmp_dir, nome)
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        log.info("download_pulado", uf=uf, motivo="arquivo ja em disco")
        return destino
    url = BASE + nome
    log.info("download_iniciado", uf=uf, url=url)
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "marenostrum-etl/1.0"})
    parcial = destino + ".part"
    with urllib.request.urlopen(req, timeout=900) as resp, open(parcial, "wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    os.replace(parcial, destino)  # so vira "pronto" se completou
    log.info("download_concluido", uf=uf,
             mb=round(os.path.getsize(destino) / 1e6, 1),
             segundos=round(time.perf_counter() - t0, 1))
    return destino


_UPDATE = text(
    "UPDATE census_geo SET geometry = CAST(:geom AS jsonb), updated_at = now() "
    "WHERE level='setor' AND cd_setor = :cd"
)


def processar_uf(db: Session, uf: str, dry_run: bool, lote: int) -> dict:
    caminho = _baixar(uf)
    zf = zipfile.ZipFile(caminho)
    base_shp = next(n for n in zf.namelist() if n.lower().endswith(".shp"))[:-4]

    leitor = shapefile.Reader(
        shp=io.BytesIO(zf.read(base_shp + ".shp")),
        dbf=io.BytesIO(zf.read(base_shp + ".dbf")),
        shx=io.BytesIO(zf.read(base_shp + ".shx")),
        encoding="latin-1",
    )
    campos = [f[0] for f in leitor.fields[1:]]
    if "CD_SETOR" not in campos:
        raise SystemExit(f"[{uf}] shapefile sem CD_SETOR. Campos: {campos[:8]}")
    idx = campos.index("CD_SETOR")

    # A contagem do que casou vem do rowcount do proprio UPDATE — o shapefile
    # ja e so daquela UF, e o banco e a fonte de verdade sobre o que existe.
    st = {"lidos": 0, "atualizados": 0, "sem_correspondencia": 0, "erros": 0}
    buffer: list[dict] = []
    t0 = time.perf_counter()

    for sr in leitor.iterShapeRecords():
        st["lidos"] += 1
        try:
            cd = str(sr.record[idx]).strip()
            geo = sr.shape.__geo_interface__
            buffer.append({
                "cd": cd,
                "geom": json.dumps({
                    "type": geo["type"],
                    "coordinates": _arredondar(geo["coordinates"]),
                }),
            })
        except Exception as e:  # noqa: BLE001 — um setor ruim nao para a UF
            st["erros"] += 1
            if st["erros"] <= 3:
                log.warning("setor_com_erro", uf=uf, erro=f"{type(e).__name__}: {e}")

        if len(buffer) >= lote:
            if not dry_run:
                res = db.execute(_UPDATE, buffer)
                db.commit()
                st["atualizados"] += res.rowcount or len(buffer)
            else:
                st["atualizados"] += len(buffer)
            buffer.clear()
            if st["lidos"] % (lote * 5) == 0:
                log.info("progresso", uf=uf, lidos=st["lidos"],
                         atualizados=st["atualizados"],
                         por_seg=int(st["lidos"] / (time.perf_counter() - t0)))

    if buffer:
        if not dry_run:
            res = db.execute(_UPDATE, buffer)
            db.commit()
            st["atualizados"] += res.rowcount or len(buffer)
        else:
            st["atualizados"] += len(buffer)

    # Setor no shapefile que nao existe no banco: acontece se o basico ainda
    # nao foi carregado, ou se o IBGE republicou a malha com setor novo.
    st["sem_correspondencia"] = max(0, st["lidos"] - st["atualizados"] - st["erros"])
    log.info("uf_concluida", uf=uf, **st,
             segundos=round(time.perf_counter() - t0, 1))
    return st


def main() -> int:
    p = argparse.ArgumentParser(description="Malha de setores censitarios por UF.")
    p.add_argument("--uf", action="append", required=True,
                   help="sigla da UF (DF, GO, BA...). Repetivel.")
    p.add_argument("--lote", type=int, default=1000, help="setores por commit")
    p.add_argument("--dry-run", action="store_true", help="le e valida, sem gravar")
    args = p.parse_args()

    ufs = [u.strip().upper()[:2] for u in args.uf]
    db = SessionLocal()
    try:
        db.execute(text("SET statement_timeout = 0"))
        db.commit()
        log.info("malha_setores_iniciada", ufs=ufs, dry_run=args.dry_run)

        total = {"lidos": 0, "atualizados": 0, "sem_correspondencia": 0, "erros": 0}
        for uf in ufs:
            st = processar_uf(db, uf, args.dry_run, args.lote)
            for k in total:
                total[k] += st[k]

        log.info("malha_setores_concluida", **total)

        if not args.dry_run:
            com, tot = db.execute(text(
                "SELECT count(*) FILTER (WHERE geometry IS NOT NULL), count(*) "
                "FROM census_geo WHERE level='setor'"
            )).first()
            log.info("estado_da_tabela", setores=tot, com_geometria=com)
            log.info("proximo_passo", acao="limpar o cache mn_census do nginx")

        return 0 if total["atualizados"] else 1
    except KeyboardInterrupt:
        log.warning("interrompido", dica="pode rodar de novo: e idempotente")
        return 130
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
