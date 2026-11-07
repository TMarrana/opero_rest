"""
Quem pode abrir cada secção do backoffice (matriz da secção 7 do plano).

É a única fonte: os mixins de `core.mixins` leem daqui os perfis de cada
view e o processador de contexto (`core.context_processors`) leva para o
menu as secções que o perfil ativo consegue abrir. Assim o menu nunca
mostra uma ligação que dá 403.

Importa `accounts.models`, por isso não se importa de nenhum `models.py`.
"""
from accounts.models import User

Role = User.Role

ADMIN = frozenset({Role.ADMIN})
PESSOAS = frozenset({Role.ADMIN, Role.MANAGER})
STOCK = frozenset({Role.ADMIN, Role.MANAGER, Role.STOCK})

SECOES: dict[str, frozenset] = {
    "dashboard": STOCK,
    "trabalhadores": PESSOAS,
    "ponto": PESSOAS,
    "ferias": PESSOAS,
    "turnos": PESSOAS,
    "stock": STOCK,
    "compras": STOCK,
    "fichas": STOCK,
    "vendas": PESSOAS,
    "analise": STOCK,
    "dispositivo": PESSOAS,
    "configuracao": ADMIN,
}


def secoes_visiveis(role: str | None) -> frozenset[str]:
    """As secções que este perfil abre; vazio sem perfil ou com perfil desconhecido."""
    if not role:
        return frozenset()
    return frozenset(secao for secao, perfis in SECOES.items() if role in perfis)
