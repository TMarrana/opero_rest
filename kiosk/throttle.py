"""
Bloqueio do código de ponto (secção 7 do plano): ao fim de MAX_FALHAS
tentativas falhadas para o mesmo trabalhador, o código dele fica
bloqueado durante BLOQUEIO_SEGUNDOS. A chave é só o trabalhador, porque o
quiosque não tem sessão e uma instância serve um restaurante.
"""
from core.throttle import Limite

MAX_FALHAS = 5
BLOQUEIO_SEGUNDOS = 60

_limite = Limite("codigo-falhas", MAX_FALHAS, BLOQUEIO_SEGUNDOS)


def esta_bloqueado(worker_id):
    return _limite.bloqueado(worker_id)


def registar_falha(worker_id):
    return _limite.falhou(worker_id)


def limpar_falhas(worker_id):
    _limite.limpar(worker_id)
