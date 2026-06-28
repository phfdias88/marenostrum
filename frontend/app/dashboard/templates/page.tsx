"use client";

/**
 * /dashboard/templates — gestão de templates de mensagem (WhatsApp).
 *
 * Mensagens reutilizáveis com variáveis ({nome}, {cidade}, {bairro},
 * {tratamento}). O envio real (substituição + wa.me) acontece a partir
 * de um contato, no CRM. Aqui o usuário cria/edita/exclui os modelos.
 */
import { MessageSquarePlus, Pencil, Plus, Trash2, X } from "lucide-react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { MessageTemplate } from "@/lib/types";

/** Variáveis suportadas — substituídas com os dados do contato no envio. */
const VARS = ["{nome}", "{cidade}", "{bairro}", "{tratamento}"];

export default function TemplatesPage() {
  const [items, setItems] = useState<MessageTemplate[] | null>(null);
  const [editing, setEditing] = useState<MessageTemplate | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await api<MessageTemplate[]>("/v1/templates"));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao carregar.");
      setItems([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function remove(id: string) {
    try {
      await api(`/v1/templates/${id}`, { method: "DELETE" });
      toast.success("Template excluído.");
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro.");
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-4">
        <Link
          href="/dashboard/contacts"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Contatos
        </Link>
        <button
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
        >
          <Plus className="w-4 h-4" /> Novo template
        </button>
      </div>

      <header className="mb-6">
        <h1 className="text-2xl font-bold inline-flex items-center gap-2">
          <MessageSquarePlus className="w-6 h-6 text-primary" /> Templates de mensagem
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Modelos reutilizáveis pra WhatsApp. Use variáveis como{" "}
          {VARS.map((v) => (
            <code key={v} className="mx-0.5 text-xs bg-muted px-1 py-0.5 rounded">
              {v}
            </code>
          ))}{" "}
          : são preenchidas com os dados do contato no envio.
        </p>
      </header>

      {items === null ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 rounded-xl border bg-card animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
          <MessageSquarePlus className="mx-auto h-9 w-9 text-muted-foreground" />
          <p className="mt-3 font-semibold">Nenhum template ainda</p>
          <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
            Crie modelos de mensagem (aniversário, convite, agradecimento) pra
            disparar rápido pros contatos no WhatsApp.
          </p>
          <button
            onClick={() => setCreating(true)}
            className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
          >
            <Plus className="w-4 h-4" /> Criar primeiro template
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {items.map((t) => (
            <div key={t.id} className="rounded-xl border bg-card p-4 flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-semibold truncate">{t.title}</p>
                  {t.category && (
                    <span className="inline-block mt-0.5 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">
                      {t.category}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => setEditing(t)}
                    className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent"
                    title="Editar"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => remove(t.id)}
                    className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                    title="Excluir"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <p className="text-sm text-muted-foreground mt-2 whitespace-pre-wrap line-clamp-4">
                {t.body}
              </p>
            </div>
          ))}
        </div>
      )}

      {(creating || editing) && (
        <TemplateDialog
          template={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSaved={() => {
            setCreating(false);
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

// ============================================================ Dialog

function TemplateDialog({
  template,
  onClose,
  onSaved,
}: {
  template: MessageTemplate | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!template;
  const [title, setTitle] = useState(template?.title ?? "");
  const [category, setCategory] = useState(template?.category ?? "");
  const [body, setBody] = useState(template?.body ?? "");
  const [busy, setBusy] = useState(false);

  function insertVar(v: string) {
    setBody((b) => (b ? `${b} ${v}` : v));
  }

  async function save() {
    if (title.trim().length < 2 || body.trim().length < 2) {
      toast.error("Preencha título e mensagem.");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        title: title.trim(),
        body: body.trim(),
        category: category.trim() || null,
      };
      if (isEdit) {
        await api(`/v1/templates/${template!.id}`, { method: "PUT", body: payload });
        toast.success("Template atualizado.");
      } else {
        await api("/v1/templates", { method: "POST", body: payload });
        toast.success("Template criado.");
      }
      onSaved();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao salvar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-start justify-center pt-12 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold">{isEdit ? "Editar template" : "Novo template"}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="text-xs uppercase tracking-wider text-muted-foreground">Título *</label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={120}
                placeholder="Ex: Parabéns de aniversário"
                className="w-full mt-1 py-2 px-3 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                autoFocus
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-muted-foreground">Categoria</label>
              <input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                maxLength={40}
                placeholder="aniversário"
                className="w-full mt-1 py-2 px-3 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground">Mensagem *</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={2000}
              rows={5}
              placeholder="Olá {nome}! ..."
              className="w-full mt-1 py-2 px-3 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-y"
            />
            <div className="flex flex-wrap gap-1.5 mt-2">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground self-center">
                Inserir variável:
              </span>
              {VARS.map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => insertVar(v)}
                  className="px-2 py-0.5 rounded-full border border-border text-xs text-muted-foreground hover:text-foreground hover:border-primary/50"
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 p-4 border-t">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-md text-sm text-muted-foreground hover:text-foreground"
          >
            Cancelar
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {busy ? "Salvando..." : isEdit ? "Salvar alterações" : "Criar template"}
          </button>
        </div>
      </div>
    </div>
  );
}
