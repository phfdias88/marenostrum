#!/usr/bin/env bash
# Mata loop+downloads presos, zera jobs zumbis, mostra cobertura real.
cd ~/marenostrum

echo "== Matando processos presos =="
pkill -f sync_all_ufs 2>/dev/null && echo "  loop morto" || echo "  (sem loop)"
pkill -f 'votacao_secao' 2>/dev/null && echo "  downloads mortos" || echo "  (sem downloads)"

echo ""
echo "== Zerando jobs zumbis (running/pending -> failed) =="
docker compose exec -T db psql -U marenostrum -d marenostrum -c \
  "UPDATE tse_sync_jobs SET status='failed', error_message='zumbi (cleanup)' WHERE status IN ('running','pending');"

echo ""
echo "== UFs com dados de secao (bairro disponivel) =="
docker compose exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT m.state, count(*) AS section_votes
FROM tse_section_votes sv
JOIN tse_voting_places vp ON vp.id=sv.voting_place_id
JOIN tse_municipalities m ON m.id=vp.municipality_id
GROUP BY m.state ORDER BY m.state;
"

echo ""
echo "== Disco + memoria =="
df -h / | tail -1
free -m | head -2

echo ""
echo "== Sanidade vote_results (Margarida JF deve ser 150.848) =="
docker compose exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT vr.votes FROM tse_vote_results vr
JOIN tse_candidates c ON c.id=vr.candidate_id
WHERE c.sq_candidato=130001883579;
"
