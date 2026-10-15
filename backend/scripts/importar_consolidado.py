#!/usr/bin/env python3
"""
Roda datasets do TSE (os mesmos do POST /tse/sync) FORA da API.

POR QUE: o job da API roda dentro do processo que atende o site — 768 MB e
0,4 vCPU, e a API cresce com o tempo de pe (655 MB depois de 45 h). Aqui o
importador roda num container proprio:

    nohup docker compose run --rm --no-deps -T --entrypoint python api \\
        /app/scripts/importar_consolidado.py consulta_cand_2026 \\
        < /dev/null > ~/importar-consolidado.log 2>&1 &

O ARQUIVO: usa o zip que estiver em tse_drop com o nome do dataset
(<dataset>.zip) SEM comparar o tamanho com o do TSE. Quem roda isto validou o
arquivo a mao, e a CDN do TSE ja serviu duas versoes do mesmo zip no mesmo dia:
a comparacao de tamanho apagaria o arquivo validado para baixar o outro. Sem
arquivo em disco, baixa do TSE. `--conferir-com-o-tse` volta ao comportamento
do job da API.

CUIDADO com candidato_munzona_<ano>: ele APAGA os votos por municipio do ano
antes de regravar. Em 14/10/2026 o arquivo oficial de 2026 veio sem os
deputados de Rondonia — importa-lo apagaria o voto deles. Conferir o arquivo
contra o banco antes (candidatos que somem, totais) e o que decide.

Para no primeiro que falhar (codigo 1). Nao limpa o cache da API nem o do
nginx: este processo nao e o da API.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
except NameError:   # pelo STDIN nao ha __file__; o PYTHONPATH=/app resolve
    pass

from app.core.database import SessionLocal  # noqa: E402
from app.models.tse.sync_job import SyncJobStatus, TseSyncJob  # noqa: E402
from app.utils import tse_sync  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Datasets do TSE fora da API.")
    p.add_argument("datasets", nargs="+", help="chaves de tse_sync.DATASETS")
    p.add_argument("--conferir-com-o-tse", action="store_true",
                   help="compara o tamanho do zip em disco com o do TSE (como o job da API)")
    args = p.parse_args()

    desconhecidos = [d for d in args.datasets if d not in tse_sync.DATASETS]
    if desconhecidos:
        print(f"ERRO: dataset desconhecido: {', '.join(desconhecidos)}", file=sys.stderr)
        return 2
    if not args.conferir_com_o_tse:
        tse_sync._cache_ainda_vale = lambda url, local: True

    for dataset in args.datasets:
        zip_path = tse_sync.CACHE_DIR / f"{dataset}.zip"
        origem = f"{zip_path} ({zip_path.stat().st_size:,} bytes)" if zip_path.exists() else "TSE (download)"
        with SessionLocal() as db:
            job = TseSyncJob(dataset=dataset, year=tse_sync.DATASETS[dataset]["year"],
                             status=SyncJobStatus.PENDING)
            db.add(job)
            db.commit()
            job_id = job.id
        print(f"{dataset}: job {job_id}, arquivo {origem}", flush=True)
        inicio = time.perf_counter()
        tse_sync.run_sync_job(job_id)
        with SessionLocal() as db:
            job = db.get(TseSyncJob, job_id)
            print(f"{dataset}: {job.status.value} em {time.perf_counter() - inicio:.0f}s | "
                  f"linhas {job.rows_processed:,} | candidatos novos {job.candidates_imported:,} | "
                  f"votos gravados {job.vote_results_imported:,}"
                  + (f" | ERRO: {job.error_message}" if job.error_message else ""), flush=True)
            if job.status != SyncJobStatus.COMPLETED:
                return 1
    print("Falta limpar o cache da API (POST /tse/ingest/cache-clear?everything=true) e o do nginx.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
