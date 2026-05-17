/**
 * Wrapper de fetch da API MareNostrum.
 * - injeta Authorization: Bearer <token>
 * - converte erros em ApiError com status e mensagem do backend
 * - usa NEXT_PUBLIC_API_URL (definido em .env)
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
  headers.set("Content-Type", "application/json");

  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE_URL}${path}`, {
    ...opts,
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });

  if (!res.ok) {
    // Tenta extrair {code, message} do handler do backend
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

  // 204 No Content
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
