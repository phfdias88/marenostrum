#!/usr/bin/env python3
"""
Confere as telas de analise UMA CONTRA A OUTRA.

O conferir_com_tse.py responde "o banco bate com o TSE?". Este responde a
pergunta seguinte: as telas batem ENTRE SI? O mesmo numero aparece em mais de
uma tela (o eleito do placar e o da analise de eleicao; a bancada e o
desempenho por partido; o vencedor do mapa e o mais votado da pagina do
municipio), cada uma por uma rota e uma consulta diferentes. Se duas
discordam, uma delas esta errada — e quem olha as duas percebe.

Passa por todas as telas de /dashboard/analises pelas MESMAS rotas que elas
chamam, com os parametros com que abrem.

USO (mora no host e entra por stdin):
    docker compose exec -T -e PYTHONPATH=/app api \
        python - < backend/scripts/conferir_analises.py

Sai com codigo 1 se alguma conferencia falhar. [aviso] nao e falha: e dado que
ainda nao existe (ex.: voto por secao de 2026, que o TSE so publica depois).
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from datetime import timedelta

import httpx
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models import User
from app.services import epocas_de_partido
from app.utils.partidos import EPOCAS, sigla_no_ano

ANO = 2026
BASE = "http://localhost:8000/api/v1"
LENTO = 8.0          # segundos: acima disso a tela parece travada

falhas: list[str] = []
avisos: list[str] = []


def ok(msg: str) -> None:
    print(f"  [ok]    {msg}")


def falhou(msg: str) -> None:
    falhas.append(msg)
    print(f"  [FALHA] {msg}")


def aviso(msg: str) -> None:
    avisos.append(msg)
    print(f"  [aviso] {msg}")


def confere(condicao: bool, certo: str, errado: str) -> None:
    ok(certo) if condicao else falhou(errado)


def main() -> int:
    db = SessionLocal()
    u = db.query(User).filter(
        User.is_superadmin.is_(True), User.is_active.is_(True)).first()
    papel = u.role.value if hasattr(u.role, "value") else str(u.role)
    token = create_access_token(
        user_id=u.id, tenant_id=u.tenant_id, role=papel,
        expires_delta=timedelta(minutes=20))
    api = httpx.Client(timeout=180, headers={"Authorization": "Bearer " + token})

    def pega(caminho: str, tela: str):
        """GET na rota da tela; acusa erro e lentidao. Devolve o JSON ou None."""
        t = time.perf_counter()
        try:
            r = api.get(BASE + caminho)
        except httpx.HTTPError as exc:
            falhou(f"{tela}: {caminho} nao respondeu ({type(exc).__name__})")
            return None
        seg = time.perf_counter() - t
        if r.status_code != 200:
            falhou(f"{tela}: {caminho} devolveu HTTP {r.status_code}")
            return None
        if seg > LENTO:
            aviso(f"{tela}: {caminho} levou {seg:.1f}s")
        return r.json()

    def um(sql: str, **p):
        return db.execute(text(sql), p).first()

    # ------------------------------------------------------------ referencias
    rio = um("SELECT id FROM tse_municipalities WHERE tse_code = 60011")
    sp = um("SELECT id FROM tse_municipalities WHERE tse_code = 71072")
    pres = db.execute(text("""
        SELECT c.id, c.urn_name, c.total_votes FROM tse_candidates c
        JOIN tse_elections e ON e.id = c.election_id
        WHERE e.year = :a AND c.office_code = 1 AND c.total_votes IS NOT NULL
        ORDER BY c.total_votes DESC LIMIT 2"""), {"a": ANO}).all()
    if not (rio and sp and len(pres) == 2):
        print("ERRO: faltam referencias (Rio, Sao Paulo ou presidenciaveis de 2026)")
        return 2
    rio, sp = str(rio[0]), str(sp[0])
    lider, segundo = pres

    # ============================================================== 1. PLACAR
    print("\n1. PLACAR x ANALISE DE ELEICAO x PAINEL DO CANDIDATO")
    eleicao = pega(f"/tse/election-results?year={ANO}&office_code=1", "Analise de eleicao")
    comparecimento = pega("/tse/stats/turnout?office_code=1&uf=BR", "Placar")
    if eleicao:
        topo = eleicao["results"][0]
        confere(
            topo["votes"] == lider.total_votes
            and topo["candidate"]["id"] == str(lider.id),
            f"lider para presidente e o mesmo do banco: {lider.urn_name} "
            f"({lider.total_votes:,} votos)".replace(",", "."),
            f"analise de eleicao mostra {topo['candidate']['urn_name']} com "
            f"{topo['votes']}; o banco tem {lider.urn_name} com {lider.total_votes}",
        )
        soma = sum(r["votes"] for r in eleicao["results"])
        confere(
            eleicao["total_votes"] == soma,
            "o total de votos do cargo e a soma dos candidatos listados",
            f"total_votes={eleicao['total_votes']} mas a lista soma {soma}",
        )
    for c in (lider, segundo):
        painel = pega(f"/tse/candidates/{c.id}/results", "Painel do candidato")
        if painel:
            # A tela mostra o total OFICIAL (candidate.total_votes); o
            # `total_votes` da raiz da resposta e a soma do detalhe por
            # municipio, conferida logo abaixo.
            oficial = painel["candidate"]["total_votes"]
            confere(
                oficial == c.total_votes,
                f"painel de {c.urn_name}: mesmo total do placar",
                f"painel de {c.urn_name} mostra {oficial}, placar mostra {c.total_votes}",
            )
            por_cidade = sum(r["votes"] for r in painel["results"])
            falta = c.total_votes - por_cidade
            # O detalhe por municipio pode ficar um fio abaixo do total (secao
            # totalizada depois da varredura); acima de 0,05% e buraco de carga.
            if falta == 0:
                ok(f"painel de {c.urn_name}: voto por municipio fecha com o total")
            elif 0 < falta <= c.total_votes * 0.0005:
                aviso(f"painel de {c.urn_name}: faltam {falta} votos no detalhe "
                      f"por municipio ({100 * falta / c.total_votes:.4f}%)")
            else:
                falhou(f"painel de {c.urn_name}: detalhe por municipio soma "
                       f"{por_cidade}, total {c.total_votes}")
    if comparecimento:
        atual = next((a for a in comparecimento["anos"] if a["ano"] == ANO), None)
        anos = [a["ano"] for a in comparecimento["anos"]]
        confere(
            atual is not None and len(anos) >= 3,
            f"comparecimento de presidente traz {anos}",
            f"comparecimento sem {ANO} ou sem historico: {anos}",
        )
        if atual and eleicao:
            # Validos do TSE = soma dos candidatos, menos os anulados sub judice.
            dif = soma - atual["validos"] - atual.get("anulados", 0)
            confere(
                dif == 0,
                "votos validos do placar = soma dos candidatos da analise de eleicao",
                f"placar tem {atual['validos']} validos (+{atual.get('anulados', 0)} "
                f"anulados); candidatos somam {soma} (diferenca {dif})",
            )

    # =========================================================== 2. BANCADA
    print("\n2. BANCADA x PARTIDOS x RANKING")
    for cargo, casa, cadeiras in ((5, "Senado", 54), (6, "Camara", 513)):
        b = pega(f"/tse/stats/bancada?year={ANO}&office_code={cargo}", f"Bancada ({casa})")
        pp = pega(f"/tse/stats/party-performance?year={ANO}&office_code={cargo}",
                  f"Partidos ({casa})")
        if not (b and pp):
            continue
        eleitos_pp = sum(i["elected_count"] for i in pp["items"])
        confere(
            eleitos_pp == b["eleitos"],
            f"{casa}: {b['eleitos']} eleitos na bancada e no desempenho por partido",
            f"{casa}: bancada diz {b['eleitos']} eleitos, partidos somam {eleitos_pp}",
        )
        por_partido_b = Counter()
        for p in b["partidos"]:
            por_partido_b[p["numero"]] += p["eleitos"]
        por_partido_pp = Counter()
        for i in pp["items"]:
            por_partido_pp[i["lineage_number"] or i["party"]["number"]] += i["elected_count"]
        difere = {n for n in set(por_partido_b) | set(por_partido_pp)
                  if por_partido_b[n] != por_partido_pp[n]}
        confere(
            not difere,
            f"{casa}: eleitos por partido iguais nas duas telas",
            f"{casa}: eleitos por partido diferem nos numeros {sorted(difere)}",
        )
        confere(
            b["em_disputa"] == cadeiras,
            f"{casa}: {cadeiras} cadeiras em disputa",
            f"{casa}: em_disputa={b['em_disputa']}, esperado {cadeiras}",
        )
        confere(
            sum(p["antes"] for p in b["partidos"]) == b["antes"]
            and len(b["cadeiras"]) == b["antes"] + b["eleitos"] + b["a_frente"],
            f"{casa}: linhas e cadeiras somam o cabecalho "
            f"({b['antes']} + {b['eleitos']} + {b['a_frente']})",
            f"{casa}: a soma das linhas nao bate com o cabecalho",
        )
        if b["ufs_pendentes"]:
            aviso(f"{casa}: TSE ainda nao proclamou em {', '.join(b['ufs_pendentes'])}")
        if cargo == 5:
            no_senado = um(
                "SELECT count(*) FROM senate_sitting_members "
                "WHERE term_end BETWEEN :i AND :f",
                i=f"{ANO + 5}-01-01", f=f"{ANO + 5}-12-31")[0]
            confere(
                b["fonte_do_mandato"] == "senado" and b["antes"] == no_senado == 27,
                f"Senado: 'no mandato' sao os {no_senado} em exercicio ate "
                f"{b['mandato_ate']}, pela filiacao de hoje (lista de "
                f"{b['mandato_atualizado_em']})",
                f"Senado: fonte={b['fonte_do_mandato']}, antes={b['antes']}, "
                f"lista do Senado tem {no_senado}",
            )
    ranking = pega(f"/tse/stats/top-candidates?year={ANO}&office_code=6&limit=50", "Ranking")
    if ranking:
        maior = um("""
            SELECT max(c.total_votes) FROM tse_candidates c
            JOIN tse_elections e ON e.id = c.election_id
            WHERE e.year = :a AND c.office_code = 6""", a=ANO)[0]
        votos = [i["total_votes"] for i in ranking["items"]]
        confere(
            votos and votos[0] == maior and votos == sorted(votos, reverse=True),
            f"ranking de deputado federal: 50 em ordem, o primeiro com {maior:,}".replace(",", "."),
            f"ranking fora de ordem ou topo ({votos[:1]}) diferente do banco ({maior})",
        )

    # ============================================================== 3. MAPAS
    print("\n3. MAPA PARTIDARIO x VIRADA x PAGINA DO MUNICIPIO")
    for cargo, nome, de in ((1, "presidente", 2022), (3, "governador", 2022),
                            (5, "senador", 2018)):
        mapa = pega(f"/tse/stats/winners-map?year={ANO}&office_code={cargo}",
                    f"Mapa ({nome})")
        virada = pega(f"/tse/stats/virada?office_code={cargo}&from_year={de}&to_year={ANO}",
                      f"Virada ({nome})")
        if not (mapa and virada):
            continue
        pontos = {p["municipality_id"]: p for p in mapa["points"]}
        confere(
            len(pontos) >= 5570,
            f"mapa de {nome}: {len(pontos)} municipios pintados",
            f"mapa de {nome}: so {len(pontos)} municipios",
        )
        confere(
            virada["viraram"] + virada["mantiveram"] == virada["municipios"]
            == len(virada["pontos"]),
            f"virada de {nome} ({de}->{ANO}): {virada['viraram']} viraram + "
            f"{virada['mantiveram']} mantiveram = {virada['municipios']}",
            f"virada de {nome}: a conta nao fecha",
        )
        # O vencedor de 2026 e o mesmo nas duas telas, municipio a municipio.
        troca = [
            v["name"] for v in virada["pontos"]
            if v["municipality_id"] in pontos
            and pontos[v["municipality_id"]]["winner_name"] != v["depois"]["winner_name"]
        ]
        confere(
            not troca,
            f"virada e mapa de {nome}: mesmo vencedor em {ANO} em todo municipio",
            f"virada e mapa de {nome} discordam em {len(troca)} municipios "
            f"(ex.: {troca[:3]})",
        )
        if virada["sem_comparacao"]:
            aviso(f"virada de {nome}: {virada['sem_comparacao']} municipio(s) sem "
                  f"resultado em um dos anos (fora do mapa)")
        if cargo == 3:
            local = pega(
                f"/tse/municipalities/{rio}/top-candidates?year={ANO}&office_code=3&limit=5",
                "Pagina do municipio")
            if local and rio in pontos:
                confere(
                    local["results"][0]["candidate"]["urn_name"]
                    == pontos[rio]["winner_name"]
                    and local["results"][0]["votes"] == pontos[rio]["votes"],
                    f"Rio de Janeiro: mais votado da pagina do municipio = vencedor "
                    f"do mapa ({pontos[rio]['winner_name']})",
                    "Rio de Janeiro: pagina do municipio e mapa discordam do vencedor",
                )

    # ======================================================= 4. DEMAIS TELAS
    print("\n4. DEMAIS TELAS: RESPONDEM E TRAZEM 2026")
    eleicoes = pega("/tse/elections", "Eleicoes")
    if eleicoes:
        de_2026 = [e for e in eleicoes if e["year"] == ANO]
        confere(bool(de_2026), f"lista de eleicoes traz {len(de_2026)} de {ANO}",
                f"lista de eleicoes sem {ANO}")
        for e in de_2026:
            st = pega(f"/tse/elections/{e['id']}/stats", "Eleicoes (sumario)")
            lista = pega(f"/tse/candidates?election_id={e['id']}&limit=20", "Eleicoes (candidatos)")
            if st and lista:
                # O sumario ja foi coluna gravada na primeira visita: comparar
                # com o banco, e nao so "e maior que zero", pega numero congelado.
                n, v = um("SELECT count(*), coalesce(sum(total_votes), 0) "
                          "FROM tse_candidates WHERE election_id = :id", id=e["id"])
                confere(
                    st["candidates_count"] == n > 0 and st["total_votes"] == int(v) > 0
                    and lista["items"],
                    f"eleicao {e['tse_code']}: {st['candidates_count']} candidatos, "
                    f"{st['total_votes']:,} votos, iguais ao banco".replace(",", "."),
                    f"eleicao {e['tse_code']}: sumario mostra {st['candidates_count']} "
                    f"candidatos e {st['total_votes']} votos; o banco tem {n} e {int(v)}",
                )

    partidos = pega("/tse/parties", "Partidos")
    if partidos:
        numeros = [p["number"] for p in partidos]
        sigla = {p["number"]: p["abbreviation"] for p in partidos}
        confere(
            len(numeros) == len(set(numeros)),
            f"lista de partidos: {len(numeros)} cartoes, um por numero",
            "lista de partidos repete numero",
        )
        confere(
            sigla.get(14) == "MISSÃO" and sigla.get(35) == "DEMOCRATA",
            "14 aparece como MISSÃO e 35 como DEMOCRATA",
            f"sigla trocada: 14={sigla.get(14)} 35={sigla.get(35)}",
        )
    evo = pega("/tse/parties/22/evolution", "Partido (PL)")
    if evo:
        confere(
            any(i["year"] == ANO for i in evo["items"]),
            f"evolucao do PL chega a {ANO}", f"evolucao do PL sem {ANO}",
        )

    busca = pega("/tse/municipalities?search=rio%20de%20janeiro&limit=5", "Municipios (busca)")
    if busca:
        confere(bool(busca["items"]), "busca de municipio responde", "busca de municipio vazia")
    linha = pega(f"/tse/municipalities/{rio}/timeline", "Municipio (linha do tempo)")
    if linha:
        anos = sorted({i["year"] for i in linha["items"]})
        confere(ANO in anos, f"linha do tempo do Rio: {anos}",
                f"linha do tempo do Rio sem {ANO}: {anos}")
    pega(f"/tse/municipalities/{rio}/electorate", "Municipio (eleitorado)")
    comparar = pega(
        f"/tse/municipalities/{sp}/top-candidates?office_code=11&year=2024&limit=5",
        "Comparar municipios")
    if comparar:
        confere(len(comparar["results"]) == 5,
                "comparar municipios: 5 mais votados para prefeito de Sao Paulo em 2024",
                "comparar municipios: lista de prefeito 2024 incompleta")
    projecao = pega(
        f"/tse/municipalities/{rio}/top-candidates?year=2022&office_code=6&limit=50",
        "Projecao")
    if projecao:
        confere(bool(projecao["results"]), "projecao: base de 2022 do Rio responde",
                "projecao: base de 2022 vazia")

    for c in (lider,):
        for rota, tela in (("trajectory", "trajetoria"), ("path-to-victory", "caminho da vitoria"),
                           ("opportunities", "oportunidades"),
                           ("electorate-profile", "perfil do eleitorado")):
            pega(f"/tse/candidates/{c.id}/{rota}", f"Candidato ({tela})")
    achou = pega("/tse/candidates?search=LULA&limit=20&group_person=true", "Candidato (busca)")
    if achou:
        confere(bool(achou["items"]), "busca de candidato responde", "busca de candidato vazia")
    pega("/monitored", "Adversarios")

    # Voto por secao (zona e bairro) de 2026: o TSE so publica semanas depois.
    zonas = pega(f"/tse/municipalities/{rio}/zones?year=2024&office_code=11", "Zona (2024)")
    if zonas:
        confere(bool(zonas.get("zones")), "zona eleitoral: prefeito 2024 no Rio por zona",
                "zona eleitoral de 2024 vazia")
    locais = pega(f"/tse/voting-places/map?municipality_id={rio}&year=2024", "Bairros (locais 2024)")
    if locais is not None:
        confere(len(locais) > 1000, f"bairros: {len(locais)} locais de votacao do Rio em 2024",
                f"bairros: so {len(locais)} locais de votacao do Rio em 2024")
    zonas_2026 = pega(
        f"/tse/municipalities/{rio}/zones?year={ANO}&office_code=3", f"Zona ({ANO})")
    if zonas_2026 is not None and not zonas_2026.get("zones"):
        aviso(f"voto por secao de {ANO} ainda nao existe: as telas de BAIRRO e ZONA "
              f"continuam em 2024 ate o TSE publicar o arquivo (votacao_secao_{ANO})")

    # ================================================== 5. PARTIDO POR EPOCA
    print("\n5. SIGLA DA EPOCA NOS ANOS ANTIGOS")
    for problema in epocas_de_partido.conferir(db):
        falhou(f"linhas de partido: {problema}")
    pendentes = epocas_de_partido.planejar(db)
    confere(
        not pendentes,
        "toda candidatura antiga esta na linha da sua epoca",
        f"{sum(m.quantidade for m in pendentes)} candidaturas ainda na linha de hoje "
        f"(rodar scripts/epocas_de_partido.py --aplicar)",
    )
    for ano, cargo in ((2016, 11), (2018, 6), (2022, 6)):
        pp = pega(f"/tse/stats/party-performance?year={ano}&office_code={cargo}",
                  f"Partidos ({ano})")
        if not pp:
            continue
        numeros = [i["party"]["number"] for i in pp["items"]]
        repetidos = sorted({n for n in numeros if numeros.count(n) > 1})
        confere(
            not repetidos,
            f"ranking de {ano}: uma linha por numero de partido ({len(numeros)})",
            f"ranking de {ano}: numero repetido em duas linhas {repetidos}",
        )
        errados = [
            (i["party"]["number"], i["party"]["abbreviation"])
            for i in pp["items"]
            if i["party"]["number"] in EPOCAS
            and i["party"]["abbreviation"]
            != sigla_no_ano(i["party"]["number"], ano, i["party"]["abbreviation"])
        ]
        confere(
            not errados,
            f"ranking de {ano}: sigla da epoca em todos os partidos que mudaram de nome",
            f"ranking de {ano}: sigla de hoje em ano antigo {errados}",
        )
    if partidos:
        uniao = next((p for p in partidos if p["number"] == 44), None)
        confere(
            bool(uniao) and "DEM" in (uniao.get("former_abbreviations") or []),
            "busca: o Uniao (44) e encontrado pela sigla antiga DEM",
            "busca: /parties nao traz DEM entre as siglas antigas do 44",
        )

    # ---------------------------------------------------------------- resumo
    print("\n" + "=" * 62)
    print(f"{len(falhas)} falha(s), {len(avisos)} aviso(s)")
    for f in falhas:
        print("  FALHA:", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
