"""
Leitura do ficheiro SAF-T (PT) 1.04_01 de faturação (Fase 10).

O ficheiro vem de outro programa e um mês pode ter dezenas de MB, por isso
lê-se em streaming (`iterparse`) com o `defusedxml`, que recusa DTDs e
entidades. Cada documento é lido e largado logo a seguir.

Só se leem o cabeçalho, os produtos e os documentos de `SalesInvoices`.
Os clientes (`MasterFiles/Customer`) e os dados do cliente nos documentos
nunca se leem: não há onde os guardar. `WorkingDocuments` (consultas de
mesa) e `Payments` saltam-se, para a mesma venda não contar duas vezes.

Este módulo não toca na base de dados: devolve o que leu, e
`sales.services.import_saft` decide o que grava.
"""
import datetime
import hashlib
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import iterparse

# Um mês de um restaurante tem poucos MB; isto trava um .zip que se
# expande para o disco inteiro.
MAX_XML_BYTES = 300 * 1024 * 1024

DOC_TYPES = {"FT", "FS", "FR", "NC", "ND"}


class SaftError(Exception):
    """O ficheiro não se pode importar. A mensagem é para o gerente."""


@dataclass
class Header:
    version: str
    tax_id: str
    start: datetime.date
    end: datetime.date
    product_id: str
    certificate_number: str


@dataclass
class Product:
    code: str
    description: str
    group: str


@dataclass
class Line:
    number: int
    product_code: str
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    credit: Decimal
    debit: Decimal
    tax_rate: Decimal | None

    @property
    def net(self):
        return self.credit - self.debit


@dataclass
class Document:
    number: str
    doc_type: str
    status: str
    invoice_date: datetime.date
    system_entry: datetime.datetime  # hora local, sem fuso, como vem no ficheiro
    source_id: str
    net_total: Decimal
    gross_total: Decimal
    lines: list = field(default_factory=list)

    @property
    def series(self):
        """Em «FS 2026A/123», a série é «2026A»."""
        resto = self.number.split(" ", 1)[-1]
        return resto.rsplit("/", 1)[0] if "/" in resto else ""


@dataclass
class Saft:
    header: Header
    products: dict  # código → Product
    documents: list
    other_types: int  # documentos de tipos que não são de venda (antigos, p. ex. VD)
    has_sales_invoices: bool
    control_debit: Decimal | None
    control_credit: Decimal | None
    file_hash: str


class _HashingReader:
    """Calcula o hash do XML à medida que o parser o lê, e trava ficheiros
    maiores do que o limite."""

    def __init__(self, raw):
        self.raw = raw
        self.hash = hashlib.sha256()
        self.size = 0

    def read(self, n=-1):
        data = self.raw.read(n)
        self.size += len(data)
        if self.size > MAX_XML_BYTES:
            raise SaftError("O ficheiro é demasiado grande. Exporte um período mais curto, por exemplo um mês.")
        self.hash.update(data)
        return data


def open_upload(f):
    """O XML de um ficheiro carregado, que pode vir dentro de um .zip."""
    f.seek(0)
    inicio = f.read(4)
    f.seek(0)
    if not inicio.startswith(b"PK"):
        return f
    try:
        arquivo = zipfile.ZipFile(f)
    except zipfile.BadZipFile:
        raise SaftError("O .zip está danificado. Exporte o ficheiro outra vez.")
    xmls = [i for i in arquivo.infolist() if not i.is_dir() and i.filename.lower().endswith(".xml")]
    if len(xmls) != 1:
        raise SaftError("O .zip tem de ter um só ficheiro XML, o SAF-T.")
    if xmls[0].file_size > MAX_XML_BYTES:
        raise SaftError("O ficheiro é demasiado grande. Exporte um período mais curto, por exemplo um mês.")
    return arquivo.open(xmls[0])


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _find(elem, path):
    """O elemento no caminho dado, ignorando o namespace (muda de versão
    para versão do SAF-T)."""
    for nome in path.split("/"):
        elem = next((c for c in elem if _local(c.tag) == nome), None)
        if elem is None:
            return None
    return elem


def _text(elem, path, default=""):
    alvo = _find(elem, path)
    if alvo is None or alvo.text is None:
        return default
    return alvo.text.strip()


def _decimal(elem, path, default=None):
    valor = _text(elem, path)
    if not valor:
        if default is not None:
            return default
        raise SaftError(f"Falta o campo {path} num documento.")
    try:
        return Decimal(valor)
    except InvalidOperation:
        raise SaftError(f"O campo {path} tem um valor que não é um número: {valor}.")


def _date(valor, campo):
    try:
        return datetime.date.fromisoformat(valor)
    except ValueError:
        raise SaftError(f"O campo {campo} tem uma data inválida: {valor or 'vazio'}.")


def _header(elem):
    return Header(
        version=_text(elem, "AuditFileVersion"),
        tax_id="".join(c for c in _text(elem, "TaxRegistrationNumber") if c.isdigit()),
        start=_date(_text(elem, "StartDate"), "StartDate"),
        end=_date(_text(elem, "EndDate"), "EndDate"),
        product_id=_text(elem, "ProductID"),
        certificate_number=_text(elem, "SoftwareCertificateNumber"),
    )


def _line(elem):
    taxa = _text(elem, "Tax/TaxPercentage")
    return Line(
        number=int(_text(elem, "LineNumber", "0") or 0),
        product_code=_text(elem, "ProductCode"),
        description=_text(elem, "ProductDescription") or _text(elem, "Description"),
        quantity=_decimal(elem, "Quantity", Decimal(0)),
        unit=_text(elem, "UnitOfMeasure"),
        unit_price=_decimal(elem, "UnitPrice", Decimal(0)),
        credit=_decimal(elem, "CreditAmount", Decimal(0)),
        debit=_decimal(elem, "DebitAmount", Decimal(0)),
        tax_rate=Decimal(taxa) if taxa else None,
    )


def _document(elem):
    numero = _text(elem, "InvoiceNo")
    entrada = _text(elem, "SystemEntryDate")
    try:
        hora = datetime.datetime.fromisoformat(entrada)
    except ValueError:
        raise SaftError(f"O documento {numero} tem uma hora inválida: {entrada or 'vazia'}.")
    return Document(
        number=numero,
        doc_type=_text(elem, "InvoiceType"),
        status=_text(elem, "DocumentStatus/InvoiceStatus"),
        invoice_date=_date(_text(elem, "InvoiceDate"), "InvoiceDate"),
        system_entry=hora.replace(tzinfo=None),
        source_id=_text(elem, "SourceID"),
        net_total=_decimal(elem, "DocumentTotals/NetTotal"),
        gross_total=_decimal(elem, "DocumentTotals/GrossTotal"),
        lines=[_line(c) for c in elem if _local(c.tag) == "Line"],
    )


# Registos que se largam sem ler, para não ocuparem memória.
_SKIP = {"Customer", "Supplier", "TaxTableEntry", "Account", "Journal", "WorkDocument", "Payment", "StockMovement"}


def parse(raw, on_header=None):
    """Lê o SAF-T de `raw` (um ficheiro binário). `on_header` recebe o
    cabeçalho logo que é lido e pode recusar o ficheiro com SaftError,
    antes de se ler o resto."""
    leitor = _HashingReader(raw)
    header, products, documents = None, {}, []
    other_types, has_sales = 0, False
    control = {}
    pilha = []
    try:
        for evento, elem in iterparse(leitor, events=("start", "end"), forbid_dtd=True):
            nome = _local(elem.tag)
            if evento == "start":
                pilha.append(nome)
                if nome == "SalesInvoices":
                    has_sales = True
                continue
            pai = pilha[-2] if len(pilha) > 1 else None
            if nome == "Header" and pai == "AuditFile":
                header = _header(elem)
                if on_header:
                    on_header(header)
                elem.clear()
            elif nome == "Product" and pai == "MasterFiles":
                codigo = _text(elem, "ProductCode")
                products[codigo] = Product(codigo, _text(elem, "ProductDescription"), _text(elem, "ProductGroup"))
                elem.clear()
            elif nome == "Invoice" and pai == "SalesInvoices":
                if _text(elem, "InvoiceType") in DOC_TYPES:
                    documents.append(_document(elem))
                else:
                    other_types += 1
                elem.clear()
            elif nome in ("TotalDebit", "TotalCredit") and pai == "SalesInvoices":
                control[nome] = Decimal(elem.text.strip()) if elem.text else None
            elif nome in _SKIP:
                elem.clear()
            pilha.pop()
    except DefusedXmlException:
        raise SaftError("O ficheiro traz declarações (DTD ou entidades) que um SAF-T não tem. Não foi lido.")
    except ParseError as exc:
        raise SaftError(f"O ficheiro não é um XML válido ({exc}). Confirme que é o SAF-T exportado pelo POS.")
    if header is None:
        raise SaftError("O ficheiro não tem o cabeçalho do SAF-T. Confirme que é o SAF-T exportado pelo POS.")
    return Saft(
        header=header,
        products=products,
        documents=documents,
        other_types=other_types,
        has_sales_invoices=has_sales,
        control_debit=control.get("TotalDebit"),
        control_credit=control.get("TotalCredit"),
        file_hash=leitor.hash.hexdigest(),
    )
