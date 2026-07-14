// basePath vem do ambiente de BUILD (Next embute em build time). VAZIO =
// servido na raiz (padrao atual). Setar NEXT_PUBLIC_BASE_PATH=/sistema no
// corte pro subdiretorio. Uma linha, sem duplicar o valor pelo codigo: o
// mesmo var alimenta o config aqui E as URLs manuais (cookie, deep-links).
// `basePath` prefixa AUTOMATICAMENTE: <Link>, useRouter().push, next/image,
// _next/static e /public. So URLs montadas "na mao" (document.cookie Path,
// window.location.href cru) precisam do prefixo explicito.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';

/** @type {import('next').NextConfig} */
module.exports = {
  // standalone gera um build minimo (server.js + .next/standalone),
  // crucial para VPS pequena: imagem ~150MB ao inves de ~1GB.
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  ...(basePath ? { basePath } : {}),

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
    // NOTA: @tanstack/react-table foi REMOVIDO desta lista — o build ESM
    // dele (index.esm.js) quebra o parser do Next 14.2 com este otimizador
    // ("'import' and 'export' may appear only with 'sourceType: module'").
    // lucide-react é o maior ganho de qualquer forma.
    optimizePackageImports: [
      'lucide-react',
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
