def restaurant_scope(request, qs, field="restaurant"):
    """
    Restringe um queryset à casa ativa do pedido (Fase 9). Sem casa ativa
    não devolve nada: um utilizador sem acesso a nenhuma casa não vê os
    dados de todas.
    """
    if request.restaurant is None:
        return qs.none()
    return qs.filter(**{field: request.restaurant.pk})
