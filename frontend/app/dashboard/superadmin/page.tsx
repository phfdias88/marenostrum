"use client";

/**
 * Painel Mare Nostrum (super-admin) — gerência CROSS-TENANT.
 *
 * Só acessível a quem tem is_superadmin=true (flag do banco). O backend
 * (/v1/admin/*) reforça o gate em TODA rota; aqui a página só redireciona
 * quem não for super-admin (defesa em profundidade, não a trava real).
 *
 * Permite: listar todos os clientes, criar conta de CORTESIA (titular sem
 * pagamento) e administrar o titular de qualquer cliente (resetar senha,
 * ativar/desativar).
 */
import {
  ArrowLeft,
  Check,
  Copy,
  Loader2,
  LogIn,
  Power,
  RefreshCcw,
  KeyRound,
  ShieldCheck,
  Trash2,
  UserPlus,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import { startImpersonation } from "@/lib/auth";
import { Button } from "@/components/ui/button";

type Me = { is_superadmin?: boolean; user_id: string; email?: string };

// Quem emite chave de API. Mesma lista do backend (API_KEY_ADMINS) — aqui
// serve so pra nao MOSTRAR um botao que o servidor vai recusar; a decisao
// que vale continua sendo a do backend.
const PODEM_EMITIR_CHAVE = [
  "admin@marenostrum.com.br",
  "danieldeluna@gmail.com",
];

type ApiKeyItem = {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  use_count: number;
};

/** Chave sem prazo nunca vence; com prazo, vale ate o instante gravado. */
function venceu(k: { expires_at: string | null }): boolean {
  return !!k.expires_at && new Date(k.expires_at) <= new Date();
}

type ApiKeyCriada = {
  id: string;
  name: string;
  api_key: string;
  prefix: string;
  expires_at: string | null;
};

type Tenant = {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  subscription_status: string | null;
  created_at: string | null;
  user_count: number;
  titular_user_id: string | null;
  titular_email: string | null;
  titular_name: string | null;
  titular_active: boolean | null;
  is_courtesy: boolean;
  // Acesso temporário do titular (cortesia com prazo).
  titular_usage_limit_hours: number | null;
  titular_first_login_at: string | null;
  titular_expires_at: string | null;
};

type CreatedComp = {
  tenant_id: string;
  tenant_slug: string;
  user_id: string;
  email: string;
  temp_password: string;
  usage_limit_hours: number | null;
};

/** Status do acesso temporário do titular, pra listagem. */
function trialLabel(t: Tenant): string | null {
  if (!t.titular_usage_limit_hours) return null;
  if (!t.titular_first_login_at || !t.titular_expires_at) {
    return "aguardando 1º login";
  }
  const exp = new Date(t.titular_expires_at);
  if (exp <= new Date()) return "acesso expirado";
  return `expira ${exp.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  })}`;
}

export default function SuperadminPage() {
  const router = useRouter();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [meuEmail, setMeuEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [created, setCreated] = useState<CreatedComp | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<{ items: Tenant[] }>("/v1/admin/tenants", { skipCache: true });
      setTenants(data.items);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setAllowed(false);
        router.replace("/dashboard");
        return;
      }
      toast.error("Erro ao carregar", {
        description: err instanceof ApiError ? err.message : "Tente novamente.",
      });
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    api<Me>("/v1/auth/me")
      .then((m) => {
        setMeuEmail((m.email || "").toLowerCase());
        if (!m.is_superadmin) {
          setAllowed(false);
          router.replace("/dashboard");
          return;
        }
        setAllowed(true);
        load();
      })
      .catch(() => {
        setAllowed(false);
        router.replace("/dashboard");
      });
  }, [router, load]);

  if (allowed === null || allowed === false) {
    return (
      <div className="min-h-[50vh] grid place-items-center">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/configuracoes"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Configurações
      </Link>

      <header className="mb-6 flex items-center gap-3">
        <span className="grid place-items-center w-11 h-11 rounded-xl bg-primary/15 text-primary shrink-0">
          <ShieldCheck className="w-6 h-6" />
        </span>
        <div>
          <h1 className="text-2xl font-bold">Painel Mare Nostrum</h1>
          <p className="text-sm text-muted-foreground">
            Gerência de todos os clientes · acesso restrito à equipe.
          </p>
        </div>
      </header>

      <div className="space-y-6">
        {created && (
          <CompCredentialsCard comp={created} onDone={() => setCreated(null)} />
        )}
        <CreateCompCard onCreated={(c) => { setCreated(c); load(); }} />
        <TenantsCard
          tenants={tenants}
          loading={loading}
          onChanged={load}
        />
        {PODEM_EMITIR_CHAVE.includes(meuEmail) && <ApiKeysCard />}
      </div>
    </div>
  );
}

// ================================================ criar conta de cortesia

function CreateCompCard({ onCreated }: { onCreated: (c: CreatedComp) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [tenantName, setTenantName] = useState("");
  // Acesso temporário: "" = cortesia sem prazo.
  const [limitHours, setLimitHours] = useState("");
  const [busy, setBusy] = useState(false);

  const limitNum = limitHours.trim() === "" ? null : Number(limitHours);
  const limitValid =
    limitNum === null ||
    (Number.isFinite(limitNum) && limitNum >= 0 && limitNum <= 8760);
  const canSubmit =
    name.trim().length >= 2 && /\S+@\S+\.\S+/.test(email) && limitValid;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    try {
      const c = await api<CreatedComp>("/v1/admin/tenants", {
        method: "POST",
        body: {
          name: name.trim(),
          email: email.trim().toLowerCase(),
          tenant_name: tenantName.trim() || undefined,
          // 0/vazio = sem limite (backend grava NULL).
          usage_limit_hours: limitNum && limitNum > 0 ? limitNum : 0,
        },
      });
      onCreated(c);
      toast.success("Conta de cortesia criada!", {
        description: c.usage_limit_hours
          ? `Titular ${c.email} · ${c.usage_limit_hours}h a partir do 1º login.`
          : `Titular ${c.email} · copie a senha provisória abaixo.`,
      });
      setName("");
      setEmail("");
      setTenantName("");
      setLimitHours("");
    } catch (err) {
      toast.error("Não foi possível criar", {
        description: err instanceof ApiError ? err.message : "Tente novamente.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <UserPlus className="w-5 h-5 text-primary" />
        <h2 className="font-semibold">Criar conta de cortesia</h2>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        Cria um cliente novo (campanha + titular) com acesso completo, sem
        cobrança. O titular troca a senha no primeiro login.
      </p>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Nome do titular" value={name} onChange={setName} placeholder="Ex: Dr. João Águia" />
        <Field label="E-mail de login" value={email} onChange={setEmail} type="email" placeholder="joao@campanha.com.br" />
        <Field label="Nome da campanha (opcional)" value={tenantName} onChange={setTenantName} placeholder="Se vazio, usa o nome do titular" />
        <div>
          <Field
            label="Tempo limite de uso (horas) · opcional"
            value={limitHours}
            onChange={setLimitHours}
            type="number"
            placeholder="Ex: 48 · vazio ou 0 = sem prazo"
          />
          <p className="mt-1 text-[11px] text-muted-foreground">
            O prazo só começa a contar no <strong>primeiro login</strong> do
            titular. Depois disso o acesso trava sozinho.{" "}
            {!limitValid && (
              <span className="text-destructive">
                Informe um número entre 0 e 8760.
              </span>
            )}
          </p>
        </div>
        <Button type="submit" disabled={!canSubmit || busy} className="w-full sm:w-auto">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
          Criar cortesia
        </Button>
      </form>
    </div>
  );
}

function CompCredentialsCard({ comp, onDone }: { comp: CreatedComp; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(comp.temp_password);
    setCopied(true);
    toast.success("Senha copiada.");
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-4">
      <div className="flex items-start gap-3">
        <span className="grid place-items-center w-9 h-9 rounded-lg bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 shrink-0">
          <ShieldCheck className="w-5 h-5" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-semibold">Conta criada · {comp.email}</p>
          <p className="text-xs text-muted-foreground">
            Senha provisória mostrada <strong>uma única vez</strong>. Copie e envie
            por canal seguro. Login em <code>/sistema/login</code>.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <code className="flex-1 px-3 py-2 rounded-md bg-background border border-border font-mono text-sm tracking-wider select-all">
              {comp.temp_password}
            </code>
            <Button onClick={copy} size="sm" variant="outline">
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              {copied ? "Copiado" : "Copiar"}
            </Button>
          </div>
        </div>
        <button onClick={onDone} className="text-xs text-muted-foreground hover:text-foreground shrink-0">
          Fechar
        </button>
      </div>
    </div>
  );
}

// ==================================================== lista de clientes

function TenantsCard({
  tenants,
  loading,
  onChanged,
}: {
  tenants: Tenant[];
  loading: boolean;
  onChanged: () => void;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <h2 className="font-semibold mb-4">Clientes ({tenants.length})</h2>
      {loading ? (
        <div className="py-8 grid place-items-center">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : tenants.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4">Nenhum cliente.</p>
      ) : (
        <div className="divide-y divide-border">
          {tenants.map((t) => (
            <TenantRow key={t.id} tenant={t} onChanged={onChanged} />
          ))}
        </div>
      )}
    </div>
  );
}

function TenantRow({ tenant, onChanged }: { tenant: Tenant; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [reset, setReset] = useState<string | null>(null);

  // "Entrar como": abre o ambiente do cliente numa sessão curta e auditada.
  async function enterTenant() {
    if (busy) return;
    if (
      !confirm(
        `Entrar no ambiente de "${tenant.name}"?\n\n` +
          "Você verá os dados do cliente (contatos, demandas, análises). " +
          "O acesso fica registrado na auditoria.",
      )
    )
      return;
    setBusy(true);
    try {
      const r = await api<{
        access_token: string;
        expires_in: number;
        tenant_name: string;
      }>(`/v1/admin/tenants/${tenant.id}/impersonate`, { method: "POST" });
      startImpersonation(r.access_token, r.expires_in, r.tenant_name);
      // Reload completo: limpa cache/estado da sessão anterior.
      window.location.href = `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/dashboard`;
    } catch (err) {
      toast.error("Não foi possível entrar", {
        description: err instanceof ApiError ? err.message : "Tente novamente.",
      });
      setBusy(false);
    }
  }

  async function resetPwd() {
    if (!tenant.titular_user_id || busy) return;
    if (!confirm(`Gerar nova senha provisória para o titular ${tenant.titular_email}?`)) return;
    setBusy(true);
    try {
      const r = await api<{ temp_password: string }>(
        `/v1/admin/users/${tenant.titular_user_id}/reset-password`,
        { method: "POST" },
      );
      setReset(r.temp_password);
      toast.success("Senha resetada!", {
        description: `Copie a senha do titular ${tenant.titular_email}.`,
      });
    } catch (err) {
      toast.error("Falha ao resetar", {
        description: err instanceof ApiError ? err.message : "Tente novamente.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive() {
    if (!tenant.titular_user_id || busy) return;
    const next = !tenant.titular_active;
    if (!confirm(`${next ? "Reativar" : "Desativar"} o titular ${tenant.titular_email}?`)) return;
    setBusy(true);
    try {
      await api<null>(`/v1/admin/users/${tenant.titular_user_id}/set-active`, {
        method: "POST",
        body: { is_active: next },
      });
      toast.success(next ? "Titular reativado." : "Titular desativado.");
      onChanged();
    } catch (err) {
      toast.error("Falha na ação", {
        description: err instanceof ApiError ? err.message : "Tente novamente.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="py-3">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="font-medium truncate flex items-center gap-2">
            <span className="truncate">{tenant.name}</span>
            {tenant.is_courtesy && (
              <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-primary/15 text-primary border border-primary/30 whitespace-nowrap">
                Cortesia
              </span>
            )}
            {tenant.titular_usage_limit_hours ? (
              <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30 whitespace-nowrap">
                {tenant.titular_usage_limit_hours}h
              </span>
            ) : null}
            {tenant.titular_active === false && (
              <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                titular inativo
              </span>
            )}
          </p>
          <p className="text-xs text-muted-foreground truncate">
            {tenant.titular_email ? (
              <>Titular: {tenant.titular_email}</>
            ) : (
              <>sem titular marcado</>
            )}{" "}
            · {tenant.user_count} usuário(s) · <code>{tenant.slug}</code>
            {trialLabel(tenant) && <> · {trialLabel(tenant)}</>}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={enterTenant}
            disabled={busy}
            title={`Entrar no ambiente de ${tenant.name}`}
            className="inline-flex items-center gap-1 h-9 px-2.5 rounded-md border border-primary/40 text-primary text-xs font-medium hover:bg-primary/10 transition-colors disabled:opacity-50"
          >
            <LogIn className="w-4 h-4" /> Entrar
          </button>
        </div>
        {tenant.titular_user_id && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={resetPwd}
              disabled={busy}
              title="Resetar senha do titular"
              className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
            </button>
            <button
              onClick={toggleActive}
              disabled={busy}
              title={tenant.titular_active ? "Desativar titular" : "Reativar titular"}
              className={
                "inline-flex h-9 w-9 items-center justify-center rounded-md transition-colors disabled:opacity-50 " +
                (tenant.titular_active
                  ? "text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                  : "text-muted-foreground hover:text-emerald-600 hover:bg-emerald-500/10")
              }
            >
              <Power className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
      {reset && (
        <div className="mt-2 flex items-center gap-2 rounded-md bg-emerald-500/5 border border-emerald-500/30 px-3 py-2">
          <code className="flex-1 font-mono text-sm tracking-wider select-all">{reset}</code>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              navigator.clipboard.writeText(reset);
              toast.success("Senha copiada.");
            }}
          >
            <Copy className="w-4 h-4" /> Copiar
          </Button>
          <button onClick={() => setReset(null)} className="text-xs text-muted-foreground hover:text-foreground">
            Fechar
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================================ helpers

function ApiKeysCard() {
  const [chaves, setChaves] = useState<ApiKeyItem[]>([]);
  const [nome, setNome] = useState("");
  const [dias, setDias] = useState("");
  const [busy, setBusy] = useState(false);
  const [criada, setCriada] = useState<ApiKeyCriada | null>(null);
  const [copiada, setCopiada] = useState(false);
  const chaveRef = useRef<HTMLElement>(null);

  // Espelha o contrato do backend (name min 3, expires_in_days 1..3650). Sem
  // isto o servidor responde 422 com a mensagem crua do Pydantic, em ingles.
  const diasNum = dias.trim() === "" ? null : Number(dias);
  const erroForm =
    nome.trim() !== "" && nome.trim().length < 3
      ? "O nome precisa de pelo menos 3 letras."
      : diasNum !== null &&
        (!Number.isInteger(diasNum) || diasNum < 1 || diasNum > 3650)
      ? "A validade vai de 1 a 3650 dias (10 anos). Deixe vazio para sem prazo."
      : null;

  const carregar = useCallback(async () => {
    try {
      setChaves(await api<ApiKeyItem[]>("/v1/admin/api-keys", { skipCache: true }));
    } catch {
      /* silencioso: o card ainda serve pra criar */
    }
  }, []);

  useEffect(() => { void carregar(); }, [carregar]);

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || busy) return;
    setBusy(true);
    try {
      const nova = await api<ApiKeyCriada>("/v1/admin/api-keys", {
        method: "POST",
        // objeto puro: o api() serializa (stringify aqui manda texto e o
        // backend responde "Input should be a valid dictionary")
        body: {
          name: nome.trim(),
          ...(Number(dias) > 0 ? { expires_in_days: Number(dias) } : {}),
        },
      });
      setCriada(nova);      // aparece UMA vez: depois só o hash fica no banco
      setNome("");
      setDias("");
      void carregar();
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Não foi possível gerar a chave.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function revogar(id: string, rotulo: string) {
    if (!confirm(`Revogar a chave "${rotulo}"? Quem usa ela perde o acesso na hora.`)) return;
    try {
      await api<null>(`/v1/admin/api-keys/${id}`, { method: "DELETE" });
      toast.success("Chave revogada.");
      void carregar();
    } catch {
      toast.error("Não foi possível revogar.");
    }
  }

  async function copiar() {
    if (!criada) return;
    try {
      await navigator.clipboard.writeText(criada.api_key);
      setCopiada(true);
      toast.success("Chave copiada.");
      setTimeout(() => setCopiada(false), 2000);
    } catch {
      // O navegador pode negar a area de transferencia (permissao bloqueada,
      // aba sem foco). Como a chave aparece UMA vez, falhar calado faria a
      // pessoa clicar em "ja guardei" sem ter guardado: seleciona o texto e
      // manda usar Ctrl+C.
      const el = chaveRef.current;
      if (el) {
        const range = document.createRange();
        range.selectNodeContents(el);
        const sel = window.getSelection();
        sel?.removeAllRanges();
        sel?.addRange(range);
      }
      toast.error("O navegador bloqueou a copia automatica.", {
        description: "A chave ja esta selecionada — use Ctrl+C para copiar.",
      });
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <KeyRound className="w-5 h-5 text-primary" />
        <h2 className="font-semibold">Chaves de acesso aos dados</h2>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        Serve para ligar o sistema a um BI, uma planilha ou outro programa. A
        chave <strong>só lê</strong> — nunca altera nem apaga nada — e pode ser
        cancelada a qualquer momento.
      </p>

      {criada && (
        <div className="mb-5 rounded-lg border border-primary/40 bg-primary/5 p-4">
          <p className="text-sm font-medium mb-1">
            Copie agora — esta chave não aparece de novo
          </p>
          <p className="text-xs text-muted-foreground mb-3">
            Guarde no gerenciador de senhas. Se perder, é só cancelar esta e
            gerar outra.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <code
              ref={chaveRef}
              className="flex-1 min-w-0 break-all rounded-md bg-background px-3 py-2 font-mono text-xs select-all"
            >
              {criada.api_key}
            </code>
            <Button onClick={copiar} variant="secondary" className="shrink-0">
              {copiada ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              {copiada ? "Copiada" : "Copiar"}
            </Button>
          </div>
          <button
            onClick={() => setCriada(null)}
            className="mt-3 text-xs text-muted-foreground underline hover:text-foreground"
          >
            Já guardei, pode esconder
          </button>
        </div>
      )}

      <form onSubmit={criar} className="space-y-3 mb-5">
        <Field
          label="Para que serve esta chave"
          value={nome}
          onChange={setNome}
          placeholder="Ex: BI do Daniel"
        />
        <Field
          label="Validade em dias · opcional"
          value={dias}
          onChange={setDias}
          type="number"
          placeholder="Vazio = sem prazo"
        />
        {erroForm && (
          <p className="text-xs text-destructive">{erroForm}</p>
        )}
        <Button type="submit" disabled={!!erroForm || !nome.trim() || busy} className="w-full sm:w-auto">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
          Gerar chave
        </Button>
      </form>

      {chaves.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="pb-2 pr-3 font-medium">Nome</th>
                <th className="pb-2 pr-3 font-medium">Início da chave</th>
                <th className="pb-2 pr-3 font-medium tabular-nums">Usos</th>
                <th className="pb-2 pr-3 font-medium">Validade</th>
                <th className="pb-2 pr-3 font-medium">Situação</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {chaves.map((k) => (
                <tr key={k.id} className="border-t border-border/60">
                  <td className="py-2 pr-3">{k.name}</td>
                  <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">
                    {k.prefix}…
                  </td>
                  <td className="py-2 pr-3 tabular-nums">{k.use_count}</td>
                  <td className="py-2 pr-3 text-xs text-muted-foreground">
                    {k.expires_at
                      ? new Date(k.expires_at).toLocaleDateString("pt-BR")
                      : "sem prazo"}
                  </td>
                  <td className="py-2 pr-3">
                    {k.revoked_at ? (
                      <span className="text-muted-foreground">cancelada</span>
                    ) : venceu(k) ? (
                      // O backend recusa chave vencida (401). Mostrar "ativa"
                      // aqui faria a pessoa abrir chamado achando que o sistema
                      // quebrou, quando foi o prazo que acabou.
                      <span className="text-destructive">vencida</span>
                    ) : (
                      <span className="text-primary">ativa</span>
                    )}
                  </td>
                  <td className="py-2 text-right">
                    {!k.revoked_at && (
                      <button
                        onClick={() => revogar(k.id, k.name)}
                        className="inline-flex items-center gap-1 text-xs text-destructive hover:underline"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        Cancelar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1.5 w-full rounded-lg border border-border bg-background px-3.5 py-2.5 text-base focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition"
      />
    </label>
  );
}
