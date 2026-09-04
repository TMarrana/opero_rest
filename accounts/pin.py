"""
Throttling do login por PIN (secção 7 do plano): após MAX_FALHAS
tentativas falhadas para o mesmo trabalhador no mesmo dispositivo, o
login fica bloqueado durante BLOQUEIO_SEGUNDOS.
"""
from django.core.cache import cache

MAX_FALHAS = 5
BLOQUEIO_SEGUNDOS = 60


def _chave(session_key, worker_id):
    return f"pin-falhas:{session_key}:{worker_id}"


def esta_bloqueado(session_key, worker_id):
    return cache.get(_chave(session_key, worker_id), 0) >= MAX_FALHAS


def registar_falha(session_key, worker_id):
    chave = _chave(session_key, worker_id)
    falhas = cache.get(chave, 0) + 1
    cache.set(chave, falhas, BLOQUEIO_SEGUNDOS)
    return falhas


def limpar_falhas(session_key, worker_id):
    cache.delete(_chave(session_key, worker_id))
