"""
Pipeline de enriquecimento de coordenadas de Locais de Votação (100% grátis).

Quando um Local de Votação vem do TSE sem coordenada válida (nula ou fora da
bounding-box do Brasil), tentamos "salvar" a coordenada ANTES de desistir e
jogá-lo na lista de Não Mapeados:

  PASSO A (ViaCEP): se o endereço trouxer um CEP (o TSE às vezes o embute na
    string livre `DS_ENDERECO`), consultamos a API gratuita do ViaCEP para
    obter logradouro/bairro/localidade/uf limpos.
  PASSO B (Nominatim/OSM): concatenamos o NOME do local (ex.: "CIEP 123") com
    o endereço qualificado e geocodificamos via Nominatim — reusando
    `app.utils.geocoding.geocode`, que já aplica o rate limit de 1s, timeout e
    User-Agent exigidos pelo OSM.

Robustez: CADA passo é protegido por try/except. Timeout do ViaCEP, CEP
inválido ou erro do Nominatim NUNCA quebram o lote de importação — no pior
caso a função devolve None e o local cai na lista de Não Mapeados.

Nota: o TseVotingPlace NÃO tem campo de CEP próprio (o CSV do TSE não traz
CEP); por isso o CEP é EXTRAÍDO da string de endereço quando presente. Sem
CEP, pulamos direto pro Nominatim com nome + endereço + bairro + município.
"""
from __future__ import annotations

import re

import httpx

from app.utils.geocoding import geocode

# CEP brasileiro: 5 dígitos + 3, com separador opcional (- . espaço).
_CEP_RE = re.compile(r"(\d{5})[-.\s]?(\d{3})")
_VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
_VIACEP_TIMEOUT = 8.0


def extract_cep(text: str | None) -> str | None:
    """Extrai um CEP (8 dígitos) de uma string de endereço, se houver."""
    if not text:
        return None
    m = _CEP_RE.search(text)
    return (m.group(1) + m.group(2)) if m else None


async def lookup_viacep(cep: str | None) -> dict | None:
    """
    Consulta o ViaCEP. Retorna dict {logradouro, bairro, localidade, uf} ou
    None (CEP inválido, não encontrado, timeout ou erro de rede). Nunca levanta.
    """
    digits = re.sub(r"\D", "", cep or "")
    if len(digits) != 8:
        return None
    try:
        async with httpx.AsyncClient(timeout=_VIACEP_TIMEOUT) as client:
            resp = await client.get(_VIACEP_URL.format(cep=digits))
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, dict) or data.get("erro"):
            return None
        return {
            "logradouro": (data.get("logradouro") or "").strip(),
            "bairro": (data.get("bairro") or "").strip(),
            "localidade": (data.get("localidade") or "").strip(),
            "uf": (data.get("uf") or "").strip(),
        }
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def build_query(
    *,
    name: str | None,
    address: str | None,
    neighborhood: str | None,
    municipality: str | None,
    uf: str | None,
    viacep: dict | None,
) -> str | None:
    """
    Monta a string altamente qualificada pro Nominatim, preferindo os campos
    limpos do ViaCEP quando disponíveis. Retorna None se não houver conteúdo
    útil o suficiente (só "Brasil" não geocodifica nada).
    """
    logradouro = (viacep or {}).get("logradouro") or address
    bairro = (viacep or {}).get("bairro") or neighborhood
    cidade = (viacep or {}).get("localidade") or municipality
    estado = (viacep or {}).get("uf") or uf

    parts = [p.strip() for p in (name, logradouro, bairro, cidade, estado) if p and p.strip()]
    # Precisa de pelo menos cidade OU (nome/logradouro) + algo — senão o
    # Nominatim devolveria qualquer coisa. Exigimos >= 2 componentes úteis.
    if len(parts) < 2:
        return None
    parts.append("Brasil")
    return ", ".join(parts)


async def enrich_location(
    *,
    name: str | None,
    address: str | None,
    neighborhood: str | None,
    municipality: str | None,
    uf: str | None,
) -> tuple[float, float] | None:
    """
    Tenta recuperar (lat, lng) de um Local de Votação sem coordenada válida.

    Fluxo: extrai CEP do endereço → ViaCEP (se houver CEP) → monta query
    qualificada → Nominatim. Devolve (lat, lng) se o Nominatim achou, ou None.
    NUNCA levanta exceção — seguro pra rodar em lote.
    """
    try:
        cep = extract_cep(address)
        viacep = await lookup_viacep(cep) if cep else None
        query = build_query(
            name=name,
            address=address,
            neighborhood=neighborhood,
            municipality=municipality,
            uf=uf,
            viacep=viacep,
        )
        if not query:
            return None
        # geocode() já faz throttle de 1s, timeout e User-Agent do Nominatim.
        return await geocode(query)
    except Exception:
        return None
