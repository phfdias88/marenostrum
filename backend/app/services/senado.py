"""Senadores em exercicio: ler a lista do Senado, gravar e responder quem fica.

Fonte: https://legis.senado.leg.br/dadosabertos/senador/lista/atual (publica,
sem chave). Traz os 81 em exercicio com partido de hoje, UF e as duas
legislaturas do mandato.

`gravar` TROCA a lista inteira: ela e um retrato, e quem saiu do exercicio (o
titular voltou, o suplente saiu) nao pode ficar para tras contando cadeira.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models.senado import SenateMember

log = structlog.get_logger("marenostrum.services.senado")

URL_EM_EXERCICIO = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json"

# O Senado tem 81 cadeiras. Uma lista muito menor que isso e resposta truncada
# ou formato novo — gravar apagaria a bancada boa que ja estava no banco.
MINIMO_ACEITAVEL = 70

# A data que vai para a tela e a de Brasilia: a carga feita as 21h30 de la ja
# e "amanha" em UTC, e a observacao anunciaria uma lista do dia seguinte.
_BRT = timezone(timedelta(hours=-3))


class ListaDoSenadoInvalida(ValueError):
    """A resposta do Senado nao tem a forma esperada; nada e gravado."""


def ler_lista(dado: dict) -> list[dict[str, Any]]:
    """Achata a resposta do Senado em {code, name, state, party_abbr, role, term_end}."""
    try:
        parlamentares = (
            dado["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
        )
    except (KeyError, TypeError) as exc:
        raise ListaDoSenadoInvalida("resposta sem a lista de parlamentares") from exc
    if isinstance(parlamentares, dict):      # um so item vem como objeto, nao lista
        parlamentares = [parlamentares]

    itens: list[dict[str, Any]] = []
    for p in parlamentares:
        ident = p.get("IdentificacaoParlamentar") or {}
        mandato = p.get("Mandato") or {}
        # O mandato de senador cobre duas legislaturas; o fim e o da ultima.
        fins = [
            (mandato.get(chave) or {}).get("DataFim")
            for chave in ("PrimeiraLegislaturaDoMandato", "SegundaLegislaturaDoMandato")
        ]
        fins = [f for f in fins if f]
        codigo = str(ident.get("CodigoParlamentar") or "").strip()
        uf = (ident.get("UfParlamentar") or mandato.get("UfParlamentar") or "").strip()
        if not (codigo.isdigit() and uf and fins):
            continue
        itens.append({
            "code": int(codigo),
            "name": (ident.get("NomeParlamentar") or "").strip()[:120],
            "state": uf.upper()[:2],
            # Senador sem partido vem sem a chave, ou como "S/Partido".
            "party_abbr": (ident.get("SiglaPartidoParlamentar") or "S/Partido").strip()[:30],
            "role": (mandato.get("DescricaoParticipacao") or "").strip()[:30] or None,
            "term_end": date.fromisoformat(max(fins)),
        })
    return itens


def gravar(db: Session, itens: list[dict[str, Any]]) -> int:
    """Troca a lista inteira pela nova. Recusa lista curta demais."""
    if len(itens) < MINIMO_ACEITAVEL:
        raise ListaDoSenadoInvalida(
            f"so {len(itens)} senadores na lista; esperado perto de 81"
        )
    agora = datetime.now(timezone.utc)
    db.execute(delete(SenateMember))
    db.execute(insert(SenateMember), [
        {"id": uuid4(), "created_at": agora, "updated_at": agora, **i} for i in itens
    ])
    db.commit()
    log.info("senado_lista_gravada", senadores=len(itens))
    return len(itens)


def _ultima_carga(db: Session) -> datetime | None:
    quando = db.execute(select(func.max(SenateMember.updated_at))).scalar()
    if quando is not None and quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)   # SQLite devolve sem fuso
    return quando


def atualizado_em(db: Session) -> date | None:
    """Dia (em Brasilia) da ultima carga — a lista e trocada inteira, e uma data so."""
    quando = _ultima_carga(db)
    return quando.astimezone(_BRT).date() if quando else None


def versao_da_lista(db: Session) -> int:
    """Muda a cada carga. Vai na chave de cache de quem depende da lista: a
    carga roda em OUTRO processo e nao alcanca o cache em memoria da API."""
    quando = _ultima_carga(db)
    return int(quando.timestamp() * 1000) if quando else 0


def fim_do_mandato_de_quem_fica(ano_da_eleicao: int) -> int:
    """Ano em que termina o mandato de quem NAO esta em disputa naquela eleicao.

    Quem fica foi eleito quatro anos antes, tomou posse no ano seguinte e tem
    oito anos de mandato: na eleicao de 2026 ficam os eleitos em 2022, ate 2031.
    """
    return ano_da_eleicao + 5


def no_mandato(db: Session, ano_da_eleicao: int) -> list[SenateMember]:
    """Quem esta em exercicio e CONTINUA depois da eleicao daquele ano.

    Filtra pela TURMA (o ano em que o mandato acaba), e nao por "mandato alem
    da posse": depois que os eleitos do ano tomam posse eles tambem tem mandato
    alem dela, e a lista viraria o Senado inteiro.
    """
    fim = fim_do_mandato_de_quem_fica(ano_da_eleicao)
    return list(db.execute(
        select(SenateMember)
        .where(
            SenateMember.term_end >= date(fim, 1, 1),
            SenateMember.term_end <= date(fim, 12, 31),
        )
        .order_by(SenateMember.state, SenateMember.name)
    ).scalars())
