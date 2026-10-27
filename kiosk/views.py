"""
Quiosque do tablet partilhado (Fase 7): nome → código → ação.

O quiosque nunca faz login. O código confirma quem está a picar e
devolve um token assinado que só serve para uma marcação dessa pessoa,
durante TOKEN_MAX_AGE segundos. Assim ninguém herda o lugar de quem picou
antes, e um código nunca abre a app nem o backoffice (secção 7).
"""
import datetime
import secrets

from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from accounts.views import device_info, device_work_area
from attendance.models import BreakType, CorrectionRequest, TimeEntry
from attendance.services import close_shift, end_break, open_shift, start_break
from core.models import Restaurant
from workers.models import Worker

from . import throttle

TOKEN_SALT = "opero-quiosque-marcacao"
TOKEN_MAX_AGE = 60
# Segundos até o ecrã voltar sozinho aos nomes.
ESPERA_CODIGO = 30
ESPERA_ENTRADA = 15
ESPERA_CURTA = 5
# Uma entrada aberta que passou do fim do turno previsto (ou, sem turno,
# de ENTRADA_LONGA) mais esta folga provavelmente ficou sem saída picada:
# o ecrã de ações avisa antes de a pessoa picar.
FOLGA_SAIDA = datetime.timedelta(minutes=30)
ENTRADA_LONGA = datetime.timedelta(hours=10)

NOMES_ACAO = {"entrada": "Entrada", "saida": "Saída", "pausa": "Início de pausa", "fim_pausa": "Fim de pausa"}


class KioskMixin:
    """Só num navegador ativado pelo gerente como tablet do restaurante.
    A lista de trabalhadores nunca é pública."""

    def dispatch(self, request, *args, **kwargs):
        self.device = device_info(request)
        # Um tablet sem casa mostraria a equipa de todas (Fase 9): tem de
        # ser ativado de novo.
        if self.device is None or not self.device["restaurante"]:
            return render(request, "kiosk/nao_ativado.html", status=403)
        return super().dispatch(request, *args, **kwargs)

    def workers(self):
        """A equipa da casa do tablet, com quem vem de outra casa do grupo
        (Fase 9)."""
        qs = Worker.objects.filter(is_active=True, kiosk_code__isnull=False).in_restaurant(self.device["restaurante"])
        return qs.order_by("full_name")


def _saida_esquecida(entry, agora):
    turno = entry.planned_shift()
    fim = turno.end_at if turno is not None else entry.check_in + ENTRADA_LONGA
    return agora > fim + FOLGA_SAIDA


def _estado(worker, restaurant_id):
    """Uma entrada aberta noutra casa do grupo não se fecha neste tablet:
    o ecrã mostra-a e oferece a entrada aqui, que a deixa por resolver
    (Fase 9)."""
    entry = worker.open_entry
    noutra_casa = None
    if entry is not None and entry.restaurant_id != restaurant_id:
        noutra_casa, entry = entry, None
    pausa = entry.open_break if entry else None
    return {
        "entry": entry,
        "noutra_casa": noutra_casa,
        "pausa": pausa,
        "saida_esquecida": entry is not None and pausa is None and _saida_esquecida(entry, timezone.now()),
        "tipos_pausa": BreakType.objects.filter(restaurant_id=restaurant_id, archived_at__isnull=True)
        if entry and not pausa
        else [],
        "hoje": timezone.localdate(),
    }


def _turno_previsto(entry):
    """O turno publicado do dia de trabalho que ainda não acabou à hora da
    entrada: numa dobra, a saída prevista é a do primeiro turno."""
    from shifts.models import Shift

    return (
        Shift.objects.filter(
            worker_id=entry.worker_id,
            work_date=entry.work_date,
            state=Shift.State.PUBLICADO,
            end_at__gt=entry.check_in,
        )
        .order_by("start_at")
        .first()
    )


def _aberta_noutra_casa(worker, restaurant_id):
    entry = worker.open_entry
    return entry is not None and entry.restaurant_id != restaurant_id


class NamesView(KioskMixin, View):
    def get(self, request):
        return render(request, "kiosk/nomes.html", {"workers": self.workers()})


class CodeView(KioskMixin, View):
    def get(self, request, pk):
        worker = get_object_or_404(self.workers(), pk=pk)
        return render(request, "kiosk/codigo.html", {"worker": worker, "espera": ESPERA_CODIGO})

    def post(self, request, pk):
        worker = get_object_or_404(self.workers(), pk=pk)
        erro = None
        if throttle.esta_bloqueado(worker.pk):
            erro = "Demasiadas tentativas. Aguarde um minuto e tente de novo."
        elif not worker.check_kiosk_code(request.POST.get("codigo", "")):
            throttle.registar_falha(worker.pk)
            erro = "Código errado. Tente de novo."
        if erro:
            return render(request, "kiosk/codigo.html", {"worker": worker, "erro": erro, "espera": ESPERA_CODIGO})
        throttle.limpar_falhas(worker.pk)
        contexto = {
            "worker": worker,
            # O valor aleatório distingue dois tokens da mesma pessoa no mesmo
            # segundo; sem ele, a segunda marcação passava por repetida.
            "token": signing.dumps({"w": worker.pk, "n": secrets.token_hex(8)}, salt=TOKEN_SALT),
            "espera": ESPERA_CODIGO,
            **_estado(worker, self.device["restaurante"]),
        }
        return render(request, "kiosk/acoes.html", contexto)


class MarkView(KioskMixin, View):
    """Aplica a ação escolhida no ecrã de ações e mostra a confirmação. O
    token só vale uma vez: um segundo toque no mesmo botão não marca duas
    vezes."""

    def _erro(self, request, worker, texto):
        return render(
            request,
            "kiosk/confirmacao.html",
            {"worker": worker, "erro": texto, "espera": ESPERA_ENTRADA},
        )

    def post(self, request, pk):
        worker = get_object_or_404(self.workers(), pk=pk)
        token = request.POST.get("token", "")
        try:
            dados = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
        except signing.BadSignature:
            dados = None
        if not dados or dados.get("w") != worker.pk:
            return self._erro(request, worker, "O tempo para picar acabou. Escreva o código de novo.")
        if not cache.add(f"quiosque-token:{token}", 1, TOKEN_MAX_AGE):
            return self._erro(request, worker, "Esta marcação já foi feita. Escreva o código de novo para outra.")

        acao = request.POST.get("acao", "")
        agora = timezone.now()
        contexto = {"worker": worker, "acao": NOMES_ACAO.get(acao, ""), "hora": agora, "espera": ESPERA_CURTA}
        try:
            if acao == "entrada":
                anterior = worker.time_entries.filter(check_out__isnull=True, missing_exit=False).first()
                entry = open_shift(
                    worker=worker,
                    at=agora,
                    work_area=device_work_area(request),
                    source=TimeEntry.Source.QUIOSQUE,
                    restaurant=Restaurant.objects.get(pk=self.device["restaurante"]),
                )
                esquecida = None
                if anterior is not None:
                    anterior.refresh_from_db()
                    esquecida = anterior if anterior.missing_exit else None
                por_resolver = worker.time_entries.unresolved(now=agora).exclude(
                    correction_requests__status=CorrectionRequest.Status.PENDENTE
                )
                if esquecida is not None:
                    por_resolver = por_resolver.exclude(pk=esquecida.pk)
                contexto.update(
                    entrada=True,
                    turno=_turno_previsto(entry),
                    esquecida=esquecida,
                    por_resolver=por_resolver.count(),
                    espera=ESPERA_ENTRADA,
                )
            elif acao in ("saida", "pausa", "fim_pausa") and _aberta_noutra_casa(worker, self.device["restaurante"]):
                raise ValidationError("A entrada aberta é de outra casa. Marque lá a saída.")
            elif acao == "saida":
                close_shift(worker=worker, at=agora)
            elif acao == "pausa":
                tipo = BreakType.objects.filter(
                    restaurant_id=self.device["restaurante"], archived_at__isnull=True, pk=request.POST.get("tipo_pausa") or None
                ).first()
                if tipo is None:
                    raise ValidationError("Escolha o tipo de pausa.")
                start_break(worker=worker, break_type=tipo, at=agora)
                contexto["detalhe"] = tipo.name
            elif acao == "fim_pausa":
                end_break(worker=worker, at=agora)
            else:
                raise ValidationError("Marcação inválida.")
        except ValidationError as exc:
            return self._erro(request, worker, exc.messages[0])
        return render(request, "kiosk/confirmacao.html", contexto)
