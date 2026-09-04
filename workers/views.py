from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from core.mixins import ManagerRequiredMixin
from core.models import Restaurant
from core.utils import restaurant_scope

from .forms import WorkerForm
from .models import Worker


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
