"""
Casas e acessos do grupo (Fase 9). Só o Admin do grupo: cria e edita as
casas e decide quem tem acesso a cada uma, e com que perfil. As contas
criam-se na ficha do trabalhador («Conta da app»); aqui só se lhes dá ou
tira acesso a outras casas.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views import View

from accounts.services import dar_acesso, tirar_acesso

from .mixins import GroupAdminRequiredMixin
from .models import Restaurant

User = get_user_model()
_INPUT = {"class": "campo-input"}


class RestaurantForm(forms.ModelForm):
    class Meta:
        model = Restaurant
        fields = ["name", "nif", "address", "municipality", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs=_INPUT),
            "nif": forms.TextInput(attrs={**_INPUT, "class": "campo-input font-dados", "inputmode": "numeric"}),
            "address": forms.TextInput(attrs=_INPUT),
            "municipality": forms.TextInput(attrs=_INPUT),
        }
        labels = {"is_active": "Casa ativa"}
        help_texts = {
            "nif": "O NIF da empresa que fatura nesta casa. Serve para reconhecer o ficheiro SAF-T que o POS exporta.",
            "is_active": "Uma casa inativa deixa de aparecer no seletor e no painel do grupo. Nada se apaga.",
        }


def _slug_livre(nome):
    base = slugify(nome)[:40] or "casa"
    slug, n = base, 2
    while Restaurant.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _casas_do_grupo(request):
    return Restaurant.objects.filter(organization_id=request.user.organization_id)


class RestaurantListView(GroupAdminRequiredMixin, View):
    def get(self, request):
        casas = _casas_do_grupo(request).order_by("-is_active", "name")
        return render(request, "manage/grupo/casas.html", {"casas": casas})


class RestaurantFormView(GroupAdminRequiredMixin, View):
    def _casa(self, request, pk):
        return None if pk is None else get_object_or_404(_casas_do_grupo(request), pk=pk)

    def get(self, request, pk=None):
        casa = self._casa(request, pk)
        return render(request, "manage/grupo/casa_form.html", {"form": RestaurantForm(instance=casa), "casa": casa})

    def post(self, request, pk=None):
        casa = self._casa(request, pk)
        form = RestaurantForm(request.POST, instance=casa)
        if not form.is_valid():
            return render(request, "manage/grupo/casa_form.html", {"form": form, "casa": casa})
        nova = form.save(commit=False)
        if casa is None:
            nova.organization_id = request.user.organization_id
            nova.slug = _slug_livre(nova.name)
        nova.save()
        messages.success(request, "Casa guardada" if casa else "Casa criada")
        return redirect("grupo:casas")


class AccessForm(forms.Form):
    user = forms.ModelChoiceField(label="Conta", queryset=User.objects.none(), widget=forms.Select(attrs=_INPUT))
    # Começa no perfil com menos acesso: dar mais é uma escolha explícita.
    role = forms.ChoiceField(
        label="Perfil", choices=User.Role.choices, initial=User.Role.STAFF, widget=forms.Select(attrs=_INPUT)
    )

    def __init__(self, *args, casa, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = (
            User.objects.filter(organization_id=casa.organization_id, is_active=True, is_group_admin=False)
            .exclude(memberships__restaurant=casa)
            .order_by("first_name", "last_name", "email")
        )


class AccessView(GroupAdminRequiredMixin, View):
    """Quem tem acesso a uma casa, e com que perfil. O Admin do grupo tem
    acesso a todas e não aparece na lista."""

    template_name = "manage/grupo/acessos.html"

    def _render(self, request, casa, form=None):
        acessos = casa.memberships.select_related("user").order_by("user__first_name", "user__email")
        return render(
            request,
            self.template_name,
            {"casa": casa, "acessos": acessos, "form": form or AccessForm(casa=casa), "perfis": User.Role.choices},
        )

    def get(self, request, pk):
        return self._render(request, get_object_or_404(_casas_do_grupo(request), pk=pk))

    def post(self, request, pk):
        casa = get_object_or_404(_casas_do_grupo(request), pk=pk)
        acao = request.POST.get("acao")
        if acao == "dar":
            form = AccessForm(request.POST, casa=casa)
            if not form.is_valid():
                return self._render(request, casa, form)
            conta, role = form.cleaned_data["user"], form.cleaned_data["role"]
        else:
            conta = get_object_or_404(
                User.objects.filter(organization_id=casa.organization_id, memberships__restaurant=casa),
                pk=request.POST.get("user"),
            )
            role = request.POST.get("role")
        if conta == request.user:
            messages.error(request, "Não pode mudar o seu próprio acesso.")
            return redirect("grupo:acessos", pk=casa.pk)
        try:
            if acao == "tirar":
                tirar_acesso(conta, casa)
                messages.success(request, f"{conta} deixou de ter acesso a {casa}")
            elif role in User.Role.values:
                dar_acesso(conta, casa, role)
                messages.success(request, "Acesso guardado")
            else:
                messages.error(request, "Perfil inválido.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("grupo:acessos", pk=casa.pk)
