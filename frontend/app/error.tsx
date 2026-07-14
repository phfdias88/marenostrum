"use client";

/**
 * Error boundary global (App Router). Captura erros de render/runtime dos
 * segmentos abaixo do layout raiz e oferece retry via reset(), no mesmo
 * palco visual do login/404 (glows dourados da marca).
 */
import { useEffect } from "react";
import Link from "next/link";
import { LayoutDashboard, RotateCcw } from "lucide-react";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log pro console — o usuário só vê a tela amigável abaixo.
    console.error(error);
  }, [error]);

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
        <h1 className="mt-6 text-2xl sm:text-3xl font-bold text-foreground">
          Algo deu errado
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Falha inesperada ao carregar esta tela. Tente de novo. Se o problema
          persistir, volte ao painel.
        </p>
        <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
          <Button
            size="lg"
            className="rounded-lg min-h-[44px]"
            onClick={() => reset()}
          >
            <RotateCcw aria-hidden="true" />
            Tentar de novo
          </Button>
          <Link
            href="/dashboard"
            className={cn(
              buttonVariants({ variant: "outline", size: "lg" }),
              "rounded-lg min-h-[44px]",
            )}
          >
            <LayoutDashboard aria-hidden="true" />
            Voltar ao painel
          </Link>
        </div>
      </div>
    </main>
  );
}
