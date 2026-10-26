def casa(request):
    """Nome do perfil na casa ativa, para o rail do backoffice (Fase 9)."""
    from accounts.models import User

    role = getattr(request, "role", None)
    return {"perfil_ativo": User.Role(role).label if role else ""}
