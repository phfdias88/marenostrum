"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { clearAuth } from "@/lib/auth";

type Contact = {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  city: string | null;
  state: string | null;
  type: string;
  created_at: string;
};

export default function ContactsPage() {
  const router = useRouter();
  const [items, setItems] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Contact[]>("/v1/contacts?limit=50")
      .then(setItems)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearAuth();
          router.replace("/login");
          return;
        }
        setError(err instanceof ApiError ? err.message : "Erro ao carregar.");
      })
      .finally(() => setLoading(false));
  }, [router]);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <main className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex justify-between items-center">
          <h1 className="text-xl font-semibold text-brand-900">Contatos</h1>
          <button
            onClick={logout}
            className="text-sm text-slate-600 hover:text-slate-900"
          >
            Sair
          </button>
        </div>
      </header>

      <section className="max-w-5xl mx-auto px-6 py-8">
        {loading && <p className="text-slate-500">Carregando...</p>}
        {error && (
          <p className="text-red-600 bg-red-50 border border-red-200 rounded-md p-3">
            {error}
          </p>
        )}
        {!loading && !error && items.length === 0 && (
          <p className="text-slate-500">
            Nenhum contato ainda. Cadastre via{" "}
            <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded">
              POST /api/v1/contacts
            </code>
            .
          </p>
        )}
        {items.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-600">
                <tr>
                  <th className="px-4 py-3">Nome</th>
                  <th className="px-4 py-3">Telefone</th>
                  <th className="px-4 py-3">Cidade/UF</th>
                  <th className="px-4 py-3">Tipo</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} className="border-t border-slate-100">
                    <td className="px-4 py-3 font-medium">{c.full_name}</td>
                    <td className="px-4 py-3 text-slate-600">{c.phone ?? "-"}</td>
                    <td className="px-4 py-3 text-slate-600">
                      {[c.city, c.state].filter(Boolean).join("/") || "-"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-brand-50 text-brand-700 px-2 py-1 rounded-full">
                        {c.type}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
