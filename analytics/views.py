"""
Análise (Fase 15): o período e as casas escolhidos, lado a lado. As vendas,
as horas, as vendas por hora trabalhada, o food cost teórico e os consumos
internos, com a exportação para Excel e CSV.

Só o Admin e o Gerente (os relatórios cruzam vendas e pessoas, secção 7).
Comparar casas é só para o Admin do grupo; os outros veem a casa ativa.
"""
import datetime
from decimal import Decimal

from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from attendance.month import month_range, next_month, previous_month
from core import exports
from core.exports import EUROS, HORAS, NUMERO, PERCENTAGEM, Tabela
from core.mixins import StockRequiredMixin

from . import reports
from . import stock_reports as sr

MAX_DIAS = 366


def _data(valor):
    try:
        return datetime.date.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


def periodo(request, meses=1):
    """(início, fim, mês ou None). Por omissão, o mês corrente, ou os últimos
    `meses` meses até hoje. Um intervalo de datas (`inicio` e `fim`) manda
    sobre o mês."""
    inicio, fim = _data(request.GET.get("inicio")), _data(request.GET.get("fim"))
    if inicio and fim and inicio <= fim and (fim - inicio).days < MAX_DIAS:
        return inicio, fim, None
    try:
        mes = datetime.datetime.strptime(request.GET.get("mes", ""), "%Y-%m").date()
    except ValueError:
        mes = timezone.localdate().replace(day=1)
        if meses > 1:
            inicio = mes
            for _ in range(meses - 1):
                inicio = previous_month(inicio)
            return inicio, timezone.localdate(), None
    inicio, fim = month_range(mes)
    return inicio, fim, mes


def casas_disponiveis(request, perfis=("ADMIN", "MANAGER")):
    """As casas que a pessoa pode pôr lado a lado: todas as do grupo onde tem
    um destes perfis, se for Admin do grupo; senão, só a ativa."""
    if not request.user.is_group_admin:
        return [request.restaurant]
    return sorted((c for c, perfil in request.casas.items() if perfil in perfis), key=lambda c: c.name)


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


class AnalysisView(StockRequiredMixin, TemplateView):
    template_name = "manage/analytics/inicio.html"

    def get(self, request, *args, **kwargs):
        # O resumo cruza vendas e pessoas: o Resp. stock vai para o stock.
        if request.role not in ("ADMIN", "MANAGER"):
            return redirect("analytics:stock")
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
            separador="resumo",
        )
        return self.render_to_response(contexto)


def _contexto_periodo(inicio, fim, mes, disponiveis, escolhidas):
    return {
        "inicio": inicio,
        "fim": fim,
        "mes": mes,
        "mes_anterior": previous_month(mes or inicio),
        "mes_seguinte": next_month(mes) if mes and next_month(mes) <= timezone.localdate() else None,
        "disponiveis": disponiveis,
        "escolhidas": escolhidas,
    }


class StockReportView(StockRequiredMixin, TemplateView):
    """Análise → Stock: o valor do stock por categoria e por casa (agora), os
    artigos mais movimentados e os ajustes do período."""

    template_name = "manage/analytics/stock.html"

    def get(self, request, *args, **kwargs):
        inicio, fim, mes = periodo(request)
        disponiveis = casas_disponiveis(request, ("ADMIN", "MANAGER", "STOCK"))
        escolhidas = casas_escolhidas(request, disponiveis)
        valor, totais, sem_custo = sr.valor_por_categoria(escolhidas)
        casas = [
            {"casa": c, "movimentados": sr.mais_movimentados(c, inicio, fim), "ajustes": sr.ajustes(c, inicio, fim)}
            for c in escolhidas
        ]
        formato = exports.formato_pedido(request)
        if formato:
            tabelas = [_tabela_valor(escolhidas, valor, totais)]
            for c in casas:
                tabelas += [_tabela_movimentados(c), _tabela_ajustes(c)]
            return exports.responder(formato, tabelas, f"stock-{inicio:%Y-%m-%d}-a-{fim:%Y-%m-%d}")
        return self.render_to_response(
            self.get_context_data(
                **_contexto_periodo(inicio, fim, mes, disponiveis, escolhidas),
                valor=valor,
                totais=totais,
                sem_custo=[(c, n) for c, n in zip(escolhidas, sem_custo) if n],
                casas=casas,
                separador="stock",
            )
        )


def _tabela_valor(casas, valor, totais):
    return Tabela(
        titulo="Valor por categoria",
        colunas=["Categoria", *[c.name for c in casas]],
        linhas=[[l["categoria"], *l["valores"]] for l in valor] + [["Total", *totais]],
        formatos=[exports.TEXTO] + [EUROS] * len(casas),
    )


def _tabela_movimentados(c):
    return Tabela(
        titulo=f"Movimentados {c['casa'].name}",
        colunas=["Artigo", "Unidade", "Movimentos", "Entradas", "Vendas", "Consumos", "Quebras", "Transferências",
                 "Ajustes", "Valor das saídas"],
        linhas=[
            [m.item.name, m.item.unit, m.movimentos, m.entradas, m.vendas, m.consumos, m.quebras, m.transferencias,
             m.ajustes, m.valor_saidas]
            for m in c["movimentados"]
        ],
        formatos=[exports.TEXTO, exports.TEXTO] + [NUMERO] * 7 + [EUROS],
    )


def _tabela_ajustes(c):
    linhas, _, _ = c["ajustes"]
    return Tabela(
        titulo=f"Ajustes {c['casa'].name}",
        colunas=["Data", "Artigo", "Unidade", "Quantidade", "Valor", "Origem", "Motivo", "Registado por"],
        linhas=[
            [l["mov"].occurred_at, l["mov"].item.name, l["mov"].item.unit, l["mov"].signed_quantity, l["valor"],
             l["mov"].get_origin_display(), l["mov"].reason, str(l["mov"].created_by)]
            for l in linhas
        ],
        formatos=[exports.DATAHORA, exports.TEXTO, exports.TEXTO, NUMERO, EUROS],
    )


class PurchasesReportView(StockRequiredMixin, TemplateView):
    """Análise → Compras: por fornecedor e por casa, por artigo, e a evolução
    do preço de um artigo. Por omissão, os últimos seis meses."""

    template_name = "manage/analytics/compras.html"

    def get(self, request, *args, **kwargs):
        inicio, fim, mes = periodo(request, meses=6)
        disponiveis = casas_disponiveis(request, ("ADMIN", "MANAGER", "STOCK"))
        escolhidas = casas_escolhidas(request, disponiveis)
        fornecedores, totais, total = sr.por_fornecedor(escolhidas, inicio, fim)
        artigos = sr.por_artigo(escolhidas, inicio, fim)
        pedido = request.GET.get("artigo", "")
        artigo = next((a for a in artigos if sr.chave_artigo(a) == pedido), artigos[0] if artigos else None)
        formato = exports.formato_pedido(request)
        if formato:
            tabelas = [_tabela_fornecedores(escolhidas, fornecedores, totais, total), _tabela_artigos(artigos)]
            if artigo is not None:
                tabelas.append(_tabela_precos(artigo))
            return exports.responder(formato, tabelas, f"compras-{inicio:%Y-%m-%d}-a-{fim:%Y-%m-%d}")
        return self.render_to_response(
            self.get_context_data(
                **_contexto_periodo(inicio, fim, mes, disponiveis, escolhidas),
                fornecedores=fornecedores,
                totais=totais,
                total=total,
                artigos=artigos,
                artigo=artigo,
                chave=sr.chave_artigo(artigo) if artigo else "",
                separador="compras",
            )
        )


def _tabela_fornecedores(casas, fornecedores, totais, total):
    return Tabela(
        titulo="Por fornecedor",
        colunas=["Fornecedor", *[c.name for c in casas], "Total", "Receções", "Peso (%)"],
        linhas=[[f["fornecedor"], *f["valores"], f["total"], f["rececoes"], f["peso"]] for f in fornecedores]
        + [["Total", *totais, total, None, None]],
        formatos=[exports.TEXTO] + [EUROS] * (len(casas) + 1) + [NUMERO, PERCENTAGEM],
    )


def _tabela_artigos(artigos):
    return Tabela(
        titulo="Por artigo",
        colunas=["Artigo", "Unidade", "Quantidade", "Total", "Preço médio", "Mínimo", "Máximo", "Último", "Variação (%)"],
        linhas=[
            [a.nome, a.unidade, a.quantidade, a.total, a.preco_medio, a.minimo, a.maximo, a.ultimo, a.variacao]
            for a in artigos
        ],
        formatos=[exports.TEXTO, exports.TEXTO, NUMERO, EUROS, EUROS, EUROS, EUROS, EUROS, PERCENTAGEM],
    )


def _tabela_precos(artigo):
    return Tabela(
        titulo=f"Preços {artigo.nome}",
        colunas=["Data", "Preço unitário", "Fornecedor", "Casa"],
        linhas=[list(p) for p in artigo.precos],
        formatos=[exports.DATA, EUROS],
    )
