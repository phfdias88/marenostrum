"use client";

/**
 * TagInput — input de chips controlado.
 *
 * Comportamento:
 * - Enter / vírgula adicionam a tag corrente
 * - Backspace em campo vazio remove a última
 * - Normaliza no client (lowercase, slug) — espelha _normalize_tag do backend
 * - Sugestões de tags já usadas no tenant (chip clicável) abaixo
 *
 * Dedup, validação e limite final ocorrem no servidor (Pydantic), mas
 * normalizamos no client pra evitar UX confusa (digita "Doador" → vira "doador").
 */
import { X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

const MAX_TAGS = 16;

function normalizeTag(raw: string): string {
  // Remove acentos, lowercase, espaço/non-slug → "-"
  const noAccents = raw.normalize("NFKD").replace(/[̀-ͯ]/g, "");
  return noAccents
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
}

type Props = {
  value: string[];
  onChange: (next: string[]) => void;
  /** Sugestões clicáveis (ex: tags já usadas no tenant). */
  suggestions?: string[];
  placeholder?: string;
};

export function TagInput({ value, onChange, suggestions = [], placeholder }: Props) {
  const [draft, setDraft] = useState("");

  function add(raw: string) {
    const norm = normalizeTag(raw);
    if (!norm) return;
    if (value.includes(norm)) return;
    if (value.length >= MAX_TAGS) return;
    onChange([...value, norm]);
    setDraft("");
  }

  function remove(t: string) {
    onChange(value.filter((x) => x !== t));
  }

  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
    } else if (e.key === "Backspace" && !draft && value.length) {
      remove(value[value.length - 1]);
    }
  }

  const free = suggestions.filter((s) => !value.includes(s)).slice(0, 12);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5 min-h-10 rounded-md border border-input bg-background px-2 py-1.5 focus-within:ring-2 focus-within:ring-primary/30">
        {value.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/15 text-primary text-xs font-medium"
          >
            {t}
            <button
              type="button"
              onClick={() => remove(t)}
              className="hover:text-foreground"
              aria-label={`Remover tag ${t}`}
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKey}
          onBlur={() => draft && add(draft)}
          placeholder={value.length ? "" : placeholder ?? "Digite uma tag e Enter..."}
          className="flex-1 min-w-32 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          maxLength={32}
        />
      </div>
      {free.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground self-center mr-1">
            Já usadas:
          </span>
          {free.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => add(s)}
              className="px-2 py-0.5 rounded-full border border-border text-xs text-muted-foreground hover:text-foreground hover:border-primary/50"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
