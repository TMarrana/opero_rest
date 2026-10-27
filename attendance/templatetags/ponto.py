from django import template

register = template.Library()


@register.filter
def horas(delta):
    """Duração em horas e minutos, como no ecrã de ponto: 8h05."""
    if delta is None:
        return "—"
    total = int(delta.total_seconds() // 60)
    h, m = divmod(total, 60)
    return f"{h}h{m:02d}"


@register.filter
def horas_sinal(delta):
    """Uma diferença de horas com sinal: +1h30 ou −0h45 (Fase 15)."""
    if delta is None:
        return "—"
    segundos = delta.total_seconds()
    sinal = "−" if segundos < 0 else "+"
    h, m = divmod(int(abs(segundos) // 60), 60)
    return f"{sinal}{h}h{m:02d}"
