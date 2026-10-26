"""Fase 10: vendas a partir do SAF-T. Só leitura, idempotente, sem dados do
cliente final, por dia de serviço."""
import datetime
import io
import zipfile
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from attendance.models import TimeEntry
from core.models import Restaurant
from sales import reports, sintetico
from sales.models import PosProduct, SalesDocument, SalesImport, SalesLine, SalesSettings
from sales.services import import_saft
from sales.sintetico import Doc
from shifts.models import Shift
from workers.models import Worker

pytestmark = pytest.mark.django_db

NIF = "509123457"
OUTRO_NIF = "510000002"
INICIO, FIM = datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)
BITOQUE = ("P001", "Bitoque", 1, Decimal("8.94"), Decimal("13"))
IMPERIAL = ("B001", "Imperial", 2, Decimal("1.46"), Decimal("23"))


@pytest.fixture
def casa(restaurant):
    restaurant.nif = NIF
    restaurant.save()
    return restaurant


def _hora(dia, h, m=0):
    return datetime.datetime(2026, 9, dia, h, m)


def _docs():
    return [
        Doc("FS 2026A/1", _hora(10, 13), [BITOQUE, IMPERIAL]),
        Doc("FS 2026A/2", _hora(10, 20), [BITOQUE]),
        Doc("FT 2026A/1", _hora(11, 13), [BITOQUE], tipo="FT", cliente=("Joana Cliente", "234567891")),
    ]


def _ficheiro(docs=None, nome="saft.xml", **kwargs):
    kwargs.setdefault("nif", NIF)
    conteudo = sintetico.gerar(documentos=_docs() if docs is None else docs, inicio=INICIO, fim=FIM, **kwargs)
    return SimpleUploadedFile(nome, conteudo, content_type="text/xml")


def _importar(casa, user, docs=None, **kwargs):
    return import_saft(restaurant=casa, upload=_ficheiro(docs, **kwargs), user=user)


class TestImportacao:
    def test_importa_documentos_linhas_e_produtos(self, casa, manager):
        imp = _importar(casa, manager)
        assert imp.documents_new == 3
        assert (imp.period_start, imp.period_end) == (INICIO, FIM)
        assert imp.product_id == "POS de Teste/Fornecedor" and imp.certificate_number == "9999"
        assert not imp.control_mismatch
        doc = SalesDocument.objects.get(number="FS 2026A/1")
        assert doc.series == "2026A" and doc.doc_type == "FS"
        assert doc.net_total == Decimal("8.94") + Decimal("2.92")
        assert doc.lines.count() == 2
        assert doc.source_id == "OP1"
        bitoque = PosProduct.objects.get(restaurant=casa, code="P001")
        assert bitoque.group == "Pratos" and bitoque.last_price == Decimal("8.94")
        # Os produtos de MasterFiles entram todos, mesmo sem vendas.
        assert PosProduct.objects.filter(restaurant=casa).count() == len(sintetico.PRODUTOS_DEMO)

    def test_saft_wrong_nif_rejected(self, casa, manager):
        with pytest.raises(ValidationError, match=OUTRO_NIF):
            _importar(casa, manager, nif=OUTRO_NIF)
        assert not SalesImport.objects.exists()
        assert not SalesDocument.objects.exists()
        assert not PosProduct.objects.exists()

    def test_casa_sem_nif_recusa(self, restaurant, manager):
        with pytest.raises(ValidationError, match="ainda não tem NIF"):
            _importar(restaurant, manager)

    def test_versao_desconhecida_recusada(self, casa, manager):
        with pytest.raises(ValidationError, match="versão 1.03"):
            _importar(casa, manager, versao="1.03_01")

    def test_saft_reimport_is_idempotent(self, casa, manager):
        _importar(casa, manager)
        with pytest.raises(ValidationError, match="já foi importado"):
            _importar(casa, manager)
        assert SalesImport.objects.count() == 1
        assert SalesDocument.objects.count() == 3
        assert SalesLine.objects.count() == 4

    def test_ficheiro_sobreposto_acrescenta_e_atualiza_estado(self, casa, manager):
        _importar(casa, manager)
        docs = _docs()
        docs[1].estado = "A"  # anulada depois
        docs.append(Doc("FS 2026A/3", _hora(12, 13), [IMPERIAL]))
        imp = _importar(casa, manager, docs=docs)
        assert (imp.documents_new, imp.documents_updated, imp.documents_unchanged) == (1, 1, 2)
        assert SalesDocument.objects.count() == 4
        assert SalesDocument.objects.get(number="FS 2026A/2").status == "A"
        assert SalesLine.objects.count() == 5

    def test_saft_cancelled_and_credit_notes(self, casa, manager):
        docs = _docs() + [
            Doc("FS 2026A/3", _hora(10, 21), [BITOQUE], estado="A"),
            Doc("NC 2026A/1", _hora(10, 22), [BITOQUE], tipo="NC"),
        ]
        _importar(casa, manager, docs=docs)
        r = reports.resumo(casa, INICIO, FIM)
        # 3 × bitoque + 2 imperiais; o anulado não conta e a nota abate um bitoque.
        assert r.total == 2 * Decimal("8.94") + Decimal("2.92")
        assert (r.vendas, r.notas) == (3, 1)
        nota = SalesDocument.objects.get(number="NC 2026A/1")
        assert nota.net_total == Decimal("-8.94")
        assert nota.lines.get().quantity == Decimal("-1")
        produtos = {p["product__code"]: p for p in reports.por_produto(casa, INICIO, FIM)}
        assert produtos["P001"]["quantidade"] == 2

    def test_saft_working_documents_ignored(self, casa, manager):
        _importar(casa, manager, consultas_de_mesa=True, recibos=True)
        assert not SalesDocument.objects.filter(number__startswith="CM").exists()
        assert not SalesDocument.objects.filter(number__startswith="RG").exists()
        assert reports.resumo(casa, INICIO, FIM).total == 3 * Decimal("8.94") + Decimal("2.92")

    def test_saft_keeps_no_customer_data(self, casa, manager):
        _importar(casa, manager)
        guardado = []
        for model in (SalesImport, SalesDocument, SalesLine, PosProduct, SalesSettings):
            for linha in model.objects.values():
                guardado.extend(str(v) for v in linha.values())
        texto = " ".join(guardado)
        for dado in ("Joana Cliente", "234567891", "Rua do Cliente", "cliente@exemplo.pt", "999999990"):
            assert dado not in texto

    def test_saft_entity_expansion_rejected(self, casa, manager):
        prologo = '<!DOCTYPE AuditFile [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>'
        with pytest.raises(ValidationError, match="DTD ou entidades"):
            _importar(casa, manager, prologo=prologo)
        assert not SalesDocument.objects.exists()

    def test_xml_invalido_recusado(self, casa, manager):
        upload = SimpleUploadedFile("saft.xml", b"<AuditFile><Header>", content_type="text/xml")
        with pytest.raises(ValidationError, match="não é um XML válido"):
            import_saft(restaurant=casa, upload=upload, user=manager)

    def test_sem_documentos_de_venda_recusado(self, casa, manager):
        conteudo = sintetico.gerar(nif=NIF, documentos=[], inicio=INICIO, fim=FIM).replace(
            b"<SalesInvoices>", b"<Outro>"
        ).replace(b"</SalesInvoices>", b"</Outro>")
        upload = SimpleUploadedFile("saft.xml", conteudo)
        with pytest.raises(ValidationError, match="SalesInvoices"):
            import_saft(restaurant=casa, upload=upload, user=manager)

    def test_aceita_zip(self, casa, manager):
        memoria = io.BytesIO()
        with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("SAFT_509123457_202609.xml", sintetico.gerar(nif=NIF, documentos=_docs(), inicio=INICIO, fim=FIM))
        upload = SimpleUploadedFile("saft.zip", memoria.getvalue(), content_type="application/zip")
        imp = import_saft(restaurant=casa, upload=upload, user=manager)
        assert imp.documents_new == 3
        # O mesmo XML, fora do .zip, é o mesmo ficheiro.
        with pytest.raises(ValidationError, match="já foi importado"):
            _importar(casa, manager)

    def test_totais_de_controlo_diferentes_assinalados(self, casa, manager):
        conteudo = sintetico.gerar(nif=NIF, documentos=_docs(), inicio=INICIO, fim=FIM).replace(
            b"<TotalCredit>", b"<TotalCredit>1", 1
        )
        imp = import_saft(restaurant=casa, upload=SimpleUploadedFile("saft.xml", conteudo), user=manager)
        assert imp.control_mismatch


class TestDiaDeServico:
    def test_sale_after_midnight_counts_on_service_day(self, casa, manager):
        _importar(casa, manager, docs=[Doc("FS 2026A/1", _hora(11, 1, 30), [BITOQUE])])
        doc = SalesDocument.objects.get()
        assert doc.service_date == datetime.date(2026, 9, 10)
        assert timezone.localtime(doc.system_entry).hour == 1

    def test_hora_de_corte_por_casa(self, casa, manager):
        regras = SalesSettings.for_restaurant(casa)
        regras.day_cutoff_hour = 0
        regras.save()
        _importar(casa, manager, docs=[Doc("FS 2026A/1", _hora(11, 1, 30), [BITOQUE])])
        assert SalesDocument.objects.get().service_date == datetime.date(2026, 9, 11)


class TestSeries:
    @pytest.fixture
    def irma(self, casa):
        return Restaurant.objects.create(organization=casa.organization, name="Tasca da Baixa", slug="baixa", nif=NIF)

    def _docs_duas_series(self):
        return [
            Doc("FS A/1", _hora(10, 13), [BITOQUE]),
            Doc("FS B/1", _hora(10, 13), [IMPERIAL]),
            Doc("FS B/2", _hora(10, 14), [IMPERIAL]),
        ]

    def test_mesmo_nif_sem_series_recusado(self, casa, irma, manager):
        with pytest.raises(ValidationError, match="mesmo NIF"):
            _importar(casa, manager, docs=self._docs_duas_series())
        assert not SalesDocument.objects.exists()

    def test_cada_casa_importa_as_suas_series(self, casa, irma, manager, admin_user):
        for r, serie in ((casa, "A"), (irma, "B")):
            regras = SalesSettings.for_restaurant(r)
            regras.series = serie
            regras.save()
        imp = _importar(casa, manager, docs=self._docs_duas_series())
        assert imp.documents_new == 1
        assert (imp.documents_other_series, imp.other_series) == (2, "B")
        imp_b = _importar(irma, admin_user, docs=self._docs_duas_series())
        assert imp_b.documents_new == 2
        assert list(SalesDocument.objects.filter(restaurant=casa).values_list("number", flat=True)) == ["FS A/1"]


class TestHorasTrabalhadas:
    def test_vendas_por_hora_trabalhada(self, casa, manager):
        _importar(casa, manager)
        w = Worker.objects.create(restaurant=casa, full_name="Marta Silva")
        tz = timezone.get_current_timezone()
        TimeEntry.objects.create(
            worker=w,
            check_in=datetime.datetime(2026, 9, 10, 11, 0, tzinfo=tz),
            check_out=datetime.datetime(2026, 9, 10, 15, 0, tzinfo=tz),
        )
        # Dia 11 sem ponto mas com turno publicado: usam-se as horas previstas.
        Shift.objects.create(
            restaurant=casa, worker=w, state=Shift.State.PUBLICADO,
            start_at=datetime.datetime(2026, 9, 11, 12, 0, tzinfo=tz),
            end_at=datetime.datetime(2026, 9, 11, 14, 0, tzinfo=tz),
        )
        regras = SalesSettings.for_restaurant(casa)
        regras.hourly_cost = Decimal("10")
        regras.save()
        linhas, totais = reports.por_dia(casa, INICIO, FIM)
        dia10 = next(l for l in linhas if l["dia"] == datetime.date(2026, 9, 10))
        assert dia10["horas"] == datetime.timedelta(hours=4) and not dia10["previstas"]
        assert dia10["por_hora"] == ((2 * Decimal("8.94") + Decimal("2.92")) / 4).quantize(Decimal("0.01"))
        dia11 = next(l for l in linhas if l["dia"] == datetime.date(2026, 9, 11))
        assert dia11["horas"] == datetime.timedelta(hours=2) and dia11["previstas"]
        assert dia10["custo_pessoal"] == (Decimal(40) / (2 * Decimal("8.94") + Decimal("2.92")) * 100).quantize(Decimal("0.1"))
        assert totais["horas"] == datetime.timedelta(hours=6)


class TestEcras:
    def test_so_admin_e_gerente(self, client, stock_user, staff_user):
        for user in (stock_user, staff_user):
            client.force_login(user)
            assert client.get(reverse("sales:vendas")).status_code == 403
            assert client.get(reverse("sales:importar")).status_code == 403

    def test_gerente_importa_pelo_ecra(self, client, casa, manager):
        client.force_login(manager)
        resp = client.post(reverse("sales:importar"), {"ficheiro": _ficheiro()})
        assert resp.status_code == 302
        assert SalesDocument.objects.filter(restaurant=casa).count() == 3
        resp = client.post(reverse("sales:importar"), {"ficheiro": _ficheiro(nif=OUTRO_NIF)})
        assert resp.status_code == 400
        assert OUTRO_NIF in resp.content.decode()

    def test_ecra_vendas_e_exportacoes(self, client, casa, manager):
        _importar(casa, manager)
        client.force_login(manager)
        resp = client.get(reverse("sales:vendas"), {"mes": "2026-09"})
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "Bitoque" in html and "Por hora" in html
        assert "29,74 €" in html  # 3 × 8,94 + 2 × 1,46
        csv_dias = client.get(reverse("sales:vendas"), {"de": "2026-09-10", "ate": "2026-09-11", "exportar": "dias"})
        texto = csv_dias.content.decode("utf-8-sig")
        assert texto.splitlines()[1].startswith("2026-09-10;20,80;2;10,40")
        assert texto.splitlines()[-1].startswith("Total;29,74;3")
        csv_prod = client.get(reverse("sales:vendas"), {"mes": "2026-09", "exportar": "produtos"}).content.decode("utf-8-sig")
        assert "P001;Bitoque;Pratos;3;26,82" in csv_prod

    def test_compara_com_o_mes_anterior(self, client, casa, manager):
        _importar(casa, manager)
        outubro = [Doc("FS 2026A/10", datetime.datetime(2026, 10, 5, 13), [BITOQUE, BITOQUE])]
        import_saft(
            restaurant=casa,
            upload=SimpleUploadedFile(
                "out.xml", sintetico.gerar(nif=NIF, documentos=outubro, inicio=datetime.date(2026, 10, 1), fim=datetime.date(2026, 10, 31))
            ),
            user=manager,
        )
        client.force_login(manager)
        resp = client.get(reverse("sales:vendas"), {"mes": "2026-10"})
        assert resp.status_code == 200
        # Outubro só tem vendas até dia 5: compara-se com 1 a 5 de setembro,
        # onde não há nenhuma.
        assert (resp.context["anterior_inicio"], resp.context["anterior_fim"]) == (INICIO, datetime.date(2026, 9, 5))
        assert resp.context["var_vendas"] is None
        resp = client.get(reverse("sales:vendas"), {"de": "2026-10-01", "ate": "2026-10-05"})
        assert (resp.context["anterior_inicio"], resp.context["anterior_fim"]) == (datetime.date(2026, 9, 26), FIM)
        resp = client.get(reverse("sales:vendas"), {"de": "2026-10-01", "ate": "2026-10-31"})
        assert (resp.context["anterior_inicio"], resp.context["anterior_fim"]) == (datetime.date(2026, 9, 26), FIM)
        # Contagens inteiras: 1 documento contra 3.
        assert reports.variacao(1, 3) == Decimal(-67)
        assert reports.variacao(3, 0) is None

    def test_ecra_vazio_leva_a_importar(self, client, casa, manager):
        client.force_login(manager)
        html = client.get(reverse("sales:vendas")).content.decode()
        assert "Ainda não há vendas" in html

    def test_vendas_de_outra_casa_nao_aparecem(self, client, casa, manager, admin_user):
        outra = Restaurant.objects.create(organization=casa.organization, name="Outra", slug="outra", nif=OUTRO_NIF)
        _importar(outra, admin_user, nif=OUTRO_NIF)
        client.force_login(manager)
        assert "Ainda não há vendas" in client.get(reverse("sales:vendas"), {"mes": "2026-09"}).content.decode()

    def test_regras_so_para_o_admin(self, client, casa, manager, admin_user):
        client.force_login(manager)
        assert client.get(reverse("sales:regras")).status_code == 403
        client.force_login(admin_user)
        resp = client.post(reverse("sales:regras"), {"day_cutoff_hour": 4, "series": " A , B ", "hourly_cost": "12.50"})
        assert resp.status_code == 302
        regras = SalesSettings.objects.get(restaurant=casa)
        assert (regras.day_cutoff_hour, regras.series, regras.hourly_cost) == (4, "A, B", Decimal("12.50"))
        resp = client.post(reverse("sales:regras"), {"day_cutoff_hour": 14, "series": ""})
        assert resp.status_code == 400

    def test_dashboard_avisa_vendas_atrasadas(self, client, casa, manager):
        client.force_login(manager)
        assert "sem importar o SAF-T" not in client.get(reverse("dashboard:home")).content.decode()
        _importar(casa, manager)
        html = client.get(reverse("dashboard:home")).content.decode()
        assert "sem importar o SAF-T" in html

    def test_painel_do_grupo_mostra_vendas(self, client, casa, manager):
        from django.contrib.auth import get_user_model

        hoje = timezone.localdate()
        docs = [Doc("FS 2026A/9", datetime.datetime.combine(hoje, datetime.time(13)), [BITOQUE])]
        import_saft(
            restaurant=casa,
            upload=SimpleUploadedFile(
                "saft.xml", sintetico.gerar(nif=NIF, documentos=docs, inicio=hoje.replace(day=1), fim=hoje)
            ),
            user=manager,
        )
        dono = get_user_model().objects.create_user(
            email="dono@tasca.pt", password="x-segredo-123", organization=casa.organization, is_group_admin=True
        )
        client.force_login(dono)
        html = client.get(reverse("grupo:painel")).content.decode()
        assert "8,94 €" in html
