#!/usr/bin/env python3
"""
Sigla da EPOCA nas candidaturas antigas.

Cria em tse_parties as linhas das epocas passadas (PFL, DEM, PMDB, PSC, PR...)
e leva cada candidatura antiga para a linha da epoca dela. Depois disto o
candidato do DEM de 2016 aparece como "DEM", e nao como "PRD", em toda tela.
As regras e o porque estao em app/services/epocas_de_partido.py.

SEM ARGUMENTO SO MOSTRA O PLANO — nada e gravado:
    docker compose exec -T -e PYTHONPATH=/app api \
        python - < backend/scripts/epocas_de_partido.py

PARA VALER (destacado do terminal: leva minutos, e se a sessao cair o veredito
nao pode ir junto — a saida vai para um arquivo no volume):
    nohup docker compose exec -T -e PYTHONPATH=/app api python - --aplicar \
        < backend/scripts/epocas_de_partido.py > ~/epocas-de-partido.log 2>&1 &

    1. tira o retrato (ano, numero) -> candidaturas, votos, eleitos, e o GRAVA
       ao lado do manifesto na primeira rodada;
    2. data a linha de hoje e cria as linhas das epocas (grava o MANIFESTO);
    3. reponta as candidaturas, um grupo (linha, ano) por vez, em fatias com
       commit e pausa do tamanho do trabalho — o banco fica metade do tempo
       livre para quem esta usando o sistema;
    4. atualiza a sigla copiada no mapa de vencedores;
    5. tira o retrato de novo e COMPARA com o da PRIMEIRA rodada: tem de ser
       identico, e nenhum (ano, numero) pode ficar em duas linhas.

Pode ser interrompido e rodado de novo: o plano e recalculado e continua de
onde parou, e a prova continua valendo porque o retrato "antes" esta em disco.

DEPOIS (o script nao alcanca estes caches):
    reiniciar a API ou POST /api/v1/tse/ingest/cache-clear?everything=true
    docker compose exec -T nginx sh -c 'rm -rf /var/cache/nginx/tse/*'
    docker compose exec -T api sh -c 'rm -f /var/marenostrum/pdf_cache/*.pdf'

PARA VOLTAR ATRAS (usa o manifesto gravado no passo 2):
    ... python - --desfazer < backend/scripts/epocas_de_partido.py

NAO rodar junto com sync do TSE, backup ou varredura da apuracao.
Sai com codigo 1 se a conferencia final acusar diferenca.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import engine
from app.services import epocas_de_partido as epocas
from app.utils import apuracao
from app.utils.tse_sync import CACHE_DIR

MANIFESTO = CACHE_DIR / "epocas_de_partido_manifesto.json"

DEPOIS = (
    "Falta (o script nao alcanca estes caches): limpar o cache da API "
    "(reiniciar, ou POST /tse/ingest/cache-clear?everything=true), o do nginx "
    "(rm -rf /var/cache/nginx/tse/*) e o dos dossies "
    "(rm -f /var/marenostrum/pdf_cache/*.pdf)."
)


def _abrir() -> tuple:
    """Sessao presa a UMA conexao durante a rodada inteira.

    A sessao comum devolve a conexao ao pool a cada commit, e o pool a troca
    por outra depois de 30 minutos (pool_recycle): os SET abaixo sumiriam no
    meio de uma rodada longa, e o retrato final morreria no statement_timeout
    do servidor — depois de todas as escritas, sem conferencia.
    """
    conexao = engine.connect()
    return conexao, Session(bind=conexao, autoflush=False, expire_on_commit=False)


def _sem_limite_de_tempo(db) -> None:
    # A fatia e pequena, mas o retrato le a tabela inteira. O SET vale para a
    # CONEXAO, e so dura a rodada porque a sessao fica presa a ela (_abrir).
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET statement_timeout = 0"))
        db.execute(text("SET lock_timeout = '10s'"))
        db.commit()


def _pausa(fator: float, minimo: float):
    """Descansa o tempo que a fatia levou (vezes `fator`): quanto mais o banco
    demora, mais folga ele ganha."""
    def pausar(duracao: float) -> None:
        time.sleep(max(minimo, duracao * fator))
    return pausar


def _indice_novo_existe(db) -> bool:
    if db.bind.dialect.name != "postgresql":
        return True
    definicao = db.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_tse_parties_number_sigla'"
    )).scalar() or ""
    return "COALESCE" in definicao.upper()


def _mostrar_plano(plano: list[epocas.Movimento]) -> None:
    if not plano:
        print("  nada a repontar: toda candidatura ja esta na linha da sua epoca")
        return
    por_destino = Counter()
    por_ano = Counter()
    for m in plano:
        por_destino[(m.numero, m.sigla_origem, m.sigla_destino)] += m.quantidade
        por_ano[m.ano] += m.quantidade
    for (numero, de, para), n in sorted(por_destino.items()):
        print(f"  {numero:>2}  {de:>14} -> {para:<10} {n:>8,}".replace(",", "."))
    print(f"  por ano: {dict(sorted(por_ano.items()))}")
    print(f"  TOTAL: {sum(m.quantidade for m in plano):,} candidaturas em "
          f"{len(plano)} grupos".replace(",", "."))


def _arquivo_do_retrato(manifesto: Path) -> Path:
    return manifesto.with_name(manifesto.stem + "_retrato_antes.json")


def _retrato_de_referencia(db, manifesto: Path) -> tuple[dict, bool]:
    """O retrato (ano, numero) de ANTES da primeira rodada, e se ele e completo.

    Tirado de novo a cada execucao, o "antes" de uma rodada retomada ja seria o
    banco meio migrado: a comparacao final diria TUDO CONFERE sem ter olhado o
    que a primeira rodada fez. Por isso vai para o disco uma vez so — na unica
    hora em que o banco ainda esta intocado: quando nao ha retrato NEM manifesto.
    """
    arquivo = _arquivo_do_retrato(manifesto)
    if arquivo.exists():
        bruto = json.loads(arquivo.read_text(encoding="utf-8"))
        return {tuple(int(x) for x in k.split(",")): tuple(v) for k, v in bruto.items()}, True
    agora = epocas.por_ano_e_numero(epocas.retrato(db))
    db.commit()
    if manifesto.exists():
        # Rodada anterior deixou manifesto e nao deixou retrato: nao ha como
        # provar o que ela moveu. A conferencia cobre so esta rodada, e avisa.
        return agora, False
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(
        json.dumps({f"{a},{n}": v for (a, n), v in agora.items()}), encoding="utf-8")
    return agora, True


def _comparar(antes: dict, depois: dict) -> list[str]:
    difs = []
    for chave in sorted(set(antes) | set(depois)):
        x, y = antes.get(chave), depois.get(chave)
        # No ano em apuracao a captura segue gravando voto e situacao entre um
        # retrato e o outro (basta o TSE proclamar uma UF): ali so a QUANTIDADE
        # de candidaturas tem de bater. O reponte nem toca nesse ano.
        if chave[0] == apuracao.ANO_EM_APURACAO and x and y:
            x, y = x[:1], y[:1]
        if x != y:
            difs.append(f"({chave[0]}, numero {chave[1]}): antes {antes.get(chave)}, "
                        f"depois {depois.get(chave)}")
    return difs


def _ensaio(db) -> int:
    # Cria as linhas numa transacao que NAO e gravada, so para o plano enxergar
    # para onde cada candidatura iria.
    print("ENSAIO — nada sera gravado.", flush=True)
    foto = epocas.retrato(db)
    print(f"candidaturas no banco: {sum(l.candidaturas for l in foto):,}".replace(",", "."))
    # Divisao que JA existe (e nao e deste script) tem de aparecer agora, e nao
    # como "diferenca" no fim de uma rodada perfeita.
    for (ano, numero), siglas in sorted(epocas.anos_divididos(foto).items()):
        print(f"  AVISO: ({ano}, numero {numero}) ja esta em mais de uma linha: {siglas}")
    feito = epocas.garantir_epocas(db)
    print(f"linhas de epoca a criar ({len(feito['criadas'])}): "
          f"{[(c['numero'], c['sigla'], c['desde']) for c in feito['criadas']]}")
    print(f"linhas de hoje a datar ({len(feito['datadas'])}): "
          f"{[(d['numero'], d['sigla'], d['depois']) for d in feito['datadas']]}")
    for aviso in feito["ignorados"]:
        print("  AVISO:", aviso)
    print("candidaturas a repontar:")
    _mostrar_plano(epocas.planejar(db))
    for problema in epocas.conferir(db):
        print("  AVISO (estrutura):", problema)
    db.rollback()
    return 0


def _aplicar(db, args, pausar) -> int:
    inicio = time.monotonic()
    print("1. retrato antes (le a tabela inteira; pode levar um minuto)...", flush=True)
    antes, prova_completa = _retrato_de_referencia(db, args.manifesto)
    print(f"   {sum(v[0] for v in antes.values()):,} candidaturas".replace(",", ".")
          + ("" if prova_completa else
             "  [ATENCAO: ha manifesto de rodada anterior sem retrato gravado]"))

    print("2. linhas das epocas...", flush=True)
    feito = epocas.garantir_epocas(db)
    # O manifesto vai para o disco ANTES do commit e acumula entre rodadas:
    # se a segunda rodada nao cria nada, o da primeira nao pode ser perdido.
    anterior = (json.loads(args.manifesto.read_text(encoding="utf-8"))
                if args.manifesto.exists() else {"criadas": [], "datadas": []})
    manifesto = {
        "criadas": anterior["criadas"] + feito["criadas"],
        "datadas": anterior["datadas"] + feito["datadas"],
    }
    args.manifesto.parent.mkdir(parents=True, exist_ok=True)
    args.manifesto.write_text(json.dumps(manifesto, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    db.commit()
    print(f"   {len(feito['criadas'])} criadas, {len(feito['datadas'])} datadas "
          f"(manifesto em {args.manifesto})")
    for aviso in feito["ignorados"]:
        print("   AVISO:", aviso)

    print("3. repontando...", flush=True)
    plano = epocas.planejar(db)
    db.commit()
    _mostrar_plano(plano)
    total = sum(m.quantidade for m in plano)
    feitas = 0
    for m in plano:
        t = time.monotonic()
        n = epocas.repontar(db, m, fatia=args.fatia, pausa=pausar)
        feitas += n
        print(f"   {m.numero:>2} {m.ano} {m.sigla_origem:>14} -> {m.sigla_destino:<10} "
              f"{n:>7} em {time.monotonic() - t:5.1f}s  [{feitas}/{total}]", flush=True)

    print("4. sigla copiada no mapa de vencedores...", flush=True)
    if db.bind.dialect.name == "postgresql":
        n = db.execute(text("""
            UPDATE tse_winners_map w SET party_abbr = p.abbreviation, updated_at = now()
            FROM tse_candidates c JOIN tse_parties p ON p.id = c.party_id
            WHERE c.id = w.candidate_id AND w.party_abbr IS DISTINCT FROM p.abbreviation
        """)).rowcount
        db.commit()
        print(f"   {n} municipios-ano com a sigla trocada")
        db.execute(text("ANALYZE tse_candidates"))
        db.commit()

    print("5. conferencia...", flush=True)
    foto = epocas.retrato(db)
    db.commit()
    falhas = _comparar(antes, epocas.por_ano_e_numero(foto))
    falhas += [f"(ano {a}, numero {n}) em mais de uma linha: {siglas}"
               for (a, n), siglas in sorted(epocas.anos_divididos(foto).items())]
    falhas += epocas.conferir(db)
    falhas += [f"sobrou no plano: {m.numero}/{m.ano} {m.quantidade}"
               for m in epocas.planejar(db)]
    print(f"   {feitas:,} candidaturas repontadas nesta rodada, em "
          f"{time.monotonic() - inicio:.0f}s".replace(",", "."))
    if falhas:
        print(f"\n{len(falhas)} DIFERENCA(S):")
        for f in falhas[:40]:
            print("  ", f)
        print("\n" + DEPOIS)
        return 1
    if prova_completa:
        print("\nTUDO CONFERE: mesmo numero de candidaturas, votos e eleitos por "
              "(ano, numero) que ANTES da primeira rodada; nenhum numero em duas "
              "linhas no mesmo ano; nada sobrou no plano.")
        # A prova foi feita: o retrato deixa de ser a referencia. Guardado com
        # outro nome, nao vira "antes" de uma rodada futura — depois de uma
        # carga nova do TSE ele acusaria diferenca que nao e do reponte.
        arquivo = _arquivo_do_retrato(args.manifesto)
        if arquivo.exists():
            arquivo.replace(arquivo.with_suffix(".conferido.json"))
    else:
        print("\nESTRUTURA CONFERE (nenhum numero em duas linhas no mesmo ano, nada "
              "sobrou no plano), mas a comparacao por (ano, numero) cobre SO esta "
              "rodada: a anterior nao deixou retrato gravado.")
    print(DEPOIS)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Sigla da epoca nas candidaturas antigas.")
    p.add_argument("--aplicar", action="store_true", help="grava (sem isto, so mostra o plano)")
    p.add_argument("--desfazer", action="store_true", help="volta ao estado do manifesto")
    p.add_argument("--fatia", type=int, default=4000, help="linhas por UPDATE")
    p.add_argument("--folga", type=float, default=1.0,
                   help="pausa = tempo da fatia x folga (1.0 = banco metade do tempo livre)")
    p.add_argument("--manifesto", type=Path, default=MANIFESTO)
    args = p.parse_args()

    conexao, db = _abrir()
    try:
        _sem_limite_de_tempo(db)
        pausar = _pausa(args.folga, 0.3)

        if args.desfazer:
            if not args.manifesto.exists():
                print(f"ERRO: nao ha manifesto em {args.manifesto}", file=sys.stderr)
                return 2
            manifesto = json.loads(args.manifesto.read_text(encoding="utf-8"))
            print(f"desfazendo: {len(manifesto.get('criadas', []))} linhas criadas, "
                  f"{len(manifesto.get('datadas', []))} datas", flush=True)
            print(epocas.desfazer(db, manifesto, fatia=args.fatia, pausa=pausar))
            args.manifesto.rename(args.manifesto.with_suffix(".desfeito.json"))
            # O banco voltou ao estado de antes: o retrato gravado deixa de ser
            # referencia (uma nova rodada tira outro).
            _arquivo_do_retrato(args.manifesto).unlink(missing_ok=True)
            print(DEPOIS)
            return 0

        if not _indice_novo_existe(db):
            print("ERRO: o indice unico ainda e o antigo (migration 072 nao rodou). "
                  "A segunda linha 'PL' do 22 seria recusada.", file=sys.stderr)
            return 2

        return _aplicar(db, args, pausar) if args.aplicar else _ensaio(db)
    finally:
        db.close()
        conexao.close()


if __name__ == "__main__":
    sys.exit(main())
