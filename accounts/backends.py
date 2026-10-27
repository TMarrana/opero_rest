from django.contrib.auth.backends import ModelBackend


class GroupHostBackend(ModelBackend):
    """No subdomínio de um grupo só entra quem é desse grupo. Uma conta de
    outro grupo recebe o mesmo erro que uma password errada, para o
    endereço não revelar que contas existem. O superutilizador entra em
    todos (`core.middleware.OrganizationHostMiddleware`)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username=username, password=password, **kwargs)
        grupo = getattr(request, "organization", None)
        if user is not None and grupo is not None and not user.is_superuser and user.organization_id != grupo.pk:
            return None
        return user
