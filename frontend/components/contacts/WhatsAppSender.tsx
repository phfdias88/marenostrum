"use client";

/**
 * WhatsAppSender — botão "WhatsApp" que abre um dialog pra escolher um
 * template, preenche as variáveis ({nome}, {cidade}...) com os dados do
 * contato, mostra preview e abre o wa.me com a mensagem pronta.
 *
 * Não envia nada pelo servidor — abre o WhatsApp Web/app do usuário (mesma
 * abordagem segura do widget de aniversariantes).
 */
import { MessageCircle, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import type { Contact, MessageTemplate } from "@/lib/types";

function digits(phone: string | null): string | null {
  if (!phone) return null;
  const d = phone.replace(/\D/g, "");
  return d.length >= 10 ? d : null;
}

/** Substitui {nome}, {cidade}, {bairro}, {tratamento} com dados do contato. */
function fill(body: string, c: Contact): string {
  const first = c.full_name.split(" ")[0];
  return body
    .replaceAll("{nome}", first)
    .replaceAll("{cidade}", c.city ?? "")
    .replaceAll("{bairro}", c.neighborhood ?? "")
    .replaceAll("{tratamento}", "") // reservado; sem campo dedicado ainda
    .replace(/\s+([,.;:!?])/g, "$1") // tira pontuação órfã ("Prezado(a) ," -> "Prezado(a),")
    .replace(/\s+/g, " ")
    .trim();
}

export function WhatsAppSender({ contact }: { contact: Contact }) {
  const [open, setOpen] = useState(false);
  // Preferência: campo WhatsApp dedicado; cai pro telefone se não houver.
  // Contato com SÓ o WhatsApp preenchido não devia ficar sem botão de enviar.
  const phone = digits(contact.whatsapp ?? contact.phone);

  if (!phone) {
    return (
      <Button disabled title="Contato sem celular válido">
        <MessageCircle className="w-4 h-4" /> WhatsApp
      </Button>
    );
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <MessageCircle className="w-4 h-4" /> WhatsApp
      </Button>
      {open && (
        <PickerDialog
          contact={contact}
          phone={phone}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

function Button({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-emerald-600/40 text-emerald-600 text-sm font-medium hover:bg-emerald-600/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
    >
      {children}
    </button>
  );
}

function PickerDialog({
  contact,
  phone,
  onClose,
}: {
  contact: Contact;
  phone: string;
  onClose: () => void;
}) {
  const [templates, setTemplates] = useState<MessageTemplate[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [custom, setCustom] = useState("");

  useEffect(() => {
    api<MessageTemplate[]>("/v1/templates")
      .then((rows) => {
        setTemplates(rows);
        if (rows.length) {
          setSelectedId(rows[0].id);
          setCustom(fill(rows[0].body, contact));
        }
      })
      .catch(() => setTemplates([]));
  }, [contact]);

  function pick(t: MessageTemplate) {
    setSelectedId(t.id);
    setCustom(fill(t.body, contact));
  }

  function send() {
    const msg = custom.trim();
    if (!msg) {
      toast.error("Mensagem vazia.");
      return;
    }
    const intl = phone.startsWith("55") ? phone : `55${phone}`;
    const url = `https://wa.me/${intl}?text=${encodeURIComponent(msg)}`;
    window.open(url, "_blank", "noopener,noreferrer");
    onClose();
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
          <h3 className="font-semibold inline-flex items-center gap-2">
            <MessageCircle className="w-5 h-5 text-emerald-600" /> WhatsApp para{" "}
            {contact.full_name.split(" ")[0]}
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          {templates === null ? (
            <p className="text-sm text-muted-foreground">Carregando templates…</p>
          ) : templates.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum template ainda. Você pode escrever a mensagem abaixo ou criar
              modelos em{" "}
              <a href="/dashboard/templates" className="text-primary hover:underline">
                Templates
              </a>
              .
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {templates.map((t) => (
                <button
                  key={t.id}
                  onClick={() => pick(t)}
                  className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                    selectedId === t.id
                      ? "border-primary bg-primary/15 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {t.title}
                </button>
              ))}
            </div>
          )}

          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground">
              Mensagem (editável)
            </label>
            <textarea
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              rows={5}
              placeholder="Escreva ou escolha um template acima…"
              className="w-full mt-1 py-2 px-3 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-y"
            />
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
            onClick={send}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700"
          >
            <MessageCircle className="w-4 h-4" /> Abrir no WhatsApp
          </button>
        </div>
      </div>
    </div>
  );
}
