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
  History,
  KeyRound,
  Layers,
  Loader2,
  Plus,
  Power,
  RefreshCcw,
  ShieldCheck,
  Trash2,
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
  analytics_enabled?: boolean;
  panel_enabled?: boolean;
  map_enabled?: boolean;
  demands_enabled?: boolean;
  agenda_enabled?: boolean;
  created_at: string;
};

// Áreas configuráveis pelo owner por usuário. `area` bate com o backend
// (/users/{id}/access), `flag` é a chave no TeamUser.
const ACCESS_AREAS: { area: string; flag: keyof TeamUser; label: string }[] = [
  { area: "analytics", flag: "analytics_enabled", label: "Análises" },
  { area: "panel", flag: "panel_enabled", label: "Painel" },
  { area: "map", flag: "map_enabled", label: "Mapa" },
  { area: "demands", flag: "demands_enabled", label: "Demandas" },
  { area: "agenda", flag: "agenda_enabled", label: "Agenda" },
  { area: "census", flag: "census_enabled", label: "Censo" },
];

type CreatedUser = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  temp_password: string;
};

const ROLE_LABELS: Record<string, string> = {
  owner: "Administrador (Dono)",
  manager: "Coordenador",
  staff: "Equipe",
  volunteer: "Liderança (só formulário)",
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
        {/* Dono/Coordenador/Equipe gerenciam equipe. Coordenador e Equipe só
            cadastram LIDERANÇA (volunteer); o Dono cria qualquer papel. */}
        {me && me.role !== "volunteer" && (
          <TeamCard isOwner={me.role === "owner"} meId={me.user_id} />
        )}
        {/* Trilha de auditoria — só o Administrador (Dono) vê. */}
        {me && me.role === "owner" && <AuditCard />}
      </div>
    </div>
  );
}

// ============================================================ auditoria

type AuditItem = {
  id: string;
  user_name: string | null;
  user_role: string | null;
  action: string;
  entity_type: string;
  summary: string | null;
  created_at: string;
};

const ACTION_LABEL: Record<string, string> = {
  create: "Cadastro",
  update: "Edição",
  delete: "Exclusão",
};
const ACTION_STYLE: Record<string, string> = {
  create: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  update: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  delete: "bg-rose-500/10 text-rose-700 dark:text-rose-400",
};

function AuditCard() {
  const [items, setItems] = useState<AuditItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [entity, setEntity] = useState<string>("");
  const [action, setAction] = useState<string>("");

  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams({ limit: "50" });
    if (entity) p.set("entity_type", entity);
    if (action) p.set("action", action);
    api<{ items: AuditItem[]; total: number }>(`/v1/audit?${p.toString()}`)
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
      })
      .catch(() => {
        setItems([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [entity, action]);

  return (
    <section className="rounded-xl border bg-card p-6">
      <div className="flex items-start justify-between gap-3 mb-1">
        <div className="flex items-center gap-2">
          <History className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold">Auditoria</h2>
        </div>
        <span className="text-xs text-muted-foreground tabular-nums">
          {total.toLocaleString("pt-BR")} registro(s)
        </span>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        Quem cadastrou, editou ou excluiu o quê — pra rastrear qualquer alteração
        na campanha.
      </p>

      <div className="flex flex-wrap gap-2 mb-3">
        <select
          value={entity}
          onChange={(e) => setEntity(e.target.value)}
          className="px-2 py-1.5 rounded-md border border-border bg-background text-sm"
        >
          <option value="">Tudo</option>
          <option value="contact">Contatos</option>
          <option value="user">Usuários</option>
        </select>
        <select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="px-2 py-1.5 rounded-md border border-border bg-background text-sm"
        >
          <option value="">Todas as ações</option>
          <option value="create">Cadastro</option>
          <option value="update">Edição</option>
          <option value="delete">Exclusão</option>
        </select>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground inline-flex items-center gap-2 py-4">
          <Loader2 className="w-4 h-4 animate-spin" /> Carregando trilha…
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4">
          Nenhuma ação registrada ainda. Conforme a equipe cadastra e edita, tudo
          aparece aqui.
        </p>
      ) : (
        <ul className="divide-y divide-border max-h-[28rem] overflow-auto -mx-2">
          {items.map((it) => (
            <li key={it.id} className="px-2 py-2.5 flex items-start gap-3">
              <span
                className={`shrink-0 mt-0.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${
                  ACTION_STYLE[it.action] ?? "bg-muted text-muted-foreground"
                }`}
              >
                {ACTION_LABEL[it.action] ?? it.action}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm">{it.summary ?? `${it.action} ${it.entity_type}`}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  <strong className="text-foreground">{it.user_name ?? "—"}</strong>
                  {it.user_role ? ` · ${it.user_role}` : ""} ·{" "}
                  {new Date(it.created_at).toLocaleString("pt-BR", {
                    day: "2-digit",
                    month: "2-digit",
                    year: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
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

function TeamCard({ isOwner, meId }: { isOwner: boolean; meId: string }) {
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
            <h2 className="font-semibold">
              {isOwner ? "Equipe da campanha" : "Lideranças"}
            </h2>
            <p className="text-xs text-muted-foreground">
              {isOwner
                ? "Crie contas pra coordenadores, equipe e lideranças."
                : "Crie logins de liderança — acesso só ao formulário de cadastro."}
            </p>
          </div>
        </div>
        {!showForm && !created && (
          <Button size="sm" onClick={() => setShowForm(true)}>
            <UserPlus className="w-4 h-4" />{" "}
            {isOwner ? "Convidar" : "Cadastrar liderança"}
          </Button>
        )}
      </div>

      {/* Form criar */}
      {showForm && !created && (
        <InviteForm
          isOwner={isOwner}
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
            {isOwner ? (
              <>Nenhum membro além de você ainda. Clique em <strong>Convidar</strong>.</>
            ) : (
              <>Nenhuma liderança cadastrada ainda. Clique em <strong>Cadastrar liderança</strong>.</>
            )}
          </div>
        )}
        {users.map((u) => (
          <UserRow
            key={u.id}
            user={u}
            isOwner={isOwner}
            meId={meId}
            onChanged={load}
            onReset={setCreated}
          />
        ))}
      </div>
    </section>
  );
}

function InviteForm({
  isOwner,
  onCancel,
  onCreated,
}: {
  isOwner: boolean;
  onCancel: () => void;
  onCreated: (u: CreatedUser) => void;
}) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  // Não-owner só cadastra liderança — papel fixo em "volunteer".
  const [role, setRole] = useState<"manager" | "staff" | "volunteer">(
    isOwner ? "staff" : "volunteer",
  );
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
        {isOwner ? (
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as typeof role)}
            className="w-full mt-1 py-2 px-3 rounded-md bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            <option value="manager">Coordenador (acesso amplo)</option>
            <option value="staff">Equipe (padrão)</option>
            <option value="volunteer">Liderança — só o formulário de cadastro</option>
          </select>
        ) : (
          // Coordenador/Equipe só criam liderança — papel fixo, sem escolha.
          <p className="w-full mt-1 py-2 px-3 rounded-md bg-background border border-border text-sm text-muted-foreground">
            Liderança — acesso só ao formulário de cadastro
          </p>
        )}
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
  isOwner,
  meId,
  onChanged,
  onReset,
}: {
  user: TeamUser;
  isOwner: boolean;
  meId: string;
  onChanged: () => void;
  onReset: (u: CreatedUser) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function changeRole(role: string) {
    if (busy || role === user.role) return;
    setBusy(true);
    try {
      await api<null>(`/v1/auth/users/${user.id}/role`, {
        method: "POST",
        body: { role },
      });
      toast.success(`${user.full_name} agora é ${ROLE_LABELS[role] ?? role}.`);
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao mudar papel.");
    } finally {
      setBusy(false);
    }
  }

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

  async function setSpecificPassword() {
    if (busy) return;
    const pwd = window.prompt(
      `Definir nova senha para ${user.full_name} (mínimo 8 caracteres):`,
    );
    if (pwd == null) return; // cancelou
    if (pwd.trim().length < 8) {
      toast.error("A senha precisa ter no mínimo 8 caracteres.");
      return;
    }
    setBusy(true);
    try {
      await api<null>(`/v1/auth/users/${user.id}/set-password`, {
        method: "POST",
        body: { password: pwd },
      });
      toast.success(`Senha de ${user.full_name} definida.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao definir senha.");
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

  async function deleteUser() {
    if (busy) return;
    if (
      !confirm(
        `EXCLUIR ${user.full_name} permanentemente? Esta ação não pode ser desfeita. ` +
          `Os contatos que essa pessoa cadastrou continuam (o nome fica registrado).`,
      )
    )
      return;
    setBusy(true);
    try {
      await api<null>(`/v1/auth/users/${user.id}`, { method: "DELETE" });
      toast.success(`${user.full_name} excluído.`);
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao excluir.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleArea(area: string, current: boolean, label: string) {
    if (busy) return;
    setBusy(true);
    try {
      await api<null>(`/v1/auth/users/${user.id}/access`, {
        method: "POST",
        body: { area, enabled: !current },
      });
      toast.success(current ? `${label} bloqueado.` : `${label} liberado.`);
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro.");
    } finally {
      setBusy(false);
    }
  }

  // Toggles de acesso por área: só o Dono configura, e só pra Coordenador/
  // Equipe (Liderança é só-formulário; o Dono não se autoconfigura).
  const showAccess =
    isOwner && (user.role === "manager" || user.role === "staff");

  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-3">
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

        <div className="flex items-center gap-2 shrink-0">
          {/* Mudar papel — só o Dono, e não no próprio usuário (evita
              se trancar fora). Promover a "Administrador (Dono)" dá acesso
              total + gestão da equipe. */}
          {isOwner && user.id !== meId && (
            <select
              value={user.role}
              onChange={(e) => changeRole(e.target.value)}
              disabled={busy}
              title="Mudar papel do membro"
              className="h-8 rounded-md border border-border bg-background px-2 text-xs focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-50"
            >
              <option value="owner">Administrador (Dono)</option>
              <option value="manager">Coordenador</option>
              <option value="staff">Equipe</option>
              <option value="volunteer">Liderança</option>
            </select>
          )}
          {user.role !== "owner" && (
            <div className="flex items-center gap-1">
              <button
                onClick={setSpecificPassword}
                disabled={busy}
                title="Definir senha (você escolhe)"
                className="p-1.5 rounded text-muted-foreground hover:text-primary hover:bg-accent/50 transition-colors disabled:opacity-50"
              >
                <KeyRound className="w-4 h-4" />
              </button>
              <button
                onClick={resetPassword}
                disabled={busy}
                title="Gerar senha aleatória"
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
              <button
                onClick={deleteUser}
                disabled={busy}
                title="Excluir de vez"
                className="p-1.5 rounded text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition-colors disabled:opacity-50"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Acessos por área — o Dono liga/desliga cada seção por pessoa. */}
      {showAccess && (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground mr-0.5 inline-flex items-center gap-1">
            <Layers className="w-3 h-3" /> Acessos:
          </span>
          {ACCESS_AREAS.map(({ area, flag, label }) => {
            const on = !!user[flag];
            return (
              <button
                key={area}
                onClick={() => toggleArea(area, on, label)}
                disabled={busy}
                title={on ? `${label} liberado — clique para bloquear` : `Liberar ${label}`}
                className={
                  "inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] transition-colors disabled:opacity-50 " +
                  (on
                    ? "border-primary bg-primary/15 text-primary font-medium"
                    : "border-border text-muted-foreground hover:border-primary/50")
                }
              >
                {label} {on ? "✓" : ""}
              </button>
            );
          })}
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
