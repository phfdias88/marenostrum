"""
Relatório estratégico por IA (Gemini) — gap EleitoAI fase 3.

Reúne os dados públicos do candidato (votos por município, eleitorado,
trajetória, redutos/oportunidades) e pede ao Gemini um relatório
estratégico estruturado em JSON: diagnóstico, score de viabilidade,
pontos fortes, onde crescer, narrativas e recomendações.

Cache GLOBAL por candidato na tabela ai_reports — gera 1x, serve sempre.
Economiza a cota da API (free tier é limitado).
"""
from __future__ import annotations

import json
import os
import time
from uuid import UUID

import httpx
import structlog
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.tse import (
    Candidate,
    Election,
    Municipality,
    MunicipalityElectorate,
    Party,
    VoteResult,
)

log = structlog.get_logger("marenostrum.ai_report")

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


class AiReportError(Exception):
    """Falha ao gerar o relatório (sem chave, quota, etc.)."""


def _gather_facts(db: Session, candidate: Candidate) -> dict:
    """Monta o dossiê de fatos do candidato pra alimentar o prompt."""
    party = db.get(Party, candidate.party_id)
    election = db.get(Election, candidate.election_id)

    # Votos por município (top 15) + eleitorado pra penetração
    latest_elect = (
        select(
            MunicipalityElectorate.municipality_id.label("mid"),
            func.max(MunicipalityElectorate.year).label("y"),
        )
        .group_by(MunicipalityElectorate.municipality_id)
        .subquery()
    )
    rows = db.execute(
        select(
            Municipality.name,
            Municipality.state,
            VoteResult.votes,
            MunicipalityElectorate.total,
        )
        .join(VoteResult, VoteResult.municipality_id == Municipality.id)
        .outerjoin(latest_elect, latest_elect.c.mid == Municipality.id)
        .outerjoin(
            MunicipalityElectorate,
            (MunicipalityElectorate.municipality_id == Municipality.id)
            & (MunicipalityElectorate.year == latest_elect.c.y),
        )
        .where(VoteResult.candidate_id == candidate.id)
        .order_by(VoteResult.votes.desc())
    ).all()

    top = []
    total_votes = 0
    for name, state, votes, elect in rows:
        votes = int(votes or 0)
        total_votes += votes
        if len(top) < 15:
            pen = round(votes / elect * 100, 1) if elect else None
            top.append(
                {"municipio": f"{name}/{state}", "votos": votes,
                 "eleitorado": int(elect or 0), "penetracao_pct": pen}
            )

    # Trajetória (mesma pessoa, outros anos)
    traj_rows = db.execute(
        select(Election.year, Candidate.office_name, Candidate.result_status)
        .select_from(Candidate)
        .join(Election, Candidate.election_id == Election.id)
        .where(
            func.lower(func.f_unaccent(Candidate.name))
            == func.lower(func.f_unaccent(candidate.name)),
            # mesma UF — evita fundir homônimos de estados diferentes (sem CPF
            # no TSE, só o nome civil fundiria pessoas distintas).
            Candidate.state == candidate.state,
        )
        .order_by(Election.year.desc())
    ).all()
    trajetoria = [
        {"ano": int(y), "cargo": o, "resultado": r} for y, o, r in traj_rows
    ]

    return {
        "nome": candidate.urn_name,
        "nome_civil": candidate.name,
        "cargo": candidate.office_name,
        "partido": party.abbreviation if party else None,
        "uf": candidate.state,
        "ano": election.year if election else None,
        "total_votos": total_votes,
        "resultado": candidate.result_status,
        "top_municipios": top,
        "trajetoria": trajetoria,
        "municipios_com_voto": len(rows),
    }


_PROMPT = """Você é um consultor político sênior especializado em eleições \
brasileiras. Com base nos DADOS REAIS do TSE abaixo sobre um candidato, gere \
um relatório estratégico de campanha objetivo e acionável, em português do \
Brasil.

DADOS DO CANDIDATO (TSE):
{facts}

Responda APENAS com um JSON válido (sem markdown, sem ```), nesta estrutura \
exata:
{{
  "diagnostico": "2-3 frases resumindo a situação eleitoral do candidato",
  "score_viabilidade": <int 0-100>,
  "score_justificativa": "1 frase justificando o score",
  "pontos_fortes": ["3 a 4 pontos fortes concretos baseados nos dados"],
  "onde_crescer": ["3 a 4 recomendações de onde/como buscar mais votos"],
  "narrativas": ["3 a 4 frases de campanha prontas pra usar, tom direto"],
  "acoes_prioritarias": ["3 a 4 ações práticas pros próximos meses"]
}}

Seja específico citando municípios e números reais dos dados. Não invente \
dados que não estão no JSON. Não use linguagem partidária ou ofensiva."""


def _candidate_total_votes(db: Session, candidate_id: UUID) -> int:
    """Votação total atual do candidato (pra detectar mudança de dados)."""
    return int(
        db.execute(
            select(func.coalesce(func.sum(VoteResult.votes), 0)).where(
                VoteResult.candidate_id == candidate_id
            )
        ).scalar()
        or 0
    )


def generate_report(db: Session, candidate_id: UUID, *, force: bool = False) -> dict:
    """
    Retorna o relatório (do cache ou gerando). Lança AiReportError em falha.
    O cache é invalidado se a votação do candidato mudou desde a geração
    (ex: re-sync do TSE) — o snapshot garante que a IA reflita o dado vigente.
    """
    current_votes = _candidate_total_votes(db, candidate_id)

    # Cache hit? (só se o snapshot de votos ainda confere)
    if not force:
        row = db.execute(
            text(
                "SELECT content, votes_snapshot FROM ai_reports "
                "WHERE candidate_id = :cid"
            ),
            {"cid": str(candidate_id)},
        ).first()
        if row is not None and row.votes_snapshot == current_votes:
            content = row.content
            return content if isinstance(content, dict) else json.loads(content)

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise AiReportError("IA não configurada (sem chave). Avise o suporte.")

    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise AiReportError("Candidato não encontrado")

    facts = _gather_facts(db, candidate)
    prompt = _PROMPT.format(facts=json.dumps(facts, ensure_ascii=False, indent=2))
    report = _call_gemini(prompt)

    # Persiste no cache (upsert) com o snapshot de votos
    db.execute(
        text(
            "INSERT INTO ai_reports (candidate_id, content, model, votes_snapshot) "
            "VALUES (:cid, :content, :model, :snap) "
            "ON CONFLICT (candidate_id) DO UPDATE SET content = :content, "
            "model = :model, votes_snapshot = :snap, created_at = now()"
        ),
        {
            "cid": str(candidate_id),
            "content": json.dumps(report, ensure_ascii=False),
            "model": GEMINI_MODEL,
            "snap": current_votes,
        },
    )
    db.commit()
    return report


def _call_gemini(prompt: str) -> dict:
    """
    Chama o Gemini exigindo JSON. Lança AiReportError em falha/cota.
    Faz retry em 503 (modelo sobrecarregado no Google) — erro transitório.
    """
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise AiReportError("IA não configurada (sem chave). Avise o suporte.")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "responseMimeType": "application/json"},
    }
    last_err = ""
    for attempt in range(3):
        try:
            with httpx.Client(timeout=60.0) as c:
                r = c.post(f"{GEMINI_URL}?key={key}", json=payload)
            if r.status_code == 429:
                raise AiReportError("Cota de IA esgotada no momento. Tente novamente mais tarde.")
            if r.status_code == 503:
                # Modelo sobrecarregado no Google — espera e tenta de novo.
                last_err = "503 overloaded"
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise AiReportError("IA temporariamente sobrecarregada. Tente novamente em instantes.")
            r.raise_for_status()
            data = r.json()
            # O Gemini devolve o consumo de tokens em usageMetadata — registramos
            # entrada/saída/total pra dar visibilidade de custo por requisição.
            # (promptTokenCount = entrada; candidatesTokenCount = saída;
            #  thoughtsTokenCount = raciocínio interno do 2.5-flash, conta na
            #  cobrança mas não aparece na saída — por isso total > entrada+saída.)
            usage = data.get("usageMetadata") or {}
            log.info(
                "ai_gemini_usage",
                model=GEMINI_MODEL,
                tokens_entrada=usage.get("promptTokenCount"),
                tokens_saida=usage.get("candidatesTokenCount"),
                tokens_raciocinio=usage.get("thoughtsTokenCount"),
                tokens_total=usage.get("totalTokenCount"),
            )
            return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
        except AiReportError:
            raise
        except Exception as e:  # pragma: no cover
            last_err = str(e)[:200]
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            log.warning("ai_gemini_failed", err=last_err)
            raise AiReportError("Falha ao gerar a análise. Tente novamente.")
    raise AiReportError("Falha ao gerar a análise. Tente novamente.")


def _head_to_head(db: Session, a: Candidate, b: Candidate) -> dict:
    """Municípios onde A e B têm voto: quem lidera, por quanto e quanto do
    eleitorado NENHUM dos dois atingiu.

    Calcula o "eleitorado não atingido" (eleitorado − votosA − votosB) e a %
    EXATOS no código e injeta no confronto — antes a IA não tinha o eleitorado
    no JSON e chutava a porcentagem (ex.: 97% no lugar de 96%).
    """
    va = dict(
        db.execute(
            select(VoteResult.municipality_id, VoteResult.votes).where(
                VoteResult.candidate_id == a.id
            )
        ).all()
    )
    vb = dict(
        db.execute(
            select(VoteResult.municipality_id, VoteResult.votes).where(
                VoteResult.candidate_id == b.id
            )
        ).all()
    )
    shared = set(va) & set(vb)

    # Eleitorado mais recente por município disputado (pra % exata, sem mistura
    # de cargos — votos vêm por candidato, que é uma só candidatura/cargo).
    elect_map: dict = {}
    if shared:
        latest_elect = (
            select(
                MunicipalityElectorate.municipality_id.label("mid"),
                func.max(MunicipalityElectorate.year).label("y"),
            )
            .group_by(MunicipalityElectorate.municipality_id)
            .subquery()
        )
        elect_map = dict(
            db.execute(
                select(
                    MunicipalityElectorate.municipality_id,
                    MunicipalityElectorate.total,
                )
                .join(
                    latest_elect,
                    (MunicipalityElectorate.municipality_id == latest_elect.c.mid)
                    & (MunicipalityElectorate.year == latest_elect.c.y),
                )
                .where(MunicipalityElectorate.municipality_id.in_(shared))
            ).all()
        )

    name_map = {
        m.id: f"{m.name}/{m.state}"
        for m in db.execute(
            select(Municipality).where(Municipality.id.in_(shared))
        ).scalars()
    } if shared else {}

    rows = []
    for mid in shared:
        vot_a = int(va[mid] or 0)
        vot_b = int(vb[mid] or 0)
        elect = int(elect_map.get(mid, 0) or 0)
        nao_atingido = max(0, elect - vot_a - vot_b) if elect else None
        nao_atingido_pct = (
            round(100 * nao_atingido / elect, 1) if elect and nao_atingido is not None else None
        )
        rows.append(
            {
                "municipio": name_map.get(mid, "?"),
                "voce": vot_a,
                "adversario": vot_b,
                "diff": vot_a - vot_b,
                "eleitorado_total": elect or None,
                "eleitorado_nao_atingido": nao_atingido,
                "nao_atingido_pct": nao_atingido_pct,
            }
        )
    a_leads = sorted([r for r in rows if r["diff"] > 0], key=lambda r: r["diff"], reverse=True)[:10]
    b_leads = sorted([r for r in rows if r["diff"] < 0], key=lambda r: r["diff"])[:10]

    def _fmt(r: dict, key_vant: str) -> dict:
        out = {k: r[k] for k in ("municipio", "voce", "adversario", "eleitorado_total",
                                 "eleitorado_nao_atingido", "nao_atingido_pct")}
        out[key_vant] = abs(r["diff"])
        return out

    return {
        "municipios_disputados": len(shared),
        "cargo": a.office_name,
        "a_lidera_em": [_fmt(r, "vantagem") for r in a_leads],
        "adversario_lidera_em": [_fmt(r, "desvantagem") for r in b_leads],
    }


_COMPARE_PROMPT = """Você é um consultor político sênior. Compare dois candidatos \
com base nos DADOS REAIS do TSE e gere uma análise de CONFRONTO DIRETO, da \
perspectiva do CANDIDATO (não do adversário), em português do Brasil.

CANDIDATO (você assessora este):
{candidato}

ADVERSÁRIO:
{adversario}

CONFRONTO MUNICÍPIO A MUNICÍPIO (dados verificados do TSE — cargo: {cargo}):
{confronto}

REGRAS CRÍTICAS DE NÚMEROS (não desobedeça):
- "eleitorado_nao_atingido" e "nao_atingido_pct" no confronto já vêm CALCULADOS \
(eleitorado − seus votos − votos do adversário). USE esses números EXATAMENTE; \
NUNCA recalcule nem invente porcentagens.
- Todos os votos são do MESMO cargo ({cargo}) — não some votos de cargos diferentes.
- Em "onde_atacar", priorize municípios com maior "eleitorado_nao_atingido" e \
cite o número/percentual exato do JSON.

Responda APENAS com JSON válido (sem markdown), nesta estrutura exata:
{{
  "panorama": "2-3 frases sobre o confronto e quem larga na frente",
  "quem_lidera": "<nome do que está em melhor posição> + 1 frase do porquê",
  "minhas_vantagens": ["3-4 vantagens concretas do CANDIDATO sobre o adversário"],
  "vantagens_adversario": ["3-4 forças do adversário que o candidato precisa observar"],
  "onde_atacar": ["3-4 municípios onde há mais eleitorado não atingido — cite o número exato do JSON"],
  "onde_defender": ["3-4 municípios/segmentos onde o candidato precisa segurar a base"],
  "recomendacao_final": "1-2 frases de estratégia direta pro candidato vencer o confronto"
}}

Cite municípios e números reais. Não invente dados. Tom técnico, sem ofensas."""


def generate_comparison(
    db: Session, candidate_id: UUID, adversary_id: UUID, *, force: bool = False
) -> dict:
    """Confronto estratégico A×B por IA (cache direcional por par)."""
    if candidate_id == adversary_id:
        raise AiReportError("Escolha um adversário diferente do candidato.")
    # Snapshot = soma das votações dos dois — muda se qualquer um for re-sincronizado.
    current_votes = (
        _candidate_total_votes(db, candidate_id)
        + _candidate_total_votes(db, adversary_id)
    )
    if not force:
        row = db.execute(
            text(
                "SELECT content, votes_snapshot FROM ai_comparisons "
                "WHERE candidate_id = :a AND adversary_id = :b"
            ),
            {"a": str(candidate_id), "b": str(adversary_id)},
        ).first()
        if row is not None and row.votes_snapshot == current_votes:
            content = row.content
            return content if isinstance(content, dict) else json.loads(content)

    a = db.get(Candidate, candidate_id)
    b = db.get(Candidate, adversary_id)
    if a is None or b is None:
        raise AiReportError("Candidato ou adversário não encontrado")

    # Confronto só faz sentido entre o MESMO cargo — comparar vereador com
    # prefeito mistura disputas diferentes (e distorceria a % de eleitorado).
    if a.office_code != b.office_code:
        raise AiReportError(
            f"Os dois concorrem a cargos diferentes ({a.office_name} × "
            f"{b.office_name}). Escolha um adversário do mesmo cargo."
        )

    fa = _gather_facts(db, a)
    fb = _gather_facts(db, b)
    h2h = _head_to_head(db, a, b)
    prompt = _COMPARE_PROMPT.format(
        candidato=json.dumps(fa, ensure_ascii=False, indent=2),
        adversario=json.dumps(fb, ensure_ascii=False, indent=2),
        confronto=json.dumps(h2h, ensure_ascii=False, indent=2),
        cargo=a.office_name,
    )
    report = _call_gemini(prompt)
    report["confronto"] = h2h  # anexa os números pro frontend exibir

    db.execute(
        text(
            "INSERT INTO ai_comparisons "
            "(candidate_id, adversary_id, content, model, votes_snapshot) "
            "VALUES (:a, :b, :content, :model, :snap) "
            "ON CONFLICT (candidate_id, adversary_id) DO UPDATE SET "
            "content = :content, model = :model, votes_snapshot = :snap, "
            "created_at = now()"
        ),
        {
            "a": str(candidate_id),
            "b": str(adversary_id),
            "content": json.dumps(report, ensure_ascii=False),
            "model": GEMINI_MODEL,
            "snap": current_votes,
        },
    )
    db.commit()
    return report


# ============================================================ CENSO (Maré IA Território)


def _gather_census_facts(db, cd_mun: str) -> dict:
    """Resumo do município a partir do census_geo (IBGE 2022)."""
    from sqlalchemy import text as _t

    head = db.execute(_t(
        "SELECT max(nm_mun) AS nm, count(*) AS setores, "
        "coalesce(sum(populacao),0) AS pop, coalesce(sum(domicilios),0) AS dom, "
        "coalesce(sum(area_km2),0) AS area, "
        "coalesce(sum(populacao) FILTER (WHERE situacao='Urbana'),0) AS pop_urb, "
        "count(DISTINCT nm_dist) AS distritos, "
        "count(DISTINCT nm_bairro) FILTER (WHERE nm_bairro<>'') AS bairros "
        "FROM census_geo WHERE level='setor' AND cd_mun=:m"
    ), {"m": cd_mun}).mappings().first()
    if not head or not head["pop"]:
        raise AiReportError("Município sem dados censitários carregados.")

    areas = db.execute(_t(
        "SELECT coalesce(NULLIF(nm_bairro,''), nm_dist) AS nome, "
        "sum(populacao) AS pop, sum(domicilios) AS dom, sum(area_km2) AS area "
        "FROM census_geo WHERE level='setor' AND cd_mun=:m "
        "GROUP BY 1 ORDER BY sum(populacao) DESC LIMIT 12"
    ), {"m": cd_mun}).mappings().all()

    return {
        "nome": head["nm"],
        "populacao": int(head["pop"]),
        "domicilios": int(head["dom"]),
        "densidade_hab_km2": round(head["pop"] / head["area"], 1) if head["area"] else None,
        "pct_urbana": round(100 * head["pop_urb"] / head["pop"], 1),
        "media_moradores_por_domicilio": round(head["pop"] / head["dom"], 2) if head["dom"] else None,
        "distritos": int(head["distritos"]),
        "bairros_mapeados": int(head["bairros"]),
        "maiores_areas": [
            {
                "nome": a["nome"], "populacao": int(a["pop"] or 0),
                "domicilios": int(a["dom"] or 0),
                "densidade": round((a["pop"] or 0) / a["area"], 0) if a["area"] else None,
            }
            for a in areas
        ],
    }


def generate_census_insight(db, cd_mun: str, *, force: bool = False) -> dict:
    """Leitura estratégica do território (Maré IA) com cache em ai_census_insights."""
    from sqlalchemy import text as _t

    if not force:
        hit = db.execute(_t(
            "SELECT content, model, created_at FROM ai_census_insights WHERE cd_mun=:m"
        ), {"m": cd_mun}).mappings().first()
        if hit:
            content = hit["content"]
            if not isinstance(content, dict):
                content = json.loads(content)
            return {"content": content, "model": hit["model"],
                    "created_at": str(hit["created_at"]), "cached": True}

    facts = _gather_census_facts(db, cd_mun)
    prompt = (
        "Você é a Maré IA, especialista em estratégia eleitoral brasileira. "
        "Com base APENAS nos dados do Censo IBGE 2022 abaixo, produza uma leitura "
        "estratégica do território para uma campanha municipal. Responda SOMENTE "
        "com JSON válido, em português, neste formato exato:\n"
        '{"perfil": "2-3 frases sobre o perfil demográfico do município",'
        '"leitura_estrategica": "3-4 frases de estratégia territorial: onde concentrar '
        'esforço de campanha e por quê, citando áreas pelo nome",'
        '"publicos": ["3 a 4 públicos-alvo prioritários inferidos dos dados"],'
        '"recomendacoes": ["4 a 5 ações táticas concretas citando áreas pelo nome"]}\n\n'
        f"DADOS DO CENSO 2022 — {facts['nome']}:\n" + json.dumps(facts, ensure_ascii=False)
    )
    content = _call_gemini(prompt)
    db.execute(_t(
        "INSERT INTO ai_census_insights (cd_mun, content, model) "
        "VALUES (:m, CAST(:c AS jsonb), :mo) "
        "ON CONFLICT (cd_mun) DO UPDATE SET content=CAST(:c AS jsonb), "
        "model=:mo, created_at=now()"
    ), {"m": cd_mun, "c": json.dumps(content, ensure_ascii=False), "mo": GEMINI_MODEL})
    db.commit()
    return {"content": content, "model": GEMINI_MODEL, "created_at": "agora", "cached": False}
