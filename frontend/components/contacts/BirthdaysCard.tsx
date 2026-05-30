"use client";

/**
 * BirthdaysCard — widget de aniversariantes pro /dashboard.
 *
 * Mostra:
 * - Quem faz hoje (badge "HOJE")
 * - Próximos 6 dias (semana)
 * - Botão "Parabenizar" abre WhatsApp com mensagem pronta
 *
 * Quando vazio mostra estado amigável (não polui o dashboard).
 */
import { Cake, MessageCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { BirthdayContact } from "@/lib/types";

// Apenas dígitos — pra urls wa.me/<n>
function digits(phone: string | null): string | null {
  if (!phone) return null;
  const d = phone.replace(/\D/g, "");
  return d.length >= 10 ? d : null;
}

function waUrl(phone: string | null, fullName: string, ageTurning: number | null): string | null {
  const d = digits(phone);
  if (!d) return null;
  // Brasil: prepend 55 se não vier com código
  const intl = d.startsWith("55") ? d : `55${d}`;
  const first = fullName.split(" ")[0];
  const idade = ageTurning ? ` ${ageTurning} anos` : "";
  const msg = encodeURIComponent(
    `Olá ${first}! 🎉 Parabéns pelo seu aniversário${idade}! Muita saúde, alegria e realizações. Conte com a gente sempre!`,
  );
  return `https://wa.me/${intl}?text=${msg}`;
}

function dayLabel(d: number): string {
  if (d === 0) return "Hoje";
  if (d === 1) return "Amanhã";
  return `Em ${d} dias`;
}

export function BirthdaysCard() {
  const [items, setItems] = useState<BirthdayContact[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api<BirthdayContact[]>("/v1/contacts/birthdays?days_ahead=6")
      .then(setItems)
      .catch(() => setError(true));
  }, []);

  const today = items?.filter((b) => b.days_until === 0) ?? [];
  const upcoming = items?.filter((b) => b.days_until > 0) ?? [];

  return (
    <div className="rounded-xl border bg-card p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Cake className="h-4 w-4 text-rose-500" />
          Aniversariantes da semana
        </div>
        <Link
          href="/dashboard/contacts"
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Ver todos
        </Link>
      </div>

      {error ? (
        <p className="text-xs text-muted-foreground">Não foi possível carregar.</p>
      ) : items === null ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-10 bg-muted rounded animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Nenhum aniversariante essa semana. Cadastre datas de nascimento nos
          contatos para receber lembretes aqui.
        </p>
      ) : (
        <ul className="space-y-2">
          {[...today, ...upcoming].slice(0, 6).map((b) => {
            const url = waUrl(b.phone, b.full_name, b.age_turning);
            return (
              <li
                key={b.id}
                className="flex items-center gap-2 rounded-md border border-border/60 bg-background/30 px-2.5 py-2"
              >
                <span
                  className={`inline-flex shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold ${
                    b.days_until === 0
                      ? "bg-rose-500/20 text-rose-600"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {dayLabel(b.days_until).toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{b.full_name}</p>
                  {b.age_turning && (
                    <p className="text-[11px] text-muted-foreground">
                      Faz {b.age_turning} anos
                    </p>
                  )}
                </div>
                {url ? (
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 hover:underline shrink-0"
                    title="Parabenizar via WhatsApp"
                  >
                    <MessageCircle className="h-3.5 w-3.5" />
                    Parabenizar
                  </a>
                ) : (
                  <span className="text-[11px] text-muted-foreground shrink-0">
                    Sem celular
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
