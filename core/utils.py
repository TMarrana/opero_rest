def restaurant_scope(user, qs, field="restaurant"):
    """
    Restringe um queryset ao restaurante do utilizador. Um utilizador sem
    restaurante (superuser de instância) vê tudo — o MVP serve um
    restaurante por instância (secção 2).
    """
    if user.restaurant_id:
        return qs.filter(**{field: user.restaurant_id})
    return qs
