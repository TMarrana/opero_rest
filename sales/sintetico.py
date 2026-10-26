"""
SAF-T (PT) 1.04_01 sintético, para os testes e para o comando `demo`.

Nunca se usa um ficheiro real de um cliente no repositório (Fase 10). Este
gerador produz um ficheiro pequeno com a mesma estrutura: cabeçalho,
produtos, um cliente, documentos de venda e, se pedido, consultas de mesa
e recibos, que a importação tem de ignorar.
"""
import datetime
import random
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from xml.sax.saxutils import escape

NS = "urn:OECD:StandardAuditFile-Tax:PT_1.04_01"
CENT = Decimal("0.01")

PRODUTOS_DEMO = [
    # código, descrição, família, preço sem IVA, taxa
    ("P001", "Bitoque", "Pratos", Decimal("8.94"), Decimal("13")),
    ("P002", "Prato do dia", "Pratos", Decimal("7.52"), Decimal("13")),
    ("P003", "Bacalhau à Brás", "Pratos", Decimal("10.62"), Decimal("13")),
    ("P004", "Francesinha", "Pratos", Decimal("10.18"), Decimal("13")),
    ("B001", "Imperial", "Bebidas", Decimal("1.46"), Decimal("23")),
    ("B002", "Água 0,5 l", "Bebidas", Decimal("1.06"), Decimal("13")),
    ("B003", "Vinho da casa, copo", "Bebidas", Decimal("2.03"), Decimal("23")),
    ("C001", "Café", "Cafetaria", Decimal("0.73"), Decimal("23")),
    ("S001", "Mousse de chocolate", "Sobremesas", Decimal("3.10"), Decimal("13")),
]


@dataclass
class Doc:
    numero: str
    hora: datetime.datetime
    linhas: list  # (código, descrição, quantidade, preço unitário sem IVA, taxa)
    tipo: str = "FS"
    estado: str = "N"
    operador: str = "OP1"
    cliente: tuple = ("Consumidor final", "999999990")
    extra: dict = field(default_factory=dict)

    def valores(self):
        linhas = []
        for codigo, descricao, qtd, preco, taxa in self.linhas:
            liquido = (Decimal(qtd) * Decimal(preco)).quantize(CENT, ROUND_HALF_UP)
            linhas.append((codigo, descricao, Decimal(qtd), Decimal(preco), Decimal(taxa), liquido))
        net = sum((l[5] for l in linhas), Decimal(0))
        imposto = sum(((l[5] * l[4] / 100).quantize(CENT, ROUND_HALF_UP) for l in linhas), Decimal(0))
        return linhas, net, net + imposto


def _linha_xml(n, l, nota_credito, data):
    codigo, descricao, qtd, preco, taxa, liquido = l
    montante = "DebitAmount" if nota_credito else "CreditAmount"
    return (
        f"<Line><LineNumber>{n}</LineNumber>"
        f"<ProductCode>{escape(codigo)}</ProductCode><ProductDescription>{escape(descricao)}</ProductDescription>"
        f"<Quantity>{qtd}</Quantity><UnitOfMeasure>UN</UnitOfMeasure><UnitPrice>{preco}</UnitPrice>"
        f"<TaxPointDate>{data}</TaxPointDate><Description>{escape(descricao)}</Description>"
        f"<{montante}>{liquido}</{montante}>"
        f"<Tax><TaxType>IVA</TaxType><TaxCountryRegion>PT</TaxCountryRegion><TaxCode>NOR</TaxCode>"
        f"<TaxPercentage>{taxa}</TaxPercentage></Tax><TaxExemptionReason/></Line>"
    )


def _documento_xml(d):
    linhas, net, gross = d.valores()
    data = d.hora.date().isoformat()
    nc = d.tipo == "NC"
    corpo = "".join(_linha_xml(i, l, nc, data) for i, l in enumerate(linhas, 1))
    return (
        f"<Invoice><InvoiceNo>{escape(d.numero)}</InvoiceNo><ATCUD>0</ATCUD>"
        f"<DocumentStatus><InvoiceStatus>{d.estado}</InvoiceStatus>"
        f"<InvoiceStatusDate>{d.hora.isoformat(timespec='seconds')}</InvoiceStatusDate>"
        f"<SourceID>{escape(d.operador)}</SourceID><SourceBilling>P</SourceBilling></DocumentStatus>"
        f"<Hash>0</Hash><HashControl>1</HashControl><Period>{d.hora.month}</Period>"
        f"<InvoiceDate>{data}</InvoiceDate><InvoiceType>{d.tipo}</InvoiceType>"
        f"<SpecialRegimes><SelfBillingIndicator>0</SelfBillingIndicator><CashVATSchemeIndicator>0</CashVATSchemeIndicator>"
        f"<ThirdPartiesBillingIndicator>0</ThirdPartiesBillingIndicator></SpecialRegimes>"
        f"<SourceID>{escape(d.operador)}</SourceID><SystemEntryDate>{d.hora.isoformat(timespec='seconds')}</SystemEntryDate>"
        f"<CustomerID>{escape(d.cliente[1])}</CustomerID>"
        f"<ShipTo><Address><AddressDetail>{escape(d.cliente[0])}, Rua do Cliente 1</AddressDetail>"
        f"<City>Lisboa</City><PostalCode>1000-001</PostalCode><Country>PT</Country></Address></ShipTo>"
        f"{corpo}"
        f"<DocumentTotals><TaxPayable>{gross - net}</TaxPayable><NetTotal>{net}</NetTotal>"
        f"<GrossTotal>{gross}</GrossTotal></DocumentTotals></Invoice>"
    )


def gerar(
    *,
    nif,
    documentos,
    inicio,
    fim,
    produtos=None,
    versao="1.04_01",
    consultas_de_mesa=True,
    recibos=True,
    totais_de_controlo=True,
    cabecalho_extra="",
    prologo="",
):
    """O ficheiro como bytes UTF-8. `documentos` é uma lista de Doc."""
    produtos = produtos if produtos is not None else PRODUTOS_DEMO
    debito = credito = Decimal(0)
    for d in documentos:
        if d.estado == "A":
            continue
        linhas, _, _ = d.valores()
        total = sum((l[5] for l in linhas), Decimal(0))
        if d.tipo == "NC":
            debito += total
        else:
            credito += total
    clientes = {d.cliente for d in documentos} or {("Consumidor final", "999999990")}
    partes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        prologo,
        f'<AuditFile xmlns="{NS}">',
        f"<Header><AuditFileVersion>{versao}</AuditFileVersion><CompanyID>{nif}</CompanyID>"
        f"<TaxRegistrationNumber>{nif}</TaxRegistrationNumber><TaxAccountingBasis>F</TaxAccountingBasis>"
        f"<CompanyName>Tasca Lda</CompanyName><FiscalYear>{inicio.year}</FiscalYear>"
        f"<StartDate>{inicio.isoformat()}</StartDate><EndDate>{fim.isoformat()}</EndDate>"
        f"<CurrencyCode>EUR</CurrencyCode><DateCreated>{fim.isoformat()}</DateCreated>"
        f"<TaxEntity>Global</TaxEntity><ProductCompanyTaxID>500000000</ProductCompanyTaxID>"
        f"<SoftwareCertificateNumber>9999</SoftwareCertificateNumber><ProductID>POS de Teste/Fornecedor</ProductID>"
        f"<ProductVersion>1.0</ProductVersion>{cabecalho_extra}</Header>",
        "<MasterFiles>",
    ]
    for nome, nif_cliente in sorted(clientes):
        partes.append(
            f"<Customer><CustomerID>{escape(nif_cliente)}</CustomerID><AccountID>Desconhecido</AccountID>"
            f"<CustomerTaxID>{escape(nif_cliente)}</CustomerTaxID><CompanyName>{escape(nome)}</CompanyName>"
            f"<BillingAddress><AddressDetail>Rua do Cliente 1</AddressDetail><City>Lisboa</City>"
            f"<PostalCode>1000-001</PostalCode><Country>PT</Country></BillingAddress>"
            f"<Email>cliente@exemplo.pt</Email><SelfBillingIndicator>0</SelfBillingIndicator></Customer>"
        )
    for codigo, descricao, familia, _, _ in produtos:
        partes.append(
            f"<Product><ProductType>P</ProductType><ProductCode>{escape(codigo)}</ProductCode>"
            f"<ProductGroup>{escape(familia)}</ProductGroup><ProductDescription>{escape(descricao)}</ProductDescription>"
            f"<ProductNumberCode>{escape(codigo)}</ProductNumberCode></Product>"
        )
    partes.append("</MasterFiles><SourceDocuments><SalesInvoices>")
    partes.append(f"<NumberOfEntries>{len(documentos)}</NumberOfEntries>")
    if totais_de_controlo:
        partes.append(f"<TotalDebit>{debito}</TotalDebit><TotalCredit>{credito}</TotalCredit>")
    partes.extend(_documento_xml(d) for d in documentos)
    partes.append("</SalesInvoices>")
    if consultas_de_mesa:
        partes.append(
            "<WorkingDocuments><NumberOfEntries>1</NumberOfEntries><TotalDebit>0</TotalDebit>"
            "<TotalCredit>100.00</TotalCredit><WorkDocument><DocumentNumber>CM M/1</DocumentNumber>"
            f"<DocumentStatus><WorkStatus>F</WorkStatus><WorkStatusDate>{inicio}T12:00:00</WorkStatusDate>"
            "<SourceID>OP1</SourceID><SourceBilling>P</SourceBilling></DocumentStatus>"
            f"<WorkDate>{inicio}</WorkDate><WorkType>CM</WorkType><SourceID>OP1</SourceID>"
            f"<SystemEntryDate>{inicio}T12:00:00</SystemEntryDate><CustomerID>999999990</CustomerID>"
            "<Line><LineNumber>1</LineNumber><ProductCode>P001</ProductCode><ProductDescription>Bitoque</ProductDescription>"
            "<Quantity>10</Quantity><UnitOfMeasure>UN</UnitOfMeasure><UnitPrice>10.00</UnitPrice>"
            f"<TaxPointDate>{inicio}</TaxPointDate><Description>Bitoque</Description><CreditAmount>100.00</CreditAmount>"
            "<Tax><TaxType>IVA</TaxType><TaxCountryRegion>PT</TaxCountryRegion><TaxCode>NOR</TaxCode>"
            "<TaxPercentage>13</TaxPercentage></Tax></Line>"
            "<DocumentTotals><TaxPayable>13.00</TaxPayable><NetTotal>100.00</NetTotal><GrossTotal>113.00</GrossTotal>"
            "</DocumentTotals></WorkDocument></WorkingDocuments>"
        )
    if recibos:
        partes.append(
            "<Payments><NumberOfEntries>1</NumberOfEntries><TotalDebit>0</TotalDebit><TotalCredit>50.00</TotalCredit>"
            f"<Payment><PaymentRefNo>RG R/1</PaymentRefNo><TransactionDate>{inicio}</TransactionDate>"
            "<PaymentType>RG</PaymentType><DocumentStatus><PaymentStatus>N</PaymentStatus>"
            f"<PaymentStatusDate>{inicio}T12:00:00</PaymentStatusDate><SourceID>OP1</SourceID>"
            "<SourcePayment>P</SourcePayment></DocumentStatus><SourceID>OP1</SourceID>"
            f"<SystemEntryDate>{inicio}T12:00:00</SystemEntryDate><CustomerID>999999990</CustomerID>"
            "<Line><LineNumber>1</LineNumber><CreditAmount>50.00</CreditAmount></Line>"
            "<DocumentTotals><TaxPayable>0</TaxPayable><NetTotal>50.00</NetTotal><GrossTotal>50.00</GrossTotal>"
            "</DocumentTotals></Payment></Payments>"
        )
    partes.append("</SourceDocuments></AuditFile>")
    return "".join(partes).encode("utf-8")


def mes_de_demonstracao(*, inicio, fim, serie="2026A", semente=1):
    """Os documentos de um período de vendas inventado: almoços e jantares
    todos os dias, alguns depois da meia-noite, mais ao fim de semana, uma
    fatura anulada e uma nota de crédito."""
    aleatorio = random.Random(semente)
    docs, n = [], 0
    dia = inicio
    while dia <= fim:
        fim_de_semana = dia.weekday() >= 4
        for inicio_servico, fim_servico, clientes in ((12, 15, 28), (19, 24, 34)):
            clientes = int(clientes * (1.4 if fim_de_semana else 1) * aleatorio.uniform(0.8, 1.2))
            for _ in range(clientes):
                minuto = aleatorio.randrange((fim_servico - inicio_servico) * 60 + (75 if fim_servico == 24 else 0))
                hora = datetime.datetime.combine(dia, datetime.time(inicio_servico)) + datetime.timedelta(minutes=minuto)
                prato = aleatorio.choice(PRODUTOS_DEMO[:4])
                linhas = [(prato[0], prato[1], aleatorio.choice((1, 1, 2)), prato[3], prato[4])]
                for bebida in aleatorio.sample(PRODUTOS_DEMO[4:], aleatorio.randrange(1, 4)):
                    linhas.append((bebida[0], bebida[1], aleatorio.choice((1, 1, 2, 3)), bebida[3], bebida[4]))
                n += 1
                docs.append(Doc(numero=f"FS {serie}/{n}", hora=hora, linhas=linhas, operador=f"OP{aleatorio.randrange(1, 4)}"))
        dia += datetime.timedelta(days=1)
    docs.sort(key=lambda d: d.hora)
    for i, d in enumerate(docs, 1):
        d.numero = f"FS {serie}/{i}"
    if len(docs) > 10:
        docs[5].estado = "A"
        original = docs[10]
        docs.append(
            Doc(
                numero=f"NC {serie}/1",
                tipo="NC",
                hora=original.hora + datetime.timedelta(minutes=20),
                linhas=[original.linhas[0][:2] + (1,) + original.linhas[0][3:]],
            )
        )
    return docs
