/** @type {import('next').NextConfig} */
module.exports = {
  // standalone gera um build minimo (server.js + .next/standalone),
  // crucial para VPS pequena: imagem ~150MB ao inves de ~1GB.
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
};
