import datetime
import json

from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import TemplateView

from attendance.forms import CorrectionRequestForm
from attendance.models import BreakType, CorrectionRequest, TimeEntry
from attendance.services import close_shift, end_break, open_shift, request_correction, start_break
from accounts.views import KIOSK_CONFIRMATION_KEY, device_work_area
from core.mixins import KIOSK_SESSION_KEY, StaffViewMixin
from vacations.forms import VacationRequestForm
from vacations.models import BlockedPeriod
from vacations.services import balance, can_cancel, cancel_request, create_request


def _worker_for(user):
    return getattr(user, "worker", None)


def _formatar(delta):
    total = int(delta.total_seconds() // 60)
    horas, minutos = divmod(total, 60)
    return f"{horas}h{minutos:02d}"


def _totais(worker):
    """Total trabalhado hoje e esta semana, sem as pausas não pagas.
    Turnos abertos contam até agora; cada turno conta no seu dia de
    trabalho, o da entrada (Fase 5)."""
    agora = timezone.now()
    hoje = timezone.localdate()
    inicio_semana = hoje - datetime.timedelta(days=hoje.weekday())

    def soma(desde):
        total = datetime.timedelta()
        for e in worker.time_entries.filter(work_date__gte=desde).prefetch_related("breaks__break_type"):
            total += e.worked(until=agora)
        return total

    total_hoje = soma(hoje)
    total_semana = soma(inicio_semana)
    return {
        "hoje": _formatar(total_hoje) if total_hoje else "—",
        "semana": _formatar(total_semana) if total_semana else "—",
    }


def _contexto_ponto(worker):
    entry = worker.open_entry
    pausa = entry.open_break if entry else None
    return {
        "worker": worker,
        "entry": entry,
        "em_turno": entry is not None,
        "pausa": pausa,
        "tipos_pausa": BreakType.objects.filter(restaurant=worker.restaurant, archived_at__isnull=True)
        if entry and not pausa
        else [],
        "totais": _totais(worker),
    }


class StaffHomeView(StaffViewMixin, TemplateView):
    """Ecrã de ponto do colaborador: o botão é o ecrã (secção 5)."""

    template_name = "staff/home.html"

    def get(self, request, *args, **kwargs):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        contexto = _contexto_ponto(worker)
        contexto["quiosque"] = bool(request.session.get(KIOSK_SESSION_KEY))
        # Registos por resolver sem pedido pendente: o colaborador indica a saída.
        contexto["por_resolver"] = worker.time_entries.unresolved().exclude(
            correction_requests__status=CorrectionRequest.Status.PENDENTE
        )
        return render(request, self.template_name, contexto)


NOMES_ACAO = {"entrada": "Entrada", "saida": "Saída", "pausa": "Início de pausa", "fim_pausa": "Fim de pausa"}


class MarkView(StaffViewMixin, View):
    """Marca entrada, saída, início ou fim de pausa. Um único hx-post
    devolve o fragmento do botão já no novo estado.

    O formulário diz a ação que o botão mostrava (`acao`), e a fila
    offline envia também `marcado_em` (o timestamp é o do momento da
    marcação, não o do envio) e `trabalhador` (quem marcou). Uma marcação
    que já não corresponde ao estado do turno, ou que é de outra pessoa,
    é recusada em vez de ser aplicada ao contrário.

    Pedidos da fila (cabeçalho X-Opero-Fila) recebem JSON: 200 se a
    marcação entrou, 409 com o motivo se foi recusada.

    No tablet partilhado (modo quiosque) a sessão termina a seguir a uma
    marcação bem sucedida e o ecrã volta ao PIN com a confirmação."""

    def post(self, request):
        worker = _worker_for(request.user)
        da_fila = request.headers.get("X-Opero-Fila") == "1"
        if worker is None:
            if da_fila:
                return JsonResponse({"ok": False, "texto": "Falta a ficha de trabalhador."}, status=409)
            return render(request, "staff/sem_ficha.html")
        momento = timezone.now()
        marcado_em = request.POST.get("marcado_em", "")
        if marcado_em:
            parsed = parse_datetime(marcado_em)
            if parsed is not None:
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed)
                # Nunca aceitar marcações no futuro.
                momento = min(parsed, timezone.now())
        acao = request.POST.get("acao", "")
        trabalhador = request.POST.get("trabalhador", "")
        try:
            if trabalhador and trabalhador != str(worker.pk):
                raise ValidationError(
                    "Esta marcação foi feita por outro colaborador. Só sincroniza com a sessão dele."
                )
            if acao == "entrada" or (not acao and not worker.open_entry):
                source = (
                    TimeEntry.Source.QUIOSQUE
                    if request.session.get(KIOSK_SESSION_KEY)
                    else TimeEntry.Source.TELEMOVEL
                )
                open_shift(worker=worker, at=momento, work_area=device_work_area(request), source=source)
                acao, texto = "entrada", "Entrada registada"
            elif acao == "saida" or not acao:
                close_shift(worker=worker, at=momento)
                acao, texto = "saida", "Saída registada"
            elif acao == "pausa":
                tipo = BreakType.objects.filter(
                    restaurant=worker.restaurant, pk=request.POST.get("tipo_pausa") or None
                ).first()
                if tipo is None:
                    raise ValidationError("Escolha o tipo de pausa.")
                start_break(worker=worker, break_type=tipo, at=momento)
                texto = "Pausa iniciada"
            elif acao == "fim_pausa":
                end_break(worker=worker, at=momento)
                texto = "Pausa terminada"
            else:
                raise ValidationError("Marcação inválida.")
            ok = True
        except ValidationError as exc:
            texto, ok = exc.messages[0], False

        sessao_terminada = False
        if ok and request.session.get(KIOSK_SESSION_KEY):
            confirmacao = {
                "nome": worker.full_name,
                "acao": NOMES_ACAO[acao],
                "hora": timezone.localtime(momento).strftime("%H:%M"),
            }
            logout(request)
            request.session[KIOSK_CONFIRMATION_KEY] = confirmacao
            sessao_terminada = True

        if da_fila:
            return JsonResponse(
                {"ok": ok, "texto": texto, "sessao_terminada": sessao_terminada},
                status=200 if ok else 409,
            )
        if sessao_terminada:
            resp = HttpResponse(status=204)
            resp["HX-Redirect"] = reverse("staff:pin_login")
            return resp
        resp = render(request, "partials/staff/ponto.html", _contexto_ponto(worker))
        resp["HX-Trigger"] = json.dumps(
            {"toast": {"texto": texto, "tom": "sucesso" if ok else "erro"}}
        )
        return resp


class StaffHistoryView(StaffViewMixin, TemplateView):
    """Histórico próprio em talões (secção 5)."""

    template_name = "staff/historico.html"

    def get(self, request, *args, **kwargs):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        entries = (
            worker.time_entries.select_related("corrected_by", "work_area")
            .prefetch_related("breaks__break_type")[:30]
        )
        pendentes = set(
            worker.correction_requests.filter(status=CorrectionRequest.Status.PENDENTE).values_list(
                "entry_id", flat=True
            )
        )
        return render(
            request,
            self.template_name,
            {
                "worker": worker,
                "entries": entries,
                "totais": _totais(worker),
                "com_pedido": pendentes,
                "pedidos": worker.correction_requests.select_related("decided_by")[:10],
            },
        )


class StaffVacationsView(StaffViewMixin, View):
    """Pedido de ausência e lista dos pedidos próprios, com o saldo de
    férias e os períodos bloqueados à vista antes de escolher as datas
    (R-060)."""

    def _render(self, request, worker, form):
        hoje = timezone.localdate()
        pedidos = list(worker.vacation_requests.select_related("decided_by", "absence_type")[:20])
        for p in pedidos:
            p.cancelavel = can_cancel(p, today=hoje)
        bloqueios = (
            BlockedPeriod.objects.filter(restaurant=worker.restaurant, end__gte=hoje)
            .exclude(exempt_workers=worker)
            .prefetch_related("absence_types")
        )
        return render(
            request,
            "staff/ferias.html",
            {
                "worker": worker,
                "form": form,
                "pedidos": pedidos,
                "saldo": balance(worker, hoje.year),
                "ano": hoje.year,
                "bloqueios": bloqueios,
            },
        )

    def get(self, request):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        form = VacationRequestForm(restaurant=worker.restaurant, with_worker=False)
        return self._render(request, worker, form)

    def post(self, request):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        form = VacationRequestForm(request.POST, restaurant=worker.restaurant, with_worker=False)
        if form.is_valid():
            try:
                pedido = create_request(
                    worker=worker,
                    absence_type=form.cleaned_data["absence_type"],
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    half_day=form.cleaned_data.get("half_day", False),
                    note=form.cleaned_data["request_note"],
                )
                messages.success(
                    request, "Ausência registada" if pedido.status == pedido.Status.APROVADO else "Pedido enviado"
                )
                return redirect("staff:ferias")
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        return self._render(request, worker, form)


class StaffVacationCancelView(StaffViewMixin, View):
    """Cancelar um pedido pendente, ou aprovado e ainda no futuro (R-056)."""

    def post(self, request, pk):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        pedido = get_object_or_404(worker.vacation_requests, pk=pk)
        try:
            cancel_request(request_obj=pedido, worker=worker)
            messages.success(request, "Pedido cancelado")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        return redirect("staff:ferias")


class StaffCorrectionView(StaffViewMixin, View):
    """Pedido de correção de um registo próprio, ou de um registo que falta
    (sem `pk`). O gerente decide no backoffice."""

    def _entry(self, worker, pk):
        if pk is None:
            return None
        return get_object_or_404(worker.time_entries, pk=pk)

    def _render(self, request, worker, entry, form):
        return render(request, "staff/correcao.html", {"worker": worker, "entry": entry, "form": form})

    def get(self, request, pk=None):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        entry = self._entry(worker, pk)
        inicial = {}
        if entry is not None:
            inicial["check_in"] = timezone.localtime(entry.check_in).strftime("%Y-%m-%dT%H:%M")
            if entry.check_out:
                inicial["check_out"] = timezone.localtime(entry.check_out).strftime("%Y-%m-%dT%H:%M")
        return self._render(request, worker, entry, CorrectionRequestForm(initial=inicial))

    def post(self, request, pk=None):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        entry = self._entry(worker, pk)
        form = CorrectionRequestForm(request.POST)
        if form.is_valid():
            try:
                request_correction(
                    worker=worker,
                    entry=entry,
                    note=form.cleaned_data["note"],
                    check_in=form.cleaned_data["check_in"],
                    check_out=form.cleaned_data["check_out"],
                )
                messages.success(request, "Pedido de correção enviado")
                return redirect("staff:historico")
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        return self._render(request, worker, entry, form)


class StaffShiftsView(StaffViewMixin, TemplateView):
    """Os meus turnos: os publicados e as folgas dos próximos 14 dias. Um
    turno em rascunho ou em reserva nunca aparece (invariante 10)."""

    template_name = "staff/turnos.html"

    def get(self, request, *args, **kwargs):
        from shifts.models import RestDay, Shift

        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        hoje = timezone.localdate()
        fim = hoje + datetime.timedelta(days=13)
        turnos = Shift.objects.filter(
            worker=worker, state=Shift.State.PUBLICADO, work_date__range=(hoje, fim)
        ).select_related("template", "work_area")
        folgas = set(
            RestDay.objects.filter(
                worker=worker, state=RestDay.State.PUBLICADO, date__range=(hoje, fim)
            ).values_list("date", flat=True)
        )
        dias = []
        for i in range(14):
            dia = hoje + datetime.timedelta(days=i)
            dias.append({"dia": dia, "turnos": [t for t in turnos if t.work_date == dia], "folga": dia in folgas})
        return render(request, self.template_name, {"worker": worker, "dias": dias, "hoje": hoje})
