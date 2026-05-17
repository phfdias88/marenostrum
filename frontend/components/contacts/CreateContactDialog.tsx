"use client";

/**
 * Dialog de criacao de contato.
 * - react-hook-form + zod resolver = validacao client-side
 * - api() injeta JWT, backend valida tudo de novo (defense-in-depth)
 * - onCreated() notifica o pai pra refazer fetch (mantemos a tabela autoritativa do servidor)
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { api, ApiError } from "@/lib/api";
import type { Contact, ContactType } from "@/lib/types";
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

// Schema espelhando o backend (ContactCreate)
const schema = z.object({
  full_name: z.string().min(2, "Mínimo 2 caracteres").max(150),
  phone: z.string().max(30).optional().or(z.literal("")),
  email: z.string().email("Email inválido").optional().or(z.literal("")),
  address: z.string().max(255).optional().or(z.literal("")),
  neighborhood: z.string().max(100).optional().or(z.literal("")),
  city: z.string().max(100).optional().or(z.literal("")),
  state: z
    .string()
    .length(2, "UF deve ter 2 letras")
    .optional()
    .or(z.literal("")),
  birth_date: z.string().optional().or(z.literal("")),
  type: z.enum(["voter", "leader", "supporter", "donor", "other"]),
  // lat/lng nao no formulario MVP — geocoding sera Fase 4
});
type FormValues = z.infer<typeof schema>;

export function CreateContactDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { type: "voter" as ContactType },
  });

  async function onSubmit(values: FormValues) {
    // Limpa strings vazias -> null (backend espera ausencia, nao "")
    const payload = Object.fromEntries(
      Object.entries(values).map(([k, v]) => [k, v === "" ? null : v]),
    );

    try {
      await api<Contact>("/v1/contacts", { method: "POST", body: payload });
      toast.success("Contato criado.");
      reset();
      setOpen(false);
      onCreated();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "Erro ao salvar.";
      toast.error(msg);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus />
          Novo contato
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Novo contato</DialogTitle>
          <DialogDescription>
            Cadastre eleitores, lideranças, apoiadores e doadores da campanha.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="grid grid-cols-1 sm:grid-cols-2 gap-4"
        >
          <Field label="Nome completo *" error={errors.full_name?.message}>
            <Input {...register("full_name")} autoFocus />
          </Field>
          <Field label="Telefone" error={errors.phone?.message}>
            <Input {...register("phone")} placeholder="(32) 99999-9999" />
          </Field>
          <Field label="Email" error={errors.email?.message}>
            <Input type="email" {...register("email")} />
          </Field>
          <Field label="Tipo">
            <select
              {...register("type")}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="voter">Eleitor</option>
              <option value="leader">Liderança</option>
              <option value="supporter">Apoiador</option>
              <option value="donor">Doador</option>
              <option value="other">Outro</option>
            </select>
          </Field>
          <Field
            label="Endereço"
            error={errors.address?.message}
            className="sm:col-span-2"
          >
            <Input {...register("address")} placeholder="Rua, número, complemento" />
          </Field>
          <Field label="Bairro" error={errors.neighborhood?.message}>
            <Input {...register("neighborhood")} />
          </Field>
          <Field label="Cidade" error={errors.city?.message}>
            <Input {...register("city")} placeholder="Juiz de Fora" />
          </Field>
          <Field label="UF" error={errors.state?.message}>
            <Input {...register("state")} maxLength={2} placeholder="MG" />
          </Field>
          <Field label="Aniversário" error={errors.birth_date?.message}>
            <Input type="date" {...register("birth_date")} />
          </Field>

          <DialogFooter className="sm:col-span-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                reset();
                setOpen(false);
              }}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Salvando..." : "Salvar contato"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  error,
  className,
  children,
}: {
  label: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      <Label className="mb-1.5 block">{label}</Label>
      {children}
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}
