"use client";

/**
 * /dashboard/contacts/[id] — perfil do contato + timeline de interacoes.
 *
 * 2 fetches em paralelo:
 *   GET /v1/contacts/{id}              -> dados do contato
 *   GET /v1/contacts/{id}/interactions -> eventos do BotConversa
 * Se qualquer um 404: contato nao existe ou pertence a outro tenant
 * (backend nao distingue por design — anti enumeration).
 */
import { ArrowLeft, ClipboardList, MapPin, Pencil, Phone, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import {
  CONTACT_TYPE_LABELS,
  type Contact,
  type Interaction,
  type Page,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { ContactFormDialog } from "@/components/contacts/ContactFormDialog";
import { WhatsAppSender } from "@/components/contacts/WhatsAppSender";
import { InteractionTimeline } from "@/components/contacts/InteractionTimeline";
import { ContactDemandsList } from "@/components/demands/ContactDemandsList";
import { Activity } from "lucide-react";

export default function ContactDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [contact, setContact] = useState<Contact | null>(null);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [loadingContact, setLoadingContact] = useState(true);
  const [loadingTimeline, setLoadingTimeline] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [editing, setEditing] = useState(false);

  const loadContact = useCallback(async () => {
    setLoadingContact(true);
    try {
      const c = await api<Contact>(`/v1/contacts/${id}`);
      setContact(c);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
      } else {
        toast.error(err instanceof ApiError ? err.message : "Erro ao carregar.");
      }
    } finally {
      setLoadingContact(false);
    }
  }, [id]);

  const loadTimeline = useCallback(async () => {
    setLoadingTimeline(true);
    try {
      const res = await api<Page<Interaction>>(
        `/v1/contacts/${id}/interactions?limit=50`,
      );
      setInteractions(res.items);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
      } else {
        toast.error(err instanceof ApiError ? err.message : "Erro ao carregar timeline.");
      }
    } finally {
      setLoadingTimeline(false);
    }
  }, [id]);

  useEffect(() => {
    loadContact();
    loadTimeline();
  }, [loadContact, loadTimeline]);

  if (notFound) {
    return (
      <section className="max-w-3xl mx-auto px-6 py-16 text-center">
        <h1 className="text-xl font-semibold">Contato não encontrado</h1>
        <p className="text-sm text-muted-foreground mt-2">
          O contato pode ter sido removido ou não pertence à sua campanha.
        </p>
        <Button asChild variant="outline" className="mt-6">
          <Link href="/dashboard/contacts">
            <ArrowLeft />
            Voltar para contatos
          </Link>
        </Button>
      </section>
    );
  }

  return (
    <section className="max-w-4xl mx-auto px-6 py-8 space-y-6">
      {/* Breadcrumb */}
      <Link
        href="/dashboard/contacts"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Contatos
      </Link>

      {/* Header do contato */}
      <header className="rounded-xl border bg-card p-6">
        {loadingContact || !contact ? (
          <div className="space-y-3">
            <Skeleton className="h-7 w-1/3" />
            <Skeleton className="h-4 w-1/4" />
          </div>
        ) : (
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-semibold tracking-tight">
                  {contact.full_name}
                </h1>
                <span className="inline-flex items-center rounded-full bg-accent px-2.5 py-0.5 text-xs font-medium text-accent-foreground">
                  {CONTACT_TYPE_LABELS[contact.type]}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
                {contact.phone && (
                  <Field icon={Phone} label="Telefone" value={contact.phone} />
                )}
                {contact.email && (
                  <Field label="Email" value={contact.email} />
                )}
                {(contact.address || contact.neighborhood) && (
                  <Field
                    icon={MapPin}
                    label="Endereço"
                    value={
                      [contact.address, contact.neighborhood]
                        .filter(Boolean)
                        .join(" — ") || "—"
                    }
                  />
                )}
                {(contact.city || contact.state) && (
                  <Field
                    label="Cidade/UF"
                    value={
                      [contact.city, contact.state]
                        .filter(Boolean)
                        .join("/") || "—"
                    }
                  />
                )}
              </dl>
            </div>
            <div className="flex items-center gap-2">
              <WhatsAppSender contact={contact} />
              <Button variant="outline" onClick={() => setEditing(true)}>
                <Pencil />
                Editar
              </Button>
            </div>
          </div>
        )}
      </header>

      {/* Tabs: Timeline + Demandas */}
      <Tabs defaultValue="timeline">
        <TabsList>
          <TabsTrigger value="timeline">
            <Activity />
            Timeline
          </TabsTrigger>
          <TabsTrigger value="demands">
            <ClipboardList />
            Demandas
          </TabsTrigger>
        </TabsList>

        <TabsContent value="timeline">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs text-muted-foreground">
              Eventos de WhatsApp recebidos do BotConversa
            </p>
            <Button
              variant="ghost"
              size="sm"
              onClick={loadTimeline}
              disabled={loadingTimeline}
              aria-label="Atualizar timeline"
            >
              <RefreshCw className={loadingTimeline ? "animate-spin" : ""} />
              Atualizar
            </Button>
          </div>
          <InteractionTimeline items={interactions} loading={loadingTimeline} />
        </TabsContent>

        <TabsContent value="demands">
          {contact && (
            <ContactDemandsList
              contactId={contact.id}
              contactName={contact.full_name}
            />
          )}
        </TabsContent>
      </Tabs>

      {/* Edit dialog */}
      <ContactFormDialog
        mode="edit"
        contact={contact}
        open={editing}
        onOpenChange={setEditing}
        onSaved={() => {
          loadContact();
          setEditing(false);
        }}
      />
    </section>
  );
}


function Field({
  icon: Icon,
  label,
  value,
}: {
  icon?: typeof Phone;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2">
      {Icon && <Icon className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />}
      <div className="min-w-0">
        <dt className="text-xs text-muted-foreground">{label}</dt>
        <dd className="truncate">{value}</dd>
      </div>
    </div>
  );
}
