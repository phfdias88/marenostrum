"""
Voto por SECAO: a rota /tse/candidates/{id}/by-section (aba "Votos por secao"
da planilha) e a leitura do zip do TSE (app/services/votacao_secao.py).

A parte que soma no Postgres (COPY + jsonb_object_agg) nao roda no SQLite da
suite; ela se prova em producao, pela conferencia que o proprio script faz
depois de gravar (soma das secoes = voto do local = total oficial).
"""
import gzip
import zipfile
from uuid import uuid4

from app.models.tse import Candidate, Election, Municipality, Party
from app.models.tse.section_vote import TseSectionVote
from app.models.tse.voting_place import TseVotingPlace
from app.services import votacao_secao as vs


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed(db):
    """Um candidato com voto em 3 locais de 2 municipios.

    - ESCOLA A (zona 5, Alfa): 30 votos, secoes 9, 10 e 101;
    - ESCOLA B (zona 7, Alfa): 50 votos, secao 9 (mesmo numero, outra zona);
    - ESCOLA C (Beta): 20 votos, SEM detalhe por secao.
    """
    election = Election(tse_code=778, year=2026, round=1, name="Eleicao 2026")
    party = Party(number=87, abbreviation="PSEC", name="Partido Secao")
    db.add_all([election, party])
    db.flush()

    m1 = Municipality(tse_code=71001, name="Cidade Alfa", state="ZZ")
    m2 = Municipality(tse_code=71002, name="Cidade Beta", state="ZZ")
    db.add_all([m1, m2])
    db.flush()

    cand = Candidate(
        election_id=election.id, party_id=party.id, sq_candidato=710001,
        number=8700, name="CANDIDATO SECAO", urn_name="SECAO",
        office_code=6, office_name="DEPUTADO FEDERAL", state="ZZ", total_votes=100,
    )
    db.add(cand)
    db.flush()

    a = TseVotingPlace(year=2026, zone=5, local_code=1, municipality_id=m1.id,
                       name="ESCOLA A", neighborhood="CENTRO", electors_total=900)
    b = TseVotingPlace(year=2026, zone=7, local_code=1, municipality_id=m1.id,
                       name="ESCOLA B", neighborhood="PRAIA", electors_total=400)
    c = TseVotingPlace(year=2026, zone=3, local_code=4, municipality_id=m2.id,
                       name="ESCOLA C", neighborhood="VILA", electors_total=300)
    db.add_all([a, b, c])
    db.flush()
    db.add_all([
        TseSectionVote(candidate_id=cand.id, voting_place_id=a.id, votes=30,
                       sections={"10": 12, "9": 8, "101": 10}),
        TseSectionVote(candidate_id=cand.id, voting_place_id=b.id, votes=50,
                       sections={"9": 50}),
        TseSectionVote(candidate_id=cand.id, voting_place_id=c.id, votes=20),
    ])
    db.commit()
    return cand, m1, m2


# ------------------------------------------------------------------ a rota


def test_secoes_vem_dentro_do_local_em_ordem_numerica(client, tenant_a, db_session):
    _, _, token = tenant_a
    cand, _, _ = _seed(db_session)

    r = client.get(f"/api/v1/tse/candidates/{cand.id}/by-section", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()

    # Local com mais voto primeiro — a mesma ordem da aba "Votos por local".
    assert [i["place"] for i in body["items"]] == ["ESCOLA B", "ESCOLA A"]
    escola_a = body["items"][1]
    # "9" antes de "10" antes de "101": ordem de NUMERO, nao de texto.
    assert escola_a["sections"] == [[9, 8], [10, 12], [101, 10]]
    assert escola_a["zone"] == 5
    assert escola_a["neighborhood"] == "CENTRO"
    assert escola_a["municipality_name"] == "Cidade Alfa"


def test_a_soma_das_secoes_fecha_com_o_voto_do_local(client, tenant_a, db_session):
    _, _, token = tenant_a
    cand, _, _ = _seed(db_session)

    body = client.get(
        f"/api/v1/tse/candidates/{cand.id}/by-section", headers=_auth(token),
    ).json()

    for item in body["items"]:
        assert sum(v for _, v in item["sections"]) == item["votes"]
    assert body["sections_total"] == 4


def test_mesma_secao_em_zonas_diferentes_nao_se_mistura(client, tenant_a, db_session):
    """A secao 9 existe na zona 5 e na zona 7: sao duas, cada uma no seu local."""
    _, _, token = tenant_a
    cand, _, _ = _seed(db_session)

    body = client.get(
        f"/api/v1/tse/candidates/{cand.id}/by-section", headers=_auth(token),
    ).json()

    secao_9 = {i["zone"]: dict(map(tuple, i["sections"]))[9] for i in body["items"]}
    assert secao_9 == {7: 50, 5: 8}


def test_local_sem_detalhe_e_contado_e_fica_fora_da_lista(client, tenant_a, db_session):
    _, _, token = tenant_a
    cand, _, _ = _seed(db_session)

    body = client.get(
        f"/api/v1/tse/candidates/{cand.id}/by-section", headers=_auth(token),
    ).json()

    assert body["places_total"] == 3
    assert body["places_without_detail"] == 1
    assert "ESCOLA C" not in [i["place"] for i in body["items"]]


def test_filtro_de_municipio(client, tenant_a, db_session):
    _, _, token = tenant_a
    cand, _, m2 = _seed(db_session)

    body = client.get(
        f"/api/v1/tse/candidates/{cand.id}/by-section?municipality_id={m2.id}",
        headers=_auth(token),
    ).json()

    # Beta so tem a ESCOLA C, que nao tem detalhe.
    assert body == {
        "places_total": 1, "places_without_detail": 1,
        "sections_total": 0, "items": [],
    }


def test_secao_com_zero_voto_nao_vira_linha(client, tenant_a, db_session):
    _, _, token = tenant_a
    cand, m1, _ = _seed(db_session)
    extra = TseVotingPlace(year=2026, zone=5, local_code=9, municipality_id=m1.id,
                           name="ESCOLA D", electors_total=100)
    db_session.add(extra)
    db_session.flush()
    db_session.add(TseSectionVote(candidate_id=cand.id, voting_place_id=extra.id,
                                  votes=4, sections={"20": 4, "21": 0}))
    db_session.commit()

    body = client.get(
        f"/api/v1/tse/candidates/{cand.id}/by-section", headers=_auth(token),
    ).json()

    escola_d = next(i for i in body["items"] if i["place"] == "ESCOLA D")
    assert escola_d["sections"] == [[20, 4]]


def test_candidato_sem_voto_por_secao_devolve_vazio(client, tenant_a, db_session):
    _, _, token = tenant_a
    cand, _, _ = _seed(db_session)
    db_session.query(TseSectionVote).delete()
    db_session.commit()

    body = client.get(
        f"/api/v1/tse/candidates/{cand.id}/by-section", headers=_auth(token),
    ).json()

    assert body["items"] == [] and body["places_total"] == 0


def test_candidato_inexistente_da_404(client, tenant_a):
    _, _, token = tenant_a
    r = client.get(f"/api/v1/tse/candidates/{uuid4()}/by-section", headers=_auth(token))
    assert r.status_code == 404


def test_exige_login(client, tenant_a, db_session):
    cand, _, _ = _seed(db_session)
    assert client.get(f"/api/v1/tse/candidates/{cand.id}/by-section").status_code == 401


def test_fica_fora_do_cache_de_borda(client, tenant_a, db_session):
    """O nginx guarda as rotas /tse pela URL e, num acerto, nem consulta a API
    (quem pede nao e conferido). O dado bruto da exportacao nao entra nisso."""
    _, _, token = tenant_a
    cand, _, _ = _seed(db_session)

    r = client.get(f"/api/v1/tse/candidates/{cand.id}/by-section", headers=_auth(token))

    assert r.headers["cache-control"] == "private, no-store"


def test_locais_empatados_saem_na_mesma_ordem_nas_duas_abas(client, tenant_a, db_session):
    """Deputado tem centenas de locais com 1, 2, 3 votos. Sem desempate igual
    nas duas rotas, a aba por secao nao acompanha a aba por local."""
    _, _, token = tenant_a
    cand, m1, _ = _seed(db_session)
    # Inseridos FORA da ordem alfabetica, todos com 2 votos.
    for n, nome in enumerate(["ESCOLA ZULU", "ESCOLA KILO", "ESCOLA XRAY", "ESCOLA LIMA"]):
        local = TseVotingPlace(year=2026, zone=9, local_code=100 + n,
                               municipality_id=m1.id, name=nome, electors_total=50)
        db_session.add(local)
        db_session.flush()
        db_session.add(TseSectionVote(candidate_id=cand.id, voting_place_id=local.id,
                                      votes=2, sections={"1": 2}))
    db_session.commit()

    por_local = client.get(
        f"/api/v1/tse/candidates/{cand.id}/by-place", headers=_auth(token),
    ).json()
    por_secao = client.get(
        f"/api/v1/tse/candidates/{cand.id}/by-section", headers=_auth(token),
    ).json()

    com_detalhe = {i["place"] for i in por_secao["items"]}
    assert [p["place"] for p in por_local if p["place"] in com_detalhe] == [
        i["place"] for i in por_secao["items"]
    ]
    empatados = [i["place"] for i in por_secao["items"] if i["votes"] == 2]
    assert empatados == ["ESCOLA KILO", "ESCOLA LIMA", "ESCOLA XRAY", "ESCOLA ZULU"]


# ------------------------------------------------- o job antigo e o detalhe


def test_job_da_api_apaga_o_detalhe_quando_o_voto_do_local_muda():
    """O job (`_process_votacao_secao`) nao conhece a secao. Se ele troca o voto
    de um local, o detalhe gravado deixou de fechar: tem de sair, e nao ficar
    mostrando secoes que somam outro numero. So-Postgres: confere o SQL."""
    from datetime import datetime, timezone

    from sqlalchemy.dialects import postgresql

    from app.utils.tse_sync import _upsert_voto_por_local

    agora = datetime.now(timezone.utc)
    stmt = _upsert_voto_por_local(
        [{"id": uuid4(), "candidate_id": uuid4(), "voting_place_id": uuid4(),
          "votes": 3, "created_at": agora, "updated_at": agora}],
        agora,
    )
    sql = " ".join(str(stmt.compile(dialect=postgresql.dialect())).split())

    assert "ON CONFLICT (candidate_id, voting_place_id) DO UPDATE SET" in sql
    assert "votes = excluded.votes" in sql
    assert (
        "sections = CASE WHEN (tse_section_votes.votes IS DISTINCT FROM excluded.votes) "
        "THEN NULL ELSE tse_section_votes.sections END"
    ) in sql
    # O INSERT continua sem a coluna: par novo nasce sem detalhe.
    assert "sections" not in sql.split("ON CONFLICT")[0]


# ------------------------------------------------------------ leitura do zip

_CABECALHO = (
    '"DT_GERACAO";"NR_TURNO";"SG_UF";"CD_MUNICIPIO";"NR_ZONA";"NR_SECAO";'
    '"CD_CARGO";"NR_VOTAVEL";"NM_VOTAVEL";"QT_VOTOS";"NR_LOCAL_VOTACAO";'
    '"SQ_CANDIDATO";"NM_LOCAL_VOTACAO"'
)


def _linha(*, turno=1, mun=58033, zona=92, secao=316, votos=1, local=1902,
           sq=190002541678, nome="JOÃO; DA SILVA", uf="RJ"):
    # O nome leva acento (latin-1) e um ';' dentro das aspas, como no arquivo real.
    return (f'"05/10/2026";"{turno}";"{uf}";"{mun}";"{zona}";"{secao}";"7";"11111";'
            f'"{nome}";"{votos}";"{local}";"{sq}";"ESCOLA MUNICIPAL"')


def _zip(caminho, arquivos: dict[str, list[str]]):
    with zipfile.ZipFile(caminho, "w") as z:
        for nome, linhas in arquivos.items():
            z.writestr(nome, ("\r\n".join([_CABECALHO, *linhas]) + "\r\n").encode("latin-1"))
        z.writestr("leiame.pdf", b"%PDF")
    return caminho


def test_le_uma_tupla_por_linha_de_candidato(tmp_path):
    z = _zip(tmp_path / "v.zip", {"votacao_secao_2026_RJ.csv": [
        _linha(secao=316, votos=1),
        _linha(secao=317, votos=28),
    ]})

    assert list(vs.linhas_do_zip(z)) == [
        (190002541678, 58033, 92, 1902, 316, 1),
        (190002541678, 58033, 92, 1902, 317, 28),
    ]


def test_branco_nulo_e_legenda_ficam_de_fora(tmp_path):
    """Sem candidato o TSE manda SQ_CANDIDATO = -1 (branco 95, nulo 96, legenda)."""
    z = _zip(tmp_path / "v.zip", {"votacao_secao_2026_RJ.csv": [
        _linha(sq=-1, votos=40),
        _linha(sq=190002541678, votos=3),
    ]})

    assert [l[5] for l in vs.linhas_do_zip(z)] == [3]


def test_so_o_turno_pedido(tmp_path):
    """O mesmo SQ aparece nos dois turnos: somar os dois dobraria a secao."""
    z = _zip(tmp_path / "v.zip", {"votacao_secao_2026_RJ.csv": [
        _linha(turno=1, votos=10),
        _linha(turno=2, votos=99),
    ]})

    assert [l[5] for l in vs.linhas_do_zip(z)] == [10]
    assert [l[5] for l in vs.linhas_do_zip(z, turno=2)] == [99]


def test_nacional_mais_estaduais_nao_conta_em_dobro(tmp_path):
    """Em 2026 o zip traz um CSV por UF MAIS um _BRASIL com todos."""
    z = _zip(tmp_path / "v.zip", {
        "votacao_secao_2026_RJ.csv": [_linha(votos=5)],
        "votacao_secao_2026_BRASIL.csv": [_linha(votos=5)],
    })

    assert [l[5] for l in vs.linhas_do_zip(z)] == [5]


def test_arquivo_nacional_de_presidente_e_lido_uma_uf_por_vez(tmp_path):
    """O _BR.zip traz todas as UFs e o exterior (ZZ); a carga e por UF."""
    z = _zip(tmp_path / "v.zip", {"votacao_secao_2026_BR.csv": [
        _linha(uf="RJ", votos=10), _linha(uf="SP", mun=71072, votos=20),
        _linha(uf="ZZ", mun=29912, votos=3), _linha(uf="rj", votos=1),
    ]})

    assert [l[5] for l in vs.linhas_do_zip(z, uf="RJ")] == [10, 1]
    assert [l[5] for l in vs.linhas_do_zip(z, uf="ZZ")] == [3]
    assert [l[5] for l in vs.linhas_do_zip(z)] == [10, 20, 3, 1]   # sem filtro: tudo


def test_linha_sem_zona_local_ou_secao_nao_entra(tmp_path):
    z = _zip(tmp_path / "v.zip", {"votacao_secao_2026_RJ.csv": [
        _linha(zona=0), _linha(local=0), _linha(secao=0), _linha(votos=7),
    ]})

    assert [l[5] for l in vs.linhas_do_zip(z)] == [7]


def test_extrair_grava_no_formato_do_copy(tmp_path):
    z = _zip(tmp_path / "v.zip", {"votacao_secao_2026_RJ.csv": [
        _linha(secao=316, votos=1),
        _linha(secao=317, votos=28, sq=190002541068),
        _linha(sq=-1, votos=40),
    ]})
    destino = tmp_path / "secoes.tsv.gz"

    resumo = vs.extrair(z, destino)

    assert resumo == {"linhas": 2, "votos": 29, "candidatos": 2}
    with gzip.open(destino, "rt", encoding="ascii") as f:
        assert f.read() == (
            "190002541678\t58033\t92\t1902\t316\t1\n"
            "190002541068\t58033\t92\t1902\t317\t28\n"
        )


# ------------------------------------------- locais que o cadastro nao tem


def test_locais_do_resultado_tem_o_nome_onde_a_secao_votou(tmp_path):
    """Secao remanejada: o resultado diz em que predio ela votou, e e esse
    nome (e nao o do cadastro) que o local novo leva."""
    z = _zip(tmp_path / "v.zip", {"votacao_secao_2026_RJ.csv": [
        _linha(local=1902, secao=316),
        _linha(local=1902, secao=317),               # mesmo local: uma entrada so
        _linha(local=2283, zona=6, secao=146),
    ]})

    locais = vs.locais_do_zip(z)

    assert set(locais) == {(58033, 92, 1902), (58033, 6, 2283)}
    assert locais[(58033, 92, 1902)][0] == "ESCOLA MUNICIPAL"


def test_locais_do_arquivo_de_presidente_saem_por_uf(tmp_path):
    z = _zip(tmp_path / "v.zip", {"votacao_secao_2026_BR.csv": [
        _linha(uf="RJ", local=10), _linha(uf="ZZ", mun=29912, local=1015),
    ]})

    assert set(vs.locais_do_zip(z, uf="ZZ")) == {(29912, 92, 1015)}


def test_extrair_locais_grava_csv_que_o_copy_le(tmp_path):
    """Nome de local tem virgula, aspas e acento; o CSV precisa sobreviver."""
    import csv as _csv

    cab = _CABECALHO + ';"DS_LOCAL_VOTACAO_ENDERECO"'
    nome = 'E.M. "PROF. JOÃO", ANEXO' + "X" * 300
    linha = _linha(nome="ALGUEM").replace('"ESCOLA MUNICIPAL"', '"' + nome.replace('"', '""') + '"')
    caminho = tmp_path / "v.zip"
    with zipfile.ZipFile(caminho, "w") as zz:
        zz.writestr("votacao_secao_2026_RJ.csv",
                    (cab + "\r\n" + linha + ';"RUA A, 10"\r\n').encode("latin-1"))
    destino = tmp_path / "locais.csv.gz"

    assert vs.extrair_locais(caminho, destino) == 1
    with gzip.open(destino, "rt", encoding="utf-8", newline="") as f:
        [mun, zona, local, lido, endereco] = next(_csv.reader(f))
    assert (mun, zona, local) == ("58033", "92", "1902")
    assert lido == nome[:200]                         # limite da coluna name
    assert endereco == "RUA A, 10"


# ------------------------------------------- exportacao em fluxo e sem cache


def test_por_local_vazio_e_uma_lista_json_valida(client, tenant_a, db_session):
    """As rotas de exportacao saem em fluxo; sem linha nenhuma o corpo ainda
    tem de ser JSON valido (a planilha faz r.json())."""
    _, _, token = tenant_a
    cand, _, _ = _seed(db_session)
    db_session.query(TseSectionVote).delete()
    db_session.commit()

    r = client.get(f"/api/v1/tse/candidates/{cand.id}/by-place", headers=_auth(token))

    assert r.status_code == 200 and r.json() == []


def test_bairros_de_candidato_do_pais_inteiro_nao_vao_para_o_cache(
    client, tenant_a, db_session, monkeypatch,
):
    """Presidente: 52 mil bairros. Ficar no cache em memoria prenderia dezenas
    de MB por horas numa API de 768 MB; a resposta continua a mesma."""
    from app.controllers import tse as rotas
    from app.utils import agg_cache

    _, _, token = tenant_a
    cand, _, _ = _seed(db_session)
    url = f"/api/v1/tse/candidates/{cand.id}/by-neighborhood"

    pequeno = client.get(url, headers=_auth(token)).json()
    assert any(k.startswith("by_nb:") for k in agg_cache._store)   # 3 bairros: cacheia

    agg_cache.clear_agg_cache()
    monkeypatch.setattr(rotas, "_BAIRROS_SEM_CACHE", 2)
    grande = client.get(url, headers=_auth(token)).json()

    assert not any(k.startswith("by_nb:") for k in agg_cache._store)
    assert grande == pequeno
    assert {i["neighborhood"] for i in grande["items"]} == {"CENTRO", "PRAIA", "VILA"}


def test_lista_em_lotes_tem_virgula_so_entre_itens(monkeypatch):
    """A saida em lotes junta itens com virgula, inclusive na emenda entre um
    lote e o outro — e nada sobra no comeco ou no fim."""
    import json

    from app.controllers import tse as rotas

    monkeypatch.setattr(rotas, "_LOTE_DO_FLUXO", 2)
    for n in (0, 1, 2, 3, 5):
        itens = (json.dumps({"i": i}).encode() for i in range(n))
        corpo = b"[" + b"".join(rotas._lista_json_em_lotes(itens)) + b"]"
        assert json.loads(corpo) == [{"i": i} for i in range(n)]
