"use client";

/**
 * Marca MareNostrum (monograma "M" dourado).
 *
 * Usa /logo-mark.png se existir em public/ (logo oficial enviado pelo
 * usuario). Enquanto nao existir, cai num SVG aproximado em dourado.
 * Assim que o arquivo for adicionado, aparece automaticamente.
 */
import { useState } from "react";

export function BrandMark({ className = "w-10 h-10" }: { className?: string }) {
  const [useImg, setUseImg] = useState(true);

  if (useImg) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src="/logo-mark.png"
        alt="MareNostrum"
        className={`${className} object-contain`}
        onError={() => setUseImg(false)}
      />
    );
  }

  // Fallback SVG: M angular dourado com triangulo interno (estilo monograma)
  return (
    <svg
      viewBox="0 0 100 116"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="MareNostrum"
    >
      <defs>
        <linearGradient id="mn-gold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#f3e4a8" />
          <stop offset="45%" stopColor="#d4af52" />
          <stop offset="100%" stopColor="#a9802f" />
        </linearGradient>
      </defs>
      {/* M angular: dois pilares + V central + perna direita formando triangulo */}
      <path
        fill="url(#mn-gold)"
        d="M2 4 h22 l26 40 26-40 h22 v108 h-22 V46 l-20 31 h-12 L24 46 v66 H2 Z"
      />
      {/* recorte triangular interno (negative space) na direita */}
      <path
        fill="#1c1b1a"
        d="M74 60 l14 21 v-21 Z"
      />
    </svg>
  );
}
