#!/usr/bin/env python3
"""
Preenche a coordenada dos municipios que ficaram SEM latitude/longitude.

POR QUE EXISTE: municipio sem coordenada nao aparece em mapa nenhum, e isso
passa despercebido — ninguem procura o que nao esta la. Em out/2026 eram 68,
entre eles BRASILIA. Dois motivos:

  * o geocode original (app/utils/tse_muni_geocode.py) casa nome por nome, e o
    TSE escreve "OLHO D AGUA DAS FLORES" onde o IBGE escreve "Olho d'Agua das
    Flores" — o apostrofo vira espaco e o nome deixa de casar;
  * municipio que so entrou no banco numa eleicao geral (Brasilia nao tem
    eleicao municipal) nasceu depois de o geocode ter rodado.

O QUE FAZ: so mexe em quem esta com a coordenada VAZIA — nunca troca uma que ja
existe. Compara os nomes sem acento, sem espaco e sem pontuacao; o que sobrar
vai pela tabela GRAFIAS, de variacoes que so se resolvem olhando.

Depois de aplicar, o mapa de vencedores precisa ser refeito (ele guarda uma
copia da coordenada): scripts/refresh_tse_winners_map.py, sem --year.

USO (entra por stdin, como os outros scripts de operacao):
    docker compose exec -T -e PYTHONPATH=/app api \
        python - < backend/scripts/completar_coordenadas.py            # so mostra
    ... python - --aplicar < backend/scripts/completar_coordenadas.py   # grava
"""
from __future__ import annotations

import argparse
import csv
import difflib
import io
import unicodedata

from sqlalchemy import text

from app.core.database import SessionLocal
from app.utils.tse_muni_geocode import UF_BY_CODE, _download_csv

# (UF, nome no TSE) -> nome na base de coordenadas. So entra aqui o que a
# comparacao automatica nao resolve: grafia divergente entre TSE e IBGE, e
# municipio que mudou de nome (a base ainda traz o antigo).
GRAFIAS: dict[tuple[str, str], str] = {
    ("BA", "CAMACÃ"): "Camacan",
    ("BA", "MUQUÉM DO SÃO FRANCISCO"): "Muquém de São Francisco",
    ("BA", "SANTA TEREZINHA"): "Santa Teresinha",
    ("PA", "ELDORADO DOS CARAJÁS"): "Eldorado do Carajás",
    ("PE", "SÃO CAITANO"): "São Caetano",
    ("PR", "MUNHOZ DE MELLO"): "Munhoz de Melo",
    ("RN", "AREZ"): "Arês",
    ("RN", "ASSÚ"): "Açu",
    ("RN", "BOA SAÚDE"): "Januário Cicco (Boa Saúde)",        # nome antigo
    ("RN", "CAMPO GRANDE"): "Augusto Severo (Campo Grande)",  # nome antigo
    ("RO", "ALVORADA DO OESTE"): "Alvorada D'Oeste",
    ("RO", "ESPIGÃO DO OESTE"): "Espigão D'Oeste",
    ("SE", "GRACCHO CARDOSO"): "Gracho Cardoso",
    ("SP", "FLORÍNEA"): "Florínia",
    ("SP", "SÃO LUÍS DO PARAITINGA"): "São Luiz do Paraitinga",
    ("TO", "TABOCÃO"): "Fortaleza do Tabocão",       # nome antigo
}


def chave(nome: str) -> str:
    """Nome reduzido a letras e numeros: sem acento, caixa, espaco ou pontuacao.

    E o que faz "OLHO D AGUA" e "Olho d'Agua" virarem a mesma coisa."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome or "")
        if not unicodedata.combining(c)
    )
    return "".join(c for c in sem_acento.lower() if c.isalnum())


def main() -> int:
    p = argparse.ArgumentParser(description="Preenche coordenada de municipio vazia.")
    p.add_argument("--aplicar", action="store_true", help="grava (padrao: so mostra)")
    args = p.parse_args()

    por_uf: dict[str, dict[str, tuple[float, float, str]]] = {}
    for row in csv.DictReader(io.StringIO(_download_csv())):
        try:
            uf = UF_BY_CODE[int(row["codigo_uf"])]
            lat, lng = float(row["latitude"]), float(row["longitude"])
        except (KeyError, ValueError):
            continue
        por_uf.setdefault(uf, {})[chave(row["nome"])] = (lat, lng, row["nome"])

    db = SessionLocal()
    vazios = db.execute(text("""
        SELECT id, name, state FROM tse_municipalities
        WHERE state <> 'ZZ' AND (latitude IS NULL OR longitude IS NULL)
        ORDER BY state, name
    """)).all()

    achados, sem_par = [], []
    for m in vazios:
        da_uf = por_uf.get(m.state, {})
        k = chave(GRAFIAS.get((m.state, m.name), m.name))
        if k in da_uf:
            achados.append((m, da_uf[k]))
            continue
        # Nao casou: mostra os nomes mais parecidos DA MESMA UF, para quem for
        # completar a tabela GRAFIAS decidir olhando — nunca casa sozinho por
        # semelhanca, que e como uma cidade ganha a coordenada da vizinha.
        proximos = difflib.get_close_matches(k, list(da_uf), n=2, cutoff=0.75)
        sem_par.append((m, [da_uf[p][2] for p in proximos]))

    print(f"sem coordenada: {len(vazios)} | casaram: {len(achados)} | "
          f"sem par: {len(sem_par)}")
    for m, (lat, lng, nome_ibge) in achados:
        print(f"  ok   {m.state} {m.name:38s} -> {nome_ibge} ({lat:.4f}, {lng:.4f})")
    for m, proximos in sem_par:
        print(f"  ???  {m.state} {m.name:38s} parecidos: {proximos or 'nenhum'}")

    if not args.aplicar:
        print("\n(nada gravado — rode com --aplicar)")
        return 0

    for m, (lat, lng, _nome) in achados:
        db.execute(
            text("""
                UPDATE tse_municipalities
                SET latitude = :lat, longitude = :lng, updated_at = now()
                WHERE id = :id AND latitude IS NULL
            """),
            {"lat": lat, "lng": lng, "id": m.id},
        )
    db.commit()
    print(f"\ngravados: {len(achados)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
