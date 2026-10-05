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

    def achar_exato(self, numero: int, sigla: str | None) -> UUID | None:
        """So a linha com esta mesma sigla — sem cair na que vale no ano."""
        alvo = normalizar_sigla(sigla)
        if not alvo:
            return None
        mesma_sigla = [l for l in self._por_numero.get(numero, []) if l[1] == alvo]
        return max(mesma_sigla)[2] if mesma_sigla else None

    def achar(
        self, numero: int, sigla: str | None = None, ano: int | None = None,
    ) -> UUID | None:
        linhas = self._por_numero.get(numero)
        if not linhas:
            return None
        return self.achar_exato(numero, sigla) or self._vigente(linhas, ano)

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
