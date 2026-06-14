"use client";

/**
 * Configuracoes — perfil + equipe da campanha.
 *
 * - Cartao "Mudar senha": qualquer usuario.
 * - Cartao "Equipe" (so owner): listar membros, convidar novo membro
 *   (senha temporaria gerada pelo servidor), resetar senha, desativar.
 */
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Copy,
  KeyRound,
  Layers,
  Loader2,
  Plus,
  Power,
  RefreshCcw,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

type Me = { user_id: string; role: string; tenant_name: string };

type TeamUser = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  census_enabled?: boolean;
  created_at: string;
};

type CreatedUser = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  temp_password: string;
};

const ROLE_LABELS: Record<string, string> = {
  owner: "Candidato / Dono",
  manager: "Coordenador",
  staff: "Equipe",
  volunteer: "Voluntário",
};

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("/v1/auth/me").then(setMe).catch(() => setMe(null));
  }, []);

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Visão geral
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-bold">Configurações</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Sua conta e equipe da campanha.
        </p>
      </header>

      <div className="space-y-6">
        <ChangePasswordCard />
        {me?.role === "owner" && <TeamCard />}
      </div>
    </div>
  );
}

// ============================================================ change password

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

// ============================================================ team

function TeamCard() {
  const [users, setUsers] = useState<TeamUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [created, setCreated] = useState<CreatedUser | null>(null);

  function load() {
    setLoading(true);
    api<TeamUser[]>("/v1/auth/users")
      .then(setUsers)
      .catch(() => setUsers([]))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    load();
  }, []);

  return (
    <section className="rounded-xl border bg-card p-6">
      <div className="flex items-start justify-between gap-3 mb-5">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
            <Users className="w-5 h-5" />
          </span>
          <div>
            <h2 className="font-semibold">Equipe da campanha</h2>
            <p className="text-xs text-muted-foreground">
              Crie contas pra coordenadores, equipe e voluntários.
            </p>
          </div>
        </div>
        {!showForm && !created && (
          <Button size="sm" onClick={() => setShowForm(true)}>
            <UserPlus className="w-4 h-4" /> Convidar
          </Button>
        )}
      </div>

      {/* Form criar */}
      {showForm && !created && (
        <InviteForm
          onCancel={() => setShowForm(false)}
          onCreated={(u) => {
            setCreated(u);
            setShowForm(false);
            load();
          }}
        />
      )}

      {/* Senha temporaria — mostrada UMA vez */}
      {created && (
        <TempPasswordCard
          user={created}
          onDone={() => setCreated(null)}
        />
      )}

      {/* Lista de membros */}
      <div className="mt-4 rounded-lg border bg-background/30 divide-y divide-border">
        {loading && (
          <div className="p-4 text-sm text-muted-foreground flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Carregando equipe…
          </div>
        )}
        {!loading && users.length === 0 && (
          <div className="p-6 text-center text-sm text-muted-foreground">
            Nenhum membro além de você ainda. Clique em <strong>Convidar</strong>.
          </div>
        )}
        {users.map((u) => (
          <UserRow key={u.id} user={u} onChanged={load} onReset={setCreated} />
        ))}
      </div>
    </section>
  );
}

function InviteForm({
  onCancel,
  onCreated,
}: {
  onCancel: () => void;
  onCreated: (u: CreatedUser) => void;
}) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<"manager" | "staff" | "volunteer">("staff");
  const [saving, setSaving] = useState(false);

  const canSubmit =
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) &&
    fullName.trim().length >= 2 &&
    !saving;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    try {
      const u = await api<CreatedUser>("/v1/auth/users", {
        method: "POST",
        body: { email: email.trim().toLowerCase(), full_name: fullName.trim(), role },
      });
      onCreated(u);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Erro ao criar usuário.";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-3 mb-4"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-muted-foreground">
            Nome completo
          </label>
          <input
            autoFocus
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Maria Souza"
            className="w-full mt-1 py-2 px-3 rounded-md bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-muted-foreground">
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="maria@campanha.com.br"
            className="w-full mt-1 py-2 px-3 rounded-md bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-muted-foreground">
          Papel
        </label>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as typeof role)}
          className="w-full mt-1 py-2 px-3 rounded-md bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
        >
          <option value="manager">Coordenador (acesso amplo)</option>
          <option value="staff">Equipe (padrão)</option>
          <option value="volunteer">Voluntário (acesso limitado)</option>
        </select>
      </div>
      <div className="flex items-center gap-2 pt-2">
        <Button type="submit" disabled={!canSubmit}>
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Criar usuário
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

function TempPasswordCard({
  user,
  onDone,
}: {
  user: CreatedUser;
  onDone: () => void;
}) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(user.temp_password);
    setCopied(true);
    toast.success("Senha copiada.");
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-4 mb-4">
      <div className="flex items-start gap-3">
        <span className="grid place-items-center w-9 h-9 rounded-lg bg-emerald-500/20 text-emerald-400 shrink-0">
          <ShieldCheck className="w-5 h-5" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-semibold">
            Senha temporária pra <span className="text-emerald-400">{user.full_name}</span>
          </p>
          <p className="text-xs text-muted-foreground">
            Mostrada <strong>uma única vez</strong>. Copie e envie pra pessoa por canal
            seguro. Ela troca no primeiro login em Configurações.
          </p>

          <div className="mt-3 flex items-center gap-2">
            <code className="flex-1 px-3 py-2 rounded-md bg-background border border-border font-mono text-sm tabular-nums tracking-wider select-all">
              {user.temp_password}
            </code>
            <Button onClick={copy} size="sm" variant="outline">
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              {copied ? "Copiado" : "Copiar"}
            </Button>
          </div>

          <div className="mt-3 flex items-start gap-2 text-xs text-amber-300/80">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <span>
              Login: <strong>{user.email}</strong>. Recomende usar 1Password,
              Bitwarden ou similar. Após fechar este aviso, não tem como
              recuperar — só gerar nova.
            </span>
          </div>

          <div className="mt-3">
            <Button onClick={onDone} variant="ghost" size="sm">
              Já anotei, fechar
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function UserRow({
  user,
  onChanged,
  onReset,
}: {
  user: TeamUser;
  onChanged: () => void;
  onReset: (u: CreatedUser) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function resetPassword() {
    if (busy) return;
    if (!confirm(`Gerar nova senha temporária pra ${user.full_name}?`)) return;
    setBusy(true);
    try {
      const u = await api<CreatedUser>(
        `/v1/auth/users/${user.id}/reset-password`,
        { method: "POST" },
      );
      onReset(u);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao resetar.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive() {
    if (busy) return;
    const action = user.is_active ? "deactivate" : "reactivate";
    if (user.is_active && !confirm(`Desativar ${user.full_name}? Perde acesso ao sistema.`))
      return;
    setBusy(true);
    try {
      await api<null>(`/v1/auth/users/${user.id}/${action}`, { method: "POST" });
      toast.success(user.is_active ? "Usuário desativado." : "Usuário reativado.");
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleCensus() {
    if (busy) return;
    setBusy(true);
    try {
      await api<null>(`/v1/auth/users/${user.id}/census`, {
        method: "POST",
        body: { enabled: !user.census_enabled },
      });
      toast.success(user.census_enabled ? "Censo bloqueado." : "Censo liberado.");
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="px-4 py-3 flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate flex items-center gap-2">
          <span className="truncate">{user.full_name}</span>
          {!user.is_active && (
            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
              desativado
            </span>
          )}
        </p>
        <p className="text-xs text-muted-foreground truncate">
          {user.email} · {ROLE_LABELS[user.role] ?? user.role}
        </p>
      </div>

      {/* Liberação do módulo Censo (IBGE) — vale pra qualquer membro, inclusive o owner */}
      <button
        onClick={toggleCensus}
        disabled={busy}
        title={user.census_enabled ? "Censo liberado — clique para bloquear" : "Liberar o módulo Censo para este usuário"}
        className={
          "shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs transition-colors disabled:opacity-50 " +
          (user.census_enabled
            ? "border-primary bg-primary/15 text-primary font-semibold"
            : "border-border text-muted-foreground hover:border-primary/50")
        }
      >
        <Layers className="w-3.5 h-3.5" />
        Censo {user.census_enabled ? "✓" : ""}
      </button>

      {user.role !== "owner" && (
        <div className="flex items-center gap-1">
          <button
            onClick={resetPassword}
            disabled={busy}
            title="Resetar senha"
            className="p-1.5 rounded text-muted-foreground hover:text-primary hover:bg-accent/50 transition-colors disabled:opacity-50"
          >
            <RefreshCcw className="w-4 h-4" />
          </button>
          <button
            onClick={toggleActive}
            disabled={busy}
            title={user.is_active ? "Desativar" : "Reativar"}
            className={
              "p-1.5 rounded hover:bg-accent/50 transition-colors disabled:opacity-50 " +
              (user.is_active
                ? "text-muted-foreground hover:text-rose-400"
                : "text-emerald-400 hover:text-emerald-300")
            }
          >
            {user.is_active ? <Power className="w-4 h-4" /> : <Check className="w-4 h-4" />}
          </button>
        </div>
      )}
    </div>
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
