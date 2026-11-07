# Revisão geral: registo da execução dos blocos A a D

Execução de 2026-11-07 do plano `2026-11-07-revisao-geral.md`, no ramo `worktree-revisao-geral`.
Este ficheiro guarda as decisões tomadas durante a execução e os problemas menores que ficaram
para depois. Foi copiado do registo de trabalho da execução (por isso o texto vem sem acentos),
que foi apagado no fim. Cada decisão diz o que custa se estiver errada.

## Decisões (41)

As «Ruling N» foram tomadas durante as tarefas; as «Final: Ruling» depois da revisão final do ramo.

- Ruling 1: A6 executa-se antes de A1 — o Step 1 da A6 commita o trabalho pendente do main; sem isso o primeiro implementador apanhava esses ficheiros nos commits dele — custo se errado: nenhum, so a ordem muda.
- Ruling 2: esta execucao cobre os blocos A a D (25 tarefas); E (pos-piloto, cada epico com brainstorming proprio) e F (hosting, juristas, aparelhos) ficam por marcar — o proprio plano manda esperar pelo piloto e F nao e codigo — custo se errado: o TM queria E ja; pode pedir um plano para um epico.
- Ruling 3: A4 nao faz push; valida o workflow localmente (YAML le-se, comandos do job sqlite correm localmente, ruff limpo) e o push fica para o fim, com o TM, no finishing-a-development-branch — push e um efeito fora do worktree que se pergunta primeiro — custo se errado: um job do CI (sobretudo o de PostgreSQL) pode falhar so quando houver push.
- Ruling 4: no teste 2 da A5, o utilizador que acrescenta o registo e de OUTRA casa (Restaurant + User criados no teste), para que `restaurant.delete()` so falhe por causa do PROTECT novo em TimeEntry — com o fixture `manager` (User.restaurant=PROTECT) o teste ja passava antes da mudanca — custo se errado: nenhum, o teste fica mais preciso.
- Ruling 5: as verificacoes no browser dos briefs ficam para uma passagem visual do controlador no fim (os implementadores registam-nas como pendentes) — evita abrir o Chrome 10 vezes — custo se errado: um defeito visual so aparece no fim e volta como correcao da revisao final.
- Ruling 6: o Step 4 (opcional) da A6 — arquivar o registo antigo do plan.md — nao se faz nesta execucao; e o documento vivo do TM e mexer-lhe em massa e uma escolha dele — custo se errado: o plan.md continua com 200 KB ate o TM pedir.
- Ruling 7: o brief da A6 lista a remocao do time-machine do plan.md §2 nos Files mas nenhum passo a faz; faz-se num commit proprio depois do Step 3 — custo se errado: nenhum.
- Ruling 8: os review packages geram-se com comandos git simples (`git log/diff --output=...`) e `cat`, porque o ambiente recusa `bash scripts/review-package` num worktree; os briefs foram extraidos com awk porque o task-brief procura titulos `Task N` e o plano usa `Tarefa A1` — custo se errado: nenhum, o conteudo e o mesmo.
- Ruling 9: cada subagente usa a linha Co-Authored-By que a instrucao de atribuicao do seu proprio ambiente lhe da (A6 ficou com Opus 5.5, A1 com Sonnet 5.5); contexto-comum.md atualizado — custo se errado: trailers mistos no historico, corrigiveis com rebase antes do merge.
- Ruling 10: o Important da B3 (link Gestao no inicio da app) entra no ambito apesar de home.html nao estar na lista de ficheiros do brief — o objetivo da tarefa (e a linha 12 do diagnostico) e passar entre as duas superficies, e o ecra inicial e a entrada principal — custo se errado: uma linha de template e um teste a mais.
- Ruling 11: na C5, o dia de servico (hora de corte) passa a valer para: turnos_de_hoje (e a escala), o subtitulo com a data do dashboard, o cartao "Em ferias", o cumprimento e o dia por omissao do Ponto do dia. O contador "Movimentos de hoje" do stock fica pelo dia do calendario — e um contador de stock, nao de servico, e mudar-lhe a janela pedia outra consulta — custo se errado: de madrugada esse contador conta so desde a meia-noite.
- Ruling 12: o ledger continua em .superpowers/sdd/2026-11-07-revisao-geral/; o sdd-workspace e o task-done da skill comparam `git rev-parse --show-toplevel` (C:/...) com `pwd -P` (/c/...) e criavam outro workspace (-plans, apagado); uso copias no scratchpad com o root normalizado por `cd root && pwd -P` e os briefs ja extraidos (Ruling 8) — custo se errado: nenhum, o ledger e os briefs sao os mesmos.
- Ruling 13: na C5 o implementador estendeu o dia de servico a ctx["hoje"] do Ponto do dia (aviso de dia passado), ao dia por omissao da exportacao mensal do Ponto e aos pendentes com datas passadas do dashboard; fica — e o mesmo hoje que o ecra mostra, e com o aviso no dia civil o proprio dia por omissao apareceria como dia passado de madrugada — custo se errado: na madrugada do dia 1 a exportacao sem ?dia= sai do mes anterior (o do dia que o ecra mostra).
- Ruling 14: o check opero.W001 (A1) dava falso positivo para sempre: o Tailwind v3 nao reescreve um CSS igual, a data do app.css ficava antiga e `manage.py css` nao calava o aviso (visto na C5: compilacao nova igual byte a byte, W001 ativo); corrigido ja, fora das tarefas, porque as tarefas D mexem em templates e o W001 e a prova de que o CSS foi recompilado — custo se errado: um commit a mais no ramo.
- Ruling 15: na C6 o cabecalho da coluna de vendas do painel do grupo passa de "Vendas de <Mes>" a "Vendas" (sai o ctx mes_atual): a legenda de cada casa ja diz o mes e o "ate"; com o cabecalho antigo o mes aparecia duas vezes por linha, e com maiuscula — custo se errado: uma palavra no cabecalho; a D2 refaz o painel em cartoes.
- Ruling 16: na C6 o nome do mes chega ao aviso "por fechar" por um filtro nome_do_mes registado em core/templatetags/interface.py (a mesma funcao de core.utils); o brief nao dizia como o template chega ao nome e interface.py nao estava nos Files — custo se errado: nenhum; a D1 pode move-lo para os filtros do core.
- Ruling 17: na C6 o cartao de vendas fica no mes do dia civil (o mesmo do total e do aviso de atraso); o dia de servico da C5 so vale onde a Ruling 11 diz — custo se errado: na madrugada do dia 1, ate a hora de corte, o cartao diz "Sem vendas de <mes novo>".
- Ruling 18: o teste do brief da D1 (stock negativo) criava a categoria "Mercearia", que cada casa nova ja tem (inventory/signals.py) -> IntegrityError antes de chegar ao comportamento; os testes usam get_or_create — custo se errado: nenhum.
- Ruling 19: a D1 acrescenta o filtro `unidade` (core.formatos.unidade, registado na interface) para os sitios que so mostram a unidade (ao lado de campos, opcoes "Arroz (kg)", data-unidade do Alpine, que so a mostra); o brief so previa `quantidade`, mas o seu teste exige que nenhum {{ x.unit }} fique em bruto — custo se errado: nenhum.
- Ruling 20: a D1 estende o formato aos dois toasts com quantidade e unidade (Stock negativo dos consumos; Transferido) — sao mensagens de stock como a de services.py:47, e o diagnostico fala de "mensagens de erro"; os testes que fixavam "-2 UN"/"1 UN" passam a "-2 un"/"1 un" — custo se errado: duas linhas.
- Ruling 21: na lista de compras o minimo (sem unidade) passa de numero a quantidade, para o stock e o minimo da mesma linha terem o mesmo formato — custo se errado: nenhum.
- Ruling 22: a D2 nao tem RED: o brief nao pede testes novos (mudanca de layout; a prova e no browser, scrollWidth <= innerWidth a 1280px e com o menu estreito), como o pre-flight registou; correm os testes do painel (test_varias_casas), da legenda (test_dashboard_vendas) e do menu — custo se errado: um defeito de layout so aparece na passagem visual final.
- Ruling 23: no painel em cartoes, text-alerta fica no stock baixo e no ponto por resolver (os dois sinais que o dashboard trata como alerta); ferias, correcoes e mes por aprovar ficam a negrito quando ha, como na tabela; "Abrir" passa a botao verde (btn-primario: a acao de cada cartao, §4) em vez de link-acao; "Por resolver" passa a "Ponto por resolver" porque fora da tabela perdia o contexto — custo se errado: classes e um rotulo num template.
- Ruling 24: na D3 as acoes da linha dos trabalhadores estao em templates/partials/workers/tabela_workers.html (incluido por lista.html); a mudanca e feita la, nao no lista.html que o brief indica — custo se errado: nenhum.
- Ruling 25: na D3 o menu e uma tag de bloco `{% menu_acoes %}...{% endmenu_acoes %}` (simple_block_tag do Django 5.2, em core/templatetags/interface.py) que desenha components/menu_acoes.html com as ligacoes e formularios de cada linha; o painel e `fixed`, posicionado pelo botao (a .cartao tem overflow-hidden e a tabela overflow-x-auto, que cortavam um menu absolute nas ultimas linhas), abre para cima quando nao cabe, e fecha com Esc (o foco volta ao botao), clique fora, scroll e resize; padrao de divulgacao (aria-haspopup="true", aria-expanded, aria-controls), como o menu da conta no cabecalho, sem role="menu" porque nao ha navegacao por setas — custo se errado: um template e uma tag.
- Ruling 26: a D3 ganha testes (o brief nao tinha): uma acao verde visivel e as outras dentro do menu, nas duas listas (RED antes: nenhum aria-haspopup na linha); test_inventory e test_people continuam a passar — custo se errado: nenhum.
- Ruling 27: na D5 o whitespace-nowrap do contacto vai para templates/partials/workers/tabela_workers.html, onde a coluna esta (como na Ruling 24) — custo se errado: nenhum.
- Ruling 28: na D5 a migracao de dados leva uma copia da regra (uma migracao aplicada nao pode mudar de comportamento se a regra mudar); como o pytest corre com --no-migrations, um teste chama a funcao da migracao sobre fichas antigas; alem dos espacos, a normalizacao tira . ( ) - entre algarismos — custo se errado: "965-852-489" tambem fica +351 965 852 489.
- Ruling 29: na D8 o menu aparece duas vezes na pagina (rail e gaveta do telemovel): cada area tem o titulo visivel (.rotulo, aria-hidden) e a lista leva o nome em aria-label, em vez de aria-labelledby com ids, que ficariam duplicados; os testes procuram o aria-label — custo se errado: nenhum.
- Ruling 30: na D8 o link "<- Stock" por cima do titulo das Contagens e dos Consumos tambem sai (o separador Artigos faz esse caminho); os separadores ficam a seguir ao subtitulo nas paginas que o tem; "Novo artigo", "Contar" e "Registar consumo" ficam como acao principal de cada pagina — custo se errado: nenhum.
- Ruling 31: na D9 o mes por omissao do ultimo dia com vendas so vale para o resumo da Analise (AnalysisView, a pagina das vendas); os relatorios de Stock, Compras e Pessoas ficam no mes corrente, porque os dados deles (stock agora, compras, ponto) nao esperam pela importacao do SAF-T — custo se errado: quem passa do resumo para outro separador sem ?mes= muda de mes.
- Final: Ruling: (declined 1) comportamento visual (D2 scrollWidth, D3 teclado, D8 gaveta) — feito na passagem visual (D2 emulado a 1280 e 358px, D3 teclado e ultima linha, D8 menu); a gaveta do telemovel nao foi aberta, mas e o mesmo partial do menu — custo se errado: um defeito so na gaveta.
- Final: Ruling: (declined 2) blocos E e F fora — e a Ruling 2 — custo se errado: nenhum novo.
- Final: Ruling: (declined 3) minors ja adiados no ledger — continuam adiados — custo se errado: o da lista de cada um.
- Final: Ruling: (declined 4) quem pica depois da meia-noite nao aparece nos Turnos de hoje do dia de servico — consequencia da regra explicita da C5 (o work_date nao muda); aparece na lista Em turno do dashboard — custo se errado: entre as 0h e as 5h essa pessoa so se ve em Em turno.
- Final: Ruling: (declined 5) cartao_vendas sem ano quando a ultima importacao tem mais de um ano — fica: uma casa sem importar ha um ano ja tem o aviso de atraso — custo se errado: a legenda "ultimo dia 25/11" ambigua.
- Final: Ruling: (declined 6) Clear-Site-Data em telemoveis reais — fica para a F5 — custo se errado: o mesmo da A7.
- Final: Ruling: (declined 7) area "Stock" com a entrada "Stock" e aria-haspopup — o plano pede-os — custo se errado: nenhum.
- Final: Ruling: (declined 8) o W001 percorre os templates em cada comando — so com DEBUG, custo desprezavel — custo se errado: alguns ms no arranque em dev.
- Final: Ruling: (declined 9) .env.example: DJANGO_CSRF_TRUSTED_ORIGINS sem comentario sombreia a linha do tunel — coberto pelo minor adiado da A2 — custo se errado: quem copiar o exemplo tem de apagar uma linha.
- Final: Ruling: (2) os templates das fichas tecnicas (templates/manage/recipes/) ficam fora da guarda de unidades e de numero — e o minor adiado da D1 (as linhas das fichas guardam a unidade em texto livre); as quantidades vendidas de produtos do POS (vendas.html, analytics/inicio.html) ficam com numero, porque nao sao stock — custo se errado: «KG» e «1,500» continuam nas fichas e «1,50» numa venda fracionada de um produto.

## Problemas menores adiados (51)

Nenhum entrou na passagem de correções. Os marcados como resolvidos foram tratados depois por outra via.

- Task A6: minor (deferred): plan.md linha 26a diz "Nao visto no browser" e a 27a diz "proximo passo A6" — reconciliar no registo final. **(Resolvido: resolvido pela linha da 28a sessao no plan.md.)**
- Task A6: minor (deferred): dashboard `em_ferias` sem limite (a lista antiga tinha [:6]).
- Task A6: minor (deferred): cartao "Em ferias" mostra todos os tipos de ausencia aprovada (titulo mais estreito que o conteudo).
- Task A1: minor (deferred): core/management/commands/css.py:131-134 — OSError/PermissionError (binario sem chmod +x) sai em traceback em vez de CommandError.
- Task A1: minor (deferred): sem testes para avisar_css_desatualizado (gate DEBUG) nem para caminho_binario (TAILWIND_BIN/plataforma).
- Task A1: minor (deferred): plan.md:152 tem duas oracoes em vez de uma frase curta.
- Task A2: minor (deferred): prod.py:37 — Sentry com include_local_variables por omissao (True) pode enviar variaveis locais com nomes/codigos; por `include_local_variables=False` para o .env.example dizer a verdade.
- Task A2: minor (deferred): DatabaseCache precisa de createcachetable; sem a tabela, o throttle do login dá 500 (vai para o runbook F2).
- Task A2: minor (deferred): DatabaseCache.incr nao e atomico; limites podem contar a menos em concorrencia.
- Task A2: minor (deferred): test_producao._prod deveria fazer monkeypatch.delenv("SENTRY_DSN") para ser hermetico.
- Task A2: minor (deferred): sem teste direto do ramo Sentry nem do caminho de sucesso do demo com --forcar.
- Task A2: minor (deferred): .env.example diz "So producao" para DJANGO_CSRF_TRUSTED_ORIGINS mas dev.py tambem le a variavel.
- Task A3: minor (deferred): core/throttle.py:92-96 falhou faz get+set nao atomico (como o quiosque ja fazia).
- Task A3: minor (deferred): faltam testes diretos de core.throttle, de instancias independentes e de o erro ser non-field.
- Task A3: minor (deferred): chave por email permite bloquear a conta de alguem por 15 min (decisao do plano: por email).
- Task A4: minor (deferred): DJ001 e DJ008 ignoradas no projeto inteiro por 1 ocorrencia cada (preferivel # noqa na linha).
- Task A4: minor (deferred): ruff>=0.8 sem teto (instala 0.17.x); fixar se o CI ficar vermelho por versao nova.
- Task A4: minor (deferred): dashboard/staff admin.py e models.py ficaram so com comentario.
- Task A4: minor (deferred): ci.yml corre duas vezes num PR do mesmo repo (push + pull_request) — pedido no brief.
- Task A5: minor (deferred): so TimeEntry.worker/restaurant tem testes de PROTECT; os outros 9 campos nao.
- Task A5: minor (deferred): delete_worker podia apanhar ProtectedError e devolver ValidationError (defesa contra futuros PROTECT esquecidos).
- Task A7: minor (deferred): o teste do logout so verifica o cabecalho, nao que a sessao termina e redireciona.
- Task B1: minor (deferred): test_cada_ligacao_do_menu_abre aceita 302.
- Task B2: minor (deferred): erro_base.html:79 e 500.html:3 repetem as cores em vez de usar .mosaico-ambar/.mosaico-perigo.
- Task B2: minor (deferred): titulo duplicado nos blocos titulo e cabecalho de cada pagina de erro.
- Task B2: minor (deferred): tests/test_erros.py:130 import de mock dentro da funcao.
- Task B2: minor (deferred): comentario entre </head> e <body> em erro_base.html.
- Task B3: minor (deferred): is_backoffice faz uma query (casas()) em cada pagina da app.
- Task B3: minor (deferred): asserts fracos nos testes ("Sair" in html; "Gestao" not in html).
- Task B3: minor (deferred): staff/home.html:21 {% if %} sem indentacao.
- Task C1: minor (deferred): desativar pela caixa "ativo" do formulario da ficha nao grava end_date (fica fora dos meses em que so tem ausencias, sem registos); por end_date=hoje nesse caminho. **(Resolvido: corrigido na revisao final, correcao (5).)**
- Task C1: minor (deferred): end_date nao e validado contra start_date.
- Task C1: minor (deferred): faltam testes do seletor para start_date depois de M e para registos noutra casa.
- Task C2: minor (deferred): regra de sobreposicao ignora meio-dia e tipos que nao descontam (dois meios-dias no mesmo dia sao recusados) — decisao de produto futura.
- Task C2: minor (deferred): primeiro_dia_util e alias de proximo_dia_util; _ensure_months_open recalcula month_start(end) em cada volta.
- Task C2: minor (deferred): teste assume que a fixture worker nao cria VacationRequest.
- Task C3: minor (deferred): falta assert negativo para pedido que acaba hoje (fronteira end_date == hoje).
- Task C4: minor (deferred): faltam testes de fronteira (turno previsto de hoje ainda conta; horas reais num dia futuro contam).
- Task C4: minor (deferred): linha nova com 110 caracteres.
- Task C5: minor (deferred): _escala limita a hora atual a 24h ao esticar a escala; de madrugada, sem turno nem registo depois da meia-noite, o marcador agora nao aparece.
- Task D1: minor (deferred): as fichas tecnicas mostram a unidade da linha em bruto (unit_label "KG"), e recipes/services.py:256 e sales/stock.py:117 escrevem "nesta casa esta em KG"; as linhas das fichas guardam a unidade em texto livre.
- Final: minor (deferred): os meses que o filtro date do Django escreve (F, M) continuam com maiuscula: "Sabado, 7 de Novembro" no subtitulo do dashboard, "18 Set 2026" nas ferias; a C6 so tratou do cartao, do aviso e do painel.
- Final: minor (deferred): (7) o Ponto do dia so lista fichas ativas: num dia passado, quem ja saiu desaparece desse dia (o fecho e o CSV mostram-no).
- Final: minor (deferred): (8) conjuntos de perfis ainda escritos a mao fora de core.permissions (dashboard/views.py:37-39 e :66, analytics/views.py:58 e :133, recipes/views.py:42, core/views.py:35).
- Final: minor (deferred): (9) core/templatetags/graficos.py ainda importa euros/numero/preco de sales.templatetags.vendas (dependencia core -> sales).
- Final: minor (deferred): (10) meses com maiuscula pelo filtro date do Django (subtitulo do dashboard, "18 Set 2026" nas ferias) e a mensagem "O mes de 11/2026 ... ja foi aprovado" de attendance/month.py:48, agora usada em mais fluxos.
- Final: minor (deferred): (11b) depois de desativada, a ficha nao mostra a data de saida em lado nenhum, por isso uma data errada nao se ve.
- Final: minor (deferred): (12) todos os botoes "Mais acoes" tem o mesmo nome acessivel; passar o nome do artigo ou da pessoa.
- Final: minor (deferred): (13) o "hoje" entre as 0h e as 5h nao e o mesmo em todo o lado (lista de ferias e C4 pelo dia civil; dashboard pelo dia de servico).
- Final: minor (deferred): (14) os separadores da Analise nao levam o periodo; com a D9 o mes muda ao trocar de separador (custo da Ruling 31).
- Final: minor (deferred): (15) o painel Mais acoes nao segue o scroll horizontal dentro da tabela; falta um teste de que a linha devolvida pelo HTMX (pos_movimento.html) tem o menu; menu_acoes nao esta em /componentes/.
