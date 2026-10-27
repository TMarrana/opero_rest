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
    valor em `campo` (como as de `sales.reports.por_dia`)."""
    valores = [(l["dia"], Decimal(l.get(campo) or 0)) for l in linhas]
    if not valores:
        return ""
    maximo = max((v for _, v in valores), default=Decimal(0))
    n = len(valores)
    passo = LARGURA / n
    largura_barra = max(passo - FOLGA, 1)
    util = ALTURA - TOPO - BASE
    partes = [
        f'<svg viewBox="0 0 {LARGURA} {ALTURA}" class="h-auto w-full" role="img" aria-label="{escape(rotulo)}">',
        # Linha de base, discreta.
        f'<line x1="0" x2="{LARGURA}" y1="{ALTURA - BASE}" y2="{ALTURA - BASE}" class="stroke-linha" stroke-width="1"/>',
    ]
    if maximo > 0:
        partes.append(
            f'<text x="0" y="13" class="fill-ardosia" font-size="13">máx. {escape(euros(maximo))}</text>'
        )
    for i, (dia, valor) in enumerate(valores):
        x = i * passo + FOLGA / 2
        altura = float(valor / maximo) * util if maximo > 0 and valor > 0 else 0
        y = ALTURA - BASE - altura
        dica = f"{dia:%d/%m}: {euros(valor)}"
        partes.append("<g>")
        partes.append(f"<title>{escape(dica)}</title>")
        # Área de toque da altura toda, maior do que a barra.
        partes.append(
            f'<rect x="{i * passo:.1f}" y="{TOPO}" width="{passo:.1f}" height="{util}" fill="transparent"/>'
        )
        if altura:
            raio = min(4, largura_barra / 2, altura)
            partes.append(
                f'<path d="{_barra(x, y, largura_barra, altura, raio)}" class="fill-floresta"/>'
            )
        partes.append("</g>")
        if i == 0 or i == n - 1 or (n > 10 and dia.day in (8, 15, 22)):
            ancora = "start" if i == 0 else ("end" if i == n - 1 else "middle")
            tx = i * passo if i == 0 else ((i + 1) * passo if i == n - 1 else x + largura_barra / 2)
            partes.append(
                f'<text x="{tx:.1f}" y="{ALTURA - 5}" text-anchor="{ancora}" class="fill-ardosia" font-size="13">{dia:%d/%m}</text>'
            )
    partes.append("</svg>")
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
