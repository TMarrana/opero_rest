import re

from django.core.exceptions import ValidationError

# Endereços que não podem ser de um grupo: ficam para o site e para a
# plataforma.
RESERVED_SUBDOMAINS = {"app", "www", "admin", "api", "static", "media", "mail", "email", "ftp", "suporte"}
_SUBDOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$")


def validate_nif(valor):
    """NIF português: nove algarismos com dígito de controlo (módulo 11).
    Vazio é aceite; a casa pode ainda não o ter preenchido."""
    if not valor:
        return
    if len(valor) != 9 or not valor.isdigit():
        raise ValidationError("O NIF tem nove algarismos.")
    soma = sum(int(d) * (9 - i) for i, d in enumerate(valor[:8]))
    controlo = 11 - soma % 11
    if controlo >= 10:
        controlo = 0
    if controlo != int(valor[8]):
        raise ValidationError("Este NIF não é válido. Confirme os algarismos.")


def validate_subdomain(valor):
    """O endereço de um grupo: a parte antes do domínio, como em
    tasca.opero.pt."""
    if not _SUBDOMAIN.match(valor or ""):
        raise ValidationError(
            "Use só letras minúsculas sem acentos, números e hífenes, sem hífen no início nem no fim."
        )
    if valor in RESERVED_SUBDOMAINS:
        raise ValidationError("Este endereço está reservado. Escolha outro.")
