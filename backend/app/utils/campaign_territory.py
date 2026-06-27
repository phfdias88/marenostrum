"""
Inteligência de Território (Maré IA) — cruza os CONTATOS privados da campanha
(CRM, por tenant) com o eleitorado (TSE), os votos do candidato e do
adversário (por município) e a população do censo (por bairro, onde houver),
e gera uma leitura tática por IA.

ISOLAMENTO MULTI-TENANT (importante): diferente de ai-report/ai-compare —
que cacheiam GLOBALMENTE por candidato porque só usam dado público do TSE —
esta análise usa dados PRIVADOS do tenant (os contatos do CRM). Por isso o
cache é chaveado por (tenant_id, candidate_id, adversary_id) na tabela
ai_territory e JAMAIS é servido a outro tenant. Poluir o cache global com
contatos vazaria dados de uma campanha pra outra.
"""
from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.tse import (
    Candidate,
    Election,
    Municipality,
    MunicipalityElectorate,
    Party,
    VoteResult,
)
from app.utils.ai_report import GEMINI_MODEL, AiReportError, _call_gemini


def _contacts_count(db: Session, tenant_id: UUID) -> int:
    """Contatos ativos do tenant — snapshot pra invalidar o cache."""
    return int(
        db.execute(
            select(func.count())
            .select_from(Contact)
            .where(Contact.tenant_id == tenant_id, Contact.is_active.is_(True))
        ).scalar()
        or 0
    )


def _candidate_votes_total(db: Session, candidate_id: UUID) -> int:
    return int(
        db.execute(
            select(func.coalesce(func.sum(VoteResult.votes), 0)).where(
                VoteResult.candidate_id == candidate_id
            )
        ).scalar()
        or 0
    )


def _census_pop_by_area(db: Session, city: str) -> dict[str, int]:
    """População do censo por bairro/distrito da cidade (match por nome).

    Só há censo carregado pra parte do país (RJ no MVP). Retorna {} se a
    cidade não tem setores censitários — aí o bairro fica só com contatos.
    Chave normalizada (sem acento, minúscula) pra casar com os contatos.
    """
    rows = db.execute(
        text(
            "SELECT lower(f_unaccent(coalesce(NULLIF(nm_bairro,''), nm_dist))) AS k, "
            "       sum(populacao) AS pop "
            "FROM census_geo "
            "WHERE level='setor' AND lower(f_unaccent(nm_mun)) = lower(f_unaccent(:c)) "
            "GROUP BY 1"
        ),
        {"c": city},
    ).all()
    return {k: int(p or 0) for k, p in rows if k}


def _gather_territory_facts(
    db: Session, tenant_id: UUID, candidate: Candidate, adversary: Candidate
) -> dict:
    """Monta o dossiê território = contatos do tenant × dados eleitorais."""
    party_c = db.get(Party, candidate.party_id)
    party_a = db.get(Party, adversary.party_id)
    elec_c = db.get(Election, candidate.election_id)
    elec_a = db.get(Election, adversary.election_id)

    total_contacts = _contacts_count(db, tenant_id)

    city_expr = func.coalesce(func.nullif(func.trim(Contact.city), ""), "")
    uf_expr = func.coalesce(func.nullif(func.trim(Contact.state), ""), "")

    # Contatos por cidade (top 30 cidades onde a campanha tem gente).
    city_rows = db.execute(
        select(
            city_expr.label("city"),
            uf_expr.label("uf"),
            func.count().label("n"),
        )
        .where(
            Contact.tenant_id == tenant_id,
            Contact.is_active.is_(True),
            city_expr != "",
        )
        .group_by(city_expr, uf_expr)
        .order_by(func.count().desc())
        .limit(30)
    ).all()

    municipios: list[dict] = []
    main_city: tuple[str, str, Municipality] | None = None
    for city, uf, n in city_rows:
        m = db.execute(
            select(Municipality)
            .where(
                func.lower(func.f_unaccent(Municipality.name))
                == func.lower(func.f_unaccent(city)),
                *([Municipality.state == uf] if uf else []),
            )
            .limit(1)
        ).scalar_one_or_none()
        if m is None:
            municipios.append(
                {
                    "municipio": f"{city}{('/' + uf) if uf else ''}",
                    "contatos": int(n),
                    "eleitorado": None,
                    "cobertura_pct": None,
                    "votos_candidato": None,
                    "votos_adversario": None,
                    "casado_tse": False,
                }
            )
            continue

        elect = db.execute(
            select(MunicipalityElectorate.total)
            .where(MunicipalityElectorate.municipality_id == m.id)
            .order_by(MunicipalityElectorate.year.desc())
            .limit(1)
        ).scalar()
        vc = db.execute(
            select(VoteResult.votes).where(
                VoteResult.candidate_id == candidate.id,
                VoteResult.municipality_id == m.id,
            )
        ).scalar()
        va = db.execute(
            select(VoteResult.votes).where(
                VoteResult.candidate_id == adversary.id,
                VoteResult.municipality_id == m.id,
            )
        ).scalar()
        cov = round(int(n) / int(elect) * 100, 2) if elect else None
        municipios.append(
            {
                "municipio": f"{m.name}/{m.state}",
                "contatos": int(n),
                "eleitorado": int(elect) if elect else None,
                "cobertura_pct": cov,
                "votos_candidato": int(vc) if vc is not None else 0,
                "votos_adversario": int(va) if va is not None else 0,
                "casado_tse": True,
            }
        )
        if main_city is None:
            main_city = (city, uf, m)

    # Bairros da cidade principal (onde a campanha tem mais contatos).
    bairros: list[dict] = []
    main_city_name: str | None = None
    if main_city is not None:
        city, uf, m = main_city
        main_city_name = f"{m.name}/{m.state}"
        census_pop = _census_pop_by_area(db, city)
        nb_expr = func.coalesce(
            func.nullif(func.trim(Contact.neighborhood), ""), "(sem bairro)"
        )
        nb_rows = db.execute(
            select(nb_expr.label("b"), func.count().label("n"))
            .where(
                Contact.tenant_id == tenant_id,
                Contact.is_active.is_(True),
                func.lower(func.f_unaccent(city_expr))
                == func.lower(func.f_unaccent(city)),
            )
            .group_by(nb_expr)
            .order_by(func.count().desc())
            .limit(15)
        ).all()
        for b, n in nb_rows:
            # casa o bairro do contato com o do censo pela chave normalizada
            pop = census_pop.get(_norm(b))
            cov = round(int(n) / pop * 100, 2) if pop else None
            bairros.append(
                {
                    "bairro": b,
                    "contatos": int(n),
                    "populacao_censo": pop,
                    "cobertura_pct": cov,
                }
            )

    return {
        "candidato": {
            "nome": candidate.urn_name,
            "cargo": candidate.office_name,
            "partido": party_c.abbreviation if party_c else None,
            "ano": elec_c.year if elec_c else None,
        },
        "adversario": {
            "nome": adversary.urn_name,
            "cargo": adversary.office_name,
            "partido": party_a.abbreviation if party_a else None,
            "ano": elec_a.year if elec_a else None,
        },
        "total_contatos_campanha": total_contacts,
        "cidade_principal": main_city_name,
        "por_municipio": municipios,
        "bairros_cidade_principal": bairros,
    }


def _norm(s: str) -> str:
    """Normalização leve (minúscula + remove acento comum) pra casar bairros."""
    import unicodedata

    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


_PROMPT = """Você é a Maré IA, consultora de estratégia eleitoral brasileira. \
Você tem acesso aos CONTATOS REAIS cadastrados por esta campanha (CRM próprio) \
cruzados com o eleitorado e os votos do TSE. Gere uma leitura TÁTICA de \
território, da perspectiva do CANDIDATO, em português do Brasil.

DADOS (contatos da campanha × eleitorado × votos):
{facts}

Entenda os campos:
- "contatos": eleitores que ESTA campanha já cadastrou naquele local.
- "eleitorado": total de eleitores do município (TSE).
- "cobertura_pct": contatos ÷ eleitorado (município) ou contatos ÷ população \
do censo (bairro) — o quanto a campanha já alcançou ali.
- "votos_candidato"/"votos_adversario": votação de cada um no município na \
última eleição registrada.

Responda APENAS com JSON válido (sem markdown, sem ```), nesta estrutura exata:
{{
  "panorama": "2-3 frases: onde a campanha tem presença (contatos) vs onde o adversário é forte",
  "onde_tenho_base": ["3-4 locais onde a campanha já tem boa cobertura de contatos — consolidar"],
  "onde_falta_cadastrar": ["3-4 locais com muito eleitorado e POUCOS contatos — prioridade de mutirão de cadastro"],
  "onde_disputar_adversario": ["3-4 municípios onde o adversário fez votos e a campanha pode crescer, citando os números"],
  "meta_cadastro": ["2-3 metas concretas de cadastro por local, com números (ex: 'Bairro X: subir de N para M contatos')"],
  "acoes_prioritarias": ["3-4 ações práticas de campo pros próximos meses"]
}}

Cite locais e números REAIS dos dados. Não invente. Quando um local não casou \
com o TSE (casado_tse=false), trate como dado só de contatos. Tom técnico e \
direto, sem ofensas."""


def generate_territory(
    db: Session,
    tenant_id: UUID,
    candidate_id: UUID,
    adversary_id: UUID,
    *,
    force: bool = False,
) -> dict:
    """
    Gera (ou serve do cache ISOLADO por tenant) a Inteligência de Território.
    Cache invalidado quando muda a contagem de contatos do tenant OU a votação
    de candidato/adversário (re-sync TSE).
    """
    if candidate_id == adversary_id:
        raise AiReportError("Escolha um adversário diferente do candidato.")

    contacts_snap = _contacts_count(db, tenant_id)
    votes_snap = _candidate_votes_total(db, candidate_id) + _candidate_votes_total(
        db, adversary_id
    )

    if not force:
        row = db.execute(
            text(
                "SELECT content, contacts_snapshot, votes_snapshot FROM ai_territory "
                "WHERE tenant_id = :t AND candidate_id = :c AND adversary_id = :a"
            ),
            {"t": str(tenant_id), "c": str(candidate_id), "a": str(adversary_id)},
        ).first()
        if (
            row is not None
            and row.contacts_snapshot == contacts_snap
            and row.votes_snapshot == votes_snap
        ):
            content = row.content
            return content if isinstance(content, dict) else json.loads(content)

    candidate = db.get(Candidate, candidate_id)
    adversary = db.get(Candidate, adversary_id)
    if candidate is None or adversary is None:
        raise AiReportError("Candidato ou adversário não encontrado")

    if contacts_snap == 0:
        raise AiReportError(
            "Sua campanha ainda não tem contatos cadastrados. Cadastre eleitores "
            "no CRM para a Maré IA cruzar com o território."
        )

    facts = _gather_territory_facts(db, tenant_id, candidate, adversary)
    prompt = _PROMPT.format(facts=json.dumps(facts, ensure_ascii=False, indent=2))
    report = _call_gemini(prompt)
    report["dados"] = facts  # anexa os números pro frontend exibir as tabelas

    db.execute(
        text(
            "INSERT INTO ai_territory "
            "(tenant_id, candidate_id, adversary_id, content, model, "
            " contacts_snapshot, votes_snapshot) "
            "VALUES (:t, :c, :a, :content, :model, :cs, :vs) "
            "ON CONFLICT (tenant_id, candidate_id, adversary_id) DO UPDATE SET "
            "content = :content, model = :model, contacts_snapshot = :cs, "
            "votes_snapshot = :vs, created_at = now()"
        ),
        {
            "t": str(tenant_id),
            "c": str(candidate_id),
            "a": str(adversary_id),
            "content": json.dumps(report, ensure_ascii=False),
            "model": GEMINI_MODEL,
            "cs": contacts_snap,
            "vs": votes_snap,
        },
    )
    db.commit()
    return report
