from django.core.exceptions import ValidationError


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
