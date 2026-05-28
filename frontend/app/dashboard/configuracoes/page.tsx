"use client";

/**
 * Configurações — por enquanto só "Mudar senha".
 * Outras seções podem ser adicionadas no mesmo layout.
 */
import { ArrowLeft, Check, KeyRound, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function SettingsPage() {
  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Visão geral
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-bold">Configurações</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Sua conta e preferências de acesso.
        </p>
      </header>

      <ChangePasswordCard />
    </div>
  );
}

function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);

  const canSubmit =
    current.length > 0 && next.length >= 8 && next === confirm && !saving;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    try {
      await api<null>("/v1/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      toast.success("Senha atualizada!", {
        description: "Use a nova senha no próximo login.",
      });
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "Erro ao atualizar senha.";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  const mismatch = confirm.length > 0 && next !== confirm;
  const tooShort = next.length > 0 && next.length < 8;

  return (
    <section className="rounded-xl border bg-card p-6">
      <div className="flex items-center gap-3 mb-5">
        <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
          <KeyRound className="w-5 h-5" />
        </span>
        <div>
          <h2 className="font-semibold">Mudar senha</h2>
          <p className="text-xs text-muted-foreground">
            Mínimo 8 caracteres. A senha atual é obrigatória.
          </p>
        </div>
      </div>

      <form onSubmit={submit} className="space-y-4">
        <Field
          label="Senha atual"
          value={current}
          onChange={setCurrent}
          autoComplete="current-password"
        />
        <Field
          label="Nova senha"
          value={next}
          onChange={setNext}
          autoComplete="new-password"
          hint={tooShort ? "Use no mínimo 8 caracteres." : undefined}
        />
        <Field
          label="Confirmar nova senha"
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
          hint={mismatch ? "Não confere com a nova senha." : undefined}
          trailing={
            confirm.length > 0 && next === confirm ? (
              <Check className="w-4 h-4 text-emerald-400" />
            ) : undefined
          }
        />

        <div className="pt-2 flex items-center gap-3">
          <Button type="submit" disabled={!canSubmit}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
          </Button>
          <p className="text-xs text-muted-foreground">
            A sessão atual continua válida até expirar (7 dias).
          </p>
        </div>
      </form>
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  autoComplete,
  hint,
  trailing,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  hint?: string;
  trailing?: React.ReactNode;
}) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      <div className="relative mt-1">
        <input
          type="password"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          className="w-full py-2 pl-3 pr-9 rounded-md bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
        {trailing && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2">
            {trailing}
          </span>
        )}
      </div>
      {hint && <p className="text-[11px] text-amber-300/80 mt-1">{hint}</p>}
    </div>
  );
}
