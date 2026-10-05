"""Duas eleicoes lado a lado: a bancada que fica e a que entra, e a virada no mapa.

BANCADA. O Senado renova em partes: quem foi eleito ha quatro anos continua no
mandato, e a eleicao do ano preenche o resto. A tela mostra os dois grupos por
partido. Para a Camara nao existe "quem fica" — a casa inteira e renovada —,
entao o mesmo quadro vira "bancada eleita ha quatro anos x eleita agora".

Tres limites do dado, todos ditos na resposta em vez de escondidos:

  * QUEM ESTA NO MANDATO VEM DO SENADO, QUANDO HA. O TSE nao publica troca de
    partido durante o mandato, nem suplente que assumiu. Para a eleicao mais
    recente, "no mandato" e a lista de senadores em exercicio do proprio
    Senado, pela filiacao de hoje (`fonte_do_mandato = "senado"`). Sem essa
    lista, ou para eleicao antiga, cai em quem foi ELEITO ha quatro anos, pelo
    partido de entao levado ao sucessor legal (`"tse"`) — e ai o numero pode
    diferir do que a imprensa mostra.
  * ELEITO E SO QUEM O TSE PROCLAMOU. Na noite da apuracao a situacao chega UF
    por UF. Onde ainda nao chegou, os mais votados entram como "a frente" —
    separados dos eleitos, nunca somados a eles como se fossem oficiais.
  * NAO SE PROJETA DEPUTADO. A vaga proporcional depende do quociente do
    partido; "os mais votados" nao e uma previsao valida. Camara so mostra os
    proclamados.

VIRADA. Compara o partido mais votado de cada municipio em duas eleicoes. Le a
tabela materializada tse_winners_map (duas leituras por indice) e cruza em
memoria — o cruzamento direto em tse_vote_results custaria minutos.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from types import SimpleNamespace
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.tse.candidate import Candidate
from app.models.tse.election import Election
from app.models.tse.party import Party
from app.services import senado as senado_federal
from app.utils.agg_cache import cached_agg
from app.utils.partidos import normalizar_sigla, numero_sucessor, sigla_no_ano

log = structlog.get_logger("marenostrum.services.eleicao_comparada")

SENADOR = 5
DEPUTADO_FEDERAL = 6
_CASAS = {SENADOR: "Senado Federal", DEPUTADO_FEDERAL: "Câmara dos Deputados"}

# Mandato de senador dura 8 anos e a eleicao e a cada 4: sempre ha uma turma
# no meio do mandato.
_INTERVALO = 4


def vagas_de_senador(ano: int) -> int:
    """Vagas de senador POR UF na eleicao do ano.

    O Senado renova um terco e dois tercos alternadamente: duas vagas por UF em
    2018 e 2026, uma em 2022 e 2030.
    """
    return 2 if (ano - 2018) % 8 == 0 else 1


def _eleito(situacao: str | None) -> bool:
    """Mesmo criterio de election_queries._eh_eleito_sql, no lado do Python.

    Por PREFIXO: "ELEITO" esta dentro de "NÃO ELEITO"."""
    s = (situacao or "").strip().upper()
    return s.startswith("ELEITO") or s == "MÉDIA"


def _derrotado(situacao: str | None) -> bool:
    s = (situacao or "").strip().upper()
    return s.startswith("NÃO ELEITO") or s.startswith("NAO ELEITO")


# ------------------------------------------------------------------ bancada

def get_bancada(db: Session, *, ano: int, cargo: int) -> dict[str, Any]:
    if cargo not in _CASAS:
        raise DomainError(
            "Bancada existe para senador (5) e deputado federal (6)."
        )
    chave = f"bancada:{ano}:{cargo}"
    if cargo == SENADOR:
        # A lista do Senado e carregada por um script, fora deste processo: sem
        # a versao dela na chave, a tela seguia ate 4h com a filiacao da carga
        # anterior (ou com os eleitos de 2022, se a primeira visita veio antes
        # da primeira carga). O ano continua na chave para a limpeza da apuracao.
        chave += f":{senado_federal.versao_da_lista(db)}"
    return cached_agg(chave, lambda: _calcular_bancada(db, ano, cargo))


def _candidatos(db: Session, ano: int, cargo: int):
    return db.execute(
        select(
            Candidate.state, Candidate.urn_name, Candidate.total_votes,
            Candidate.result_status, Party.number, Party.abbreviation,
        )
        .select_from(Candidate)
        .join(Election, Election.id == Candidate.election_id)
        .join(Party, Party.id == Candidate.party_id)
        .where(Election.year == ano, Candidate.office_code == cargo)
    ).all()


# Senador sem partido: linha propria, fora da numeracao do TSE.
_SEM_PARTIDO = 0


def _em_exercicio(db: Session, ano: int, do_ano) -> list[SimpleNamespace]:
    """Senadores no mandato segundo o Senado, no formato das linhas do TSE.

    Vazio quando o retrato nao serve: tabela sem carga, ou `ano` que nao e a
    eleicao mais recente — a lista e de HOJE, e pinta-la sobre 2022 misturaria
    a filiacao de agora com os eleitos de entao.
    """
    mais_recente = db.execute(
        select(func.max(Election.year)).where(Election.year % 4 == ano % 4)
    ).scalar()
    if mais_recente != ano:
        return []
    membros = senado_federal.no_mandato(db, ano)
    if not membros:
        return []

    # O Senado da a SIGLA; a tela soma por NUMERO. A sigla sozinha e ambigua
    # na nossa tabela (PSD foi 41 e e 55; PODE foi 19 e e 20), entao o numero
    # vem de quem concorre no ano — primeiro para senador, depois qualquer cargo.
    numero_de: dict[str, tuple[int, str]] = {}
    for r in do_ano:
        numero_de.setdefault(normalizar_sigla(r.abbreviation), (r.number, r.abbreviation))
    if any(normalizar_sigla(m.party_abbr) not in numero_de for m in membros):
        for numero, sigla in db.execute(
            select(Party.number, Party.abbreviation)
            .join(Candidate, Candidate.party_id == Party.id)
            .join(Election, Election.id == Candidate.election_id)
            .where(Election.year == ano)
            .distinct()
        ).all():
            numero_de.setdefault(normalizar_sigla(sigla), (numero, sigla))

    linhas: list[SimpleNamespace] = []
    fora_do_tse: dict[str, int] = {}
    for m in membros:
        chave = normalizar_sigla(m.party_abbr)
        if chave in numero_de:
            numero, sigla = numero_de[chave]
        elif chave in ("SPARTIDO", "SEMPARTIDO", ""):
            numero, sigla = _SEM_PARTIDO, "Sem partido"
        else:
            # Legenda que o Senado cita e nao concorreu no ano: linha propria,
            # com numero negativo para nao colidir com nenhum partido do TSE.
            numero = fora_do_tse.setdefault(chave, -(len(fora_do_tse) + 1))
            sigla = m.party_abbr
        linhas.append(SimpleNamespace(
            state=m.state, urn_name=m.name, total_votes=0, result_status=None,
            number=numero, abbreviation=sigla, papel=m.role,
        ))
    return linhas


def _calcular_bancada(db: Session, ano: int, cargo: int) -> dict[str, Any]:
    anterior = ano - _INTERVALO
    senado = cargo == SENADOR

    do_ano = _candidatos(db, ano, cargo)
    em_exercicio = _em_exercicio(db, ano, do_ano) if senado else []
    if em_exercicio:
        # Ja vem com o numero de hoje: nada de levar ao sucessor de 2022.
        de_antes, ano_de_antes = em_exercicio, ano
    else:
        de_antes = [
            r for r in _candidatos(db, anterior, cargo) if _eleito(r.result_status)
        ]
        ano_de_antes = anterior

    por_uf: dict[str, list] = defaultdict(list)
    for r in do_ano:
        por_uf[r.state].append(r)

    cadeiras_antes: dict[str, int] = defaultdict(int)
    for r in de_antes:
        cadeiras_antes[r.state] += 1

    eleitos: list = []
    a_frente: list = []
    ufs_pendentes: list[str] = []
    vagas = vagas_de_senador(ano) if senado else None
    em_disputa = 0
    for uf in sorted(por_uf):
        proclamados = [r for r in por_uf[uf] if _eleito(r.result_status)]
        eleitos.extend(proclamados)
        if not senado:
            # Deputado sai de uma vez por UF, quando o TSE fecha a conta do
            # quociente. UF fechada: as cadeiras sao as que ela elegeu. UF
            # aberta: vale o tamanho da bancada anterior, que e o melhor numero
            # disponivel ate o resultado sair.
            if proclamados:
                em_disputa += len(proclamados)
            else:
                ufs_pendentes.append(uf)
                em_disputa += cadeiras_antes[uf]
            continue
        em_disputa += vagas
        faltam = vagas - len(proclamados)
        if faltam <= 0:
            continue
        ufs_pendentes.append(uf)
        # Majoritario: enquanto o TSE nao proclama, os mais votados sao quem
        # esta na frente. Fica de fora quem ja consta como derrotado.
        na_disputa = sorted(
            (
                r for r in por_uf[uf]
                if not _eleito(r.result_status)
                and not _derrotado(r.result_status)
                and (r.total_votes or 0) > 0
            ),
            key=lambda r: (-(r.total_votes or 0), r.urn_name or ""),
        )
        a_frente.extend(na_disputa[:faltam])

    # A sigla que aparece e a da eleicao mais recente: um senador eleito pelo
    # PSC em 2022 esta hoje na bancada do Podemos, que o incorporou.
    sigla_de: dict[int, str] = {}
    for r in de_antes:
        sigla_de.setdefault(numero_sucessor(r.number, ano_de_antes), r.abbreviation)
    for r in do_ano:
        sigla_de[numero_sucessor(r.number, ano)] = r.abbreviation

    partidos: dict[int, dict[str, Any]] = {}
    cadeiras: list[dict[str, Any]] = []

    def _contar(linhas, ano_da_linha: int, campo: str) -> None:
        for r in linhas:
            numero = numero_sucessor(r.number, ano_da_linha)
            p = partidos.setdefault(numero, {
                "numero": numero, "sigla": sigla_de[numero],
                "antes": 0, "eleitos": 0, "a_frente": 0,
            })
            p[campo] += 1
            cadeiras.append({
                "uf": r.state, "nome": r.urn_name, "numero": numero,
                "sigla": sigla_de[numero], "situacao": campo,
                "votos": int(r.total_votes or 0),
                # So o retrato do Senado sabe se quem ocupa a cadeira e o
                # titular ou o suplente; nas linhas do TSE fica vazio.
                "papel": getattr(r, "papel", None),
            })

    _contar(de_antes, ano_de_antes, "antes")
    _contar(eleitos, ano, "eleitos")
    _contar(a_frente, ano, "a_frente")

    for p in partidos.values():
        # No Senado quem estava continua, entao soma. Na Camara a bancada
        # antiga e SUBSTITUIDA: somar daria uma casa com o dobro do tamanho.
        entrando = p["eleitos"] + p["a_frente"]
        p["total"] = p["antes"] + entrando if senado else entrando

    lista = sorted(
        partidos.values(),
        key=lambda p: (-p["total"], -p["eleitos"], -p["antes"], p["sigla"]),
    )

    fonte_do_mandato = mandato_ate = mandato_atualizado_em = None
    if senado:
        mandato_ate = senado_federal.fim_do_mandato_de_quem_fica(ano)
        a_frente_txt = (
            " 'À frente' são os mais votados nas UFs onde o TSE ainda não "
            "proclamou o resultado — não são eleitos."
        )
        if em_exercicio:
            fonte_do_mandato = "senado"
            carga = senado_federal.atualizado_em(db)
            mandato_atualizado_em = carga.isoformat() if carga else None
            quando = f" (lista de {carga:%d/%m/%Y})" if carga else ""
            observacao = (
                f"'No mandato' são os senadores em exercício com mandato até "
                f"{mandato_ate}, pela filiação de hoje segundo o Senado "
                f"Federal{quando}: já considera troca de partido e suplente "
                "que assumiu a cadeira." + a_frente_txt
            )
        else:
            fonte_do_mandato = "tse"
            observacao = (
                f"'No mandato' são os senadores eleitos em {anterior}, pelo "
                "partido daquela eleição: o TSE não publica troca de partido "
                "durante o mandato nem suplente que assumiu, então o número "
                "pode diferir do que usa a filiação de hoje." + a_frente_txt
            )
    else:
        observacao = (
            f"A Câmara é renovada por inteiro: a coluna de {anterior} é a "
            "bancada eleita naquele ano, não gente que continua. Só entram como "
            "eleitos os deputados que o TSE já proclamou; vaga proporcional "
            "depende do quociente do partido e não se projeta pelos mais votados."
        )
        if ufs_pendentes:
            observacao += (
                " Nas UFs ainda sem resultado, o total de cadeiras considera o "
                f"mesmo número de {anterior}."
            )

    log.info(
        "bancada_pronta", ano=ano, cargo=cargo, antes=len(de_antes),
        eleitos=len(eleitos), a_frente=len(a_frente), pendentes=len(ufs_pendentes),
        fonte_do_mandato=fonte_do_mandato,
    )
    return {
        "ano": ano,
        "ano_anterior": anterior,
        "cargo": cargo,
        "casa": _CASAS[cargo],
        "modo": "soma" if senado else "troca",
        "vagas_por_uf": vagas,
        "em_disputa": em_disputa,
        "antes": len(de_antes),
        "eleitos": len(eleitos),
        "a_frente": len(a_frente),
        "ufs": len(por_uf),
        "ufs_pendentes": ufs_pendentes,
        # De onde vem "no mandato": "senado" (em exercicio, partido de hoje),
        # "tse" (eleitos ha 4 anos, partido de entao) ou nada, na Camara.
        "fonte_do_mandato": fonte_do_mandato,
        "mandato_ate": mandato_ate,
        "mandato_atualizado_em": mandato_atualizado_em,
        "observacao": observacao,
        "partidos": lista,
        "cadeiras": cadeiras,
    }


# ------------------------------------------------------------------- virada

def get_virada(db: Session, *, cargo: int, de: int, para: int) -> dict[str, Any]:
    if de >= para:
        raise DomainError("O ano de partida precisa ser anterior ao de chegada.")
    return cached_agg(
        f"virada:{cargo}:{de}:{para}", lambda: _calcular_virada(db, cargo, de, para),
    )


_VENCEDORES = text("""
    SELECT municipality_id, municipality, state, latitude, longitude,
           party_number, party_abbr, urn_name, votes
    FROM tse_winners_map
    WHERE year = :ano AND office_code = :cargo AND latitude IS NOT NULL
""")


def _calcular_virada(db: Session, cargo: int, de: int, para: int) -> dict[str, Any]:
    antes = db.execute(_VENCEDORES, {"ano": de, "cargo": cargo}).mappings().all()
    depois = db.execute(_VENCEDORES, {"ano": para, "cargo": cargo}).mappings().all()
    resultado = cruzar_vencedores(antes, depois, de, para)
    resultado.update({"cargo": cargo, "de": de, "para": para})
    log.info(
        "virada_pronta", cargo=cargo, de=de, para=para,
        municipios=len(resultado["pontos"]), viraram=resultado["viraram"],
    )
    return resultado


def cruzar_vencedores(antes, depois, de: int, para: int) -> dict[str, Any]:
    """Junta o vencedor de cada municipio nas duas eleicoes.

    So entra municipio que tem vencedor nos DOIS anos: sem um dos lados nao ha
    o que comparar, e pinta-lo como "virou" seria inventar."""
    antigo = {str(r["municipality_id"]): r for r in antes}
    pontos: list[dict[str, Any]] = []
    transicoes: dict[str, dict[str, Any]] = {}
    viraram = 0

    for r in depois:
        mid = str(r["municipality_id"])
        a = antigo.get(mid)
        if a is None:
            continue
        num_a = numero_sucessor(int(a["party_number"]), de)
        num_d = numero_sucessor(int(r["party_number"]), para)
        # O mapa materializado guarda a sigla de HOJE do numero: o DEM de 2018
        # vinha como "PRD". O rotulo e o da epoca de cada lado.
        sigla_a = sigla_no_ano(int(a["party_number"]), de, a["party_abbr"])
        sigla_d = sigla_no_ano(int(r["party_number"]), para, r["party_abbr"])
        virou = num_a != num_d
        viraram += virou
        chave = f"{num_a}>{num_d}"
        t = transicoes.setdefault(chave, {
            "chave": chave, "virou": virou, "municipios": 0,
            "de": {"numero": num_a, "sigla": ""},
            "para": {"numero": num_d, "sigla": ""},
            "_de": Counter(), "_para": Counter(),
        })
        t["municipios"] += 1
        t["_de"][sigla_a] += 1
        t["_para"][sigla_d] += 1
        pontos.append({
            "municipality_id": mid,
            "name": r["municipality"],
            "state": r["state"],
            "lat": float(r["latitude"]),
            "lng": float(r["longitude"]),
            "transicao": chave,
            "virou": virou,
            "antes": {
                "party_number": num_a, "party_abbreviation": sigla_a,
                "winner_name": a["urn_name"], "votes": int(a["votes"]),
            },
            "depois": {
                "party_number": num_d, "party_abbreviation": sigla_d,
                "winner_name": r["urn_name"], "votes": int(r["votes"]),
            },
        })

    # O grupo e por SUCESSOR, entao pode juntar mais de uma sigla antiga (PSL e
    # DEM de 2018 caem os dois no 44). Rotular pela primeira linha lida dizia
    # "DEM → PL · 5" para um grupo com 3 do DEM e 2 do PSL — e qual das duas
    # aparecia dependia da ordem em que o banco devolveu as linhas.
    def _rotulo(siglas: Counter) -> str:
        return "/".join(s for s, _ in sorted(siglas.items(), key=lambda x: (-x[1], x[0])))

    for t in transicoes.values():
        t["para"]["sigla"] = _rotulo(t.pop("_para"))
        de = _rotulo(t.pop("_de"))
        # Quem manteve aparece numa linha so, com um nome so: o de chegada. O
        # municipio que era PSL e hoje e Uniao "manteve o Uniao", nao "o PSL".
        t["de"]["sigla"] = de if t["virou"] else t["para"]["sigla"]

    return {
        "municipios": len(pontos),
        "viraram": viraram,
        "mantiveram": len(pontos) - viraram,
        # Municipios com vencedor em so UM dos anos, de qualquer dos lados
        # (carga incompleta). Fora do mapa, mas contados para o numero nao sumir
        # calado: com 2026 carregado so para o RJ, a conta antiga (so o lado
        # novo) dizia "0 de fora" enquanto 5.478 municipios estavam fora.
        "sem_comparacao": len(antes) + len(depois) - 2 * len(pontos),
        "transicoes": sorted(
            transicoes.values(), key=lambda t: (-t["municipios"], t["chave"]),
        ),
        "pontos": pontos,
    }
