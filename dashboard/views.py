from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from accounts.models import BACKOFFICE_ROLES
from attendance.models import CorrectionRequest, TimeEntry
from core.middleware import SESSION_KEY
from core.mixins import GroupAdminRequiredMixin, RoleRequiredMixin
from core.utils import restaurant_scope, workers_scope
from inventory.models import Item, StockMovement
from vacations.models import VacationRequest

# O dashboard avisa quando o último dia de vendas importado tem mais do que isto.
VENDAS_ATRASO_DIAS = 7


class DashboardView(RoleRequiredMixin, TemplateView):
    """Dashboard do gerente (Fase 4): sem gráficos sofisticados — os
    quatro sinais do docx, cada um a um clique do seu módulo."""

    template_name = "manage/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        from accounts.models import User

        self.allowed_roles = (User.Role.ADMIN, User.Role.MANAGER, User.Role.STOCK)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request

        itens_baixos = (
            restaurant_scope(request, Item.objects.filter(is_active=True))
            .filter(current_stock__lte=F("minimum_stock"))
            .select_related("category")
        )
        ctx["stock_baixo"] = itens_baixos[:6]
        ctx["contador_baixo"] = itens_baixos.count()

        movimentos = restaurant_scope(
            request,
            StockMovement.objects.select_related("item", "created_by"),
            field="item__restaurant",
        )
        ctx["ultimos_movimentos"] = movimentos[:5]
        ctx["movimentos_hoje"] = movimentos.filter(occurred_at__date=timezone.localdate()).count()

        # As áreas de pessoas só aparecem a quem as pode abrir (matriz da secção 7).
        ctx["ve_pessoas"] = request.role in ("ADMIN", "MANAGER")
        if ctx["ve_pessoas"]:
            pendentes = restaurant_scope(
                request,
                VacationRequest.objects.filter(status=VacationRequest.Status.PENDENTE)
                .select_related("worker")
                .order_by("start_date"),
                field="worker__restaurant",
            )
            ctx["ferias_pendentes_total"] = pendentes.count()
            # Quem está fora hoje: ausências aprovadas que apanham o dia de hoje.
            hoje = timezone.localdate()
            ctx["em_ferias"] = restaurant_scope(
                request,
                VacationRequest.objects.filter(
                    status=VacationRequest.Status.APROVADO, start_date__lte=hoje, end_date__gte=hoje
                )
                .select_related("worker", "absence_type")
                .order_by("end_date", "worker__full_name"),
                field="worker__restaurant",
            )
            entradas = restaurant_scope(request, TimeEntry.objects.all())
            ctx["em_turno"] = (
                entradas.filter(check_out__isnull=True).resolved().select_related("worker").order_by("check_in")
            )
            ctx["por_resolver"] = entradas.unresolved().count()
            # Aviso de mês por fechar: a partir do dia 1, até todos os
            # trabalhadores ativos terem o mês anterior aprovado.
            from attendance.models import MonthClose
            from attendance.month import previous_month
            from workers.models import Worker

            anterior = previous_month(timezone.localdate())
            ativos = restaurant_scope(request, Worker.objects.filter(is_active=True))
            aprovados = MonthClose.objects.filter(
                worker__in=ativos, month=anterior, reopened_at__isnull=True
            ).count()
            ctx["mes_por_fechar"] = anterior
            ctx["por_aprovar"] = ativos.count() - aprovados
            # Vendas (Fase 10): avisa quando o último dia importado ficou para trás.
            from attendance.month import month_range
            from sales.reports import resumo, ultimo_dia

            ctx["ultimo_dia_vendas"] = ultimo_dia(request.restaurant)
            ctx["vendas_mes"] = resumo(request.restaurant, *month_range(timezone.localdate())).total
            if ctx["ultimo_dia_vendas"] is not None:
                atraso = (timezone.localdate() - ctx["ultimo_dia_vendas"]).days
                ctx["vendas_atraso"] = atraso if atraso > VENDAS_ATRASO_DIAS else 0
            ctx["pedidos_correcao"] = restaurant_scope(
                request, CorrectionRequest.objects.filter(status=CorrectionRequest.Status.PENDENTE)
            ).count()
            ctx.update(turnos_de_hoje(request))
            from attendance.views import overlapping_entries

            ctx["sobrepostos"] = len(overlapping_entries(request))
        return ctx


def turnos_de_hoje(request, agora=None):
    """Os turnos publicados de hoje nesta casa, um por pessoa, com o ponto ao
    lado: em turno, já saiu, em falta (passou a hora de entrada mais a
    tolerância e não picou) ou ainda por entrar. Quem picou sem turno
    planeado aparece no fim. As ausências aprovadas tiram o turno da lista
    (fica em reserva, R-033)."""
    import datetime

    from django.conf import settings

    from attendance.views import _desvios
    from shifts.models import Shift
    from workers.models import Worker

    agora = agora or timezone.now()
    dia = timezone.localdate(agora)
    casa = request.restaurant
    tolerancia = datetime.timedelta(minutes=settings.SHIFT_TOLERANCE_MINUTES)
    workers = workers_scope(request, Worker.objects.all())

    turnos = {}
    for t in (
        Shift.objects.filter(restaurant=casa, worker__in=workers, work_date=dia, state=Shift.State.PUBLICADO)
        .select_related("worker", "template", "work_area")
        .order_by("start_at")
    ):
        turnos.setdefault(t.worker, []).append(t)
    registos = {}
    for e in (
        TimeEntry.objects.filter(restaurant=casa, worker__in=workers, work_date=dia)
        .select_related("worker")
        .order_by("check_in")
    ):
        registos.setdefault(e.worker, []).append(e)

    linhas = []
    for worker, previstos in turnos.items():
        do_dia = registos.pop(worker, [])
        inicio = previstos[0].start_at
        if any(r.is_open for r in do_dia):
            estado = "em_turno"
        elif do_dia:
            estado = "saiu"
        elif agora > inicio + tolerancia:
            estado = "em_falta"
        else:
            estado = "por_entrar"
        linhas.append(
            {
                "worker": worker,
                "turnos": previstos,
                "registos": do_dia,
                "estado": estado,
                "desvios": [d for d in _desvios(previstos, do_dia, agora) if d != "Sem marcação"],
            }
        )
    sem_turno = [
        {"worker": w, "turnos": [], "registos": rs, "estado": "sem_turno", "desvios": []}
        for w, rs in registos.items()
    ]
    todas = linhas + sem_turno
    escala = _escala(todas, dia, agora)
    return {
        "turnos_hoje": todas,
        "escala": escala,
        "turnos_previstos": len(linhas),
        "turnos_picaram": sum(1 for l in linhas if l["estado"] in ("em_turno", "saiu")),
        "turnos_em_falta": sum(1 for l in linhas if l["estado"] == "em_falta"),
    }


# Cores das barras por estado: (turno planeado, ponto).
TONS = {
    "em_turno": ("border-servico-100 bg-servico-50", "bg-servico"),
    "saiu": ("border-neutro-300 bg-neutro-100", "bg-neutro-500"),
    "em_falta": ("border-dashed border-perigo-200 bg-perigo-50", "bg-perigo"),
    "por_entrar": ("border-ambar-100 bg-ambar-50", "bg-ambar"),
    "sem_turno": ("", "bg-alerta"),
}


def _pct(fracao):
    """Percentagem para um `style`: em texto, com ponto decimal (o Django
    escreveria vírgula, à portuguesa, e o CSS não a lê)."""
    return f"{100 * fracao:.2f}"


def _escala(linhas, dia, agora):
    """A linha do tempo do card «Turnos de hoje»: das horas cheias antes do
    primeiro turno ou entrada até depois do último fim (no mínimo 8 horas;
    um turno que passa a meia-noite estica para lá das 24). Acrescenta a
    cada linha as barras do turno e do ponto, em percentagem da largura."""
    import datetime
    import math

    zero = timezone.make_aware(datetime.datetime.combine(dia, datetime.time()))

    def horas(momento):
        return (momento - zero).total_seconds() / 3600

    pontos = []
    for l in linhas:
        for t in l["turnos"]:
            pontos += [horas(t.start_at), horas(t.end_at)]
        for r in l["registos"]:
            pontos += [horas(r.check_in), horas(r.check_out or max(agora, r.check_in))]
    if pontos:
        # A hora atual entra sempre na escala, para se ver onde está o dia.
        pontos.append(min(max(horas(agora), 0), 24))
        inicio, fim = math.floor(min(pontos)), math.ceil(max(pontos))
    else:
        inicio, fim = 9, 23
    if fim - inicio < 8:
        fim = inicio + 8
    total = fim - inicio

    def barra(de, ate):
        esquerda = max(horas(de), inicio) - inicio
        direita = min(horas(ate), fim) - inicio
        return {"esquerda": _pct(esquerda / total), "largura": _pct(max((direita - esquerda) / total, 0.006))}

    for l in linhas:
        l["tom_turno"], l["tom_ponto"] = TONS[l["estado"]]
        l["barras_turno"] = [
            {**barra(t.start_at, t.end_at), "titulo": f"{t.label} {timezone.localtime(t.start_at):%H:%M}–{timezone.localtime(t.end_at):%H:%M}"}
            for t in l["turnos"]
        ]
        l["barras_ponto"] = [
            {**barra(r.check_in, r.check_out or max(agora, r.check_in)), "aberto": r.check_out is None}
            for r in l["registos"]
        ]
    passo = 1 if total <= 12 else 2
    agora_h = horas(agora)
    return {
        "horas": [
            {"hora": f"{h % 24:02d}h", "pos": _pct((h - inicio) / total)}
            for h in range(inicio, fim + 1, passo)
        ],
        "agora": _pct((agora_h - inicio) / total) if inicio <= agora_h <= fim else None,
        "agora_txt": f"{timezone.localtime(agora):%H:%M}",
    }


class SwitchRestaurantView(LoginRequiredMixin, View):
    """Muda a casa ativa (Fase 9). Volta ao dashboard e não à página onde
    estava, porque essa página era da outra casa."""

    def post(self, request):
        casa = next((r for r in request.casas if str(r.pk) == request.POST.get("casa")), None)
        if casa is None:
            messages.error(request, "Não tem acesso a essa casa.")
        else:
            request.session[SESSION_KEY] = casa.pk
        if casa is not None and request.casas[casa] not in BACKOFFICE_ROLES:
            return redirect("staff:home")
        return redirect("dashboard:home")


def _sinais(restaurant):
    """Os sinais do dashboard de uma casa, em números (painel do grupo)."""
    from attendance.models import MonthClose
    from attendance.month import previous_month
    from workers.models import Worker

    entradas = TimeEntry.objects.filter(restaurant=restaurant)
    ativos = Worker.objects.filter(restaurant=restaurant, is_active=True)
    anterior = previous_month(timezone.localdate())
    aprovados = MonthClose.objects.filter(worker__in=ativos, month=anterior, reopened_at__isnull=True).count()
    from attendance.month import month_range
    from sales.reports import resumo, ultimo_dia

    vendas_mes = resumo(restaurant, *month_range(timezone.localdate())).total
    return {
        "casa": restaurant,
        "stock_baixo": Item.objects.filter(restaurant=restaurant, is_active=True, current_stock__lte=F("minimum_stock")).count(),
        "em_turno": entradas.filter(check_out__isnull=True).resolved().count(),
        "por_resolver": entradas.unresolved().count(),
        "ferias_pendentes": VacationRequest.objects.filter(
            worker__restaurant=restaurant, status=VacationRequest.Status.PENDENTE
        ).count(),
        "correcoes_pendentes": CorrectionRequest.objects.filter(
            restaurant=restaurant, status=CorrectionRequest.Status.PENDENTE
        ).count(),
        "por_aprovar": ativos.count() - aprovados,
        "vendas_mes": vendas_mes,
        "ultimo_dia_vendas": ultimo_dia(restaurant),
    }


class GroupDashboardView(GroupAdminRequiredMixin, TemplateView):
    """Painel do grupo (Fase 9): uma linha por casa, com os mesmos sinais do
    dashboard. Só o Admin do grupo vê as casas lado a lado (secção 7)."""

    template_name = "manage/grupo/painel.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from attendance.month import previous_month

        ctx["linhas"] = [_sinais(casa) for casa in self.request.casas]
        ctx["mes_por_fechar"] = previous_month(timezone.localdate())
        ctx["mes_atual"] = timezone.localdate()
        return ctx
