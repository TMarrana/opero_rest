"""
Regras das compras (Fase 11). As views só chamam estas funções; é aqui que
se valida e que se mexe no stock, sempre pelo `register_movement()`.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from inventory.models import Item, StockMovement
from inventory.services import register_movement

from .models import PurchaseOrder, PurchaseOrderLine, Receipt, ReceiptLine, SupplierItem

CENT = Decimal("0.01")
# Unidades no texto da encomenda: «3 kg», e não «3 quilograma».
UNIDADES_CURTAS = {"UN": "un.", "KG": "kg", "L": "l", "CX": "cx.", "EMB": "emb."}


def parse_decimal(texto, campo="O valor"):
    """Um número escrito à portuguesa (vírgula decimal) ou com ponto. Vazio
    dá None."""
    texto = (texto or "").strip().replace(" ", "").replace(",", ".")
    if not texto:
        return None
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        raise ValidationError(f"{campo} «{texto}» não é um número.")
    if valor < 0:
        raise ValidationError(f"{campo} não pode ser negativo.")
    return valor


def pending_by_item(restaurant):
    """{artigo: quantidade encomendada que ainda não chegou}, nas encomendas
    em aberto da casa."""
    pendente = defaultdict(Decimal)
    linhas = PurchaseOrderLine.objects.filter(
        order__restaurant=restaurant, order__state__in=PurchaseOrder.OPEN_STATES
    ).annotate(recebido=Sum("receipt_lines__quantity"))
    for l in linhas:
        pendente[l.item_id] += max(l.quantity - (l.recebido or Decimal(0)), Decimal(0))
    return pendente


def shopping_list(restaurant):
    """Os artigos ativos no mínimo ou abaixo dele, agrupados pelo fornecedor
    preferido. A quantidade sugerida repõe o mínimo, descontando o que já
    está encomendado e ainda não chegou.

    Devolve [(fornecedor ou None, [linha, ...]), ...], com os artigos sem
    fornecedor preferido no fim."""
    itens = (
        Item.objects.filter(restaurant=restaurant, is_active=True, current_stock__lte=F("minimum_stock"))
        .select_related("category")
        .order_by("name")
    )
    preferidos = {
        si.item_id: si
        for si in SupplierItem.objects.filter(item__in=itens, preferred=True, supplier__is_active=True).select_related(
            "supplier"
        )
    }
    pendente = pending_by_item(restaurant)
    grupos = defaultdict(list)
    for item in itens:
        si = preferidos.get(item.pk)
        ja = pendente.get(item.pk, Decimal(0))
        sugerido = max(item.minimum_stock - item.current_stock - ja, Decimal(0))
        grupos[si.supplier if si else None].append(
            {"item": item, "encomendado": ja, "sugerido": sugerido, "preco": si.last_price if si else None, "ref": si.supplier_ref if si else ""}
        )
    ordem = sorted((s for s in grupos if s is not None), key=lambda s: s.name)
    return [(s, grupos[s]) for s in ordem] + ([(None, grupos[None])] if None in grupos else [])


def save_supplier_item(*, supplier, item, supplier_ref="", last_price=None, preferred=False):
    """Liga um artigo da casa a um fornecedor. Só há um fornecedor preferido
    por artigo: marcar este tira a marca ao anterior."""
    with transaction.atomic():
        if preferred:
            SupplierItem.objects.filter(item=item, preferred=True).exclude(supplier=supplier).update(preferred=False)
        atual = SupplierItem.objects.filter(supplier=supplier, item=item).first()
        dados = {"supplier_ref": supplier_ref, "preferred": preferred, "last_price": last_price}
        if last_price is not None and (atual is None or atual.last_price != last_price):
            dados["last_price_at"] = timezone.localdate()
        return SupplierItem.objects.update_or_create(supplier=supplier, item=item, defaults=dados)[0]


def _check_supplier(restaurant, supplier):
    if supplier.organization_id != restaurant.organization_id:
        raise ValidationError("Este fornecedor não é do grupo desta casa.")
    if not supplier.is_active:
        raise ValidationError(f"{supplier} está arquivado. Reative-o antes de lhe fazer uma encomenda.")


def _check_item(restaurant, item):
    if item.restaurant_id != restaurant.pk:
        raise ValidationError(f"{item} não é um artigo desta casa.")


def create_order(*, restaurant, supplier, lines, user, notes="", expected_date=None):
    """Cria uma encomenda em rascunho. `lines` é uma lista de (artigo,
    quantidade, preço ou None); as quantidades a zero ficam de fora."""
    _check_supplier(restaurant, supplier)
    precos = {si.item_id: si.last_price for si in SupplierItem.objects.filter(supplier=supplier)}
    vistas, validas = set(), []
    for item, quantidade, preco in lines:
        _check_item(restaurant, item)
        if not quantidade:
            continue
        if item.pk in vistas:
            raise ValidationError(f"{item} aparece duas vezes. Junte as quantidades numa só linha.")
        vistas.add(item.pk)
        validas.append((item, quantidade, preco if preco is not None else precos.get(item.pk)))
    with transaction.atomic():
        encomenda = PurchaseOrder.objects.create(
            restaurant=restaurant, supplier=supplier, created_by=user, notes=notes, expected_date=expected_date
        )
        PurchaseOrderLine.objects.bulk_create(
            PurchaseOrderLine(order=encomenda, item=i, quantity=q, unit_price=p) for i, q, p in validas
        )
    return encomenda


def _locked(order, *estados):
    locked = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if locked.state not in estados:
        raise ValidationError(f"A encomenda {locked.reference} está {locked.get_state_display().lower()}.")
    return locked


def update_draft(*, order, lines, notes=None, expected_date=None):
    """Muda as linhas de um rascunho: {artigo: (quantidade, preço)}. Uma
    quantidade a zero tira a linha."""
    with transaction.atomic():
        encomenda = _locked(order, PurchaseOrder.State.RASCUNHO)
        for item, (quantidade, preco) in lines.items():
            _check_item(encomenda.restaurant, item)
            if not quantidade:
                encomenda.lines.filter(item=item).delete()
            else:
                PurchaseOrderLine.objects.update_or_create(
                    order=encomenda, item=item, defaults={"quantity": quantidade, "unit_price": preco}
                )
        if notes is not None:
            encomenda.notes = notes
        encomenda.expected_date = expected_date
        encomenda.save(update_fields=["notes", "expected_date", "updated_at"])
    return encomenda


def send_order(*, order, user):
    """Marca o rascunho como enviado. O envio em si (email, WhatsApp) faz-o
    o utilizador, com o texto da encomenda, até haver envio de emails."""
    with transaction.atomic():
        encomenda = _locked(order, PurchaseOrder.State.RASCUNHO)
        if not encomenda.lines.exists():
            raise ValidationError("A encomenda não tem linhas. Acrescente pelo menos um artigo.")
        encomenda.state = PurchaseOrder.State.ENVIADA
        encomenda.sent_at, encomenda.sent_by = timezone.now(), user
        encomenda.save(update_fields=["state", "sent_at", "sent_by", "updated_at"])
    return encomenda


def cancel_order(*, order, user):
    """Cancela uma encomenda que ainda não recebeu nada. Uma recebida em
    parte fica como está: o que chegou entrou no stock."""
    with transaction.atomic():
        encomenda = _locked(order, PurchaseOrder.State.RASCUNHO, PurchaseOrder.State.ENVIADA)
        encomenda.state = PurchaseOrder.State.CANCELADA
        encomenda.cancelled_at, encomenda.cancelled_by = timezone.now(), user
        encomenda.save(update_fields=["state", "cancelled_at", "cancelled_by", "updated_at"])
    return encomenda


def order_text(order):
    """A encomenda em texto, para copiar para um email ou uma mensagem."""
    casa = order.restaurant
    linhas = [f"Encomenda {order.reference} · {casa}"]
    if casa.address:
        linhas.append(f"Entregar em: {casa.address}")
    if order.expected_date:
        linhas.append(f"Entrega pretendida: {order.expected_date:%d/%m/%Y}")
    linhas.append("")
    refs = {si.item_id: si.supplier_ref for si in SupplierItem.objects.filter(supplier=order.supplier)}
    for l in order.lines.select_related("item"):
        ref = f" (ref. {refs[l.item_id]})" if refs.get(l.item_id) else ""
        linhas.append(f"- {_qtd(l.quantity)} {UNIDADES_CURTAS.get(l.item.unit, l.item.unit)} · {l.item.name}{ref}")
    if order.notes:
        linhas += ["", order.notes]
    linhas += ["", "Obrigado."]
    return "\n".join(linhas)


def _qtd(valor):
    valor = Decimal(valor)
    texto = str(valor.quantize(Decimal(1)) if valor == valor.to_integral_value() else valor.normalize())
    return texto.replace(".", ",")


def receive(*, restaurant, supplier, lines, user, document_number, document_date, order=None, notes=""):
    """Regista uma receção. `lines` é uma lista de (artigo, quantidade,
    preço ou None, linha da encomenda ou None). Cada linha recebida é uma
    ENTRADA de origem compra, com a referência da encomenda; o preço passa
    a ser o custo de referência do artigo e o último preço do fornecedor.
    Tudo na mesma transação: ou entra a receção inteira, ou nada."""
    _check_supplier_for_receipt(restaurant, supplier)
    if not (document_number or "").strip():
        raise ValidationError("Indique o número da fatura ou da guia que veio com a mercadoria.")
    if document_date is None:
        raise ValidationError("Indique a data da fatura ou da guia.")
    if document_date > timezone.localdate():
        raise ValidationError("A data da fatura ou da guia não pode ser no futuro.")
    validas = []
    for item, quantidade, preco, linha in lines:
        _check_item(restaurant, item)
        if linha is not None and (order is None or linha.order_id != order.pk or linha.item_id != item.pk):
            raise ValidationError(f"A linha de {item} não é desta encomenda.")
        if quantidade:
            validas.append((item, quantidade, preco, linha))
    if not validas:
        raise ValidationError("Não há nada recebido. Indique a quantidade que chegou em pelo menos uma linha.")

    with transaction.atomic():
        if order is not None:
            order = _locked(order, PurchaseOrder.State.ENVIADA, PurchaseOrder.State.PARCIAL)
            if order.supplier_id != supplier.pk:
                raise ValidationError("A encomenda é de outro fornecedor.")
        agora = timezone.now()
        rececao = Receipt.objects.create(
            restaurant=restaurant,
            supplier=supplier,
            order=order,
            document_number=document_number.strip(),
            document_date=document_date,
            received_at=agora,
            received_by=user,
            notes=notes,
        )
        referencia = (order.reference if order else rececao.reference) + f" · {rececao.document_number}"
        for item, quantidade, preco, linha in validas:
            movimento = register_movement(
                item=item,
                movement_type=StockMovement.Type.ENTRADA,
                quantity=quantidade,
                user=user,
                occurred_at=agora,
                reason=f"Receção de {supplier}",
                reference=referencia[:80],
                origin=StockMovement.Origin.COMPRA,
            )
            ReceiptLine.objects.create(
                receipt=rececao, item=item, order_line=linha, quantity=quantidade, unit_price=preco, movement=movimento
            )
            if preco is not None:
                # Só o custo: o stock já mudou pelo movimento (invariante 1).
                Item.objects.filter(pk=item.pk).update(reference_cost=preco.quantize(CENT), updated_at=agora)
            SupplierItem.objects.update_or_create(
                supplier=supplier,
                item=item,
                defaults={"last_price": preco, "last_price_at": document_date} if preco is not None else {},
            )
        if order is not None:
            _update_order_state(order)
    return rececao


def _check_supplier_for_receipt(restaurant, supplier):
    # Um fornecedor arquivado ainda pode entregar o que já estava encomendado.
    if supplier.organization_id != restaurant.organization_id:
        raise ValidationError("Este fornecedor não é do grupo desta casa.")


def _update_order_state(order):
    linhas = list(order.lines.annotate(recebido=Sum("receipt_lines__quantity")))
    completa = all((l.recebido or 0) >= l.quantity for l in linhas)
    order.state = PurchaseOrder.State.RECEBIDA if completa else PurchaseOrder.State.PARCIAL
    order.save(update_fields=["state", "updated_at"])


def month_receipts(restaurant, month):
    """Linhas recebidas no mês (pela data da fatura ou guia)."""
    from attendance.month import month_range

    inicio, fim = month_range(month)
    return (
        ReceiptLine.objects.filter(receipt__restaurant=restaurant, receipt__document_date__range=(inicio, fim))
        .select_related("receipt__supplier", "receipt__order", "item")
        .order_by("receipt__document_date", "receipt_id", "item__name")
    )


def by_supplier(lines):
    """[(fornecedor, receções, total)] a partir das linhas de um mês."""
    totais = {}
    for l in lines:
        s = l.receipt.supplier
        t = totais.setdefault(s, {"rececoes": set(), "total": Decimal(0), "sem_preco": 0})
        t["rececoes"].add(l.receipt_id)
        if l.unit_price is None:
            t["sem_preco"] += 1
        else:
            t["total"] += l.total()
    return sorted(
        ((s, len(t["rececoes"]), t["total"], t["sem_preco"]) for s, t in totais.items()), key=lambda r: -r[2]
    )

