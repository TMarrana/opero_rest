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
| 5 — Ponto e ausências, segunda iteração | ⬜ Por iniciar (âmbito a validar com AT) |
| 6 — Planeador de turnos | ⬜ Por iniciar (âmbito a validar com AT) |

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

**Não é** um ERP, um POS nem software de contabilidade.

### Desvio assumido face ao documento de origem

O docx trata a interface como mínima ("navegação simples", dashboard sem gráficos). Este plano eleva deliberadamente o nível de acabamento do frontend, por decisão do TM, porque os utilizadores finais mais frequentes são pessoal de cozinha e sala a usar telemóvel em serviço. Concretamente, acrescenta-se ao âmbito:

| Adição | Estado |
|---|---|
| Sistema de design próprio (secção 4) | Decidido |
| Vista móvel dedicada ao colaborador, separada do backoffice | Decidido |
| PWA instalável | Decidido |
| Login por PIN para marcar ponto | **A validar com AT** (secção 7) |
| Fases 5 e 6: pausas, fecho do mês, saldo de férias, planeador de turnos | **A validar com AT** (secção 12) |

Tudo o resto neste documento deriva do docx, exceto as Fases 5 e 6. Essas vêm do estudo da Factorial (`re-factorial/clone/prd.md`) e incluem duas coisas que o docx deixou fora do MVP: o saldo anual de férias e o planeamento visual de equipa.

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
| Testes | `pytest-django`, `pytest-cov` | |

**HTMX e Alpine são vendored** em `static/js/`, não carregados de CDN: a PWA precisa de shell offline e a rede de um restaurante não é de confiança.

### Decisões estruturais

- **`AbstractUser` custom desde a primeira migração.** Trocar o modelo de utilizador depois de existirem dados é uma operação dolorosa. Faz-se no dia 1, mesmo que comece sem campos extra.
- **Permissões por Django Groups**, um por perfil, mais mixins de verificação explícita nas views. Não confiar apenas em esconder botões no template.
- **Multi-tenant preparado, não exposto.** Existe `core.Restaurant` e todos os modelos operacionais têm FK `restaurant` desde o início — acrescentar isto mais tarde obriga a migrar dados existentes. Mas o MVP serve **um restaurante por instância**: não há seletor de restaurante na UI nem middleware de tenant. O docx deixa em aberto se cada cliente terá domínio próprio, subdomínio ou área partilhada; esta abordagem não fecha nenhuma dessas portas.

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
  accounts/                 # User, perfis, login email+password, login PIN
  workers/                  # Worker
  attendance/               # TimeEntry
  vacations/                # VacationRequest
  inventory/                # Category, Item, StockMovement
  dashboard/                # vista agregada do gerente
  staff/                    # vista do colaborador (mobile)

  templates/
    base_manage.html        base_staff.html
    components/             botao, campo, badge, talao, tabela, modal, toast
    manage/                 um diretório por módulo
    staff/                  ponto, historico, ferias
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

**Princípio de partida: isto é _back of house_, não sala.** A estética óbvia de restaurante — creme quente, serifa editorial, terracota — é a da carta e do menu. Está errada para uma ferramenta operacional usada por quem está do outro lado da porta de vaivém. O vocabulário visual vem da cozinha: aço, contraste alto, legibilidade sob luz má e com pressa.

### Paleta

Definida como CSS custom properties em `static/src/input.css` e exposta ao Tailwind em `theme.extend.colors`.

| Token | Hex | Uso |
|---|---|---|
| `carvao` | `#14171C` | shell da vista staff; texto principal no backoffice |
| `aco` | `#E8ECEF` | fundo do backoffice |
| `superficie` | `#FFFFFF` | cartões, tabelas, formulários |
| `chama` | `#FF4D14` | sinal único: stock abaixo do mínimo, ações irreversíveis |
| `servico` | `#00C27A` | estado "em serviço", turno aberto, aprovado |
| `ardosia` | `#5A6672` | texto secundário, labels, metadados |

Uma só cor quente e uma só cor de estado. Tudo o resto é neutro. **Se um ecrã tem duas coisas cor de laranja, uma delas está errada.**

### Tipografia

Três papéis. Ficheiros servidos localmente a partir de `static/fonts/`, sem chamadas ao Google Fonts.

| Papel | Face | Onde |
|---|---|---|
| Display | **Archivo** | títulos de ecrã, o botão de ponto |
| Corpo | **IBM Plex Sans** | formulários, listagens, prosa |
| Dados | **IBM Plex Mono** | quantidades, horas, datas, referências |

**Regra transversal: todos os números do sistema são mono, com figuras tabulares.** É o que dá coerência às duas superfícies e o que faz uma coluna de quantidades alinhar e ler-se de relance.

### Elemento de assinatura — o passe

O histórico é apresentado como uma sequência de **talões de serviço**: bloco mono, filete tracejado a separar, timestamp em cima, autor em baixo. Usado nos dois lados — histórico de movimentos de stock do gerente e histórico de turnos do colaborador.

Não é decoração. O talão comunica visualmente a invariante central do sistema: *o stock só muda por movimento, e os movimentos nunca se apagam*. Um talão acrescenta-se ao rail; não se rasga.

Sem bordas rasgadas, sem textura de papel, sem skeuomorfismo. Um bloco mono e um filete. A ideia é forte; a execução é contida.

### Ergonomia

Alvos de toque ≥48px na vista staff. Contraste AA. `prefers-reduced-motion` respeitado. Foco de teclado visível no backoffice.

---

## 5. Duas superfícies

São dois produtos sobre o mesmo backend, não um produto com menus condicionais.

### `base_staff.html` — vista do colaborador

Mobile-first, shell escuro (`carvao`), coluna única, ação na zona do polegar. Três coisas e nada mais.

```
┌───────────────────┐
│  Olá, Marta       │
│  09:14 · Terça    │
│                   │
│  ┌─────────────┐  │   fora de turno: `servico`, "ENTRADA"
│  │             │  │   em turno:      `chama`, cronómetro + "SAÍDA"
│  │   ENTRADA   │  │   Archivo, caps, ~40% do ecrã
│  │             │  │
│  └─────────────┘  │
│                   │
│  Hoje     —       │   mono, tabular
│  Semana   32h10   │
│                   │
│  Histórico  Férias│
└───────────────────┘
```

**O botão é o ecrã.** O estado do turno determina cor, label e ação; um único `hx-post` devolve o fragmento do botão já no novo estado. Sem menu, sem navegação hierárquica, sem tabelas.

### `base_manage.html` — backoffice

Desktop-first, funcional em tablet. Rail de navegação fixo à esquerda com as seis áreas do docx:

`Dashboard · Trabalhadores · Ponto · Férias · Stock · Configuração`

Conteúdo denso, tabelas com pesquisa e filtros, figuras mono alinhadas à direita, histórico sempre a um clique de distância de qualquer ação que altere stock, ponto ou férias.

---

## 6. Modelo de dados

### `core`

**`Restaurant`** — `name`, `slug`, `is_active`, timestamps.
**`TimeStampedModel`** (abstract) — `created_at`, `updated_at`. Base de tudo o resto.

### `accounts`

**`User(AbstractUser)`** — `email` como `USERNAME_FIELD`, `restaurant` (FK), `role` (choices: `ADMIN`, `MANAGER`, `STOCK`, `STAFF`), `staff_pin` (hash, nullable), `pin_set_at`.

### `workers`

**`Worker`** — `restaurant` (FK), `full_name`, `contact`, `job_title`, `is_active`, `user` (OneToOne, nullable), `start_date` (nullable), `notes`.

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

### Invariantes — implementar e testar

Estas regras são o núcleo do sistema. Cada uma tem um teste dedicado na secção 11.

1. **O stock nunca é editado diretamente no artigo.** `Item.current_stock` só muda através de um `StockMovement`, num serviço `inventory/services.py::register_movement()` dentro de `transaction.atomic()` com `select_for_update()` sobre o item. Nenhuma view escreve `current_stock`.
2. **Movimentos não se apagam.** Sem delete na UI nem no admin. Correções fazem-se com novos movimentos de ajuste, preservando o histórico.
3. **Um trabalhador não pode ter dois turnos abertos.** `UniqueConstraint` parcial (`worker`, `check_out__isnull=True`) mais validação no serviço.
4. **Não há saída sem entrada prévia.** Marcar saída sem turno aberto é rejeitado com mensagem clara.
5. **Cada registo guarda data, hora e utilizador.** Ponto, movimentos e decisões de férias.
6. **Pedidos de férias aprovados não se apagam.** E o sistema avisa visualmente quando um pedido se sobrepõe a outro já aprovado do mesmo trabalhador.

---

## 7. Perfis, permissões e autenticação

### Matriz de acesso

| Ação | Admin | Gerente | Resp. stock | Colaborador |
|---|:--:|:--:|:--:|:--:|
| Criar utilizadores, atribuir perfis | ✓ | | | |
| Configurações do restaurante | ✓ | | | |
| Gerir trabalhadores | ✓ | ✓ | | |
| Consultar ponto da equipa | ✓ | ✓ | | |
| Corrigir registo de ponto (auditado) | ✓ | ✓ | | |
| Aprovar / recusar férias | ✓ | ✓ | | |
| Criar e editar artigos | ✓ | ✓ ⚠ | ✓ | |
| Registar movimentos de stock | ✓ | ✓ ⚠ | ✓ | |
| Consultar stock, alertas e histórico | ✓ | ✓ | ✓ | |
| Marcar o próprio ponto | ✓ | ✓ | ✓ | ✓ |
| Ver o próprio histórico | ✓ | ✓ | ✓ | ✓ |
| Submeter pedido de férias | ✓ | ✓ | ✓ | ✓ |

Regras que decorrem do docx:

- O colaborador não vê férias, horários nem consumos de outros colaboradores.
- O colaborador não edita artigos nem altera stock.
- O responsável de stock não gere permissões de utilizadores.
- Nenhum utilizador comum apaga movimentos de stock.
- O número de administradores deve ser reduzido.

⚠ **Decisão a validar com AT** (sinalizada no próprio docx): se o gerente também pode criar artigos e registar movimentos, ou se isso é exclusivo do responsável de stock. **Pressuposto atual: pode.** É mais permissivo, e restringir depois é uma linha de código; alargar depois obriga a repensar fluxos.

### Dois caminhos de autenticação

| Caminho | Quem | Dá acesso a |
|---|---|---|
| Email + password | Admin, Gerente, Resp. stock | backoffice completo |
| PIN | qualquer trabalhador | **apenas** a vista staff |

Fronteira de segurança explícita: **um PIN nunca abre o backoffice**, mesmo que o titular seja gerente. Quem gere entra por email e password.

Implementação do PIN: hash com o hasher de passwords do Django, throttling por tentativas falhadas, dispositivo do restaurante identificado por token de sessão de longa duração, PIN reposto pelo gerente.

⚠ **Decisão a validar com AT.** O docx exclui geolocalização, QR code, biometria e relógio físico, mas não se pronuncia sobre PIN. Racional: obrigar pessoal de cozinha a escrever email e password em serviço torna o registo de ponto inutilizável, o que põe em risco o próprio módulo. Mitigante: o PIN dá a menor superfície de acesso possível — o próprio ponto, o próprio histórico e o próprio pedido de férias.

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

- [x] Login por PIN e ecrã de seleção de trabalhador no dispositivo do restaurante.
- [x] Ecrã de ponto com o botão de estado descrito na secção 5.
- [x] Histórico próprio em talões; totais do dia e da semana em mono.
- [x] Pedido de férias em três campos: início, fim, observação.
- [~] `manifest.webmanifest`, ícones, service worker com o shell em cache.
- [~] Marcações feitas offline entram em fila e sincronizam ao voltar a rede — com o timestamp do momento da marcação, não do envio.

*Aceitação:* um colaborador instala a aplicação no telemóvel, entra com PIN e marca entrada e saída em **menos de 5 segundos e 2 toques**, sem formação prévia.

---

### Fase 4 — Dashboard, estabilização e piloto
*P0-19, P0-22, P0-23. Depende de: Fases 1 a 3, P0-20 e P0-21 (AT).*
**Estado:** 🟡 Em curso

- [x] Dashboard do gerente, sem gráficos sofisticados: contador de artigos com stock baixo, últimos movimentos, pedidos de férias pendentes, quem está em turno.
- [ ] Correção de bugs P0 e P1 encontrados nos testes funcionais do AT.
- [ ] Ambiente de demonstração: domínio, hosting, HTTPS, backups, utilizadores de teste. *(bloqueado pelas decisões de hosting/domínio da secção 12)*
- [x] Fixtures de dados de exemplo para demonstração e para o percurso dos quatro perfis. *(`python manage.py demo`, idempotente)*

---

### Fase 5 — Ponto e ausências, segunda iteração
*Fora do docx. Vem do estudo da Factorial (`re-factorial/clone/prd.md`, prioridade P1). Depende de: Fases 2 e 3, de a AT aprovar o âmbito e da validação jurídica do registo de tempos (secção 12).*
**Estado:** ⬜ Por iniciar

O MVP regista entradas e saídas. Esta fase dá ao gerente o que precisa para fechar o mês e prová-lo ao contabilista ou a uma inspeção. A ordem dos blocos é a de construção: cada um assenta no anterior.

**Modelo de dados e persistência**

- [ ] `core.WorkArea` (`restaurant`, `name`, `archived_at`): cozinha, sala, bar. O dispositivo do restaurante passa a estar associado a uma área, e cada marcação herda a área do dispositivo onde foi feita.
- [ ] `TimeEntry.work_date`: o dia de trabalho é o dia da entrada, e um turno das 19h às 2h conta todo no dia em que começou. Uma data migration preenche o campo a partir de `check_in`. Hoje os totais da vista staff já seguem esta regra (`staff/views.py::_totais`), mas a vista da equipa (`TeamDayView`) mostra o mesmo turno nos dois dias. As duas passam a agrupar por `work_date`.
- [ ] `TimeEntry.work_area` e `TimeEntry.source` (quiosque, telemóvel, gerente).
- [ ] Pausas: `attendance.BreakType` (`name`, `paid`, `archived_at`) e `attendance.Break` (`entry`, `start`, `end`, `break_type`). As pausas não pagas não contam para os totais. Na primeira versão as pausas são marcadas à mão; as pausas automáticas ficam para depois.
- [ ] Histórico de correções: hoje `correct_entry()` escreve por cima do registo e o valor anterior perde-se. Cada correção passa a guardar os valores antigos e os novos, com autor, motivo e data.

**Ecrãs do ciclo principal**

- [ ] Ecrã de ponto do colaborador com pausa: em turno, o ecrã mostra «Iniciar pausa» e «Saída»; em pausa, mostra «Terminar pausa». Continua a ser um único botão de estado principal (secção 5), e cumpre a aceitação da Fase 3 (5 segundos, 2 toques).
- [ ] Pedido de correção pelo colaborador (`attendance.CorrectionRequest`: `entry`, `kind` com criar, alterar ou apagar, valores antigos e novos, `status`, `decided_by`). O gerente aprova ou recusa, e a decisão fica registada no histórico de correções.
- [ ] Registos por resolver: uma entrada sem saída que passe de um limite fixo (valor a decidir, por exemplo 14 horas) fica pendente e não conta para os totais até o gerente a resolver. Na Fase 6 este limite passa a vir das horas previstas no turno.

**Ausências**

- [ ] Tipos de ausência (`vacations.AbsenceType`: `name`, `color`, `deducts_balance`, `requires_approval`, `requires_attachment`, `half_days`). `VacationRequest` ganha `absence_type`, `half_day` e `days_taken`. As férias passam a ser um tipo entre outros: falta justificada, baixa, licença.
- [ ] Saldo anual (`vacations.Allowance`: `worker`, `year`, `days`, `carried_over`, `carry_over_expires_on`). O saldo aparece no pedido e na decisão. O valor por defeito português (22 dias úteis) está por validar (secção 12).
- [ ] Feriados (`vacations.Holiday`: `restaurant`, nulo para os nacionais, `date`, `name`, `half_day`). Os feriados nacionais vêm de origem, os municipais são acrescentados por restaurante, e o cálculo de `days_taken` não conta feriados nem folgas.
- [ ] Períodos bloqueados (`vacations.BlockedPeriod`: `restaurant`, `start`, `end`, `absence_types`, `exempt_workers`). Um pedido que caia num período bloqueado é recusado na submissão, com uma mensagem que diz porquê.

**Fecho do mês**

- [ ] `attendance.MonthClose` (`restaurant`, `month`, `worker`, `approved_by`, `approved_at`). O gerente aprova o mês por trabalhador, e só o pode fazer quando não restam registos por resolver nem pedidos de correção pendentes.
- [ ] Depois de aprovado, um mês fica bloqueado: não aceita correções, registos manuais nem pedidos de correção. Para reabrir, é preciso uma ação explícita, auditada e com motivo.
- [ ] Exportação do mês aprovado (CSV na primeira versão), num formato a acordar com o contabilista (secção 12).

*Invariantes novas, que passam para a secção 6 quando a fase arrancar:*

7. **Uma correção nunca apaga o valor anterior.** O histórico de correções guarda o antes e o depois.
8. **Um mês aprovado não muda** sem que seja reaberto de forma explícita e auditada.
9. **Um registo por resolver não conta para os totais.**

*Aceitação:* um colaborador marca entrada, uma pausa não paga e saída num turno que passa a meia-noite. O gerente vê o turno num só dia, com a pausa descontada. O colaborador pede uma correção, que o gerente aprova, e o valor anterior fica no histórico. Por fim, o gerente aprova o mês e exporta-o, e a partir daí o mês recusa alterações.

---

### Fase 6 — Planeador de turnos
*Fora do docx. Vem do estudo da Factorial (prioridade P1). Depende de: Fase 5 (áreas de trabalho, tipos de ausência) e de a AT aprovar o âmbito.*
**Estado:** ⬜ Por iniciar

Módulo novo, numa app `shifts`. É o primeiro passo do ciclo semanal do gerente: planear e publicar a semana, e depois comparar o planeado com o realizado.

- [ ] `shifts.ShiftTemplate` (`restaurant`, `name`, `start`, `end`, `work_area`, `color`): turnos guardados, como «Almoço» ou «Jantar».
- [ ] `shifts.Shift` (`worker`, `start_at`, `end_at`, `work_area`, `state` com rascunho, publicado ou reserva, `template`). A grelha semanal é organizada por trabalhador e pode ser filtrada por área.
- [ ] Copiar a semana anterior: os turnos copiados nascem em rascunho.
- [ ] Folgas (`shifts.RestDay`: `worker`, `date`, `state`).
- [ ] Ausências no planeador: as férias aprovadas e as outras ausências aparecem na grelha. Um turno marcado sobre uma ausência, uma folga ou outro turno é assinalado como conflito.
- [ ] Publicar a semana: o colaborador só vê os turnos publicados. A vista staff ganha «Os meus turnos», um quarto elemento além dos três que a secção 5 previa, o que é uma alteração a validar visualmente.
- [ ] As horas previstas no turno substituem o limite fixo dos registos por resolver da Fase 5.

*Invariante nova:* 10. **O colaborador nunca vê um turno em rascunho.**

*Aceitação:* o gerente copia a semana anterior, ajusta dois turnos a partir dos turnos guardados, marca uma folga e vê um conflito com férias aprovadas. Depois de o resolver, publica a semana, e o colaborador vê os seus turnos no telemóvel.

---

## 9. Estados e feedback

Regra transversal, aplicada em todos os ecrãs das duas superfícies.

- **Toast de confirmação** em todas as ações de escrita, com o mesmo verbo do botão que a despoletou: "Registar entrada" → "Entrada registada".
- **Indicador de loading** (`hx-indicator`) em todas as ações HTMX; botão desativado durante o pedido, para eliminar duplos submits.
- **Ecrãs vazios com instrução e a ação seguinte.** Nunca "sem dados": "Ainda não há artigos. Comece por criar o primeiro."
- **Erros em português simples**, que dizem o que falhou e como resolver. Não pedem desculpa, não são vagos.
- **Confirmação explícita** antes de ações irreversíveis: ajuste de stock, recusa de férias, correção de ponto.
- Uma ação principal clara por ecrã. Formulários curtos. Listagens sempre com pesquisa.

---

## 10. Fora do âmbito

### V1.1 — só depois do MVP estável num cliente piloto
Fornecedores, lista de compras, encomendas e receção com geração de entradas. Consumos internos por colaborador. Relatórios básicos: artigos mais movimentados, histórico de ajustes, compras por fornecedor, presenças e ausências.

### Futuro
Integração com POS e atualização de stock por vendas. Fichas técnicas e receitas. Previsão de compras. Multi-restaurante com painel de grupo. Aplicação móvel nativa. Integrações contabilísticas. Alertas por email, SMS ou WhatsApp. Gestão de validade e lotes. Relatórios financeiros avançados.

**Nada desta lista entra no MVP.** Construir agora põe em risco o prazo e a qualidade da primeira versão.

### Depois das Fases 5 e 6 (estudo da Factorial, prioridades P2 e P3)
- **P2:** trocas de turno entre colegas (precisam de notificações push na PWA; testar em iOS primeiro), uma caixa de pedidos única no dashboard (férias, correções e trocas), horas extra com um só nível de aprovação, cobertura mínima por área e hora, e horários fixos para quem não faz turnos.
- **P3:** geolocalização na marcação, só em modo de alerta e só depois de uma avaliação de impacto (AIPD), e equipas e contratos para grupos com várias casas.

### Não fazer
Reconhecimento facial e biometria. Contadores de férias para vários países. Aprovação em vários níveis. Grupos de permissões configuráveis, porque os quatro perfis da secção 7 chegam. API pública e marketplace.

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
| `test_pin_does_not_open_backoffice` | sessão criada por PIN é rejeitada em todas as views de gestão |
| `test_vacation_overlap_flagged` | sobreposição com pedido aprovado é assinalada |

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
| `test_staff_never_sees_draft_shift` | um turno em rascunho não aparece na vista staff (invariante 10) |

### Manual, por fase

Seguir os critérios de aceitação de cada fase (secção 8), que são os do docx.

### Antes do piloto

- Vista staff testada a 375px de largura **e num telemóvel real**, não só no emulador.
- Instalação da PWA verificada em Android e iOS.
- Percurso completo dos quatro perfis com as fixtures de demonstração.
- Build do Tailwind a correr em produção sem watch, com `--minify`.
- `collectstatic`, HTTPS, backups e restauro de backup testado uma vez.

---

## 12. Decisões em aberto

Bloqueiam a Fase 4, não a Fase 0. O desenvolvimento começa sem elas.

| Decisão | Quem | Impacto técnico |
|---|---|---|
| Nome final da marca e domínio | AT | branding, `ALLOWED_HOSTS`, ícones da PWA |
| Hosting e ambiente de produção | TM | settings de produção, deploy, custos |
| Isolamento por cliente: domínio, subdomínio ou área partilhada | AT + TM | middleware de tenant; o modelo já está preparado |
| RGPD e tratamento de dados de trabalhadores | AT | retenção, exportação, consentimento, política de privacidade |
| Política de backups e recuperação | TM | frequência, retenção, teste de restauro |
| Permissões do gerente sobre stock (⚠ secção 7) | AT | uma linha nos mixins |
| PIN para o staff (⚠ secção 7) | AT | Fase 3 completa depende disto |
| Cliente piloto e disponibilidade semanal AT/TM | AT | calendário das sprints |
| Âmbito das Fases 5 e 6 (saldo anual e planeamento, que o docx exclui do MVP) | AT | se as fases arrancam e em que ordem face ao piloto |
| Validação jurídica do registo de tempos, férias e descansos (Código do Trabalho; Q-001 e Q-010 do estudo) | AT, com contabilista ou jurista | pode bloquear o piloto; define os valores por defeito da Fase 5 |
| Formato da exportação mensal | AT, com o contabilista | formato do ficheiro na Fase 5 |

---

## 13. Referência ao plano de produto

As tarefas P0-01 a P0-09, P0-20, P0-21 e P0-24 são do AT — definição de requisitos, desenho de fluxos, cenários de teste e guia do cliente piloto. Não são trabalho de engenharia e não estão detalhadas aqui; entram neste plano como dependências de entrada das fases, indicadas em cada uma.

---

## 14. Registo de progresso

Uma linha por sessão de trabalho, a mais recente em cima. Preencher sempre antes de terminar a sessão — ver o protocolo na secção 0.

O campo **Próximo passo** é o mais importante: é o que a sessão seguinte lê primeiro.

| Data | Fase | O que foi feito | Por fechar | Próximo passo |
|---|---|---|---|---|
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

- **2026-09-04 · whitenoise acrescentado ao stack** (servir estáticos em produção sem depender do proxy; em dev `WHITENOISE_AUTOREFRESH=True`). Refletido na tabela da secção 2? Não — a tabela lista camadas principais; whitenoise fica registado aqui e em `requirements.txt`.
- **2026-09-04 · Tailwind fixado em v3.4.17** (a v4 abandonou o `tailwind.config.js`; o plano assume config JS). Tokens de cor definidos como triplos RGB em `input.css` para os modificadores de opacidade (`/25`) funcionarem.
- **2026-09-04 · Fila offline em app.js, não no service worker** — o SW só faz cache do shell (GET); os POST falhados do ponto entram numa fila em localStorage gerida pela página, que reenvia com `marcado_em` ao voltar a rede. Mais simples de depurar que interceção de POST no SW, e cumpre o requisito do timestamp original. Limite: o servidor recusa `marcado_em` no futuro.
- **2026-09-04 · Dispositivo do restaurante = cookie assinado** (`django.core.signing`, 180 dias), ativado pelo gerente em /conta/dispositivo/. O ecrã de PIN devolve 403 fora de dispositivos ativados; a lista de trabalhadores nunca é pública.
- **2026-09-04 · Registo manual de ponto pelo gerente** — o plano previa só «correção de registo»; acrescentou-se «acrescentar registo em falta», que nasce auditado (autor + motivo), porque na prática há dias inteiros sem marcação. É correção no espírito da invariante 5.
- **2026-09-04 · Pedido de férias criado pelo gerente** — até a Fase 3 dar a vista staff, o backoffice permite registar pedidos em nome do trabalhador; sem isto a aceitação da Fase 2 não era testável de ponta a ponta.
- **2026-09-04 · Stock não pode ficar negativo** — o plano não se pronunciava; `register_movement()` rejeita saídas e ajustes que deixem `current_stock < 0`, com mensagem a sugerir ajuste prévio. Racional: um ajuste negativo abaixo de zero implicaria uma contagem física negativa, impossível.
- **2026-09-04 · Artigos não se apagam** — desativam-se (`is_active`), porque os movimentos os protegem (`on_delete=PROTECT`) e o histórico não se perde. O "D" do CRUD de artigos é a desativação.
- **2026-09-04 · Grupos criados por data migration** (`accounts/0002`), com sincronização `role`→grupo em signal `post_save`. A autorização efetiva nas views é feita pelos mixins; os grupos mantêm o admin coerente.
- **2026-10-23 · Estudo da Factorial (fontes públicas)** em `re-factorial/` (repo git próprio, fora do git deste projeto). Recomendações em `re-factorial/clone/prd.md` e `clone/implications.md`: áreas de trabalho (cozinha, sala, bar), dia de trabalho para turnos que passam a meia-noite, pausas, correções pedidas pelo colaborador com histórico, fecho do mês, tipos de ausência e saldo, e um planeador de turnos com rascunho e publicação. A 2026-10-24 entraram no plano como Fases 5 e 6, com o âmbito a validar com a AT (secção 12). Validação jurídica do registo de tempos pendente (Q-001 do estudo).
