"""
Dados censitários (IBGE Censo 2022) — POC.

Serve os setores censitários como GeoJSON pro mapa coroplético, e um resumo
por município. Granularidade: setor (com hierarquia distrito/bairro). Sem
PostGIS — geometria em JSONB, render client-side.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import ORJSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant

router = APIRouter(prefix="/census", tags=["census"])

# Censo é dado estático, MAS adicionamos indicadores novos com frequência —
# um max-age de 7 dias no browser fazia o dado novo (renda, PIB, IDHM...) só
# aparecer dias depois. max-age curto + stale-while-revalidate longo: continua
# instantâneo (serve do cache na hora) e revalida em background em ~15 min, então
# atualização de dado aparece rápido. O nginx (proxy_cache) segura a carga.
_CACHE = "public, max-age=900, stale-while-revalidate=604800"

# Cache in-process do dissolve do /malha (shapely/GEOS, ~12s a frio no Rio).
# LRU DEDICADO e pequeno (nao o agg_cache global): as features de malha pesam
# ate ~1-3MB cada — no agg_cache (256 entradas) despejariam as agregacoes TSE
# e poderiam estourar os 768MB do container. 40 entradas cobrem os municipios
# realmente visitados; o proxy_cache do nginx segura a cauda. Beneficio extra:
# o warmup (2 encodings) so paga o dissolve 1x por municipio/level.
# Lock: handlers sync rodam no threadpool do FastAPI (ha concorrencia real).
import threading as _threading
from collections import OrderedDict as _OrderedDict

_MALHA_MAX = 40
_malha_cache: "_OrderedDict[str, list]" = _OrderedDict()
_malha_lock = _threading.Lock()


def _malha_cache_get(key: str) -> list | None:
    with _malha_lock:
        feats = _malha_cache.get(key)
        if feats is not None:
            _malha_cache.move_to_end(key)
        return feats


def _malha_cache_set(key: str, feats: list) -> None:
    with _malha_lock:
        _malha_cache[key] = feats
        _malha_cache.move_to_end(key)
        while len(_malha_cache) > _MALHA_MAX:
            _malha_cache.popitem(last=False)


def _round_coords(obj, nd: int = 5):
    """Arredonda recursivamente as coordenadas (lat/lng) de um GeoJSON.
    5 casas decimais ≈ 1,1 m — invisível no zoom de cidade, mas corta ~40% do
    payload (Rio: 10MB→~6MB). Carregamento do mapa mais leve, principalmente mobile."""
    if isinstance(obj, list):
        return [_round_coords(x, nd) for x in obj]
    if isinstance(obj, float):
        return round(obj, nd)
    return obj


def _round_geom(geom, nd: int = 5):
    if not isinstance(geom, dict) or "coordinates" not in geom:
        return geom
    return {**geom, "coordinates": _round_coords(geom["coordinates"], nd)}


@router.get(
    "/municipalities",
    summary="Municípios com dados censitários disponíveis",
)
def census_municipalities(ctx: CurrentTenant, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT cd_mun, max(nm_mun) AS nm_mun, count(*) AS setores, "
            "       coalesce(sum(populacao),0) AS populacao, "
            "       coalesce(sum(domicilios),0) AS domicilios, "
            "       count(distinct cd_dist) AS distritos, "
            "       count(distinct nm_bairro) FILTER (WHERE nm_bairro <> '') AS bairros "
            "FROM census_geo WHERE level='setor' GROUP BY cd_mun ORDER BY max(nm_mun)"
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@router.get(
    "/uf-overview",
    summary="Visão estadual: municípios (coroplético) de uma UF como GeoJSON",
    description=(
        "FeatureCollection dos municípios da UF com população/domicílios "
        "agregados do Censo — pro mapa do estado com drill-down pro setor."
    ),
)
def census_uf_overview(
    ctx: CurrentTenant,
    uf: str = Query("33", description="Código IBGE da UF (33 = RJ)"),
    db: Session = Depends(get_db),
) -> Response:
    rows = db.execute(
        text(
            "SELECT g.cd_mun, g.nm_mun, g.populacao, g.domicilios, g.geometry, "
            "       g.renda_media_domiciliar, g.renda_mediana_domiciliar, "
            "       g.renda_media_resp_2022, g.renda_mediana_resp_2022, "
            "       g.pib_total, g.pib_per_capita, g.idhm, g.idhm_educacao, "
            "       g.idhm_longevidade, g.idhm_renda, "
            "       g.ideb_anos_iniciais, g.ideb_anos_finais, "
            "       g.dom_agua_rede, g.dom_agua_total, g.dom_esgoto_adequado, "
            "       g.dom_esgoto_total, g.dom_lixo_coletado, g.dom_lixo_total, "
            "       md.cadunico_familias, md.pbf_familias, md.anomes AS mds_anomes, "
            "       s.setores, s.taxa_alfabetizacao, s.pct_pretos_pardos, s.pct_urbana, "
            "       s.sexo_masculino, s.sexo_feminino, "
            "       s.idade_0_4, s.idade_5_9, s.idade_10_14, s.idade_15_19, s.idade_20_24, "
            "       s.idade_25_29, s.idade_30_39, s.idade_40_49, s.idade_50_59, "
            "       s.idade_60_69, s.idade_70_mais "
            "FROM census_geo g "
            "LEFT JOIN LATERAL ("
            "  SELECT count(*) AS setores, "
            "         round(100*sum(alfabetizados_15mais)::numeric"
            "               / NULLIF(sum(pop_15mais),0), 1) AS taxa_alfabetizacao, "
            "         round(100*(coalesce(sum(raca_preta),0)+coalesce(sum(raca_parda),0))::numeric"
            "               / NULLIF(sum(populacao),0), 1) AS pct_pretos_pardos, "
            "         round(100*sum(populacao) FILTER (WHERE situacao='Urbana')::numeric"
            "               / NULLIF(sum(populacao),0), 1) AS pct_urbana, "
            "         sum(sexo_masculino) AS sexo_masculino, sum(sexo_feminino) AS sexo_feminino, "
            "         sum(idade_0_4) AS idade_0_4, sum(idade_5_9) AS idade_5_9, "
            "         sum(idade_10_14) AS idade_10_14, sum(idade_15_19) AS idade_15_19, "
            "         sum(idade_20_24) AS idade_20_24, sum(idade_25_29) AS idade_25_29, "
            "         sum(idade_30_39) AS idade_30_39, sum(idade_40_49) AS idade_40_49, "
            "         sum(idade_50_59) AS idade_50_59, sum(idade_60_69) AS idade_60_69, "
            "         sum(idade_70_mais) AS idade_70_mais "
            "  FROM census_geo s WHERE s.level='setor' AND s.cd_mun = g.cd_mun"
            ") s ON true "
            # CadÚnico/Bolsa Família (MDS): último mês disponível por município.
            "LEFT JOIN LATERAL ("
            "  SELECT cadunico_familias, pbf_familias, anomes "
            "  FROM mds_social_municipio m WHERE m.cd_mun = g.cd_mun "
            "  ORDER BY m.anomes DESC LIMIT 1"
            ") md ON true "
            "WHERE g.level='municipio' AND g.cd_mun LIKE :u "
            "ORDER BY g.nm_mun"
        ),
        {"u": uf + "%"},
    ).mappings().all()
    feats = [{
        "type": "Feature",
        "geometry": r["geometry"],
        "properties": {
            "cd_mun": r["cd_mun"], "nm_mun": r["nm_mun"],
            "populacao": r["populacao"], "domicilios": r["domicilios"],
            "setores": r["setores"],
            "media_moradores": (
                round(r["populacao"] / r["domicilios"], 2)
                if r["domicilios"] and r["populacao"] else None
            ),
            "taxa_alfabetizacao": (
                float(r["taxa_alfabetizacao"]) if r["taxa_alfabetizacao"] is not None else None
            ),
            "pct_pretos_pardos": (
                float(r["pct_pretos_pardos"]) if r["pct_pretos_pardos"] is not None else None
            ),
            "pct_urbana": (
                float(r["pct_urbana"]) if r["pct_urbana"] is not None else None
            ),
            # Sexo + faixa etária (Censo 2022, agregado demografia). Contagens
            # por município (soma dos setores). Onde não há setores ingeridos,
            # vêm null.
            "sexo_masculino": r["sexo_masculino"],
            "sexo_feminino": r["sexo_feminino"],
            "faixa_etaria": {
                "0_4": r["idade_0_4"], "5_9": r["idade_5_9"], "10_14": r["idade_10_14"],
                "15_19": r["idade_15_19"], "20_24": r["idade_20_24"],
                "25_29": r["idade_25_29"], "30_39": r["idade_30_39"],
                "40_49": r["idade_40_49"], "50_59": r["idade_50_59"],
                "60_69": r["idade_60_69"], "70_mais": r["idade_70_mais"],
            },
            "pct_feminino": (
                round(100 * r["sexo_feminino"]
                      / ((r["sexo_masculino"] or 0) + (r["sexo_feminino"] or 0)), 1)
                if ((r["sexo_masculino"] or 0) + (r["sexo_feminino"] or 0)) > 0
                and r["sexo_feminino"] is not None else None
            ),
            "pct_60mais": (
                round(100 * ((r["idade_60_69"] or 0) + (r["idade_70_mais"] or 0))
                      / r["populacao"], 1)
                if (r["populacao"] or 0) > 0
                and (r["idade_60_69"] is not None or r["idade_70_mais"] is not None)
                else None
            ),
            # Renda dos responsáveis (Censo 2022) — variável pedida pelo PO;
            # fallback pra renda domiciliar 2010 se o município ainda não tiver
            # o dado 2022 (ex: antes de rodar a ingestão nova).
            "renda_media": (
                float(r["renda_media_resp_2022"])
                if r["renda_media_resp_2022"] is not None
                else (
                    float(r["renda_media_domiciliar"])
                    if r["renda_media_domiciliar"] is not None else None
                )
            ),
            "renda_mediana": (
                float(r["renda_mediana_resp_2022"])
                if r["renda_mediana_resp_2022"] is not None
                else (
                    float(r["renda_mediana_domiciliar"])
                    if r["renda_mediana_domiciliar"] is not None else None
                )
            ),
            # CadÚnico / Bolsa Família (MDS) — contagens + % sobre domicílios
            # (comparável entre municípios de tamanhos diferentes).
            "cadunico_familias": r["cadunico_familias"],
            "pbf_familias": r["pbf_familias"],
            "pct_bolsa_familia": (
                round(100 * r["pbf_familias"] / r["domicilios"], 1)
                if r["domicilios"] and r["pbf_familias"] is not None else None
            ),
            "pct_cadunico": (
                round(100 * r["cadunico_familias"] / r["domicilios"], 1)
                if r["domicilios"] and r["cadunico_familias"] is not None else None
            ),
            "mds_anomes": r["mds_anomes"],
            # PIB (IBGE 2023)
            "pib_per_capita": (
                float(r["pib_per_capita"]) if r["pib_per_capita"] is not None else None
            ),
            "pib_total": (
                float(r["pib_total"]) if r["pib_total"] is not None else None
            ),
            # IDHM (Atlas/PNUD, Censo 2010)
            "idhm": float(r["idhm"]) if r["idhm"] is not None else None,
            "idhm_educacao": float(r["idhm_educacao"]) if r["idhm_educacao"] is not None else None,
            "idhm_longevidade": float(r["idhm_longevidade"]) if r["idhm_longevidade"] is not None else None,
            "idhm_renda": float(r["idhm_renda"]) if r["idhm_renda"] is not None else None,
            # IDEB (INEP 2023, rede pública)
            "ideb_anos_iniciais": (
                float(r["ideb_anos_iniciais"]) if r["ideb_anos_iniciais"] is not None else None
            ),
            "ideb_anos_finais": (
                float(r["ideb_anos_finais"]) if r["ideb_anos_finais"] is not None else None
            ),
            # Saneamento (Censo 2022) — % de domicílios
            "pct_agua_rede": (
                round(100 * r["dom_agua_rede"] / r["dom_agua_total"], 1)
                if r["dom_agua_total"] else None
            ),
            "pct_esgoto_adequado": (
                round(100 * r["dom_esgoto_adequado"] / r["dom_esgoto_total"], 1)
                if r["dom_esgoto_total"] else None
            ),
            "pct_lixo_coletado": (
                round(100 * r["dom_lixo_coletado"] / r["dom_lixo_total"], 1)
                if r["dom_lixo_total"] else None
            ),
        },
    } for r in rows]
    return ORJSONResponse(
        content={"type": "FeatureCollection", "features": feats},
        headers={"Cache-Control": _CACHE},
    )


@router.get(
    "/ai-insight",
    summary="Maré IA · leitura estratégica do território (Censo 2022)",
    description=(
        "Gera (ou retorna do cache) a leitura estratégica da Maré IA para o "
        "município, a partir dos dados censitários. force=true regenera."
    ),
)
def census_ai_insight(
    ctx: CurrentTenant,
    cd_mun: str = Query(..., description="Código IBGE do município"),
    force: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    from app.utils.ai_report import AiReportError, generate_census_insight

    try:
        result = generate_census_insight(db, cd_mun, force=force)
    except AiReportError as e:
        raise HTTPException(status_code=503, detail=str(e))
    # no-store: o cache é o do banco (ai_census_insights); o nginx NÃO deve
    # congelar esta resposta por 7d (senão force/regeneração não aparecem).
    return ORJSONResponse(content=result, headers={"Cache-Control": "no-store"})


@router.get(
    "/setores",
    summary="Setores censitários de um município como GeoJSON (coroplético)",
    description=(
        "Retorna um FeatureCollection GeoJSON dos setores censitários do "
        "município, com população, domicílios e hierarquia (distrito/bairro) "
        "nas properties — pronto pro mapa temático."
    ),
)
def census_setores(
    ctx: CurrentTenant,
    cd_mun: str = Query(..., description="Código IBGE do município (7 dígitos)"),
    db: Session = Depends(get_db),
) -> Response:
    rows = db.execute(
        text(
            "SELECT cd_setor, nm_mun, cd_dist, nm_dist, nm_subdist, nm_bairro, "
            "       situacao, area_km2, populacao, domicilios, geometry, "
            "       alfabetizados_15mais, pop_15mais, "
            "       raca_branca, raca_preta, raca_amarela, raca_parda, raca_indigena, "
            "       sexo_masculino, sexo_feminino, idade_60_69, idade_70_mais "
            "FROM census_geo WHERE cd_mun = :m AND level='setor' ORDER BY cd_setor "
            "LIMIT 30000"  # cap defensivo: maior município do BR (SP) tem ~27k setores
        ),
        {"m": cd_mun},
    ).mappings().all()

    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": _round_geom(r["geometry"]),
            "properties": {
                "cd_setor": r["cd_setor"],
                "nm_mun": r["nm_mun"],
                "cd_dist": r["cd_dist"],
                "nm_dist": r["nm_dist"],
                "nm_subdist": r["nm_subdist"],
                "nm_bairro": r["nm_bairro"],
                "situacao": r["situacao"],
                "area_km2": r["area_km2"],
                "populacao": r["populacao"],
                "domicilios": r["domicilios"],
                "densidade_hab_km2": (
                    round(r["populacao"] / r["area_km2"], 1)
                    if r["area_km2"] and r["populacao"] else None
                ),
                "media_moradores": (
                    round(r["populacao"] / r["domicilios"], 2)
                    if r["domicilios"] and r["populacao"] else None
                ),
                # Indicadores extras (IBGE 2022; None = sigilo/sem dado)
                "taxa_alfabetizacao": (
                    round(100 * r["alfabetizados_15mais"] / r["pop_15mais"], 1)
                    if r["pop_15mais"] and r["alfabetizados_15mais"] is not None else None
                ),
                "alfabetizados_15mais": r["alfabetizados_15mais"],
                "pop_15mais": r["pop_15mais"],
                "pct_pretos_pardos": (
                    round(100 * ((r["raca_preta"] or 0) + (r["raca_parda"] or 0))
                          / r["populacao"], 1)
                    if (r["populacao"] or 0) > 0
                    and (r["raca_preta"] is not None or r["raca_parda"] is not None)
                    else None
                ),
                "raca_branca": r["raca_branca"],
                "raca_preta": r["raca_preta"],
                "raca_amarela": r["raca_amarela"],
                "raca_parda": r["raca_parda"],
                "raca_indigena": r["raca_indigena"],
                # Sexo + idade (Censo 2022) como indicadores de mapa.
                "pct_feminino": (
                    round(100 * r["sexo_feminino"]
                          / ((r["sexo_masculino"] or 0) + (r["sexo_feminino"] or 0)), 1)
                    if ((r["sexo_masculino"] or 0) + (r["sexo_feminino"] or 0)) > 0
                    and r["sexo_feminino"] is not None else None
                ),
                "pct_60mais": (
                    round(100 * ((r["idade_60_69"] or 0) + (r["idade_70_mais"] or 0))
                          / r["populacao"], 1)
                    if (r["populacao"] or 0) > 0
                    and (r["idade_60_69"] is not None or r["idade_70_mais"] is not None)
                    else None
                ),
            },
        })
    # ORJSONResponse direto: FastAPI NÃO roda o jsonable_encoder (caro pra
    # 8MB de dicts) — orjson serializa tudo em Rust de uma vez.
    return ORJSONResponse(
        content={"type": "FeatureCollection", "features": features},
        headers={"Cache-Control": _CACHE},
    )


@router.get(
    "/malha",
    summary="Contornos de bairro/distrito de um município (setores dissolvidos)",
    description=(
        "Dissolve os setores censitários por bairro (nm_bairro) ou distrito "
        "(nm_dist) e retorna os CONTORNOS como GeoJSON — para sobrepor no WebGIS "
        "acima da malha de setores. O dissolve roda no servidor (shapely/GEOS) e "
        "é cacheado; o browser não paga o custo."
    ),
)
def census_malha(
    ctx: CurrentTenant,
    cd_mun: str = Query(..., description="Código IBGE do município (7 dígitos)"),
    level: str = Query("bairro", pattern="^(bairro|distrito)$"),
    db: Session = Depends(get_db),
) -> Response:
    # Import lazy: se por algum motivo o shapely não estiver instalado, só este
    # endpoint falha (com 503), não o controller inteiro.
    try:
        from shapely.geometry import mapping, shape
        from shapely.ops import unary_union
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=503, detail="Geometria indisponível (shapely).")

    # Cache in-process do dissolve: mesmo se o nginx for purgado (todo deploy),
    # o dissolve pesado so roda 1x por (municipio, level) por vida do processo.
    _ck = f"{cd_mun}:{level}"
    _cached = _malha_cache_get(_ck)
    if _cached is not None:
        return ORJSONResponse(
            content={"type": "FeatureCollection", "features": _cached},
            headers={"Cache-Control": _CACHE},
        )

    # Nome da área. Para bairro, cai pro distrito quando o setor não tem bairro
    # mapeado — MESMA chave que o frontend usa (nm_bairro || nm_dist), pra os
    # polígonos dissolvidos casarem com o agregado calculado no front.
    name_expr = (
        "COALESCE(NULLIF(nm_bairro, ''), nm_dist)" if level == "bairro" else "nm_dist"
    )
    rows = db.execute(
        text(
            f"SELECT {name_expr} AS nome, geometry, populacao "
            "FROM census_geo WHERE cd_mun = :m AND level='setor' "
            "AND geometry IS NOT NULL ORDER BY nome"
        ),
        {"m": cd_mun},
    ).mappings().all()

    # Agrupa os setores por bairro/distrito e faz a UNIÃO das geometrias.
    groups: dict[str, list] = {}
    pop: dict[str, int] = {}
    for r in rows:
        nome = (r["nome"] or "—").strip() or "—"
        try:
            geom = shape(r["geometry"])
            if not geom.is_valid:
                geom = geom.buffer(0)  # conserta anéis inválidos (sliver, etc.)
            groups.setdefault(nome, []).append(geom)
            pop[nome] = pop.get(nome, 0) + int(r["populacao"] or 0)
        except Exception:
            continue

    features = []
    for nome, geoms in groups.items():
        try:
            merged = unary_union(geoms)
        except Exception:
            continue
        features.append({
            "type": "Feature",
            "geometry": _round_geom(mapping(merged)),
            "properties": {"nome": nome, "level": level, "populacao": pop.get(nome)},
        })

    _malha_cache_set(_ck, features)
    return ORJSONResponse(
        content={"type": "FeatureCollection", "features": features},
        headers={"Cache-Control": _CACHE},
    )


# ------------------------------------------------------------- busca global

# Abreviações que o IBGE usa nos nomes de bairro — mesma tabela da busca do
# frontend (censo/page.tsx), para "nossa senhora" achar "N. S. das Graças".
_SEARCH_ABBR = [
    (" n s ", " nossa senhora "),
    (" n sra ", " nossa senhora "),
    (" sta ", " santa "),
    (" sto ", " santo "),
    (" jd ", " jardim "),
    (" vl ", " vila "),
    (" pq ", " parque "),
    (" pe ", " padre "),
    (" dr ", " doutor "),
    (" eng ", " engenheiro "),
    (" pres ", " presidente "),
]

_UF_SIGLA = {"31": "MG", "32": "ES", "33": "RJ", "35": "SP"}


def _search_key(s: str) -> str:
    import re
    import unicodedata

    x = unicodedata.normalize("NFD", (s or "").lower())
    x = "".join(c for c in x if unicodedata.category(c) != "Mn")
    x = " " + re.sub(r"[^a-z0-9]+", " ", x).strip() + " "
    for old, new in _SEARCH_ABBR:
        x = x.replace(old, new)
    return re.sub(r"\s+", " ", x).strip()


@router.get(
    "/search-areas",
    summary="Bairros/distritos do censo para a busca global",
    description=(
        "Busca por nome (sem acento, abreviações IBGE expandidas) nos "
        "bairros e distritos com dados censitários. Vazio se o usuário "
        "não tem o módulo Censo liberado."
    ),
)
def census_search_areas(
    ctx: CurrentTenant,
    q: str = Query(..., min_length=2, max_length=80),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.models.user import User
    from app.utils.agg_cache import agg_get, agg_set

    # Módulo Censo é feature-flag por usuário — sem flag, sem resultados.
    user = db.get(User, ctx.user_id)
    if user is None or not getattr(user, "census_enabled", False):
        return []

    # Índice (cd_mun, nome, kind, chave normalizada) em memória por 4h —
    # o DISTINCT varre ~200k setores, mas só na primeira busca.
    index = agg_get("census:area_index")
    if index is None:
        rows = db.execute(
            text(
                "SELECT DISTINCT cd_mun, nm_mun, "
                "  CASE WHEN coalesce(nm_bairro,'') <> '' THEN nm_bairro "
                "       ELSE nm_dist END AS nome, "
                "  (coalesce(nm_bairro,'') <> '') AS is_bairro "
                "FROM census_geo WHERE level='setor' "
                "  AND (coalesce(nm_bairro,'') <> '' OR coalesce(nm_dist,'') <> '')"
            )
        ).mappings().all()
        index = [
            {
                "cd_mun": str(r["cd_mun"]),
                "nm_mun": r["nm_mun"],
                "nome": r["nome"],
                "kind": "Bairro" if r["is_bairro"] else "Distrito",
                "uf": _UF_SIGLA.get(str(r["cd_mun"])[:2], ""),
                "_key": _search_key(str(r["nome"])),
            }
            for r in rows
        ]
        agg_set("census:area_index", index)

    qk = _search_key(q)
    if not qk:
        return []
    matches = [it for it in index if qk in it["_key"]]
    # Quem COMEÇA com o termo vem primeiro; bairros antes de distritos.
    matches.sort(
        key=lambda r: (
            not r["_key"].startswith(qk),
            r["kind"] != "Bairro",
            r["nome"],
        )
    )
    return [{k: v for k, v in it.items() if k != "_key"} for it in matches[:8]]


# Prefixo IBGE (cd_mun começa com) por sigla de UF — inverso de _UF_SIGLA.
_SIGLA_PREFIX = {v: k for k, v in _UF_SIGLA.items()}


@router.get(
    "/municipality-neighborhoods",
    summary="Bairros/distritos de um município (pra cascata do cadastro de contato)",
    description=(
        "Lista os bairros (ou distritos, se o município não tiver bairro) de "
        "um município, a partir do Censo. Usado no formulário de contato: o "
        "usuário escolhe UF → município e aqui sugerimos os bairros. Vazio se "
        "o município não tem dado censitário (aí o usuário digita livre)."
    ),
)
def census_municipality_neighborhoods(
    ctx: CurrentTenant,
    uf: str = Query(..., min_length=2, max_length=2),
    municipio: str = Query(..., min_length=1, max_length=120),
    db: Session = Depends(get_db),
) -> list[str]:
    pfx = _SIGLA_PREFIX.get(uf.upper())

    # 1) Bairros REAIS do IBGE (nm_bairro preenchido) — só Sudeste tem censo.
    #    Ignora distrito aqui de propósito: município que só tem distrito (ex:
    #    Seropédica) cai pro TSE no passo 2.
    ibge: list[str] = []
    if pfx:
        rows = db.execute(
            text(
                "SELECT DISTINCT s.nm_bairro AS nome "
                "FROM census_geo s "
                "WHERE s.level='setor' AND coalesce(s.nm_bairro,'') <> '' "
                "  AND s.cd_mun = ("
                "    SELECT g.cd_mun FROM census_geo g "
                "    WHERE g.level='municipio' AND g.cd_mun LIKE :pfx "
                "      AND upper(public.f_unaccent(g.nm_mun)) = upper(public.f_unaccent(:mname)) "
                "    LIMIT 1) "
                "ORDER BY nome"
            ),
            {"pfx": pfx + "%", "mname": municipio},
        ).all()
        ibge = [r.nome for r in rows if r.nome]
    if ibge:
        return ibge

    # 2) Fallback TSE: bairros dos locais de votação. O TSE atualiza a cada
    #    eleição (2 anos, vs 10 do IBGE) e cobre o Brasil inteiro — então
    #    municípios sem bairro no IBGE (só distrito) ou fora do Sudeste ainda
    #    ganham sugestões.
    rows = db.execute(
        text(
            "SELECT DISTINCT tvp.neighborhood AS nome "
            "FROM tse_voting_places tvp "
            "JOIN tse_municipalities tm ON tm.id = tvp.municipality_id "
            "WHERE tm.state = :uf "
            "  AND tvp.year = 2024 "
            "  AND upper(public.f_unaccent(tm.name)) = upper(public.f_unaccent(:mname)) "
            "  AND coalesce(tvp.neighborhood,'') <> '' "
            "ORDER BY nome"
        ),
        {"uf": uf.upper(), "mname": municipio},
    ).all()
    # TSE vem em CAIXA ALTA — deixa "Title Case" (connectores em minúsculo)
    # pra ficar igual ao padrão do IBGE.
    return [_titlecase(r.nome) for r in rows if r.nome]


_CONNECTORS = {"de", "da", "do", "das", "dos", "e", "di", "du", "no", "na"}


def _titlecase(s: str) -> str:
    words = s.lower().split()
    out = [
        w.capitalize() if (i == 0 or w not in _CONNECTORS) else w
        for i, w in enumerate(words)
    ]
    return " ".join(out)
