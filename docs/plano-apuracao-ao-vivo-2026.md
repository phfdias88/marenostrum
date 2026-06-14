# Plano — Apuração ao Vivo (Eleições Out/2026)

> Status: planejado (task #74). Não dá para validar de ponta a ponta sem uma
> eleição em curso; o TSE só liga os endpoints de divulgação no dia. Estratégia:
> construir em setembro com **replay dos JSONs de 2024** e ligar no 1º turno.

## O que o cliente vê
- Painel "Apuração ao vivo" (rota `/dashboard/apuracao`, modo TV incluído):
  % apurado, ranking em tempo real do(s) cargo(s) escolhidos, candidatos
  monitorados destacados, projeção eleito/não-eleito (QE/D'Hondt já existentes
  no projeto reaproveitados pra proporcionais).
- Atualização a cada 30–60s sem refresh (polling com `If-None-Match`).

## Fonte de dados (dia da eleição)
- CDN pública do TSE (mesma dos apps de imprensa):
  `https://resultados.tse.jus.br/oficial/ele2026/<ELEICAO>/dados-simplificados/<uf>/<uf>-c<cargo>-e<eleicao>-r.json`
  (+ `comum/config/ele-c.json` para descobrir códigos de eleição do ano).
- JSONs pequenos (~KB), atualizados pelo TSE a cada ~30s. Sem auth.
- 2º turno = outro código de eleição (mesma estrutura).

## Arquitetura (encaixa no que já temos)
1. **Worker de polling** (asyncio task no lifespan, como o warmup):
   busca os JSONs das UFs/cargos configurados a cada 45s, normaliza e grava
   em `tse_live_results` (upsert por `(eleicao, uf, cargo, sq_candidato)`).
   Liga/desliga por env `LIVE_ELECTION=ele2026-1t` (vazio = dormente).
2. **Endpoints**: `GET /tse/live/summary?uf=&office=` (ranking + % apurado,
   `Cache-Control: no-store`, agg em memória 15s) e `GET /tse/live/status`.
3. **Frontend**: página com auto-refresh (SWR-style, 30s), barra de % apurado,
   ranking com foto/partido (componentes existentes), badge nos monitorados,
   confete pro eleito 🎉. Modo TV reaproveita o 17A.
4. **nginx**: rota `/api/v1/tse/live/` fora do cache de borda (no-store).

## Cronograma sugerido
- **Set/2026 (semana 1-2)**: worker + replay de 2024 (gravamos amostras reais
  dos JSONs de 2024 — estrutura idêntica) + página.
- **Set/2026 (semana 3)**: teste de carga (50 clientes simultâneos no painel),
  modo TV, polimento.
- **Simulado nacional do TSE (~1 semana antes)**: ensaio geral com dados do
  simulado oficial.
- **1º turno (04/10/2026)**: ligar `LIVE_ELECTION`; plantão.

## Riscos e mitigação
- TSE mudar o formato → parser tolerante + replay do simulado pega antes.
- Pico de uso no VPS 1 vCPU → os dados live são MEMÓRIA (poucos KB) e os
  clientes batem num agg cacheado 15s; o resto do site segue no cache nginx.
- CDN TSE instável na 1ª hora (histórico) → backoff exponencial + última
  leitura válida com timestamp "atualizado há Xs" na tela.

## Por que vende
Todo cliente quer estar na frente do telão na noite da eleição. É o momento
de maior atenção do ciclo — e o painel com a marca MareNostrum vira a peça
central da "war room" do candidato.
