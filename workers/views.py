import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from core.mixins import ManagerRequiredMixin
from core.models import Restaurant
from core.utils import restaurant_scope

from .forms import AccountCreateForm, AccountRoleForm, KioskCodeForm, WorkerForm, roles_que_gere
from .models import Worker

User = get_user_model()
# Sem letras e algarismos que se confundem ao ditar (0/o, 1/l/i).
_ALFABETO_PROVISORIA = "abcdefghjkmnpqrstuvwxyz23456789"


class WorkerListView(ManagerRequiredMixin, TemplateView):
    template_name = "manage/workers/lista.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = restaurant_scope(self.request.user, Worker.objects.select_related("user"))
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(job_title__icontains=q))
        if not self.request.GET.get("inativos"):
            qs = qs.filter(is_active=True)
        ctx["workers"] = qs
        ctx["filtros"] = {"q": q, "inativos": self.request.GET.get("inativos", "")}
        return ctx

    def get(self, request, *args, **kwargs):
        if request.headers.get("HX-Request"):
            return render(request, "partials/workers/tabela_workers.html", self.get_context_data())
        return super().get(request, *args, **kwargs)


class WorkerFormView(ManagerRequiredMixin, View):
    def _get_worker(self, request, pk):
        if pk is None:
            return None
        return get_object_or_404(restaurant_scope(request.user, Worker.objects.all()), pk=pk)

    def get(self, request, pk=None):
        worker = self._get_worker(request, pk)
        restaurant = request.user.restaurant or Restaurant.objects.first()
        form = WorkerForm(instance=worker, restaurant=restaurant)
        return render(request, "manage/workers/form.html", {"form": form, "worker": worker})

    def post(self, request, pk=None):
        worker = self._get_worker(request, pk)
        restaurant = request.user.restaurant or Restaurant.objects.first()
        if restaurant is None:
            messages.error(request, "Ainda não há restaurante configurado. Crie-o no admin primeiro.")
            return redirect("workers:lista")
        form = WorkerForm(request.POST, instance=worker, restaurant=restaurant)
        if not form.is_valid():
            return render(request, "manage/workers/form.html", {"form": form, "worker": worker})
        novo = form.save(commit=False)
        novo.restaurant = restaurant
        novo.save()
        messages.success(request, "Trabalhador guardado" if worker else "Trabalhador criado")
        return redirect("workers:lista")


def _worker_do_gerente(request, pk):
    return get_object_or_404(restaurant_scope(request.user, Worker.objects.select_related("user")), pk=pk)


def password_provisoria():
    """Três grupos de quatro, fácil de ditar: o titular muda-a no primeiro
    login (Fase 7)."""
    return "-".join("".join(secrets.choice(_ALFABETO_PROVISORIA) for _ in range(4)) for _ in range(3))


class WorkerCodeView(ManagerRequiredMixin, View):
    """Definir ou repor o código de ponto do tablet (Fase 7). Não exige
    conta: quem não tem email pica na mesma."""

    def get(self, request, pk):
        worker = _worker_do_gerente(request, pk)
        return render(request, "manage/workers/codigo.html", {"worker": worker, "form": KioskCodeForm()})

    def post(self, request, pk):
        worker = _worker_do_gerente(request, pk)
        form = KioskCodeForm(request.POST)
        if not form.is_valid():
            return render(request, "manage/workers/codigo.html", {"worker": worker, "form": form})
        worker.set_kiosk_code(form.cleaned_data["codigo"])
        messages.success(request, "Código definido")
        return redirect("workers:lista")


class WorkerAccountView(ManagerRequiredMixin, View):
    """Conta da app do trabalhador (Fase 7): criar com email e perfil,
    repor a password e mudar o perfil. A password provisória só se mostra
    uma vez, nesta resposta, e o titular tem de a mudar no primeiro login.

    O gerente só gere contas de Colaborador e Resp. stock; ninguém muda o
    próprio perfil nem repõe a própria password aqui (secção 7)."""

    template_name = "manage/workers/conta.html"

    def _pode_gerir(self, request, conta):
        return conta != request.user and conta.role in roles_que_gere(request.user)

    def _render(self, request, worker, **extra):
        contexto = {"worker": worker, "conta": worker.user}
        if worker.user is None:
            contexto["form"] = extra.pop("form", None) or AccountCreateForm(gestor=request.user)
        else:
            contexto["pode_gerir"] = self._pode_gerir(request, worker.user)
            contexto["form_perfil"] = extra.pop("form_perfil", None) or AccountRoleForm(
                gestor=request.user, initial={"role": worker.user.role}
            )
        contexto.update(extra)
        return render(request, self.template_name, contexto)

    def _mostrar_provisoria(self, request, worker, password):
        resp = render(request, "manage/workers/password_provisoria.html", {"worker": worker, "password": password})
        resp["Cache-Control"] = "no-store"
        return resp

    def get(self, request, pk):
        return self._render(request, _worker_do_gerente(request, pk))

    def post(self, request, pk):
        worker = _worker_do_gerente(request, pk)
        acao = request.POST.get("acao", "")
        conta = worker.user

        if conta is None:
            form = AccountCreateForm(request.POST, gestor=request.user)
            if not form.is_valid():
                return self._render(request, worker, form=form)
            password = password_provisoria()
            nome, _, apelido = worker.full_name.partition(" ")
            worker.user = User.objects.create_user(
                email=form.cleaned_data["email"],
                password=password,
                restaurant=worker.restaurant,
                role=form.cleaned_data["role"],
                first_name=nome,
                last_name=apelido,
                must_change_password=True,
            )
            worker.save(update_fields=["user", "updated_at"])
            return self._mostrar_provisoria(request, worker, password)

        if not self._pode_gerir(request, conta):
            messages.error(request, "Esta conta só o administrador a pode gerir.")
            return redirect("workers:conta", pk=worker.pk)
        if acao == "repor":
            password = password_provisoria()
            conta.set_password(password)
            conta.must_change_password = True
            conta.save(update_fields=["password", "must_change_password"])
            return self._mostrar_provisoria(request, worker, password)
        if acao == "perfil":
            form = AccountRoleForm(request.POST, gestor=request.user)
            if not form.is_valid():
                return self._render(request, worker, form_perfil=form)
            conta.role = form.cleaned_data["role"]
            conta.save(update_fields=["role"])
            messages.success(request, "Perfil guardado")
            return redirect("workers:conta", pk=worker.pk)
        messages.error(request, "Ação inválida.")
        return redirect("workers:conta", pk=worker.pk)
