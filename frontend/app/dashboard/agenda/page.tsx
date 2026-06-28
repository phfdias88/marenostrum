"use client";

/**
 * /dashboard/agenda — agenda parlamentar/campanha geo-localizada.
 *
 * Eventos com data/hora, local e geolocalização. Lista cronológica
 * (próximos destacados, passados esmaecidos) + link "Abrir no mapa"
 * (Google Maps) por evento. Criar/editar/excluir via dialog.
 */
import {
  ArrowLeft,
  CalendarClock,
  MapPin,
  Navigation,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { AgendaEvent } from "@/lib/types";

const CATEGORIES = ["visita", "reunião", "comício", "evento", "agenda interna"];

function fmtDate(iso: string): { day: string; time: string; weekday: string } {
  const d = new Date(iso);
  return {
    day: d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }),
    time: d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
    weekday: d.toLocaleDateString("pt-BR", { weekday: "short" }),
  };
}

function mapsUrl(e: AgendaEvent): string | null {
  if (e.latitude != null && e.longitude != null) {
    return `https://www.google.com/maps/search/?api=1&query=${e.latitude},${e.longitude}`;
  }
  const parts = [e.location_name, e.address, e.city, e.state].filter(Boolean);
  if (parts.length === 0) return null;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(parts.join(", "))}`;
}

export default function AgendaPage() {
  const [items, setItems] = useState<AgendaEvent[] | null>(null);
  const [editing, setEditing] = useState<AgendaEvent | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await api<AgendaEvent[]>("/v1/agenda"));
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
      await api(`/v1/agenda/${id}`, { method: "DELETE" });
      toast.success("Evento excluído.");
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro.");
    }
  }

  const now = Date.now();
  const upcoming = (items ?? []).filter((e) => new Date(e.starts_at).getTime() >= now);
  const past = (items ?? [])
    .filter((e) => new Date(e.starts_at).getTime() < now)
    .reverse();

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-4">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Visão geral
        </Link>
        <button
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
        >
          <Plus className="w-4 h-4" /> Novo evento
        </button>
      </div>

      <header className="mb-6">
        <h1 className="text-2xl font-bold inline-flex items-center gap-2">
          <CalendarClock className="w-6 h-6 text-primary" /> Agenda
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Compromissos com local e mapa. Visitas, reuniões, comícios e eventos.
        </p>
      </header>

      {items === null ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 rounded-xl border bg-card animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState onAdd={() => setCreating(true)} />
      ) : (
        <div className="space-y-6">
          {upcoming.length > 0 && (
            <Section
              title={`Próximos (${upcoming.length})`}
              events={upcoming}
              onEdit={setEditing}
              onRemove={remove}
            />
          )}
          {past.length > 0 && (
            <Section
              title={`Realizados (${past.length})`}
              events={past}
              onEdit={setEditing}
              onRemove={remove}
              dim
            />
          )}
        </div>
      )}

      {(creating || editing) && (
        <EventDialog
          event={editing}
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

function Section({
  title,
  events,
  onEdit,
  onRemove,
  dim,
}: {
  title: string;
  events: AgendaEvent[];
  onEdit: (e: AgendaEvent) => void;
  onRemove: (id: string) => void;
  dim?: boolean;
}) {
  return (
    <section>
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
        {title}
      </h2>
      <ul className="space-y-2">
        {events.map((e) => {
          const dt = fmtDate(e.starts_at);
          const url = mapsUrl(e);
          const loc = [e.location_name, e.city && `${e.city}${e.state ? "/" + e.state : ""}`]
            .filter(Boolean)
            .join(" · ");
          return (
            <li
              key={e.id}
              className={`rounded-xl border bg-card p-3 flex items-start gap-3 ${dim ? "opacity-70" : ""}`}
            >
              <div className="shrink-0 text-center w-14 rounded-lg bg-primary/10 py-1.5">
                <p className="text-[10px] uppercase text-muted-foreground leading-none">
                  {dt.weekday}
                </p>
                <p className="text-sm font-bold text-primary leading-tight">{dt.day}</p>
                <p className="text-[11px] text-muted-foreground">{dt.time}</p>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold">{e.title}</p>
                  {e.category && (
                    <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">
                      {e.category}
                    </span>
                  )}
                </div>
                {loc && (
                  <p className="text-xs text-muted-foreground mt-0.5 inline-flex items-center gap-1">
                    <MapPin className="w-3 h-3 shrink-0" /> {loc}
                  </p>
                )}
                {e.description && (
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                    {e.description}
                  </p>
                )}
                <div className="flex items-center gap-3 mt-1.5">
                  {url && (
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      <Navigation className="w-3 h-3" /> Abrir no mapa
                    </a>
                  )}
                  <button
                    onClick={() => onEdit(e)}
                    className="text-[11px] inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                  >
                    <Pencil className="w-3 h-3" /> Editar
                  </button>
                  <button
                    onClick={() => onRemove(e.id)}
                    className="text-[11px] inline-flex items-center gap-1 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="w-3 h-3" /> Excluir
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
      <CalendarClock className="mx-auto h-9 w-9 text-muted-foreground" />
      <p className="mt-3 font-semibold">Agenda vazia</p>
      <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
        Cadastre compromissos com local e horário pra organizar visitas,
        reuniões e eventos, com link direto pro mapa.
      </p>
      <button
        onClick={onAdd}
        className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
      >
        <Plus className="w-4 h-4" /> Criar primeiro evento
      </button>
    </div>
  );
}

// ============================================================ Dialog

function EventDialog({
  event,
  onClose,
  onSaved,
}: {
  event: AgendaEvent | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!event;
  // datetime-local quer "YYYY-MM-DDTHH:mm" no fuso local
  const toLocalInput = (iso: string) => {
    const d = new Date(iso);
    const off = d.getTimezoneOffset() * 60000;
    return new Date(d.getTime() - off).toISOString().slice(0, 16);
  };
  const [title, setTitle] = useState(event?.title ?? "");
  const [startsAt, setStartsAt] = useState(
    event ? toLocalInput(event.starts_at) : "",
  );
  const [category, setCategory] = useState(event?.category ?? "");
  const [locationName, setLocationName] = useState(event?.location_name ?? "");
  const [address, setAddress] = useState(event?.address ?? "");
  const [city, setCity] = useState(event?.city ?? "");
  const [state, setState] = useState(event?.state ?? "");
  const [description, setDescription] = useState(event?.description ?? "");
  const [busy, setBusy] = useState(false);

  async function save() {
    if (title.trim().length < 2 || !startsAt) {
      toast.error("Preencha título e data/hora.");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        title: title.trim(),
        starts_at: new Date(startsAt).toISOString(),
        category: category.trim() || null,
        location_name: locationName.trim() || null,
        address: address.trim() || null,
        city: city.trim() || null,
        state: state.trim().toUpperCase() || null,
        description: description.trim() || null,
      };
      if (isEdit) {
        await api(`/v1/agenda/${event!.id}`, { method: "PUT", body: payload });
        toast.success("Evento atualizado.");
      } else {
        await api("/v1/agenda", { method: "POST", body: payload });
        toast.success("Evento criado.");
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
      className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-start justify-center pt-10 px-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl border bg-card shadow-2xl my-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold">{isEdit ? "Editar evento" : "Novo evento"}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <Field label="Título *">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={160}
              placeholder="Ex: Visita ao bairro Centro"
              className={inputCls}
              autoFocus
            />
          </Field>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Data e hora *">
              <input
                type="datetime-local"
                value={startsAt}
                onChange={(e) => setStartsAt(e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="Categoria">
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className={inputCls}
              >
                <option value="">—</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Local (nome)">
            <input
              value={locationName}
              onChange={(e) => setLocationName(e.target.value)}
              maxLength={160}
              placeholder="Praça da Matriz"
              className={inputCls}
            />
          </Field>
          <Field label="Endereço">
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              maxLength={255}
              placeholder="Rua, número"
              className={inputCls}
            />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <Field label="Cidade">
                <input
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  maxLength={100}
                  className={inputCls}
                />
              </Field>
            </div>
            <Field label="UF">
              <input
                value={state}
                onChange={(e) => setState(e.target.value)}
                maxLength={2}
                placeholder="MG"
                className={inputCls}
              />
            </Field>
          </div>
          <Field label="Observações">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={2000}
              rows={2}
              className={`${inputCls} resize-y`}
            />
          </Field>
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
            {busy ? "Salvando..." : isEdit ? "Salvar" : "Criar evento"}
          </button>
        </div>
      </div>
    </div>
  );
}

const inputCls =
  "w-full mt-1 py-2 px-3 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}
