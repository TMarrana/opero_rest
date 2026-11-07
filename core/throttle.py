"""
Limite de tentativas falhadas, guardado na cache: ao fim de `max_falhas`
falhas para a mesma chave, esta fica bloqueada durante `segundos`. Cada
falha renova o prazo. O `prefixo` separa os contadores de cada uso.
"""
from django.core.cache import cache


class Limite:
    def __init__(self, prefixo, max_falhas, segundos):
        self.prefixo = prefixo
        self.max_falhas = max_falhas
        self.segundos = segundos

    def _chave(self, chave):
        return f"{self.prefixo}:{chave}"

    def bloqueado(self, chave):
        return cache.get(self._chave(chave), 0) >= self.max_falhas

    def falhou(self, chave):
        k = self._chave(chave)
        falhas = cache.get(k, 0) + 1
        cache.set(k, falhas, self.segundos)
        return falhas

    def limpar(self, chave):
        cache.delete(self._chave(chave))
