# O que falta do lado do TM

> Tirado do `plan.md` a 2026-10-26, depois da Fase 13. Só tem o que precisa de ti: decisões, conversas, testes à mão e infraestrutura. O código que falta escrever está nas fases do plano.
> Marca `- [x]` à medida que fechares, e passa a decisão para o `plan.md` (secção 12 e Notas de desvio).

## 1. Decidir com a AT

Bloqueiam fases ou o piloto. A proposta de cada uma está na secção 12 do plano.

- [x] **Catálogo de artigos do grupo ou de cada casa.** Decidido a 2026-10-27: de cada casa.
- [x] **Trabalhador em mais de uma casa.** Decidido a 2026-10-27: uma casa principal, que é a entidade empregadora, com o saldo e o fecho do mês; pica e tem turnos nas outras. Já está construído. Falta o contabilista confirmar (secção 2).
- [x] **Âmbito e ordem das Fases 9 a 15** face ao piloto. Decidido a 2026-10-27: as Fases 9 a 13 entram no piloto; a 14 faz-se já e fica desligada nele; a 15 depois. Falta dar conhecimento à AT.
- [x] **Âmbito das Fases 5 e 6** (saldo anual e planeamento de turnos, que o docx deixava fora do MVP). Decidido a 2026-10-27: entram no piloto, ligadas. Falta dar conhecimento à AT.
- [x] **Aprovar as fases já feitas:** 7 (quiosque e app), 9, 11 (compras) e 13 (fichas). Aprovadas pelo TM a 2026-10-27, tal como estão construídas. Falta dar conhecimento à AT, que dá o visto funcional nos testes dela.
- [x] **O gerente pode criar artigos e registar movimentos?** Decidido a 2026-10-27: pode, como estava, incluindo as compras. Falta dar conhecimento à AT.
- [x] **Código de ponto só no tablet partilhado.** Confirmado a 2026-10-27: fica como está. Falta dar conhecimento à AT.
- [x] **Hora de corte do dia de serviço nas vendas.** Confirmado a 2026-10-27: 5h, configurável por casa. Falta dar conhecimento à AT.
- [x] **Serviço (almoço e jantar) nas vendas por hora trabalhada.** Decidido a 2026-10-27: por uma hora de mudança por casa, 17h por omissão. Já está construído. Falta dar conhecimento à AT.
- [x] **Stock negativo causado pelas vendas** (Fase 14). Decidido a 2026-10-27: só os movimentos de origem venda o deixam negativo, e o artigo fica assinalado para contar. Já está construído. Falta dar conhecimento à AT.
- [x] **Pergunta na saída tardia (R-012).** Decidido a 2026-10-27: entra, como pedido de correção ao gerente. Já está construído. Falta dar conhecimento à AT.
- [x] **Nome da marca e domínio.** Decidido a 2026-10-27: Opero. O domínio escolhe-se com o hosting (secção 6). Falta dar conhecimento à AT.
- [x] **Isolamento entre clientes.** Decidido a 2026-10-27: subdomínio por grupo (`<endereço>.opero.pt`), desde o piloto. Já está construído. Falta dar conhecimento à AT.
- [x] **Cliente piloto e disponibilidade semanal AT/TM.** Decidido a 2026-10-27: a Peco, que é o cliente de teste, com duas casas (Peco no Mercado e Peco no Foco), em `peco.opero.pt`. Sem calendário fixo: a AT e o TM estão em contacto constante.

## 2. Contabilista e jurista (com a AT)

- [ ] **Validação jurídica do registo de tempos (BR-001, Q-001):** conteúdo mínimo, prazo de conservação, mapa de horário e o que a ACT pede numa inspeção. **O piloto não arranca sem esta resposta.** Depois, arquivar a resposta e refletir as regras no produto.
- [ ] **Contrato coletivo da restauração (Q-010) e dias de férias extra (Q-008):** turnos, folgas, trabalho noturno e saldo por omissão.
- [ ] **Formato da exportação mensal de ponto** (Fase 5). Ganhou a coluna «Casa».
- [ ] **Trabalhador em várias casas:** confirmar que o fecho do mês e a exportação na casa principal, com as horas de todas as casas, servem. E se os consumos feitos noutra casa devem ir para o mapa da casa principal.
- [ ] **Refeições do pessoal e consumos internos no processamento salarial:** como querem as refeições em espécie no mapa da Fase 12.
- [ ] **Operador do POS (`SourceID`) ligado ao trabalhador**, para vendas por empregado: toca em RGPD e na relação laboral. Fica desligado até haver decisão.
- [ ] **RGPD (BR-006):** acordo de tratamento de dados (DPA) com o restaurante, lista de subcontratantes, alojamento na UE, retenção e política de privacidade.
- [ ] **Limite de horas para um registo ficar por resolver.** Proposta: 14 horas.

## 3. Cliente de teste (Peco)

- [ ] **Pedir o SAF-T de um mês e o relatório de vendas do POS desse mês.** Importar em Vendas → Importar e confirmar que o total sem IVA bate ao cêntimo. É o critério de aceitação da Fase 10. O ficheiro não entra no repositório.
- [ ] Confirmar com o cliente, a partir do ficheiro:
  - se o POS exporta um período à escolha (dia, semana) ou só o mês;
  - como numera as séries (importa se várias casas faturarem com o mesmo NIF);
  - se os totais de controlo batem (o aviso da importação);
  - se usa o estado F e em que documentos.
- [ ] Carregar um ficheiro pelo browser, à mão. Até agora só os testes o fizeram.
- [ ] Usar as compras (Fase 11) com um fornecedor real.
- [ ] Depois de o total do SAF-T bater, fazer as fichas dos produtos mais vendidos, ligar o stock pelas vendas numa casa a partir do dia a seguir a uma contagem, e comparar na contagem seguinte (Fase 14). No piloto fica desligado.

## 4. Testar em aparelhos reais

- [ ] **Quiosque num tablet real**, ao alto e deitado: nome, código e ação em menos de 5 segundos.
- [ ] Dois colaboradores seguidos no mesmo tablet: o segundo não herda nada do primeiro.
- [ ] Tablet desligado da rede: o ecrã diz que nada foi registado, e o gerente acrescenta o registo depois.
- [ ] Saída tardia no tablet (R-012): com um turno publicado já acabado, ver «Saí agora» e «Saí às HH:MM», e o pedido a chegar a Ponto → Pedidos.
- [ ] Ecrã de pausa no tablet: ver se o estado «em pausa» (contorno, sem cor) se percebe.
- [ ] **App do colaborador num telemóvel real**, a 375px: «Os meus turnos», férias, «Os meus consumos».
- [ ] Instalar a PWA em Android e em iOS, e ver as limitações de notificações push no iOS (BR-004). Isto decide se as trocas de turno podem depender de push.

## 5. Rever no browser

Ecrãs que só foram verificados pelos testes ou pelo texto da página, sem ninguém os ver.

- [ ] **Fichas técnicas (Fase 13):** lista, ficha, formulário, ficha para a cozinha e produtos do POS sem ficha.
- [ ] **Planeador de turnos (Fase 6):** ainda ninguém o viu.
- [ ] Fase 5: pedidos de correção, fecho do mês, configuração e saldos.
- [ ] Calendário de ausências (Fase 8) com dados reais.
- [ ] **Trabalhador em várias casas (Fase 9)** com o `demo`: a Inês no tablet da Esquina, o planeador da Esquina e a ficha dela na Ribeira.
- [ ] **Stock pelas vendas (Fase 14)** com o `demo` na Esquina: Vendas → Stock, a lista do stock com o bife negativo, uma contagem na folha e Stock → Contagens.
- [ ] **Vendas por serviço (Fase 10)** com o `demo`: o cartão «Por serviço» no ecrã Vendas, e a hora de mudança nas Regras.
- [ ] **Análise (Fase 15)** com o `demo`: Resumo, Stock, Pessoas e Compras, como dono com as duas casas e como Resp. stock; abrir um Excel exportado no Excel ou no LibreOffice.
- [ ] «Os meus turnos» na vista do colaborador: é um quarto elemento além dos três previstos (secção 5).
- [ ] Percurso completo dos quatro perfis com o `demo`. As compras foram feitas pelo Admin do grupo; o Resp. stock só pelos testes.

## 6. Infraestrutura e produção

- [ ] **Escolher o hosting e montar o ambiente de demonstração:** domínio (a marca é Opero) com DNS wildcard e certificado `*.opero.pt`, `OPERO_BASE_DOMAIN` e `DJANGO_ALLOWED_HOSTS=.opero.pt`, HTTPS, utilizadores de teste. Bloqueia a Fase 4.
- [ ] **Política de backups:** frequência, retenção, e um restauro testado pelo menos uma vez.
- [ ] **Envio de emails** (recuperação de password, avisos, encomendas aos fornecedores). Até lá, a password esquecida resolve-se com uma provisória gerada pelo gerente.
- [ ] Cache partilhada em produção (a cache em base de dados do Django chega) para o bloqueio do código de ponto e os tokens do quiosque, com vários processos.
- [ ] `collectstatic` e build do Tailwind com `--minify`, sem watch.
- [ ] Correr o `pytest` contra PostgreSQL, para os locks e as constraints serem testados de verdade.
- [ ] Corrigir os bugs P0 e P1 dos testes funcionais da AT, quando os houver.

## 7. Arrumação (opcional)

O `db.sqlite3` de desenvolvimento tem restos dos testes no browser: a entrada e a pausa abertas da Marta, `ENC-1`, `REC-2`, `CI-4` e a versão 3 do Bitoque. Não fazem mal; limpa-os se quiseres uma demonstração limpa.
