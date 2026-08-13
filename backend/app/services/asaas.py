"""
Cliente HTTP da API do Asaas (v3) — cobrança recorrente (assinatura).

Auth por header `access_token` (NÃO Bearer). `User-Agent` é obrigatório. Base
URL vem de ASAAS_ENV (produção vs sandbox) — chave e base TÊM que ser do mesmo
ambiente, senão 401.

Só a parte que a gente usa: criar cliente, criar assinatura mensal, pegar a URL
de pagamento da 1ª fatura (a assinatura NÃO devolve link — é um segundo GET
/subscriptions/{id}/payments), cancelar assinatura (DELETE — usado no teste de
produção de risco mínimo). 100% mockável: os testes injetam um fake sem rede.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.config import get_settings

_TIMEOUT = 30.0


class AsaasError(Exception):
    """Falha de comunicação/negócio com o Asaas (status != 2xx ou payload ruim)."""

    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class AsaasClient:
    def __init__(self, *, api_key: str, base_url: str, user_agent: str, timeout: float = _TIMEOUT):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._headers = {
            "access_token": api_key,
            "Content-Type": "application/json",
            # Obrigatório na API do Asaas (contas pós-11/06/2024) — sem isso bloqueia.
            "User-Agent": user_agent,
        }

    def _request(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as c:
                # GET NUNCA leva body (o Asaas responde 403 a GET com corpo).
                resp = c.request(method, url, headers=self._headers, json=json, params=params)
        except httpx.HTTPError as exc:
            raise AsaasError(f"Falha de rede com o Asaas: {exc}") from exc
        if resp.status_code // 100 != 2:
            body: Any
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            raise AsaasError(
                f"Asaas retornou {resp.status_code} em {method} {path}",
                status_code=resp.status_code,
                body=body,
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise AsaasError("Resposta do Asaas não é JSON") from exc

    # ------------------------------ Clientes ------------------------------
    def create_customer(
        self,
        *,
        name: str,
        cpf_cnpj: str,
        email: str | None = None,
        mobile_phone: str | None = None,
        external_reference: str | None = None,
    ) -> dict:
        payload = {"name": name, "cpfCnpj": cpf_cnpj}
        if email:
            payload["email"] = email
        if mobile_phone:
            payload["mobilePhone"] = mobile_phone
        if external_reference:
            payload["externalReference"] = external_reference
        return self._request("POST", "/customers", json=payload)

    # ----------------------------- Assinaturas ----------------------------
    def create_subscription(
        self,
        *,
        customer_id: str,
        value: float,
        next_due_date: str | None = None,
        cycle: str = "MONTHLY",
        billing_type: str = "UNDEFINED",
        description: str | None = None,
        external_reference: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "customer": customer_id,
            "billingType": billing_type,
            "value": value,
            "nextDueDate": next_due_date or date.today().isoformat(),
            "cycle": cycle,
        }
        if description:
            payload["description"] = description[:500]
        if external_reference:
            payload["externalReference"] = external_reference
        return self._request("POST", "/subscriptions", json=payload)

    def get_subscription_payments(self, subscription_id: str, *, status: str | None = None) -> list[dict]:
        params = {"status": status} if status else None
        data = self._request("GET", f"/subscriptions/{subscription_id}/payments", params=params)
        return list(data.get("data", []))

    def first_invoice_url(self, subscription_id: str) -> str | None:
        """URL da página de pagamento da 1ª fatura. A cobrança é gerada de forma
        assíncrona logo após criar a assinatura — 1 retry se vier vazia."""
        for _ in range(2):
            payments = self.get_subscription_payments(subscription_id)
            if payments:
                return payments[0].get("invoiceUrl")
        return None

    def delete_subscription(self, subscription_id: str) -> dict:
        """Cancela a assinatura (e as cobranças pendentes). Usado no cancelamento
        e no teste de produção de risco mínimo. NÃO é estorno de cobrança paga."""
        return self._request("DELETE", f"/subscriptions/{subscription_id}")


def get_asaas_client() -> AsaasClient:
    """Fábrica a partir das settings. Levanta AsaasError se a chave não estiver
    configurada (billing desligado) — o caller devolve 503/erro amigável."""
    s = get_settings()
    if not s.ASAAS_API_KEY:
        raise AsaasError("Billing indisponível: ASAAS_API_KEY não configurada.")
    return AsaasClient(
        api_key=s.ASAAS_API_KEY,
        base_url=s.asaas_base_url,
        user_agent=s.ASAAS_USER_AGENT,
    )
