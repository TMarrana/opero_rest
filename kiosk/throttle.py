"""
Bloqueio do código de ponto (secção 7 do plano): ao fim de MAX_FALHAS
tentativas falhadas para o mesmo trabalhador, o código dele fica
bloqueado durante BLOQUEIO_SEGUNDOS. A chave é só o trabalhador, porque o
quiosque não tem sessão e uma instância serve um restaurante.
"""
from django.core.cache import cache

MAX_FALHAS = 5
BLOQUEIO_SEGUNDOS = 60


def _chave(worker_id):
    return f"codigo-falhas:{worker_id}"


def esta_bloqueado(worker_id):
    return cache.get(_chave(worker_id), 0) >= MAX_FALHAS


def registar_falha(worker_id):
    chave = _chave(worker_id)
    falhas = cache.get(chave, 0) + 1
    cache.set(chave, falhas, BLOQUEIO_SEGUNDOS)
    return falhas


def limpar_falhas(worker_id):
    cache.delete(_chave(worker_id))
