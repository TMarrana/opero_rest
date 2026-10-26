"""
Importação do SAF-T (Fase 10). Valida antes de gravar e grava tudo numa
transação: ou o ficheiro entra inteiro, ou nada muda.

Importar o mesmo período duas vezes não duplica nada, porque os documentos
se identificam pelo número (único por casa). Um ficheiro que se sobrepõe a
outro já importado só acrescenta os documentos novos e atualiza o estado
dos que mudaram, como uma fatura anulada depois.
"""
import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Restaurant

from . import saft
from .models import PosProduct, SalesDocument, SalesImport, SalesLine, SalesSettings

_LOTE = 500


def service_date(local_entry, cutoff_hour):
    """O dia de serviço de uma venda: antes da hora de corte, conta no dia
    anterior. Calcula-se na hora local, como vem no ficheiro, para a noite
    da mudança de hora não trocar o dia."""
    return (local_entry - datetime.timedelta(hours=cutoff_hour)).date()


def _check_header(restaurant):
    def check(header):
        if not header.version.startswith("1.04"):
            raise saft.SaftError(
                f"Este ficheiro é da versão {header.version or 'desconhecida'} do SAF-T. "
                "O Opero lê a versão 1.04_01, que é a que os programas certificados exportam."
            )
        if header.tax_id != restaurant.nif:
            raise saft.SaftError(
                f"Este ficheiro é do NIF {header.tax_id or 'em branco'}, e o NIF de {restaurant} é {restaurant.nif}. "
                "Confirme que exportou o ficheiro da casa certa."
            )
        if header.start > header.end:
            raise saft.SaftError("O período do ficheiro acaba antes de começar. Exporte o ficheiro outra vez.")

    return check


def _series_filter(restaurant, settings_):
    """As séries a importar nesta casa, ou None para todas. Se outra casa
    fatura com o mesmo NIF, as séries são obrigatórias: sem elas, as
    vendas das duas casas contavam em ambas."""
    series = settings_.series_list()
    if series:
        return set(series)
    irmas = Restaurant.objects.filter(nif=restaurant.nif).exclude(pk=restaurant.pk)
    if irmas.exists():
        nomes = ", ".join(r.name for r in irmas)
        raise ValidationError(
            f"{nomes} fatura{'m' if irmas.count() > 1 else ''} com o mesmo NIF. "
            "Indique as séries desta casa em Vendas → Regras, para as vendas não contarem nas duas."
        )
    return None


def _control_matches(ficheiro):
    """Os totais de controlo de SalesInvoices batem com as linhas lidas? Os
    anulados nunca entram; os já faturados (F) entram consoante o programa,
    por isso aceitam-se as duas somas."""
    if ficheiro.control_credit is None or ficheiro.control_debit is None:
        return True
    for excluidos in (("A",), ("A", "F")):
        credito = sum((l.credit for d in ficheiro.documents if d.status not in excluidos for l in d.lines), Decimal(0))
        debito = sum((l.debit for d in ficheiro.documents if d.status not in excluidos for l in d.lines), Decimal(0))
        if abs(credito - ficheiro.control_credit) < Decimal("0.01") and abs(debito - ficheiro.control_debit) < Decimal("0.01"):
            return True
    return False


def import_saft(*, restaurant, upload, user):
    """Importa um ficheiro SAF-T carregado (XML ou .zip) para a casa.
    Devolve a SalesImport. Recusa com ValidationError, sem gravar nada."""
    if not restaurant.nif:
        raise ValidationError(
            f"{restaurant} ainda não tem NIF. O Admin do grupo preenche-o em Grupo → Casas e acessos."
        )
    regras = SalesSettings.for_restaurant(restaurant)
    series = _series_filter(restaurant, regras)
    try:
        ficheiro = saft.parse(saft.open_upload(upload), on_header=_check_header(restaurant))
    except saft.SaftError as exc:
        raise ValidationError(str(exc))
    if not ficheiro.has_sales_invoices:
        raise ValidationError(
            "O ficheiro não traz documentos de venda (SalesInvoices). Exporte o SAF-T de faturação, e não o de contabilidade."
        )
    anterior = SalesImport.objects.filter(restaurant=restaurant, file_hash=ficheiro.file_hash).first()
    if anterior is not None:
        raise ValidationError(
            f"Este ficheiro já foi importado a {timezone.localtime(anterior.created_at):%d/%m/%Y} "
            f"por {anterior.imported_by}. Nada mudou."
        )

    documentos, outras = [], {}
    for d in ficheiro.documents:
        if series is None or d.series in series:
            documentos.append(d)
        else:
            outras[d.series] = outras.get(d.series, 0) + 1

    with transaction.atomic():
        importacao = SalesImport.objects.create(
            restaurant=restaurant,
            file_name=getattr(upload, "name", "")[:200],
            file_hash=ficheiro.file_hash,
            period_start=ficheiro.header.start,
            period_end=ficheiro.header.end,
            tax_id=ficheiro.header.tax_id,
            product_id=ficheiro.header.product_id[:255],
            certificate_number=ficheiro.header.certificate_number[:20],
            imported_by=user,
            documents_other_series=sum(outras.values()),
            other_series=", ".join(sorted(outras))[:200],
            control_mismatch=not _control_matches(ficheiro),
        )
        produtos = _save_products(restaurant, ficheiro, documentos)
        _save_documents(restaurant, importacao, documentos, produtos, regras.day_cutoff_hour)
        _update_prices(produtos, documentos)
    importacao.other_types = ficheiro.other_types
    return importacao


def _save_products(restaurant, ficheiro, documentos):
    """Cria ou atualiza os produtos do POS. Uma linha com um código que não
    vem nos produtos do ficheiro cria o produto com a descrição da linha."""
    lidos = dict(ficheiro.products)
    for d in documentos:
        for l in d.lines:
            if l.product_code not in lidos:
                lidos[l.product_code] = saft.Product(l.product_code, l.description, "")
    existentes = {p.code: p for p in PosProduct.objects.filter(restaurant=restaurant, code__in=list(lidos))}
    novos, alterados = [], []
    for codigo, p in lidos.items():
        atual = existentes.get(codigo)
        descricao, familia = p.description[:200] or codigo, p.group[:100]
        if atual is None:
            novos.append(PosProduct(restaurant=restaurant, code=codigo[:60], description=descricao, group=familia))
        elif (atual.description, atual.group) != (descricao, familia):
            atual.description, atual.group = descricao, familia
            alterados.append(atual)
    PosProduct.objects.bulk_create(novos, batch_size=_LOTE)
    PosProduct.objects.bulk_update(alterados, ["description", "group"], batch_size=_LOTE)
    return {p.code: p for p in PosProduct.objects.filter(restaurant=restaurant, code__in=list(lidos))}


def _save_documents(restaurant, importacao, documentos, produtos, cutoff_hour):
    numeros = [d.number for d in documentos]
    existentes = {}
    for i in range(0, len(numeros), _LOTE):
        for doc in SalesDocument.objects.filter(restaurant=restaurant, number__in=numeros[i : i + _LOTE]):
            existentes[doc.number] = doc

    novos, mudados, iguais = [], [], 0
    for d in documentos:
        atual = existentes.get(d.number)
        if atual is None:
            novos.append(d)
        elif atual.status != d.status:
            atual.status = d.status
            mudados.append(atual)
        else:
            iguais += 1
    SalesDocument.objects.bulk_update(mudados, ["status"], batch_size=_LOTE)

    tz = timezone.get_current_timezone()
    criados = SalesDocument.objects.bulk_create(
        [
            SalesDocument(
                restaurant=restaurant,
                sales_import=importacao,
                number=d.number[:60],
                doc_type=d.doc_type,
                series=d.series[:60],
                status=d.status[:1],
                invoice_date=d.invoice_date,
                system_entry=timezone.make_aware(d.system_entry, tz),
                service_date=service_date(d.system_entry, cutoff_hour),
                net_total=_signed(d, d.net_total),
                gross_total=_signed(d, d.gross_total),
                source_id=d.source_id[:60],
            )
            for d in novos
        ],
        batch_size=_LOTE,
    )
    if criados and criados[0].pk is None:  # base de dados sem RETURNING
        pks = dict(SalesDocument.objects.filter(sales_import=importacao).values_list("number", "pk"))
        for c in criados:
            c.pk = pks[c.number]
    linhas = []
    for doc, d in zip(criados, novos):
        for l in d.lines:
            sinal = -1 if l.debit and not l.credit else 1
            linhas.append(
                SalesLine(
                    document=doc,
                    line_number=l.number,
                    product=produtos[l.product_code[:60]],
                    description=l.description[:200],
                    quantity=sinal * l.quantity,
                    unit=l.unit[:20],
                    unit_price=l.unit_price,
                    net_amount=l.net,
                    tax_rate=l.tax_rate,
                )
            )
    SalesLine.objects.bulk_create(linhas, batch_size=_LOTE)
    importacao.documents_new = len(criados)
    importacao.documents_updated = len(mudados)
    importacao.documents_unchanged = iguais
    importacao.save(update_fields=["documents_new", "documents_updated", "documents_unchanged", "updated_at"])


def _signed(documento, valor):
    """Uma nota de crédito abate às vendas: os totais ficam negativos."""
    return -valor if documento.doc_type == SalesDocument.Type.NC else valor


def _update_prices(produtos, documentos):
    """O último preço de cada produto é o da venda mais recente, se for mais
    recente do que o que já estava guardado."""
    tz = timezone.get_current_timezone()
    ultimos = {}
    for d in documentos:
        if d.doc_type not in SalesDocument.SALE_TYPES or d.status in SalesDocument.EXCLUDED_STATUSES:
            continue
        for l in d.lines:
            atual = ultimos.get(l.product_code)
            if atual is None or d.system_entry > atual[0]:
                ultimos[l.product_code] = (d.system_entry, l.unit_price)
    alterados = []
    for codigo, (quando, preco) in ultimos.items():
        produto = produtos[codigo[:60]]
        quando = timezone.make_aware(quando, tz)
        if produto.last_price_at is None or quando > produto.last_price_at:
            produto.last_price, produto.last_price_at = preco, quando
            alterados.append(produto)
    PosProduct.objects.bulk_update(alterados, ["last_price", "last_price_at"], batch_size=_LOTE)
