"""
Planeado contra realizado (Fase 6; revisto a 2026-11-04). Cada registo de
ponto liga-se ao turno publicado com que mais coincide, e a entrada e a
saída comparam-se com esse turno. Assim, quem fez 9h–17h30 num turno das
11h às 16h e voltou às 19h tem «entrou 2h mais cedo» e «saiu 1h30 depois»,
e o registo das 19h aparece à parte, como fora do turno.

Um turno aberto conta como ainda a decorrer. A tolerância é a de
`SHIFT_TOLERANCE_MINUTES`.
"""
import datetime
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

ATRASO = "atraso"
CEDO = "cedo"
SAIDA_ANTES = "saida_antes"
SAIDA_DEPOIS = "saida_depois"
SEM_MARCACAO = "sem_marcacao"
FORA_DO_TURNO = "fora_do_turno"


@dataclass
class Desvio:
    tipo: str
    minutos: int | None
    turno: object = None  # o Shift, ou None num registo fora do turno
    registo: object = None  # o TimeEntry fora do turno


def _coincide(registo, turno):
    """Tempo em comum entre o registo e o turno; um registo aberto vai até
    ao fim."""
    fim = registo.check_out or max(turno.end_at, registo.check_in)
    return max(min(fim, turno.end_at) - max(registo.check_in, turno.start_at), datetime.timedelta())


def _minutos(delta):
    return int(delta.total_seconds() // 60)


def calcular(turnos, registos, agora, tolerancia=None):
    """Os desvios de um dia: por turno (atraso, chegou cedo, saiu antes ou
    depois, sem marcação) e os registos que não tocam em nenhum turno."""
    if not turnos:
        return []
    tolerancia = tolerancia if tolerancia is not None else datetime.timedelta(minutes=settings.SHIFT_TOLERANCE_MINUTES)
    turnos = sorted(turnos, key=lambda t: t.start_at)
    por_turno = {t.pk: [] for t in turnos}
    fora = []
    for r in sorted(registos, key=lambda r: r.check_in):
        melhor = max(turnos, key=lambda t: _coincide(r, t))
        if _coincide(r, melhor) > datetime.timedelta():
            por_turno[melhor.pk].append(r)
        else:
            fora.append(r)

    desvios = []
    for t in turnos:
        seus = por_turno[t.pk]
        if not seus:
            if agora > t.start_at + tolerancia:
                desvios.append(Desvio(SEM_MARCACAO, None, t))
            continue
        entrada = seus[0].check_in
        if entrada > t.start_at + tolerancia:
            desvios.append(Desvio(ATRASO, _minutos(entrada - t.start_at), t))
        elif entrada < t.start_at - tolerancia:
            desvios.append(Desvio(CEDO, _minutos(t.start_at - entrada), t))
        if all(r.check_out for r in seus):
            saida = max(r.check_out for r in seus)
            if saida < t.end_at - tolerancia:
                desvios.append(Desvio(SAIDA_ANTES, _minutos(t.end_at - saida), t))
            elif saida > t.end_at + tolerancia:
                desvios.append(Desvio(SAIDA_DEPOIS, _minutos(saida - t.end_at), t))
    desvios += [Desvio(FORA_DO_TURNO, None, registo=r) for r in fora]
    return desvios


def duracao(minutos):
    """45 → «45 min»; 90 → «1h30»; 120 → «2h»."""
    if minutos < 60:
        return f"{minutos} min"
    h, m = divmod(minutos, 60)
    return f"{h}h{m:02d}" if m else f"{h}h"


def _hora(momento):
    return f"{timezone.localtime(momento):%H:%M}"


def textos(turnos, registos, agora):
    """Os desvios em frases curtas, para o ecrã. Com mais de um turno no
    dia, cada frase diz de que turno é."""
    varios = len(turnos) > 1
    frases = []
    for d in calcular(turnos, registos, agora):
        qual = f" (turno das {_hora(d.turno.start_at)})" if varios and d.turno is not None else ""
        if d.tipo == SEM_MARCACAO:
            frases.append(f"Sem marcação{qual}")
        elif d.tipo == ATRASO:
            frases.append(f"Entrou {duracao(d.minutos)} depois{qual}")
        elif d.tipo == CEDO:
            frases.append(f"Entrou {duracao(d.minutos)} mais cedo{qual}")
        elif d.tipo == SAIDA_ANTES:
            frases.append(f"Saiu {duracao(d.minutos)} antes{qual}")
        elif d.tipo == SAIDA_DEPOIS:
            frases.append(f"Saiu {duracao(d.minutos)} depois{qual}")
        else:
            r = d.registo
            fim = _hora(r.check_out) if r.check_out else "…"
            frases.append(f"Fora do turno: {_hora(r.check_in)}–{fim}")
    return frases
