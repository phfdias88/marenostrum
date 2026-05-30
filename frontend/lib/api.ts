/**
 * Wrapper de fetch da API MareNostrum.
 * - injeta Authorization: Bearer <token>
 * - JSON body por padrao; FormData passa raw (browser cuida do multipart boundary)
 * - converte erros do backend em ApiError com {status, code, message}
 */
import { getToken } from "./auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

type RequestOpts = Omit<RequestInit, "body"> & { body?: unknown };

export async function api<T>(path: string, opts: RequestOpts = {}): Promise<T> {
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

  // Cache strategy:
  // - GET em /v1/tse/* (dados publicos historicos): "default" → respeita
  //   Cache-Control do backend (max-age=3600 + stale-while-revalidate=86400).
  //   Navegacoes repetidas viram instant (sem round-trip).
  // - Resto (POST/PUT/DELETE ou GETs de tenant): "no-store" → sempre fresco.
  const method = (opts.method ?? "GET").toUpperCase();
  const isTseRead = method === "GET" && path.startsWith("/v1/tse/");
  const cacheMode: RequestCache = isTseRead ? "default" : "no-store";

  const res = await fetch(`${BASE_URL}${path}`, {
    ...opts,
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
