# Opero Rest — Plano de Implementação do MVP

> Backoffice personalizado para restaurantes.
> Fonte: `plano-mvp-clickup-backoffice-restaurantes.docx` (AT — produto; TM — desenvolvimento).
> Este documento é a tradução desse plano para engenharia. Decisões técnicas: TM.

---

## 0. Como usar este documento

**Este ficheiro é o estado do projeto, não só o plano.** Sempre que uma sessão de trabalho executa parte do plano, atualiza-o antes de terminar. É assim que a sessão seguinte — humana ou assistida — sabe onde pegar sem reler o código todo.

### Protocolo de atualização

Ao concluir qualquer trabalho descrito na secção 8:

1. **Marcar as caixas** dos itens efetivamente concluídos e verificados.
2. **Atualizar o `Estado:`** da fase no seu cabeçalho.
3. **Acrescentar uma linha ao Registo de progresso** (secção 14) com a data, o que foi feito e o que ficou por fazer.
4. Se surgir um desvio ao plano — decisão diferente da prevista, ou dependência nova — **escrevê-lo no plano** em vez de o deixar só no código.

### Convenção de marcação

| Marca | Significado |
|---|---|
| `- [ ]` | por fazer |
| `- [~]` | em curso ou parcial — explicar o que falta no Registo de progresso |
| `- [x]` | feito **e verificado** contra o critério de aceitação da fase |

**Só marcar `[x]` depois de verificar.** Uma caixa marcada é uma promessa à sessão seguinte de que aquilo funciona; código escrito mas não testado é `[~]`, não `[x]`.

### Estado por fase

| Fase | Estado |
|---|---|
| 0 — Fundação e sistema de design | ✅ Concluída |
| 1 — Stock, ponta a ponta | 🟡 Em curso |
| 2 — Pessoas | 🟡 Em curso |
| 3 — Vista do colaborador e PWA | 🟡 Em curso |
| 4 — Dashboard, estabilização e piloto | 🟡 Em curso |
| 5 — Ponto e ausências, segunda iteração | 🟡 Código completo; falta revisão visual, teste no telemóvel e aprovação do âmbito pela AT |
| 6 — Planeador de turnos | 🟡 Código completo; falta revisão visual do planeador e aprovação do âmbito pela AT |
| 7 — Quiosque e app do colaborador separados | 🟡 Código completo; falta testar num tablet e num telemóvel reais e a aprovação da AT |
| 8 — Calendário mensal de ausências | 🟡 Código completo e visto no browser; falta a revisão do TM com dados reais |
| 9 — Vários restaurantes | 🟡 Código completo; o trabalhador em várias casas só foi testado pelos testes, não no browser. Falta a aprovação da AT e a confirmação do contabilista sobre a casa principal |
| 10 — Vendas a partir do SAF-T | 🟡 Código completo e visto no browser com dados sintéticos; falta validar com o ficheiro real do cliente de teste e as vendas por serviço |
| 11 — Fornecedores e compras | 🟡 Código completo, testado e visto no browser; falta a aprovação da AT e o uso real com um fornecedor |
| 12 — Consumos internos | 🟡 Código completo, testado e visto no browser; falta o consumo de pratos (Fase 13) e a resposta do contabilista sobre o mapa |
| 13 — Fichas técnicas | 🟡 Código completo, testado e visto no browser (só pelo texto das páginas); falta a revisão visual, a decisão do catálogo de artigos e a aprovação da AT |
| 14 — Stock atualizado pelas vendas | ⬜ Por iniciar |
| 15 — Extração e análise de dados | ⬜ Por iniciar |

Legenda: ⬜ Por iniciar · 🟡 Em curso · ✅ Concluída

---

## 1. Contexto e objetivo

O MVP prova que o produto resolve um problema real num restaurante: **controlo básico e centralizado sobre pessoas, stock e operação diária**, sem depender de folhas de cálculo, cadernos ou ferramentas separadas.

No fim do MVP, um gerente consegue:

- entrar na aplicação com o seu utilizador;
- consultar e gerir trabalhadores;
- registar entrada e saída de trabalhadores;
- registar e aprovar pedidos de férias;
- criar artigos de stock e consultar stock atual e mínimo;
- registar entradas, saídas e ajustes de stock e consultar o histórico;
- dar acessos diferentes a gerente, responsável de stock e colaborador.

**Não é** um ERP, um POS nem software de contabilidade. Lê as vendas do POS a partir do ficheiro SAF-T (Fase 10), mas não fatura nem substitui o POS.

### Mapa do produto

As áreas que o produto tem de cobrir, e onde está cada uma neste plano (pedido do TM a 2026-10-26):

| Área | Onde está | Estado |
|---|---|---|
| Stock e movimentos | Fase 1 | 🟡 código feito; falta a revisão visual |
| Compras e fornecedores | Fase 11 (estava na V1.1) | 🟡 código feito |
| Trabalhadores, ponto e férias | Fases 2, 3, 5, 7 e 8; turnos na Fase 6 | 🟡 código feito; faltam os testes em aparelhos reais |
| Consumos internos | Fase 12 (estava na V1.1) | 🟡 código feito; os pratos esperam pela Fase 13 |
| Fichas técnicas | Fase 13 (estava no Futuro) | 🟡 código feito |
| Vendas do POS | Fase 10, pelo ficheiro SAF-T | 🟡 código feito; falta o ficheiro real |
| Atualização de stock por vendas | Fase 14 (estava no Futuro) | ⬜ |
| Extração e análise de dados | exportação do mês na Fase 5; o resto na Fase 15 | 🟡 parcial |
| Vários restaurantes | Fase 9 | 🟡 código feito; falta ver no browser o trabalhador em várias casas |

### Posicionamento
Os HRIS generalistas, como a Factorial, ganham pela amplitude: payroll, recrutamento, avaliação de desempenho, marketplace de integrações. O Opero Rest não compete aí. Ganha pelo foco no restaurante: stock, ponto e turnos no mesmo sítio, ecrãs pensados para a cozinha e um registo de tempos que serve para a inspeção e para o contabilista sem configuração (estudo em `re-factorial/`, BR-007). Cada funcionalidade nova passa por este filtro: se só faz sentido para uma empresa de escritório, fica de fora.

### Desvio assumido face ao documento de origem

O docx trata a interface como mínima ("navegação simples", dashboard sem gráficos). Este plano eleva deliberadamente o nível de acabamento do frontend, por decisão do TM, porque os utilizadores finais mais frequentes são pessoal de cozinha e sala a usar telemóvel em serviço. Concretamente, acrescenta-se ao âmbito:

| Adição | Estado |
|---|---|
| Sistema de design próprio (secção 4) | Decidido |
| App do colaborador no telemóvel, separada do backoffice, só para consultar e pedir | Decidido |
| PWA instalável | Decidido |
| Ponto picado só no tablet partilhado, com nome e código (Fase 7) | Decidido pelo TM; **a validar com AT** (secção 7) |
| Fases 5 e 6: pausas, fecho do mês, saldo de férias, planeador de turnos | **A validar com AT** (secção 12) |
| Fases 9 a 15: vários restaurantes, vendas pelo SAF-T, compras, consumos internos, fichas técnicas, stock pelas vendas, análise de dados | Pedido do TM; **a validar com AT** (secção 12) |

Tudo o resto neste documento deriva do docx, exceto as Fases 5 e 6 e as Fases 9 a 15. As Fases 5 e 6 vêm do estudo da Factorial (`re-factorial/clone/prd.md`) e incluem duas coisas que o docx deixou fora do MVP: o saldo anual de férias e o planeamento visual de equipa. As Fases 9 a 15 trazem para o plano o que o docx deixava para a V1.1 ou para o futuro (secção 10).

---

## 2. Stack

| Camada | Escolha | Porquê |
|---|---|---|
| Runtime | Python 3.12 | já instalado no `.venv` |
| Framework | Django 5.x | auth, permissões, ORM, migrações e admin resolvidos de origem |
| Interatividade | HTMX + Alpine.js | ações parciais sem SPA; sem Node no sistema |
| CSS | Tailwind CSS **standalone** (`tools/tailwindcss.exe`) | binário único, lê `tailwind.config.js` sem npm |
| BD (dev) | SQLite | zero setup |
| BD (prod) | PostgreSQL | via `dj-database-url` e variável de ambiente |
| Config | `django-environ` | settings por ambiente, segredos fora do código |
| Estáticos (prod) | `whitenoise` | serve estáticos sem depender do proxy |
| Testes | `pytest-django`, `pytest-cov` | |
| Testes com tempo | `time-machine` *(Fase 5)* | fecho do mês, registos por resolver e turnos na noite da mudança de hora dependem do relógio |
| Feriados | cálculo próprio em `vacations/holidays.py` *(Fase 5)* | feriados nacionais portugueses, incluindo os móveis (Sexta-feira Santa, Páscoa, Corpo de Deus); os municipais ficam em `vacations.Holiday` (ver Notas de desvio) |
| XML de fora | `defusedxml` *(Fase 10, instalado)* | o SAF-T vem de outro programa: lê-se em streaming e sem expandir entidades |
| Excel | `openpyxl` *(Fase 15)* | extração de dados em Excel, além do CSV |

### O que as Fases 5 e 6 não acrescentam

- **Sem fila de tarefas** (Celery, Redis, cron). O aviso de mês por fechar e o estado «por resolver» calculam-se quando se lê a página, não por um job agendado. Só as notificações push (P2) podem vir a precisar de um envio em segundo plano.
- **Sem SPA para o planeador.** A grelha semanal é feita com HTMX e Alpine: clicar numa célula e escolher o turno guardado. O arrastar e largar vem depois e, se vier, usa o SortableJS vendored em `static/js/`, sem npm.
- **Sem biblioteca de auditoria** (`django-simple-history`). O histórico de correções é um modelo próprio, porque só existe num sítio e precisa de motivo e autor obrigatórios.
- **Exportação com o módulo `csv` do Python.** O `openpyxl` entra na Fase 15, com a extração de dados em Excel.
- **Notificações push (P2):** `pywebpush` com chaves VAPID, sobre o service worker que já existe. Só depois do teste em iOS (BR-004).

### Cuidados

- **Hora local.** `TIME_ZONE = "Europe/Lisbon"` e `USE_TZ = True`. O `work_date` calcula-se na hora local da entrada, não em UTC, e na noite da mudança de hora um turno tem uma hora a mais ou a menos. Tem de haver um teste para isto.
- **SQLite não serve de prova de concorrência.** O SQLite ignora o `select_for_update()`, e as constraints de sobreposição de turnos (`ExclusionConstraint` com `btree_gist`) só existem em PostgreSQL. As regras ficam nos serviços, e os testes correm também contra PostgreSQL antes do piloto.

**HTMX e Alpine são vendored** em `static/js/`, não carregados de CDN: a PWA precisa de shell offline e a rede de um restaurante não é de confiança.

### Decisões estruturais

- **`AbstractUser` custom desde a primeira migração.** Trocar o modelo de utilizador depois de existirem dados é uma operação dolorosa. Faz-se no dia 1, mesmo que comece sem campos extra.
- **Permissões por Django Groups**, um por perfil, mais mixins de verificação explícita nas views. Não confiar apenas em esconder botões no template.
- **Multi-tenant preparado, não exposto.** Existe `core.Restaurant` e todos os modelos operacionais têm FK `restaurant` desde o início — acrescentar isto mais tarde obriga a migrar dados existentes. Mas o MVP serve **um restaurante por instância**: não há seletor de restaurante na UI nem middleware de tenant. O docx deixa em aberto se cada cliente terá domínio próprio, subdomínio ou área partilhada; esta abordagem não fecha nenhuma dessas portas.

  **A Fase 9 expõe-no:** várias casas por cliente, com a casa ativa em cada pedido (`core/middleware.py`). Os atalhos de casa única saíram: `restaurant_scope()` recebe o pedido e, sem casa ativa, não devolve nada, e já não há `Restaurant.objects.first()` nas views.

---

## 3. Estrutura de ficheiros

```
opero_rest/
  manage.py
  requirements.txt          requirements-dev.txt
  .env.example              .gitignore
  tailwind.config.js
  tools/tailwindcss.exe     # standalone, fora do git

  config/
    settings/{base,dev,prod}.py
    urls.py  wsgi.py  asgi.py

  core/                     # Restaurant, TimeStampedModel, mixins de permissão
  accounts/                 # User, perfis, login email+password, password provisória, dispositivo
  workers/                  # Worker, código de ponto, conta da app
  kiosk/                    # Fase 7: tablet partilhado — nome, código e marcação
  attendance/               # TimeEntry
  vacations/                # VacationRequest (Fase 5: AbsenceType, Allowance, Holiday, BlockedPeriod)
  shifts/                   # Fase 6: ShiftTemplate, Shift, RestDay
  inventory/                # Category, Item, StockMovement
  sales/                    # Fase 10: SAF-T (saft.py lê, services.py grava, reports.py conta)
  purchasing/               # Fase 11: Supplier, SupplierItem, PurchaseOrder, Receipt
  recipes/                  # Fase 13: Recipe, RecipeVersion, RecipeLine, RecipeProduct
  dashboard/                # vista agregada do gerente
  staff/                    # vista do colaborador (mobile)

  templates/
    base_manage.html        base_staff.html        base_kiosk.html
    components/             botao, campo, badge, talao, tabela, modal, toast
    manage/                 um diretório por módulo
    staff/                  inicio, historico, ferias, turnos, correcao
    kiosk/                  nomes, codigo, acoes, confirmacao
    partials/               fragmentos de resposta HTMX

  static/
    src/input.css           # fonte Tailwind
    css/app.css             # gerado, fora do git
    js/htmx.min.js  js/alpine.min.js
    fonts/                  # Archivo, IBM Plex Sans, IBM Plex Mono
    manifest.webmanifest  sw.js  icons/

  tests/
```

`main.py` é scaffold do PyCharm e apaga-se na Fase 0.

---

## 4. Direção de design

Fixada aqui para que a implementação não tome decisões visuais avulsas ecrã a ecrã.

**Desde 2026-10-27, a linguagem visual é a do shot «EMBER — Restaurant Dashboard» (Tajrin Nahar, Dribbble), por decisão do TM.** Substitui a direção «back of house» anterior (aço, carvão, mono), que rejeitava precisamente o creme, a serifa e a terracota. Do EMBER vem a linguagem: cores, tipografia, forma, cartão de perfil, navegação com contadores, estados em pílula, números com ícone tingido e seguimento por passos. Não vêm o nome, o logo, as fotografias nem os textos. O logo do Opero mantém-se, com uma variante de palavra escura para fundos claros (`static/img/logo-opero-escuro.png`).

### Paleta

As cores base estão em `static/src/input.css`. Os tons claros e escuros são **escalas fixas** em `tailwind.config.js` (`neutro-50…900`, `floresta-50…900`, e 50/100/200/700 de `chama`, `perigo`, `alerta`, `servico` e `ambar`). Sobre fundos claros não se usa transparência (`bg-x/10`), porque dá tons diferentes conforme o fundo; usa-se o tom da escala. A transparência fica para as sobreposições do cartão verde e dos fundos de modal.

| Token | Hex | Uso |
|---|---|---|
| `carvao` = `neutro-900` | `#221E18` | tinta: texto principal |
| `floresta` | `#15302B` | preenchimentos: botão primário, item ativo, cartão de perfil |
| `creme` | `#FAF6EB` | fundo das três superfícies; texto sobre `floresta` |
| `neutro-50…800` | `#FDFBF7` … `#36322B` | fundos de cabeçalhos de tabela, pílulas, bordas |
| `linha` | `#ECE5D9` | filetes e divisórias |
| `superficie` | `#FFFFFF` | cartões, tabelas, formulários |
| `chama` | `#C2461B` | **só** a ação principal da página e os contadores |
| `perigo` | `#B42318` | ações irreversíveis, erros, recusado |
| `alerta` | `#B54708` | avisos: stock baixo, registos por resolver, conflitos, linhas sem custo |
| `servico` | `#2E7D4F` | estado «em serviço», aprovado |
| `ambar` | `#E39B2D` | à espera, perfil no cartão verde |
| `ardosia` = `neutro-600` | `#6E675B` | texto secundário (5,2:1 sobre creme) |

Hierarquia de botões: **laranja** (`btn-acento`) só na ação principal da página, no cabeçalho, uma por ecrã; **verde** (`btn-primario`) para gravar e para a ação de cada cartão ou linha; **branco** (`btn-fantasma`) para o resto; **vermelho** (`btn-perigo`) para o que não se desfaz. Estados em pílula: tom 50 de fundo e tom 700 no texto (AA).

### Espaço, forma e elevação

- **Espaçamento:** interior dos cartões 24px (`p-6`), cabeçalho de cartão `px-6 py-4`, linhas de lista e de tabela com 56px, 24px do título ao conteúdo, 32px entre secções. Nas tabelas, 24px na primeira e na última coluna e 20px nas outras.
- **Raios:** três. 12px (`rounded-xl`) nos campos e blocos pequenos, 16px (`rounded-2xl`) nos cartões, modais e moldura, pílula (`rounded-full`) nos botões e estados.
- **Sombras:** três níveis em `tailwind.config.js`: `shadow-cartao` (repouso), `shadow-elevado` (cartão clicável ao passar o rato), `shadow-flutuante` (modais, painéis e menus).
- **Largura:** o conteúdo do backoffice vai até `max-w-7xl`; o calendário e o planeador usam a largura toda.

### Tipografia

Ficheiros variáveis servidos localmente a partir de `static/fonts/`, sem chamadas ao Google Fonts.

| Papel | Face | Onde |
|---|---|---|
| Display | **Playfair Display** (600–800) | **só** o título da página (`titulo-pagina`), os nomes no cartão verde, os títulos dos modais e do quiosque |
| Corpo | **Inter** (400–700) | tudo o resto: `secao-titulo` (18px semibold), `cartao-titulo` (16px semibold), botões |
| Dados | **Inter** com figuras tabulares (`font-dados`) | quantidades, horas, datas, valores; nunca partem de linha nas tabelas |

**Regra transversal: todos os números usam figuras tabulares**, para as colunas alinharem. Um total vazio mostra-se como `0h00`, não como «—».

### Componentes

Em `static/src/input.css` e `templates/components/`; a página `/componentes/` mostra-os todos. Os principais: `.cartao` (branco, 16px), `.cartao-perfil` (verde com o círculo no canto), `.nav-item` e `.contador`, `.separadores` (filtros e sub-navegação em pílula), `.mosaico` (ícone tingido), `.link-acao` (ação de uma linha), `.link-voltar` (migalha), `.aviso`. Ícones de traço em linha com `{% load interface %}{% icone "nome" %}` (`core/templatetags/interface.py`, desenhos do Lucide, ISC), e iniciais nos avatares com `|iniciais`.

### O histórico

O antigo «talão» continua a ser a forma do histórico: uma linha por movimento num cartão branco, com a hora em cima e o autor em baixo, que se acrescenta e nunca se apaga. Perdeu o bloco mono e o filete tracejado.

### Ergonomia

Alvos de toque ≥48px na app e no quiosque. Contraste AA no texto (verificado token a token). A borda dos campos (`neutro-300`) é clara e fica abaixo dos 3:1 do WCAG 1.4.11; o campo distingue-se pelo rótulo, pela sombra interior e pela borda escura ao passar e no foco. É uma troca assumida pelo TM a 2026-10-27. `prefers-reduced-motion` respeitado. Foco de teclado visível (anel verde). Abaixo de `lg`, a coluna do backoffice abre numa gaveta.

### Sala limpa
As funcionalidades inspiradas no estudo da Factorial reconstroem comportamentos e não copiam materiais: nem textos, nem nomes de ecrãs, nem ícones, nem cores. Os termos da Factorial proíbem a engenharia reversa (BR-003). Todo o microcopy é escrito de raiz em português, segundo a secção 9.

---

## 5. Três superfícies

São três produtos sobre o mesmo backend, não um produto com menus condicionais. Desde a Fase 7, **o ponto só se pica no tablet partilhado**, e a app do colaborador serve para consultar e pedir.

| | Quiosque | App do colaborador | Backoffice |
|---|---|---|---|
| Quem | todos os que têm ficha e código, incluindo gerentes e responsáveis de stock | todos os que têm conta | Admin, Gerente, Resp. stock |
| Onde | tablet do restaurante, ativado pelo gerente | telemóvel de cada um | computador ou tablet do gerente |
| Como se entra | nome e código, sem login | email e password, sessão longa | email e password |
| O que faz | entrada, pausa, saída | histórico, turnos, férias, saldo, correções | tudo o resto |
| Sem rede | avisa que nada foi registado | — | — |

### `base_kiosk.html` — quiosque (tablet partilhado)

Fundo creme, cartão verde com o nome, botões grandes, sem navegação. Três passos: **nome → código → ação**.

```
┌─────────────────────────────┐
│  Quem está a picar?         │
│  [Marta Silva] [Rui Gomes]  │   1. um botão por pessoa
│  [João Duarte] [Beatriz N.] │
└─────────────────────────────┘
┌─────────────────────────────┐
│  Marta Silva                │
│  ● ● ● ○                    │   2. teclado numérico no ecrã
│  [1][2][3] … [⌫][0][OK]     │
└─────────────────────────────┘
┌─────────────────────────────┐
│  Olá, Marta                 │
│  Em turno desde 11:58       │   3. só as ações possíveis no estado atual
│  [        SAÍDA        ]    │      fora de turno: ENTRADA (`servico`)
│  [Pausa · Refeição] [Curta] │      em turno: SAÍDA (`chama`) + pausas
└─────────────────────────────┘      em pausa: TERMINAR PAUSA (contorno `aco`)
```

- **Sem sessão.** O quiosque nunca faz login. O código confirma quem está a picar e devolve um token assinado, válido por 60 segundos, que só serve para essa marcação. Ninguém herda o lugar de quem picou antes, e um código nunca abre a app nem o backoffice.
- **Pausas sem passo extra.** Os tipos de pausa ativos aparecem como botões ao lado da Saída. Com um só tipo, o botão diz «Iniciar pausa».
- **Confirmação da entrada.** Fica visível até alguém tocar «OK», ou no máximo 15 segundos. Mostra a hora da entrada, a saída prevista pelo turno publicado do dia (ou «Sem turno previsto hoje»), e os esquecimentos: a saída anterior que esta entrada acabou de pôr de lado e quantos registos estão por resolver. Todos levam à mesma indicação: «Peça a correção na app», ou «Fale com o gerente para corrigir» a quem não tem conta.
- **Confirmação da saída e das pausas.** Informação mínima, o nome, a ação e a hora, durante 5 segundos ou até tocar «OK».
- **Entrada aberta há pouco.** Quando há uma entrada aberta que ainda não passou do limite, o ecrã de ações diz desde quando («Em turno desde 24/10 às 19:02»). Se já passou meia hora do fim do turno previsto (ou 10 horas, sem turno), avisa que provavelmente ficou uma saída por picar: pique a saída, depois a entrada, e peça a correção da hora.
- **Sem rede, nada fica registado,** e o ecrã diz isso claramente. Não há fila offline. O gerente acrescenta o registo depois, com motivo (registo manual da Fase 2).

### `base_staff.html` — app do colaborador

Mobile-first, fundo creme, coluna única, cartão verde com o estado do dia no topo. **Não tem botão de ponto.** O ecrã inicial mostra o estado do dia, só para leitura (em turno desde, em pausa, fora de turno, turno previsto de hoje), os totais do dia e da semana, os avisos de registos por resolver com ligação para o pedido de correção, e três entradas: Turnos, Histórico (onde se pedem as correções) e Férias.

```
┌───────────────────┐
│  Olá, Marta       │
│  09:14 · Terça    │
│                   │
│  Em turno · 08:58 │   estado do dia, só leitura
│  Turno 09–16 Sala │
│                   │
│  Hoje     5h16    │   mono, tabular
│  Semana   32h10   │
│                   │
│  [Turnos]         │
│  [Histórico]      │
│  [Férias]         │
└───────────────────┘
```

Entra-se com email e password. A sessão dura o defeito do Django (14 dias), por isso a password raramente se escreve. A conta é criada pelo admin ou pelo gerente com uma password provisória, que o colaborador muda no primeiro login (secção 7). Continua a ser uma PWA instalável (`start_url` `/equipa/`), e o service worker guarda só a casca e as últimas páginas vistas.

### `base_manage.html` — backoffice

Desktop-first, funcional em tablet. A aplicação numa folha creme sobre fundo areia, com cabeçalho (logo, casa, conta) e uma coluna à esquerda: o cartão de perfil e o cartão de navegação, com contadores do que está por tratar. A entrada Férias abre o calendário mensal da Fase 8. As áreas do docx:

`Dashboard · Trabalhadores · Ponto · Férias · Stock · Configuração`

Depois do MVP juntaram-se Grupo (Fase 9, só o Admin do grupo), Turnos (Fase 6), Compras (Fase 11, com o stock) e Vendas (Fase 10, Admin e Gerente).

Conteúdo denso, tabelas com pesquisa e filtros, figuras mono alinhadas à direita, histórico sempre a um clique de distância de qualquer ação que altere stock, ponto ou férias.

---

## 6. Modelo de dados

### `core`

**`Restaurant`** — `name`, `slug`, `is_active`, timestamps.
**`TimeStampedModel`** (abstract) — `created_at`, `updated_at`. Base de tudo o resto.

### `accounts`

**`User(AbstractUser)`** — `email` como `USERNAME_FIELD`, `restaurant` (FK), `role` (choices: `ADMIN`, `MANAGER`, `STOCK`, `STAFF`), `must_change_password` *(Fase 7)*. Até à Fase 7 guardava também o PIN (`staff_pin`, `pin_set_at`), que passou para o `Worker`.

### `workers`

**`Worker`** — `restaurant` (FK, a casa principal), `other_restaurants` (M2M, as outras casas do grupo onde pica e tem turnos, *Fase 9*), `full_name`, `contact`, `job_title`, `is_active`, `user` (OneToOne, nullable), `start_date` (nullable), `notes`, `kiosk_code` (hash, nullable) e `code_set_at` *(Fase 7)*.

O código de ponto pertence à ficha e não à conta: quem não tem email pica no tablet na mesma, só não tem app. Ter conta é opcional; para picar, é preciso ter código.

Sem documentos laborais, contratos, recibos ou cálculo salarial — excluídos pelo docx.

### `inventory`

**`Category`** — `restaurant` (FK), `name`. Sementes: bebidas, mercearia, frescos, limpeza, embalagem.

**`Item`** — `restaurant` (FK), `name`, `category` (FK), `unit` (choices: `UN`, `KG`, `L`, `CX`, `EMB`), `current_stock` (Decimal 12,3), `minimum_stock` (Decimal 12,3), `reference_cost` (Decimal, nullable), `is_active`, `notes`.

**`StockMovement`** — `item` (FK), `movement_type` (`ENTRADA`, `SAIDA`, `AJUSTE_POS`, `AJUSTE_NEG`), `quantity` (Decimal, sempre positiva), `occurred_at`, `created_by` (FK User), `reason`, `reference` (nullable).

| Tipo | Quando | Efeito |
|---|---|---|
| Entrada | receção de mercadoria, compra, devolução | aumenta |
| Saída | consumo manual, quebra, desperdício | diminui |
| Ajuste positivo | contagem física superior ao registado | aumenta |
| Ajuste negativo | contagem física inferior ao registado | diminui |

Fora do MVP, por decisão do docx: lotes, datas de validade, múltiplos armazéns, conversão de unidades, preço médio ponderado, fichas técnicas.

### `attendance`

**`TimeEntry`** — `worker` (FK), `check_in`, `check_out` (nullable), `corrected_by` (FK User, nullable), `correction_reason`, `corrected_at`.

### `vacations`

**`VacationRequest`** — `worker` (FK), `start_date`, `end_date`, `status` (`PENDENTE`, `APROVADO`, `RECUSADO`, `CANCELADO`), `request_note`, `decided_by` (FK User, nullable), `decided_at`, `decision_note`.

Fora do MVP: contagem automática de saldo anual, integração com payroll, regras laborais, substituições, planeamento visual de equipa. As Fases 5 e 6 propõem trazer o saldo anual e o planeamento para depois do MVP, e as alterações ao modelo de dados estão descritas nessas fases.

### Depois do MVP

As Fases 9 a 15 acrescentam o grupo e o acesso por casa (`core.Organization`, `accounts.Membership`), as vendas (app `sales`), as compras (app `purchasing`), os consumos internos (em `inventory`) e as fichas técnicas (app `recipes`). Os modelos estão descritos em cada fase. A invariante 1 mantém-se: compras, consumos, transferências e vendas mexem no stock só através do `register_movement()`.

### Invariantes — implementar e testar

Estas regras são o núcleo do sistema. Cada uma tem um teste dedicado na secção 11.

1. **O stock nunca é editado diretamente no artigo.** `Item.current_stock` só muda através de um `StockMovement`, num serviço `inventory/services.py::register_movement()` dentro de `transaction.atomic()` com `select_for_update()` sobre o item. Nenhuma view escreve `current_stock`.
2. **Movimentos não se apagam.** Sem delete na UI nem no admin. Correções fazem-se com novos movimentos de ajuste, preservando o histórico.
3. **Um trabalhador não pode ter dois turnos abertos.** `UniqueConstraint` parcial (`worker`, `check_out__isnull=True`) mais validação no serviço.
4. **Não há saída sem entrada prévia.** Marcar saída sem turno aberto é rejeitado com mensagem clara.
5. **Cada registo guarda data, hora e utilizador.** Ponto, movimentos e decisões de férias.
6. **Pedidos de férias aprovados não se apagam.** E o sistema avisa visualmente quando um pedido se sobrepõe a outro já aprovado do mesmo trabalhador. Um pedido já decidido não volta a ser decidido (`decide_request()` só aceita pedidos pendentes): se um pedido foi recusado, o colaborador faz um pedido novo.
7. **Uma correção nunca apaga o valor anterior.** O histórico de correções (`attendance.EntryCorrection`) guarda o antes e o depois, com autor, motivo e data. *(Fase 5)*
8. **Um mês aprovado não muda** sem que seja reaberto de forma explícita e auditada. *(Fase 5)*
9. **Um registo por resolver não conta para os totais.** *(Fase 5)*

10. **O colaborador nunca vê um turno em rascunho nem um turno em reserva.** *(Fase 6)*

---

## 7. Perfis, permissões e autenticação

### Matriz de acesso

| Ação | Admin | Gerente | Resp. stock | Colaborador |
|---|:--:|:--:|:--:|:--:|
| Criar utilizadores, atribuir perfis | ✓ | | | |
| Criar contas da app e repor a password, para Colaborador e Resp. stock *(Fase 7)* | ✓ | ✓ | | |
| Definir e repor o código de ponto *(Fase 7)* | ✓ | ✓ | | |
| Configurações do restaurante | ✓ | | | |
| Gerir trabalhadores | ✓ | ✓ | | |
| Consultar ponto da equipa | ✓ | ✓ | | |
| Corrigir registo de ponto (auditado) | ✓ | ✓ | | |
| Aprovar / recusar férias | ✓ | ✓ | | |
| Criar e editar artigos | ✓ | ✓ ⚠ | ✓ | |
| Registar movimentos de stock | ✓ | ✓ ⚠ | ✓ | |
| Consultar stock, alertas e histórico | ✓ | ✓ | ✓ | |
| Marcar o próprio ponto (só no tablet, desde a Fase 7) | ✓ | ✓ | ✓ | ✓ |
| Ver o próprio histórico | ✓ | ✓ | ✓ | ✓ |
| Submeter pedido de férias | ✓ | ✓ | ✓ | ✓ |
| *Fases 5 e 6* | | | | |
| Configurar áreas, tipos de pausa e de ausência, feriados, períodos bloqueados | ✓ | | | |
| Pedir correção do próprio registo | ✓ | ✓ | ✓ | ✓ |
| Decidir pedidos de correção, aprovar e reabrir o mês, exportar | ✓ | ✓ | | |
| Registar ausência em nome de um trabalhador (fica aprovada) | ✓ | ✓ | | |
| Planear e publicar turnos | ✓ | ✓ | | |
| Ver os próprios turnos publicados | ✓ | ✓ | ✓ | ✓ |
| *Fases 9 a 15* | | | | |
| Criar e editar casas, dar e tirar acessos, painel do grupo | só o Admin do grupo | | | |
| Transferir stock entre casas | ✓ | ✓ | ✓ | |
| Importar o SAF-T e ver as vendas | ✓ | ✓ | | |
| Fornecedores, encomendas e receções | ✓ | ✓ ⚠ | ✓ | |
| Registar consumos internos | ✓ | ✓ | ✓ | |
| Ver os próprios consumos | ✓ | ✓ | ✓ | ✓ |
| Criar e editar fichas técnicas | ✓ | ✓ | ✓ | |
| Relatórios e extração de stock e compras | ✓ | ✓ | ✓ | |
| Relatórios e extração de vendas e de pessoas | ✓ | ✓ | | |

Na Fase 9, o perfil passa a ser por casa: a mesma pessoa pode ser gerente numa casa e não ter acesso a outra. Acima dos quatro perfis fica o **Admin do grupo**, que vê e configura todas as casas do mesmo cliente e é o único a ver as casas lado a lado.

Regras que decorrem do docx:

- O colaborador não vê férias, horários nem consumos de outros colaboradores.
- O colaborador não edita artigos nem altera stock.
- O responsável de stock não gere permissões de utilizadores.
- Nenhum utilizador comum apaga movimentos de stock.
- O número de administradores deve ser reduzido.

Regra do estudo da Factorial: os perfis continuam fixos. Não há grupos de permissões configuráveis nem interruptores por funcionalidade, porque num restaurante quem decide é o gerente e um único nível de aprovação chega (secção 10, «Não fazer»).

⚠ **Decisão a validar com AT** (sinalizada no próprio docx): se o gerente também pode criar artigos e registar movimentos, ou se isso é exclusivo do responsável de stock. **Pressuposto atual: pode.** É mais permissivo, e restringir depois é uma linha de código; alargar depois obriga a repensar fluxos.

### Autenticação e código de ponto (desde a Fase 7)

| Caminho | Quem | Dá acesso a |
|---|---|---|
| Email + password | Admin, Gerente, Resp. stock | backoffice, e a própria app |
| Email + password | Colaborador | **apenas** a app do colaborador |
| Nome + código no tablet | qualquer trabalhador com código | **apenas** uma marcação; não cria sessão |

Fronteira de segurança explícita: **um código de ponto nunca abre uma sessão**, nem na app nem no backoffice, mesmo que o titular seja gerente. O quiosque não faz login: o código serve para uma marcação e mais nada.

**Código de ponto.** De 4 a 6 algarismos, guardado no `Worker` com o hasher de passwords do Django. É definido e reposto pelo gerente. Ao fim de 5 falhas seguidas, o código desse trabalhador fica bloqueado durante 60 segundos. O ecrã de nomes só abre num navegador ativado pelo gerente como dispositivo do restaurante (cookie assinado, 180 dias, com a área de trabalho). Já não há o modo «telemóvel pessoal»: um cookie antigo desse modo deixa de dar acesso ao quiosque.

**Contas da app.** São criadas pelo admin ou pelo gerente a partir da ficha do trabalhador. O sistema gera uma password provisória, que só se mostra uma vez, e o colaborador é obrigado a mudá-la no primeiro login (`must_change_password`). Esquecer a password resolve-se da mesma maneira: o gerente gera uma nova provisória. Não há recuperação por email, porque o envio de emails ainda não está configurado (secção 12).

O gerente só cria e gere contas com os perfis Colaborador e Responsável de stock. Contas de Gerente e de Admin só o admin as gere, porque o número de administradores deve ser reduzido. Ninguém muda o próprio perfil nem repõe a própria password neste ecrã.

⚠ **Decisão a validar com AT.** O docx exclui geolocalização, QR code, biometria e relógio físico, mas não se pronuncia sobre um código de marcação. Racional: obrigar pessoal de cozinha a escrever email e password em serviço torna o registo de ponto inutilizável. Picar só no tablet do restaurante dá credibilidade ao registo, porque ninguém marca a entrada a caminho do trabalho, e o código só dá acesso a uma marcação.

---

## 8. Fases de implementação

Ciclos curtos de uma semana, com revisão semanal AT + TM. Estimativas técnicas a confirmar por TM antes de fechar cada sprint.

### Fase 0 — Fundação e sistema de design
*Corresponde a P0-10 e P0-11. Depende de: P0-01 a P0-05 (AT).*
**Estado:** ✅ Concluída

- [x] `git init`, `.gitignore`, dependências, apagar `main.py`.
- [x] Projeto Django, settings por ambiente, `.env.example`.
- [x] `core.Restaurant`, `TimeStampedModel`, `accounts.User` custom — **primeira migração**.
- [x] Groups por perfil e mixins de permissão em `core/mixins.py`.
- [x] Login por email e password, logout, redirecionamento por perfil.
- [x] Tailwind standalone em watch; tokens de cor e tipo em `input.css`; fontes locais.
- [x] `base_manage.html`, `base_staff.html` e a biblioteca `components/` completa — botão, campo, badge, talão, tabela, modal, toast.

**Construir os componentes antes dos ecrãs.** É o que impede a deriva visual módulo a módulo, e é a razão pela qual o sistema de design entra na Fase 0 e não no fim.

*Aceitação:* um utilizador entra, vê o shell correto para o seu perfil, e a página de componentes mostra todos os elementos nos seus estados.

---

### Fase 1 — Stock, ponta a ponta
*P0-16, P0-17, P0-18. Depende de: Fase 0, P0-03, P0-04, P0-05 (AT).*
**Estado:** 🟡 Em curso

Módulo central e primeiro a ser construído, por decisão explícita do docx: é a necessidade declarada inegociável e dá valor direto ao gerente e ao responsável de stock.

- [x] CRUD de categorias e artigos.
- [x] `register_movement()` com a invariante 1 garantida por transação e lock.
- [x] Registo de movimento via HTMX, sem recarregar a listagem.
- [x] Listagem com pesquisa, filtro por categoria e filtro **"Stock baixo"**.
- [x] Badge `chama` no artigo com `current_stock <= minimum_stock`; contador no topo do módulo.
- [x] Histórico de movimentos em talões, com filtro por artigo e por período.

Alertas são visuais. Sem email, SMS ou notificações nesta fase.

*Aceitação (docx):* um responsável de stock cria um artigo, regista uma entrada ou saída, e confirma que o stock atual foi atualizado e que o movimento ficou guardado no histórico.

---

### Fase 2 — Pessoas
*P0-13, P0-14, P0-15. Depende de: Fase 0, P0-02, P0-08, P0-09 (AT).*
**Estado:** 🟡 Em curso

- [x] CRUD de trabalhadores, com associação opcional a um `User`.
- [x] Ponto no backoffice: vista da equipa por dia, identificação de entradas ou saídas em falta, correção de registo com autor e motivo obrigatórios.
- [x] Férias: lista de pendentes, aprovar ou recusar com observação, histórico por trabalhador, aviso visual de sobreposição com pedidos aprovados.

*Aceitação (docx):* um colaborador regista entrada e saída no mesmo dia e o gerente consulta esse registo no histórico da equipa. Um colaborador pede férias e recebe uma decisão do gerente, ficando todo o processo em histórico.

---

### Fase 3 — Vista do colaborador e PWA
*Fora do docx — requisito do TM. Depende de: Fase 2.*
**Estado:** 🟡 Em curso

> **A Fase 7 substitui parte desta fase:** o login por PIN, o botão de ponto no telemóvel, a fila offline e o modo quiosque com sessão. Os itens ficam abaixo como histórico. Desta fase continuam em vigor o histórico próprio, o pedido de férias e a PWA.

- [x] Login por PIN e ecrã de seleção de trabalhador no dispositivo do restaurante.
- [x] Ecrã de ponto com o botão de estado descrito na secção 5.
- [x] Histórico próprio em talões; totais do dia e da semana em mono.
- [x] Pedido de férias em três campos: início, fim, observação.
- [~] `manifest.webmanifest`, ícones, service worker com o shell em cache.
- [~] Marcações feitas offline entram em fila e sincronizam ao voltar a rede — com o timestamp do momento da marcação, não do envio.
- [~] Falhas de sincronização visíveis: cada marcação da fila mostra o estado, «por enviar» ou «recusada», e o envio aparece num toast. Uma marcação recusada mostra o motivo que o servidor devolveu (JSON 409) até o colaborador a dispensar. A marcação guarda a ação que o botão mostrava (`acao`), e por isso nunca é aplicada ao contrário. Também guarda quem marcou (`trabalhador`), e por isso só sincroniza na sessão dessa pessoa. *Falta verificar num browser real.*
- [~] Modo quiosque no tablet partilhado: o dispositivo ativado é marcado como partilhado ou pessoal. No partilhado, a sessão PIN termina logo a seguir a cada marcação, e o ecrã de PIN mostra o nome, a ação e a hora (secção 5). No pessoal, a sessão mantém-se. *Falta verificar num tablet real.*

*Aceitação:* um colaborador instala a aplicação no telemóvel, entra com PIN e marca entrada e saída em **menos de 5 segundos e 2 toques**, sem formação prévia.

---

### Fase 4 — Dashboard, estabilização e piloto
*P0-19, P0-22, P0-23. Depende de: Fases 1 a 3, P0-20 e P0-21 (AT).*
**Estado:** 🟡 Em curso

- [x] Dashboard do gerente, sem gráficos sofisticados: contador de artigos com stock baixo, últimos movimentos, pedidos de férias pendentes, quem está em turno.
- [ ] Correção de bugs P0 e P1 encontrados nos testes funcionais do AT.
- [ ] Ambiente de demonstração: domínio, hosting, HTTPS, backups, utilizadores de teste. *(bloqueado pelas decisões de hosting/domínio da secção 12)*
- [x] Fixtures de dados de exemplo para demonstração e para o percurso dos quatro perfis. *(`python manage.py demo`, idempotente)*
- [ ] Validação jurídica do registo de tempos antes do piloto (BR-001, secção 12): conteúdo mínimo do registo, prazo de conservação, mapa de horário de trabalho e o que uma inspeção da ACT pede para ver. O piloto não arranca sem esta resposta.
- [ ] Testar a PWA nos telemóveis reais do piloto, em iOS e Android, incluindo as limitações de notificações push e de localização no iOS (BR-004). Decide se as trocas de turno (P2) podem depender de push.
- [ ] Documentação RGPD mínima para vender: acordo de tratamento de dados (DPA) com o restaurante, lista de subcontratantes e alojamento na UE (BR-006). Não é preciso certificação no MVP.

---

### Fase 5 — Ponto e ausências, segunda iteração
*Fora do docx. Vem do estudo da Factorial (`re-factorial/clone/prd.md`, prioridade P1). Depende de: Fases 2 e 3, de a AT aprovar o âmbito e da validação jurídica do registo de tempos (secção 12).*
**Estado:** 🟡 Código completo e testado, incluindo o critério de aceitação (`tests/test_fecho_mes.py::test_aceitacao_fase_5`). O TM arrancou-a a 2026-10-24 sem esperar pela aprovação da AT (ver Notas de desvio). Falta a revisão visual e o teste no telemóvel.

O MVP regista entradas e saídas. Esta fase dá ao gerente o que precisa para fechar o mês e prová-lo ao contabilista ou a uma inspeção. A ordem dos blocos é a de construção: cada um assenta no anterior.

**Modelo de dados e persistência**

- [x] `core.WorkArea` (`restaurant`, `name`, `archived_at`): cozinha, sala, bar. O dispositivo do restaurante passa a estar associado a uma área, e cada marcação herda a área do dispositivo onde foi feita.
- [x] `TimeEntry.work_date`: o dia de trabalho é o dia da entrada, e um turno das 19h às 2h conta todo no dia em que começou. Uma data migration preenche o campo a partir de `check_in`. Hoje os totais da vista staff já seguem esta regra (`staff/views.py::_totais`), mas a vista da equipa (`TeamDayView`) mostra o mesmo turno nos dois dias. As duas passam a agrupar por `work_date`.
- [x] `TimeEntry.work_area` e `TimeEntry.source` (quiosque, telemóvel, gerente).
- [x] Pausas: `attendance.BreakType` (`name`, `paid`, `archived_at`) e `attendance.Break` (`entry`, `start`, `end`, `break_type`). As pausas não pagas não contam para os totais. Na primeira versão as pausas são marcadas à mão; as pausas automáticas ficam para depois. Só se inicia uma pausa com a entrada marcada, e só pode haver uma pausa aberta de cada vez (R-004). Os tipos de pausa arquivam-se em vez de se apagarem, porque as pausas já registadas apontam para eles (R-006). Fechar o turno com uma pausa aberta fecha também a pausa.
- [x] Histórico de correções: hoje `correct_entry()` escreve por cima do registo e o valor anterior perde-se. Cada correção passa a guardar os valores antigos e os novos, com autor, motivo e data. Os campos `corrected_by`, `correction_reason` e `corrected_at` do `TimeEntry` passam a ser derivados da última correção, e uma data migration cria uma linha de histórico para cada correção já feita. Na vista da equipa, o histórico de correções de um registo aparece em talões (secção 4).

**Ecrãs do ciclo principal**

- [~] Ecrã de ponto do colaborador com pausa: em turno, o ecrã mostra «Iniciar pausa» e «Saída»; em pausa, mostra «Terminar pausa». Continua a ser um único botão de estado principal (secção 5), e cumpre a aceitação da Fase 3 (5 segundos, 2 toques). *Feito e testado no servidor, incluindo pausas da fila offline. Falta ver no telemóvel e decidir se o estado «em pausa» (contorno `aco`, sem cor) se lê bem. Desde a Fase 7, este ecrã está no tablet partilhado e não no telemóvel.*
- [x] Pedido de correção pelo colaborador (`attendance.CorrectionRequest`: `entry`, `kind` com criar, alterar ou apagar, valores antigos e novos, `status`, `decided_by`). O gerente aprova ou recusa, e a decisão fica registada no histórico de correções.
- [x] Registos por resolver: uma entrada sem saída que passe de um limite fixo (valor a decidir, por exemplo 14 horas) fica pendente e não conta para os totais até ser resolvida (R-013). O colaborador vê o aviso no ecrã de ponto e pode propor a hora de saída com um pedido de correção. O gerente vê o número de registos por resolver no dashboard. Na Fase 6 este limite passa a vir das horas previstas no turno.

**Ausências**

- [x] Tipos de ausência (`vacations.AbsenceType`: `name`, `color`, `deducts_balance`, `requires_approval`, `requires_attachment`, `half_days`). `VacationRequest` ganha `absence_type`, `half_day` e `days_taken`. As férias passam a ser um tipo entre outros: falta justificada, baixa, licença parental, formação. Os tipos de origem vêm na data migration, e os tipos já usados arquivam-se em vez de se apagarem. Um tipo que não exige aprovação fica aprovado logo que é pedido (R-051).
- [x] Regras do ciclo de vida do pedido:
  - Um pedido registado pelo gerente em nome de um trabalhador nasce aprovado e fica com o gerente como decisor (R-057). Isto substitui o desvio de 2026-09-04, em que esse pedido nascia pendente.
  - O colaborador pode cancelar um pedido pendente ou um pedido aprovado ainda no futuro. Usa-se o estado `CANCELADO`, que já existe no modelo mas não tem nenhum fluxo que o use. Pedidos com datas passadas o colaborador já não cancela (R-056).
  - Um pedido recusado não volta a aprovado, e a decisão chega ao colaborador com a observação do gerente (R-055, já garantido por `decide_request()`).
- [x] Saldo anual (`vacations.Allowance`: `worker`, `year`, `days`, `carried_over`, `carry_over_expires_on`). O saldo aparece no pedido e na decisão. O valor por defeito português (22 dias úteis) está por validar (secção 12).
  - Os dias só se descontam quando o pedido é aprovado (R-053). Os dias transitados do ano anterior gastam-se primeiro e caducam na data definida (R-066).
  - Um pedido que exceda o saldo disponível mostra um aviso a `chama` ao gerente, mas não é bloqueado: em Portugal a decisão é do gerente.
  - Ficam de fora a proporcionalidade, os escalões de antiguidade e os contadores alternativos, salvo se a validação jurídica disser o contrário (Q-008).
- [x] Feriados (`vacations.Holiday`: `restaurant`, nulo para os nacionais, `date`, `name`, `half_day`). Os feriados nacionais vêm de origem, os municipais são acrescentados por restaurante, e o cálculo de `days_taken` não conta feriados nem folgas.
  - Até haver planeador (Fase 6), `days_taken` conta os dias úteis, de segunda a sexta, sem os feriados. A partir da Fase 6, os dias sem turno planeado e as folgas também deixam de contar (R-037, R-067).
  - Num restaurante as folgas raramente calham ao fim de semana. A regra legal para quem trabalha ao sábado e ao domingo está por confirmar (Q-001).
- [x] Períodos bloqueados (`vacations.BlockedPeriod`: `restaurant`, `start`, `end`, `absence_types`, `exempt_workers`). Um pedido que caia num período bloqueado é recusado na submissão, com uma mensagem que diz porquê. Os períodos bloqueados aparecem no formulário de pedido antes de o colaborador escolher as datas (R-060).

**Fecho do mês**

- [x] `attendance.MonthClose` (`restaurant`, `month`, `worker`, `approved_by`, `approved_at`). O gerente aprova o mês por trabalhador, e só o pode fazer quando não restam registos por resolver nem pedidos de correção pendentes. Se faltar resolver alguma coisa, a aprovação é recusada com uma mensagem que diz quantos trabalhadores e quantos registos faltam, e com uma ligação para eles (R-016). Também se pode aprovar de uma vez todos os trabalhadores que estão prontos.
- [x] Aviso no dashboard: a partir do dia 1, «O mês anterior está por fechar», com o número de trabalhadores por aprovar. Não há email, de acordo com a regra da Fase 1 sobre alertas.
- [x] Depois de aprovado, um mês fica bloqueado: não aceita correções, registos manuais nem pedidos de correção. Para reabrir, é preciso uma ação explícita, auditada e com motivo.
- [x] Exportação do mês aprovado (CSV na primeira versão), num formato a acordar com o contabilista (secção 12). Conteúdo mínimo provisório: uma linha por trabalhador e por dia de trabalho, com entrada, saída, pausas não pagas, horas trabalhadas, área e ausência com o seu tipo. No fim vêm os totais do mês por trabalhador. É isto que substitui a integração com payroll (BR-005).

*Invariantes novas: 7, 8 e 9, já na secção 6.*

*Aceitação:* um colaborador marca entrada, uma pausa não paga e saída num turno que passa a meia-noite. O gerente vê o turno num só dia, com a pausa descontada. O colaborador pede uma correção, que o gerente aprova, e o valor anterior fica no histórico. Por fim, o gerente aprova o mês e exporta-o, e a partir daí o mês recusa alterações.

---

### Fase 6 — Planeador de turnos
*Fora do docx. Vem do estudo da Factorial (prioridade P1). Depende de: Fase 5 (áreas de trabalho, tipos de ausência) e de a AT aprovar o âmbito.*
**Estado:** 🟡 Código completo e testado, incluindo o critério de aceitação (`tests/test_turnos.py::test_aceitacao_fase_6`). Falta ver o planeador num browser: ainda ninguém o viu.

Módulo novo, numa app `shifts`. É o primeiro passo do ciclo semanal do gerente: planear e publicar a semana, e depois comparar o planeado com o realizado.

- [x] `shifts.ShiftTemplate` (`restaurant`, `name`, `start`, `end`, `work_area`, `color`): turnos guardados, como «Almoço», «Jantar», «Fecho» ou «Dobra». Um restaurante tem entre 3 e 6. Arquivam-se em vez de se apagarem.
- [x] `shifts.Shift` (`worker`, `start_at`, `end_at`, `work_area`, `state` com rascunho, publicado ou reserva, `template`). A grelha semanal é organizada por trabalhador e pode ser filtrada por área. Os turnos da noite usam o mesmo `work_date` do ponto, isto é, contam no dia em que começam.
- [x] Criar turnos em lote: aplicar um turno guardado a vários trabalhadores e a vários dias de uma vez (R-034).
- [x] Copiar a semana anterior, com os turnos e as folgas. O que é copiado nasce em rascunho (R-038).
- [x] Folgas (`shifts.RestDay`: `worker`, `date`, `state`). Uma folga não desconta dias de férias (R-037).
- [x] Ausências no planeador:
  - Uma ausência pendente aparece riscada e não conta como conflito.
  - Quando se aprova uma ausência de dia inteiro, o turno desse dia passa a «reserva», que só o gerente vê. Assim o gerente fica a saber que tem um buraco no planeamento (R-033).
  - Se a ausência for cancelada, o turno volta a rascunho.
- [x] Conflitos a `chama`, que impedem a publicação (R-032):
  - dois turnos sobrepostos para a mesma pessoa;
  - um turno num dia de ausência aprovada ou de folga;
  - menos de 11 horas de descanso entre o fim de um turno e o início do seguinte. O valor está por confirmar (Q-001), e é aqui que o Opero Rest faz melhor do que a Factorial, que só aplica esta regra no plano Enterprise.
- [x] Publicar a semana: o colaborador só vê os turnos publicados (R-030). Antes de publicar, o gerente vê o que mudou desde a última publicação e quem é afetado. Um turno publicado pode voltar a rascunho com uma ação explícita, e editá-lo exige nova publicação. Ao contrário da Factorial, que não deixa despublicar (B-007), aqui pode-se. Na primeira versão não há push nem email: o colaborador vê a mudança da próxima vez que abre a aplicação.
- [~] A vista staff ganha «Os meus turnos», um quarto elemento além dos três que a secção 5 previa, o que é uma alteração a validar visualmente.
- [x] Planeado contra realizado: as horas previstas no turno substituem o limite fixo dos registos por resolver da Fase 5. Na vista da equipa, cada registo aparece ao lado do turno previsto, e um atraso ou uma saída fora do previsto ficam assinalados.
- [ ] Na marcação de saída, quando o colaborador já passou bastante da hora prevista, o ecrã pergunta se a saída é agora ou se foi à hora prevista e esqueceu de marcar (R-012). Fica a decidir se isto entra.

*Invariante nova: 10, já na secção 6.*

*Aceitação:* o gerente copia a semana anterior, ajusta dois turnos a partir dos turnos guardados, marca uma folga e vê um conflito com férias aprovadas. Depois de o resolver, publica a semana, e o colaborador vê os seus turnos no telemóvel.

---

### Fase 7 — Quiosque e app do colaborador separados
*Decisão do TM a 2026-10-25. Substitui o login por PIN, o botão de ponto no telemóvel, a fila offline e o modo quiosque da Fase 3. Depende de: Fases 3, 5 e 6.*
**Estado:** 🟡 Código completo e testado, incluindo a aceitação passo a passo nos testes de `tests/test_staff.py` e `tests/test_contas.py`. O quiosque foi visto num browser de secretária. Falta um tablet real, a app num telemóvel real e a aprovação da AT.

O ponto passa a ser picado só no tablet partilhado, com nome e código, e a vista do colaborador passa a ser uma app de consulta e pedidos, com email e password (secções 5 e 7).

**Modelo e dados**

- [x] `Worker.kiosk_code` e `Worker.code_set_at`. Uma data migration copia para a ficha os PINs que estavam no `User`, e depois `User.staff_pin` e `User.pin_set_at` são removidos.
- [x] `User.must_change_password`.

**Quiosque (app `kiosk`, em `/quiosque/`)**

- [x] Ecrã de nomes: só num dispositivo ativado, só com trabalhadores ativos e com código, do restaurante do dispositivo.
- [x] Ecrã do código com teclado numérico no ecrã. Bloqueio do código de um trabalhador durante 60 segundos ao fim de 5 falhas.
- [x] Ecrã de ações com as ações possíveis no estado atual, e as pausas como botões ao lado da Saída. Mostra desde quando há uma entrada aberta.
- [x] Marcação com um token assinado de 60 segundos, de uso único, sem login. A origem é «tablet partilhado» e a área vem do dispositivo.
- [x] Confirmação da entrada: saída prevista ou «Sem turno previsto hoje», a saída esquecida que a entrada pôs de lado, os registos por resolver e «Pede a correção na app». Fica até «OK» ou 15 segundos. As outras confirmações são mínimas e duram 5 segundos.
- [~] Sem rede, o ecrã diz que nada foi registado. *Visto no browser com uma resposta de erro do servidor (405). O caso sem rede usa o mesmo aviso (`htmx:send-error`), mas ainda não foi visto com o tablet desligado da rede.*
- [x] Ativação do dispositivo sem modo pessoal. Um cookie antigo em modo pessoal deixa de abrir o quiosque.

**App do colaborador**

- [x] Entrada com email e password (`/conta/entrar/`); `/equipa/` sem sessão leva ao login.
- [x] Ecrã inicial sem botão de ponto, com o estado do dia só para leitura, o turno previsto de hoje, os totais, os registos por resolver e a navegação.
- [x] Remover o `MarkView`, o login por PIN, a fila offline do `app.js` e as sessões PIN (`PIN_SESSION_KEY`, `KIOSK_SESSION_KEY`). Cache do service worker para v5.

**Contas e códigos no backoffice**

- [x] Ficha do trabalhador → «Código de ponto»: definir ou repor, sem exigir conta.
- [x] Ficha do trabalhador → «Conta da app»: criar a conta com email e perfil, gerar uma password provisória (mostrada uma vez), repor a password e mudar o perfil. O gerente só gere contas de Colaborador e Resp. stock; o admin gere todas.
- [x] Mudança obrigatória da password provisória no primeiro login, em qualquer das superfícies.
- [x] `manage.py demo` com códigos para a Marta, o Rui e o gerente, e o gerente com ficha. Uma conta que já tenha ficha fica com ela.

*Aceitação:* o gerente cria a ficha da Marta, define o código e cria a conta da app. No tablet, a Marta escolhe o nome, escreve o código e pica a entrada, e vê a saída prevista. Depois inicia e termina uma pausa e pica a saída, sem que ninguém fique com sessão aberta no tablet. No telemóvel, entra com a password provisória, é obrigada a mudá-la e vê o turno do dia e os totais, sem botão de ponto. O gerente também pica no tablet com o seu código, e o código não lhe abre o backoffice.

---

### Fase 8 — Calendário mensal de ausências
*Pedido do TM a 2026-10-25. Depende de: Fases 5 e 6.*
**Estado:** 🟡 Código completo e testado (`tests/test_calendario_ferias.py`), visto no browser com os dados do `demo`. Falta a revisão do TM com dados reais.

Na área Férias, o gerente vê o mês inteiro de toda a equipa e marca ausências como marca os turnos: clica numa célula e abre um painel.

- [x] `/gestao/ferias/calendario/?mes=AAAA-MM` passa a ser a entrada «Férias» do menu lateral. Tem uma linha por trabalhador ativo e uma coluna por dia, e a navegação entre meses. A lista de pedidos e os saldos ficam a um clique.
- [x] Ausências aprovadas a cheio, na cor do tipo, com as duas primeiras letras do tipo (ou ½ num meio dia). Pendentes só com contorno tracejado. Uma aprovada tapa uma pendente no mesmo dia.
- [x] Fins de semana e feriados sombreados; períodos bloqueados com um filete no cabeçalho; o dia de hoje destacado. Por baixo, quantas pessoas estão fora em cada dia (só as aprovadas). À direita, o saldo de férias disponível no ano.
- [x] Painel da célula, por cima da grelha, à direita, para o mês inteiro caber num portátil:
  - mostra as ausências desse dia, com o tipo, as datas, os dias e o decisor;
  - **marcar ausência** a partir do dia clicado, com o tipo, o início, o fim, o meio dia e uma observação. Fica logo aprovada (R-057), e os turnos desse dia passam a reserva;
  - **aprovar ou recusar** um pedido pendente, com uma observação opcional;
  - **cancelar** uma ausência aprovada que ainda não acabou, com confirmação. Não apaga nada (invariante 6): o pedido fica cancelado, com autor e data, e os turnos em reserva voltam a rascunho.
- [x] `VacationRequest.cancelled_by`: quem cancelou, o colaborador ou o gerente.

*Aceitação:* o gerente abre Férias e vê o mês com as ausências de todos. Clica na célula de um trabalhador, marca cinco dias de férias e vê-os no calendário, com o saldo descontado e a contagem de quem está fora. Aprova um pedido pendente no mesmo ecrã e cancela uma ausência marcada por engano.

---

### Roteiro depois do MVP (Fases 9 a 15)
*Pedido do TM a 2026-10-26. O cliente de teste já consegue extrair o ficheiro SAF-T do POS (Zone Soft). Âmbito e ordem a aprovar pela AT (secção 12).*

A ordem tem uma razão:
1. **Vários restaurantes primeiro**, porque mexe em todos os módulos. Cada fase seguinte já nasce a funcionar com várias casas, em vez de ser corrigida depois.
2. **As vendas logo a seguir**, porque o ficheiro já existe e a leitura não depende de mais nada.
3. **Compras, consumos e fichas técnicas** preparam o abate de stock pelas vendas, que precisa das três.
4. **A análise fecha**, porque cruza tudo.

Cada fase traz a sua exportação em CSV. A Fase 15 junta as análises que cruzam módulos e casas.

### Fase 9 — Vários restaurantes
*Depende de: Fases 0 a 8.*
**Estado:** 🟡 Código completo e testado (`tests/test_varias_casas.py`, `tests/test_trabalhador_varias_casas.py`). O primeiro bloco foi visto no browser com o `demo`; o trabalhador em várias casas ainda não. Falta a aprovação da AT.

O mesmo cliente gere várias casas na mesma conta. Cada pessoa vê só as casas a que tem acesso. O Admin do grupo vê todas.

- [x] `core.Organization` (no ecrã, «Grupo») é o cliente.
  - `Restaurant` ganha `organization`, `nif` (validado com o dígito de controlo), `address` e `municipality`. As séries de faturação entram com a Fase 10, que é quem as usa.
  - A data migration (`core/0003`) cria um grupo por restaurante existente. Uma casa criada sem grupo fica sozinha num grupo novo.
- [~] `accounts.Membership` tem os campos `user`, `restaurant` e `role`: o perfil passa a ser por casa.
  - Feito: o Admin do grupo é `User.is_group_admin` com `User.organization`, e tem o perfil de Administrador em todas as casas ativas do grupo. Os mixins leem `request.role`, o perfil na casa ativa. A data migration (`accounts/0004`) dá a cada conta o acesso à casa que tinha; um superuser sem casa passa a Admin do grupo quando há um só grupo.
  - Por fazer: `User.restaurant` e `User.role` continuam como casa e perfil por omissão, e um signal mantém a linha de acesso dessa casa igual a eles. Os Django Groups seguem o perfil por omissão, não o de cada casa; hoje só servem o admin do Django.
- [x] Casa ativa na sessão.
  - Há um seletor no rail do backoffice para quem tem mais de uma casa, e o nome da casa está sempre à vista.
  - Cada página leva a casa em que foi aberta: `X-Opero-Casa` nos pedidos HTMX e `_casa` nos formulários (`static/js/casa.js`). Um POST de outra casa é recusado antes de gravar, com «Mudou para … noutro separador».
  - Quem entra com uma casa de colaborador e tem backoffice noutra entra pela casa do backoffice.
- [x] Isolamento num só sítio: `core.middleware.ActiveRestaurantMiddleware` põe `request.restaurant` e `request.role`, e todas as views filtram com `restaurant_scope(request, …)`.
  - Saíram o «sem restaurante vê tudo» de `restaurant_scope()` e os seis `user.restaurant or Restaurant.objects.first()`.
  - Um objeto de outra casa dá 404, mesmo com o pk certo. Uma conta sem casa recebe 403 no backoffice.
- [x] O tablet do quiosque só mostra os trabalhadores da casa onde foi ativado. Um cookie antigo sem casa deixa de abrir o quiosque, em vez de mostrar a equipa de todas.
- [x] Grupo → Casas e acessos, para o Admin do grupo: criar e editar casas (as sementes de áreas, categorias e tipos de ausência correm na casa nova) e dar, mudar ou tirar o acesso de cada conta a cada casa (`accounts/services.py`). O perfil de uma conta nova começa em Colaborador.
- [~] Separação entre o que é de cada casa e o que é do grupo:
  - são de cada casa, como já eram: o stock, os trabalhadores, o ponto, os turnos, as áreas, os feriados municipais, os períodos bloqueados e o fecho do mês. As vendas serão (Fase 10);
  - serão do grupo: os fornecedores (Fase 11) e as fichas técnicas (Fase 13);
  - o catálogo de artigos é de cada casa (decidido a 2026-10-27, secção 12). As fichas e os fornecedores ligam-se aos artigos de cada casa pelo nome e pela unidade, como já fazem;
  - os tipos de ausência e de pausa ficam por decidir. Até lá, continuam por casa.
- [x] `StockMovement` ganha `origin` (manual ou transferência; as fases seguintes juntam compra, consumo interno e venda) e `transfer`, a ligação à transferência que o gerou. O histórico assinala as transferências.
- [x] Transferência de stock entre duas casas do grupo (`inventory/services.py::transfer_stock()`, modelo `StockTransfer`): uma saída numa e uma entrada na outra, na mesma transação, com a referência `TRF-n`.
  - Os dois artigos têm de ter a mesma unidade, porque não há conversão.
  - Se a casa de destino não tem o artigo, o ecrã cria-o lá, com o mesmo nome, unidade e categoria.
  - Não é preciso ter acesso à casa de destino: é uma entrega à casa irmã.
- [x] Painel do grupo (Grupo → Painel), com uma linha por casa: stock baixo, em turno, por resolver, férias e correções pendentes e mês por aprovar. «Abrir» muda a casa ativa. As vendas entram com a Fase 10.
- [~] Trabalhador em mais de uma casa, com uma casa principal (decidido a 2026-10-27, secção 12). Feito e testado; falta vê-lo no browser.
  - `Worker.restaurant` é a casa principal, a entidade empregadora: a ficha, o código de ponto, a conta, as férias, o saldo e o fecho do mês. `Worker.other_restaurants` são as outras casas do grupo onde a pessoa pica e tem turnos. Escolhem-se na ficha, em «Também trabalha em», que só aparece num grupo com mais de uma casa.
  - `Worker.objects.in_restaurant(casa)` e `core.utils.workers_scope(request, …)` dão quem trabalha na casa: os da casa e os que vêm de outra. `restaurant_scope` continua a dar só os da casa principal, para a ficha, as férias e o fecho do mês.
  - `TimeEntry.restaurant` é a casa onde se picou, e `CorrectionRequest.restaurant` a casa que decide (migração `attendance/0007`; os registos antigos ficaram na casa principal). O ponto do dia, os pedidos, os contadores, o dashboard, o painel do grupo e as vendas por hora trabalhada contam pela casa do registo.
  - Quiosque: o tablet mostra também quem vem de outra casa, e a entrada fica na casa do tablet. Uma entrada aberta noutra casa não se fecha aqui: o ecrã avisa, e picar a entrada deixa a outra por resolver, como uma saída esquecida.
  - Turnos: cada casa planeia os seus. Os conflitos (sobreposição, as 11 h de descanso e a folga) contam os turnos e as folgas da pessoa em todas as casas, e dizem onde está o outro turno. O planeador mostra os turnos publicados de outra casa só para consulta.
  - Ponto do dia: quem vem de outra casa aparece só nos dias em que cá picou ou tinha turno, com «de …». Na app, o pedido de um registo que falta pergunta a casa, e os turnos e o histórico dizem onde foram.
  - Fecho do mês: só na casa principal, com as horas de todas as casas. Um registo por resolver noutra casa impede a aprovação. O CSV ganhou a coluna «Casa».
  - Consumos: quem vem de outra casa consome aqui, e o limite de refeições é o desta casa. O mapa do mês continua por casa (ver Notas de desvio).

*Aceitação:* um grupo com duas casas.
- A gerente da casa A não vê nada da casa B, nem mudando o URL.
- O dono vê as duas no painel do grupo e transfere 5 kg de arroz da A para a B. Os dois históricos mostram o movimento, e o tablet da B só tem a equipa da B.

### Fase 10 — Vendas a partir do SAF-T
*Depende de: Fase 9 (NIF e séries da casa).*
**Estado:** 🟡 Código completo, testado (`tests/test_vendas.py`, 28 testes) e visto no browser com o `demo`, que importa um SAF-T sintético em cada casa. Faltam o ficheiro real do cliente de teste e as vendas por serviço.

O gerente carrega o ficheiro SAF-T (PT) de faturação que o POS exporta, e o Opero Rest passa a saber o que se vendeu, quando e por quanto.
- **Só leitura:** não mexe no stock (isso é a Fase 14) e não emite nem altera documentos fiscais.
- **Qualquer POS:** funciona com qualquer POS certificado pela AT, e não só com a Zone Soft.
- **A API da Zone Soft fica para depois:** não tem documentação pública, e o acesso faz-se pelo revendedor (secção 10).

- [x] Vendas → Importar, para o Admin e o Gerente (`sales/views.py::ImportView`).
  - Aceita o XML do SAF-T (PT) 1.04_01, também dentro de um .zip com um só XML.
  - O ficheiro lê-se em streaming (`iterparse`) com `defusedxml`, porque um mês pode ter dezenas de MB e o XML vem de outro programa (`sales/saft.py`). Recusa DTDs e entidades. Cada documento larga-se depois de lido: um ficheiro de 30 MB (seis meses, 13 mil documentos) lê-se em 4 segundos.
  - Limites: 100 MB no carregamento e 300 MB de XML depois de descomprimido.
- [x] Antes de gravar, valida-se:
  - o NIF do cabeçalho (`TaxRegistrationNumber`) tem de ser o da casa. Um ficheiro de outra empresa é recusado, e a mensagem mostra o NIF que trazia. Uma casa sem NIF não importa;
  - a versão (`AuditFileVersion` 1.04) e o período (`StartDate`, `EndDate`);
  - o programa que o gerou (`ProductID`, `SoftwareCertificateNumber`), que fica guardado para referência;
  - que há `SalesInvoices`: um SAF-T de contabilidade é recusado.
  - Os totais de controlo (`TotalDebit`, `TotalCredit`) comparam-se com as linhas lidas. Se não batem, a importação fica assinalada, mas não é recusada (ver Notas de desvio).
- [x] Documentos:
  - contam só os de `SalesInvoices` (FT, FS, FR, NC, ND);
  - ignoram-se `WorkingDocuments` (consultas de mesa) e `Payments`, para a mesma venda não contar duas vezes;
  - os anulados (`InvoiceStatus` A) não contam, e os já faturados noutro documento (F) também não;
  - as notas de crédito abatem: os totais e as linhas ficam com sinal negativo.
- [x] Várias casas com o mesmo NIF distinguem-se pela série dos documentos (secção 12). Cada casa indica as suas séries nas regras de vendas. Se outra casa tem o mesmo NIF e esta não tem séries, a importação é recusada, para as vendas não contarem nas duas. Os documentos de outras séries contam-se e mostram-se na importação.
- [x] A hora da venda é o `SystemEntryDate`. Dá as vendas por hora.
- [x] O dia de serviço tem uma hora de corte por casa (5h por omissão, entre 0 e 11). Assim, um jantar que fecha à 1h conta no dia em que começou. Calcula-se na hora local do ficheiro.
- [x] Modelo (`sales/models.py`):
  - `SalesImport`: casa, período, hash do ficheiro, programa, quem e quando, e as contagens (novos, com estado alterado, já importados, de outras séries);
  - `SalesDocument`: casa, número (`InvoiceNo`, único por casa), série, tipo, estado, data e hora, dia de serviço, totais sem e com IVA, `SourceID`;
  - `SalesLine`: produto e descrição, quantidade, unidade, preço unitário, valor sem IVA e taxa de IVA;
  - `PosProduct`: código do POS, descrição, família (`ProductGroup`), último preço, por casa. Vem de `MasterFiles/Product`;
  - `SalesSettings`, por casa: hora de corte, séries e custo médio por hora (Vendas → Regras, só o Admin; também em Configuração).
- [x] Importar o mesmo período duas vezes não duplica nada, porque os documentos se identificam pelo número.
  - O mesmo ficheiro (o mesmo hash, com ou sem .zip) é recusado com «Este ficheiro já foi importado a … Nada mudou».
  - Um ficheiro que se sobrepõe a outro já importado só acrescenta os documentos novos.
  - Também atualiza o estado dos que mudaram, como uma fatura anulada depois.
- [x] Dados pessoais:
  - do cliente final (`MasterFiles/Customer` e os dados do cliente nos documentos) não se guarda nada: nem se leem;
  - o ficheiro original também não fica guardado: guarda-se só o hash, para reconhecer um ficheiro repetido.
- [x] Ecrã Vendas (`templates/manage/sales/vendas.html`):
  - vendas por dia (com barra), por hora (mapa da semana a começar na hora de corte), por produto (os 20 primeiros) e por família;
  - total sem IVA, número de documentos e ticket médio;
  - comparação com o período anterior. Um período que ainda não está todo importado, como o mês corrente, compara-se só com os mesmos dias do anterior;
  - por mês, com setas, ou por um intervalo de datas.
- [~] Vendas ao lado do ponto: vendas por hora trabalhada, por dia e por serviço. Na semana em planeamento, usam-se as horas previstas nos turnos.
  - Feito: por dia e no total do período. As horas são as do ponto, sem pausas não pagas nem registos por resolver; num dia sem ponto, as dos turnos publicados, assinaladas «prev.».
  - Feito: o custo médio por hora opcional dá o custo de pessoal estimado em percentagem das vendas. Não há salários, porque o docx exclui o cálculo salarial.
  - Por fazer: por serviço (almoço e jantar). Falta decidir como se define um serviço: pelas horas, ou pelos turnos guardados.
- [x] O dashboard avisa quando o último dia importado tem mais de 7 dias, e leva a Importar. O painel do grupo tem as vendas do mês de cada casa e o último dia importado.
- [x] Exportação CSV das vendas por dia (com as horas) e por produto, com `;`, BOM e vírgula decimal, como a do mês.
- [ ] Validar com um ficheiro real do cliente de teste, sem o pôr no repositório. Nos testes e no `demo` usa-se um SAF-T sintético (`sales/sintetico.py`). Confirmar com o cliente:
  - se o POS exporta um período à escolha (um dia, uma semana) ou só o mês;
  - como numera as séries;
  - se os totais de controlo batem (o aviso da importação) e se o total do mês bate com o relatório do POS;
  - se usa o estado F e em que documentos.

*Aceitação:* o gerente carrega o SAF-T de um mês do cliente de teste.
- O total do mês sem IVA é igual, ao cêntimo, ao do relatório do POS.
- Aparecem as vendas por hora, os produtos mais vendidos e as vendas por hora trabalhada de cada dia.
- Carregar o mesmo ficheiro outra vez não muda nada.

### Fase 11 — Fornecedores e compras
*Estava na V1.1. Depende de: Fase 9 (os fornecedores são do grupo).*
**Estado:** 🟡 Código completo, testado (`tests/test_compras.py`, 21 testes, com o critério de aceitação) e visto no browser com o `demo`. Falta a aprovação da AT e o uso com um fornecedor real.

App `purchasing`, em Compras no rail, para o Admin, o Gerente e o Responsável de stock. Tem quatro separadores: Lista de compras, Encomendas, Receções e Fornecedores.

- [x] `Supplier`, do grupo: nome (único no grupo), NIF, pessoa de contacto, telefone, email, dias de entrega, observações e ativo. Um fornecedor com encomendas ou receções arquiva-se; sem histórico, apaga-se.
- [x] Artigos por fornecedor (`SupplierItem`), geridos na página do fornecedor: a referência do fornecedor, o último preço e qual é o fornecedor preferido. Um só preferido por artigo (constraint parcial): marcar outro tira a marca ao anterior. A unidade de compra é a unidade do artigo, porque a conversão de unidades continua fora (docx). O fornecedor é do grupo, mas os artigos que se lhe ligam são os da casa ativa.
- [x] Lista de compras: os artigos ativos no mínimo ou abaixo dele (o mesmo critério do «Stock baixo»), agrupados pelo fornecedor preferido. A quantidade sugerida repõe o mínimo e desconta o que já está encomendado e ainda não chegou, e pode ser alterada. Os artigos sem preferido aparecem no fim, com a escolha do fornecedor. Cada grupo cria o rascunho de uma encomenda.
- [x] Encomenda, com linhas (`PurchaseOrder`, `PurchaseOrderLine`, referência `ENC-n`). Estados: rascunho, enviada, recebida em parte, recebida e cancelada.
  - Em rascunho, as linhas, a entrega pretendida e as observações mudam-se; o preço previsto vem do último preço do fornecedor.
  - Enquanto não houver envio de emails (secção 12), a encomenda imprime-se (folha sem o rail) ou copia-se como texto («- 3 kg · Alface frisada») para mandar por email ou WhatsApp. «Marcar como enviada» é o passo seguinte.
  - Cancela-se em rascunho ou enviada. Uma recebida em parte não se cancela (ver Notas de desvio).
- [x] Receção (`Receipt`, `ReceiptLine`, referência `REC-n`):
  - confirma-se, linha a linha, o que chegou e a que preço, com o número e a data da fatura ou da guia, que é obrigatória e não pode ser no futuro;
  - cada linha recebida gera uma `ENTRADA`, de origem compra (`StockMovement.Origin.COMPRA`, migração `inventory/0003`), pelo `register_movement()`, com a referência «ENC-n · número do documento» (invariantes 1 e 5). O histórico do stock assinala «compra»;
  - tudo numa transação: ou entra a receção inteira, ou nada;
  - uma receção não se apaga (nem na UI nem no admin, e as linhas protegem-na); um erro corrige-se com um ajuste;
  - há também receção sem encomenda, para quando o fornecedor aparece sem aviso: oito linhas com artigo, quantidade e preço;
  - pede-se uma confirmação antes de registar, porque mexe no stock (secção 9).
- [x] O preço da última receção passa a ser o `reference_cost` do artigo e o último preço do fornecedor. Uma linha sem preço não mexe no custo. O preço médio ponderado continua fora.
- [x] Histórico de preços por artigo e fornecedor: «Preços» na lista do stock, com os fornecedores do artigo e as receções.
- [x] Exportação das compras por fornecedor e por mês: Receções mostra o mês (pela data da fatura ou guia) com o total por fornecedor, e exporta as linhas em CSV (`;`, BOM, vírgula decimal).

*Aceitação:* o responsável de stock abre a lista de compras e faz a encomenda ao fornecedor de frescos. Recebe-a com uma linha a menos.
- O stock e o custo dos artigos mudam.
- A encomenda fica «recebida em parte».

### Fase 12 — Consumos internos
*Estava na V1.1. Depende de: Fase 9. Os consumos de pratos dependem da Fase 13.*
**Estado:** 🟡 Código completo, testado (`tests/test_consumos.py`, 13 testes, com o critério de aceitação) e visto no browser com o `demo`. Faltam o consumo de pratos, que depende das fichas técnicas, e a resposta do contabilista sobre o mapa.

Em `inventory` (`models.py`, `consumption.py`, `consumption_views.py`), em Stock → Consumos.

- [~] Registo de um consumo interno (`InternalConsumption`, com linhas `ConsumptionLine`, referência `CI-n`):
  - quem consumiu: um trabalhador da casa, ou a casa, para ofertas, provas e o dono. Uma refeição do pessoal é sempre de um trabalhador;
  - o quê: um ou mais artigos, até seis por registo. **Por fazer:** o prato com ficha técnica, depois da Fase 13;
  - a quantidade, o dia (não no futuro), o motivo (refeição do pessoal, oferta, prova, dono) e uma observação.
  - Cada linha gera uma `SAIDA`, de origem consumo interno (`StockMovement.Origin.CONSUMO`, migração `inventory/0004`), pelo `register_movement()`. Tudo numa transação.
- [x] Quem regista: o Admin, o Gerente e o Responsável de stock. O colaborador vê os seus consumos na app («Os meus consumos», por mês, com o valor) e nunca vê os dos outros (regra do docx, secção 7).
- [x] Valor ao custo de referência do momento. Fica guardado na linha e não se recalcula quando o custo muda. Um artigo sem custo sai do stock na mesma e fica «sem custo» no mapa.
- [x] Limite opcional de refeições por turno, para toda a casa (`ConsumptionSettings`, em Configuração, só o Admin). Os turnos do dia são os registos de ponto ou, sem ponto, os turnos publicados. Passar o limite não bloqueia: o consumo fica assinalado e o gerente vê um aviso que diz porquê.
- [x] Mapa mensal por pessoa (refeições, outros consumos, valor ao custo), com a exportação em CSV para o contabilista: uma linha por artigo e os totais de cada pessoa. O tratamento das refeições em espécie fica por confirmar com ele (secção 12).
- [x] Um consumo não se apaga. Anula-se, com motivo: uma `ENTRADA` da mesma origem repõe o stock, e o consumo deixa de contar no mapa (ver Notas de desvio).

*Aceitação:* o gerente regista o consumo de dois trabalhadores, um café e uma água cada.
- O stock desce.
- Cada um vê o seu consumo na app.
- O mapa do mês mostra o valor por pessoa.

### Fase 13 — Fichas técnicas
*Estava no Futuro. Depende de: Fase 9 (as fichas são do grupo). A ligação ao POS depende da Fase 10.*
**Estado:** 🟡 Código completo, testado (`tests/test_fichas.py`, 28 testes, com o critério de aceitação) e visto no browser com o `demo`, só pelo texto das páginas: as capturas de ecrã falharam. Faltam a revisão visual, a decisão do catálogo de artigos (secção 12) e a aprovação da AT.

App `recipes`, em Fichas no rail, para o Admin, o Gerente e o Responsável de stock. Dois separadores: Fichas e Produtos do POS sem ficha.

- [x] `Recipe`, do grupo: nome (único no grupo), tipo (prato, bebida ou preparação), preço de venda de referência sem IVA e ativa. Uma ficha arquiva-se e não se apaga. Uma preparação que entra numa ficha ativa não se arquiva, e uma preparação usada noutra ficha não muda de tipo.
- [x] Linhas (`RecipeLine`): o artigo e a quantidade limpa, na unidade do artigo (sem conversão de unidades), com uma percentagem de quebra opcional. A quantidade bruta, que sai do stock, é a limpa a dividir por (1 − quebra): com 20 %, 200 g limpos gastam 250 g. O número de doses e as notas de preparação são da versão.
  - As quantidades são as da receita inteira, que dá o número de doses. Num prato é uma dose; num molho podem ser dez (ver Notas de desvio).
  - **O artigo guarda-se pelo nome e pela unidade**, porque as fichas são do grupo e os artigos ainda são de cada casa (ver Notas de desvio). Em cada casa, a linha liga-se ao artigo com o mesmo nome, sem contar maiúsculas, e a mesma unidade. Se um artigo muda de nome e nenhuma outra casa tem o nome antigo, as fichas passam ao nome novo (`recipes/signals.py`).
- [x] Preparações usadas noutras fichas, como um molho, com a quantidade em doses da preparação. Só um nível: uma preparação leva só artigos. Uma ficha não entra nela própria, e só as preparações entram noutras fichas.
- [x] Custo por dose, a partir do `reference_cost` atual dos artigos da casa ativa, e food cost face ao preço de venda sem IVA.
  - O preço é o do produto do POS ligado nesta casa, vendido mais recentemente. Sem ele, conta o preço de referência da ficha, assinalado «ref.».
  - Uma linha sem artigo nesta casa, com outra unidade ou sem custo fica assinalada. O custo passa a ser um mínimo («≥») e o food cost não se mostra. Sem nenhuma linha com custo, aparece «—».
- [x] Ligação ao POS (`RecipeProduct`):
  - cada ficha liga a um ou mais produtos do POS (`PosProduct`) de cada casa. Um produto tem no máximo uma ficha. Uma preparação ou uma ficha arquivada não se ligam;
  - a lista dos produtos do POS sem ficha ordena-se pelas vendas sem IVA dos últimos 90 dias (só os documentos que contam) e diz que parte das vendas está sem ficha. Em cada produto, «Ligar a…» uma ficha que já existe, ou «Criar ficha», que traz o nome do produto e o liga ao guardar. O valor das vendas só aparece ao Admin e ao Gerente; o Resp. stock vê as quantidades e o peso.
- [x] Versões (`RecipeVersion`): guardar uma receita diferente cria uma versão nova, com a data a partir da qual vale (hoje, por omissão). Não pode começar antes da última. Se nada mudou na receita, não se cria versão. As versões antigas não se mudam (nem no admin). `Recipe.version_on(dia)` dá a versão em vigor num dia, para o consumo de um dia passado (Fase 14), e o custo pode calcular-se para esse dia.
- [x] Ficha imprimível para a cozinha, sem preços, por dose e para N doses, com as quantidades limpa e bruta.
- [ ] O consumo de pratos na Fase 12 (registar um prato com ficha, que sai do stock artigo a artigo).
- [ ] Fora desta fase: os alergénios e a informação nutricional (secção 10).

*Aceitação:* o gerente cria a ficha do «Bitoque» (bife, ovo, batata e arroz) e liga-a ao código do POS. Depois vê o custo por dose e o food cost face ao preço de venda que vem do SAF-T.
- Feito em `test_fichas.py::TestAceitacao`, pelos ecrãs, com um SAF-T importado: 2,67 € por dose e 29,9 % de food cost a 8,94 €.

### Fase 14 — Stock atualizado pelas vendas
*Estava no Futuro. Depende de: Fases 10 e 13.*
**Estado:** ⬜ Por iniciar.

- [ ] Ao importar as vendas, cada linha com ficha técnica dá um consumo teórico.
  - Por casa, por dia de serviço e por artigo, gera-se uma `SAIDA` de origem venda, pelo `register_movement()`, com a referência da importação.
  - É um movimento por artigo e por dia, e não um por linha de venda, que seriam milhares por mês.
- [ ] Um dia já aplicado não se aplica duas vezes.
  - Se uma importação nova muda as vendas de um dia já aplicado (uma fatura anulada, uma nota de crédito), a diferença entra como um movimento novo.
  - O movimento antigo nunca se edita (invariante 2).
- [ ] Stock negativo: hoje o `register_movement()` recusa-o, mas uma venda que já aconteceu não se pode recusar. Ver a decisão na secção 12. Proposta:
  - os movimentos de origem venda podem levar o stock abaixo de zero;
  - o artigo fica assinalado «stock negativo, contar»;
  - a contagem seguinte corrige com um ajuste.
- [ ] Os produtos vendidos sem ficha não mexem no stock. Aparecem numa lista, com o seu peso nas vendas, para o gerente criar a ficha.
- [ ] Teórico contra real: entre duas contagens físicas de um artigo, compara-se o consumo esperado com a diferença real, em quantidade e em valor.
  - O consumo esperado vem das vendas, dos consumos internos e das quebras registadas.
  - É o relatório que mostra o desperdício, as porções mal servidas e as fichas erradas.
- [ ] Liga-se e desliga-se por casa, porque uma casa pode querer só ver as vendas.

*Aceitação:* importa-se um dia com 40 bitoques.
- O stock de bife desce 40 × 180 g, num só movimento com a referência da importação.
- Voltar a importar o mesmo ficheiro não mexe no stock.
- Uma nota de crédito de 2 bitoques, importada depois, devolve 360 g.

### Fase 15 — Extração e análise de dados
*Depende de: as fases cujos dados analisa. Pode avançar por partes, à medida que cada uma fica pronta.*
**Estado:** ⬜ Por iniciar. Já existe a exportação CSV do mês aprovado (Fase 5).

- [ ] Exportação de todas as listas, com os mesmos filtros do ecrã, em CSV (`;` e BOM, como a do mês) e em Excel (`openpyxl`). As listas são: artigos e stock, movimentos, ponto, ausências, turnos, compras, consumos e vendas.
- [ ] Relatórios de stock (vinham da V1.1): artigos mais movimentados, histórico de ajustes e valor do stock por categoria e por casa.
- [ ] Relatórios de pessoas: presenças e ausências por mês, horas por área, atrasos e faltas de marcação face aos turnos.
- [ ] Relatórios de compras: por fornecedor, por artigo e evolução dos preços.
- [ ] Relatórios de vendas e margem: vendas por produto com o food cost teórico, margem por prato, vendas por hora trabalhada e custo de pessoal estimado em percentagem das vendas.
- [ ] Comparação entre casas, só para o Admin do grupo.
- [ ] Gráficos simples, de barras e de linhas, em SVG gerado no servidor. Sem biblioteca de BI e sem Node.
- [ ] Em todos os relatórios escolhem-se o período e a casa. As datas são na hora local, e os totais batem com os ecrãs de cada módulo.
- [ ] Acesso conforme a matriz da secção 7. Os relatórios com dados de pessoas ficam só para o Admin e o Gerente.
- [ ] Agregados diários das vendas, calculados na importação. Assim, os relatórios não somam meses inteiros de linhas a cada pedido.
- [ ] Fora desta fase: BI externo, previsões e relatórios financeiros (secção 10).

*Aceitação:* o dono do grupo abre «Análise», escolhe outubro e as duas casas.
- Vê, lado a lado, as vendas, as horas trabalhadas, as vendas por hora trabalhada, o food cost teórico e os consumos internos.
- Exporta a tabela para Excel, e os totais batem com os de cada módulo.

---

## 9. Estados e feedback

Regra transversal, aplicada em todos os ecrãs das três superfícies.

- **Toast de confirmação** em todas as ações de escrita, com o mesmo verbo do botão que a despoletou: "Registar entrada" → "Entrada registada".
- **Indicador de loading** (`hx-indicator`) em todas as ações HTMX; botão desativado durante o pedido, para eliminar duplos submits.
- **Ecrãs vazios com instrução e a ação seguinte.** Nunca "sem dados": "Ainda não há artigos. Comece por criar o primeiro."
- **Erros em português simples**, que dizem o que falhou e como resolver. Não pedem desculpa, não são vagos.
- **Confirmação explícita** antes de ações irreversíveis: ajuste de stock, recusa de férias, correção de ponto.
- Uma ação principal clara por ecrã. Formulários curtos. Listagens sempre com pesquisa.
- **Quando uma ação é recusada por haver coisas por resolver, a mensagem diz quantas são e leva até elas.** Por exemplo, «Faltam 3 registos de 2 trabalhadores» com uma ligação para a lista. Aplica-se ao fecho do mês e à publicação de turnos com conflitos.
- **Estados de espera visíveis:** «pendente» nos pedidos, «rascunho» nos turnos. Uma coisa que ainda não teve efeito nunca parece feita.
- **Uma marcação que falhou nunca parece feita.** No quiosque, sem rede ou com erro do servidor, o ecrã diz «Nada foi registado» e o que fazer a seguir (Fase 7).

---

## 10. Fora do âmbito

### V1.1 — só depois do MVP estável num cliente piloto
A V1.1 passou para as Fases 11 (fornecedores, lista de compras, encomendas e receção), 12 (consumos internos) e 15 (relatórios básicos). Continuam a vir depois do piloto.

### Futuro
A leitura das vendas do POS (pelo SAF-T), a atualização de stock por vendas, as fichas técnicas e os vários restaurantes com painel de grupo passaram para as Fases 9, 10, 13 e 14. Ficam no futuro:
- **Ligação direta à API do POS**, em vez do SAF-T, para ter as vendas em tempo real. Só depois de a Fase 10 estar em uso e com a documentação na mão.
  - A Zone Soft tem uma «API Zone Soft» sobre os dados do ZS bms na nuvem, mas sem documentação pública.
  - O acesso faz-se pela Zone Soft ou pelo revendedor (estudo de 2026-10-25).
  - Cada POS é uma integração à parte.
- Previsão de compras.
- Aplicação móvel nativa.
- Integrações contabilísticas.
- Alertas por email, SMS ou WhatsApp.
- Gestão de validade e lotes.
- Relatórios financeiros avançados.
- Alergénios e informação nutricional nas fichas técnicas.

**Nada desta lista entra no MVP.** Construir agora põe em risco o prazo e a qualidade da primeira versão.

### Depois das Fases 5 e 6 (estudo da Factorial, prioridades P2 e P3)
- **P2:** trocas de turno entre colegas (precisam de notificações push na PWA; testar em iOS primeiro), uma caixa de pedidos única no dashboard (férias, correções e trocas), horas extra com um só nível de aprovação, cobertura mínima por área e hora, e horários fixos para quem não faz turnos.
- **P3:** geolocalização na marcação, só em modo de alerta e só depois de uma avaliação de impacto (AIPD), e equipas e contratos para grupos com várias casas (as casas em si entram na Fase 9). Na geolocalização guardam-se as coordenadas só no momento da entrada e da saída, nunca o percurso (BR-002). Turnos rotativos, com um padrão semanal ou quinzenal que se repete (R-036), entram quando houver um piloto com folgas rotativas fixas.
- **Integrações de payroll** (Primavera, Sage) e terminais de ponto: só depois de a exportação mensal estar em uso, e se o contabilista do piloto o pedir. Cada uma obriga a um programa de parceiros com meses de espera (BR-005).

### Não fazer
- **Biometria:** nem reconhecimento facial nem outros dados biométricos. A Lei 58/2019, art. 28, só permite tratá-los para assiduidade e controlo de acessos, e o código de ponto já resolve a marcação.
- **Contadores de férias:** nem vários países, nem proporcionalidade, nem escalões, nem saldos negativos transitados.
- **Aprovação em vários níveis.**
- **Grupos de permissões configuráveis:** os quatro perfis da secção 7 chegam.
- **Planeamento automático e arredondamento por tolerância.**
- **API pública e marketplace.**
- **Certificações** ISO 27001 e SOC 2 no MVP (BR-006).

---

## 11. Verificação

### Automática

```
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

Um teste por invariante, no mínimo:

| Teste | Verifica |
|---|---|
| `test_stock_only_changes_via_movement` | o serviço atualiza corretamente; nenhuma view escreve `current_stock` |
| `test_movement_cannot_be_deleted` | não existe caminho de delete na UI nem no admin |
| `test_double_open_shift_rejected` | constraint e validação do turno aberto único |
| `test_checkout_without_checkin_rejected` | saída sem entrada devolve erro |
| `test_staff_cannot_see_others_data` | colaborador não acede a ponto nem férias de terceiros |
| `test_staff_cannot_edit_items` | colaborador recebe 403 nas views de stock |
| `test_kiosk_code_never_opens_a_session` | depois de picar com código, quem está no tablet continua anónimo: nem app nem backoffice *(Fase 7; substitui `test_pin_does_not_open_backoffice`)* |
| `test_vacation_overlap_flagged` | sobreposição com pedido aprovado é assinalada |

Testes da Fase 7, que substituem os da sessão PIN e da fila offline da Fase 3:

| Teste | Verifica |
|---|---|
| `test_next_person_does_not_inherit_previous` | duas pessoas seguidas no tablet: a segunda não herda nada da primeira |
| `test_action_token_expires` | um token de marcação com mais de 60 segundos, ou de outra pessoa, é recusado |
| `test_entry_confirmation_shows_planned_exit_and_forgotten_exit` | a confirmação da entrada mostra a saída prevista e a saída esquecida |
| `test_staff_app_has_no_mark_button` | a app do colaborador não tem botão de ponto e não aceita marcações |
| `test_manager_cannot_manage_manager_accounts` | o gerente só cria e gere contas de Colaborador e Resp. stock |
| `test_temporary_password_must_be_changed` | uma conta com password provisória só chega ao ecrã de mudar a password |

Testes da Fase 8, em `tests/test_calendario_ferias.py`:

| Teste | Verifica |
|---|---|
| `test_mostra_o_mes_com_aprovadas_e_pendentes` | o mês, as marcas aprovadas e pendentes e a contagem de quem está fora |
| `test_gerente_marca_ausencia_aprovada` | uma ausência marcada no calendário nasce aprovada, com o gerente como decisor |
| `test_gerente_cancela_ausencia_que_ainda_nao_acabou` | cancelar não apaga, guarda quem e quando, e tira a ausência do calendário |
| `test_ausencia_que_ja_acabou_nao_se_cancela` | uma ausência passada fica como está |

Quando as Fases 5 e 6 arrancarem, juntam-se estes testes. A lista completa de testes do estudo, um por regra, está em `re-factorial/clone/parity.md`.

| Teste | Verifica |
|---|---|
| `test_overnight_shift_counts_on_work_date` | um turno das 19h às 2h conta todo no dia da entrada, nas duas superfícies |
| `test_unpaid_break_excluded_from_total` | as pausas não pagas não contam para os totais |
| `test_correction_keeps_previous_values` | uma correção guarda o antes e o depois (invariante 7) |
| `test_approved_month_is_locked` | um mês aprovado recusa correções e registos manuais (invariante 8) |
| `test_unresolved_entry_excluded_from_total` | um registo por resolver não conta para os totais (invariante 9) |
| `test_blocked_period_rejects_request` | um pedido de férias num período bloqueado é recusado |
| `test_days_taken_skips_holidays` | o cálculo de dias não conta feriados nem folgas |
| `test_break_requires_open_entry` | não se inicia uma pausa sem entrada marcada |
| `test_manager_created_absence_is_approved` | uma ausência registada pelo gerente nasce aprovada |
| `test_staff_cannot_cancel_past_absence` | o colaborador cancela pedidos pendentes ou futuros, não passados |
| `test_balance_deducted_only_on_approval` | o saldo só desce quando o pedido é aprovado |
| `test_month_approval_lists_unresolved` | aprovar um mês com registos por resolver é recusado com a contagem |
| `test_staff_never_sees_draft_shift` | um turno em rascunho ou em reserva não aparece na vista staff (invariante 10) |
| `test_conflicts_block_publish` | sobreposição, ausência aprovada ou descanso insuficiente impedem a publicação |
| `test_approved_absence_moves_shift_to_backup` | uma ausência de dia inteiro aprovada passa o turno a reserva |
| `test_rest_day_not_deducted` | uma folga não desconta dias de férias |
| `test_work_date_across_dst_change` | um turno na noite da mudança de hora conta no dia certo e com a duração real |

Quando as Fases 9 a 15 arrancarem, juntam-se estes:

| Teste | Verifica |
|---|---|
| `test_no_cross_restaurant_leak` | em cada lista e cada detalhe, um objeto de outra casa dá 404, mesmo com o pk certo *(Fase 9, feito; ver `tests/test_varias_casas.py`)* |
| `test_post_from_other_restaurant_tab_rejected` | um formulário aberto noutra casa é recusado depois de mudar de casa *(Fase 9)* |
| `test_kiosk_shows_only_its_restaurant` | o tablet de uma casa só mostra a equipa dessa casa *(Fase 9)* |
| `test_transfer_moves_stock_between_restaurants` | a transferência tira de uma casa e põe na outra, na mesma transação *(Fase 9)* |
| `test_saft_wrong_nif_rejected` | um SAF-T de outro NIF é recusado sem gravar nada *(Fase 10, feito; ver `tests/test_vendas.py`)* |
| `test_saft_reimport_is_idempotent` | importar o mesmo ficheiro duas vezes não duplica documentos *(Fase 10, feito; ver `tests/test_vendas.py`)* |
| `test_saft_cancelled_and_credit_notes` | os anulados não contam e as notas de crédito abatem *(Fase 10, feito; ver `tests/test_vendas.py`)* |
| `test_saft_working_documents_ignored` | as consultas de mesa não contam como vendas *(Fase 10, feito; ver `tests/test_vendas.py`)* |
| `test_saft_keeps_no_customer_data` | nenhum dado do cliente final fica gravado *(Fase 10, feito; ver `tests/test_vendas.py`)* |
| `test_saft_entity_expansion_rejected` | um XML com entidades é recusado *(Fase 10, feito; ver `tests/test_vendas.py`)* |
| `test_sale_after_midnight_counts_on_service_day` | uma venda à 1h conta no dia de serviço anterior *(Fase 10, feito; ver `tests/test_vendas.py`)* |
| `test_receipt_creates_entry_movement` | a receção gera entradas com a referência da encomenda e atualiza o custo *(Fase 11, feito; ver `tests/test_compras.py`)* |
| `test_staff_sees_only_own_consumption` | o colaborador vê os seus consumos e não os dos outros *(Fase 12, feito; ver `tests/test_consumos.py`)* |
| `test_recipe_version_used_for_past_day` | o consumo de um dia passado usa a versão da ficha desse dia *(Fase 13, feito; ver `tests/test_fichas.py`)* |
| `test_sales_deduct_stock_once_per_day` | um dia de vendas gera um movimento por artigo, e reimportar não repete *(Fase 14)* |
| `test_credit_note_after_apply_returns_stock` | uma nota de crédito importada depois devolve o stock com um movimento novo *(Fase 14)* |
| `test_export_totals_match_screens` | os totais da exportação são os mesmos do ecrã *(Fase 15)* |

### Manual, por fase

Seguir os critérios de aceitação de cada fase (secção 8), que são os do docx.

### Antes do piloto

- App do colaborador testada a 375px de largura **e num telemóvel real**, não só no emulador.
- Quiosque testado num tablet real, ao alto e deitado: nome, código e ação em menos de 5 segundos.
- Instalação da PWA verificada em Android e iOS.
- Percurso completo dos quatro perfis com as fixtures de demonstração.
- Build do Tailwind a correr em produção sem watch, com `--minify`.
- `collectstatic`, HTTPS, backups e restauro de backup testado uma vez.
- `pytest` a correr também contra PostgreSQL, para que os locks e as constraints sejam testados de verdade.
- Marcação num tablet partilhado por dois colaboradores seguidos: o segundo não herda nada do primeiro.
- Tablet sem rede: o ecrã diz que nada foi registado, e o gerente acrescenta o registo depois.
- Resposta da validação jurídica do registo de tempos (secção 12) arquivada e refletida nas regras.

---

## 12. Decisões em aberto

Bloqueiam a Fase 4, não a Fase 0. O desenvolvimento começa sem elas.

| Decisão | Quem | Impacto técnico |
|---|---|---|
| Nome final da marca e domínio | AT | branding, `ALLOWED_HOSTS`, ícones da PWA |
| Hosting e ambiente de produção | TM | settings de produção, deploy, custos |
| Isolamento por cliente: domínio, subdomínio ou área partilhada | AT + TM | middleware de tenant; o modelo já está preparado. A Fase 9 resolve as casas dentro do mesmo cliente; esta decisão continua a valer entre clientes diferentes |
| RGPD e tratamento de dados de trabalhadores | AT | retenção, exportação, consentimento, política de privacidade; DPA com o restaurante e lista de subcontratantes (BR-006) |
| Política de backups e recuperação | TM | frequência, retenção, teste de restauro |
| Permissões do gerente sobre stock (⚠ secção 7) | AT | uma linha nos mixins |
| Código de ponto só no tablet partilhado (⚠ secção 7) | AT | Fase 7; o TM já decidiu e implementou |
| Cliente piloto e disponibilidade semanal AT/TM | AT | calendário das sprints |
| Âmbito das Fases 5 e 6 (saldo anual e planeamento, que o docx exclui do MVP) | AT | se as fases arrancam e em que ordem face ao piloto |
| Validação jurídica do registo de tempos, férias e descansos (Código do Trabalho; Q-001 e Q-010 do estudo) | AT, com contabilista ou jurista | pode bloquear o piloto; define os valores por defeito da Fase 5 |
| Formato da exportação mensal | AT, com o contabilista | formato do ficheiro na Fase 5 |
| Contrato coletivo da restauração (Q-010) e dias de férias extra (Q-008) | AT, com contabilista | turnos, folgas, trabalho noturno e saldo por defeito |
| Limite de horas para um registo ficar por resolver (antes do planeador) | AT + TM | um número em configuração; proposta: 14 horas |
| Envio de emails (recuperação de password, avisos) | TM | enquanto não houver, a password esquecida resolve-se com uma provisória gerada pelo gerente (Fase 7) |
| Âmbito e ordem das Fases 9 a 15 face ao piloto | AT | o docx deixava estas áreas para a V1.1 ou para o futuro; proposta: depois do piloto arrancar, pela ordem do roteiro |
| Catálogo de artigos do grupo ou de cada casa | AT + TM | **Decidido a 2026-10-27: de cada casa.** O modelo do stock não muda. As fichas (Fase 13) e os fornecedores (Fase 11) continuam ligados aos artigos de cada casa pelo nome e pela unidade, e a transferência cria o artigo no destino se faltar |
| Trabalhador que trabalha em mais de uma casa | AT, com o contabilista | **Decidido a 2026-10-27: uma casa principal** (o empregador), com a ficha, o saldo de férias e o fecho do mês; pica e tem turnos nas outras. Feito (Fase 9). Falta o contabilista confirmar que o fecho e a exportação na casa principal, com as horas de todas, lhe servem |
| Várias casas com o mesmo NIF | TM, com o cliente de teste | distinguem-se pela série dos documentos no SAF-T; confirmar como o POS numera as séries (Fase 10). Já está feito: cada casa indica as suas séries nas regras de vendas, e sem elas a importação é recusada |
| Hora de corte do dia de serviço nas vendas | AT + TM | proposta: 5h, configurável por casa (Fase 10). Feito com as 5h por omissão; falta a AT confirmar |
| Serviço (almoço, jantar) nas vendas por hora trabalhada | AT + TM | proposta: pelos turnos guardados, ou por uma hora de mudança configurável (Fase 10) |
| Operador do POS (`SourceID`) ligado ao trabalhador, para vendas por empregado | AT, com jurista | toca em RGPD e na relação laboral; fica desligado até haver decisão (Fase 10) |
| Stock negativo causado pelas vendas | AT + TM | proposta: aceitar só nos movimentos de origem venda e assinalar o artigo para contar (Fase 14) |
| Refeições do pessoal e consumos internos no processamento salarial | AT, com o contabilista | formato e conteúdo do mapa mensal da Fase 12 |

---

## 13. Referência ao plano de produto

As tarefas P0-01 a P0-09, P0-20, P0-21 e P0-24 são do AT — definição de requisitos, desenho de fluxos, cenários de teste e guia do cliente piloto. Não são trabalho de engenharia e não estão detalhadas aqui; entram neste plano como dependências de entrada das fases, indicadas em cada uma.

---

## 14. Registo de progresso

Uma linha por sessão de trabalho, a mais recente em cima. Preencher sempre antes de terminar a sessão — ver o protocolo na secção 0.

O campo **Próximo passo** é o mais importante: é o que a sessão seguinte lê primeiro.

| Data | Fase | O que foi feito | Por fechar | Próximo passo |
|---|---|---|---|---|
| 2026-10-27 (3ª) | 9 | **Decisões do TM: catálogo de artigos por casa, e trabalhador em várias casas com uma casa principal. A segunda foi construída.** Secções 1, 6, 8 e 12 e Notas de desvio atualizadas; `todo.md` marcado.<br>• **Dados:** `Worker.other_restaurants` (migração `workers/0003`), `TimeEntry.restaurant` e `CorrectionRequest.restaurant` (migração `attendance/0007`, que põe os registos antigos na casa principal). `Worker.objects.in_restaurant()`, `Worker.works_in()` e `core.utils.workers_scope()`.<br>• **Serviços:** `open_shift`, `add_manual_entry` e `request_correction` recebem a casa e recusam uma onde a pessoa não trabalha. Uma entrada aberta noutra casa fica por resolver quando se pica a entrada aqui. Os conflitos do planeador contam os turnos, as folgas e as ausências da pessoa em todas as casas.<br>• **Ecrãs:** quiosque (equipa com quem vem de fora e aviso da entrada aberta noutra casa), ponto do dia, pedidos, planeador e painel da célula (turnos de outra casa só para consulta), lista e ficha do trabalhador («Casa principal: …», «Também trabalha em»), app do colaborador (casa no pedido de um registo em falta, nos turnos e no histórico), consumos. Dashboard, contadores, painel do grupo e vendas por hora trabalhada contam pela casa do registo. CSV do mês com a coluna «Casa».<br>• **Demo:** a Inês, da Ribeira, também trabalha na Esquina.<br>23 testes novos (`tests/test_trabalhador_varias_casas.py`), 370 no total; `check` e `makemigrations --check` limpos; migrações e `demo` aplicados ao `db.sqlite3` (cópia de segurança fora do repositório). As classes novas já estavam no CSS, por isso o CSS e o service worker não mudaram. | Nada visto no browser. Falta o contabilista confirmar o fecho do mês na casa principal. O mapa de consumos continua por casa. Nada commitado. | Ver no browser, com o `demo`, o tablet da Esquina com a Inês, o planeador e a ficha. Depois commitar. |
| 2026-10-27 (2ª) | — | **Afinação «SaaS premium» do frontend**, a pedido do TM depois de uma análise do CSS. Escalas fixas de cor no `tailwind.config.js` em vez de transparências; tokens novos `perigo` (vermelho) e `alerta`, e o laranja só na ação principal e nos contadores (erros, recusas e «Sair» deixam de ser laranja). Três raios, três sombras, escala de espaçamento (cartões a 24px, linhas a 56px, secções a 32px), conteúdo até `max-w-7xl`. Serifa só nos títulos de página; títulos de cartão e de secção em Inter semibold. Borda dos campos clara com sombra interior. Totais vazios da app como `0h00`. 266 trocas por script nos templates e acertos à mão (dashboard, estados, toasts).<br>347 testes a passar; `check` limpo. Visto com Chrome headless (a extensão continua desligada): dashboard, stock, vendas, encomenda, componentes, férias, novo artigo, e a app e o quiosque a 500px e 1024px. Daí saíram dois acertos: números de tabela sem quebra de linha e células interiores a 20px, porque as ações do stock passavam da margem. | A largura de 375px não foi vista (o Chrome headless não abre janelas com menos de 500px). A borda dos campos fica abaixo de 3:1 (secção 4). Nada commitado. | Ver no telemóvel a 375px. Commitar. |
| 2026-10-27 | — | **Frontend refeito com a linguagem do EMBER** (shot do Dribbble indicado pelo TM). Secção 4 reescrita.<br>• **Base:** tokens novos (`floresta`, `creme`, `areia`, `linha`, `ambar`; `aco` saiu), Inter e Playfair Display variáveis em `static/fonts/` (as fontes antigas saíram), componentes novos em `input.css`, ícones em `core/templatetags/interface.py`, logo escuro.<br>• **Backoffice:** moldura areia, cabeçalho com a casa e a conta, cartão de perfil verde e navegação com ícones e contadores (`core/context_processors.py`: `nav_secao` e `contadores`, calculados só se usados). Dashboard com saudação, quatro números com ícone, «Por tratar» e listas em linhas (a view ganhou `vendas_mes`, `ferias_pendentes_total`, `movimentos_hoje`). Separadores em pílula no Ponto, Férias, Compras, Fichas e Grupo. Ação principal de cada página a laranja. Seguimento por passos na encomenda. Planeador com a largura toda e painel por cima da grelha, como no calendário.<br>• **Quiosque e app:** passam de escuros a claros, com o cartão verde no topo; ações e textos iguais.<br>• **Resto:** 59 templates convertidos por um script de tokens e revistos no browser. Service worker para v12 e manifest creme.<br>347 testes a passar (um teste deixou de contar a classe `talao-escuro` e conta `data-consumo`); `check` limpo. Visto no browser como `admin@tasca.pt`: dashboard, trabalhadores, stock e modal do movimento, ponto, férias, calendário, turnos, compras, encomenda, fichas, vendas, configuração, dispositivo e componentes. | **Por ver no browser** (a extensão do Chrome caiu a meio): quiosque, app do colaborador, login, área do grupo, formulários e os passos da encomenda; só os testes os renderizaram. Os ícones da PWA continuam escuros. Nada commitado. | Ver no browser o quiosque (este browser está ativado), a app com uma conta de colaborador, o login e o Grupo com `dono@tasca.pt`. Depois commitar. |
| 2026-10-26 (6ª) | 12, 13 | **Fase 12 commitada e enviada** (`b4ee837`). **Fase 13: fichas técnicas**, app nova `recipes`.<br>• **Modelos:** `Recipe` (do grupo), `RecipeVersion` (data de início, doses, preparação), `RecipeLine` (artigo pelo nome e unidade, ou preparação, quantidade e quebra), `RecipeProduct` (um produto do POS, uma ficha). Migração `recipes/0001`.<br>• **Serviços (`recipes/services.py`):** criar e mudar fichas, com uma versão nova só quando a receita muda; custo por dose em cada casa, com as linhas sem artigo, com outra unidade ou sem custo assinaladas; preparações a um nível; preço do POS ou de referência e food cost; ligar produtos; produtos sem ficha pelo peso nas vendas de 90 dias. `recipes/signals.py` acompanha a mudança de nome de um artigo.<br>• **Ecrãs:** Fichas no rail, com a lista (custo, preço e food cost da casa ativa), a ficha (receita com custo, produtos do POS, versões, onde entra), o formulário (dados e receita juntos), a ficha para a cozinha para N doses e os produtos do POS sem ficha.<br>• **Demo:** o Bitoque com duas versões e o molho como preparação, e o café, ligados ao P001 e ao C001 nas duas casas. Na Esquina, o Bitoque custa 3,10 € (34,7 % de food cost).<br>28 testes novos, 347 no total; `check` e `makemigrations --check` limpos; migração e `demo` aplicados ao `db.sqlite3` (cópia de segurança fora do repositório). CSS reconstruído e service worker para v11.<br>No browser, como `dono@tasca.pt` na Esquina: a lista, a ficha do Bitoque, os produtos sem ficha e a edição, que criou a versão 3 (dois ovos). As capturas de ecrã falharam (o separador do Chrome não respondia), por isso as páginas foram lidas só pelo texto. Daí saiu um acerto: o custo de cada linha passou a ter duas casas («0,2504 €»). Antes, o Bitoque da Ribeira, sem nenhum artigo com custo, aparecia a 0,00 € e passou a «—». | A revisão visual dos ecrãs novos. O consumo de pratos nos consumos internos (Fase 12). A decisão do catálogo de artigos (secção 12), que mudaria a ligação das linhas. A versão 3 do Bitoque ficou no `db.sqlite3`. Fase 13 por commitar. | Ver os ecrãs das fichas com o browser a funcionar. Depois, o consumo de pratos nos consumos internos (com `version_on` do dia do consumo) e a Fase 14. |
| 2026-10-26 (5ª) | 11, 12 | **Fase 11 commitada e enviada** (`7406bea`). **Fase 12: consumos internos**, em `inventory`.<br>• **Modelos:** `InternalConsumption` (pessoa ou casa, motivo, dia, acima do limite, anulação), `ConsumptionLine` (custo e valor do momento, movimento e movimento da anulação), `ConsumptionSettings` (refeições por turno). `StockMovement.Origin.CONSUMO`. Migração `inventory/0004`.<br>• **Serviços (`inventory/consumption.py`):** registar numa transação, com uma `SAIDA` por linha pelo `register_movement()`; limite de refeições pelos turnos do dia (ponto, ou turnos publicados); anular com uma `ENTRADA` por linha; mapa do mês e CSV.<br>• **Ecrãs:** Stock → Consumos (mapa do mês por pessoa, consumos em talões, filtro por pessoa, anular com motivo, CSV), Registar consumo (até seis artigos), regras em Configuração (só o Admin), e «Os meus consumos» na app do colaborador.<br>• **Demo:** café e água com custo, uma refeição por turno, as refeições de ontem da Marta e do Rui e uma oferta da casa.<br>13 testes novos, 319 no total; `check` e `makemigrations --check` limpos; migração e `demo` aplicados ao `db.sqlite3` (cópia de segurança fora do repositório). CSS reconstruído e service worker para v10.<br>No browser, como `dono@tasca.pt` na Esquina: o mapa, a lista e o registo de uma refeição do Rui, que ficou acima do limite. Daí saíram dois acertos: o aviso passou a dizer porque passou o limite («não tinha turno nesse dia»), e um valor desconhecido deixou de aparecer como 0,00 €. | O consumo de pratos espera pela Fase 13. A app do colaborador só foi vista pelos testes, não num telemóvel. O contabilista tem de dizer como quer as refeições em espécie (secção 12). O consumo `CI-4` do teste ficou no `db.sqlite3`. Fase 12 por commitar. | Commitar a Fase 12. Depois, Fase 13 (fichas técnicas), que liga os pratos aos produtos do POS da Fase 10 e permite o consumo de pratos nesta fase. |
| 2026-10-26 (4ª) | 10, 11 | **Fase 10 commitada e enviada** (`7d01623`). **Fase 11: fornecedores e compras**, app nova `purchasing`.<br>• **Modelos:** `Supplier` (do grupo), `SupplierItem` (um preferido por artigo), `PurchaseOrder` e linhas, `Receipt` e linhas, ligadas ao movimento que geraram. `StockMovement.Origin.COMPRA`. Migrações `inventory/0003` e `purchasing/0001`.<br>• **Serviços (`purchasing/services.py`):** lista de compras (repor o mínimo menos o já encomendado), criar, mudar, enviar e cancelar encomendas, texto da encomenda, receção numa transação (entrada de origem compra pelo `register_movement()`, custo de referência e último preço do fornecedor, estado da encomenda), mês por fornecedor.<br>• **Ecrãs:** Compras no rail para o Admin, o Gerente e o Resp. stock, com Lista de compras, Encomendas (rascunho editável, texto para copiar, folha para imprimir), Receber, Receções (mês por fornecedor e CSV), Fornecedores (artigos, preferido, arquivar) e Preços de cada artigo, a partir do stock. O histórico do stock assinala as compras.<br>• **Demo:** três fornecedores, os preferidos dos artigos da Esquina, alface e cebola abaixo do mínimo e uma receção da semana passada.<br>21 testes novos, 306 no total; `check` e `makemigrations --check` limpos; migrações e `demo` aplicados ao `db.sqlite3` (cópia de segurança fora do repositório). CSS reconstruído e service worker para v9.<br>No browser, como `dono@tasca.pt` na Esquina: o critério de aceitação de ponta a ponta (lista de compras → encomenda aos Frescos do Mercado → tomate acrescentado ao rascunho → enviada → recebida sem a cebola → «Recebida em parte», stock e custo mudados, entradas no histórico), mais Receções e a página do fornecedor. Daí saíram três acertos: a unidade partia para baixo do campo, o texto dizia «3 quilograma» e os preços apareciam como «0,9». | A AT tem de aprovar o âmbito. Sem «dar por fechada» uma encomenda recebida em parte (Notas de desvio). O fluxo foi feito no browser pelo Admin do grupo; o Resp. stock só pelos testes. A encomenda `ENC-1` e a receção `REC-2` ficaram no `db.sqlite3` de desenvolvimento. Fase 11 por commitar. | Commitar a Fase 11. Depois, Fase 12 (consumos internos): acrescenta a origem «consumo interno» e valoriza ao custo de referência, que as receções passaram a atualizar. |
| 2026-10-26 (3ª) | 10 | **Fase 10: vendas a partir do SAF-T.** App nova `sales`.<br>• **Leitura (`sales/saft.py`):** streaming com `defusedxml` (nova dependência em `requirements.txt`), XML ou .zip, sem DTDs nem entidades. Só o cabeçalho, os produtos e `SalesInvoices`; os clientes nunca se leem; `WorkingDocuments` e `Payments` saltam-se.<br>• **Importação (`sales/services.py`):** NIF, versão, período e programa validados antes de gravar; tudo numa transação. Documentos únicos por número: o mesmo ficheiro é recusado, um sobreposto acrescenta os novos e atualiza o estado. Anulados (A) e faturados (F) não contam; notas de crédito com sinal negativo. Séries por casa, obrigatórias quando há outra casa com o mesmo NIF. Dia de serviço com hora de corte (5h). Totais de controlo comparados, só com aviso.<br>• **Modelos:** `SalesImport`, `SalesDocument`, `SalesLine`, `PosProduct`, `SalesSettings` (migração `sales/0001`).<br>• **Ecrãs:** Vendas (resumo com comparação, por dia com horas do ponto e vendas por hora trabalhada, mapa da semana por hora, produtos, famílias, dois CSV), Importar (com o histórico de importações) e Regras (só o Admin, também em Configuração). Entrada Vendas no rail para o Admin e o Gerente. Aviso no dashboard com mais de 7 dias sem importar, e vendas do mês no painel do grupo.<br>• **Demo:** NIF nas duas casas e um SAF-T sintético de cada uma (`sales/sintetico.py`), do dia 1 do mês passado até ontem.<br>28 testes novos, 285 no total; `check` e `makemigrations --check` limpos; migração e `demo` aplicados ao `db.sqlite3` (cópia de segurança fora do repositório). CSS reconstruído e service worker para v8.<br>No browser, como `dono@tasca.pt`: Vendas de setembro e outubro, Importar e painel do grupo. Daí saíram três correções: a variação do número de documentos rebentava com inteiros (`float` sem `quantize`), o rodapé da tabela estava desalinhado, e outubro incompleto aparecia comparado com setembro inteiro. | Ficheiro real do cliente de teste por importar: é o critério de aceitação (o total do mês igual ao do relatório do POS). Vendas por serviço por fazer, à espera da decisão nova da secção 12. O carregamento de um ficheiro pelo browser só foi testado pelos testes, não à mão. Nada commitado. | Pedir ao cliente de teste o SAF-T de um mês e o relatório de vendas do POS desse mês; importar e comparar o total ao cêntimo. Confirmar as séries, o estado F e os totais de controlo (Notas de desvio). Depois, Fase 11. |
| 2026-10-26 (2ª) | 9 | **Fase 9 arrancada: várias casas no mesmo grupo.**<br>• **Dados:** `Organization`; `Restaurant.organization`, `nif`, `address` e `municipality`; `User.organization` e `is_group_admin`; `Membership` (acesso e perfil por casa); `StockTransfer`, `StockMovement.origin` e `transfer`. Migrações `core/0003`, `accounts/0004` e `inventory/0002`, com data migrations.<br>• **Casa ativa:** `core.middleware.ActiveRestaurantMiddleware` põe `request.restaurant` e `request.role`. As views passaram todas para `restaurant_scope(request, …)` e os mixins para `request.role`; saíram o «sem restaurante vê tudo» e os seis `Restaurant.objects.first()`. Seletor de casa no rail e recusa de POSTs abertos noutra casa (`static/js/casa.js`, `X-Opero-Casa`).<br>• **Grupo:** painel com uma linha por casa, casas e acessos, só para o Admin do grupo. O gerente muda o perfil de uma conta só na casa onde está.<br>• **Stock:** transferência entre casas, com a criação do artigo no destino se faltar.<br>• **Quiosque:** só a equipa da casa do tablet; um cookie sem casa já não abre o quiosque.<br>• **Demo:** Grupo Tasca com a Tasca da Esquina e a Tasca da Ribeira, `dono@tasca.pt` como Admin do grupo e o gerente com acesso às duas.<br>23 testes novos, 257 no total; `check` e `makemigrations --check` limpos; migrações e `demo` aplicados ao `db.sqlite3` (cópia de segurança fora do repositório). No `db.sqlite3`, o superuser sem casa passou a Admin do grupo. CSS reconstruído e service worker para v7.<br>No browser, como `dono@tasca.pt`: painel do grupo, «Abrir» a Ribeira, transferir 5 kg de arroz para a Esquina (cria o artigo lá), mudar de casa no seletor e ver a entrada no histórico da Esquina, ecrã de acessos. | As duas decisões da secção 12 (catálogo de artigos do grupo, trabalhador em várias casas) não foram tomadas: tudo continua por casa. `User.restaurant` e `User.role` ainda existem, como casa e perfil por omissão. A recusa de POSTs de outra casa depende de JavaScript nos formulários normais (no HTMX vai no cabeçalho); sem JavaScript, o POST passa. Nada commitado. | Fechar com a AT as duas decisões da secção 12 e, com elas, acabar a Fase 9. Depois, Fase 10 (SAF-T). |
| 2026-10-26 | 9–15 | **Roteiro depois do MVP no plano, sem código.** Pedido do TM: o cliente de teste já extrai o SAF-T do POS (Zone Soft), e o produto tem de cobrir stock e movimentos, compras e fornecedores, trabalhadores, ponto e férias, consumos internos, fichas técnicas, atualização de stock por vendas, extração e análise de dados e, sobretudo, vários restaurantes.<br>Mapa do produto na secção 1, a confirmar onde está cada área. Fases novas: 9 (vários restaurantes), 10 (vendas pelo SAF-T), 11 (fornecedores e compras), 12 (consumos internos), 13 (fichas técnicas), 14 (stock pelas vendas) e 15 (extração e análise). Acertos nas secções 2, 6, 7, 10, 11 e 12.<br>Antes, a 2026-10-25, um estudo da Zone Soft feito com fontes públicas: a «BMS Mobile» é o ZS bms mobile, e a API não tem documentação pública. | Âmbito e ordem por aprovar pela AT. Sete decisões novas na secção 12, das quais o catálogo de artigos e o trabalhador em várias casas mexem no modelo da Fase 9. | Pedir ao cliente de teste um SAF-T de um mês e saber se o POS exporta um período à escolha. Levar à AT a ordem das fases e as decisões novas. |
| 2026-10-25 (2ª) | 8 | **Calendário mensal de ausências no backoffice.** A entrada «Férias» abre o mês: uma linha por trabalhador, uma coluna por dia, ausências aprovadas a cheio e pendentes tracejadas, fins de semana, feriados e períodos bloqueados assinalados, contagem de quem está fora e saldo de cada um. Clicar numa célula abre um painel, como no planeador, para marcar uma ausência (fica aprovada), aprovar ou recusar um pedido e cancelar uma ausência que ainda não acabou. Serviço novo `cancel_by_manager()` e campo `cancelled_by`, com migração `vacations/0005`.<br>18 testes novos, 234 no total; `check` e `makemigrations --check` limpos; migração aplicada ao `db.sqlite3`.<br>No browser: marcar, ver o saldo e a contagem a mudar, e cancelar (a ausência de teste do Rui ficou cancelada no `db.sqlite3`). O painel começou ao lado da grelha, como no planeador, mas assim só cabiam 20 dias: passou a abrir por cima, e a página pode usar a largura toda (bloco `largura` em `base_manage.html`). | Marcar com arrastar sobre várias células não foi feito: o painel tem início e fim. Sem filtro por área, porque as ausências não têm área. | Rever o calendário com dados reais e decidir se vale a pena arrastar para marcar períodos. |
| 2026-10-25 | 7 | **Fase 7 completa em código: o ponto pica-se só no tablet partilhado e a app do colaborador passa a ser de consulta e pedidos.** Decidido em conversa com o TM; secções 1, 3, 5, 6, 7, 9, 10, 11 e 12 atualizadas.<br>• **Dados:** o código de ponto passou do `User` para o `Worker` (`kiosk_code`, `code_set_at`); a data migration copiou o PIN que havia (o da Marta) e removeu os campos do utilizador. `User.must_change_password`.<br>• **Quiosque (app `kiosk`, `/quiosque/`):** nomes → código no teclado do ecrã → ações do estado atual, com as pausas ao lado da Saída. Sem sessão: o código devolve um token assinado de 60 s e de uso único. Confirmação da entrada com a saída prevista, a saída esquecida e os registos por resolver, até «OK» ou 15 s; as outras durante 5 s. Aviso no ecrã de ações quando já passou do fim previsto. `hx-boost` e um aviso «Nada foi registado» para falhas de rede ou do servidor. Bloqueio de 60 s ao fim de 5 falhas, por trabalhador.<br>• **App:** sem botão de ponto, com o estado do dia, o turno de hoje, os totais e as três entradas. Login por email; o login por PIN, o `MarkView`, a fila offline e as sessões PIN saíram. Service worker v5.<br>• **Backoffice:** «Código de ponto» e «Conta da app» na lista de trabalhadores. A conta é criada com uma password provisória mostrada uma vez; o gerente só gere Colaborador e Resp. stock. O middleware obriga a mudar a provisória. A ativação do dispositivo perdeu o modo pessoal.<br>• **Testes:** 216 (eram 195). Os da sessão PIN e da fila offline foram substituídos pelos do quiosque e das contas. Os testes passaram a usar um hasher rápido e a limpar a cache: a suite desceu de 8 minutos para menos de 15 segundos.<br>• **No browser:** quiosque visto de ponta a ponta (nomes, código, entrada, regresso aos 15 s, ações em turno, pausa e regresso aos 5 s), app, lista de trabalhadores e conta. Daí saíram duas correções: o formulário do código publicava para `/quiosque/` (com `hx-push-url="false"` o endereço não muda) e o teclado subia quando a dica desaparecia. Nos testes apareceu também o token repetido no mesmo segundo, corrigido com um valor aleatório.<br>`check` e `makemigrations --check` limpos; migrações e `demo` aplicados ao `db.sqlite3` (cópia de segurança fora do repositório). Nada commitado. | O aviso sem rede não foi visto com o tablet desligado. Tablet e telemóvel reais por testar. Cache local: o bloqueio do código e o uso único dos tokens só valem dentro de um processo (ver Notas de desvio). A Marta ficou com uma entrada e uma pausa abertas no `db.sqlite3` de desenvolvimento, do teste no browser. | Testar num tablet real: duas pessoas seguidas, o tablet em modo avião e a leitura do teclado com luz má. No telemóvel: criar a conta de alguém, entrar com a provisória e mudá-la. Levar à AT a decisão do código no tablet (secção 12). |
| 2026-10-24 (5ª) | 5, 6 | **Fase 5 completa em código e Fase 6 inteira.** Commits `0764720`, `b7b9495`, `82b3aa9` e `f2d45cc`.<br>• **Por resolver e pedidos de correção:** uma entrada sem saída que passe do limite (14 h, `ATTENDANCE_UNRESOLVED_HOURS`) fica por resolver e conta zero. Já não impede a entrada seguinte: ao marcar nova entrada, a antiga fica com `missing_exit`. O colaborador pede correção no histórico ou a partir do aviso no ecrã de ponto; o gerente decide em Ponto → Pedidos, e a aprovação passa pelos serviços e fica no histórico.<br>• **Ausências:** `AbsenceType` com cinco tipos de origem, meio dia, aprovação automática, ausência do gerente já aprovada, cancelamento pelo colaborador. `Allowance` com transitados que caducam e ecrã de saldos. Feriados nacionais calculados, municipais por restaurante. `BlockedPeriod` recusa na submissão e aparece antes de pedir.<br>• **Configuração:** a entrada do rail deixou de ser um marcador. CRUD para o Admin (áreas, tipos de pausa e de ausência, feriados, períodos bloqueados) e turnos guardados para o gerente.<br>• **Fecho do mês:** `MonthClose`, aprovação por trabalhador ou de todos os prontos, recusa com contagem, bloqueio nos serviços (incluindo marcações offline atrasadas), reabertura com motivo, aviso no dashboard e CSV (`;`, BOM, só aprovados).<br>• **Planeador (app `shifts`):** turnos guardados, grelha semanal com painel por célula (HTMX), lote, cópia da semana anterior, folgas, conflitos (sobreposição, folga, ausência aprovada, menos de 11 h de descanso), publicação com resumo do que muda e despublicação. Ausência aprovada passa turnos a reserva; cancelada, volta a rascunho. «Os meus turnos» na vista staff. Na vista da equipa, o previsto ao lado do realizado, com atraso, saída fora de horas e falta de marcação. O limite dos registos por resolver passa a ser o fim do turno publicado mais 4 h. Folgas e dias sem turno em semanas planeadas não descontam férias.<br>195 testes; `check` e `makemigrations --check` limpos; migrações aplicadas ao `db.sqlite3`. | **Ninguém viu os ecrãs novos:** a extensão do Chrome não estava ligada, por isso o planeador, os pedidos, o fecho do mês, a configuração e os saldos só foram verificados pelos testes. R-012 (pergunta na saída tardia) não foi feito, como o plano deixava em aberto. Anexos nos tipos de ausência ficaram de fora (ver Notas de desvio). O `demo` não cria turnos. | Rever no browser, com `manage.py demo`, os ecrãs novos: Turnos (sobretudo a largura da grelha com o painel ao lado), Ponto → Pedidos e Fecho do mês, Férias → Saldos e Configuração. Depois levar à AT o âmbito das Fases 5 e 6 e os valores por confirmar (14 h, 22 dias, 11 h de descanso, formato do CSV). |
| 2026-10-24 (4ª) | 5 | **Fase 5 arrancada: primeiro bloco (modelo e persistência) e ecrã de ponto com pausa.** Antes, commit `f34f92d` com o trabalho da Fase 3 que estava por commitar.<br>• **Áreas:** `core.WorkArea`, com Cozinha, Sala e Bar de origem (signal e data migration). O gerente escolhe a área ao ativar o dispositivo; o cookie guarda-a e a entrada herda-a. Uma área arquivada deixa de ser herdada.<br>• **`TimeEntry`:** `work_date` calculado no `save()` na hora local, `work_area` e `source` (tablet partilhado, telemóvel, gerente). Data migration preenche o `work_date`. A vista da equipa e os totais da vista staff agrupam por `work_date`; a vista da equipa ganhou a coluna «Trabalhado», a área e as pausas.<br>• **Pausas:** `BreakType` (Refeição não paga, Pausa curta paga, de origem) e `Break`, com constraint de uma pausa aberta por registo. Serviços `start_break` e `end_break`; `close_shift` fecha a pausa aberta. `TimeEntry.worked()` desconta as não pagas.<br>• **Ecrã de ponto:** em turno, «Saída» mais um botão por tipo de pausa; em pausa, «Terminar pausa». A fila offline (`app.js`) guarda `tipo_pausa`. Cache do service worker para v4.<br>• **Histórico de correções:** `EntryCorrection` com antes e depois. A página de correção mostra-o em talões. As correções antigas ficaram com «valor anterior não guardado».<br>• **Falha corrigida:** `correct_entry()` usava os valores da instância que recebia. Com uma instância antiga, uma correção só da entrada reabria um turno já fechado. Agora relê o registo com lock.<br>25 testes novos, 106 no total; `check` e `makemigrations --check` limpos; migração aplicada ao `db.sqlite3` de desenvolvimento (9 registos, 1 correção passada para o histórico). | Ecrã de pausa por ver num telemóvel. Áreas e tipos de pausa só se configuram no admin do Django (ver Notas de desvio). Do resto da Fase 5 falta tudo: pedidos de correção, registos por resolver, ausências, saldo, feriados, períodos bloqueados, fecho do mês e exportação. | Seguir a ordem da Fase 5: pedido de correção pelo colaborador (`CorrectionRequest`) e depois registos por resolver. Em paralelo, levar à AT a aprovação do âmbito, que continua por dar. |
| 2026-10-24 (3ª) | 3 | **Modo quiosque e falhas de sincronização visíveis.**<br>• **Dispositivo:** o cookie passa a guardar o modo, partilhado ou pessoal, e o gerente escolhe-o na ativação.<br>• **Sessão no tablet partilhado:** expira em 5 minutos e termina a seguir a cada marcação. O HTMX recebe `HX-Redirect` para o PIN, onde aparece a confirmação com o nome e a hora. No ecrã, sai sozinha ao fim de 90 segundos sem marcação.<br>• **`MarkView`:** aceita `acao` e `trabalhador` e recusa a marcação quando a ação já não corresponde ao estado do turno ou quando é de outra pessoa. Os pedidos da fila (`X-Opero-Fila`) recebem JSON, 200 ou 409 com o motivo.<br>• **`app.js`:** a fila guarda a ação, quem marcou e o estado, e a lista «Marcações sem rede» aparece no ecrã de ponto.<br>• **Falha corrigida:** a fila marcava em nome de quem tivesse a sessão aberta no momento do envio.<br>12 testes novos, 81 no total; `check` e `makemigrations --check` limpos; `app.js` passa no `node --check`. | Os dois itens estão `[~]` porque o comportamento do `app.js` (lista da fila, dispensar, redirecionamento depois de sincronizar) não foi verificado num browser. Os dispositivos já ativados contam como partilhados: o telemóvel pessoal de um colaborador tem de ser reativado como pessoal. | Testar no telemóvel e num tablet: duas pessoas seguidas no tablet partilhado, marcação em modo avião, e uma recusa forçada (por exemplo, o gerente fecha o turno enquanto o telemóvel está offline). |
| 2026-10-24 (2ª) | 3–6 | Revisão do plano inteiro com os dados do estudo da Factorial:<br>• **Secção 1:** posicionamento.<br>• **Secção 4:** sala limpa.<br>• **Secção 5:** dispositivo partilhado ou pessoal, e evolução do ecrã de ponto.<br>• **Secção 7:** permissões das Fases 5 e 6.<br>• **Fase 3:** dois itens novos, as falhas de sincronização visíveis e o modo quiosque.<br>• **Fase 4:** validação jurídica, PWA em iOS e RGPD como pré-requisitos do piloto.<br>• **Fases 5 e 6:** detalhadas regra a regra (R-004 a R-067).<br>• **Secções 9 a 12:** regras de feedback, P3 e lista do que não fazer, testes novos e quatro decisões novas.<br>Nenhum código alterado. | Os dois itens novos da Fase 3 são falhas reais no código atual: `app.js` deita fora em silêncio as marcações recusadas, e a sessão PIN de 12 horas fica aberta num tablet partilhado. | Corrigir os dois itens novos da Fase 3 antes do piloto. |
| 2026-10-24 | 5, 6 | Recomendações do PRD do estudo da Factorial passadas para o plano: Fase 5 (áreas de trabalho, dia de trabalho, pausas, histórico e pedidos de correção, registos por resolver, tipos de ausência, saldo, feriados, períodos bloqueados, fecho do mês e exportação), Fase 6 (planeador de turnos), prioridades P2 e P3 e lista do que não fazer na secção 10, testes novos na secção 11 e três decisões novas na secção 12. Nenhum código alterado. | Âmbito das duas fases por aprovar pela AT, e validação jurídica pendente. | Fechar as Fases 1 a 4 (revisão visual, PWA no telemóvel) e levar à AT as decisões novas da secção 12. |
| 2026-10-23 | — | Estudo da Factorial a partir de fontes públicas, em `re-factorial/` (ver Notas de desvio). | Recomendações por passar para as fases. | Passar o PRD para o plano (feito a 2026-10-24). |
| 2026-09-09 | — | O `runserver` passa a arrancar em `127.0.0.1:8001` por omissão (`DEFAULT_ADDRPORT` em `manage.py`; um endereço explícito na linha de comandos continua a mandar). O túnel HTTPS para o teste da PWA passa a ser `ssh -R 80:127.0.0.1:8001 nokey@localhost.run` (o `cloudflared` continua sem funcionar nesta rede). Além disso, a palavra OPERO no rail do backoffice e nos dois ecrãs de entrada passou a ser o logo (`static/img/logo-opero.png`, recortado do PNG que estava em `media/`, que é ignorado pelo git e não é servido). 69 testes a passar. | Nada. | Retomar o teste da PWA no telemóvel, agora contra a porta 8001. |
| 2026-09-04 (3ª sessão) | 3 | **Bug encontrado no teste real da PWA no telemóvel:** instalada a app, abrir o ícone levava ao login de email e password — a `start_url` é `/equipa/` e o `LoginRequiredMixin` usava o `LOGIN_URL` global. Sem escrever `/equipa/entrar/` à mão não havia forma de marcar ponto. Corrigido: `StaffViewMixin.login_url = staff:pin_login`, «Sair» da vista staff volta ao PIN, e o service worker deixou de guardar respostas redirecionadas (servir uma a um pedido de navegação rebenta offline), cache para v2. 4 testes novos, 69 no total. `cloudflared` não funciona nesta rede (ligação à API cortada); o túnel HTTPS usado é `ssh -R 80:127.0.0.1:8000 nokey@localhost.run`. | Retomar o guião da PWA a partir do passo da instalação, agora que o arranque leva ao PIN. Continua por verificar: marcação em modo de avião e sincronização com o timestamp original. | Reinstalar a PWA no telemóvel (limpar os dados do site primeiro, para largar o service worker v1) e completar o teste offline. |
| 2026-09-04 (2ª sessão, cont. 3) | 4 | Dashboard do gerente com os quatro sinais do docx (áreas de pessoas escondidas ao resp. de stock) e comando `manage.py demo` — restaurante Tasca da Esquina, contas dos 4 perfis (password demo1234, PIN da Marta 2468), stock com movimentos, ponto e férias, incluindo um pedido pendente que sobrepõe um aprovado. 65 testes. Commit na sequência de `bae972d`. | Da Fase 4 falta: bugs P0/P1 do AT (depende dos testes funcionais dele) e ambiente de demonstração (bloqueado por hosting/domínio, secção 12). Das Fases 1–3: revisão visual + teste da PWA em telemóvel real. | O TM deve: correr `manage.py demo` + `runserver`, percorrer os 4 perfis, testar a PWA num telemóvel (instalar, modo avião, sincronizar) e marcar as fases ✅. Em paralelo: fechar com o AT as decisões da secção 12 (PIN, permissões do gerente, hosting). |
| 2026-09-04 (2ª sessão, cont. 2) | 3 | Fase 3 escrita: login por PIN (seleção de trabalhador + PIN 4–6 dígitos, hash do Django, throttling 5 falhas/60s, cookie assinado de dispositivo com 180 dias ativado pelo gerente em Configuração→Dispositivo), sessão PIN marcada na sessão e testada contra o backoffice com login real; botão de estado com cronómetro (hx-post único), totais dia/semana, histórico em talões escuros, férias em 3 campos; gestão de PIN no backoffice (Trabalhadores→Definir/Repor PIN); PWA com manifest, ícones Pillow, sw.js (cache do shell, servido na raiz via view) e fila offline em `app.js` (localStorage, `marcado_em` com o timestamp original, nunca no futuro; reenvia ao voltar online). 62 testes. Commit `bae972d`. | Itens de PWA/offline estão `[~]`: o service worker e a fila offline só se verificam num browser real (instalação Android/iOS, modo avião) — não há teste automático que os cubra. Restante por fechar: revisão visual das Fases 1–3. | Testar a PWA num telemóvel real (instalar, marcar ponto em modo avião, voltar a ter rede) e rever visualmente os módulos. Depois: Fase 4 (dashboard, fixtures, ambiente de demonstração). |
| 2026-09-04 (2ª sessão, cont.) | 2 | Fase 2 completa em código: `Worker` (conta opcional), `TimeEntry` com constraint parcial de turno único aberto + serviços `open/close_shift` (invariantes 3 e 4), correção e registo manual auditados com motivo obrigatório (invariante 5), `VacationRequest` com decisão auditada, badge de sobreposição com aprovados e bloqueio de delete de aprovados no admin (invariante 6). Vista de equipa por dia com navegação de datas e «Saída em falta»; novo pedido de férias em nome do trabalhador; modal único de decisão. 46 testes no total — `test_double_open_shift_rejected`, `test_checkout_without_checkin_rejected`, `test_vacation_overlap_flagged`, `test_staff_cannot_see_others_data` incluídos. Commit `d262050`. | Revisão visual dos três módulos no browser. Fases 1 e 2 ficam 🟡 até à revisão visual do TM. | Rever visualmente stock + pessoas; marcar fases ✅. Depois: Fase 3 (login PIN, ecrã de ponto staff, PWA) — atenção à decisão pendente do PIN com o AT (secção 12). |
| 2026-09-04 (2ª sessão) | 0→1 | Fase 0 fechada após revisão visual do TM. Fase 1 completa em código: modelos `inventory` com constraints, `register_movement()` (transação + `select_for_update`, rejeita stock negativo), admin de movimentos só-consulta, sementes de categorias no `post_save` do `Restaurant`, CRUD de artigos (sem delete — `is_active`) e categorias (criar/renomear/eliminar com PROTECT), movimento em modal HTMX com linha + contador OOB e toast por `HX-Trigger`, pesquisa/filtros parciais, histórico em talões (limite 200). 25 testes; invariantes 1, 2 e 5 testadas. Commit `925769e`. | Revisão visual do módulo de stock no browser e o percurso de aceitação do docx feito à mão (criar artigo → registar entrada → confirmar stock e histórico). Estado da fase fica 🟡 até lá. | Rever visualmente o módulo de stock; se estiver bom, marcar a Fase 1 ✅ e arrancar a Fase 2 (Pessoas: `Worker`, ponto no backoffice, férias). |
| 2026-09-04 | 0 | Fase 0 quase completa: projeto Django 5.2, settings dev/prod, primeira migração (`Restaurant`, `TimeStampedModel`, `User` custom), groups por perfil com sync no save, mixins em `core/mixins.py` (incl. fronteira PIN→403), login/logout com redirecionamento por perfil, tokens + Tailwind v3.4.17 standalone, fontes woff2 locais, HTMX 2.0.7 e Alpine 3.15 vendored, `base_manage`/`base_staff`, componentes todos e página `/componentes/`. 9 testes a passar (`test_pin_does_not_open_backoffice` incluído); `check` e `makemigrations --check` limpos. Commit `30cf284`. | Revisão visual no browser das duas superfícies e da página de componentes — os templates renderizam nos testes mas ninguém os viu; por isso o último item está `[~]`. | Correr `runserver` + `tailwindcss -w`, criar um superuser, rever visualmente `/componentes/`, o login e os dois shells; marcar o item e fechar a Fase 0. Depois: Fase 1 (modelos `inventory` + `register_movement()`). |
| 2026-09-04 | — | Plano de engenharia escrito a partir do docx. Stack, direção de design e fases fixadas. | Nada implementado. | Arrancar a Fase 0: `git init`, dependências e projeto Django. |

### Notas de desvio

Alterações ao plano decididas durante a execução. Se algo aqui contradiz uma secção acima, **corrigir também a secção** — este registo é o histórico, não a fonte de verdade.

- **2026-10-27 · Entrada aberta noutra casa fica por resolver.** O plano não dizia o que acontece quando alguém pica a entrada numa casa com a entrada da outra ainda aberta. Recusar deixava a pessoa sem conseguir picar; fechar a outra à hora atual inventava uma saída. Ficou como uma saída esquecida: o registo da outra casa fica por resolver e corrige-se com um pedido. No tablet de outra casa não se pica a saída nem as pausas.
- **2026-10-27 · Mapa de consumos por casa.** O consumo de quem vem de outra casa aparece no mapa da casa onde comeu, não no da casa principal. Rever quando o contabilista disser como quer as refeições em espécie (secção 12).
- **2026-10-27 · Coluna «Casa» no CSV do mês.** Acrescentada no fim, para não mudar as colunas que já existiam. O formato continua por confirmar com o contabilista.
- **2026-10-27 · Catálogo de artigos por casa.** Decisão do TM, contra a proposta de um catálogo do grupo. Ficam definitivas as notas «Linha da ficha pelo nome do artigo» e «Fornecedor do grupo, artigos da casa». Consequência para a Fase 14: uma linha de ficha sem artigo com o mesmo nome e unidade numa casa não abate stock nessa casa, e tem de aparecer assinalada.

- **2026-10-27 · Laranja só na ação principal.** Com o tom `perigo` e o `alerta`, o laranja (`chama`) deixou de servir para erros, recusas, avisos e «Sair». A variante `chama` do componente de estado continua a funcionar e dá o estilo de alerta.
- **2026-10-27 · Linguagem visual do EMBER.** O TM pediu o frontend do shot «Restaurant Dashboard» (EMBER). A direção «back of house» da secção 4 deixa de valer: entram o creme, a serifa e a terracota que ela recusava. A regra «uma só coisa laranja por ecrã» passa a «uma só ação principal laranja por ecrã»; os contadores e alertas também são laranja. Os números deixam a mono e ficam em Inter com figuras tabulares. O painel do planeador passa a flutuar por cima da grelha, como o do calendário (Fase 8), porque a coluna nova é mais larga. Service worker para v12.
- **2026-10-26 · Linha da ficha pelo nome do artigo.** As fichas são do grupo e o catálogo de artigos continua por casa (decisão da secção 12 por tomar). Uma linha guarda o nome e a unidade, e em cada casa liga-se ao artigo com o mesmo nome e unidade. Assim a mesma ficha serve as duas casas, cada uma com o seu custo. Se o catálogo passar a ser do grupo, as linhas passam a apontar para o artigo do grupo, que se encontra pelo nome.
- **2026-10-26 · Mudar o nome de um artigo acompanha as fichas.** Quando nenhuma outra casa do grupo tem um artigo com o nome antigo, as linhas de todas as versões passam ao nome novo. Não é uma mudança da receita, por isso não cria versão. Se outra casa ainda tem o nome antigo, a ficha fica assinalada «não há este artigo nesta casa» onde o nome mudou.
- **2026-10-26 · Quantidades da receita inteira.** O plano dizia «a quantidade por dose». Ficou a quantidade da receita, que dá o número de doses: é como se escreve um molho ou uma massa, e num prato de uma dose é o mesmo. O custo por dose divide pelas doses.
- **2026-10-26 · O número de doses e a preparação são da versão.** O nome, o tipo e o preço de referência mudam sem criar versão, porque não mudam o que sai do stock.
- **2026-10-26 · Food cost com o preço sem IVA.** O preço do POS vem sem IVA no SAF-T, por isso o preço de referência da ficha também é sem IVA.
- **2026-10-26 · O consumo de pratos fica para a sessão seguinte.** Estava na Fase 12, à espera desta. Fica por fazer nas duas fases.
- **2026-10-26 · Service worker para v11.** O CSS mudou com as fichas.
- **2026-10-26 · Consumos anulam-se.** O plano não dizia como se corrige um consumo registado em nome errado. Como os movimentos não se apagam (invariante 2), a anulação lança uma `ENTRADA` por linha, da mesma origem, com o motivo, e o consumo fica marcado e fora do mapa.
- **2026-10-26 · Limite de refeições por casa, não por colaborador.** O plano falava em «limite opcional por colaborador, por exemplo uma refeição por turno». Ficou um limite da casa por turno, que vale para todos: é o caso do exemplo e não obriga a configurar pessoa a pessoa. Sem turno no dia, o limite é zero e a refeição fica assinalada.
- **2026-10-26 · `parse_decimal` em `core/utils.py`.** Saiu das compras, porque os consumos também leem números escritos com vírgula.
- **2026-10-26 · Service worker para v10.** O CSS mudou com os consumos.
- **2026-10-26 · Fornecedor do grupo, artigos da casa.** O catálogo de artigos continua por casa (decisão da secção 12 por tomar), por isso a ligação fornecedor–artigo (`SupplierItem`) é a um artigo de uma casa. Se o catálogo passar a ser do grupo, a ligação muda para o artigo do grupo.
- **2026-10-26 · Uma encomenda recebida em parte não se cancela.** O que chegou já entrou no stock. O que falta continua a contar como «já encomendado» na lista de compras até chegar. Se o fornecedor não vai mandar o resto, falta um «dar por fechada»; fica para quando houver uso real.
- **2026-10-26 · Fornecedor arquivado ainda entrega.** Um fornecedor arquivado não recebe encomendas novas, mas uma receção de uma encomenda que já tinha ainda se regista.
- **2026-10-26 · Lista de compras com «no mínimo ou abaixo».** O plano dizia «abaixo do mínimo»; ficou o mesmo critério do «Stock baixo» do dashboard e do stock (`current_stock <= minimum_stock`). Um artigo exatamente no mínimo aparece com sugestão zero.
- **2026-10-26 · Service worker para v9.** O CSS mudou com as Compras.
- **2026-10-26 · Regras de vendas num modelo à parte.** A Fase 9 dizia que as séries de faturação entravam no `Restaurant`. Ficaram em `sales.SalesSettings`, com a hora de corte e o custo médio por hora, para a app `sales` não mexer no modelo do `core`. O NIF continua no `Restaurant`, em Grupo → Casas.
- **2026-10-26 · Estado F não conta.** Um documento «faturado» (F) já foi incluído noutro, e contá-lo seria contar a venda duas vezes. A especificação não é clara sobre se entra nos totais de controlo, por isso o aviso de totais diferentes aceita as duas somas. Confirmar com o ficheiro real.
- **2026-10-26 · Totais de controlo só avisam.** Uma diferença entre os totais de `SalesInvoices` e as linhas lidas assinala a importação em vez de a recusar: recusar podia bloquear um ficheiro real por uma diferença de interpretação. O critério de aceitação continua a ser o total do mês igual ao do relatório do POS.
- **2026-10-26 · O mesmo ficheiro outra vez é recusado**, com «Nada mudou», em vez de criar uma importação vazia. O hash é o do XML, por isso o mesmo ficheiro dentro e fora de um .zip é o mesmo.
- **2026-10-26 · Horas previstas só nos dias sem ponto.** O plano dizia «na semana em planeamento, usam-se as horas previstas nos turnos». As vendas são sempre de dias passados, por isso a regra ficou: num dia com vendas e sem registos de ponto, mas com turnos publicados, usam-se as horas dos turnos, assinaladas «prev.».
- **2026-10-26 · Comparação com os mesmos dias.** Um período que ainda não está todo importado (o mês corrente) compara-se com os mesmos dias do período anterior. Sem isto, outubro até dia 25 aparecia 15 % abaixo de setembro inteiro.
- **2026-10-26 · Importação no próprio pedido.** Sem fila de tarefas (secção 2): um mês lê-se e grava-se em poucos segundos. Se um ficheiro real demorar demais, passa para segundo plano.
- **2026-10-26 · `SourceID` guardado, não ligado.** O operador do POS fica em cada documento, como o plano previa, mas não aparece em nenhum ecrã nem se liga ao trabalhador até haver a decisão da secção 12.
- **2026-10-26 · Service worker para v8.** O CSS mudou com o ecrã Vendas.

- **2026-10-26 · Admin do grupo como atributo da conta, e casa por omissão mantida.** O plano previa o Admin do grupo «no `Organization`»: ficou `User.is_group_admin` com `User.organization`, sem uma linha de acesso por casa, para que uma casa nova lhe fique logo visível. `User.restaurant` e `User.role` ficam como casa e perfil por omissão, com um signal que mantém a linha de acesso dessa casa; assim o código e os testes que criam contas com casa e perfil continuam certos. O acesso real é sempre o de `Membership`.
- **2026-10-26 · Service worker para v7.** O CSS mudou com a Fase 9 (seletor de casa, área do grupo).
- **2026-10-26 · A V1.1 e parte do Futuro passam a fases do plano.** Os fornecedores e compras, os consumos internos, as fichas técnicas, a atualização de stock por vendas, os relatórios e os vários restaurantes deixam de estar só na secção 10 e passam às Fases 9 a 15. A ligação ao POS faz-se pelo ficheiro SAF-T e não pela API, porque o cliente de teste já o extrai e porque funciona com qualquer POS certificado. «Multi-tenant preparado, não exposto» (secção 2) deixa de valer a partir da Fase 9.
- **2026-10-25 · O gerente cancela ausências aprovadas.** Até aqui só o colaborador cancelava (R-056). No calendário, o gerente cancela uma ausência aprovada que ainda não acabou, para desfazer uma marcação errada. As que já acabaram ficam, porque contam no saldo e no mês. Um pedido pendente recusa-se.
- **2026-10-25 · Service worker para v6 e CSS antigo em desenvolvimento.** O service worker serve `/static/` primeiro da cache, sem revalidar. Em desenvolvimento, o `app.css` tem sempre o mesmo nome, por isso as classes novas só chegam ao browser quando a versão da cache muda ou com Ctrl+Shift+R. Em produção, o `whitenoise` dá um nome com hash a cada versão do CSS e o problema não existe. Sempre que o CSS mudar em desenvolvimento, subir a versão (`CACHE` em `static/sw.js`).
- **2026-10-25 · Código de ponto na ficha, não na conta.** Quem não tem email pica na mesma; ter conta da app é opcional. A migração copiou os PINs existentes sem os pedir de novo.
- **2026-10-25 · Sem fila offline.** Desaparecem o `marcado_em` enviado pelo cliente e o cabeçalho `X-Opero-Fila`: a hora da marcação é sempre a do servidor. `TimeEntry.Source.TELEMOVEL` fica nas escolhas para os registos antigos, mas já nada o cria.
- **2026-10-25 · Token de marcação com valor aleatório e de uso único.** O `signing` só tem resolução de segundos: sem o valor aleatório, duas marcações da mesma pessoa no mesmo segundo davam o mesmo token, e a segunda passava por repetida. O uso único fica na cache e trava também o duplo toque.
- **2026-10-25 · Bloqueio do código por trabalhador, não por dispositivo.** O quiosque não tem sessão. Um colega pode bloquear o código de outro durante um minuto, o que se aceita.
- **2026-10-25 · Cache local (LocMem) por agora.** O bloqueio do código e o uso único dos tokens vivem na cache de cada processo. Com vários processos em produção, passam a precisar de uma cache partilhada (a cache em base de dados do Django chega). Fica para o ambiente de demonstração da Fase 4.
- **2026-10-25 · Sessões PIN antigas.** As que já estavam abertas antes desta mudança continuam válidas até expirar (no máximo 12 horas) e passam a ver a app nova. Não se invalidaram à força.
- **2026-10-25 · «Conta de acesso» no formulário do trabalhador mantida.** Serve para ligar uma conta que já existe, por exemplo a do gerente. As contas novas criam-se em «Conta da app».
- **2026-10-25 · Hasher rápido e cache limpa nos testes** (`tests/conftest.py`). O hasher de produção fazia a suite demorar 8 minutos.
- **2026-09-04 · whitenoise acrescentado ao stack** (servir estáticos em produção sem depender do proxy; em dev `WHITENOISE_AUTOREFRESH=True`). Refletido na tabela da secção 2 a 2026-10-24.
- **2026-09-04 · Tailwind fixado em v3.4.17** (a v4 abandonou o `tailwind.config.js`; o plano assume config JS). Tokens de cor definidos como triplos RGB em `input.css` para os modificadores de opacidade (`/25`) funcionarem.
- **2026-09-04 · Fila offline em app.js, não no service worker** — o SW só faz cache do shell (GET); os POST falhados do ponto entram numa fila em localStorage gerida pela página, que reenvia com `marcado_em` ao voltar a rede. Mais simples de depurar que interceção de POST no SW, e cumpre o requisito do timestamp original. Limite: o servidor recusa `marcado_em` no futuro.
- **2026-09-04 · Dispositivo do restaurante = cookie assinado** (`django.core.signing`, 180 dias), ativado pelo gerente em /conta/dispositivo/. O ecrã de PIN devolve 403 fora de dispositivos ativados; a lista de trabalhadores nunca é pública.
- **2026-09-04 · Registo manual de ponto pelo gerente** — o plano previa só «correção de registo»; acrescentou-se «acrescentar registo em falta», que nasce auditado (autor + motivo), porque na prática há dias inteiros sem marcação. É correção no espírito da invariante 5.
- **2026-09-04 · Pedido de férias criado pelo gerente** — até a Fase 3 dar a vista staff, o backoffice permite registar pedidos em nome do trabalhador; sem isto a aceitação da Fase 2 não era testável de ponta a ponta. *A Fase 5 muda isto:* um pedido registado pelo gerente passa a nascer aprovado (R-057).
- **2026-09-04 · Stock não pode ficar negativo** — o plano não se pronunciava; `register_movement()` rejeita saídas e ajustes que deixem `current_stock < 0`, com mensagem a sugerir ajuste prévio. Racional: um ajuste negativo abaixo de zero implicaria uma contagem física negativa, impossível.
- **2026-09-04 · Artigos não se apagam** — desativam-se (`is_active`), porque os movimentos os protegem (`on_delete=PROTECT`) e o histórico não se perde. O "D" do CRUD de artigos é a desativação.
- **2026-09-04 · Grupos criados por data migration** (`accounts/0002`), com sincronização `role`→grupo em signal `post_save`. A autorização efetiva nas views é feita pelos mixins; os grupos mantêm o admin coerente.
- **2026-10-24 · Entrada esquecida não bloqueia a seguinte.** O plano dizia que um registo por resolver não contava para os totais, mas não dizia o que acontecia à entrada seguinte, que a constraint do turno aberto único recusava. Agora, ao marcar uma entrada nova, o registo antigo fica com `missing_exit` e a constraint ignora-o. Nenhuma hora de saída é inventada.
- **2026-10-24 · Pedido de correção sem «apagar».** O plano previa criar, alterar ou apagar. Apagar um registo apagaria também o seu histórico de correções, contra a invariante 7. Um registo a mais resolve-se com o gerente, que o corrige; se fizer falta, entra um estado «anulado» em vez de um delete.
- **2026-10-24 · Tipos de ausência sem anexos.** `requires_attachment` ficou de fora: guardar baixas médicas obriga a ficheiros privados com acesso controlado e a uma decisão de RGPD (BR-006). Entra quando essa decisão estiver tomada.
- **2026-10-24 · Feriados calculados, sem a biblioteca `holidays`.** São treze datas fixas ou derivadas da Páscoa, em `vacations/holidays.py`, e não se guardam na base de dados. O Carnaval não é obrigatório e fica de fora; acrescenta-se como feriado do restaurante.
- **2026-10-24 · Pedido sem tipo é de férias.** O formulário e o modelo assumem o tipo que desconta do saldo quando não vem nenhum, para manter o pedido em três campos da Fase 3.
- **2026-10-24 · `days_taken` calculado na submissão.** Se o planeamento mudar depois (uma folga nova, uma semana publicada), os dias de um pedido já feito não são recalculados.
- **2026-10-24 · Alterar um turno publicado tira-o da vista do colaborador** até à publicação seguinte: editar passa-o a rascunho, apagar marca-o para remoção. Assim o colaborador nunca vê uma versão que o gerente não confirmou, à custa de deixar de ver o turno antigo entretanto.
- **2026-10-24 · Configuração na aplicação, não no admin do Django.** Substitui a nota anterior sobre áreas e tipos de pausa. Os turnos guardados ficam na mesma área, mas abertos ao gerente.
- **2026-10-24 · Fase 5 arrancada antes da aprovação da AT.** Decisão do TM. O primeiro bloco (áreas, dia de trabalho, pausas, histórico de correções) não muda nenhum comportamento que a AT tenha validado, mas o âmbito da fase continua por aprovar (secção 12).
- **2026-10-24 · Campos de correção no `TimeEntry` mantidos como cópia.** O plano dizia que `corrected_by`, `correction_reason` e `corrected_at` passavam a ser derivados da última correção. Ficaram como campos, atualizados pelo serviço na mesma transação que grava a `EntryCorrection`, para não mudar templates e consultas que já os usam. A fonte de verdade é o histórico.
- **2026-10-24 · Sem `time-machine` por agora.** O teste da mudança de hora (`test_work_date_across_dst_change`) passa as horas explicitamente aos serviços. A dependência entra quando os registos por resolver e o fecho do mês precisarem de mexer no relógio.
- **2026-10-24 · Marcação com intenção explícita.** Antes, `MarkView` alternava o estado: entrava se não houvesse turno aberto e saía se houvesse. Agora o formulário envia a ação que o botão mostrava, e o servidor recusa-a se o estado já mudou. Sem `acao`, continua a alternar, por compatibilidade com marcações antigas que estejam na fila.
- **2026-10-24 · Cookies de dispositivo antigos contam como partilhados.** É o caso mais seguro. O telemóvel pessoal de um colaborador tem de ser reativado com o modo «Uma só pessoa».
- **2026-10-23 · Estudo da Factorial (fontes públicas)** em `re-factorial/` (repo git próprio, fora do git deste projeto). Recomendações em `re-factorial/clone/prd.md` e `clone/implications.md`: áreas de trabalho (cozinha, sala, bar), dia de trabalho para turnos que passam a meia-noite, pausas, correções pedidas pelo colaborador com histórico, fecho do mês, tipos de ausência e saldo, e um planeador de turnos com rascunho e publicação. A 2026-10-24 entraram no plano como Fases 5 e 6, com o âmbito a validar com a AT (secção 12). Validação jurídica do registo de tempos pendente (Q-001 do estudo).
