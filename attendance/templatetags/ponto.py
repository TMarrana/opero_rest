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
