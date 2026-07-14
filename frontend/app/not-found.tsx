import type { Metadata } from "next";
import Link from "next/link";
import { LayoutDashboard } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Página não encontrada" };

/**
 * 404 global (App Router). Mesmo palco visual do login (glows dourados
 * sobre o fundo da marca) pra rota quebrada não parecer "outro site".
 */
export default function NotFound() {
  return (
    <main className="min-h-[100dvh] grid place-items-center px-4 py-6 relative overflow-hidden bg-background">
      {/* Fundo com gradiente + glow — mesmo padrão do login */}
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-primary/5" />
      <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-primary/10 blur-3xl" />
      <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full bg-primary/10 blur-3xl" />

      <div className="relative w-full max-w-md text-center mn-fade-in">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/logo-mark.png`}
          alt="MareNostrum"
          className="mx-auto h-16 w-16 object-contain"
        />
        <p className="mt-6 text-xs font-semibold tracking-[0.2em] text-primary">
          ERRO 404
        </p>
        <h1 className="mt-2 text-2xl sm:text-3xl font-bold text-foreground">
          Página não encontrada
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">
          O endereço pode ter mudado ou nunca existiu. Volte ao painel pra
          continuar de onde parou.
        </p>
        <div className="mt-8 flex justify-center">
          <Link
            href="/dashboard"
            className={cn(buttonVariants({ size: "lg" }), "rounded-lg min-h-[44px]")}
          >
            <LayoutDashboard aria-hidden="true" />
            Voltar ao painel
          </Link>
        </div>
      </div>
    </main>
  );
}
