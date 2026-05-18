"""
Converte votos_adriana_kutwak.csv (locais de votacao) pro formato esperado
pelo CRM MareNostrum (cadastro de contatos).

Mapeamento:
  'Local de Votacao'  -> Nome (obrigatorio no CRM)
  'Endereco'          -> Endereco
  'Bairro'            -> Bairro
  'Municipio'         -> Cidade
  'Latitude'          -> Latitude (preenchida — nao chama Nominatim)
  'Longitude'         -> Longitude (idem)
  'Votos'             -> Observacoes ("X votos para Adriana Kutwak")
  fixo                -> Tipo='Outro', UF='RJ'

Phone fica vazio — todos seriam "" e o unique constraint do DB nao
permitiria muitas duplicatas (NULL nao conflita com NULL em PG, mas
melhor garantir).
"""
import csv
import sys
from pathlib import Path

SRC = Path(r"C:\Users\PAULO-ASUS\Downloads\votos_adriana_kutwak.csv")
DST = Path(r"C:\Users\PAULO-ASUS\Downloads\contatos_locais_votacao.csv")

if not SRC.exists():
    sys.exit(f"ERRO: nao achei {SRC}")

# Cabecalhos do CRM (PT-BR; parser do MareNostrum reconhece via HEADER_MAP)
# Latitude/Longitude agora suportadas → pins direto no mapa, sem geocoding
OUT_HEADERS = [
    "Nome", "Telefone", "Email", "Endereço", "Bairro",
    "Cidade", "UF", "Tipo", "Latitude", "Longitude", "Observações"
]

count_in = 0
count_out = 0
skipped = 0

with SRC.open(encoding="utf-8-sig", newline="") as f_in:
    # Sniff dialect — esse arquivo usa ;
    reader = csv.DictReader(f_in, delimiter=";")

    with DST.open("w", encoding="utf-8-sig", newline="") as f_out:
        writer = csv.DictWriter(
            f_out, fieldnames=OUT_HEADERS, delimiter=";", quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()

        for row in reader:
            count_in += 1
            nome = (row.get("Local de Votação") or "").strip()
            if not nome:
                skipped += 1
                continue

            votos = (row.get("Votos") or "0").strip()
            try:
                votos_int = int(votos)
            except ValueError:
                votos_int = 0

            obs = f"{votos_int} voto(s) para Adriana Kutwak"
            lat = (row.get("Latitude") or "").strip()
            lng = (row.get("Longitude") or "").strip()

            writer.writerow({
                "Nome": nome[:150],  # CRM limita a 150 chars
                "Telefone": "",
                "Email": "",
                "Endereço": (row.get("Endereço") or "").strip()[:255],
                "Bairro": (row.get("Bairro") or "").strip()[:100],
                "Cidade": (row.get("Município") or "").strip()[:100],
                "UF": "RJ",
                "Tipo": "Outro",
                "Latitude": lat,
                "Longitude": lng,
                "Observações": obs[:1000],
            })
            count_out += 1

print(f"Lidos:       {count_in}")
print(f"Pulados:     {skipped} (sem nome)")
print(f"Convertidos: {count_out}")
print(f"Saida:       {DST}")
print()
print("ATENCAO: Latitude/Longitude do CSV original viraram texto na coluna")
print("'Observações'. O parser do CRM IGNORA lat/lng aqui porque os")
print("cabecalhos 'Nome,Telefone,Email,Endereco,Bairro,Cidade,UF,Tipo,Obs'")
print("nao incluem campos numericos de coordenadas.")
print("Pra usar lat/lng e ver pins no mapa, precisa endpoint diferente")
print("(ou geocoding em background apos importar).")
