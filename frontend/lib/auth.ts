/**
 * Armazenamento do token JWT no browser.
 * Decisao: cookie (nao localStorage) para que o `middleware.ts`
 * possa proteger rotas no Edge antes mesmo do React montar.
 *
 * Em producao, considere ler do servidor (cookie httpOnly) - aqui mantemos
 * leitura no client para simplificar a Fase 2.
 */

const COOKIE_NAME = "mn_token";

// Path do cookie casa com o basePath: na raiz vira "/"; sob subpath vira
// "/sistema" — assim o token NAO vaza pro site principal do domínio
// compartilhado e AINDA chega ao middleware (a request /sistema/dashboard
// casa o Path). Mesmo var do next.config (basePath).
const COOKIE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "/";

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
  )}; Path=${COOKIE_PATH}; Max-Age=${maxAge}; SameSite=Lax${_secureFlag()}`;
}

/**
 * Sessão deslizante: troca só o cookie do token (sem mexer no resto).
 * Usado quando /auth/me devolve um token renovado.
 */
export function refreshTokenCookie(token: string, expiresIn: number): void {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(token)}; Path=${COOKIE_PATH}; Max-Age=${Math.max(60, expiresIn)}; SameSite=Lax${_secureFlag()}`;
}

export function getToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE_NAME}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// ------------------------------------------------ Acesso Mare Nostrum
// Ao "entrar como" um cliente, guardamos a sessão REAL do superadmin aqui e
// trocamos o cookie pelo token da visita. Sair = restaurar o que estava.
const IMP_BACKUP_KEY = "mn_imp_backup";
const IMP_TENANT_KEY = "mn_imp_tenant";

export function startImpersonation(
  token: string,
  expiresIn: number,
  tenantName: string,
): void {
  try {
    const current = getToken();
    if (current) sessionStorage.setItem(IMP_BACKUP_KEY, current);
    sessionStorage.setItem(IMP_TENANT_KEY, tenantName);
  } catch {
    /* sessionStorage indisponível — segue sem backup */
  }
  refreshTokenCookie(token, expiresIn);
}

/** Nome do cliente visitado (null = não está em visita). */
export function impersonatedTenantName(): string | null {
  try {
    return sessionStorage.getItem(IMP_TENANT_KEY);
  } catch {
    return null;
  }
}

/** Volta pra sessão do superadmin. `false` se não havia backup. */
export function stopImpersonation(): boolean {
  try {
    const prev = sessionStorage.getItem(IMP_BACKUP_KEY);
    sessionStorage.removeItem(IMP_BACKUP_KEY);
    sessionStorage.removeItem(IMP_TENANT_KEY);
    if (!prev) return false;
    // 7 dias: o token do superadmin tem a validade original dele.
    refreshTokenCookie(prev, 7 * 24 * 3600);
    return true;
  } catch {
    return false;
  }
}

export function clearAuth(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE_NAME}=; Path=${COOKIE_PATH}; Max-Age=0; SameSite=Lax`;
}
