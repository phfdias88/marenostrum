"""
Correção cirúrgica: remove votos de 2º turno somados indevidamente na votação
nominal dos finalistas (presidente/governador/prefeito de capital).

Causa: o importador antigo agregava votos por (SQ_CANDIDATO, município) sem
filtrar NR_TURNO. Como o SQ é o mesmo nos dois turnos, votos de 1º + 2º turno
caíam na MESMA linha — ex: Lula 2022 = 117M (57M 1ºT + 60M 2ºT) em vez de 57M.

Correção (cirúrgica, sem truncar nada):
  1. Baixa o munzona de cada ano.
  2. Pass 1: identifica finalistas = SQ com linha NR_TURNO==2.
  3. Pass 2: soma SÓ os votos de 1º turno (NR_TURNO==1) desses finalistas.
  4. Só sobrescreve candidatos CONFIRMADAMENTE inflados (total atual > 1ºT
     calculado). Registros já corretos (R1/R2 separados) são protegidos.

Uso:
  python fix_runoff_votes.py            # DRY-RUN (só mostra, não grava)
  python fix_runoff_votes.py --apply    # aplica de verdade
"""
import sys
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, func, insert, select

from app.core.database import SessionLocal
from app.models.tse import Candidate, Election, Municipality, VoteResult
from app.utils.tse_sync import CACHE_DIR, DATASETS, _i, download_zip, iter_csv_rows

YEARS = [2014, 2016, 2018, 2020, 2022, 2024]
APPLY = "--apply" in sys.argv


def fix_year(db, year, munis_by_tse):
    key = f"candidato_munzona_{year}"
    meta = DATASETS[key]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE_DIR / f"{key}.zip"
    if not zip_path.exists():
        print(f"[{year}] baixando {meta['url']} ...")
        download_zip(meta["url"], zip_path, max_mb=meta.get("max_mb"))
    else:
        print(f"[{year}] zip já em cache")

    # Pass 1: finalistas = SQ com NR_TURNO==2
    finalist_sqs = set()
    for _, row in iter_csv_rows(zip_path, name_contains="_BRASIL"):
        if _i(row.get("NR_TURNO")) == 2:
            sq = _i(row.get("SQ_CANDIDATO"))
            if sq:
                finalist_sqs.add(sq)
    print(f"[{year}] finalistas (SQ com 2º turno): {len(finalist_sqs)}")
    if not finalist_sqs:
        return 0, 0

    # Mapeia SQ -> candidate_id (do ano)
    year_eids = list(
        db.execute(select(Election.id).where(Election.year == year)).scalars()
    )
    cand_rows = db.execute(
        select(Candidate.id, Candidate.sq_candidato, Candidate.urn_name)
        .where(
            Candidate.election_id.in_(year_eids),
            Candidate.sq_candidato.in_(finalist_sqs),
        )
    ).all()
    # SQ pode mapear p/ +1 registro (R1 e R2 separados) — nesse caso já está
    # correto e NÃO mexemos. Só corrigimos SQ com EXATAMENTE 1 registro.
    sq_count = {}
    for cid, sq, urn in cand_rows:
        sq_count[sq] = sq_count.get(sq, 0) + 1
    sq_to_cid = {
        sq: cid for cid, sq, urn in cand_rows if sq_count[sq] == 1
    }
    cid_name = {cid: urn for cid, sq, urn in cand_rows}
    print(f"[{year}] finalistas no banco: {len(cand_rows)} | "
          f"com 1 registro (candidatos a corrigir): {len(sq_to_cid)}")

    # Pass 2: soma votos de 1º turno só pros finalistas-alvo
    acc = {}  # (cid, muni_id) -> votos 1ºT
    for _, row in iter_csv_rows(zip_path, name_contains="_BRASIL"):
        if _i(row.get("NR_TURNO")) != 1:
            continue
        sq = _i(row.get("SQ_CANDIDATO"))
        cid = sq_to_cid.get(sq)
        if not cid:
            continue
        mid = munis_by_tse.get(_i(row.get("CD_MUNICIPIO")))
        if not mid:
            continue
        acc[(cid, mid)] = acc.get((cid, mid), 0) + _i(row.get("QT_VOTOS_NOMINAIS"))

    # Total 1ºT calculado por candidato
    t1_by_cid = {}
    for (cid, _mid), v in acc.items():
        t1_by_cid[cid] = t1_by_cid.get(cid, 0) + v

    # Guarda: só corrige quem está REALMENTE inflado (total atual > 1ºT calc).
    now = datetime.now(timezone.utc)
    corrected = 0
    rows_written = 0
    for cid, t1 in t1_by_cid.items():
        if t1 <= 0:
            continue
        current = db.execute(
            select(func.coalesce(func.sum(VoteResult.votes), 0)).where(
                VoteResult.candidate_id == cid
            )
        ).scalar()
        if current <= t1 * 1.001:  # não inflado (margem p/ arredondamento)
            print(f"    SKIP {cid_name.get(cid):<22} atual={current:,} ~ 1ºT={t1:,} (ok)")
            continue
        new_rows = [
            {"id": uuid4(), "candidate_id": cid, "municipality_id": mid,
             "votes": v, "created_at": now, "updated_at": now}
            for (c, mid), v in acc.items() if c == cid and v > 0
        ]
        print(f"    FIX  {cid_name.get(cid):<22} {current:>14,} -> {t1:>14,} "
              f"({len(new_rows)} munis)")
        if APPLY:
            db.execute(delete(VoteResult).where(VoteResult.candidate_id == cid))
            for i in range(0, len(new_rows), 5000):
                db.execute(insert(VoteResult), new_rows[i:i + 5000])
            db.commit()
        corrected += 1
        rows_written += len(new_rows)
    return corrected, rows_written


def main():
    db = SessionLocal()
    munis_by_tse = {
        m.tse_code: m.id for m in db.execute(select(Municipality)).scalars()
    }
    print(f"=== {'APPLY' if APPLY else 'DRY-RUN'} | municípios={len(munis_by_tse)} ===")
    tot_c = 0
    tot_r = 0
    for y in YEARS:
        c, r = fix_year(db, y, munis_by_tse)
        tot_c += c
        tot_r += r
        print(f"[{y}] -> corrigidos={c}")
    print(f"=== TOTAL candidatos corrigidos={tot_c} linhas={tot_r} "
          f"({'APLICADO' if APPLY else 'DRY-RUN — nada gravado'}) ===")


if __name__ == "__main__":
    main()
