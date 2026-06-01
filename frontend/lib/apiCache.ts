/**
 * Cache em memória + dedupe de requisições in-flight pra GETs da API.
 *
 * Objetivo: navegação fluida. Quando o usuário volta pra uma página já
 * visitada (ou dois componentes pedem o mesmo dado ao mesmo tempo), servimos
 * da memória — zero round-trip, render instantâneo.
 *
 * Três camadas:
 *  1. In-flight dedup: dois GETs idênticos simultâneos compartilham 1 fetch.
 *  2. Memory cache (TTL): GET recente volta instantâneo da RAM.
 *  3. Bust em mutação: POST/PUT/DELETE limpa o cache do recurso afetado,
 *     evitando dados velhos depois de criar/editar/excluir.
 *
 * NÃO substitui o HTTP cache do browser — soma. Memory cache morre no
 * reload da página (é volátil), então não há risco de "dado preso".
 */

type Entry = { data: unknown; expires: number };

const memCache = new Map<string, Entry>();
const inflight = new Map<string, Promise<unknown>>();

/** TTL por tipo de rota (ms). TSE = público/imutável → longo. Tenant → curto. */
export function ttlFor(path: string): number {
  // Dados TSE históricos não mudam — cache agressivo de 5 min em memória.
  if (path.startsWith("/v1/tse/")) return 5 * 60 * 1000;
  // Dados do tenant (contatos, demandas, monitorados): 30s — fresco o
  // suficiente, mas back-nav imediato dentro da janela.
  return 30 * 1000;
}

export function getCached(key: string): unknown | undefined {
  const e = memCache.get(key);
  if (!e) return undefined;
  if (Date.now() > e.expires) {
    memCache.delete(key);
    return undefined;
  }
  return e.data;
}

export function setCached(key: string, data: unknown, ttlMs: number): void {
  // Teto defensivo: não deixa o cache crescer infinito (LRU simplão).
  if (memCache.size > 200) {
    const oldest = memCache.keys().next().value;
    if (oldest) memCache.delete(oldest);
  }
  memCache.set(key, { data, expires: Date.now() + ttlMs });
}

export function getInflight(key: string): Promise<unknown> | undefined {
  return inflight.get(key);
}

export function setInflight(key: string, p: Promise<unknown>): void {
  inflight.set(key, p);
}

export function clearInflight(key: string): void {
  inflight.delete(key);
}

/**
 * Invalida entradas cujo key começa com algum dos prefixos.
 * Chamado após mutações. Ex: POST /v1/contacts → bust ["/v1/contacts"].
 */
export function bustCache(prefixes: string[]): void {
  for (const key of Array.from(memCache.keys())) {
    if (prefixes.some((p) => key.startsWith(p))) {
      memCache.delete(key);
    }
  }
}

/**
 * Deriva os prefixos a invalidar a partir do path de uma mutação.
 * Ex: PUT /v1/contacts/123 → bust "/v1/contacts" (lista + detalhe).
 * Conservador: pega o recurso raiz (/v1/<recurso>).
 */
export function bustPrefixesFor(path: string): string[] {
  const m = path.match(/^(\/v1\/[^/?]+)/);
  return m ? [m[1]] : [];
}
