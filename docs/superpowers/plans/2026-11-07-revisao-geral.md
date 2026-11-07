# Revisão geral do Opero Rest — plano de ação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir os erros de lógica, de permissões e de aspeto encontrados na revisão de 2026-11-07, preparar a produção para o piloto da Peco e ordenar as melhorias de produto para depois do piloto.

**Architecture:** A arquitetura fica como está: um monólito Django com três superfícies (quiosque, app do colaborador e backoffice), HTMX e Alpine. As correções entram nos serviços e seletores de cada app. Há duas peças novas e partilhadas: o mapa de permissões em `core/permissions.py` e a formatação de números em `core/formatos.py`.

**Tech Stack:** Python 3.12, Django 5.2 LTS, HTMX, Alpine.js, Tailwind CSS standalone v3.4.17, SQLite em desenvolvimento, PostgreSQL em produção, pytest-django.

**Spec:** a secção «Diagnóstico» deste documento é a especificação desta revisão. As regras de produto continuam no `plan.md` (secções 4, 6, 7, 9 e 12) e o trabalho que não é código está no `todo.md`.

## Global Constraints

- `Django>=5.2,<6.0` e Python 3.12. Sem npm e sem SPA: HTMX e Alpine ficam em `static/js/`, e o Tailwind corre pelo binário standalone v3.4.17.
- Os textos da interface são em português de Portugal e seguem a secção 9 do `plan.md`: o toast usa o verbo do botão, o erro diz o que fazer e o ecrã vazio indica a ação seguinte.
- Os perfis são fixos: `ADMIN`, `MANAGER`, `STOCK`, `STAFF`, e acima deles o Admin do grupo (secção 7 do `plan.md`). Não há permissões configuráveis.
- As invariantes 1 a 10 do `plan.md` (secção 6) continuam em vigor. Cada correção que lhes toque leva um teste.
- Não há fila de tarefas (Celery, Redis). O trabalho periódico faz-se com um management command e cron.
- `TIME_ZONE = "Europe/Lisbon"`. O dia de trabalho de um registo é o dia da entrada.
- Os testes ficam em `tests/test_*.py` e usam as fixtures `restaurant`, `admin_user`, `manager`, `stock_user` e `staff_user` de `tests/conftest.py`.
- A consola do Windows é cp1252: os management commands só imprimem ASCII, e as mensagens de commit vão sem acentos, como no resto do repo.
- Sempre que um template muda, recompila-se o CSS (`python manage.py css`, criado na Tarefa A1).
- No fim de cada sessão acrescenta-se uma linha ao Registo de progresso do `plan.md` (protocolo da secção 0) a dizer que tarefa deste plano avançou.

## Review Focus

1. **Uma conta com perfis diferentes em duas casas:** o menu e as permissões seguem a casa ativa (teste `test_menu_segue_o_perfil_da_casa_ativa`, na Tarefa B1).
2. **Um trabalhador que sai a meio do mês:** continua no fecho e no CSV desse mês (teste `test_quem_saiu_a_meio_do_mes_entra_no_fecho_e_no_csv`, na Tarefa C1).
3. **A madrugada, com turnos que passam a meia-noite:** «hoje» é o dia de serviço que ainda está a decorrer (teste `test_de_madrugada_mostra_o_servico_da_noite`, na Tarefa C5).
4. **Decisões que tocam num mês já aprovado:** aprovar ou registar uma ausência nesse mês é recusado (teste `test_aprovar_em_mes_aprovado_e_recusado`, na Tarefa C2).
5. **Vários processos em produção:** o bloqueio do código e os tokens do quiosque ficam numa cache partilhada (teste `test_prod_cache_partilhada_entre_processos`, na Tarefa A2).

---

## Como usar este plano

- `- [x]` só depois de os testes da tarefa passarem. `- [~]` quer dizer parcial, como no `plan.md`.
- Cada tarefa termina com um commit.
- A ordem recomendada é a das letras:
  - **A** e **B** antes do piloto;
  - **C** antes do primeiro fecho de mês real;
  - **D** entre umas e outras, quando houver tempo;
  - **E** só depois de o piloto dar feedback;
  - **F** é o caminho até ao piloto fora do código (aponta para o `todo.md`).

## Diagnóstico (2026-11-07)

**Ponto de partida:**
- 517 testes a passar e cobertura de 94%.
- `check --deploy` só deixa o aviso do HSTS preload, e as migrações estão em dia.
- As 15 fases têm código, e nenhuma está em uso real.
- A revisão passou pelo código das apps, pelo browser (como Admin do grupo, Responsável de stock e colaboradora, com o `demo`) e pela configuração de produção.

**Gravidade:**
- **P0:** bloqueia o piloto.
- **P1:** um utilizador vai dar com o problema.
- **P2:** melhoria.

| # | Grav. | O que está mal | Onde | Tarefa |
|---|---|---|---|---|
| 1 | P1 | O `static/css/app.css` estava desatualizado: faltavam 16 classes usadas pelo dashboard, e a linha do tempo «Turnos de hoje» aparecia partida. Nada avisa quando isto acontece. Recompilado durante a revisão. | `static/css/app.css` | A1 |
| 2 | P0 | O `requirements.txt` não tem `gunicorn` nem um driver de PostgreSQL. A produção, tal como o plano a descreve, não arranca. | `requirements.txt` | A2 |
| 3 | P0 | O `prod.py` não tem `SECURE_PROXY_SSL_HEADER` (atrás de um proxy, o `SECURE_SSL_REDIRECT` entra em ciclo), `CSRF_TRUSTED_ORIGINS`, cache partilhada (o bloqueio do código e os tokens do quiosque só funcionam com um processo) nem `LOGGING`. | `config/settings/prod.py` | A2 |
| 4 | P0 | `manage.py demo` cria um superutilizador com uma palavra-passe conhecida e corre em qualquer ambiente. | `core/management/commands/demo.py:59` | A2 |
| 5 | P1 | O login por email e palavra-passe não tem limite de tentativas. O quiosque tem. | `accounts/views.py:25` | A3 |
| 6 | P1 | Não há CI. O `pytest` corre com `--no-migrations` e em SQLite, por isso nem as migrações nem as constraints de PostgreSQL são testadas. | `pytest.ini` | A4 |
| 7 | P1 | Registos com valor legal apagam-se em cascata: ponto, fecho do mês, pedidos, ausências, vendas, receções e consumos têm `on_delete=CASCADE`. O admin do Django trava parte disto; um `delete()` no código ou na shell não. | `attendance/models.py:81,86,399,402`, `vacations/models.py:51`, `sales/models.py:84,160` | A5 |
| 8 | P2 | Não há `.gitattributes`, e cada diff avisa LF/CRLF. Os ficheiros sintéticos de `saft-teste/` não estão no git nem no `.gitignore`. O trabalho do dashboard (26ª sessão) está por commitar. O `time-machine` aparece no plano mas não está instalado. | raiz | A6 |
| 9 | P1 | O service worker guarda as páginas `/equipa/`, e sair da conta não as apaga. Num telemóvel partilhado e sem rede, abrem-se as horas e as férias de quem lá esteve antes. O manifest diz «ferias». | `static/sw.js:68`, `static/manifest.webmanifest` | A7 |
| 10 | P1 | O menu mostra Trabalhadores, Ponto, Férias, Turnos e Dispositivo ao Responsável de stock, que ao clicar recebe «403 Forbidden» sem estilo (visto no browser). | `templates/partials/nav_manage.html:22-25,37` | B1 |
| 11 | P1 | Não há páginas de erro próprias para 403, 404, 500 e CSRF: em produção aparecem as do Django. | `templates/` | B2 |
| 12 | P2 | Um gerente sem ficha que abre a app do colaborador fica num beco: o ecrã «Falta a ficha» só tem «Sair». E o backoffice não tem ligação para a própria app. | `templates/staff/sem_ficha.html` | B3 |
| 13 | P1 | O fecho e a exportação do mês usam «fichas ativas hoje». Quem saiu a meio do mês desaparece do fecho e do CSV para o contabilista. Quem só começa no mês seguinte aparece «por aprovar» no anterior. | `attendance/views.py:364`, `dashboard/views.py:87,277` | C1 |
| 14 | P1 | Registar ou aprovar uma ausência não verifica se o mês já está aprovado (invariante 8), nem se a ausência se sobrepõe a outra aprovada. Duas aprovadas sobrepostas descontam o saldo duas vezes. | `vacations/services.py:115,166,220` | C2 |
| 15 | P2 | Os pedidos pendentes cujas datas já passaram não se distinguem dos outros. O do Rui (18 a 22/09) continuava pendente em novembro. | `templates/manage/vacations/lista.html` | C3 |
| 16 | P1 | As horas previstas dos turnos entram nas «horas trabalhadas» também nos dias que ainda não chegaram. A Análise de novembro mostrava 189h30 a 7/11, e as vendas por hora ficam erradas. | `sales/reports.py:115-123` | C4 |
| 17 | P1 | De madrugada, «hoje» é o dia do calendário. À 01:21, o turno da noite em curso não aparece no dashboard nem no Ponto do dia, e já aparecem os turnos do almoço seguinte. O cumprimento diz «Bom dia», e a etiqueta da hora atual tapa a primeira hora da escala. | `dashboard/views.py:127`, `templates/manage/dashboard.html:7` | C5 |
| 18 | P2 | O cartão «0,00 € · Vendas de Novembro · até 25/10» lê-se como zero vendas. Também diz «O mês de 10/2026», com o número do mês em vez do nome. O painel do grupo repete o mesmo cartão. | `templates/manage/dashboard.html:31-32`, `templates/manage/grupo/painel.html:37` | C6 |
| 19 | P2 | As quantidades aparecem em três formatos: «4,000 KG» no stock e no dashboard, «4 KG» nas compras e «-2.000 KG» nas mensagens de erro, com as unidades em maiúsculas. O filtro `numero` vive em `sales`. | `templates/partials/inventory/item_row.html:4` e mais 6 sítios | D1 |
| 20 | P2 | O painel do grupo tem scroll horizontal num ecrã de 1639px, o nome de cada casa parte-se em três linhas e o botão «Abrir» fica cortado. | `templates/manage/grupo/painel.html` | D2 |
| 21 | P2 | As linhas das listas têm 3 ou 4 botões (Stock: Movimento, Transferir, Preços e Editar; Trabalhadores: código, conta e editar). A lista fica pesada e a ação principal de cada linha perde-se no meio das outras. | `templates/partials/inventory/item_row.html`, `templates/manage/workers/lista.html` | D3 |
| 22 | P2 | No login, o email é `type="text"` com `autocomplete="email"`. No telemóvel não abre o teclado de email, e os gestores de palavras-passe não o reconhecem. | `accounts/forms.py:15` | D4 |
| 23 | P2 | As funções e os contactos não seguem regra nenhuma: «copeiro» ao lado de «Sala», e «+351 911 043 974» ao lado de «965852489». | `workers/forms.py` | D5 |
| 24 | P2 | O Ponto do dia mostra «—» nos totais vazios, e a secção 4 do plano manda mostrar `0h00`. | `templates/manage/attendance/dia.html:68` | D6 |
| 25 | P2 | O `dashboard` importa funções privadas de `attendance.views` (`_desvios`, `overlapping_entries`). Há imports dentro de funções para fugir a ciclos. | `dashboard/views.py:106,122` | D7 |
| 26 | P2 | O menu tem 12 entradas sem grupos. O Stock usa botões no cabeçalho como sub-navegação, e o Ponto, as Férias e as Compras usam pílulas. | `templates/partials/nav_manage.html`, `templates/manage/inventory/lista.html` | D8 |
| 27 | P2 | A Análise abre no mês corrente, quase sempre sem vendas, enquanto as Vendas abrem no último mês importado. | `analytics/views.py:36` | D9 |

### Utilidade e potencial

**O que o produto tem a seu favor:**
- Junta num só sítio o ponto com valor legal, os turnos, as férias, o stock, as compras, as fichas técnicas e as vendas, e foi pensado para um restaurante.
- Ler as vendas pelo SAF-T é a vantagem mais difícil de copiar: funciona com qualquer POS certificado e não precisa de integração nenhuma.
- O quiosque com código e a app só de consulta resolvem bem o problema do pessoal de cozinha.

**O maior risco** não está no código. É a largura antes do uso: 15 fases construídas e nenhuma usada por um restaurante.

**Recomendação:**
- Fechar os blocos A a C, pôr a Peco a usar o produto e não abrir funcionalidades novas (bloco E) antes de 4 semanas de uso real.
- Medir três coisas nesse período:
  - picagens por dia sem correção;
  - fecho do mês feito sem Excel;
  - SAF-T importado todas as semanas.

**O que mais torna o software intuitivo**, por ordem:
1. Menu que só mostra o que se pode abrir (B1).
2. Um formato único para números e datas (D1, C6).
3. Uma ação por linha (D3).
4. Lista de primeiros passos numa casa nova (E1).
5. Ficha do trabalhador como página central (E2).

## Veredicto sobre o stack

**Mantinha o que está:**
- **Django 5.2 LTS** (suporte até abril de 2028).
- **HTMX e Alpine vendored:** o produto é feito de formulários e listas, e a PWA precisa da casca offline.
- **Tailwind standalone, sem npm.**
- **SQLite em desenvolvimento.**
- **`defusedxml`, `openpyxl` e `whitenoise`.**

Uma SPA (React) ou o Tailwind v4 não trazem nada de que o produto precise agora.

**Acrescentava, antes do piloto:**

| O quê | Para quê | Tarefa |
|---|---|---|
| `gunicorn`, `psycopg[binary]` | arrancar em produção com PostgreSQL | A2 |
| `DatabaseCache` do Django | cache partilhada entre processos, sem Redis | A2 |
| `sentry-sdk` (DSN opcional, sem dados pessoais) | ver os erros de produção no piloto | A2 |
| GitHub Actions com PostgreSQL 16 | testar as migrações e as constraints a sério em cada push | A4 |
| `ruff` | apanhar imports mortos, variáveis por usar e erros simples | A4 |
| `django-anymail` com um fornecedor de email na UE | recuperar a palavra-passe e enviar avisos e encomendas, quando os emails entrarem (`todo.md` §6) | fora deste plano |
| cron + management commands | trabalho periódico (lembretes, limpeza) sem Celery | E |

**Hosting** (decisão do TM, `todo.md` §6): a recomendação é uma VPS na UE (por exemplo, a Hetzner) com Caddy, que trata do certificado `*.opero.pt` por desafio DNS, mais gunicorn, PostgreSQL 16 e um `pg_dump` diário para armazenamento noutro sítio. É a forma mais simples de ter subdomínios em wildcard com controlo total e dados na UE. Uma PaaS europeia também serve, desde que aceite domínios wildcard próprios: confirmar isso antes de escolher.

**Na organização do código:**
- Lógica partilhada passa para módulos de seletores (D7).
- Permissões num só sítio (B1).
- Filtros de formatação no `core` (D1).
- O `plan.md` tem 200 KB e cada sessão gasta contexto a lê-lo: arquivar o registo antigo (passo opcional da Tarefa A6).

---

## Bloco A — Produção e base técnica (antes do piloto)

### Tarefa A1: CSS sempre compilado

**Files:**
- Create: `core/management/commands/css.py`
- Create: `core/checks.py`
- Modify: `core/apps.py` (importar `core.checks` no `ready()`)
- Modify: `plan.md` §2 «Cuidados» (uma linha sobre o comando)
- Test: `tests/test_css.py`

**Interfaces:**
- Produces: `core.checks.css_desatualizado(css: pathlib.Path, fontes: list[pathlib.Path]) -> bool` e o comando `python manage.py css [--watch] [--minify]`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_css_mais_antigo_que_um_template_esta_desatualizado(tmp_path):
    css, tpl = _ficheiros(tmp_path)
    os.utime(css, (1, 1))
    assert css_desatualizado(css, [tmp_path / "templates"]) is True

def test_css_recente_esta_em_dia(tmp_path):
    css, tpl = _ficheiros(tmp_path)
    os.utime(tpl, (1, 1))
    assert css_desatualizado(css, [tmp_path / "templates"]) is False

def test_css_em_falta_esta_desatualizado(tmp_path):
    assert css_desatualizado(tmp_path / "app.css", [tmp_path]) is True
```
(`_ficheiros` cria `app.css` e `templates/x.html` em `tmp_path`.)

- [ ] **Step 2: Correr e ver falhar.** `pytest tests/test_css.py -v`. Esperado: `ImportError`.
- [ ] **Step 3: Implementar.**
  - `css_desatualizado` compara o `st_mtime` do CSS com o mais recente de `*.html` nas pastas e dos ficheiros indicados.
  - O aviso do sistema (`@register(Tags.staticfiles)`, id `opero.W001`) só corre com `DEBUG=True`. Usa como fontes `templates/`, `static/src/input.css`, `tailwind.config.js` e `*/templates/`, e diz: «O CSS está desatualizado. Corra: python manage.py css».
  - O comando corre `tools/tailwindcss.exe` no Windows, `tools/tailwindcss` noutros sistemas, ou o binário de `TAILWIND_BIN` se estiver definido, com `-i static/src/input.css -o static/css/app.css`, e passa-lhe `--watch` e `--minify`. Sem binário, dá `CommandError` e diz onde o descarregar (release v3.4.17).
- [ ] **Step 4: Correr e ver passar.** `pytest tests/test_css.py -v` → PASS. Depois mexer num template e correr `python manage.py check` → mostra `opero.W001`.
- [ ] **Step 5: Commit.** `git commit -m "CSS: comando css e aviso no check quando o CSS fica para tras"`

### Tarefa A2: Settings de produção, dependências e `demo` seguro

**Files:**
- Modify: `requirements.txt` (acrescentar `gunicorn>=23,<24`, `psycopg[binary]>=3.2,<4`, `sentry-sdk[django]>=2.18,<3`)
- Modify: `config/settings/prod.py`, `config/settings/base.py` (`LOGGING`)
- Modify: `.env.example` (`DJANGO_CSRF_TRUSTED_ORIGINS=https://*.opero.pt`, `SENTRY_DSN=`)
- Modify: `core/management/commands/demo.py`
- Test: `tests/test_producao.py`

- [ ] **Step 1: Escrever os testes que falham**

```python
def _prod(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x" * 60)
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", ".opero.pt")
    monkeypatch.setenv("DJANGO_CSRF_TRUSTED_ORIGINS", "https://*.opero.pt")
    import config.settings.prod as prod
    return importlib.reload(prod)

def test_prod_atras_de_proxy_https(monkeypatch):
    prod = _prod(monkeypatch)
    assert prod.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert prod.CSRF_TRUSTED_ORIGINS == ["https://*.opero.pt"]

def test_prod_cache_partilhada_entre_processos(monkeypatch):
    prod = _prod(monkeypatch)
    assert prod.CACHES["default"]["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"

def test_demo_recusa_fora_de_desenvolvimento(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="desenvolvimento"):
        call_command("demo")
```

- [ ] **Step 2: Correr e ver falhar.** `pytest tests/test_producao.py -v`. Esperado: 3 FAIL.
- [ ] **Step 3: Implementar.**
  - **`prod.py`:**
    - `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`.
    - `CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])`.
    - `CACHES` com `DatabaseCache` e `LOCATION = "opero_cache"`.
    - `CONN_MAX_AGE = 60` e `CONN_HEALTH_CHECKS = True` na base de dados `default`.
    - `sentry_sdk.init(dsn=..., send_default_pii=False, traces_sample_rate=0)`, só se `SENTRY_DSN` estiver definido.
  - **`base.py`:** `LOGGING` para a consola, `INFO` para `django`, `ERROR` com traceback para `django.request` e formato `%(asctime)s %(levelname)s %(name)s %(message)s`.
  - **`demo`:** opção `--forcar`. Sem ela e com `DEBUG=False`, dá `CommandError("O demo so corre em desenvolvimento (DEBUG=True). Use --forcar num ambiente de demonstracao.")`.
- [ ] **Step 4: Correr e ver passar.** `pytest tests/test_producao.py -v` → PASS. Correr `python manage.py check --deploy --settings=config.settings.prod` com as variáveis do teste: só fica o W021 (preload).
- [ ] **Step 5: Commit.** `git commit -m "Producao: proxy HTTPS, CSRF por subdominio, cache partilhada, logs, Sentry e demo so em dev"`

### Tarefa A3: Limite de tentativas no login

**Files:**
- Create: `core/throttle.py`
- Modify: `kiosk/throttle.py` (passa a usar `core.throttle.Limite`; mantém `esta_bloqueado`, `registar_falha`, `limpar_falhas`, que o `kiosk/views.py` usa)
- Modify: `accounts/forms.py` (`LoginForm.clean`)
- Test: `tests/test_auth.py` (classe nova `TestLimiteLogin`)

**Interfaces:**
- Produces: `core.throttle.Limite(prefixo: str, max_falhas: int, segundos: int)` com `bloqueado(chave) -> bool`, `falhou(chave) -> int` e `limpar(chave) -> None`.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestLimiteLogin:
    URL = reverse_lazy("accounts:login")

    def test_dez_falhas_bloqueiam_o_email(self, client, manager):
        for _ in range(10):
            client.post(self.URL, {"username": "gerente@tasca.pt", "password": "errada"})
        r = client.post(self.URL, {"username": "GERENTE@tasca.pt", "password": "segredo-de-teste-123"})
        assert "Demasiadas tentativas" in r.content.decode()
        assert "_auth_user_id" not in client.session

    def test_entrar_bem_limpa_as_falhas(self, client, manager):
        for _ in range(9):
            client.post(self.URL, {"username": "gerente@tasca.pt", "password": "errada"})
        client.post(self.URL, {"username": "gerente@tasca.pt", "password": "segredo-de-teste-123"})
        client.logout()
        client.post(self.URL, {"username": "gerente@tasca.pt", "password": "errada"})
        r = client.post(self.URL, {"username": "gerente@tasca.pt", "password": "segredo-de-teste-123"})
        assert r.status_code == 302
```

- [ ] **Step 2: Correr e ver falhar.** `pytest tests/test_auth.py -k Limite -v`. Esperado: o primeiro FAIL.
- [ ] **Step 3: Implementar.**
  - Limite do login: 10 falhas em 900 segundos. A chave é o email em minúsculas, sem espaços.
  - Mensagem: «Demasiadas tentativas. Espere 15 minutos ou peça ao gerente uma palavra-passe provisória.»
  - No `clean()`: verificar o bloqueio, depois chamar `super().clean()`. Se falhar, registar a falha e voltar a levantar o erro; se passar, limpar as falhas.
  - O quiosque passa a usar `Limite("codigo-falhas", 5, 60)`, com o mesmo comportamento de hoje.
- [ ] **Step 4: Correr e ver passar.** `pytest tests/test_auth.py tests/test_staff.py -v` → PASS (os testes do quiosque continuam verdes).
- [ ] **Step 5: Commit.** `git commit -m "Login: bloqueio de 15 minutos ao fim de 10 tentativas falhadas"`

### Tarefa A4: CI no GitHub Actions, com PostgreSQL e ruff

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `ruff.toml`
- Modify: `requirements-dev.txt` (acrescentar `ruff>=0.8`)

- [ ] **Step 1: Configurar o ruff.**
  - Valores: `line-length = 120`, `target-version = "py312"`, `extend-exclude = ["*/migrations/*", "re-factorial", "floorplan"]`, `lint.select = ["E4", "E7", "E9", "F", "I", "B", "DJ"]`.
  - Correr `ruff check . --fix` e corrigir à mão o que sobrar.
  - Commit: `git commit -m "ruff: configuracao e correcoes"`.
- [ ] **Step 2: Escrever o workflow.**
  - Gatilhos: `push` e `pull_request`.
  - Job `sqlite`, em Python 3.12: `pip install -r requirements-dev.txt`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `ruff check .` e `pytest -q`.
  - Job `postgres`:
    - serviço `postgres:16` com `POSTGRES_PASSWORD=postgres`;
    - `DATABASE_URL=postgres://postgres:postgres@localhost:5432/opero`;
    - `python manage.py migrate`, que aplica as migrações reais a uma base vazia (o que o `--no-migrations` esconde);
    - `pytest -q --migrations`.
  - Job `css`: `pip install -r requirements.txt`, descarregar `https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64` para `tools/tailwindcss`, dar-lhe `chmod +x` e correr `python manage.py css --minify`.
- [ ] **Step 3: Verificar.** Fazer push de um ramo e ver os três jobs verdes no separador Actions. Se o job `postgres` falhar, cada falha passa a ser uma tarefa nova neste bloco, porque é exatamente o que o CI veio mostrar.
- [ ] **Step 4: Commit.** `git commit -m "CI: testes em SQLite e PostgreSQL, migracoes, ruff e build do CSS"`

### Tarefa A5: Registos legais protegidos na base de dados

**Files:**
- Modify: `attendance/models.py` (`TimeEntry.worker`, `TimeEntry.restaurant`, `CorrectionRequest.worker`, `CorrectionRequest.restaurant`, `MonthClose.worker`, `MonthClose.restaurant`)
- Modify: `vacations/models.py` (`VacationRequest.worker`)
- Modify: `sales/models.py` (`SalesImport.restaurant`, `SalesDocument.restaurant`)
- Modify: `inventory/models.py` (`InternalConsumption.restaurant`)
- Modify: `purchasing/models.py` (`Receipt.restaurant`)
- Create: as migrações geradas (`makemigrations`), só com `AlterField`
- Test: `tests/test_ficha_trabalhador.py`

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_ficha_com_registos_nao_se_apaga_nem_por_codigo(restaurant, manager):
    w = Worker.objects.create(restaurant=restaurant, full_name="Rui Registo")
    agora = timezone.now()
    add_manual_entry(worker=w, user=manager, check_in=agora - 3 * H, check_out=agora - H)
    with pytest.raises(ProtectedError):
        w.delete()

def test_casa_com_registos_nao_se_apaga(restaurant, manager):
    w = Worker.objects.create(restaurant=restaurant, full_name="Rui Registo")
    agora = timezone.now()
    add_manual_entry(worker=w, user=manager, check_in=agora - 3 * H, check_out=agora - H)
    with pytest.raises(ProtectedError):
        restaurant.delete()
```

- [ ] **Step 2: Correr e ver falhar.** `pytest tests/test_ficha_trabalhador.py -k "nao_se_apaga" -v`. Esperado: FAIL (DID NOT RAISE).
- [ ] **Step 3: Implementar.** `on_delete=models.PROTECT` nos campos listados, e depois `python manage.py makemigrations`. O `workers.services.delete_worker` continua a apagar fichas sem histórico, porque os apagáveis (turnos, folgas, saldos) mantêm `CASCADE`.
- [ ] **Step 4: Correr tudo.** `pytest -q` → PASS (o apagar a ficha sem histórico continua a funcionar).
- [ ] **Step 5: Commit.** `git commit -m "Registos de ponto, ausencias, vendas e rececoes protegidos contra apagar em cascata"`

### Tarefa A6: Arrumação do repositório

**Files:**
- Create: `.gitattributes`
- Modify: `.gitignore` (acrescentar `/saft-teste/`)
- Modify: `plan.md` §2 (tirar o `time-machine`, porque os testes passam `agora=`)

- [ ] **Step 1: Commitar o trabalho pendente da 26ª sessão.** O dashboard com as férias pendentes em «Por tratar» e o cartão «Em férias» foi visto no browser nesta revisão e está bem. `pytest tests/test_dashboard_ferias.py tests/test_staff.py -q` → PASS. Depois: `git commit -m "Dashboard: ferias pendentes em Por tratar e cartao Em ferias"`.
- [ ] **Step 2: Escrever o `.gitattributes`.**
  - `* text=auto`.
  - `binary` para `*.png`, `*.woff2`, `*.xlsx`, `*.docx` e `*.exe`.
  - Depois: `git add --renormalize .` e `git commit -m "gitattributes: fins de linha normalizados"`.
- [ ] **Step 3: Pôr `/saft-teste/` no `.gitignore`.** Os ficheiros são sintéticos e podem gerar-se outra vez com `sales/sintetico.py`. Commit.
- [ ] **Step 4 (opcional): Arquivar o registo antigo.** Mover as linhas do Registo de progresso anteriores a 2026-11-01 para `docs/registo-de-progresso.md`, com uma ligação no `plan.md`. O ficheiro passa de 200 KB para uma fração disso, e cada sessão lê menos. Commit.

### Tarefa A7: Sair da conta limpa o telemóvel

**Files:**
- Modify: `accounts/views.py` (`LogoutView`)
- Modify: `static/manifest.webmanifest` («férias» com acento)
- Test: `tests/test_auth.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_sair_limpa_a_cache_do_telemovel(client, staff_user):
    client.force_login(staff_user)
    r = client.post(reverse("accounts:logout"))
    assert r["Clear-Site-Data"] == '"cache", "storage"'
```

- [ ] **Step 2: Correr e ver falhar.** Esperado: `KeyError`.
- [ ] **Step 3: Implementar.** No `LogoutView.post`, a resposta leva `Clear-Site-Data: "cache", "storage"`, o que apaga a Cache Storage do service worker e anula o registo dele, que se refaz na visita seguinte. Corrigir também o texto do manifest.
- [ ] **Step 4: Correr e ver passar.** Depois, no Android (`todo.md` §4): entrar, ver o histórico, sair, desligar a rede e abrir `/equipa/historico/`. Não deve aparecer o histórico.
- [ ] **Step 5: Commit.** `git commit -m "Sair da conta apaga as paginas guardadas pelo service worker"`

---

## Bloco B — Navegação e erros (antes do piloto)

### Tarefa B1: Um mapa de permissões para as views e para o menu

**Files:**
- Create: `core/permissions.py`
- Modify: `core/mixins.py` (os mixins passam a ler os conjuntos de `core.permissions`)
- Modify: `core/context_processors.py` (põe `secoes` no contexto)
- Modify: `templates/partials/nav_manage.html` (cada entrada fica dentro de `{% if "<secao>" in secoes %}`)
- Test: `tests/test_menu.py`

**Interfaces:**
- Produces:
  - `core.permissions.PESSOAS`, `STOCK` e `ADMIN` (`frozenset` de `User.Role`);
  - `SECOES: dict[str, frozenset]`, com as chaves `dashboard`, `trabalhadores`, `ponto`, `ferias`, `turnos`, `stock`, `compras`, `fichas`, `vendas`, `analise`, `dispositivo` e `configuracao`;
  - `secoes_visiveis(role: str | None) -> frozenset[str]`.

| Secção | Perfis |
|---|---|
| dashboard, stock, compras, fichas, analise | ADMIN, MANAGER, STOCK |
| trabalhadores, ponto, ferias, turnos, vendas, dispositivo | ADMIN, MANAGER |
| configuracao | ADMIN |

O Grupo continua a depender de `is_group_admin`.

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.mark.parametrize("perfil", ["admin_user", "manager", "stock_user"])
def test_cada_ligacao_do_menu_abre(client, perfil, request):
    client.force_login(request.getfixturevalue(perfil))
    html = client.get(reverse("dashboard:home")).content.decode()
    menu = html[html.index('aria-label="Navegação principal"'):]
    menu = menu[: menu.index("</nav>")]
    for href in set(re.findall(r'href="(/[^"]+)"', menu)):
        assert client.get(href).status_code in (200, 302), href

def test_resp_stock_nao_ve_as_areas_de_pessoas(client, stock_user):
    client.force_login(stock_user)
    html = client.get(reverse("dashboard:home")).content.decode()
    for nome in ("workers:lista", "attendance:dia", "vacations:calendario", "shifts:planeador", "accounts:dispositivo"):
        assert f'href="{reverse(nome)}"' not in html

def test_menu_segue_o_perfil_da_casa_ativa(client, restaurant, stock_user):
    outra = Restaurant.objects.create(name="Tasca Dois", slug="tasca-dois", organization=restaurant.organization)
    dar_acesso(stock_user, outra, User.Role.MANAGER)
    client.force_login(stock_user)
    client.post(reverse("dashboard:mudar_casa"), {"casa": outra.pk})
    html = client.get(reverse("dashboard:home")).content.decode()
    assert f'href="{reverse("attendance:dia")}"' in html
```

- [ ] **Step 2: Correr e ver falhar.** `pytest tests/test_menu.py -v`. Esperado: `test_cada_ligacao_do_menu_abre[stock_user]` e `test_resp_stock_nao_ve_as_areas_de_pessoas` falham.
- [ ] **Step 3: Implementar.**
  - `ManagerRequiredMixin.allowed_roles = PESSOAS`, `StockRequiredMixin.allowed_roles = STOCK` e `AdminRequiredMixin.allowed_roles = ADMIN`, como atributos de classe. Isto tira o `dispatch` que só servia para os definir.
  - O processador de contexto acrescenta `secoes = secoes_visiveis(request.role)`.
  - O menu deixa de comparar `request.role` com texto.
- [ ] **Step 4: Correr tudo.** `pytest -q` → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Menu e permissoes a partir do mesmo mapa: cada perfil so ve o que pode abrir"`

### Tarefa B2: Páginas de erro com o aspeto da app

**Files:**
- Create: `templates/erro_base.html` (creme, logo, título em Playfair, um parágrafo e um botão para `/`)
- Create: `templates/403.html`, `templates/404.html`, `templates/500.html`, `templates/403_csrf.html`
- Test: `tests/test_erros.py`

| Página | Título | Texto |
|---|---|---|
| 403 | «Não tem acesso a esta página» | «O seu perfil nesta casa não abre esta área. Se precisa dela, peça ao gerente.» |
| 404 | «Esta página não existe» | «O endereço pode estar errado ou a página foi removida.» |
| 500 | «Algo correu mal» | «O erro ficou registado. Tente de novo daqui a pouco.» |
| CSRF | «A página expirou» | «Volte atrás, recarregue a página e repita.» |

O 500 não usa `{% url %}` nem dados do pedido, porque o Django o mostra sem contexto.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_403_tem_o_aspeto_da_app(client, stock_user):
    client.force_login(stock_user)
    r = client.get(reverse("workers:lista"))
    assert r.status_code == 403
    assert "Não tem acesso a esta página" in r.content.decode()

def test_404_tem_o_aspeto_da_app(client, manager):
    client.force_login(manager)
    r = client.get("/gestao/nao-existe/")
    assert r.status_code == 404 and "Esta página não existe" in r.content.decode()

def test_500_mostra_se_sem_contexto():
    assert "Algo correu mal" in loader.get_template("500.html").render()
```

- [ ] **Step 2: Correr e ver falhar.** `pytest tests/test_erros.py -v`.
- [ ] **Step 3: Implementar** os templates com os textos da tabela.
- [ ] **Step 4: Correr e ver passar**, recompilar o CSS e ver o 403 no browser como Resp. stock.
- [ ] **Step 5: Commit.** `git commit -m "Paginas de erro 403, 404, 500 e CSRF com o aspeto da app"`

### Tarefa B3: Passar entre a app e a gestão

**Files:**
- Modify: `templates/staff/sem_ficha.html`, `templates/staff/_cabecalho.html` (ligação «Gestão» para quem tem `request.user.is_backoffice`)
- Modify: `templates/base_manage.html` (menu da conta: «A minha app» → `staff:home`)
- Test: `tests/test_staff.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_sem_ficha_com_backoffice_tem_caminho_para_a_gestao(client, manager):
    client.force_login(manager)
    html = client.get(reverse("staff:home")).content.decode()
    assert f'href="{reverse("dashboard:home")}"' in html
```

- [ ] **Step 2: Correr e ver falhar.**
- [ ] **Step 3: Implementar** as duas ligações. O colaborador sem backoffice não vê nenhuma.
- [ ] **Step 4: Correr e ver passar.** `pytest tests/test_staff.py -q`.
- [ ] **Step 5: Commit.** `git commit -m "Ligacoes entre a app do colaborador e a gestao"`

---

## Bloco C — Correções de lógica (antes do primeiro fecho real)

### Tarefa C1: Quem entra no fecho do mês

**Files:**
- Modify: `workers/models.py` (`end_date = models.DateField("data de saída", null=True, blank=True)`), mais a migração gerada
- Modify: `workers/views.py:112` (`WorkerDeactivateView`: lê `data_saida`, que por omissão é hoje, e grava `end_date`; reativar limpa-o)
- Modify: `templates/manage/workers/form.html` (o botão Desativar passa a pedir a data de saída)
- Create: `attendance/selectors.py`
- Modify: `attendance/views.py:364` (`MonthView._workers`), `dashboard/views.py:87` (`por_aprovar`), `dashboard/views.py:270` (`_sinais`)
- Test: `tests/test_fecho_mes.py` (classe nova `TestQuemEntraNoMes`)

**Interfaces:**
- Produces: `attendance.selectors.workers_for_month(qs: QuerySet[Worker], month: datetime.date) -> QuerySet[Worker]`. Uma ficha entra no mês M se:
  - começou antes do fim de M (`start_date` nulo ou menor ou igual ao último dia de M); **e**
  - estava ativa sem data de saída, **ou** saiu dentro ou depois de M (`end_date` maior ou igual ao primeiro dia de M), **ou** tem registos de ponto em M.
  
  A ordem é por `full_name`, e o resultado leva `.distinct()`.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestQuemEntraNoMes:
    def test_quem_saiu_a_meio_do_mes_entra_no_fecho_e_no_csv(self, client, manager, restaurant, mes_passado):
        w = Worker.objects.create(restaurant=restaurant, full_name="Rita Saiu")
        add_manual_entry(worker=w, user=manager, check_in=_dia(mes_passado, 3), check_out=_dia(mes_passado, 3, 17))
        w.is_active, w.end_date = False, _dia(mes_passado, 15).date()
        w.save()
        client.force_login(manager)
        url = reverse("attendance:mes") + f"?mes={mes_passado:%Y-%m}"
        assert "Rita Saiu" in client.get(url).content.decode()
        mes.approve_month(worker=w, month=mes_passado, user=manager)
        assert "Rita Saiu" in client.get(url + "&exportar=csv").content.decode()

    def test_quem_comeca_depois_do_mes_nao_esta_por_aprovar(self, client, manager, restaurant, mes_passado):
        Worker.objects.create(restaurant=restaurant, full_name="Jorge Novo", start_date=timezone.localdate().replace(day=1))
        client.force_login(manager)
        url = reverse("attendance:mes") + f"?mes={mes_passado:%Y-%m}"
        assert "Jorge Novo" not in client.get(url).content.decode()
        assert "por fechar" not in client.get(reverse("dashboard:home")).content.decode()

    def test_desativar_guarda_a_data_de_saida(self, client, manager, restaurant):
        w = Worker.objects.create(restaurant=restaurant, full_name="Ana Sai")
        client.force_login(manager)
        client.post(reverse("workers:desativar", args=[w.pk]), {"data_saida": "2026-10-31"})
        w.refresh_from_db()
        assert not w.is_active and w.end_date == datetime.date(2026, 10, 31)
```

- [ ] **Step 2: Correr e ver falhar.** `pytest tests/test_fecho_mes.py -k QuemEntra -v`.
- [ ] **Step 3: Implementar** o seletor e usá-lo nos três sítios. No dashboard e no painel do grupo, «por aprovar» passa a ser `workers_for_month(...).count()` menos os aprovados.
- [ ] **Step 4: Correr tudo.** `pytest -q` → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Fecho do mes: entra quem trabalhou no mes, incluindo quem ja saiu; data de saida na ficha"`

### Tarefa C2: Ausências respeitam o mês aprovado e não se sobrepõem

**Files:**
- Modify: `vacations/services.py` (`create_request`, `decide_request`, `cancel_by_manager`)
- Test: `tests/test_ausencias.py` (classe nova `TestMesAprovadoESobreposicao`)

**Interfaces:**
- Consumes: `attendance.month.ensure_open(worker, *days)` e `attendance.month.month_start`.
- Produces: `vacations.services.overlapping_approved(worker, start, end, exclude=None) -> QuerySet[VacationRequest]`.

**Regras:**
- Uma ausência que nasce aprovada (registada pelo gerente, ou de um tipo sem aprovação) chama `ensure_open` para o primeiro dia de cada mês entre o início e o fim.
- Aprovar um pedido faz o mesmo.
- Cancelar uma ausência aprovada também, porque muda o mês.
- Recusar continua sempre possível.
- Aprovar ou registar uma ausência sobreposta a outra aprovada é recusado com: «Sobrepõe-se a {tipo} de {dd/mm} a {dd/mm}, já aprovada. Recuse este pedido ou cancele a outra ausência.»
- Um pedido pendente sobreposto continua a poder submeter-se, com o aviso visual da invariante 6.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestMesAprovadoESobreposicao:
    def test_aprovar_em_mes_aprovado_e_recusado(self, worker, manager, ferias, mes_passado):
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        dia = primeiro_dia_util(worker, mes_passado)
        pedido = VacationRequest.objects.create(worker=worker, absence_type=ferias, start_date=dia, end_date=dia, days_taken=1)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            decide_request(request_obj=pedido, user=manager, approve=True)

    def test_recusar_em_mes_aprovado_continua_possivel(self, worker, manager, ferias, mes_passado): ...
        # o mesmo pedido, approve=False → status RECUSADO

    def test_gerente_nao_regista_ausencia_em_mes_aprovado(self, worker, manager, ferias, mes_passado):
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        dia = primeiro_dia_util(worker, mes_passado)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            create_request(worker=worker, absence_type=ferias, start_date=dia, end_date=dia, created_by=manager)

    def test_aprovar_sobreposta_a_aprovada_e_recusado_e_o_saldo_desce_uma_vez(self, worker, manager, ferias):
        inicio = proximo_dia_util(worker, timezone.localdate() + datetime.timedelta(days=20))
        create_request(worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + 2 * DIA, created_by=manager)
        saldo = balance(worker, inicio.year)
        pedido = create_request(worker=worker, absence_type=ferias, start_date=inicio + DIA, end_date=inicio + 3 * DIA)
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            decide_request(request_obj=pedido, user=manager, approve=True)
        assert balance(worker, inicio.year) == saldo
```
O ficheiro já tem as fixtures `worker` e `ferias`. Acrescentar ao ficheiro:
- a fixture `mes_passado`, igual à de `tests/test_fecho_mes.py`;
- a constante `DIA = datetime.timedelta(days=1)`;
- os ajudantes `primeiro_dia_util(worker, mes)` e `proximo_dia_util(worker, dia)`, que avançam até `count_days(worker, d, d) == 1`. É a mesma ideia do teste de férias corrigido na 25ª sessão.

- [ ] **Step 2: Correr e ver falhar.** `pytest tests/test_ausencias.py -k MesAprovado -v`.
- [ ] **Step 3: Implementar** as regras dentro das transações que já existem.
- [ ] **Step 4: Correr tudo.** `pytest -q` → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Ausencias: mes aprovado bloqueia, sobreposicao a uma aprovada recusada"`

### Tarefa C3: Pedidos com datas passadas assinalados

**Files:**
- Modify: `templates/manage/vacations/lista.html` (pílula de alerta «Datas já passaram» nos pendentes com `end_date < hoje`)
- Modify: `vacations/views.py` (`hoje` no contexto)
- Modify: `templates/partials/dashboard/avisos.html` (o aviso de férias acrescenta «, X com datas passadas»)
- Test: `tests/test_ausencias.py`

Decisão: não expiram sozinhos. Aprovar uma ausência passada é legítimo, por exemplo uma baixa entregue tarde.

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_pendente_com_datas_passadas_assinalado(client, manager, restaurant):
    w = Worker.objects.create(restaurant=restaurant, full_name="Rui Atrasado")
    tipo = AbsenceType.objects.get(restaurant=restaurant, name="Férias")
    ontem = timezone.localdate() - datetime.timedelta(days=1)
    VacationRequest.objects.create(worker=w, absence_type=tipo, start_date=ontem, end_date=ontem)
    client.force_login(manager)
    assert "Datas já passaram" in client.get(reverse("vacations:lista")).content.decode()
```

- [ ] **Step 2: Correr e ver falhar.** **Step 3: Implementar.** **Step 4: Correr e ver passar.**
- [ ] **Step 5: Commit.** `git commit -m "Ferias: pedidos pendentes com datas passadas assinalados"`

### Tarefa C4: As horas previstas só contam até hoje

**Files:**
- Modify: `sales/reports.py:115-123` (`horas_por_servico`)
- Test: `tests/test_vendas.py` (`TestServicos`)

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_horas_previstas_so_ate_hoje(self, casa, manager):
    w = Worker.objects.create(restaurant=casa, full_name="Ana Futuro")
    amanha = timezone.localdate() + datetime.timedelta(days=1)
    turno = create_shift(restaurant=casa, worker=w, day=amanha, start=datetime.time(12), end=datetime.time(16))
    Shift.objects.filter(pk=turno.pk).update(state=Shift.State.PUBLICADO)
    horas = reports.horas_trabalhadas(casa, timezone.localdate(), amanha)
    assert amanha not in horas
```

- [ ] **Step 2: Correr e ver falhar.**
- [ ] **Step 3: Implementar.** As horas previstas só substituem as reais em dias `<= timezone.localdate(agora)`.
- [ ] **Step 4: Correr tudo.** `pytest tests/test_vendas.py tests/test_analise.py -q` → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Horas trabalhadas: turnos previstos so contam ate hoje"`

### Tarefa C5: De madrugada, «hoje» é o dia de serviço

> Decidido pelo TM a 2026-11-07: o «hoje» só passa depois da hora de corte. A hora de corte das vendas (`SalesSettings.day_cutoff_hour`, 5h por omissão) passa a definir também o «hoje» do dashboard e do Ponto do dia. O `work_date` dos registos não muda.

**Files:**
- Modify: `sales/services.py` (nova `dia_de_servico`)
- Modify: `dashboard/views.py` (`turnos_de_hoje`, `DashboardView`, `_escala`, nova `saudacao`)
- Modify: `attendance/views.py` (`TeamDayView`: o dia por omissão)
- Modify: `templates/manage/dashboard.html:5-7` (o cumprimento vem de `saudacao`; nas horas da escala, saltar as que têm `oculta`)
- Test: `tests/test_dashboard_turnos.py`

**Interfaces:**
- Produces:
  - `sales.services.dia_de_servico(restaurant, agora: datetime | None = None) -> datetime.date`;
  - `dashboard.views.saudacao(hora: int) -> str`;
  - cada hora de `_escala(...)["horas"]` ganha a chave `oculta: bool`.

- [ ] **Step 1: Escrever os testes que falham**

```python
SEXTA = datetime.date(2026, 11, 6)

def _sabado(h, m):
    return timezone.make_aware(datetime.datetime(2026, 11, 7, h, m))

def test_de_madrugada_mostra_o_servico_da_noite(restaurant, equipa):
    turno(restaurant, equipa["Ana"], datetime.time(20), datetime.time(2), dia=SEXTA)
    r = turnos_de_hoje(SimpleNamespace(restaurant=restaurant), agora=_sabado(1, 30))
    assert [l["worker"] for l in r["turnos_hoje"]] == [equipa["Ana"]]

def test_etiqueta_agora_esconde_a_hora_por_baixo(restaurant, equipa):
    # Escala das 11h às 26h (02h de sábado), de 2 em 2 horas: «01h» fica a 93,3%
    # e a hora atual (01:21) a 95,7%, a menos de 4 pontos.
    turno(restaurant, equipa["Ana"], datetime.time(11), datetime.time(16), dia=SEXTA)
    turno(restaurant, equipa["Bruno"], datetime.time(20), datetime.time(2), dia=SEXTA)
    r = turnos_de_hoje(SimpleNamespace(restaurant=restaurant), agora=_sabado(1, 21))
    horas = {h["hora"]: h["oculta"] for h in r["escala"]["horas"]}
    assert horas["01h"] is True and horas["23h"] is False

@pytest.mark.parametrize("hora,texto", [(1, "Boa noite"), (9, "Bom dia"), (15, "Boa tarde"), (21, "Boa noite")])
def test_saudacao(hora, texto):
    assert saudacao(hora) == texto
```

- [ ] **Step 2: Correr e ver falhar.** `pytest tests/test_dashboard_turnos.py -v`.
- [ ] **Step 3: Implementar.**
  - `dia_de_servico` usa `service_date(timezone.localtime(agora), SalesSettings.for_restaurant(restaurant).day_cutoff_hour)`.
  - `saudacao`: «Boa noite» antes das 5h e a partir das 20h, «Bom dia» antes das 12h, «Boa tarde» no resto.
  - Uma hora fica `oculta` quando está a menos de 4 pontos percentuais da posição de `agora`.
- [ ] **Step 4: Correr tudo, recompilar o CSS e ver o dashboard no browser.**
- [ ] **Step 5: Commit.** `git commit -m "Dashboard e ponto do dia pelo dia de servico; boa noite de madrugada"`

### Tarefa C6: Cartões e avisos com datas legíveis

**Files:**
- Modify: `core/utils.py` (`MESES` e `nome_do_mes`)
- Modify: `dashboard/views.py` (nova `cartao_vendas`, usada no dashboard e em `_sinais`)
- Modify: `templates/manage/dashboard.html:31-32`, `templates/manage/grupo/painel.html:37`, `templates/partials/dashboard/avisos.html` («O mês de outubro de 2026 está por fechar»)
- Test: `tests/test_dashboard_vendas.py`

**Interfaces:**
- Produces:
  - `core.utils.nome_do_mes(dia: date) -> str` (minúsculas: «novembro»);
  - `dashboard.views.cartao_vendas(total: Decimal, ultimo_dia: date | None, hoje: date) -> dict`, com as chaves `valor: Decimal | None` e `legenda: str`.

- [ ] **Step 1: Escrever os testes que falham**

```python
HOJE = datetime.date(2026, 11, 7)

def test_cartao_vendas_sem_importacoes():
    assert cartao_vendas(Decimal(0), None, HOJE) == {"valor": None, "legenda": "Ainda não há vendas importadas"}

def test_cartao_vendas_mes_ainda_sem_dados():
    c = cartao_vendas(Decimal(0), datetime.date(2026, 10, 25), HOJE)
    assert c == {"valor": None, "legenda": "Sem vendas de novembro · último dia 25/10"}

def test_cartao_vendas_com_dados():
    c = cartao_vendas(Decimal("812.40"), datetime.date(2026, 11, 5), HOJE)
    assert c == {"valor": Decimal("812.40"), "legenda": "Vendas de novembro · até 05/11"}
```

- [ ] **Step 2: Correr e ver falhar.** **Step 3: Implementar.** Com `valor` None, o cartão mostra «—» e a legenda leva a Vendas → Importar. **Step 4: Correr e ver passar.**
- [ ] **Step 5: Commit.** `git commit -m "Cartao de vendas e avisos do mes com nomes de meses e sem zeros enganadores"`

---

## Bloco D — Acabamento e consistência

### Tarefa D1: Um formato para as quantidades

**Files:**
- Create: `core/formatos.py` (para lá passam `_milhares`, `numero` e `euros`, que hoje estão em `sales/templatetags/vendas.py`, e entra `quantidade`)
- Modify: `sales/templatetags/vendas.py` (regista os mesmos filtros a partir de `core.formatos`, para não mexer nos 15 templates que fazem `{% load vendas %}`)
- Modify: `core/templatetags/interface.py` (regista `quantidade`)
- Modify: `templates/manage/dashboard.html:142`, `templates/partials/inventory/item_row.html:4`, `templates/partials/inventory/movimento_form.html:6`, `templates/manage/inventory/form.html:6`, `templates/manage/inventory/transferir.html:10`, `templates/manage/inventory/contagem.html:44`, `templates/manage/purchasing/lista.html:56`, e qualquer outro `{{ ….unit }}`
- Modify: `inventory/services.py:47` (a mensagem do stock negativo)
- Test: `tests/test_formatos.py`

**Interfaces:**
- Produces:
  - `core.formatos.UNIDADES = {"UN": "un", "KG": "kg", "L": "L", "CX": "cx", "EMB": "emb"}`;
  - `core.formatos.quantidade(valor: Decimal | None, unidade: str = "") -> str`, com até 3 casas decimais e sem zeros à direita;
  - o filtro `{{ item.current_stock|quantidade:item.unit }}`.

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.mark.parametrize("valor,unidade,texto", [
    ("4.000", "KG", "4 kg"), ("0.220", "L", "0,22 L"), ("1.125", "KG", "1,125 kg"),
    ("-6", "UN", "-6 un"), ("1250.5", "KG", "1 250,5 kg"), (None, "UN", "—"),
])
def test_quantidade(valor, unidade, texto):
    assert quantidade(Decimal(valor) if valor else None, unidade) == texto

def test_templates_nao_mostram_stock_nem_unidades_em_bruto():
    padrao = re.compile(r"\{\{\s*[\w.]*(current_stock|minimum_stock|\.unit)\s*\}\}")
    sujos = [p for p in Path("templates").rglob("*.html") if padrao.search(p.read_text(encoding="utf-8"))]
    assert sujos == []

def test_mensagem_de_stock_negativo_formatada(restaurant, stock_user):
    item = Item.objects.create(restaurant=restaurant, name="Arroz", unit="KG", category=Category.objects.create(restaurant=restaurant, name="Mercearia"))
    with pytest.raises(ValidationError, match="-2 kg"):
        register_movement(item=item, movement_type=StockMovement.Type.SAIDA, quantity=2, user=stock_user)
```

- [ ] **Step 2: Correr e ver falhar.**
- [ ] **Step 3: Implementar e trocar nos templates.**
- [ ] **Step 4: Correr tudo, recompilar o CSS e ver o Stock, o Dashboard e as Compras no browser.**
- [ ] **Step 5: Commit.** `git commit -m "Quantidades com o mesmo formato em todo o lado: 4 kg, 0,22 L"`

### Tarefa D2: Painel do grupo sem scroll horizontal

**Files:**
- Modify: `templates/manage/grupo/painel.html` (a tabela de 9 colunas passa a uma grelha de cartões, um por casa, `grid gap-6 sm:grid-cols-2 xl:grid-cols-3`: nome, os sinais em pares rótulo e valor, e o botão «Abrir»)
- Test: `tests/test_varias_casas.py` (os testes do painel continuam a passar)

- [ ] **Step 1:** Trocar a tabela pelos cartões. Os números com alerta usam `text-alerta`, e o cartão de vendas usa a legenda da Tarefa C6.
- [ ] **Step 2:** `pytest tests/test_varias_casas.py -q` → PASS.
- [ ] **Step 3:** Recompilar o CSS e ver no browser a 1280px e no menu estreito: `document.documentElement.scrollWidth <= innerWidth`.
- [ ] **Step 4: Commit.** `git commit -m "Painel do grupo em cartoes, sem scroll horizontal"`

### Tarefa D3: Uma ação por linha

**Files:**
- Create: `templates/components/menu_acoes.html` (um botão «Mais ações» com `aria-haspopup`, que abre uma lista em Alpine com ligações e formulários; fecha com Esc e com um clique fora)
- Modify: `templates/partials/inventory/item_row.html` («Movimento» fica visível; Transferir, Preços e Editar passam para o menu)
- Modify: `templates/manage/workers/lista.html` («Editar» fica visível; código e conta passam para o menu, e as pílulas «Definido» e «Com conta» continuam nas colunas)

- [ ] **Step 1:** Criar o componente e usá-lo nas duas listas. A ação que fica visível mantém o verde (`btn-primario`), como manda a secção 4 do `plan.md` para a ação de cada linha.
- [ ] **Step 2:** `pytest tests/test_inventory.py tests/test_people.py -q` → PASS (as ligações continuam no HTML).
- [ ] **Step 3:** Recompilar o CSS e ver no browser. Fazer o percurso só com o teclado: Tab até «Mais ações», Enter abre, Esc fecha.
- [ ] **Step 4: Commit.** `git commit -m "Listas com uma acao por linha e as outras em Mais acoes"`

### Tarefa D4: Login pensado para o telemóvel

**Files:**
- Modify: `accounts/forms.py:15` (o widget do email passa a `forms.EmailInput` com `autocomplete="username"`, `inputmode="email"`, `autocapitalize="none"` e `spellcheck="false"`)
- Test: `tests/test_auth.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_login_com_campo_de_email(client):
    html = client.get(reverse("accounts:login")).content.decode()
    assert 'type="email"' in html and 'autocomplete="username"' in html
```

- [ ] **Step 2: Correr e ver falhar.** **Step 3: Implementar.** **Step 4: Correr e ver passar.**
- [ ] **Step 5: Commit.** `git commit -m "Login: campo de email com teclado e autocomplete certos"`

### Tarefa D5: Funções e contactos com regra

**Files:**
- Create: `workers/formatos.py` (`normalizar_contacto`)
- Modify: `workers/forms.py` (`clean_job_title` com `capfirst(texto.strip())`, `clean_contact` com `normalizar_contacto`)
- Create: uma migração de dados em `workers/migrations/` (RunPython que aplica as duas regras às fichas que já existem)
- Modify: `templates/manage/workers/lista.html` (contacto com `whitespace-nowrap`)
- Test: `tests/test_ficha_trabalhador.py`

**Interfaces:**
- Produces: `workers.formatos.normalizar_contacto(texto: str) -> str`. Um número português (9 algarismos começados por 2 ou 9, com ou sem `+351` ou `00351`) fica `+351 XXX XXX XXX`. O resto fica como foi escrito, sem espaços nas pontas.

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.mark.parametrize("entrada,saida", [
    ("965852489", "+351 965 852 489"), ("+351911043974", "+351 911 043 974"),
    ("00351 910 161 333", "+351 910 161 333"), ("+44 20 7946 0958", "+44 20 7946 0958"),
    (" ana@mail.pt ", "ana@mail.pt"),
])
def test_normalizar_contacto(entrada, saida):
    assert normalizar_contacto(entrada) == saida
```
Mais um teste do formulário: gravar com a função «copeiro» guarda «Copeiro».

- [ ] **Step 2: Correr e ver falhar.** **Step 3: Implementar, com a migração.** **Step 4: `pytest -q`.**
- [ ] **Step 5: Commit.** `git commit -m "Fichas: funcao com maiuscula e telefones no formato +351"`

### Tarefa D6: Totais vazios como `0h00`

**Files:**
- Modify: `templates/manage/attendance/dia.html:68` (o total vazio mostra `0h00` em `text-ardosia`)
- Test: `tests/test_people.py`

- [ ] **Step 1:** Escrever um teste: o Ponto do dia de uma pessoa sem registos contém `0h00` na coluna «Trabalhado».
- [ ] **Step 2: Correr e ver falhar.** **Step 3: Implementar.** **Step 4: Correr e ver passar.**
- [ ] **Step 5: Commit.** `git commit -m "Ponto do dia: total vazio como 0h00"`

### Tarefa D7: Seletores do ponto fora das views

**Files:**
- Modify: `attendance/selectors.py` (o ficheiro criado na Tarefa C1): passam para lá `overlapping_entries`, `tabela_registos` e `_desvios` (este como `desvios_do_dia`), que hoje estão em `attendance/views.py`
- Modify: `attendance/views.py`, `dashboard/views.py`, `analytics/people_reports.py` (os imports apontam para `attendance.selectors`; os imports dentro de funções sobem para o topo quando não criam ciclos)

- [ ] **Step 1:** Mover as funções sem mudar o que fazem.
- [ ] **Step 2:** `pytest -q` → PASS, com o mesmo número de testes. `ruff check .` limpo.
- [ ] **Step 3: Commit.** `git commit -m "Ponto: consultas partilhadas em attendance/selectors.py"`

### Tarefa D8: Menu por áreas e sub-navegação igual em todo o lado

**Files:**
- Modify: `templates/partials/nav_manage.html` (três grupos com título pequeno: **Pessoas** com Trabalhadores, Ponto, Férias e Turnos; **Stock** com Stock, Compras e Fichas; **Negócio** com Vendas e Análise. Um grupo sem entradas visíveis não aparece)
- Create: `templates/manage/inventory/_nav.html` (pílulas `separadores`: Artigos, Histórico, Contagens, Consumos e Categorias, como em `templates/manage/attendance/_nav.html`)
- Modify: os templates das cinco páginas do stock (os botões do cabeçalho dão lugar ao `_nav.html`; «Novo artigo» fica como a ação principal)
- Test: `tests/test_menu.py`

- [ ] **Step 1:** Escrever o teste: o Resp. stock não vê o título «Pessoas», e o gerente vê os três grupos.
- [ ] **Step 2: Correr e ver falhar.** **Step 3: Implementar.** **Step 4: Correr, recompilar o CSS e ver no browser.**
- [ ] **Step 5: Commit.** `git commit -m "Menu por areas e sub-navegacao do stock em pilulas"`

### Tarefa D9: A Análise abre no último mês com vendas

**Files:**
- Modify: `analytics/views.py:36` (`periodo(request, meses=1, por_omissao=None)`: sem `mes` nem datas no pedido, usa o mês de `por_omissao`; as views passam o mês de `sales.reports.ultimo_dia(request.restaurant)`)
- Test: `tests/test_analise.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_periodo_por_omissao_e_o_ultimo_mes_com_vendas(rf):
    inicio, fim, mes = periodo(rf.get("/gestao/analise/"), por_omissao=datetime.date(2026, 9, 25))
    assert (inicio, fim) == (datetime.date(2026, 9, 1), datetime.date(2026, 9, 30))
```

- [ ] **Step 2: Correr e ver falhar.** **Step 3: Implementar.** **Step 4: `pytest tests/test_analise*.py -q`.**
- [ ] **Step 5: Commit.** `git commit -m "Analise abre no ultimo mes com vendas, como as Vendas"`

---

## Bloco E — Produto, depois do piloto

Cada épico precisa da sua conversa de desenho (superpowers:brainstorming) e do seu plano próprio. Aqui fica o resultado que se quer e a ordem sugerida. Não arrancar nenhum antes de o piloto ter 4 semanas de uso, e reordenar pelo que a Peco pedir.

- [ ] **E1 — Primeiros passos numa casa nova.**
  - Um cartão no dashboard do Admin com uma lista que se marca sozinha a partir dos dados:
    - áreas de trabalho;
    - equipa com códigos;
    - tablet ativado;
    - primeiro horário publicado;
    - NIF e séries do SAF-T;
    - primeiro SAF-T importado;
    - artigos com mínimo.
  - Desaparece quando a lista fica completa.
  - Aceitação: uma casa nova mostra 0 de 7; a casa do `demo` não mostra o cartão.
- [ ] **E2 — Ficha do trabalhador como página** (`/gestao/trabalhadores/<pk>/`).
  - Mostra:
    - o estado de hoje;
    - os próximos turnos;
    - as horas do mês contra as previstas;
    - o saldo de férias e os pedidos;
    - os consumos do mês;
    - o código e a conta;
    - o histórico.
  - As ações de D3 vivem aqui.
- [ ] **E3 — Caixa de pedidos única** (P2 do `plan.md` §10): férias e correções numa lista, decididas na própria linha, com espaço para as trocas de turno quando vierem.
- [ ] **E4 — App do colaborador, segunda versão.**
  - No início: os próximos 3 turnos e o saldo de férias.
  - «Novidades»: pedido aprovado ou recusado, horário publicado. Fica dentro da app, sem push.
  - Barra inferior com Início, Turnos, Férias e Histórico.
- [ ] **E5 — Planeador com números.**
  - Uma linha de totais por dia: pessoas, horas e custo (horas × custo por hora das Regras de vendas).
  - Horas de contrato por semana na ficha, com aviso quando o planeado passa delas.
- [ ] **E6 — Encomenda para o fornecedor.** Página de impressão ou PDF, e um botão WhatsApp (`https://wa.me/<telefone>?text=…`) com as linhas. O email fica para quando houver envio.
- [ ] **E7 — Valor do stock e food cost.**
  - Coluna «Valor» e total na lista do stock (stock × custo de referência).
  - Nas fichas, o food cost acima do alvo da casa (35% por omissão, configurável) aparece a laranja.
- [ ] **E8 — Pesquisa global (Ctrl+K):** trabalhadores, artigos, fichas e fornecedores da casa ativa, por HTMX em `/gestao/procurar/?q=`.
- [ ] **E9 — Tendências na Análise:** vendas por semana, horas por semana e food cost, com o SVG de `core/templatetags/graficos.py`, comparadas com o período anterior.
- [ ] **E10 — Notificações push** (P2 do `plan.md`), só depois do teste em iOS (`todo.md` §4). São elas que permitem as trocas de turno.

**Não fazer agora:**
- ligação direta à API do POS;
- payroll;
- app nativa;
- Tailwind v4;
- SPA;
- tudo o que está em «Não fazer» no `plan.md` §10.

---

## Bloco F — Caminho até ao piloto (fora do código)

Não se repete aqui o que já está no `todo.md`. Este bloco só dá a ordem.

- [ ] **F1 — Escolher o hosting** (`todo.md` §6). Recomendação na secção «Veredicto sobre o stack».
- [ ] **F2 — Escrever `docs/deploy.md` e fazer o primeiro deploy**, depois de A1 a A5. O runbook tem:
  - as variáveis de ambiente;
  - `python manage.py migrate`;
  - `python manage.py createcachetable`;
  - `python manage.py css --minify`;
  - `python manage.py collectstatic --noinput`;
  - `gunicorn config.wsgi --workers 3` atrás do Caddy, com `X-Forwarded-Proto`;
  - `DJANGO_ALLOWED_HOSTS=.opero.pt` e `DJANGO_CSRF_TRUSTED_ORIGINS=https://*.opero.pt`;
  - o `demo` só com `--forcar`, num grupo de demonstração.
- [ ] **F3 — Backups com restauro testado uma vez** (`todo.md` §6): `pg_dump` diário guardado 30 dias noutro sítio, e um restauro numa base vazia com `pytest` a correr contra ela.
- [ ] **F4 — Validação jurídica do registo de tempos** (`todo.md` §2). Bloqueia o piloto.
- [ ] **F5 — Testes em aparelhos reais** (`todo.md` §4), incluindo o A7 no Android.
- [ ] **F6 — SAF-T real da Peco a bater ao cêntimo** (`todo.md` §3).
- [ ] **F7 — Arranque do piloto e as três medidas da secção «Utilidade e potencial»**, revistas ao fim de 4 semanas antes de abrir o bloco E.
