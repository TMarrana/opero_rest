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
        # add + incr: dois processos a falhar ao mesmo tempo nao se apagam um
        # ao outro (atomico onde a cache o e; a DatabaseCache faz o incr em
        # duas consultas, e pode contar uma falha a menos em concorrencia).
        if cache.add(k, 1, self.segundos):
            falhas = 1
        else:
            try:
                falhas = cache.incr(k)
            except ValueError:  # expirou entre o add e o incr
                cache.set(k, 1, self.segundos)
                falhas = 1
        cache.touch(k, self.segundos)  # cada falha renova o prazo
        return falhas

    def limpar(self, chave):
        cache.delete(self._chave(chave))
