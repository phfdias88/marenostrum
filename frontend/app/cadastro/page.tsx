"use client";

/**
 * /cadastro — área RESTRITA da liderança (role=volunteer).
 *
 * A liderança faz login e cai aqui: uma tela enxuta com APENAS o formulário de
 * cadastro de contato. Sem dashboard, sem dados do TSE/censo, sem mapas, sem
 * listas. O backend reforça isso (middleware default-deny) — o token de
 * liderança só consegue criar contato + as buscas que o formulário precisa.
 *
 * Os demais papéis (owner/coordenador/equipe) usam /dashboard normalmente; se
 * algum deles abrir esta URL, funciona igual (é só um atalho de cadastro).
 */
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CheckCircle2, LogOut, Plus, UserPlus } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { clearAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { ContactFormDialog } from "@/components/contacts/ContactFormDialog";

type Me = { full_name: string; tenant_name: string; role?: string };

export default function CadastroPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [count, setCount] = useState(0);

  useEffect(() => {
    api<Me>("/v1/auth/me")
      .then(setMe)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearAuth();
          router.replace("/login");
        }
      });
  }, [router]);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  const firstName = me?.full_name?.trim().split(/\s+/)[0] ?? "";

  return (
    <main
      className="min-h-[100dvh] relative overflow-hidden flex flex-col"
      style={{
        paddingTop: "max(env(safe-area-inset-top), 0px)",
        paddingBottom: "max(env(safe-area-inset-bottom), 0px)",
      }}
    >
      {/* Fundo com gradiente + glow (mesma identidade do login) */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-br from-background via-background to-primary/5" />
      <div className="absolute -top-40 -right-40 -z-10 w-96 h-96 rounded-full bg-primary/10 blur-3xl" />
      <div className="absolute -bottom-40 -left-40 -z-10 w-96 h-96 rounded-full bg-blue-500/10 blur-3xl" />

      {/* Topo: marca + sair */}
      <header className="flex items-center justify-between px-4 sm:px-6 h-14 border-b border-border/60 bg-card/40 backdrop-blur">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/logo-wordmark.png"
          alt="MareNostrum"
          className="h-7 w-auto object-contain hidden dark:block"
        />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/logo-wordmark-light.png"
          alt="MareNostrum"
          className="h-7 w-auto object-contain dark:hidden"
        />
        <Button variant="ghost" size="sm" onClick={logout} className="gap-1.5">
          <LogOut className="w-4 h-4" /> Sair
        </Button>
      </header>

      {/* Conteúdo */}
      <div className="flex-1 grid place-items-center px-4 py-8">
        <div className="w-full max-w-md">
          <div className="bg-card/85 backdrop-blur rounded-2xl shadow-xl border border-border p-6 sm:p-8 text-center">
            <div className="mx-auto w-14 h-14 rounded-2xl bg-primary/10 grid place-items-center mb-4">
              <UserPlus className="w-7 h-7 text-primary" />
            </div>

            <h1 className="text-xl font-semibold">
              {firstName ? `Olá, ${firstName}!` : "Cadastro de contatos"}
            </h1>
            {me?.tenant_name && (
              <p className="text-sm text-muted-foreground mt-1">{me.tenant_name}</p>
            )}
            <p className="text-sm text-muted-foreground mt-3">
              Cadastre os contatos da campanha. Toque no botão abaixo, preencha
              os dados e salve — pode cadastrar quantos quiser.
            </p>

            <div className="mt-6">
              <ContactFormDialog
                mode="create"
                onSaved={() => setCount((c) => c + 1)}
              >
                <Button size="lg" className="w-full gap-2 min-h-[52px] text-base">
                  <Plus className="w-5 h-5" /> Novo contato
                </Button>
              </ContactFormDialog>
            </div>

            {count > 0 && (
              <p className="mt-5 text-sm text-emerald-500 flex items-center justify-center gap-1.5">
                <CheckCircle2 className="w-4 h-4" />
                {count} {count === 1 ? "contato cadastrado" : "contatos cadastrados"} nesta sessão
              </p>
            )}
          </div>

          <p className="text-center text-xs text-muted-foreground mt-4">
            Acesso de liderança — você só tem acesso ao cadastro de contatos.
          </p>
        </div>
      </div>
    </main>
  );
}
