/**
 * Armazenamento do token JWT no browser.
 * Decisao: cookie (nao localStorage) para que o `middleware.ts`
 * possa proteger rotas no Edge antes mesmo do React montar.
 *
 * Em producao, considere ler do servidor (cookie httpOnly) - aqui mantemos
 * leitura no client para simplificar a Fase 2.
 */

const COOKIE_NAME = "mn_token";

export type AuthData = {
  access_token: string;
  user_id: string;
  tenant_id: string;
  role: string;
  expires_in: number;
};

// Secure só em HTTPS (produção) — em dev local http o cookie seria
// silenciosamente descartado pelo browser se levasse a flag.
function _secureFlag(): string {
  return typeof location !== "undefined" && location.protocol === "https:"
    ? "; Secure"
    : "";
}

export function saveAuth(data: AuthData): void {
  if (typeof document === "undefined") return;
  const maxAge = Math.max(60, data.expires_in);
  // SameSite=Lax mitiga CSRF basico; Secure impede vazar o token em
  // requisições http acidentais.
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(
    data.access_token,
  )}; Path=/; Max-Age=${maxAge}; SameSite=Lax${_secureFlag()}`;
}

/**
 * Sessão deslizante: troca só o cookie do token (sem mexer no resto).
 * Usado quando /auth/me devolve um token renovado.
 */
export function refreshTokenCookie(token: string, expiresIn: number): void {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(token)}; Path=/; Max-Age=${Math.max(60, expiresIn)}; SameSite=Lax${_secureFlag()}`;
}

export function getToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE_NAME}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function clearAuth(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE_NAME}=; Path=/; Max-Age=0; SameSite=Lax`;
}
