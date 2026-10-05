"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2, MessageCircle } from "lucide-react";

import { api } from "@/lib/api";
import { clearAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";

type BillingMe = {
  status: string;
  plan: string | null;
  current_period_end: string | null;
  invoice_url: string | null;
};

const _WHATS =
  "https://wa.me/5521990405321?text=" +
  encodeURIComponent("Olá, quero regularizar minha assinatura do MareNostrum.");

// Tela de bloqueio por assinatura. O tenant cai aqui quando o backend devolve
// 402 (assinatura suspensa/cancelada). /billing/me é isento do gate, então
// carrega normalmente pra mostrar o status. Fora do /dashboard de propósito —
// não dispara as chamadas gateadas do layout (evita loop).
export default function AssinaturaPage() {
  const router = useRouter();
  const [me, setMe] = useState<BillingMe | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<BillingMe>("/v1/billing/me")
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
  }, []);

  function sair() {
    clearAuth();
    router.push("/login");
  }

  const isActive = me?.status === "active";

  return (
    <main className="min-h-[100dvh] grid place-items-center px-4 py-6 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-primary/5" />
      <div className="relative w-full max-w-md mn-glass rounded-2xl p-6 sm:p-8 text-center space-y-4">
        {loading ? (
          <div className="py-8 grid place-items-center">
            <Loader2 className="animate-spin text-muted-foreground" />
          </div>
        ) : isActive ? (
          <>
            <h1 className="text-xl font-bold">Sua assinatura está ativa</h1>
            <p className="text-sm text-muted-foreground">Você já pode usar o sistema.</p>
            <Button onClick={() => router.push("/dashboard")} className="w-full min-h-[48px]">
              Ir para o painel
            </Button>
          </>
        ) : (
          <>
            <div className="mx-auto w-12 h-12 rounded-full bg-amber-500/15 grid place-items-center">
              <AlertTriangle className="text-amber-500" />
            </div>
            <h1 className="text-xl font-bold">Assinatura inativa</h1>
            <p className="text-sm text-muted-foreground">
              {me?.status === "canceled"
                ? "Sua assinatura foi cancelada."
                : "Encontramos uma pendência no pagamento da sua assinatura."}{" "}
              Regularize para voltar a acessar o B.I. Eleitoral Completo.
            </p>
            <Button asChild className="w-full min-h-[48px]">
              <a href={_WHATS} target="_blank" rel="noopener noreferrer">
                <MessageCircle className="w-4 h-4" /> Falar com a equipe
              </a>
            </Button>
            <button
              onClick={sair}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Sair
            </button>
          </>
        )}
      </div>
    </main>
  );
}
