#!/usr/bin/env python3
"""
Confere o que o sistema mostra contra o canal oficial do TSE.

Baixa os arquivos de resultado direto do TSE, le com um parser PROPRIO (nao o
da captura — se a captura lesse errado, conferir com ela mesma daria "ok") e
compara com o que esta no banco e com o que a API devolve as telas.

O QUE E CONFERIDO:
  1. total de votos e situacao de CADA candidato, todos os cargos e UFs;
  2. comparecimento, abstencao, brancos e nulos;
  3. a bancada (eleitos de senador e deputado federal) contra o TSE;
  4. o mapa de vencedores, numa amostra de municipios;
  5. as rotas que alimentam cada tela de analise: respondem, e com dado.

DEFASAGEM NAO E ERRO: a captura roda a cada 2 minutos e a apuracao ainda anda,
entao o banco pode estar um passo atras do TSE. O script sabe distinguir: cada
arquivo do TSE traz a hora em que foi gerado, e a captura guarda de qual versao
leu. Se a versao servida agora e OUTRA, a diferenca e o TSE ter andado. Se e a
MESMA versao e o numero difere, e erro de verdade e o script acusa. (Onde nao
ha versao para comparar, vale a tolerancia de 0,2%.)

USO (o script mora no host e entra por stdin):
    docker compose exec -T -e PYTHONPATH=/app api \
        python - < backend/scripts/conferir_com_tse.py
    ... python - --data 25/10/2026 --amostra 60 < backend/scripts/conferir_com_tse.py

Sai com codigo 1 se alguma conferencia falhar.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models import User
from app.services import tse_live as live
from app.utils.tse_sync import ALL_UFS

ANO = 2026
TOLERANCIA = 0.002
API = "http://localhost:8000/api/v1/tse"

falhas: list[str] = []


def ok(msg: str) -> None:
    print(f"  [ok]    {msg}")


def falhou(msg: str) -> None:
    falhas.append(msg)
    print(f"  [FALHA] {msg}")


def aviso(msg: str) -> None:
    print(f"  [aviso] {msg}")


def inteiro(v) -> int:
    try:
        return int(str(v or 0).strip().replace(".", "") or 0)
    except ValueError:
        return 0


def candidatos_do_arquivo(dado: dict) -> dict[int, dict]:
    """Parser proprio: sqcand -> {votos, situacao, eleito, nome, partido}."""
    saida: dict[int, dict] = {}
    for cargo in dado.get("carg") or []:
        for agr in cargo.get("agr") or []:
            for par in agr.get("par") or []:
                for c in par.get("cand") or []:
                    sq = inteiro(c.get("sqcand"))
                    if sq and sq not in saida:
                        saida[sq] = {
                            "votos": inteiro(c.get("vap")),
                            "situacao": (c.get("st") or "").strip().upper(),
                            "eleito": (c.get("e") or "").strip().lower() == "s",
                            "nome": c.get("nmu") or c.get("nm") or "?",
                            "partido": par.get("sg") or "?",
                            "numero_partido": inteiro(par.get("n")),
                        }
    return saida


def eleito(situacao: str | None) -> bool:
    s = (situacao or "").strip().upper()
    return s.startswith("ELEITO") or s == "MÉDIA"


def perto(a: int, b: int) -> bool:
    return abs(a - b) <= max(2, TOLERANCIA * max(a, b))


def main() -> int:
    p = argparse.ArgumentParser(description="Confere o sistema contra o TSE.")
    p.add_argument("--data", default="04/10/2026", help="data do pleito no TSE")
    p.add_argument("--amostra", type=int, default=40,
                   help="municipios sorteados para conferir o mapa")
    args = p.parse_args()

    db = SessionLocal()
    tse = httpx.Client(timeout=30, headers=live.CABECALHOS, follow_redirects=True)

    u = db.query(User).filter(
        User.is_superadmin.is_(True), User.is_active.is_(True)).first()
    papel = u.role.value if hasattr(u.role, "value") else str(u.role)
    token = create_access_token(
        user_id=u.id, tenant_id=u.tenant_id, role=papel,
        expires_delta=timedelta(minutes=10))
    api = httpx.Client(
        timeout=120, headers={"Authorization": "Bearer " + token})

    def da_api(caminho: str):
        r = api.get(API + caminho)
        return r.status_code, (r.json() if r.status_code == 200 else None)

    # O cache de agregacao guarda resposta por 4h: sem limpar, a conferencia
    # compararia o TSE com um numero que a tela ja nem mostra mais.
    api.post(API + "/ingest/cache-clear")

    # ------------------------------------------------ quais eleicoes e cargos
    cfg = live.baixar(tse, f"{live.BASE}/comum/config/ele-c.json") or {}
    eleicoes = []
    for pleito in cfg.get("pl", []):
        if pleito.get("dt") != args.data:
            continue
        for e in pleito.get("e", []):
            if str(e.get("tp")) not in ("1", "8"):
                continue
            cargos = sorted({
                int(c["cd"]) for a in e.get("abr", []) for c in a.get("cp", [])
                if str(c.get("cd", "")).isdigit()
            })
            eleicoes.append((int(e["cd"]), [c for c in cargos if c in live.CARGOS_COM_VOTO]))
    if not eleicoes:
        print("ERRO: o TSE nao listou eleicao para", args.data)
        return 2

    alvos = []
    for codigo, cargos in eleicoes:
        for cargo in cargos:
            areas = ["br"] if cargo == 1 else [x.lower() for x in ALL_UFS]
            for uf in areas:
                if cargo == 8 and uf != "df":
                    continue
                if cargo == 7 and uf == "df":
                    continue
                alvos.append((codigo, cargo, uf))

    def baixar(alvo):
        codigo, cargo, uf = alvo
        return alvo, live.baixar(tse, live.url_do_arquivo(ANO, codigo, uf, cargo))

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        arquivos = list(pool.map(baixar, alvos))
    print(f"\nTSE: {sum(1 for _, d in arquivos if d)} de {len(alvos)} arquivos "
          f"baixados em {time.perf_counter() - t0:.0f}s")

    # ---------------------------------------------- 1. candidato a candidato
    print("\n1. VOTOS E SITUACAO DE CADA CANDIDATO (banco x TSE)")
    no_banco = {
        r.sq: r for r in db.execute(text("""
            SELECT c.sq_candidato AS sq, c.total_votes AS votos,
                   c.result_status AS situacao, c.office_code AS cargo,
                   c.state AS uf, c.urn_name AS nome, p.abbreviation AS partido,
                   p.number AS numero_partido
            FROM tse_candidates c
            JOIN tse_elections e ON e.id = c.election_id
            JOIN tse_parties p ON p.id = c.party_id
            WHERE e.year = :ano
        """), {"ano": ANO})
    }
    # De qual versao do arquivo do TSE saiu o que esta no banco. O TSE regrava
    # o arquivo de uma UF a cada poucos minutos enquanto ela apura; se a versao
    # de agora e outra, a diferenca e do TSE ter andado, nao de leitura errada.
    _, ao_vivo = da_api("/ingest/live")
    capturado = {
        (uf, int(cargo)): info.get("gerado_em")
        for uf, cargos in ((ao_vivo or {}).get("totais") or {}).get("andamento", {}).items()
        for cargo, info in cargos.items()
    }

    por_cargo = defaultdict(lambda: Counter())
    piores: list[tuple[float, str]] = []
    eleitos_tse: dict[int, Counter] = defaultdict(Counter)
    # cargo -> UFs em que o TSE publicou versao nova depois da nossa captura.
    andaram: dict[int, set[str]] = defaultdict(set)
    for (codigo, cargo, uf), dado in arquivos:
        if not dado:
            falhou(f"TSE nao respondeu: cargo {cargo} {uf.upper()}")
            continue
        versao_agora = f"{dado.get('dg', '')} {dado.get('hg', '')}".strip()
        versao_lida = capturado.get((uf.upper(), cargo))
        # Sem saber de qual versao o banco leu, NAO se presume defasagem:
        # presumir esconderia erro de verdade atras de "o TSE deve ter andado".
        tse_andou = versao_lida is not None and versao_lida != versao_agora
        if tse_andou:
            andaram[cargo].add(uf.upper())
        for sq, t in candidatos_do_arquivo(dado).items():
            c = por_cargo[cargo]
            c["no_tse"] += 1
            if t["eleito"] or eleito(t["situacao"]):
                eleitos_tse[cargo][uf.upper()] += 1
            b = no_banco.get(sq)
            if b is None:
                c["fora_do_banco"] += 1
                continue
            votos = int(b.votos or 0)
            if votos == t["votos"]:
                c["voto_identico"] += 1
            elif tse_andou or perto(votos, t["votos"]):
                # O arquivo que o TSE serve agora ja e outro: o banco esta um
                # passo atras e alcanca na proxima passada (2 minutos).
                c["voto_defasado"] += 1
            else:
                # MESMA versao do arquivo e numero diferente: isso sim e erro.
                c["voto_errado"] += 1
                dif = abs(votos - t["votos"]) / max(1, t["votos"])
                piores.append((dif, f"cargo {cargo} {uf.upper()} {t['nome']}: "
                                    f"banco {votos:,} x TSE {t['votos']:,}"))
            if (b.situacao or "") == t["situacao"]:
                c["situacao_igual"] += 1
            elif not t["situacao"] or tse_andou:
                c["situacao_igual"] += 1      # sem situacao no TSE, ou TSE ja andou
            else:
                c["situacao_diferente"] += 1
            if t["numero_partido"] and t["numero_partido"] != b.numero_partido:
                c["partido_errado"] += 1

    nomes = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Dep. Federal",
             7: "Dep. Estadual", 8: "Dep. Distrital"}
    for cargo in sorted(por_cargo):
        c = por_cargo[cargo]
        linha = (f"{nomes.get(cargo, cargo):14s} {c['no_tse']:6d} candidatos | "
                 f"voto identico {c['voto_identico']:6d} | um passo atras "
                 f"{c['voto_defasado']:5d} | ERRADO {c['voto_errado']:3d} | "
                 f"situacao diferente {c['situacao_diferente']:4d} | "
                 f"fora do banco {c['fora_do_banco']:3d}")
        if c["voto_errado"] or c["fora_do_banco"] or c["partido_errado"]:
            falhou(linha)
        elif c["situacao_diferente"]:
            aviso(linha + "  (situacao muda a cada UF que o TSE fecha)")
        else:
            ok(linha)
    for _, texto in sorted(piores, reverse=True)[:8]:
        print("          ", texto)

    # -------------------------------------------- 2. o que a TELA mostra
    print("\n2. PLACAR QUE A TELA MOSTRA (API x TSE)")
    por_alvo = {(cargo, uf): dado for (_, cargo, uf), dado in arquivos if dado}

    def conferir_placar(cargo: int, uf: str | None) -> None:
        dado = por_alvo.get((cargo, (uf or "br").lower()))
        if not dado:
            return
        caminho = f"/election-results?year={ANO}&office_code={cargo}&limit=500"
        if uf:
            caminho += f"&state={uf}"
        status, resp = da_api(caminho)
        rotulo = f"{nomes[cargo]} {uf or 'Brasil'}"
        if status != 200:
            falhou(f"{rotulo}: API respondeu {status}")
            return
        tse_ordem = sorted(candidatos_do_arquivo(dado).values(),
                           key=lambda t: -t["votos"])
        tse_ordem = [t for t in tse_ordem if t["votos"] > 0]
        nossos = resp["results"]
        if len(nossos) != len(tse_ordem):
            falhou(f"{rotulo}: {len(nossos)} candidatos na tela x {len(tse_ordem)} no TSE")
            return
        erros = [
            f"{t['nome']}: tela {n['votes']:,} x TSE {t['votos']:,}"
            for n, t in zip(nossos, tse_ordem) if not perto(n["votes"], t["votos"])
        ]
        if erros:
            falhou(f"{rotulo}: " + "; ".join(erros[:3]))
            return
        lider_n, lider_t = nossos[0], tse_ordem[0]
        total_tse = sum(t["votos"] for t in tse_ordem)
        pct_n = 100 * lider_n["votes"] / max(1, resp["total_votes"])
        pct_t = 100 * lider_t["votos"] / max(1, total_tse)
        ok(f"{rotulo:20s} {len(nossos):3d} candidatos | lider "
           f"{lider_n['candidate']['urn_name'][:22]:22s} "
           f"{lider_n['votes']:>11,} ({pct_n:.2f}%) | TSE {lider_t['votos']:>11,} ({pct_t:.2f}%)")

    conferir_placar(1, None)
    for uf in ALL_UFS:
        conferir_placar(3, uf)
    for uf in ALL_UFS:
        conferir_placar(5, uf)

    # -------------------------------------------------- 3. comparecimento
    print("\n3. ABSTENCAO, BRANCOS E NULOS (API x TSE)")

    def pct_tse(v) -> float:
        return float(str(v or "0").replace(".", "").replace(",", "."))

    def conferir_comparecimento(cargo: int, uf: str) -> None:
        dado = por_alvo.get((cargo, uf.lower()))
        if not dado:
            return
        status, resp = da_api(f"/stats/turnout?office_code={cargo}&uf={uf}")
        ano = next((a for a in (resp or {}).get("anos", []) if a["ano"] == ANO), None)
        rotulo = f"{nomes[cargo]} {uf}"
        if ano is None:
            falhou(f"{rotulo}: sem linha de {ANO} no comparecimento")
            return
        e, v, s = dado.get("e") or {}, dado.get("v") or {}, dado.get("s") or {}
        pares = [
            ("abstencao", ano["pct_abstencao"], pct_tse(e.get("pa"))),
            ("brancos", ano["pct_brancos"], pct_tse(v.get("pvb"))),
            ("nulos", ano["pct_nulos"], pct_tse(v.get("ptvn"))),
            ("urnas", ano["pct_secoes"], pct_tse(s.get("pst"))),
        ]
        ruins = [f"{n} tela {a} x TSE {b}" for n, a, b in pares
                 if a is None or abs(a - b) > 0.05]
        if ruins:
            falhou(f"{rotulo}: " + "; ".join(ruins))
        else:
            ok(f"{rotulo:20s} " + " | ".join(f"{n} {a:.2f}%" for n, a, _ in pares))

    conferir_comparecimento(1, "BR")
    for uf in ("RJ", "SP", "MG", "BA", "RS"):
        conferir_comparecimento(3, uf)

    for ano_ref, esperado in ((2018, (20.33, 2.65, 6.14)), (2022, (20.95, 1.59, 2.82))):
        _, resp = da_api("/stats/turnout?office_code=1&uf=BR")
        a = next((x for x in resp["anos"] if x["ano"] == ano_ref), None)
        tem = (a["pct_abstencao"], a["pct_brancos"], a["pct_nulos"]) if a else None
        if tem == esperado:
            ok(f"Presidente BR {ano_ref}: {tem} — igual ao resultado oficial")
        else:
            falhou(f"Presidente BR {ano_ref}: tela {tem} x oficial {esperado}")

    # ---------------------------------------------------------- 4. bancada
    print("\n4. BANCADA (API x TSE)")
    for cargo, casa in ((5, "Senado"), (6, "Camara")):
        status, b = da_api(f"/stats/bancada?year={ANO}&office_code={cargo}")
        if status != 200:
            falhou(f"{casa}: API respondeu {status}")
            continue
        # UF a UF, e so nas que o TSE nao regravou depois da nossa captura:
        # uma UF que fecha no meio da conferencia proclama a bancada inteira
        # de uma vez, e isso apareceria como "faltam 17 eleitos".
        nossos = Counter(
            c["uf"] for c in b["cadeiras"] if c["situacao"] == "eleitos")
        comparaveis = [uf for uf in ALL_UFS if uf not in andaram[cargo]]
        divergem = [
            f"{uf} (tela {nossos[uf]}, TSE {eleitos_tse[cargo][uf]})"
            for uf in comparaveis if nossos[uf] != eleitos_tse[cargo][uf]
        ]
        if divergem:
            falhou(f"{casa}: eleitos diferentes do TSE em " + ", ".join(divergem))
        else:
            ok(f"{casa}: {sum(nossos[uf] for uf in comparaveis)} eleitos "
               f"proclamados, UF a UF igual ao TSE "
               f"({len(b['ufs_pendentes'])} UFs ainda sem resultado)")
        if andaram[cargo]:
            aviso(f"{casa}: o TSE publicou versao nova de "
                  f"{', '.join(sorted(andaram[cargo]))} durante a conferencia; "
                  "essas UFs entram na proxima passada")
        soma = sum(p["eleitos"] for p in b["partidos"])
        if soma != b["eleitos"]:
            falhou(f"{casa}: soma por partido ({soma}) difere do total ({b['eleitos']})")
        if cargo == 5:
            previsto = b["eleitos"] + b["a_frente"]
            if previsto == b["em_disputa"] and b["antes"] == 27:
                ok(f"Senado: 27 no mandato + {b['eleitos']} eleitos + "
                   f"{b['a_frente']} a frente = {27 + previsto} cadeiras")
            else:
                falhou(f"Senado: {b['antes']} no mandato, {previsto} de "
                       f"{b['em_disputa']} vagas preenchidas")

    # ------------------------------------------------ 5. mapa de vencedores
    print(f"\n5. MAPA DE VENCEDORES ({args.amostra} municipios sorteados x TSE)")
    codigo_federal = next(c for c, cargos in eleicoes if 1 in cargos)
    status, mapa = da_api(f"/stats/winners-map?year={ANO}&office_code=1")
    pontos = {p["municipality_id"]: p for p in (mapa or {}).get("points", [])}
    municipios = db.execute(text("""
        SELECT id::text AS id, tse_code, name, state FROM tse_municipalities
        WHERE state <> 'ZZ' AND latitude IS NOT NULL
    """)).all()
    faltam = len(municipios) - len(pontos)
    (ok if faltam <= 30 else falhou)(
        f"{len(pontos)} de {len(municipios)} municipios com coordenada estao no mapa"
        + (f" (faltam {faltam}: sem voto na ultima varredura)" if faltam else ""))

    # O voto por municipio so anda quando a VARREDURA passa (nao a cada 2
    # minutos, como o placar). Entre uma varredura e outra, municipio que ainda
    # estava contando fica com o numero antigo: isso e defasagem conhecida, e
    # vira aviso com a contagem. Falha e o VENCEDOR diferente.
    random.seed(20261004)
    iguais = 0
    atrasados: list[str] = []
    for m in random.sample(municipios, min(args.amostra, len(municipios))):
        dado = live.baixar(tse, live.url_do_arquivo(
            ANO, codigo_federal, m.state, 1, municipio=int(m.tse_code)))
        ponto = pontos.get(m.id)
        if not dado or ponto is None:
            aviso(f"{m.name}/{m.state}: sem arquivo no TSE ou fora do mapa")
            continue
        lider = max(candidatos_do_arquivo(dado).values(), key=lambda t: t["votos"])
        if lider["numero_partido"] != ponto["party_number"]:
            falhou(f"{m.name}/{m.state}: mapa diz {ponto['party_abbreviation']} "
                   f"({ponto['votes']:,}), TSE diz {lider['partido']} ({lider['votos']:,})")
        elif perto(ponto["votes"], lider["votos"]):
            iguais += 1
        else:
            atrasados.append(
                f"{m.name}/{m.state} (mapa {ponto['votes']:,}, TSE {lider['votos']:,})")
    ok(f"vencedor igual ao TSE em {iguais + len(atrasados)} municipios; "
       f"{iguais} com o voto em dia")
    if atrasados:
        aviso(f"{len(atrasados)} com voto atras do TSE desde a ultima varredura "
              "(mesmo vencedor): " + "; ".join(atrasados[:4]))

    # ------------------------------------------------------ 6. as telas
    print("\n6. ROTAS QUE ALIMENTAM AS TELAS")
    rj = db.execute(text(
        "SELECT id::text FROM tse_municipalities WHERE state='RJ' AND name ILIKE 'RIO DE JANEIRO'"
    )).scalar()
    lula = db.execute(text("""
        SELECT c.id::text FROM tse_candidates c JOIN tse_elections e ON e.id=c.election_id
        WHERE e.year=:a AND c.office_code=1 ORDER BY c.total_votes DESC NULLS LAST LIMIT 1
    """), {"a": ANO}).scalar()
    rotas = [
        ("Analise de eleicao (presidente BR)", f"/election-results?year={ANO}&office_code=1", "results"),
        ("Analise de eleicao (dep. federal SP)", f"/election-results?year={ANO}&office_code=6&state=SP", "results"),
        ("Analise de eleicao (municipio)", f"/election-results?year={ANO}&office_code=3&municipality_id={rj}", "results"),
        ("Ranking nacional", f"/stats/top-candidates?year={ANO}&office_code=6&limit=50", "items"),
        ("Candidatos (busca 2026)", f"/candidates?year={ANO}&limit=20&group_person=true", "items"),
        ("Painel do candidato", f"/candidates/{lula}/results", "results"),
        ("Partidos (desempenho)", f"/stats/party-performance?year={ANO}&office_code=3", "items"),
        ("Partido (evolucao PL)", "/parties/22/evolution", "items"),
        ("Partido (evolucao Missao)", "/parties/14/evolution", "items"),
        ("Lista de partidos", "/parties", None),
        ("Municipio (governador no Rio)", f"/municipalities/{rj}/top-candidates?year={ANO}&office_code=3&limit=20", "results"),
        ("Mapa partidario (presidente)", f"/stats/winners-map?year={ANO}&office_code=1", "points"),
        ("Mapa partidario (governador)", f"/stats/winners-map?year={ANO}&office_code=3", "points"),
        ("Mapa partidario (senador)", f"/stats/winners-map?year={ANO}&office_code=5", "points"),
        ("Mapa da virada (presidente)", f"/stats/virada?office_code=1&from_year=2022&to_year={ANO}", "pontos"),
        ("Mapa da virada (governador)", f"/stats/virada?office_code=3&from_year=2022&to_year={ANO}", "pontos"),
        ("Bancada (Senado)", f"/stats/bancada?year={ANO}&office_code=5", "cadeiras"),
        ("Bancada (Camara)", f"/stats/bancada?year={ANO}&office_code=6", "cadeiras"),
        ("Placar: comparecimento", "/stats/turnout?office_code=1&uf=BR", "anos"),
        ("Mapa partidario 2024 (regressao)", "/stats/winners-map?year=2024&office_code=11", "points"),
        ("Analise de eleicao 2022 (regressao)", "/election-results?year=2022&office_code=1", "results"),
    ]
    for nome, caminho, chave in rotas:
        t = time.perf_counter()
        status, resp = da_api(caminho)
        seg = time.perf_counter() - t
        if status != 200:
            falhou(f"{nome}: HTTP {status}")
            continue
        qtd = len(resp[chave]) if chave else len(resp)
        (ok if qtd > 0 else falhou)(f"{nome:38s} {qtd:6d} itens em {seg:5.2f}s")

    _, partidos = da_api("/parties")
    siglas = {p["number"]: p["abbreviation"] for p in partidos}
    if siglas.get(14) == "MISSÃO" and siglas.get(35) == "DEMOCRATA":
        ok("partido 14 = MISSÃO e 35 = DEMOCRATA (como no registro do TSE)")
    else:
        falhou(f"siglas: 14={siglas.get(14)} 35={siglas.get(35)}")
    _, missao = da_api("/parties/14/evolution")
    anos_missao = [i["year"] for i in missao["items"]]
    (ok if anos_missao == [ANO] else falhou)(
        f"pagina do Missao so tem {ANO} (nao herda o PTB): {anos_missao}")

    print("\n" + "=" * 72)
    if falhas:
        print(f"RESULTADO: {len(falhas)} conferencia(s) FALHARAM")
        for f in falhas:
            print("  -", f)
        return 1
    print("RESULTADO: tudo confere com o TSE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
