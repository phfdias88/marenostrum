"use client";

/**
 * Bloco de perfil rico: patrimonio declarado + redes sociais.
 * Dados do TSE (bem_candidato + rede_social_candidato).
 */
import {
  Facebook,
  Globe,
  Instagram,
  Linkedin,
  Twitter,
  Wallet,
  Youtube,
} from "lucide-react";

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});

function iconFor(url: string) {
  const u = url.toLowerCase();
  if (u.includes("instagram")) return Instagram;
  if (u.includes("facebook")) return Facebook;
  if (u.includes("twitter") || u.includes("x.com")) return Twitter;
  if (u.includes("youtube")) return Youtube;
  if (u.includes("linkedin")) return Linkedin;
  return Globe;
}

function label(url: string) {
  const u = url.toLowerCase();
  if (u.includes("instagram")) return "Instagram";
  if (u.includes("facebook")) return "Facebook";
  if (u.includes("twitter") || u.includes("x.com")) return "Twitter/X";
  if (u.includes("youtube")) return "YouTube";
  if (u.includes("linkedin")) return "LinkedIn";
  if (u.includes("tiktok")) return "TikTok";
  return "Site";
}

export function CandidateProfile({
  assetsTotal,
  socialLinks,
}: {
  assetsTotal: number | null;
  socialLinks: string[] | null;
}) {
  const hasAssets = assetsTotal != null && assetsTotal > 0;
  const links = (socialLinks ?? []).filter(Boolean);
  if (!hasAssets && links.length === 0) return null;

  return (
    <div className="space-y-3">
      {hasAssets && (
        <div className="flex items-center gap-2 rounded-md bg-card/60 border border-border p-3">
          <Wallet className="w-4 h-4 text-primary shrink-0" />
          <div>
            <p className="text-xs text-muted-foreground">
              Patrimônio declarado
            </p>
            <p className="font-bold text-primary">{brl.format(assetsTotal!)}</p>
          </div>
        </div>
      )}

      {links.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1.5">
            Redes sociais
          </p>
          <div className="flex flex-wrap gap-2">
            {links.map((url) => {
              const Icon = iconFor(url);
              return (
                <a
                  key={url}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-border bg-card hover:border-primary/60 hover:text-primary text-xs transition-colors"
                >
                  <Icon className="w-3.5 h-3.5" />
                  {label(url)}
                </a>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
