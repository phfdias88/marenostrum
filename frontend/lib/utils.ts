import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// bg-<cor> passado via className deve APAGAR o gradiente do variant default do
// Button (bg-gradient-to-b from-primary...). Sem este conflito registrado, o
// tailwind-merge mantém o gradiente (grupo bg-image) junto do bg-color novo e o
// background-image DOURADO pinta por cima do vermelho/verde — os "Excluir" e o
// CTA do WhatsApp ficavam dourados. Validado com o tailwind-merge 2.5.4 do repo.
const twMerge = extendTailwindMerge({
  extend: {
    conflictingClassGroups: {
      "bg-color": ["bg-image", "gradient-from", "gradient-via", "gradient-to"],
    },
  },
});

/**
 * Helper padrao shadcn: junta classes condicionais (clsx)
 * e resolve conflitos de Tailwind (twMerge) numa string só.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
