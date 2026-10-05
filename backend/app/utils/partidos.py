"""Partido ao longo do tempo: o NUMERO nao e o partido.

O TSE identifica a legenda pelo numero, e `tse_parties` nasceu com uma linha por
numero. Isso erra em dois casos reais, e os dois apareceram em 2026:

  * numero reaproveitado por OUTRO partido — o 14 foi PTB ate 2022 (fundiu-se
    no PRD em 2023) e em 2026 e o MISSAO. Sem tratar, o candidato a presidente
    do Missao saia na tela como "PTB";
  * partido que trocou de nome — o 35 era PMB e passou a DEMOCRATA.

A saida e ter mais de uma linha por numero, cada uma valendo a partir de um ano
(`valid_from`; vazio = desde sempre). Quem importa pergunta "qual a linha deste
numero, com esta sigla, neste ano?" — e a resposta mora aqui, num lugar so.

ORDEM DA BUSCA em `IndiceDePartidos.achar`:
  1. linha com a MESMA sigla (o arquivo do TSE traz SG_PARTIDO em toda linha:
     e a evidencia mais forte de qual partido aquele numero era);
  2. senao, a linha que valia naquele ano;
  3. senao, nada — quem chamou cria.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tse.party import Party


def normalizar_sigla(sigla: str | None) -> str:
    """'PC do B' e 'PCDOB' sao o mesmo partido escrito de dois jeitos.

    Caixa, acento, espaco e pontuacao mudam de um arquivo do TSE para outro;
    comparar a sigla crua criaria um partido novo a cada variacao de grafia.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", sigla or "")
        if unicodedata.category(c) != "Mn"
    )
    return "".join(c for c in sem_acento.upper() if c.isalnum())


class IndiceDePartidos:
    """Todas as linhas de partido em memoria, consultaveis por numero+sigla+ano."""

    def __init__(self) -> None:
        # numero -> [(valid_from ou 0, sigla normalizada, id)]
        self._por_numero: dict[int, list[tuple[int, str, UUID]]] = {}

    @classmethod
    def do_banco(cls, db: Session) -> "IndiceDePartidos":
        indice = cls()
        for p in db.execute(select(Party)).scalars():
            indice.registrar(p.number, p.abbreviation, p.id, p.valid_from)
        return indice

    def registrar(
        self, numero: int, sigla: str | None, pid: UUID, valid_from: int | None = None,
    ) -> None:
        self._por_numero.setdefault(numero, []).append(
            (valid_from or 0, normalizar_sigla(sigla), pid)
        )

    def conhece(self, numero: int) -> bool:
        return bool(self._por_numero.get(numero))

    def achar_exato(
        self, numero: int, sigla: str | None, ano: int | None = None,
    ) -> UUID | None:
        """So a linha com esta mesma sigla — sem cair na que vale no ano.

        Um numero pode ter DUAS linhas com a mesma sigla: o 22 foi PL, virou PR
        e voltou a ser PL. Entre elas o ano decide — sem ele, o candidato do PL
        de 2002 caia na linha do PL de hoje.
        """
        alvo = normalizar_sigla(sigla)
        if not alvo:
            return None
        mesma_sigla = [l for l in self._por_numero.get(numero, []) if l[1] == alvo]
        if not mesma_sigla:
            return None
        return self._vigente(mesma_sigla, ano)

    def achar(
        self, numero: int, sigla: str | None = None, ano: int | None = None,
    ) -> UUID | None:
        linhas = self._por_numero.get(numero)
        if not linhas:
            return None
        return self.achar_exato(numero, sigla, ano) or self._vigente(linhas, ano)

    @staticmethod
    def _vigente(linhas: list[tuple[int, str, UUID]], ano: int | None) -> UUID:
        if ano is not None:
            ate_o_ano = [l for l in linhas if l[0] <= ano]
            if ate_o_ano:
                return max(ate_o_ano)[2]
            # Ano anterior a todas as linhas: a mais antiga e o melhor palpite.
            return min(linhas)[2]
        return max(linhas)[2]


def partido_atual(linhas: list[Any]) -> Any | None:
    """Entre as linhas de um mesmo numero, a que vale hoje (a de maior valid_from)."""
    if not linhas:
        return None
    return max(linhas, key=lambda p: p.valid_from or 0)


# ------------------------------------------------------------------ sucessao
#
# Para comparar duas eleicoes ("o municipio manteve o partido?", "a bancada
# cresceu?") o numero sozinho engana nos dois sentidos:
#
#   * o Podemos era 19 em 2022 e e 20 desde 2023 (herdou o numero do PSC ao
#     incorpora-lo). Comparando numero, toda cidade do Podemos teria "virado";
#   * o 14 era PTB e hoje e Missao. Comparando numero, uma cidade que saiu do
#     PTB para o Missao teria "mantido".
#
# A regra: leva-se cada partido antigo ao numero de quem o SUCEDEU legalmente
# (fusao ou incorporacao aprovada pelo TSE). Mudanca de nome nao entra — o
# numero continua o mesmo (35: PMB -> Democrata).
#
# Cada numero aparece UMA vez: a tabela guarda a ultima vez em que ele mudou de
# dono. As sucessoes se encadeiam (PRP -> Patriota -> PRD) e a funcao segue a
# corrente ate o partido de hoje.
_SUCESSOES: dict[int, tuple[int, int]] = {
    # numero antigo: (ultimo ano em que valeu, numero do sucessor)
    18: (2002, 22),  # PST -> PL (incorporado em 2003); desde 2015 o 18 e da Rede
    30: (2002, 22),  # PGT -> PL (incorporado em 2003); desde 2015 o 30 e do Novo
    41: (2002, 14),  # PSD antigo -> PTB (incorporado em 2003)
    26: (2006, 14),  # PAN -> PTB (incorporado em 2006)
    56: (2006, 22),  # PRONA -> PR, hoje PL (fusao em 2006)
    31: (2018, 19),  # PHS -> Podemos (incorporado em 2019)
    44: (2018, 51),  # PRP -> Patriota (incorporado em 2019); desde 2022 o 44 e do Uniao
    54: (2018, 65),  # PPL -> PCdoB (incorporado em 2019)
    17: (2021, 44),  # PSL -> Uniao Brasil (fusao com o DEM, 2022)
    25: (2021, 44),  # DEM -> Uniao Brasil; desde 2023 o 25 e do PRD
    14: (2024, 25),  # PTB -> PRD (fusao com o Patriota, 2023); desde 2025 o 14 e do Missao
    51: (2024, 25),  # Patriota -> PRD
    90: (2024, 77),  # PROS -> Solidariedade (incorporado em 2023)
    19: (2024, 20),  # Podemos trocou o 19 pelo 20 ao incorporar o PSC (2023)
}


# Numeros que, depois de o dono antigo sair, foram dados a OUTRO partido. Os
# demais da tabela simplesmente deixaram de existir (17, 19, 26, 31, 41, 51,
# 54, 56, 90): ninguem os usou de novo.
_REAPROVEITADOS = frozenset({14, 18, 25, 30, 44})


def numero_sucessor(numero: int, ano: int) -> int:
    """Numero, HOJE, do partido que sucedeu o `numero` da eleicao de `ano`."""
    regra = _SUCESSOES.get(numero)
    # Cada passo avanca o ano para depois da sucessao, entao a corrente sempre
    # termina — inclusive nos numeros que se revezam (25 -> 44 -> 51 -> 25).
    while regra and ano <= regra[0]:
        numero, ano = regra[1], regra[0] + 1
        regra = _SUCESSOES.get(numero)
    return numero


def trechos_da_linhagem(numero: int) -> list[tuple[int, int | None, int | None]]:
    """A historia do partido que HOJE usa `numero`, em faixas de numero e ano.

    Cada faixa e (numero, depois_de, ate): os candidatos daquele numero em
    eleicoes de ano > depois_de e <= ate (None = sem limite) pertencem a esta
    linhagem. Para o PRD (25): o proprio 25 depois de 2021 (antes era DEM), o
    14 ate 2024 (PTB) e o 51 ate 2024 (Patriota).

    E o que impede a pagina do Missao (14) de exibir a historia do PTB.
    """
    propria = _SUCESSOES.get(numero)
    if propria is None:
        proprio = (numero, None, None)
    elif numero in _REAPROVEITADOS:
        # O numero trocou de dono: so vale o que veio depois da troca.
        proprio = (numero, propria[0], None)
    else:
        # Partido extinto cujo numero ninguem reusou: a pagina dele mostra a
        # propria historia, ate o fim. (Antes devolvia "so depois do fim" e a
        # pagina do PSL, do Patriota ou do PROS vinha vazia.)
        proprio = (numero, None, propria[0])
    trechos: list[tuple[int, int | None, int | None]] = [proprio]
    for antigo, (ate, _) in sorted(_SUCESSOES.items()):
        if antigo != numero and numero_sucessor(antigo, ate) == numero:
            trechos.append((antigo, None, ate))
    return trechos


# ------------------------------------------------------- as epocas de cada numero
#
# O mesmo numero ja teve mais de um nome — e as vezes mais de um dono. A tabela
# diz, para cada numero que mudou, as epocas PASSADAS (da mais antiga para a
# mais nova) e desde quando vale a de HOJE. E a fonte unica de tres coisas:
#
#   * as linhas de `tse_parties`: uma por epoca (services/epocas_de_partido.py
#     cria as que faltam e reponta as candidaturas antigas);
#   * o rotulo de telas que guardam a sigla copiada (`sigla_no_ano`);
#   * as siglas antigas pelas quais um partido de hoje pode ser buscado.
#
# Fonte: consulta_coligacao do TSE, 2002 a 2024, eleicao ordinaria — uma sigla
# por numero e ano, e o nome que o TSE publicou. `desde` e o ano seguinte ao
# ultimo em que a epoca anterior concorreu (ou ao corte de `_SUCESSOES`, quando
# o numero mudou de dono), para sigla e linhagem nunca discordarem num ano.
#
# 14 (PTB -> MISSAO) e 35 (PMB -> DEMOCRATA) nao estao aqui: ja nasceram com
# linha por epoca (migration 067). Eleicao suplementar leva a sigla do CICLO em
# que foi registrada (a de 2019 do ciclo de 2016 sai como PMDB): quem decide a
# epoca e o ano, para um numero nunca ficar em duas linhas no mesmo ano.
@dataclass(frozen=True)
class Epoca:
    desde: int | None          # None = desde sempre (a mais antiga)
    sigla: str
    nome: str


@dataclass(frozen=True)
class EpocasDoNumero:
    passadas: tuple[Epoca, ...]
    desde_atual: int
    sigla_atual: str


def _ep(passadas: list[tuple[int | None, str, str]], desde_atual: int, atual: str) -> EpocasDoNumero:
    return EpocasDoNumero(tuple(Epoca(*p) for p in passadas), desde_atual, atual)


EPOCAS: dict[int, EpocasDoNumero] = {
    10: _ep([(None, "PRB", "Partido Republicano Brasileiro")], 2019, "REPUBLICANOS"),
    11: _ep([(None, "PPB", "Partido Progressista Brasileiro")], 2003, "PP"),
    15: _ep([(None, "PMDB", "Partido do Movimento Democrático Brasileiro")], 2017, "MDB"),
    18: _ep([(None, "PST", "Partido Social Trabalhista")], 2003, "REDE"),
    19: _ep([(None, "PTN", "Partido Trabalhista Nacional")], 2017, "PODE"),
    20: _ep([(None, "PSC", "Partido Social Cristão")], 2023, "PODE"),
    # PL, depois PR, depois PL de novo: a epoca do meio obriga a ter duas
    # linhas "PL" (a antiga, sem data, e a de hoje).
    22: _ep([(None, "PL", "Partido Liberal"),
             (2007, "PR", "Partido da República")], 2019, "PL"),
    23: _ep([(None, "PPS", "Partido Popular Socialista")], 2019, "CIDADANIA"),
    # O DEM concorreu ate 2020 e o corte da linhagem e 2021: o PRD comeca em 2022.
    25: _ep([(None, "PFL", "Partido da Frente Liberal"),
             (2007, "DEM", "Democratas")], 2022, "PRD"),
    27: _ep([(None, "PSDC", "Partido Social Democrata Cristão")], 2017, "DC"),
    30: _ep([(None, "PGT", "Partido Geral dos Trabalhadores")], 2003, "NOVO"),
    33: _ep([(None, "PMN", "Partido da Mobilização Nacional")], 2023, "MOBILIZA"),
    36: _ep([(None, "PTC", "Partido Trabalhista Cristão")], 2021, "AGIR"),
    44: _ep([(None, "PRP", "Partido Republicano Progressista")], 2019, "UNIÃO"),
    # O arquivo do TSE (regerado em 2021) traz a sigla "PATRIOTA" ja em 2014 e
    # 2016, mas com o NOME "Partido Ecológico Nacional" na mesma linha: quem
    # concorreu naqueles anos foi o PEN. O Patriota so existe desde 2018.
    51: _ep([(None, "PEN", "Partido Ecológico Nacional")], 2017, "PATRIOTA"),
    70: _ep([(None, "PT do B", "Partido Trabalhista do Brasil")], 2017, "AVANTE"),
    # Mesma legenda; o TSE passou a publicar a sigla por extenso.
    77: _ep([(None, "SD", "Solidariedade")], 2017, "SOLIDARIEDADE"),
}


def sigla_no_ano(numero: int, ano: int, sigla_do_banco: str) -> str:
    """A sigla que aquele numero usava naquele ano; a do banco, se era a mesma.

    Para quem guarda a sigla COPIADA (o mapa de vencedores materializado): a
    copia e a de hoje, e um mapa de 2018 pintava o DEM como "PRD". Depois que
    as candidaturas apontam para a linha da epoca, a resposta e a propria sigla
    do banco — a funcao so confirma.
    """
    epocas = EPOCAS.get(numero)
    if epocas is None or ano >= epocas.desde_atual:
        return sigla_do_banco
    vigente = epocas.passadas[0]
    for e in epocas.passadas:
        if e.desde is not None and e.desde <= ano:
            vigente = e
    return vigente.sigla


def siglas_anteriores(
    numero: int, linhas_por_numero: dict[int, list[Any]],
) -> list[str]:
    """Siglas antigas da LINHAGEM do partido que hoje usa `numero`, da mais
    recente para a mais antiga.

    E o que permite achar o Uniao digitando "DEM": a candidatura de 2016
    aparece como DEM, e o partido de hoje que a herdou e o 44. Sai da lista o
    que confundiria em vez de ajudar: a sigla de hoje do proprio partido (o PL
    antigo do 22 e "PL") e a sigla que hoje e de OUTRO partido (o PSD antigo,
    41, foi parar no PRD — mas "PSD" hoje e o 55).
    """
    atual = partido_atual(linhas_por_numero.get(numero, []))
    if atual is None:
        return []
    propria = normalizar_sigla(atual.abbreviation)
    # Siglas de partidos que EXISTEM hoje. Numero extinto (17, 51...) tambem
    # tem "linha atual" — a ultima que teve —, e ela e justamente sigla antiga.
    extintos = frozenset(_SUCESSOES) - _REAPROVEITADOS
    de_hoje = {
        normalizar_sigla(partido_atual(linhas).abbreviation)
        for num, linhas in linhas_por_numero.items() if linhas and num not in extintos
    }
    # sigla -> ultimo ano em que respondeu por um numero desta linhagem
    ultimo_ano: dict[str, int] = {}
    for num, depois_de, ate in trechos_da_linhagem(numero):
        linhas = sorted(linhas_por_numero.get(num, []), key=lambda l: l.valid_from or 0)
        for i, linha in enumerate(linhas):
            inicio = linha.valid_from or 0
            # A epoca vai ate a vespera da proxima linha do mesmo numero.
            fim = (linhas[i + 1].valid_from or 0) - 1 if i + 1 < len(linhas) else 9999
            if ate is not None:
                fim = min(fim, ate)
            if depois_de is not None:
                inicio = max(inicio, depois_de + 1)
            chave = normalizar_sigla(linha.abbreviation)
            if inicio > fim or chave == propria or chave in de_hoje:
                continue
            ultimo_ano[linha.abbreviation] = max(ultimo_ano.get(linha.abbreviation, 0), fim)
    return [s for s, _ in sorted(ultimo_ano.items(), key=lambda x: (-x[1], x[0]))]
