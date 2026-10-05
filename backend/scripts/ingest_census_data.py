#!/usr/bin/env python3
"""
ETL do Censo IBGE — carga dos Agregados por Setores Censitarios, ate o pais inteiro.

O QUE ESTE SCRIPT SUBSTITUI: hoje existe um script por tema
(ingest_census_demografia, _indicators, _saneamento...), cada um repetindo
download, parsing latin-1, tratamento de sigilo e UPDATE em lote — e cada um
com a URL do IBGE cravada no codigo. Aqui os temas viram DADO (o catalogo
DATASETS) e o motor e um so: incluir um agregado novo passa a ser acrescentar
uma entrada no dicionario.

DECISOES QUE IMPORTAM:

- Chunks, sempre. O agregado "basico" do Brasil tem ~452 mil linhas e os
  tematicos passam de 140 MB compactados. `pandas.read_csv(chunksize=...)`
  mantem a memoria constante — a API roda com 768 MB e 0,4 vCPU nesta VPS,
  entao ler o arquivo inteiro na memoria nao e uma opcao.

- Nome de arquivo resolvido em tempo de execucao. O IBGE republica os
  agregados com a data no nome (`..._basico_BR_20260520.zip`), e os scripts
  atuais tem essa data cravada — quando o instituto republica, o script quebra
  com 404. Aqui o catalogo guarda o PREFIXO e o script acha o arquivo listando
  o diretorio, preferindo a versao mais recente.

- Idempotente por construcao. Todo lote vai num INSERT ... ON CONFLICT
  (cd_setor) DO UPDATE. Rodar duas vezes nao duplica; rodar de novo depois de
  uma queda no meio so reescreve o que ja tinha entrado.

- Uma linha ruim nao derruba o arquivo. O parsing de cada linha e protegido, e
  um lote que falhe e reprocessado linha a linha pra isolar o culpado. Sigilo
  do IBGE ("X", "..", vazio) vira NULL, nao erro.

- Geometria NAO vem por aqui. Este ETL carrega indicadores; a malha — que e o
  que pesa em disco — continua vindo por shapefile, so nas UFs em uso. Por isso
  a migration 061 tornou `census_geo.geometry` nullable.

USO (padrao da casa: scripts/ nao vai pra imagem, entao copia + PYTHONPATH):

    docker compose cp backend/scripts/ingest_census_data.py api:/tmp/
    docker compose exec -T -e PYTHONPATH=/app api \\
        python /tmp/ingest_census_data.py --dataset basico --all-brasil

    # so algumas UFs, a partir de arquivo ja baixado, sem gravar:
    docker compose exec -T -e PYTHONPATH=/app api \\
        python /tmp/ingest_census_data.py --dataset demografia \\
        --uf 33 --uf 35 --file /tmp/demografia.zip --dry-run

    docker compose exec -T -e PYTHONPATH=/app api \\
        python /tmp/ingest_census_data.py --list-datasets

ORDEM: rode `basico` primeiro — e o unico agregado que traz o cadastro do setor
(municipio, distrito, bairro) e, portanto, o unico que pode criar linha. Os
tematicos so atualizam setor existente.

DEPOIS DA CARGA: rodar `scripts/refresh_census_muni_agg.py`. Os agregados por
municipio sao materializados (migration 058) e nao se atualizam sozinhos.

CUIDADO EM PRODUCAO: a carga concorre com a API pelo unico vCPU — rodar fora
do horario comercial. Em ago/2026 o disco estava em 75%; o `basico` nacional
acrescenta ~150 MB (sem geometria).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from typing import Iterator

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

# ---------------------------------------------------------------------------
# Log estruturado
# ---------------------------------------------------------------------------
# Mesmo structlog que a API usa: a saida do ETL fica pesquisavel por campo
# (evento + chave=valor), em vez de frase solta. ConsoleRenderer porque isto e
# lido a olho nu no terminal — troque por JSONRenderer se for pra um coletor.
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
)
log = structlog.get_logger("census.etl")

FTP_BASE = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/"
)


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Dataset:
    """Um agregado do IBGE e o de-para pras colunas de `census_geo`.

    columns: {coluna_no_banco: expressao}. A expressao soma variaveis do CSV:
        "V0001"              -> a variavel
        "V00309+V00310"      -> soma de duas
        "V00644..V00656"     -> soma da faixa (inclusive)
      Faixas existem porque o IBGE publica por grupo de idade: "alfabetizados
      de 15+" e a soma de 13 variaveis, uma por faixa etaria.

    prefix:  inicio do nome do arquivo. O sufixo de data (_20260520) e
             resolvido em tempo de execucao — ver `_resolver_url`.
    creates: True so no `basico`, o unico com o cadastro do setor. Nos demais,
             setor desconhecido e ignorado; sem isso um tematico criaria linha
             orfa, sem municipio nem nome.
    """

    name: str
    prefix: str
    columns: dict[str, str]
    kind: str = "int"
    creates: bool = False
    description: str = ""


def _faixa(ini: int, fim: int, largura: int = 5) -> str:
    """Monta "V00644..V00656" a partir dos numeros."""
    return f"V{ini:0{largura}d}..V{fim:0{largura}d}"


DATASETS: dict[str, Dataset] = {
    "basico": Dataset(
        name="basico",
        prefix="Agregados_por_setores_basico_BR",
        columns={"populacao": "V0001", "domicilios": "V0002"},
        creates=True,
        description="Populacao e domicilios + cadastro do setor",
    ),
    "demografia": Dataset(
        name="demografia",
        prefix="Agregados_por_setores_demografia_BR",
        columns={
            "sexo_masculino": "V01007",
            "sexo_feminino": "V01008",
            "idade_0_4": "V01031",
            "idade_5_9": "V01032",
            "idade_10_14": "V01033",
            "idade_15_19": "V01034",
            "idade_20_24": "V01035",
            "idade_25_29": "V01036",
            "idade_30_39": "V01037",
            "idade_40_49": "V01038",
            "idade_50_59": "V01039",
            "idade_60_69": "V01040",
            "idade_70_mais": "V01041",
        },
        description="Sexo e faixa etaria",
    ),
    "cor_ou_raca": Dataset(
        name="cor_ou_raca",
        prefix="Agregados_por_setores_cor_ou_raca_BR",
        columns={
            "raca_branca": "V01317",
            "raca_preta": "V01318",
            "raca_amarela": "V01319",
            "raca_parda": "V01320",
            "raca_indigena": "V01321",
        },
        description="Cor ou raca",
    ),
    "alfabetizacao": Dataset(
        name="alfabetizacao",
        prefix="Agregados_por_setores_alfabetizacao_BR",
        columns={
            # Numerador e denominador da taxa, ambos somando 13 faixas etarias
            # (o mesmo par que o ingest_census_indicators.py ja usava).
            "alfabetizados_15mais": _faixa(748, 760),
            "pop_15mais": _faixa(644, 656),
        },
        description="Alfabetizados de 15+ e populacao de 15+ (taxa)",
    ),
    "saneamento": Dataset(
        name="saneamento",
        prefix="Agregados_por_setores_caracteristicas_domicilio2_BR",
        columns={
            # "adequado" = as primeiras categorias da lista; "total" = a lista
            # inteira. Mesma leitura do ingest_census_saneamento.py.
            "dom_agua_rede": "V00111",
            "dom_agua_total": _faixa(111, 118),
            "dom_esgoto_adequado": "V00309+V00310",
            "dom_esgoto_total": _faixa(309, 315),
            "dom_lixo_coletado": "V00397+V00398",
            "dom_lixo_total": _faixa(397, 402),
        },
        description="Agua, esgoto e lixo por domicilio",
    ),
}

# NOTA: renda do responsavel (V06004) NAO esta aqui de proposito — o IBGE a
# publica noutro diretorio (Agregados..._Rendimento_do_Responsavel) e por
# MUNICIPIO, nao por setor. Continua no ingest_census_renda_responsavel.py.


# ---------------------------------------------------------------------------
# Expressoes e conversao
# ---------------------------------------------------------------------------
_NULOS = {"", "-", "..", "...", "X", "x", "nan", "none", "null"}
_RE_FAIXA = re.compile(r"^([A-Za-z]+)(\d+)\.\.[A-Za-z]+(\d+)$")

# O IBGE nomeia a coluna do codigo do setor de um jeito diferente em cada
# agregado: "CD_SETOR" no basico, "CD_setor" na demografia e simplesmente
# "setor" em caracteristicas_domicilio (que tambem nao traz CD_UF nenhum).
# A comparacao e feita em minusculo, entao aqui basta uma grafia de cada.
NOMES_SETOR = ("CD_SETOR", "cod_setor", "setor", "codigo_setor")
NOMES_UF = ("CD_UF", "cod_uf")


def _expandir(expr: str) -> list[str]:
    """"V00309+V00310" -> ["V00309","V00310"]; "V00111..V00113" -> 3 codigos."""
    codigos: list[str] = []
    for termo in expr.split("+"):
        termo = termo.strip()
        if not termo:
            continue
        if (m := _RE_FAIXA.match(termo)) is not None:
            prefixo, ini, fim = m.group(1), m.group(2), m.group(3)
            largura = len(ini)
            codigos += [f"{prefixo}{n:0{largura}d}" for n in range(int(ini), int(fim) + 1)]
        else:
            codigos.append(termo)
    return codigos


def _to_number(raw: object, kind: str) -> int | float | None:
    """Converte uma celula. Sigilo/vazio/lixo viram None (nao erro)."""
    if raw is None:
        return None
    s = str(raw).strip().strip('"')
    if s.lower() in _NULOS:
        return None
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        return None
    if v != v:  # NaN
        return None
    return int(v) if kind == "int" else v


def _somar(row: dict, codigos: list[str], kind: str) -> int | float | None:
    """Soma os codigos, ignorando os que vierem em sigilo.

    Se NENHUM tiver valor, devolve None — diferente de zero. Zero significaria
    "nao ha ninguem neste setor", e sigilo nao e isso.
    """
    total: float = 0.0
    tem_algum = False
    for cod in codigos:
        v = _to_number(row.get(cod), kind)
        if v is not None:
            total += v
            tem_algum = True
    if not tem_algum:
        return None
    return int(total) if kind == "int" else total


@dataclass
class Stats:
    """Contadores do run — viram o progresso e o resumo final."""

    lidas: int = 0
    gravadas: int = 0
    ignoradas_uf: int = 0
    ignoradas_sem_codigo: int = 0
    erros: int = 0
    exemplos_erro: list[str] = field(default_factory=list)

    def registrar_erro(self, msg: str) -> None:
        self.erros += 1
        if len(self.exemplos_erro) < 5:
            self.exemplos_erro.append(msg)


# ---------------------------------------------------------------------------
# Descoberta e leitura do arquivo
# ---------------------------------------------------------------------------
def _resolver_url(ds: Dataset) -> str:
    """Acha o arquivo atual do dataset no diretorio do IBGE.

    Existe porque o IBGE versiona por data no nome do arquivo. Se a listagem
    falhar (rede, mudanca de layout do indice), cai pro nome sem data — que e
    o formato de boa parte dos agregados.
    """
    try:
        req = urllib.request.Request(FTP_BASE, headers={"User-Agent": "marenostrum-etl/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            html = resp.read().decode("utf-8", "ignore")
        nomes = sorted(set(re.findall(r'href="([^"]+\.zip)"', html)))
        candidatos = [n for n in nomes if n.startswith(ds.prefix)]
        if candidatos:
            # sorted() poe a data maior por ultimo: pega a republicacao recente
            escolhido = candidatos[-1]
            if len(candidatos) > 1:
                log.info("varias_versoes_no_ibge",
                         dataset=ds.name, escolhido=escolhido, todas=candidatos)
            return FTP_BASE + escolhido
        log.warning("prefixo_sem_correspondencia", dataset=ds.name, prefixo=ds.prefix)
    except Exception as e:  # noqa: BLE001 — indisponibilidade nao pode travar o ETL
        log.warning("listagem_ibge_falhou", erro=f"{type(e).__name__}: {e}")
    return f"{FTP_BASE}{ds.prefix}.zip"


def _abrir_csv(origem: str, tmp_dir: str = "/tmp") -> str:
    """Devolve o caminho de um CSV local, baixando/descompactando se preciso.

    Baixa e extrai em disco (nao em memoria): os tematicos passam de 300 MB
    descompactados. Arquivo ja presente e reaproveitado — util quando a carga
    e retomada depois de uma queda.
    """
    if origem.startswith("http"):
        destino_zip = os.path.join(tmp_dir, os.path.basename(origem))
        if os.path.exists(destino_zip) and os.path.getsize(destino_zip) > 0:
            log.info("download_pulado", motivo="arquivo ja em disco", arquivo=destino_zip)
        else:
            log.info("download_iniciado", url=origem)
            t0 = time.perf_counter()
            req = urllib.request.Request(
                origem, headers={"User-Agent": "marenostrum-etl/1.0"}
            )
            parcial = destino_zip + ".part"
            with urllib.request.urlopen(req, timeout=900) as resp, open(parcial, "wb") as fh:
                while chunk := resp.read(1 << 20):  # 1 MB por vez
                    fh.write(chunk)
            # rename atomico: download interrompido nao vira "arquivo pronto"
            os.replace(parcial, destino_zip)
            log.info("download_concluido",
                     mb=round(os.path.getsize(destino_zip) / 1e6, 1),
                     segundos=round(time.perf_counter() - t0, 1))
        origem = destino_zip

    if origem.lower().endswith(".zip"):
        with zipfile.ZipFile(origem) as zf:
            nome = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            destino_csv = os.path.join(tmp_dir, os.path.basename(nome))
            if not os.path.exists(destino_csv):
                log.info("descompactando", de=os.path.basename(origem), para=destino_csv)
                with zf.open(nome) as src, open(destino_csv, "wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
            return destino_csv

    return origem


def _chunks(caminho: str, chunksize: int, usecols: list[str] | None) -> Iterator[pd.DataFrame]:
    """Le o CSV do IBGE em lotes, trazendo SO as colunas necessarias.

    `usecols` nao e otimizacao de luxo, e o que faz a carga caber na maquina:
    os agregados de alfabetizacao e saneamento tem 363 e 407 colunas, e ler
    tudo num chunk de 50 mil linhas estourou os 768 MB do container — o
    processo foi morto pelo OOM killer sem deixar mensagem, so parou. Com as
    ~15 colunas que o dataset usa, o mesmo chunk ocupa uma fracao disso.

    dtype=str e deliberado: deixar o pandas inferir tipo transforma o codigo do
    setor em float (330455705000001 vira 3.3e14) e come o zero a esquerda do
    codigo de municipio. A conversao numerica e feita coluna a coluna.
    """
    return pd.read_csv(
        caminho,
        sep=";",
        encoding="latin-1",
        dtype=str,
        chunksize=chunksize,
        usecols=usecols,
        on_bad_lines="warn",  # linha malformada avisa e segue
    )


def _preparar_leitura(
    caminho: str, ds: Dataset, mapa_cod: dict[str, list[str]]
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """Le so o cabecalho e decide o que trazer do disco.

    Devolve (mapa de codigos resolvido, colunas a ler, codigos ausentes).
    Resolver aqui — e nao no primeiro chunk — permite passar `usecols` ja na
    primeira leitura, que e onde a memoria estourava.
    """
    cabecalho = pd.read_csv(caminho, sep=";", encoding="latin-1", dtype=str, nrows=0)
    reais = {c.strip().lower(): c for c in cabecalho.columns}

    resolvido: dict[str, list[str]] = {}
    ausentes: list[str] = []
    for col_banco, codigos in mapa_cod.items():
        encontrados = []
        for cod in codigos:
            real = reais.get(cod.lower())
            if real is None:
                ausentes.append(cod)
            else:
                encontrados.append(real)
        resolvido[col_banco] = encontrados

    # Identificacao: sempre; cadastro: so no dataset que cria setor.
    ident = [*NOMES_SETOR, *NOMES_UF]
    if ds.creates:
        ident += ["CD_MUN", "NM_MUN", "CD_DIST", "NM_DIST", "NM_SUBDIST",
                  "NM_BAIRRO", "SITUACAO", "AREA_KM2"]
    usecols = [reais[n.lower()] for n in ident if n.lower() in reais]
    usecols += [c for cods in resolvido.values() for c in cods]

    # Sem a coluna de codigo do setor nao ha o que casar — parar aqui, com o
    # cabecalho na mao, e muito mais claro do que estourar no primeiro chunk.
    if not any(reais.get(n.lower()) for n in NOMES_SETOR):
        raise SystemExit(
            f"[{ds.name}] nenhuma coluna de codigo de setor neste CSV "
            f"(procurei por {', '.join(NOMES_SETOR)}). "
            f"Colunas do arquivo: {list(cabecalho.columns)[:10]}"
        )

    return resolvido, sorted(set(usecols)), ausentes


def _coluna(df: pd.DataFrame, *nomes: str) -> str | None:
    """Acha a coluna ignorando caixa — o IBGE alterna CD_SETOR e CD_setor
    entre agregados, e isso ja quebrou script neste projeto."""
    mapa = {c.strip().lower(): c for c in df.columns}
    for n in nomes:
        if (achado := mapa.get(n.lower())) is not None:
            return achado
    return None




# ---------------------------------------------------------------------------
# Gravacao
# ---------------------------------------------------------------------------
def _montar_sql(ds: Dataset):
    cols = list(ds.columns)
    if ds.creates:
        campos = ["cd_setor", "cd_mun", "nm_mun", "cd_dist", "nm_dist",
                  "nm_subdist", "nm_bairro", "situacao", "area_km2", *cols]
        # COALESCE no UPDATE: valor novo NULL (sigilo) nao apaga o que ja estava
        # gravado. Sem isso, reprocessar o basico zeraria dado bom de tematico.
        sets = ", ".join(f"{c}=COALESCE(EXCLUDED.{c}, census_geo.{c})" for c in campos[1:])
        # updated_at carimbado na mao: e o que responde "quando esta UF foi
        # carregada?" numa carga que roda por partes ao longo de semanas.
        return text(
            f"INSERT INTO census_geo (level, updated_at, {', '.join(campos)}) "
            f"VALUES ('setor', now(), {', '.join(f':{c}' for c in campos)}) "
            f"ON CONFLICT (cd_setor) DO UPDATE SET {sets}, updated_at=now()"
        )
    # Tematico: so atualiza setor existente. Nao casar e o caso NORMAL quando
    # se carrega uma UF por vez.
    sets = ", ".join(f"{c}=:{c}" for c in cols)
    return text(
        f"UPDATE census_geo SET {sets}, updated_at=now() "
        f"WHERE cd_setor=:cd_setor AND level='setor'"
    )


def _gravar(db: Session, sql, linhas: list[dict], st: Stats) -> int:
    """Grava um lote; se ele falhar, reprocessa linha a linha.

    O fallback existe pra que um unico registro problematico nao custe o lote
    inteiro (ate dezenas de milhares de linhas).
    """
    if not linhas:
        return 0
    try:
        db.execute(sql, linhas)
        db.commit()
        return len(linhas)
    except Exception as e:  # noqa: BLE001 — lote ruim nao para o arquivo
        db.rollback()
        salvas = 0
        for item in linhas:
            try:
                db.execute(sql, [item])
                db.commit()
                salvas += 1
            except Exception as e2:  # noqa: BLE001
                db.rollback()
                st.registrar_erro(f"setor {item.get('cd_setor')}: {type(e2).__name__}: {e2}")
        log.warning("lote_falhou_reprocessado_linha_a_linha",
                    erro=str(e)[:200], salvas=salvas, do_lote=len(linhas))
        return salvas


def _parse_linha(row: dict, ds: Dataset, mapa_cod: dict[str, list[str]],
                 col_setor: str, col_uf: str | None, cadastro: dict[str, str | None],
                 ufs: set[str] | None, st: Stats) -> dict | None:
    """Converte uma linha do CSV no dict de bind. None = pular."""
    cd = str(row.get(col_setor) or "").strip().strip('"')
    if not cd or cd.lower() == "nan":
        st.ignoradas_sem_codigo += 1
        return None

    if ufs is not None:
        # A UF sao os 2 primeiros digitos do codigo do setor; a coluna CD_UF e
        # preferida quando existe.
        uf = str(row.get(col_uf) or cd[:2]).strip().strip('"')[:2]
        if uf not in ufs:
            st.ignoradas_uf += 1
            return None

    dados: dict = {"cd_setor": cd}
    for col_banco, codigos in mapa_cod.items():
        dados[col_banco] = _somar(row, codigos, ds.kind)

    if ds.creates:
        for campo, origem in cadastro.items():
            valor = row.get(origem) if origem else None
            valor = str(valor).strip().strip('"') if valor is not None else None
            # "." e o "nao se aplica" do IBGE em campo de texto — aparece em
            # CD_NU, CD_FCU, CD_AGLOM e, principalmente, no CD_MUN das duas
            # unidades que nao sao municipio: Lagoa dos Patos (4300001) e Lagoa
            # Mirim (4300002), corpos d'agua do RS com populacao zero. Sem este
            # tratamento o "." era gravado como se fosse codigo de municipio.
            if valor in (None, "", ".", "..") or valor.lower() == "nan":
                valor = None
            dados[campo] = valor
        # cd_mun a partir do codigo do setor: mais confiavel que a coluna do
        # arquivo, que ja veio vazia em alguns agregados.
        dados["cd_mun"] = (dados.get("cd_mun") or cd[:7])[:7]
        # area_km2 vem com virgula decimal ("0,5393102") e e float, nao texto.
        dados["area_km2"] = _to_number(row.get("AREA_KM2"), "float")

    return dados


def processar(db: Session, ds: Dataset, caminho: str, chunksize: int,
              ufs: set[str] | None, dry_run: bool, limite: int | None) -> Stats:
    st = Stats()
    sql = _montar_sql(ds)
    mapa_cod = {col: _expandir(expr) for col, expr in ds.columns.items()}

    mapa_cod, usecols, ausentes = _preparar_leitura(caminho, ds, mapa_cod)
    if ausentes:
        log.warning("variaveis_ausentes_no_csv", dataset=ds.name,
                    quantas=len(ausentes), exemplos=ausentes[:6],
                    efeito="essas colunas ficarao NULL")
    # Nenhuma variavel encontrada = arquivo errado ou layout novo do IBGE.
    # Seguir gravaria centenas de milhares de linhas com tudo NULL, apagando
    # o que ja existia — melhor parar e avisar.
    if not any(mapa_cod.values()):
        raise SystemExit(
            f"[{ds.name}] nenhuma variavel do catalogo existe neste CSV. "
            f"Esperadas: {sorted({c for v in ds.columns.values() for c in _expandir(v)})[:6]}..."
        )
    log.info("colunas_lidas_do_arquivo", quantas=len(usecols),
             motivo="so o necessario: o arquivo inteiro nao cabe na memoria")

    t0 = time.perf_counter()
    proximo_aviso = 50_000

    for i, df in enumerate(_chunks(caminho, chunksize, usecols), start=1):
        col_setor = _coluna(df, *NOMES_SETOR)
        col_uf = _coluna(df, *NOMES_UF)  # None em caracteristicas_domicilio:
        # ali a UF sai dos 2 primeiros digitos do codigo do setor (ver _parse_linha)
        cadastro = {
            "cd_mun": _coluna(df, "CD_MUN"),
            "nm_mun": _coluna(df, "NM_MUN"),
            "cd_dist": _coluna(df, "CD_DIST"),
            "nm_dist": _coluna(df, "NM_DIST"),
            "nm_subdist": _coluna(df, "NM_SUBDIST"),
            "nm_bairro": _coluna(df, "NM_BAIRRO"),
            "situacao": _coluna(df, "SITUACAO"),
        } if ds.creates else {}

        lote: list[dict] = []
        for row in df.to_dict("records"):
            st.lidas += 1
            try:
                item = _parse_linha(row, ds, mapa_cod, col_setor, col_uf,
                                    cadastro, ufs, st)
            except Exception as e:  # noqa: BLE001 — linha ruim nao para o arquivo
                st.registrar_erro(f"linha {st.lidas}: {type(e).__name__}: {e}")
                continue
            if item is not None:
                lote.append(item)

        if dry_run:
            st.gravadas += len(lote)  # o que gravaria
        else:
            st.gravadas += _gravar(db, sql, lote, st)

        if st.lidas >= proximo_aviso:
            decorrido = time.perf_counter() - t0
            log.info("progresso",
                     lidas=st.lidas, gravadas=st.gravadas, erros=st.erros,
                     linhas_por_seg=int(st.lidas / decorrido) if decorrido else 0)
            proximo_aviso += 50_000

        if limite and st.lidas >= limite:
            log.info("limite_atingido", limite=limite)
            break

    log.info("arquivo_concluido", dataset=ds.name,
             segundos=round(time.perf_counter() - t0, 1))
    return st


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(
        description="Carga dos Agregados por Setores do Censo IBGE 2022."
    )
    p.add_argument("--dataset", help="tema a carregar (ver --list-datasets)")
    p.add_argument("--list-datasets", action="store_true", help="lista os temas")
    p.add_argument("--uf", action="append", default=[],
                   help="codigo IBGE da UF (33=RJ). Repetivel.")
    p.add_argument("--all-brasil", action="store_true", help="carrega o pais inteiro")
    p.add_argument("--file", help="usa um .zip/.csv local em vez de baixar")
    p.add_argument("--chunksize", type=int, default=50_000, help="linhas por lote")
    p.add_argument("--limit", type=int, help="para depois de N linhas (teste)")
    p.add_argument("--dry-run", action="store_true", help="le e valida, sem gravar")
    args = p.parse_args()

    if args.list_datasets:
        print("\nTemas disponiveis:\n")
        for nome, ds in DATASETS.items():
            marca = "  [cria setores — rode primeiro]" if ds.creates else ""
            print(f"  {nome:<16} {ds.description}{marca}")
            print(f"  {'':<16} colunas: {', '.join(ds.columns)}\n")
        return 0

    if not args.dataset:
        p.error("informe --dataset (ou --list-datasets)")
    if args.dataset not in DATASETS:
        p.error(f"dataset '{args.dataset}' nao existe. Veja --list-datasets.")
    if not args.uf and not args.all_brasil:
        p.error("informe --uf (repetivel) ou --all-brasil. A carga nacional e "
                "pesada demais pra acontecer por descuido.")

    ds = DATASETS[args.dataset]
    ufs = {u.strip()[:2] for u in args.uf} or None

    log.info("etl_iniciado", dataset=ds.name,
             escopo="Brasil" if ufs is None else ",".join(sorted(ufs)),
             chunksize=args.chunksize, dry_run=args.dry_run,
             colunas=list(ds.columns))

    db = SessionLocal()
    try:
        # Carga longa nao pode morrer no statement_timeout do servidor (que
        # existe pra proteger a API) — ja derrubou script de agregacao aqui.
        db.execute(text("SET statement_timeout = 0"))
        db.commit()

        caminho = _abrir_csv(args.file or _resolver_url(ds))
        log.info("csv_pronto", arquivo=caminho,
                 mb=round(os.path.getsize(caminho) / 1e6, 1))

        st = processar(db, ds, caminho, args.chunksize, ufs, args.dry_run, args.limit)

        log.info("etl_concluido", dataset=ds.name, lidas=st.lidas,
                 gravadas=st.gravadas, ignoradas_outra_uf=st.ignoradas_uf,
                 ignoradas_sem_codigo=st.ignoradas_sem_codigo, erros=st.erros,
                 dry_run=args.dry_run)
        for exemplo in st.exemplos_erro:
            log.warning("exemplo_de_erro", detalhe=exemplo)

        if not args.dry_run:
            total, com_pop = db.execute(text(
                "SELECT count(*), count(*) FILTER (WHERE populacao IS NOT NULL) "
                "FROM census_geo WHERE level='setor'"
            )).first()
            log.info("estado_da_tabela", setores=total, com_populacao=com_pop)
            log.info("proximo_passo",
                     acao="rodar scripts/refresh_census_muni_agg.py",
                     motivo="agregados por municipio sao materializados (migration 058)")

        # Nada gravado com linhas lidas = arquivo errado, UF inexistente ou
        # layout mudou. Sai != 0 pro cron/CI perceber.
        if st.lidas and st.gravadas == 0:
            log.error("nada_gravado", dica="confira --uf e o dataset")
            return 1
        return 0
    except KeyboardInterrupt:
        log.warning("interrompido", dica="pode rodar de novo: e idempotente")
        return 130
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
