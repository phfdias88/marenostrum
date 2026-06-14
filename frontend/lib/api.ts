/**
 * Wrapper de fetch da API MareNostrum.
 * - injeta Authorization: Bearer <token>
 * - JSON body por padrao; FormData passa raw (browser cuida do multipart boundary)
 * - converte erros do backend em ApiError com {status, code, message}
 */
import { getToken } from "./auth";
import {
  bustCache,
  bustPrefixesFor,
  clearInflight,
  getCached,
  getInflight,
  setCached,
  setInflight,
  ttlFor,
} from "./apiCache";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

type RequestOpts = Omit<RequestInit, "body"> & { body?: unknown };

/**
 * Opções extras de cache (além de RequestInit):
 *  - skipCache: força ir à rede (ex: refresh manual / pull-to-refresh)
 */
type ApiOpts = RequestOpts & { skipCache?: boolean };

export async function api<T>(path: string, opts: ApiOpts = {}): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();

  // --- Camada de cache (só GET) -------------------------------------------
  // Memory cache + in-flight dedupe → navegação back/forward instantânea.
  if (method === "GET" && !opts.skipCache) {
    const cached = getCached(path);
    if (cached !== undefined) return cached as T;

    const pending = getInflight(path);
    if (pending) return pending as Promise<T>;

    const p = _doFetch<T>(path, opts, method)
      .then((data) => {
        setCached(path, data, ttlFor(path));
        return data;
      })
      .finally(() => clearInflight(path));

    setInflight(path, p);
    return p;
  }

  // Mutações: invalida o cache do recurso afetado (lista + detalhe ficam
  // frescos no próximo GET) e vai direto à rede.
  if (method !== "GET") {
    const result = await _doFetch<T>(path, opts, method);
    bustCache(bustPrefixesFor(path));
    return result;
  }

  // GET com skipCache: rede direta, mas atualiza o cache pra próximos.
  const data = await _doFetch<T>(path, opts, method);
  setCached(path, data, ttlFor(path));
  return data;
}

async function _doFetch<T>(
  path: string,
  opts: ApiOpts,
  method: string,
): Promise<T> {
  const headers = new Headers(opts.headers);

  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  // FormData/Blob: NAO setar Content-Type — o browser inclui o boundary correto.
  // JSON: serializar e definir o header.
  let body: BodyInit | undefined;
  if (opts.body === undefined) {
    body = undefined;
  } else if (opts.body instanceof FormData || opts.body instanceof Blob) {
    body = opts.body;
  } else {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.body);
  }

  // Cache strategy (HTTP/browser layer):
  // - GET em /v1/tse/* (dados publicos historicos): "default" → respeita
  //   Cache-Control do backend (max-age + stale-while-revalidate).
  // - Resto (POST/PUT/DELETE ou GETs de tenant): "no-store" → sempre fresco.
  // Dados públicos/estáticos (TSE histórico, Censo IBGE): respeitam o
  // Cache-Control do backend → re-carregar fica instantâneo.
  const isPublicRead =
    method === "GET" &&
    (path.startsWith("/v1/tse/") || path.startsWith("/v1/census/"));
  const cacheMode: RequestCache = isPublicRead ? "default" : "no-store";

  // Remove chaves nao-padrao do RequestInit antes de passar ao fetch.
  const { skipCache: _sk, body: _b, ...rest } = opts;

  const res = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers,
    body,
    cache: cacheMode,
  });

  if (!res.ok) {
    let code = "http_error";
    let message = res.statusText;
    try {
      const data = await res.json();
      code = data.code ?? code;
      message = data.message ?? message;
    } catch {
      /* nao-json */
    }
    throw new ApiError(res.status, code, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
