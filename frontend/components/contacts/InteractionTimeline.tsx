"use client";

/**
 * Timeline de interacoes do contato (estilo GitHub/Stripe).
 *
 * Renderiza payload_data de forma legivel:
 *  - mensagem_recebida com {message: {text}} -> mostra o texto
 *  - fluxo_concluido com {flow: "X"} -> mostra "Concluiu fluxo X"
 *  - default -> mostra event_type + JSON colapsado (<details>)
 *
 * Estado vazio quando contato nao tem interacoes ainda.
 */
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  MessageCircle,
  PhoneIncoming,
  Send,
  Webhook,
  type LucideIcon,
} from "lucide-react";

import type { Interaction } from "@/lib/types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------- formatters


const dateFmt = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function formatTimestamp(iso: string): string {
  try {
    return dateFmt.format(new Date(iso));
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------- summarize

type Summary = {
  title: string;
  body?: string;
  icon: LucideIcon;
  tone: "default" | "success" | "info" | "muted";
};

// Procura recursivamente no payload um campo de texto candidato a mensagem.
function findFirst(
  obj: unknown,
  keys: string[],
  depth = 0,
): string | null {
  if (depth > 3 || !obj || typeof obj !== "object") return null;
  const o = obj as Record<string, unknown>;
  for (const k of keys) {
    const v = o[k];
    if (typeof v === "string" && v.trim()) return v;
  }
  for (const v of Object.values(o)) {
    if (v && typeof v === "object") {
      const found = findFirst(v, keys, depth + 1);
      if (found) return found;
    }
  }
  return null;
}

function summarize(it: Interaction): Summary {
  const type = (it.event_type ?? "").toLowerCase();
  const text = findFirst(it.payload_data, ["text", "body", "message", "content"]);

  if (type.includes("mensagem_recebida") || type === "message_received") {
    return {
      title: "Mensagem recebida",
      body: text ?? undefined,
      icon: PhoneIncoming,
      tone: "info",
    };
  }
  if (type.includes("mensagem_enviada") || type === "message_sent") {
    return {
      title: "Mensagem enviada",
      body: text ?? undefined,
      icon: Send,
      tone: "default",
    };
  }
  if (type.includes("fluxo_concluido") || type === "flow_completed") {
    const flow = findFirst(it.payload_data, ["flow", "flow_name", "name"]);
    return {
      title: flow ? `Concluiu fluxo: ${flow}` : "Fluxo concluído",
      icon: CheckCircle2,
      tone: "success",
    };
  }
  if (type.includes("mensagem") || type.includes("message")) {
    return {
      title: it.event_type ?? "Mensagem",
      body: text ?? undefined,
      icon: MessageCircle,
      tone: "info",
    };
  }
  if (!it.event_type) {
    return {
      title: "Evento recebido",
      icon: Webhook,
      tone: "muted",
    };
  }
  return {
    title: it.event_type,
    body: text ?? undefined,
    icon: Activity,
    tone: "default",
  };
}

const TONE_CLASSES: Record<Summary["tone"], string> = {
  default: "bg-card text-foreground border-border",
  success: "bg-emerald-50 text-emerald-700 border-emerald-200",
  info: "bg-brand-50 text-brand-700 border-brand-100",
  muted: "bg-muted text-muted-foreground border-border",
};

// ---------------------------------------------------------- component


export function InteractionTimeline({
  items,
  loading,
}: {
  items: Interaction[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="space-y-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex gap-4">
            <div className="h-9 w-9 rounded-full bg-muted animate-pulse" />
            <div className="flex-1 space-y-2 pt-1.5">
              <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
              <div className="h-3 w-2/3 rounded bg-muted animate-pulse" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-12 border border-dashed rounded-lg">
        <Webhook className="mx-auto h-8 w-8 text-muted-foreground" />
        <p className="mt-2 text-sm text-muted-foreground">
          Nenhuma interação ainda. Eventos do WhatsApp aparecerão aqui quando o
          BotConversa enviar webhooks pra este contato.
        </p>
      </div>
    );
  }

  return (
    <ol className="relative">
      {/* Linha vertical conectora (estilo GitHub) */}
      <div
        className="absolute left-[18px] top-2 bottom-2 w-px bg-border"
        aria-hidden
      />

      {items.map((it) => (
        <TimelineItem key={it.id} interaction={it} />
      ))}
    </ol>
  );
}


function TimelineItem({ interaction }: { interaction: Interaction }) {
  const summary = summarize(interaction);
  const Icon = summary.icon;

  return (
    <li className="relative pl-12 pb-6 last:pb-0">
      {/* Bolha do icone */}
      <span
        className={cn(
          "absolute left-0 top-0 grid h-9 w-9 place-items-center rounded-full border",
          TONE_CLASSES[summary.tone],
        )}
      >
        <Icon className="h-4 w-4" />
      </span>

      {/* Card de conteudo */}
      <div className="rounded-lg border bg-card p-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium text-sm">{summary.title}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {formatTimestamp(interaction.created_at)}
              <span className="mx-1.5">·</span>
              <span className="capitalize">{interaction.channel}</span>
              {interaction.phone && (
                <>
                  <span className="mx-1.5">·</span>
                  <span className="font-mono">{interaction.phone}</span>
                </>
              )}
            </p>
          </div>
        </div>

        {summary.body && (
          <blockquote className="mt-2 border-l-2 border-border pl-3 text-sm text-foreground/90 italic">
            {summary.body}
          </blockquote>
        )}

        {/* Raw payload (auditoria) */}
        <details className="mt-2 group">
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
            <ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" />
            Ver dados brutos
          </summary>
          <pre className="mt-2 text-xs bg-muted/50 rounded-md p-2 overflow-x-auto font-mono max-h-60">
            {JSON.stringify(interaction.payload_data, null, 2)}
          </pre>
        </details>
      </div>
    </li>
  );
}
