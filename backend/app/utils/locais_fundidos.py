"""Municipios onde a chave antiga do local de votacao fundiu locais distintos.

Ate a migration 064 o local era gravado com a chave (ano, municipio, numero),
mas no TSE o NR_LOCAL_VOTACAO so e unico DENTRO da zona eleitoral. Onde o
municipio tem mais de uma zona reaproveitando o mesmo numero, os locais
colidiram e o bairro de um deles ficou com os votos de todos.

Apurado no proprio arquivo do TSE (eleitorado_local_votacao_2024.zip),
comparando, por municipio, quantos numeros de local distintos existem contra
quantos pares (zona, numero) existem. Onde os dois batem, nada se perdeu.

Resultado: 187 municipios afetados de 5.569 (3,4%) — mas sao as capitais e as
cidades grandes. Sao Paulo tinha 160 locais no lugar de 2.062; o Rio, 163 no
lugar de 1.440.

ESTA LISTA E TRANSITORIA. Assim que uma UF for reimportada com a zona
(scripts/corrigir_locais_zona.py), os locais daquele municipio passam a ter
`zone` preenchido e o codigo confia nisso em vez da lista — ver
`bairro_confiavel()`. Quando nao sobrar municipio com zona nula, o arquivo
inteiro pode ser apagado.

Codigos sao TSE (Municipality.tse_code), nao IBGE.
"""

MUNICIPIOS_COM_LOCAIS_FUNDIDOS: frozenset[int] = frozenset({
    35, 51, 1392, 2550, 3018, 4154, 4278, 4472, 4839, 5355, 5835, 6050,
    8036, 9210, 10430, 11533, 12190, 13730, 13897, 14478, 15598, 15857,
    17590, 17612, 19810, 20516, 21750, 23574, 23817, 24570, 24910, 25135,
    25216, 25313, 26271, 26298, 27057, 27855, 31054, 33634, 34134, 35157,
    35734, 35971, 36617, 36692, 37818, 38075, 38490, 38733, 39659, 41238,
    41335, 42676, 43710, 44458, 45535, 45950, 46256, 47333, 48658, 49590,
    50350, 50911, 51551, 53430, 54011, 54038, 56235, 56251, 56995, 57037,
    57053, 58017, 58041, 58076, 58130, 58190, 58335, 58378, 58467, 58475,
    58491, 58637, 58653, 58670, 58696, 58777, 58831, 58971, 59013, 59153,
    59196, 59250, 60011, 61310, 61557, 61638, 62138, 62197, 62510, 62910,
    63134, 63614, 63770, 64017, 64254, 64750, 64777, 65633, 65897, 66192,
    66397, 66818, 66893, 67130, 67890, 68756, 69213, 69299, 69671, 69698,
    69795, 70572, 70718, 70750, 70777, 70793, 70971, 70998, 71072, 71218,
    71455, 71498, 71510, 71579, 71838, 74934, 75132, 75353, 75639, 75833,
    76678, 76910, 77771, 78859, 80390, 80470, 80810, 80837, 80896, 81051,
    81612, 81752, 81795, 81833, 82333, 83275, 83674, 85111, 85316, 85898,
    85995, 86371, 86835, 87718, 87858, 87912, 88013, 88153, 88390, 88412,
    88773, 89630, 90514, 90638, 90670, 90735, 91316, 91510, 91650, 91677,
    92215, 92274, 92410, 93734, 95710
})
