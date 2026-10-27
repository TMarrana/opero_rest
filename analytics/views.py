"""
Análise (Fase 15): o período e as casas escolhidos, lado a lado. As vendas,
as horas, as vendas por hora trabalhada, o food cost teórico e os consumos
internos, com a exportação para Excel e CSV.

Só o Admin e o Gerente (os relatórios cruzam vendas e pessoas, secção 7).
Comparar casas é só para o Admin do grupo; os outros veem a casa ativa.
"""
import datetime
from decimal import Decimal

from django.utils import timezone
from django.views.generic import TemplateView

from attendance.month import month_range, next_month, previous_month
from core import exports
from core.exports import EUROS, HORAS, NUMERO, PERCENTAGEM, Tabela
from core.mixins import ManagerRequiredMixin

from . import reports

MAX_DIAS = 366


def _data(valor):
    try:
        return datetime.date.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


def periodo(request):
    """(início, fim, mês ou None). Por omissão, o mês corrente. Um intervalo
    de datas (`inicio` e `fim`) manda sobre o mês."""
    inicio, fim = _data(request.GET.get("inicio")), _data(request.GET.get("fim"))
    if inicio and fim and inicio <= fim and (fim - inicio).days < MAX_DIAS:
        return inicio, fim, None
    try:
        mes = datetime.datetime.strptime(request.GET.get("mes", ""), "%Y-%m").date()
    except ValueError:
        mes = timezone.localdate().replace(day=1)
    inicio, fim = month_range(mes)
    return inicio, fim, mes


def casas_disponiveis(request):
    """As casas que a pessoa pode pôr lado a lado: todas as do grupo onde é
    Admin ou Gerente, se for Admin do grupo; senão, só a ativa."""
    if not request.user.is_group_admin:
        return [request.restaurant]
    return sorted(
        (c for c, perfil in request.casas.items() if perfil in ("ADMIN", "MANAGER")), key=lambda c: c.name
    )


def casas_escolhidas(request, disponiveis):
    pedidas = set(request.GET.getlist("casa"))
    escolhidas = [c for c in disponiveis if str(c.pk) in pedidas]
    return escolhidas or ([request.restaurant] if request.restaurant in disponiveis else disponiveis[:1])


LINHAS = [
    # (rótulo, atributo, formato)
    ("Vendas sem IVA", "vendas", EUROS),
    ("Documentos de venda", "documentos", NUMERO),
    ("Ticket médio", "ticket", EUROS),
    ("Horas trabalhadas", "horas", HORAS),
    ("Vendas por hora trabalhada", "por_hora", EUROS),
    ("Custo de pessoal estimado (% das vendas)", "custo_pessoal", PERCENTAGEM),
    ("Food cost teórico (%)", "food_cost", PERCENTAGEM),
    ("Vendas com custo teórico (%)", "cobertura", PERCENTAGEM),
    ("Margem teórica dos produtos com custo", "margem", EUROS),
    ("Consumos internos ao custo", "consumos", EUROS),
    ("Refeições do pessoal", "refeicoes", NUMERO),
]


def tabela_casas(indicadores, inicio, fim):
    return Tabela(
        titulo="Casas",
        colunas=[f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}", *[i.restaurant.name for i in indicadores]],
        linhas=[[rotulo, *[getattr(i, attr) for i in indicadores]] for rotulo, attr, _ in LINHAS],
        formatos_linha=[formato for _, _, formato in LINHAS],
    )


def tabela_produtos(ind):
    return Tabela(
        titulo=f"Produtos {ind.restaurant.name}",
        colunas=["Código", "Produto", "Família", "Quantidade", "Vendas sem IVA", "Preço médio", "Ficha",
                 "Custo por dose", "Custo teórico", "Margem", "Food cost (%)"],
        linhas=[
            [p.code, p.description, p.group, p.quantity, p.sales, p.unit_price, p.recipe.name if p.recipe else "",
             p.cost_per_dose.quantize(Decimal("0.01")) if p.cost_per_dose is not None else None,
             p.cost, p.margin, p.food_cost]
            for p in ind.produtos
        ],
        formatos=[exports.TEXTO] * 3 + [NUMERO, EUROS, EUROS, exports.TEXTO, EUROS, EUROS, EUROS, PERCENTAGEM],
    )


def tabela_dias(indicadores):
    colunas = ["Dia"]
    for i in indicadores:
        colunas += [f"Vendas {i.restaurant.name}", f"Horas {i.restaurant.name}"]
    linhas = []
    for n, dia in enumerate(l["dia"] for l in indicadores[0].por_dia):
        linha = [dia]
        for i in indicadores:
            l = i.por_dia[n]
            linha += [l["total"], l["horas"]]
        linhas.append(linha)
    return Tabela(
        titulo="Por dia", colunas=colunas, linhas=linhas, formatos=[exports.DATA] + [EUROS, HORAS] * len(indicadores)
    )


class AnalysisView(ManagerRequiredMixin, TemplateView):
    template_name = "manage/analytics/inicio.html"

    def get(self, request, *args, **kwargs):
        inicio, fim, mes = periodo(request)
        disponiveis = casas_disponiveis(request)
        escolhidas = casas_escolhidas(request, disponiveis)
        indicadores = [reports.indicadores(c, inicio, fim) for c in escolhidas]
        formato = request.GET.get("exportar")
        nome = f"analise-{inicio:%Y-%m-%d}-a-{fim:%Y-%m-%d}"
        if formato == "xlsx":
            return exports.xlsx_response(
                [tabela_casas(indicadores, inicio, fim), tabela_dias(indicadores), *[tabela_produtos(i) for i in indicadores]],
                nome,
            )
        if formato == "csv":
            return exports.csv_response(tabela_casas(indicadores, inicio, fim), nome)
        contexto = self.get_context_data(
            inicio=inicio,
            fim=fim,
            mes=mes,
            mes_anterior=previous_month(mes or inicio),
            mes_seguinte=next_month(mes) if mes and next_month(mes) <= timezone.localdate() else None,
            disponiveis=disponiveis,
            escolhidas=escolhidas,
            indicadores=indicadores,
            linhas=[
                {"rotulo": rotulo, "formato": formato_, "valores": [getattr(i, attr) for i in indicadores]}
                for rotulo, attr, formato_ in LINHAS
            ],
            query=request.GET.urlencode(),
        )
        return self.render_to_response(contexto)
