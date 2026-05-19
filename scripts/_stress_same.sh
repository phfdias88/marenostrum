#!/usr/bin/env bash
ID=185bf3c7-8104-493d-8cdc-88d953c6015f
# Limpa cache da Margarida pra forcar fetch real
docker compose -f ~/marenostrum/docker-compose.yml exec -T api rm -f /var/marenostrum/tse_photos/MG/130001883579.jpg

echo "== 4 reqs concorrentes pro mesmo candidato (Margarida) =="
for i in 1 2 3 4; do
  curl -s "http://localhost/api/v1/tse/candidates/$ID/photo" -o /tmp/m_$i.jpg \
    -w "  req$i: %{http_code} size=%{size_download} time=%{time_total}s\n" &
done
wait
echo ""
echo "== Hashes (todas devem ser iguais) =="
md5sum /tmp/m_*.jpg
rm /tmp/m_*.jpg
