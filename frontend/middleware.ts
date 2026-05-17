/**
 * Middleware Edge: protege rotas /contatos (e futuras) checando
 * a presenca do cookie mn_token. NAO valida assinatura - so se existe.
 * A validacao real (assinatura, expiracao, tenant) e do backend.
 */
import { NextResponse, type NextRequest } from "next/server";

const PROTECTED_PATHS = ["/dashboard", "/contatos"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const isProtected = PROTECTED_PATHS.some((p) => pathname.startsWith(p));

  if (!isProtected) return NextResponse.next();

  const token = req.cookies.get("mn_token")?.value;
  if (!token) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Aplica apenas onde for necessario (perf no Edge)
  matcher: ["/dashboard/:path*", "/contatos/:path*"],
};
