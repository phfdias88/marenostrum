"""
Normalizacao de telefone (fundacao do auto-vinculo do webhook).

PROBLEMA: o CRM grava o telefone como veio ("(21) 99999-1234") e o
BotConversa manda "5521999991234" — igualdade exata NUNCA casa. A regra
canonica mora aqui e e' espelhada em SQL puro na migration 054 (backfill).

REGRA (normalize_phone):
1. So' digitos.
2. Se comeca com "55" e tem 12-13 digitos, e' DDI Brasil -> remove o "55"
   (12 = DDD + fixo 8, 13 = DDD + celular 9). 10-11 digitos comecando com
   55 sao DDD 55 (regiao de Santa Maria/RS) — NAO remove.
3. Menos de 8 digitos sobrando = nao e' telefone util -> None.
"""
import re

_NON_DIGITS = re.compile(r"\D+")

# Tamanho da coluna contacts.phone_normalized (migration 054).
_MAX_LEN = 20


def normalize_phone(raw: str | None) -> str | None:
    """'(21) 99999-1234' -> '21999991234'; '5521999991234' -> '21999991234'."""
    if not raw:
        return None
    digits = _NON_DIGITS.sub("", raw)
    # DDI Brasil: 55 + DDD(2) + numero(8-9) = 12-13 digitos.
    if digits.startswith("55") and 12 <= len(digits) <= 13:
        digits = digits[2:]
    if len(digits) < 8:
        return None
    # Defensiva: cabe na coluna varchar(20) mesmo com lixo de input.
    return digits[:_MAX_LEN]


def mask_phone(raw: str | None) -> str | None:
    """
    Mascara pra log/UI: so' os 4 ultimos digitos ("***1234").
    Telefone de eleitor e' PII (LGPD) — nunca logar em claro.
    """
    if not raw:
        return None
    digits = _NON_DIGITS.sub("", raw)
    if not digits:
        return "***"
    return f"***{digits[-4:]}"
