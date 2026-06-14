"""
Ingestão STREAMING dos indicadores extras do Censo 2022 (RJ):
- alfabetizados 15+ (V00644..V00656, arquivo alfabetizacao — 136MB)
- população 15+    (V01006 − 0-14 anos, arquivo demografia)
- cor/raça         (V01317..V01321, arquivo cor_ou_raca)

Lê linha a linha direto do zip (TextIOWrapper) — nunca carrega o CSV inteiro
em memória (o de 136MB derrubou o VPS quando lido de uma vez). Só guarda os
~41,7k setores do RJ num dict.

Pré: /tmp/alfa.zip, /tmp/demo.zip, /tmp/raca.zip no container.
"""
import csv
import io
import zipfile

from sqlalchemy import text

from app.core.database import SessionLocal

import os
UF = os.environ.get("UF", "33")

# Dicionário oficial: V00644..V00656 = PESSOAS por faixa (15+ — denominador);
# V00748..V00760 = pessoas ALFABETIZADAS por faixa (numerador). Mesmo arquivo,
# mesmo universo — taxa = sum(748..760) / sum(644..656).
POP15_COLS = [f"V006{n}" for n in range(44, 57)]
ALFA_COLS = [f"V007{n}" for n in range(48, 61)]
RACA_COLS = {
    "raca_branca": "V01317", "raca_preta": "V01318", "raca_amarela": "V01319",
    "raca_parda": "V01320", "raca_indigena": "V01321",
}


def _num(s):
    s = (s or "").strip().strip('"')
    if not s or s.upper() == "X":  # X = valor protegido por sigilo
        return None
    try:
        return int(float(s.replace(",", ".")))
    except ValueError:
        return None


def stream(zip_path: str):
    """Itera (idx, row) do CSV dentro do zip sem carregar tudo."""
    z = zipfile.ZipFile(zip_path)
    name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    with z.open(name) as fh:
        txt = io.TextIOWrapper(fh, encoding="latin-1", newline="")
        rdr = csv.reader(txt, delimiter=";")
        hdr = [h.strip('"').upper() for h in next(rdr)]
        idx = {h: i for i, h in enumerate(hdr)}
        yield idx, None
        for row in rdr:
            yield idx, row


def collect(zip_path: str, want_cols: list[str], label: str) -> dict:
    """cd_setor -> [valores das colunas pedidas], filtrado ao RJ."""
    out: dict[str, list] = {}
    gen = stream(zip_path)
    idx, _ = next(gen)
    i_set = idx["CD_SETOR"]
    col_is = [idx[c.upper()] for c in want_cols]
    n = 0
    for _, row in gen:
        cd = row[i_set].strip('"')
        if not cd.startswith(UF):
            continue
        out[cd] = [_num(row[i]) for i in col_is]
        n += 1
        if n % 20000 == 0:
            print(f"  {label}: {n} setores RJ lidos...")
    print(f"  {label}: {n} setores RJ no total")
    return out


def main():
    print("== streaming alfabetizacao (136MB) ==")
    both = collect("/tmp/alfa.zip", ALFA_COLS + POP15_COLS, "alfa")
    nA = len(ALFA_COLS)
    alfa = {k: v[:nA] for k, v in both.items()}
    demo = {k: v[nA:] for k, v in both.items()}
    print("== streaming cor_ou_raca ==")
    raca = collect("/tmp/raca.zip", list(RACA_COLS.values()), "raca")

    db = SessionLocal()
    cds = [r[0] for r in db.execute(text(
        "SELECT cd_setor FROM census_geo WHERE level='setor' AND cd_mun LIKE :u"
    ), {"u": UF + "%"}).all()]
    print(f"setores no banco: {len(cds)}")

    upd = text(
        "UPDATE census_geo SET alfabetizados_15mais=:a, pop_15mais=:p15, "
        "raca_branca=:rb, raca_preta=:rp, raca_amarela=:ra, raca_parda=:rd, "
        "raca_indigena=:ri WHERE cd_setor=:cd"
    )
    n = sem_alfa = 0
    for cd in cds:
        av = alfa.get(cd)
        a = sum(v for v in av if v is not None) if av and any(v is not None for v in av) else None
        if a is None:
            sem_alfa += 1
        dv = demo.get(cd)
        p15 = (sum(v for v in dv if v is not None)
               if dv and any(v is not None for v in dv) else None)
        rv = raca.get(cd) or [None] * 5
        db.execute(upd, {
            "a": a, "p15": p15,
            "rb": rv[0], "rp": rv[1], "ra": rv[2], "rd": rv[3], "ri": rv[4],
            "cd": cd,
        })
        n += 1
        if n % 2000 == 0:
            db.commit()
            print(f"  ... {n} updates")
    db.commit()

    chk = db.execute(text(
        "SELECT count(*) FILTER (WHERE alfabetizados_15mais IS NOT NULL), "
        "count(*) FILTER (WHERE pop_15mais IS NOT NULL), "
        "count(*) FILTER (WHERE raca_parda IS NOT NULL), "
        "sum(alfabetizados_15mais), sum(pop_15mais), "
        "sum(coalesce(raca_branca,0)+coalesce(raca_preta,0)+coalesce(raca_amarela,0)"
        "    +coalesce(raca_parda,0)+coalesce(raca_indigena,0)), "
        "sum(populacao) "
        "FROM census_geo WHERE level='setor' AND cd_mun LIKE :u"
    ), {"u": UF + "%"}).first()
    print(f"FINAL: alfa={chk[0]} pop15={chk[1]} raca={chk[2]} setores")
    print(f"  alfabetizados 15+ RJ: {chk[3]:,} | pop 15+ RJ: {chk[4]:,} "
          f"(taxa {100*chk[3]/chk[4]:.1f}%)")
    print(f"  soma raças: {chk[5]:,} vs população: {chk[6]:,} "
          f"({'OK' if abs(chk[5]-chk[6])/chk[6] < 0.02 else 'DIVERGE'})")


if __name__ == "__main__":
    main()
