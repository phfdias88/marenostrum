/** @type {import('next').NextConfig} */
module.exports = {
  // standalone gera um build minimo (server.js + .next/standalone),
  // crucial para VPS pequena: imagem ~150MB ao inves de ~1GB.
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,

  compiler: {
    // Remove console.* do bundle de producao (mantem error/warn pra erros
    // reais ainda aparecerem). Reduz JS + evita vazar logs de debug.
    removeConsole: { exclude: ['error', 'warn'] },
  },

  experimental: {
    // Tree-shaking agressivo de barrel imports. lucide-react e Radix sao os
    // maiores ofensores: `import { X } from "lucide-react"` puxava o barrel
    // inteiro. Next reescreve pra imports diretos por icone/modulo, cortando
    // KBs grandes do bundle de cada rota.
    optimizePackageImports: [
      'lucide-react',
      '@tanstack/react-table',
      '@radix-ui/react-alert-dialog',
      '@radix-ui/react-dialog',
      '@radix-ui/react-dropdown-menu',
      '@radix-ui/react-tabs',
      'sonner',
    ],
  },

  // Source maps de producao desligados (default, mas explicito): bundle
  // menor servido ao cliente.
  productionBrowserSourceMaps: false,
};
