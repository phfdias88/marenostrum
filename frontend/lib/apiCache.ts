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
  // Censo IBGE é estático — voltar pro mesmo município não re-baixa nada.
  if (path.startsWith("/v1/census/")) return 10 * 60 * 1000;
  // Dados do tenant (contatos, demandas, monitorados): 30s — fresco o
  // suficiente, mas back-nav imediato dentro da janela.
  return 30 * 1000;
}

// ---- Persistência opcional em sessionStorage (só dados TSE) --------------
// O memCache morre no reload (F5/nova aba). Pra dados TSE — públicos e
// imutáveis — persistimos em sessionStorage: F5 e reabrir aba na mesma
// sessão servem instantâneo, sem re-buscar do backend.
// Guards: só TSE, só respostas pequenas (<120KB serializado), try/catch
// pra nunca quebrar em quota cheia / modo privado.
const SS_PREFIX = "mn:apicache:";
const SS_MAX_BYTES = 120 * 1024;

function ssGet(key: string): Entry | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const raw = window.sessionStorage.getItem(SS_PREFIX + key);
    if (!raw) return undefined;
    const e = JSON.parse(raw) as Entry;
    if (Date.now() > e.expires) {
      window.sessionStorage.removeItem(SS_PREFIX + key);
      return undefined;
    }
    return e;
  } catch {
    return undefined;
  }
}

function ssSet(key: string, entry: Entry): void {
  if (typeof window === "undefined") return;
  // Só persiste TSE (imutável). Dados de tenant ficam só em memória.
  if (!key.startsWith("/v1/tse/")) return;
  try {
    const raw = JSON.stringify(entry);
    if (raw.length > SS_MAX_BYTES) return; // grande demais (ex: winners-map)
    window.sessionStorage.setItem(SS_PREFIX + key, raw);
  } catch {
    // QuotaExceeded / modo privado: limpa o namespace e desiste silenciosamente.
    try {
      for (let i = window.sessionStorage.length - 1; i >= 0; i--) {
        const k = window.sessionStorage.key(i);
        if (k && k.startsWith(SS_PREFIX)) window.sessionStorage.removeItem(k);
      }
    } catch {
      /* ignore */
    }
  }
}

export function getCached(key: string): unknown | undefined {
  const e = memCache.get(key);
  if (e) {
    if (Date.now() > e.expires) {
      memCache.delete(key);
      return undefined;
    }
    return e.data;
  }
  // Miss em memória: tenta sessionStorage (sobrevive a reload).
  const ss = ssGet(key);
  if (ss) {
    memCache.set(key, ss); // re-hidrata o memCache
    return ss.data;
  }
  return undefined;
}

export function setCached(key: string, data: unknown, ttlMs: number): void {
  // Teto defensivo: não deixa o cache crescer infinito (LRU simplão).
  if (memCache.size > 200) {
    const oldest = memCache.keys().next().value;
    if (oldest) memCache.delete(oldest);
  }
  const entry: Entry = { data, expires: Date.now() + ttlMs };
  memCache.set(key, entry);
  ssSet(key, entry);
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
  // Limpa tambem o sessionStorage (consistencia; relevante se algum dia
  // um recurso persistido for invalidado).
  if (typeof window !== "undefined") {
    try {
      for (let i = window.sessionStorage.length - 1; i >= 0; i--) {
        const k = window.sessionStorage.key(i);
        if (!k || !k.startsWith(SS_PREFIX)) continue;
        const bare = k.slice(SS_PREFIX.length);
        if (prefixes.some((p) => bare.startsWith(p))) {
          window.sessionStorage.removeItem(k);
        }
      }
    } catch {
      /* ignore */
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
