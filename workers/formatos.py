"""Regras de escrita da ficha do trabalhador (Tarefa D5)."""
import re

# 9 algarismos começados por 2 (fixo) ou 9 (móvel), com ou sem o indicativo.
_TELEFONE_PT = re.compile(r"(?:\+351|00351)?([29]\d{8})")


def normalizar_contacto(texto):
    """Um telefone português fica «+351 965 852 489», escrito como for
    (965852489, +351965852489, 00351 965 852 489). Um email ou um número
    estrangeiro fica como foi escrito, sem espaços nas pontas."""
    texto = (texto or "").strip()
    numero = _TELEFONE_PT.fullmatch(re.sub(r"[\s.()-]", "", texto))
    if not numero:
        return texto
    n = numero.group(1)
    return f"+351 {n[:3]} {n[3:6]} {n[6:]}"
