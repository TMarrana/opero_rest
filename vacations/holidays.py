"""Feriados nacionais portugueses (Código do Trabalho, art. 234.º),
incluindo os móveis: Sexta-feira Santa, Páscoa e Corpo de Deus. O
Carnaval não é feriado obrigatório e fica de fora; os municipais
guardam-se por restaurante em `Holiday`.

Calculados aqui em vez de virem da biblioteca `holidays`: são treze datas
e uma fórmula, e evitam uma dependência (ver Notas de desvio do plano)."""
import datetime
from functools import lru_cache

FIXOS = [
    ((1, 1), "Ano Novo"),
    ((4, 25), "Dia da Liberdade"),
    ((5, 1), "Dia do Trabalhador"),
    ((6, 10), "Dia de Portugal"),
    ((8, 15), "Assunção de Nossa Senhora"),
    ((10, 5), "Implantação da República"),
    ((11, 1), "Dia de Todos os Santos"),
    ((12, 1), "Restauração da Independência"),
    ((12, 8), "Imaculada Conceição"),
    ((12, 25), "Natal"),
]


def easter(year):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário
    gregoriano)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return datetime.date(year, month, day + 1)


@lru_cache(maxsize=32)
def national_holidays(year):
    """{data: nome} dos feriados nacionais de um ano."""
    pascoa = easter(year)
    feriados = {datetime.date(year, m, d): nome for (m, d), nome in FIXOS}
    feriados[pascoa - datetime.timedelta(days=2)] = "Sexta-feira Santa"
    feriados[pascoa] = "Páscoa"
    feriados[pascoa + datetime.timedelta(days=60)] = "Corpo de Deus"
    return feriados
