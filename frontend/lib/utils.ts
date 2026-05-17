import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Helper padrao shadcn: junta classes condicionais (clsx)
 * e resolve conflitos de Tailwind (twMerge) numa string só.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
