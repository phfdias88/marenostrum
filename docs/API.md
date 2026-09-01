# API MareNostrum — guia de acesso aos dados

Documento de uso interno da MareNostrum. Explica como puxar dados do sistema
por fora da tela: BI, planilha, script ou outro sistema.

---

## 1. Por que API e não FTP

A pergunta original era "API ou FTP". A resposta é API, e vale registrar o porquê:

| | FTP | API com chave |
|---|---|---|
| Senha | trafega em texto puro | nunca trafega senha |
| Quem vê o quê | quem entra vê o diretório | cada chave só enxerga a campanha dela |
| Registro | não diz quem baixou | grava data e contagem de uso |
| Cortar acesso | trocar a senha derruba todos | revogar uma chave, efeito imediato |
| Atualidade | arquivo gerado ontem | consulta o banco agora |

O FTP ainda exigiria exportar cópias do banco para arquivos — que envelhecem
no mesmo dia e viram uma segunda fonte de verdade para manter.

---

## 2. Como autenticar

Toda chamada leva a chave num cabeçalho:

```
X-API-Key: mn_live_xxxxxxxxxxxxxxxxxxxxxxxx
```

Exemplo completo:

```bash
curl -H "X-API-Key: SUA_CHAVE" "https://marenostrumconsult.com.br/sistema/api/v1/tse/stats/counts?year=2024"
```

**Três regras que a chave sempre obedece:**

1. **Somente leitura.** Tentar criar, alterar ou apagar devolve `403`. A trava
   fica no portão de entrada, não em cada rota — então rota nova já nasce
   protegida, sem ninguém precisar lembrar.
2. **Não atravessa campanhas.** A chave pertence a uma campanha e só enxerga
   os dados dela — a mesma regra de isolamento do login normal.
3. **Revogável na hora.** Cortar o acesso é imediato e não mexe na senha de
   ninguém.

Respostas de autenticação:

| Código | Significa |
|---|---|
| `200` | tudo certo |
| `401` | chave inexistente, revogada ou vencida |
| `403` | tentou escrever com chave de leitura |
| `429` | muitas chamadas em pouco tempo |

---

## 3. Árvore de dados — o que dá para puxar

Base de todas as URLs:
`https://marenostrumconsult.com.br/sistema/api/v1`

### 3.1 Eleições (TSE) — dado público, 2002 a 2024

| Caminho | O que devolve |
|---|---|
| `/tse/candidates?search=nome` | busca por nome ou nome de urna |
| `/tse/candidates?year=2024&office_code=11&state=RJ` | filtra por ano, cargo e UF |
| `/tse/candidates/{id}` | ficha completa: partido, patrimônio, votação |
| `/tse/candidates/{id}/results` | votos por município |
| `/tse/candidates/{id}/by-zone` | votos por zona eleitoral |
| `/tse/candidates/{id}/by-neighborhood?municipality_id=…` | votos por bairro |
| `/tse/candidates/{id}/trajectory` | histórico de candidaturas da pessoa |
| `/tse/stats/counts?year=2024` | totais de candidatos, municípios e partidos |
| `/tse/stats/top-candidates?year=2024&office_code=13` | mais votados |
| `/tse/stats/winners-map?year=2024&office_code=11` | vencedor por município |
| `/tse/stats/party-performance?year=2024&office_code=11` | desempenho por partido |
| `/tse/stats/aggregated-votes?uf=SP&year=2024&office_code=11` | **votos já somados por município** |
| `/tse/stats/aggregated-votes?…&municipality_id=…` | **votos já somados por bairro** |
| `/tse/parties` | lista de partidos |
| `/tse/municipalities` | municípios com código IBGE e TSE |

### Votos já somados (para painel e BI)

`/tse/stats/aggregated-votes` devolve o dado agregado, sem cálculo do lado de quem
consome. O escopo decide a granularidade:

- **sem `municipality_id`** → soma por **município** (2014–2024, Brasil, número exato)
- **com `municipality_id`** → soma por **bairro** (2024 no Brasil; 2018/2020/2022 só no RJ)

```bash
curl -H "X-API-Key: SUA_CHAVE"   ".../v1/tse/stats/aggregated-votes?uf=SP&year=2024&office_code=11&limit=5"
```

```json
{ "escopo": "municipio", "dados_confiaveis": true,
  "itens": [ { "municipio": "SÃO PAULO", "bairro": null, "total_votos": 6109051 } ] }
```

Dois avisos que a própria resposta carrega:

- **`dados_confiaveis`** diz, **por município**, se a divisão por bairro pode ser
  usada. Vem `true` em 5.382 dos 5.569 municípios. Vem `false` em 187 — as
  capitais e cidades grandes —, onde locais de zonas eleitorais diferentes com o
  mesmo número foram gravados como um só e parte dos votos aparece no bairro
  vizinho (São Paulo tinha 160 locais no lugar de 2.062; o Rio, 163 no lugar de
  1.440). O total do município continua certo nos dois casos. O campo volta a
  `true` sozinho conforme cada estado é reimportado com a zona na chave.
- **Não há filtro de turno**, de propósito: a base só tem votação de 1º turno, e
  quem foi ao 2º turno fica num registro separado carregando os votos do 1º.
  Filtrar por turno esconderia os dois mais votados de toda cidade que teve
  segundo turno.

**Códigos de cargo:** `1` presidente · `3` governador · `5` senador ·
`6` deputado federal · `7` deputado estadual · `11` prefeito · `13` vereador

> Candidaturas existem de 2002 a 2024, mas **voto por município só de 2014 em
> diante**. Antes disso a consulta responde vazia — não é erro.

### 3.2 Censo e socioeconômico (IBGE, MDS, INEP) — Brasil inteiro

| Caminho | O que devolve |
|---|---|
| `/census/municipalities` | os 5.570 municípios com dado censitário |
| `/census/uf-overview?uf=33` | municípios de uma UF em GeoJSON |
| `/census/setores?cd_mun=3304557` | setores censitários do município em GeoJSON |
| `/census/malha?cd_mun=3304557&level=bairro` | contornos de bairro ou distrito |
| `/census/mds-series?cd_mun=3304557` | série mensal de CadÚnico e Bolsa Família |
| `/census/search-areas?q=copacabana` | busca bairros e distritos pelo nome |

**Indicadores:** população, domicílios, sexo, 11 faixas etárias, cor/raça,
alfabetização, renda do responsável, água, esgoto, lixo, PIB per capita, IDHM,
IDEB, CadÚnico e Bolsa Família.

**Granularidade:** município (5.570), setor censitário (468.099) e — onde o
IBGE publica — bairro. Fora das cidades grandes o recorte intermediário é o
distrito: o IBGE só mapeia bairro em 16% dos municípios.

### 3.3 CRM da campanha — dado privado, isolado por cliente

| Caminho | O que devolve |
|---|---|
| `/contacts` | contatos da campanha, paginado e com filtros |
| `/contacts/{id}` | ficha do contato |
| `/contacts/{id}/interactions` | histórico de contatos com a pessoa |
| `/contacts/map` | contatos com coordenadas, para mapa |
| `/contacts/map-aggregate?group_by=neighborhood` | contagem por bairro |
| `/contacts/birthdays` | aniversariantes |
| `/contacts/tags` | tags em uso |
| `/demands` | demandas, paginado |
| `/demands/stats` | contagem por status |
| `/agenda` | eventos da agenda |

> Estes carregam **dados pessoais de eleitores**. A chave só devolve os da
> campanha dona dela, mas quem consome assume o mesmo cuidado de LGPD que o
> sistema tem.

### 3.4 Serviço

| Caminho | O que devolve |
|---|---|
| `/api/health` | o serviço está de pé |
| `/api/ready` | o serviço e o banco respondem |

> Duas rotas **não** atendem chave de API, de propósito: `/auth/me` e `/audit`
> respondem a sessão humana apenas. A chave não tem identidade própria — ela
> carrega a de quem a emitiu —, então tudo que decide por identidade (a área
> administrativa inclusive) fica fora do alcance dela.

---

## 4. Paginação e formatos

Listagens aceitam `limit` (máximo 200) e `offset`:

```bash
curl -H "X-API-Key: SUA_CHAVE" ".../v1/contacts?limit=100&offset=200"
```

e respondem:

```json
{ "items": [ ], "total": 1523, "limit": 100, "offset": 200 }
```

Os endpoints de mapa (`uf-overview`, `setores`, `malha`, `contacts/map`)
devolvem **GeoJSON** padrão — QGIS, Google Earth e bibliotecas de mapa abrem
direto.

---

## 5. Documentação viva

A API se documenta sozinha, sempre em dia com o código:

- **Interativa**, dá para testar na hora: `/sistema/api/docs`
- **Leitura corrida**: `/sistema/api/redoc`
- **Formato máquina**, importa no Postman ou Insomnia: `/sistema/api/openapi.json`

---

## 6. Exemplos prontos

**Planilha — mais votados de um cargo, em CSV:**

```bash
curl -H "X-API-Key: SUA_CHAVE" \
  ".../v1/tse/stats/top-candidates?year=2024&office_code=11&limit=200" \
  -o top.json
python -c "import json,csv; d=json.load(open('top.json',encoding='utf-8')); w=csv.writer(open('mais_votados.csv','w',newline='',encoding='utf-8')); w.writerow(['nome','partido','uf','votos']); [w.writerow([i['candidate']['urn_name'], (i['candidate'].get('party') or {}).get('abbreviation'), i['candidate'].get('state'), i['total_votes']]) for i in d['items']]"
```

Saída (testada):

```
EDUARDO PAES,PSD,RJ,1861856
RICARDO NUNES,MDB,SP,1801139
GUILHERME BOULOS,PSOL,SP,1776127
```

> Repare no formato: as listagens vêm como `{"items": [...]}`, e cada item de
> ranking traz `candidate` (a ficha) e `total_votes` (o número). Vale conferir
> a forma da resposta em `/api/docs` antes de escrever o parser.

**Python — renda por bairro de um município:**

```python
import requests

BASE = "https://marenostrumconsult.com.br/sistema/api/v1"
H = {"X-API-Key": "SUA_CHAVE"}

setores = requests.get(f"{BASE}/census/setores",
                       params={"cd_mun": "3304557"}, headers=H).json()

# média ponderada pelo número de responsáveis — a mesma conta da tela
por_bairro = {}
for f in setores["features"]:
    p = f["properties"]
    nome = p.get("nm_bairro") or p.get("nm_subdist") or p.get("nm_dist")
    renda, peso = p.get("renda_media"), p.get("responsaveis")
    if renda and peso:
        soma, total = por_bairro.get(nome, (0, 0))
        por_bairro[nome] = (soma + renda * peso, total + peso)

ranking = sorted(por_bairro.items(), key=lambda x: -x[1][0] / x[1][1])
for nome, (soma, total) in ranking[:10]:
    print(f"{nome:<25} R$ {soma / total:>10,.0f}")
```

---

## 7. Operação das chaves

**Quem pode emitir:** apenas `admin@marenostrum.com.br` e `danieldeluna@gmail.com`
(lista em `API_KEY_ADMINS`). A trava é por identidade, além do super-acesso:
super-acesso é concedido para dar suporte dentro da conta do cliente, e emitir
credencial que lê dados por fora do sistema não deveria vir junto no pacote.
Qualquer outra conta — mesmo superadmin — recebe `403`.

**Pelo painel (jeito recomendado):** entre no Painel Mare Nostrum e role até
"Chaves de acesso aos dados", no fim da página. Preencha para que serve, clique
em **Gerar chave** e copie — ela aparece uma vez só. A mesma lista mostra o uso
de cada chave e o botão de cancelar.

**Pela linha de comando:**

```bash
# criar
curl -X POST -H "Authorization: Bearer SEU_TOKEN" -H "Content-Type: application/json" -d "{\"name\":\"BI do Daniel\",\"expires_in_days\":365}" ".../v1/admin/api-keys"

# listar — mostra uso e prefixo, nunca a chave
curl -H "Authorization: Bearer SEU_TOKEN" ".../v1/admin/api-keys"

# revogar — efeito imediato
curl -X DELETE -H "Authorization: Bearer SEU_TOKEN" ".../v1/admin/api-keys/{id}"
```

**A chave aparece uma única vez**, na resposta da criação. Depois o sistema
guarda apenas um resumo criptográfico dela — nem nós conseguimos recuperá-la.
Perdeu, revoga e cria outra.

**Cuidados:** trate a chave como senha. Não coloque em código versionado, em
planilha compartilhada ou em mensagem. Se vazar, revogue — leva um comando e
vale na hora.

Prefira **uma chave por finalidade** ("BI", "site", "parceiro X"): assim dá
para cortar uma sem afetar as outras, e o registro de uso mostra qual
integração ainda está viva.
