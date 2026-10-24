import datetime
import json

from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import TemplateView

from attendance.services import close_shift, open_shift
from accounts.views import KIOSK_CONFIRMATION_KEY
from core.mixins import KIOSK_SESSION_KEY, StaffViewMixin
from vacations.forms import VacationRequestForm
from vacations.models import VacationRequest


def _worker_for(user):
    return getattr(user, "worker", None)


def _formatar(delta):
    total = int(delta.total_seconds() // 60)
    horas, minutos = divmod(total, 60)
    return f"{horas}h{minutos:02d}"


def _totais(worker):
    """Total trabalhado hoje e esta semana. Turnos abertos contam até
    agora; cada turno conta no dia da entrada (simplificação assumida)."""
    agora = timezone.now()
    hoje = timezone.localdate()
    inicio_semana = hoje - datetime.timedelta(days=hoje.weekday())

    def soma(desde):
        limite = timezone.make_aware(datetime.datetime.combine(desde, datetime.time.min))
        total = datetime.timedelta()
        for e in worker.time_entries.filter(check_in__gte=limite):
            total += (e.check_out or agora) - e.check_in
        return total

    total_hoje = soma(hoje)
    total_semana = soma(inicio_semana)
    return {
        "hoje": _formatar(total_hoje) if total_hoje else "—",
        "semana": _formatar(total_semana) if total_semana else "—",
    }


def _contexto_ponto(worker):
    entry = worker.open_entry
    return {
        "worker": worker,
        "entry": entry,
        "em_turno": entry is not None,
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
        return render(request, self.template_name, contexto)


class MarkView(StaffViewMixin, View):
    """Marca entrada ou saída. Um único hx-post devolve o fragmento do
    botão já no novo estado.

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
                open_shift(worker=worker, at=momento)
                acao, texto = "entrada", "Entrada registada"
            elif acao == "saida" or not acao:
                close_shift(worker=worker, at=momento)
                acao, texto = "saida", "Saída registada"
            else:
                raise ValidationError("Marcação inválida.")
            ok = True
        except ValidationError as exc:
            texto, ok = exc.messages[0], False

        sessao_terminada = False
        if ok and request.session.get(KIOSK_SESSION_KEY):
            confirmacao = {
                "nome": worker.full_name,
                "acao": "Entrada" if acao == "entrada" else "Saída",
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
        entries = worker.time_entries.select_related("corrected_by")[:30]
        return render(
            request,
            self.template_name,
            {"worker": worker, "entries": entries, "totais": _totais(worker)},
        )


class StaffVacationsView(StaffViewMixin, View):
    """Pedido de férias em três campos e lista dos pedidos próprios."""

    def _render(self, request, worker, form):
        pedidos = worker.vacation_requests.select_related("decided_by")[:20]
        return render(request, "staff/ferias.html", {"worker": worker, "form": form, "pedidos": pedidos})

    def get(self, request):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        form = VacationRequestForm(restaurant=worker.restaurant)
        form.fields.pop("worker")
        return self._render(request, worker, form)

    def post(self, request):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        form = VacationRequestForm(request.POST, restaurant=worker.restaurant)
        form.fields.pop("worker")
        if form.is_valid():
            pedido = form.save(commit=False)
            pedido.worker = worker
            pedido.status = VacationRequest.Status.PENDENTE
            pedido.save()
            messages.success(request, "Pedido enviado")
            return redirect("staff:ferias")
        return self._render(request, worker, form)
