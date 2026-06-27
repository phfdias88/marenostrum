/**
 * Middleware Edge: protege rotas /dashboard/* checando presenca do
 * cookie mn_token. NAO valida assinatura — apenas existencia.
 * A validacao real (assinatura, expiracao, tenant) e do backend.
 */
import { NextResponse, type NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const token = req.cookies.get("mn_token")?.value;
  if (!token) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", req.nextUrl.pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Tudo sob /dashboard exige autenticacao (inclui /contacts, /map, etc.).
  // /cadastro é a área restrita da liderança (só o formulário) — também exige
  // login.
  matcher: ["/dashboard/:path*", "/cadastro/:path*"],
};
