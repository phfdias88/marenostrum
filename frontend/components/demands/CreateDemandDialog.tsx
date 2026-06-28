"use client";

/**
 * Dialog de criacao de demanda.
 *
 * Dois modos de uso:
 * - Sem contactId (visao global): mostra dropdown nativo de contatos
 *   (carrega lista com 100 contatos ativos)
 * - Com contactId (perfil do contato): contato fixo, sem dropdown
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { api, ApiError } from "@/lib/api";
import type { Contact, Demand, Page } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const schema = z.object({
  contact_id: z.string().uuid("Selecione um contato"),
  title: z.string().min(3, "Mínimo 3 caracteres").max(180),
  description: z.string().min(1).max(10_000),
  category: z.string().min(1).max(80),
  status: z.enum(["aberta", "em_andamento", "resolvida", "cancelada"]),
});
type FormValues = z.infer<typeof schema>;

const CATEGORIES = [
  "Saúde",
  "Infraestrutura",
  "Educação",
  "Segurança",
  "Documentação",
  "Habitação",
  "Transporte",
  "Outro",
];

type Props = {
  onSaved: () => void;
  /** Se fornecido, contato fica fixo (uso no perfil do contato). */
  contactId?: string;
  contactName?: string;
  children: React.ReactNode; // trigger
};

export function CreateDemandDialog({
  onSaved,
  contactId,
  contactName,
  children,
}: Props) {
  const [open, setOpen] = useState(false);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const fixedContact = Boolean(contactId);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      contact_id: contactId ?? "",
      title: "",
      description: "",
      category: "Saúde",
      status: "aberta",
    },
  });

  // Carrega lista de contatos so' no modo "visao global"
  useEffect(() => {
    if (!open || fixedContact) return;
    api<Page<Contact>>("/v1/contacts?limit=100")
      .then((res) => setContacts(res.items))
      .catch(() => toast.error("Não foi possível carregar contatos."));
  }, [open, fixedContact]);

  // Garante que contactId fixo entra no form
  useEffect(() => {
    if (contactId) setValue("contact_id", contactId);
  }, [contactId, setValue]);

  async function onSubmit(values: FormValues) {
    try {
      await api<Demand>("/v1/demands", { method: "POST", body: values });
      toast.success("Demanda criada.");
      reset({
        contact_id: contactId ?? "",
        title: "",
        description: "",
        category: "Saúde",
        status: "aberta",
      });
      setOpen(false);
      onSaved();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao salvar.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nova demanda</DialogTitle>
          <DialogDescription>
            {fixedContact && contactName
              ? `Pedido para o gabinete em nome de ${contactName}.`
              : "Pedido para o gabinete vinculado a um contato."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Contato */}
          {fixedContact ? (
            <div>
              <Label className="mb-1.5 block">Contato</Label>
              <p className="text-sm text-muted-foreground">{contactName ?? "—"}</p>
            </div>
          ) : (
            <div>
              <Label className="mb-1.5 block">Contato *</Label>
              <select
                {...register("contact_id")}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="">Selecione...</option>
                {contacts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.full_name}
                    {c.phone ? ` · ${c.phone}` : ""}
                  </option>
                ))}
              </select>
              {errors.contact_id && (
                <p className="mt-1 text-xs text-destructive">
                  {errors.contact_id.message}
                </p>
              )}
            </div>
          )}

          <div>
            <Label className="mb-1.5 block">Título *</Label>
            <Input {...register("title")} placeholder="Buraco na Rua A" autoFocus />
            {errors.title && (
              <p className="mt-1 text-xs text-destructive">{errors.title.message}</p>
            )}
          </div>

          <div>
            <Label className="mb-1.5 block">Categoria *</Label>
            <select
              {...register("category")}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          <div>
            <Label className="mb-1.5 block">Descrição *</Label>
            <textarea
              {...register("description")}
              rows={4}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder="Detalhes do pedido..."
            />
            {errors.description && (
              <p className="mt-1 text-xs text-destructive">{errors.description.message}</p>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Salvando..." : "Criar demanda"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
