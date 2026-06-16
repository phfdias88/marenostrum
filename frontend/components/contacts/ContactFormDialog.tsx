"use client";

/**
 * Dialog dual-mode (create | edit) de contato.
 *
 * Uso:
 *   <ContactFormDialog mode="create" onSaved={refresh}>
 *     <Button><Plus/>Novo</Button>      // trigger custom
 *   </ContactFormDialog>
 *
 *   <ContactFormDialog
 *     mode="edit"
 *     contact={editing}
 *     open={!!editing}
 *     onOpenChange={(o) => !o && setEditing(null)}
 *     onSaved={refresh}
 *   />
 *
 * Validacao: zod (client) + backend Pydantic (server).
 * Strings vazias viram null antes de enviar — backend espera ausencia.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { api, ApiError } from "@/lib/api";
import type { Contact, ContactTag, ContactType } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { TagInput } from "@/components/contacts/TagInput";
import { AddressFields, type AddressValue } from "@/components/contacts/AddressFields";
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
  full_name: z.string().min(2, "Mínimo 2 caracteres").max(150),
  phone: z.string().max(30).optional().or(z.literal("")),
  whatsapp: z.string().max(30).optional().or(z.literal("")),
  email: z.string().email("Email inválido").optional().or(z.literal("")),
  instagram: z.string().max(120).optional().or(z.literal("")),
  facebook: z.string().max(200).optional().or(z.literal("")),
  cep: z.string().max(9).optional().or(z.literal("")),
  address: z.string().max(255).optional().or(z.literal("")),
  birth_date: z.string().optional().or(z.literal("")),
  type: z.enum(["voter", "leader", "supporter", "donor", "other"]),
});
type FormValues = z.infer<typeof schema>;

// Estado/Município/Bairro + coordenada saem do RHF e viram estado controlado
// (cascata via AddressFields), igual as tags.
const EMPTY_ADDRESS: AddressValue = {
  state: "",
  city: "",
  neighborhood: "",
  votingPlace: "",
  latitude: null,
  longitude: null,
};

const EMPTY_DEFAULTS: FormValues = {
  full_name: "",
  phone: "",
  whatsapp: "",
  email: "",
  instagram: "",
  facebook: "",
  cep: "",
  address: "",
  birth_date: "",
  type: "voter" as ContactType,
};

type CommonProps = {
  onSaved: () => void;
};

type CreateProps = CommonProps & {
  mode: "create";
  children: React.ReactNode;
  // Modo "uncontrolled" — dialog usa estado interno.
};

type EditProps = CommonProps & {
  mode: "edit";
  contact: Contact | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

type Props = CreateProps | EditProps;

export function ContactFormDialog(props: Props) {
  const isEdit = props.mode === "edit";
  const contact = isEdit ? props.contact : null;

  const [tags, setTags] = useState<string[]>([]);
  const [tagSuggestions, setTagSuggestions] = useState<string[]>([]);
  const [address, setAddress] = useState<AddressValue>(EMPTY_ADDRESS);
  // Bairro fora da base exige coordenada no mapa — AddressFields nos avisa.
  const [coordMissing, setCoordMissing] = useState(false);
  // Modo criar é controlado (estado interno) pra o Cancelar/Salvar fecharem
  // o dialog. Modo editar usa props.open/onOpenChange.
  const [createOpen, setCreateOpen] = useState(false);

  function closeDialog() {
    if (props.mode === "edit") props.onOpenChange(false);
    else setCreateOpen(false);
  }

  // Carrega tags ja' usadas no tenant (sugestoes pro chip "ja usadas")
  useEffect(() => {
    api<ContactTag[]>("/v1/contacts/tags")
      .then((rows) => setTagSuggestions(rows.map((r) => r.tag)))
      .catch(() => setTagSuggestions([]));
  }, []);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY_DEFAULTS,
  });

  // Quando muda o contato (modo edit), repopula o form
  useEffect(() => {
    if (!isEdit) return;
    if (contact) {
      reset({
        full_name: contact.full_name,
        phone: contact.phone ?? "",
        whatsapp: contact.whatsapp ?? "",
        email: contact.email ?? "",
        instagram: contact.instagram ?? "",
        facebook: contact.facebook ?? "",
        cep: contact.cep ?? "",
        address: contact.address ?? "",
        birth_date: contact.birth_date ?? "",
        type: contact.type,
      });
      setTags(contact.tags ?? []);
      setAddress({
        state: contact.state ?? "",
        city: contact.city ?? "",
        neighborhood: contact.neighborhood ?? "",
        votingPlace: contact.voting_place ?? "",
        latitude: contact.latitude,
        longitude: contact.longitude,
      });
    } else {
      reset(EMPTY_DEFAULTS);
      setTags([]);
      setAddress(EMPTY_ADDRESS);
    }
  }, [isEdit, contact, reset]);

  async function onSubmit(values: FormValues) {
    if (coordMissing) {
      toast.error("Bairro fora da base: marque a localização do contato no mapa.");
      return;
    }
    const payload: Record<string, unknown> = Object.fromEntries(
      Object.entries(values).map(([k, v]) => [k, v === "" ? null : v]),
    );
    payload.tags = tags;
    payload.state = address.state || null;
    payload.city = address.city || null;
    payload.neighborhood = address.neighborhood.trim() || null;
    payload.voting_place = address.votingPlace.trim() || null;
    payload.latitude = address.latitude;
    payload.longitude = address.longitude;

    try {
      if (isEdit && contact) {
        await api<Contact>(`/v1/contacts/${contact.id}`, {
          method: "PUT",
          body: payload,
        });
        toast.success("Contato atualizado.");
        props.onOpenChange(false);
      } else {
        await api<Contact>("/v1/contacts", { method: "POST", body: payload });
        toast.success("Contato criado.");
        reset(EMPTY_DEFAULTS);
        setTags([]);
        setAddress(EMPTY_ADDRESS);
        setCreateOpen(false);
      }
      props.onSaved();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao salvar.");
    }
  }

  const title = isEdit ? "Editar contato" : "Novo contato";
  const description = isEdit
    ? "Atualize os dados do contato."
    : "Cadastre eleitores, lideranças, apoiadores e doadores da campanha.";
  const submitLabel = isEdit ? "Salvar alterações" : "Salvar contato";

  const body = (
    <DialogContent className="max-w-2xl max-h-[90dvh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="grid grid-cols-1 sm:grid-cols-2 gap-4"
      >
        <Field label="Nome completo *" error={errors.full_name?.message}>
          <Input {...register("full_name")} autoFocus />
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
        <Field label="Telefone" error={errors.phone?.message}>
          <Input {...register("phone")} placeholder="(21) 3333-4444 (fixo ou celular)" />
        </Field>
        <Field label="WhatsApp" error={errors.whatsapp?.message}>
          <Input {...register("whatsapp")} placeholder="(21) 99999-9999" />
        </Field>
        <Field label="Email" error={errors.email?.message}>
          <Input type="email" {...register("email")} />
        </Field>
        <Field label="Instagram" error={errors.instagram?.message}>
          <Input {...register("instagram")} placeholder="@usuario" />
        </Field>
        <Field label="Facebook" error={errors.facebook?.message} className="sm:col-span-2">
          <Input {...register("facebook")} placeholder="facebook.com/usuario ou nome do perfil" />
        </Field>

        {/* Endereço em cascata: Estado → Município → Bairro (+ mapa se livre) */}
        <AddressFields
          value={address}
          onChange={setAddress}
          onCoordMissingChange={setCoordMissing}
        />

        <Field label="CEP" error={errors.cep?.message}>
          <Input {...register("cep")} placeholder="00000-000" maxLength={9} />
        </Field>
        <Field label="Aniversário" error={errors.birth_date?.message}>
          <Input type="date" {...register("birth_date")} />
        </Field>
        <Field
          label="Endereço completo (rua, número)"
          error={errors.address?.message}
          className="sm:col-span-2"
        >
          <Input {...register("address")} placeholder="Rua, número, complemento" />
        </Field>

        <Field
          label="Tags"
          className="sm:col-span-2"
        >
          <TagInput
            value={tags}
            onChange={setTags}
            suggestions={tagSuggestions}
            placeholder="ex: doador-2024, lideranca-bairro, voluntario..."
          />
        </Field>

        <DialogFooter className="sm:col-span-2 pt-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              reset(EMPTY_DEFAULTS);
              setTags([]);
              setAddress(EMPTY_ADDRESS);
              setCoordMissing(false);
              closeDialog();
            }}
          >
            Cancelar
          </Button>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Salvando..." : submitLabel}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );

  if (isEdit) {
    return (
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        {props.open && body}
      </Dialog>
    );
  }

  return (
    <Dialog
      open={createOpen}
      onOpenChange={(o) => {
        setCreateOpen(o);
        // Ao abrir, começa com o formulário limpo.
        if (o) {
          reset(EMPTY_DEFAULTS);
          setTags([]);
          setAddress(EMPTY_ADDRESS);
          setCoordMissing(false);
        }
      }}
    >
      <DialogTrigger asChild>{props.children}</DialogTrigger>
      {/* Renderiza o conteúdo só quando aberto: garante que ao fechar o
          dialog SOME na hora, sem depender da animação de saída do Radix
          (que estava travando e mantinha o modal visível). */}
      {createOpen && body}
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
