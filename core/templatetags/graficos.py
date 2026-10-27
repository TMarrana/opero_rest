"""
Gráficos simples em SVG, gerados no servidor (Fase 15): sem biblioteca de BI
e sem Node. Uma série por gráfico, por isso sem legenda: o título diz o que
é. Cada barra tem uma área de toque da altura toda com a dica (`<title>`),
e a tabela ao lado tem os números.
"""
from decimal import Decimal

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from sales.templatetags.vendas import euros

register = template.Library()

LARGURA, ALTURA = 480, 150
TOPO, BASE = 20, 24  # espaço para o valor máximo e para as datas
FOLGA = 2  # a folga de superfície entre barras vizinhas


@register.simple_tag
def barras_por_dia(linhas, campo="total", rotulo="Vendas por dia"):
    """Barras verticais, uma por dia. `linhas` são dicionários com `dia` e o
    valor em `campo` (como as de `sales.reports.por_dia`).

    Só as barras ficam no SVG, que estica à largura do cartão; o máximo e as
    datas são HTML, para o texto ter o tamanho do resto da página em
    qualquer largura."""
    valores = [(l["dia"], Decimal(l.get(campo) or 0)) for l in linhas]
    if not valores:
        return ""
    maximo = max((v for _, v in valores), default=Decimal(0))
    n = len(valores)
    passo = LARGURA / n
    largura_barra = max(passo - FOLGA, 1)
    util = ALTURA - TOPO - BASE
    partes = []
    if maximo > 0:
        partes.append(f'<p class="font-dados text-xs text-ardosia">máx. {escape(euros(maximo))}</p>')
    partes += [
        f'<svg viewBox="0 0 {LARGURA} {util}" preserveAspectRatio="none" class="mt-1 block h-40 w-full" '
        f'role="img" aria-label="{escape(rotulo)}">',
        # Linha de base, discreta.
        f'<line x1="0" x2="{LARGURA}" y1="{util}" y2="{util}" class="stroke-linha" stroke-width="1" '
        f'vector-effect="non-scaling-stroke"/>',
    ]
    datas = []
    for i, (dia, valor) in enumerate(valores):
        x = i * passo + FOLGA / 2
        altura = float(valor / maximo) * util if maximo > 0 and valor > 0 else 0
        y = util - altura
        dica = f"{dia:%d/%m}: {euros(valor)}"
        partes.append("<g>")
        partes.append(f"<title>{escape(dica)}</title>")
        # Área de toque da altura toda, maior do que a barra.
        partes.append(f'<rect x="{i * passo:.1f}" y="0" width="{passo:.1f}" height="{util}" fill="transparent"/>')
        if altura:
            raio = min(4, largura_barra / 2, altura)
            partes.append(f'<path d="{_barra(x, y, largura_barra, altura, raio)}" class="fill-floresta"/>')
        partes.append("</g>")
        if i == 0 or i == n - 1 or (n > 10 and dia.day in (8, 15, 22)):
            if i == 0:
                posicao = "left: 0"
            elif i == n - 1:
                posicao = "right: 0"
            else:
                posicao = f"left: {(i + 0.5) / n * 100:.2f}%; transform: translateX(-50%)"
            datas.append(f'<span class="absolute" style="{posicao}">{dia:%d/%m}</span>')
    partes.append("</svg>")
    partes.append(f'<div class="relative mt-2 h-4 font-dados text-xs text-ardosia">{"".join(datas)}</div>')
    return mark_safe("".join(partes))


def _barra(x, y, largura, altura, raio):
    """Uma barra com os cantos de cima arredondados e assente na base."""
    fundo = y + altura
    return (
        f"M{x:.1f},{fundo:.1f} V{y + raio:.1f} Q{x:.1f},{y:.1f} {x + raio:.1f},{y:.1f} "
        f"H{x + largura - raio:.1f} Q{x + largura:.1f},{y:.1f} {x + largura:.1f},{y + raio:.1f} V{fundo:.1f} Z"
    )


@register.filter
def medida(valor, formato):
    """Um valor da Análise no formato da sua linha (`core.exports`)."""
    from attendance.templatetags.ponto import horas
    from sales.templatetags.vendas import numero

    if valor is None:
        return "—"
    if formato == "euros":
        return euros(valor)
    if formato == "horas":
        return horas(valor)
    if formato == "pct":
        return f"{Decimal(valor).quantize(Decimal('0.1'))} %".replace(".", ",")
    return numero(valor)


@register.simple_tag
def linha_precos(pontos, unidade="", rotulo="Evolução do preço"):
    """Uma linha de preços no tempo: o x é a data, à escala; cada receção é um
    ponto com a dica (data, preço, fornecedor). `pontos` são tuplos (data,
    preço, fornecedor, ...), por data."""
    if not pontos:
        return ""
    datas = [p[0] for p in pontos]
    precos = [Decimal(p[1]) for p in pontos]
    d0, d1 = min(datas), max(datas)
    vmin, vmax = min(precos), max(precos)
    # Uma folga de 10 % em cima e em baixo, para a linha não colar às bordas.
    folga = (vmax - vmin) * Decimal("0.1") or (vmax * Decimal("0.1")) or Decimal(1)
    vmin, vmax = max(vmin - folga, Decimal(0)), vmax + folga
    # Mais larga do que as barras: ocupa a largura toda do cartão, e assim o
    # texto fica do mesmo tamanho.
    largura, altura = LARGURA * 2, ALTURA + 40
    esquerda, direita = 8, 8
    util_x = largura - esquerda - direita
    util_y = altura - TOPO - BASE
    dias = (d1 - d0).days or 1

    def xy(data, preco):
        x = esquerda + ((data - d0).days / dias * util_x if d1 != d0 else util_x / 2)
        y = TOPO + float((vmax - preco) / (vmax - vmin)) * util_y
        return x, y

    pts = [xy(d, p) for d, p in zip(datas, precos)]
    partes = [
        f'<svg viewBox="0 0 {largura} {altura}" class="h-auto w-full" role="img" aria-label="{escape(rotulo)}">',
        f'<line x1="0" x2="{largura}" y1="{altura - BASE}" y2="{altura - BASE}" class="stroke-linha" stroke-width="1"/>',
        f'<text x="0" y="13" class="fill-ardosia" font-size="13">{escape(_extremos(precos))}</text>',
    ]
    if len(pts) > 1:
        caminho = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
        partes.append(
            f'<path d="{caminho}" fill="none" class="stroke-floresta" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
    for (x, y), p in zip(pts, pontos):
        dica = f"{p[0]:%d/%m/%Y}: {_preco(p[1])}{' / ' + unidade if unidade else ''} · {p[2]}"
        # Anel da cor da superfície à volta do ponto, e área de toque maior.
        partes.append(
            f'<g><title>{escape(dica)}</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="transparent"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="fill-floresta stroke-superficie" stroke-width="2"/></g>'
        )
    for data, ancora, x in ((d0, "start", esquerda), (d1, "end", largura - direita)):
        if data == d1 and d0 == d1 and ancora == "end":
            continue
        partes.append(
            f'<text x="{x}" y="{altura - 5}" text-anchor="{ancora}" class="fill-ardosia" font-size="13">{data:%d/%m/%Y}</text>'
        )
    partes.append("</svg>")
    return mark_safe("".join(partes))


def _preco(valor):
    from sales.templatetags.vendas import preco

    return preco(valor)


def _extremos(precos):
    if max(precos) == min(precos):
        return _preco(max(precos))
    return f"{_preco(max(precos))} máx. · {_preco(min(precos))} mín."
