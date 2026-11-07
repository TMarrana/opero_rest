import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import TemplateView

from accounts.services import dar_acesso, perfil_na_casa
from core.mixins import ManagerRequiredMixin
from core.utils import restaurant_scope, workers_scope

from .forms import AccountCreateForm, AccountRoleForm, KioskCodeForm, WorkerForm, roles_que_gere
from .models import Worker
from .services import delete_blockers, delete_worker

User = get_user_model()
# Sem letras e algarismos que se confundem ao ditar (0/o, 1/l/i).
_ALFABETO_PROVISORIA = "abcdefghjkmnpqrstuvwxyz23456789"


class WorkerListView(ManagerRequiredMixin, TemplateView):
    template_name = "manage/workers/lista.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = workers_scope(self.request, Worker.objects.select_related("user", "restaurant"))
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
        return get_object_or_404(restaurant_scope(request, Worker.objects.all()), pk=pk)

    def get(self, request, pk=None):
        worker = self._get_worker(request, pk)
        restaurant = request.restaurant
        form = WorkerForm(instance=worker, restaurant=restaurant)
        return render(request, "manage/workers/form.html", self._contexto(request, form, worker))

    def _contexto(self, request, form, worker):
        contexto = {"form": form, "worker": worker}
        if worker is not None:
            bloqueios = delete_blockers(worker)
            contexto["bloqueios"] = bloqueios
            contexto["propria"] = worker.user_id == request.user.pk
            contexto["conta_protegida"] = bool(
                worker.user and worker.user_id != request.user.pk and not _pode_gerir_conta(request, worker.user)
            )
            if bloqueios:
                fim = (
                    "Pode desativá-lo: deixa de aparecer nas listas e de picar o ponto, e o histórico fica guardado."
                    if worker.is_active
                    else "Já está desativado."
                )
                contexto["aviso_bloqueio"] = (
                    f"{worker.full_name} tem histórico que tem de ficar guardado ({', '.join(bloqueios)}). {fim}"
                )
        return contexto

    def post(self, request, pk=None):
        worker = self._get_worker(request, pk)
        restaurant = request.restaurant
        if restaurant is None:
            messages.error(request, "Ainda não há restaurante configurado. Crie-o no admin primeiro.")
            return redirect("workers:lista")
        form = WorkerForm(request.POST, instance=worker, restaurant=restaurant)
        if not form.is_valid():
            return render(request, "manage/workers/form.html", self._contexto(request, form, worker))
        novo = form.save(commit=False)
        novo.restaurant = restaurant
        if novo.is_active:
            novo.end_date = None  # reativar apaga a data de saída
        novo.save()
        form.save_m2m()
        messages.success(request, "Trabalhador guardado" if worker else "Trabalhador criado")
        return redirect("workers:lista")


class WorkerDeleteView(ManagerRequiredMixin, View):
    """Apagar a ficha de um trabalhador sem histórico (ver workers.services)."""

    def post(self, request, pk):
        worker = _worker_do_gerente(request, pk)
        nome = worker.full_name
        try:
            if worker.user and worker.user != request.user and not _pode_gerir_conta(request, worker.user):
                raise ValidationError("A conta da app desta ficha só o administrador a pode eliminar.")
            delete_worker(worker=worker, user=request.user)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("workers:editar", pk=pk)
        messages.success(request, f"{nome} eliminado")
        return redirect("workers:lista")


class WorkerDeactivateView(ManagerRequiredMixin, View):
    """Desativar a ficha (a alternativa a eliminar quando há histórico)."""

    def post(self, request, pk):
        worker = _worker_do_gerente(request, pk)
        valor = request.POST.get("data_saida", "").strip()
        if valor:
            try:
                saida = parse_date(valor)
            except ValueError:  # bem formada mas inexistente, como 2026-02-31
                saida = None
            if saida is None:
                messages.error(request, "A data de saída não é válida. Indique um dia no formato AAAA-MM-DD.")
                return redirect("workers:editar", pk=pk)
        else:
            saida = timezone.localdate()
        worker.is_active = False
        worker.end_date = saida
        worker.save(update_fields=["is_active", "end_date", "updated_at"])
        messages.success(request, f"{worker.full_name} desativado")
        return redirect("workers:lista")


def _pode_gerir_conta(request, conta):
    return perfil_na_casa(conta, request.restaurant) in roles_que_gere(request.role)


def _worker_do_gerente(request, pk):
    return get_object_or_404(restaurant_scope(request, Worker.objects.select_related("user")), pk=pk)


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
        return conta != request.user and perfil_na_casa(conta, request.restaurant) in roles_que_gere(request.role)

    def _render(self, request, worker, **extra):
        contexto = {"worker": worker, "conta": worker.user}
        if worker.user is None:
            contexto["form"] = extra.pop("form", None) or AccountCreateForm(gestor=request.role)
        else:
            contexto["pode_gerir"] = self._pode_gerir(request, worker.user)
            contexto["form_perfil"] = extra.pop("form_perfil", None) or AccountRoleForm(
                gestor=request.role, initial={"role": perfil_na_casa(worker.user, request.restaurant)}
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
            form = AccountCreateForm(request.POST, gestor=request.role)
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
            form = AccountRoleForm(request.POST, gestor=request.role)
            if not form.is_valid():
                return self._render(request, worker, form_perfil=form)
            dar_acesso(conta, worker.restaurant, form.cleaned_data["role"])
            messages.success(request, "Perfil guardado")
            return redirect("workers:conta", pk=worker.pk)
        messages.error(request, "Ação inválida.")
        return redirect("workers:conta", pk=worker.pk)
