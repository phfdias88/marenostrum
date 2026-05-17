"use client";

import { useEffect, useState } from "react";

/**
 * Atrasa a atualizacao de um valor — util para campo de busca que dispara
 * fetch na API: o usuario digita, mas so rodamos a query quando ele para.
 */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}
