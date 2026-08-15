#!/usr/bin/env python3
"""
Malha de MUNICIPIOS do IBGE — o contorno que o mapa estadual desenha.

POR QUE ESTE SCRIPT EXISTE: o `ingest_census_data.py` carrega indicador, nao
geometria. Depois da carga nacional (ago/2026) o pais inteiro tem numero, mas
so SP/MG/RJ/ES tinham contorno — em qualquer outra UF o mapa abria vazio
(`/census/uf-overview` respondendo `features: []`).

CUSTO: ~1 KB por municipio. Os 3.904 municipios que faltavam couberam em ~4 MB.
Nao confundir com a malha de SETORES, que e outra ordem de grandeza: 251 MB
para as 4 UFs que ja tinham. Por isso o setor continua entrando por UF, sob
demanda, e o municipio pode entrar pro pais todo de uma vez.

DE ONDE VEM: API de malhas do IBGE, uma chamada por UF, recortando por
municipio. Qualidade "intermediaria" e o meio-termo que o projeto ja usava:
"maxima" multiplica o peso sem diferenca visivel no zoom de estado.

O QUE GRAVA: uma linha `level='municipio'` por municipio, com a geometria e os
totais somados dos setores daquele municipio (populacao, domicilios). Os
demais indicadores do mapa vem de `census_muni_agg` (migration 058), que e
materializado a parte.

USO:
    docker compose cp backend/scripts/ingest_census_malha_municipios.py api:/tmp/
    docker compose exec -T -e PYTHONPATH=/app api \\
        python /tmp/ingest_census_malha_municipios.py --all-brasil

    # so o que falta (pula UF que ja tem malha) — o caso comum ao retomar:
    ... --all-brasil --somente-faltantes

    # uma UF especifica:
    ... --uf 29 --uf 23

DEPOIS: limpar o cache `mn_census` do nginx, senao a UF continua respondendo
o GeoJSON vazio que ficou guardado.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.request

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
log = structlog.get_logger("census.malha")

MALHA_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
    "?formato=application/vnd.geo+json&intrarregiao=municipio&qualidade={q}"
)

# Codigos das 27 UFs (26 estados + DF).
UFS_BRASIL = [
    "11", "12", "13", "14", "15", "16", "17",              # Norte
    "21", "22", "23", "24", "25", "26", "27", "28", "29",  # Nordeste
    "31", "32", "33", "35",                                # Sudeste
    "41", "42", "43",                                      # Sul
    "50", "51", "52", "53",                                # Centro-Oeste
]

# 5 casas decimais ~ 1 metro. Mais que isso e ruido que so engorda o payload
# servido no mapa (mesmo criterio do ingest_census_rj.py).
CASAS = 5


def _arredondar(obj):
    """Arredonda as coordenadas do GeoJSON, em qualquer profundidade."""
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(obj[0]), CASAS), round(float(obj[1]), CASAS)]
        return [_arredondar(x) for x in obj]
    return obj


def _baixar_malha(uf: str, qualidade: str, tentativas: int = 3) -> dict | None:
    """Baixa a malha de uma UF. None se o IBGE nao entregar.

    Com retry porque sao 27 chamadas seguidas a um servico publico: uma falha
    isolada nao pode custar a UF inteira.
    """
    url = MALHA_URL.format(uf=uf, q=qualidade)
    for tentativa in range(1, tentativas + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "marenostrum-etl/1.0"}
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                bruto = resp.read()
                # O servicodados do IBGE responde GZIP mesmo sem Accept-Encoding,
                # e o urllib nao descomprime sozinho: sem isto o JSON chega como
                # bytes binarios e estoura em "byte 0x8b in position 1".
                if bruto[:2] == b"\x1f\x8b" or (
                    resp.headers.get("Content-Encoding", "").lower() == "gzip"
                ):
                    bruto = gzip.decompress(bruto)
                return json.loads(bruto.decode("utf-8"))
        except Exception as e:  # noqa: BLE001 — servico externo, qualquer erro
            log.warning("malha_falhou", uf=uf, tentativa=tentativa,
                        erro=f"{type(e).__name__}: {e}")
            if tentativa < tentativas:
                time.sleep(5 * tentativa)  # espera crescente
    return None


def _agregados_da_uf(db: Session, uf: str) -> dict[str, tuple]:
    """Totais dos setores por municipio: (nome, populacao, domicilios)."""
    linhas = db.execute(
        text(
            "SELECT cd_mun, max(nm_mun), coalesce(sum(populacao),0), "
            "       coalesce(sum(domicilios),0) "
            "FROM census_geo "
            "WHERE level='setor' AND cd_mun LIKE :pfx "
            "GROUP BY cd_mun"
        ),
        {"pfx": uf + "%"},
    ).all()
    return {r[0]: (r[1], int(r[2]), int(r[3])) for r in linhas}


_UPSERT = text(
    "INSERT INTO census_geo "
    "  (level, cd_setor, cd_mun, nm_mun, populacao, domicilios, geometry, updated_at) "
    "VALUES ('municipio', :chave, :cd_mun, :nm_mun, :pop, :dom, "
    "        CAST(:geom AS jsonb), now()) "
    "ON CONFLICT (cd_setor) DO UPDATE SET "
    "  nm_mun=EXCLUDED.nm_mun, populacao=EXCLUDED.populacao, "
    "  domicilios=EXCLUDED.domicilios, geometry=EXCLUDED.geometry, "
    "  updated_at=now()"
)


def processar_uf(db: Session, uf: str, qualidade: str, dry_run: bool) -> tuple[int, int]:
    """Devolve (gravados, ignorados)."""
    agregados = _agregados_da_uf(db, uf)
    if not agregados:
        log.warning("uf_sem_setores", uf=uf,
                    dica="rode o ingest_census_data.py --dataset basico antes")
        return 0, 0

    fc = _baixar_malha(uf, qualidade)
    if fc is None:
        log.error("uf_pulada", uf=uf, motivo="malha indisponivel apos as tentativas")
        return 0, 0

    features = fc.get("features") or []
    gravados = ignorados = 0

    for ft in features:
        try:
            codigo = str((ft.get("properties") or {}).get("codarea", "")).strip()
            if codigo not in agregados:
                # Municipio na malha sem setor carregado: nao inventamos linha.
                ignorados += 1
                continue
            nome, populacao, domicilios = agregados[codigo]
            geom = ft.get("geometry") or {}
            if not geom.get("coordinates"):
                ignorados += 1
                continue
            payload = {
                "type": geom["type"],
                "coordinates": _arredondar(geom["coordinates"]),
            }
            if not dry_run:
                db.execute(_UPSERT, {
                    "chave": "MUN" + codigo, "cd_mun": codigo, "nm_mun": nome,
                    "pop": populacao, "dom": domicilios,
                    "geom": json.dumps(payload),
                })
            gravados += 1
        except Exception as e:  # noqa: BLE001 — um municipio ruim nao derruba a UF
            ignorados += 1
            log.warning("municipio_com_erro", uf=uf, erro=f"{type(e).__name__}: {e}")

    if not dry_run:
        db.commit()

    log.info("uf_concluida", uf=uf, municipios_na_malha=len(features),
             gravados=gravados, ignorados=ignorados)
    return gravados, ignorados


def main() -> int:
    p = argparse.ArgumentParser(description="Carrega a malha de municipios do IBGE.")
    p.add_argument("--uf", action="append", default=[], help="codigo da UF. Repetivel.")
    p.add_argument("--all-brasil", action="store_true", help="as 27 UFs")
    p.add_argument("--somente-faltantes", action="store_true",
                   help="pula UF que ja tem malha de municipio")
    p.add_argument("--qualidade", default="intermediaria",
                   choices=["minima", "intermediaria", "maxima"])
    p.add_argument("--dry-run", action="store_true", help="baixa e valida, sem gravar")
    args = p.parse_args()

    if not args.uf and not args.all_brasil:
        p.error("informe --uf (repetivel) ou --all-brasil")

    ufs = [u.strip()[:2] for u in args.uf] or UFS_BRASIL
    db = SessionLocal()
    try:
        db.execute(text("SET statement_timeout = 0"))
        db.commit()

        if args.somente_faltantes:
            ja_tem = {
                r[0] for r in db.execute(text(
                    "SELECT DISTINCT left(cd_mun,2) FROM census_geo "
                    "WHERE level='municipio' AND geometry IS NOT NULL"
                )).all()
            }
            pulando = [u for u in ufs if u in ja_tem]
            ufs = [u for u in ufs if u not in ja_tem]
            if pulando:
                log.info("ufs_puladas", quantas=len(pulando), ufs=sorted(pulando),
                         motivo="ja tem malha")

        log.info("malha_iniciada", ufs=len(ufs), qualidade=args.qualidade,
                 dry_run=args.dry_run)

        t0 = time.perf_counter()
        total_gravados = total_ignorados = 0
        falhas: list[str] = []
        for uf in ufs:
            gravados, ignorados = processar_uf(db, uf, args.qualidade, args.dry_run)
            total_gravados += gravados
            total_ignorados += ignorados
            if gravados == 0:
                falhas.append(uf)

        log.info("malha_concluida", gravados=total_gravados,
                 ignorados=total_ignorados, ufs_sem_resultado=falhas or None,
                 minutos=round((time.perf_counter() - t0) / 60, 1))

        if not args.dry_run:
            com_malha, total = db.execute(text(
                "SELECT count(*) FILTER (WHERE geometry IS NOT NULL), count(*) "
                "FROM census_geo WHERE level='municipio'"
            )).first()
            log.info("estado_da_tabela", municipios=total, com_malha=com_malha)
            log.info("proximo_passo",
                     acao="limpar o cache mn_census do nginx",
                     motivo="a UF nova respondeu features:[] e isso ficou cacheado")

        return 1 if falhas else 0
    except KeyboardInterrupt:
        log.warning("interrompido", dica="pode rodar de novo: e idempotente")
        return 130
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
