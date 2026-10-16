# 📜 Changelog

## [2026.9.13.02]
- Corrigido: na categoria Campeonato (que já abre selecionada), o Enter não levava às opções Pilotos e Construtores. Agora o Enter confirma o que está selecionado e, no Campeonato, leva direto à caixa Opção. A lista de opções não é mais aberta pelo Enter.
- Menu Ferramentas do NVDA: os dois itens soltos ("Fórmula 1" e "Configurações - Fórmula 1") viraram o submenu "Fórmula 1", com "Abrir painel" e "Configurações".
- Rótulos das caixas: o da Categoria traz uma instrução curta, dita uma vez ao abrir ("pressione Enter na categoria desejada e depois no item que deseja visualizar"), e o da Opção é só "Opção".
- Configurações, aba Ao Vivo: a pergunta "Quais ultrapassagens anunciar" só aparece enquanto "Ultrapassagens" estiver marcada.
- Janela principal reorganizada em duas caixas de combinação: Categoria (Campeonato, Fim de semana, Temporada, Resultados) e Opção, que só aparece quando a categoria tem mais de uma opção. As setas só percorrem e o Enter confirma o que está selecionado (na categoria Campeonato, que já abre selecionada, o Enter leva direto à caixa Opção). Ao escolher uma categoria com várias opções, o foco vai para a caixa Opção, sem falar nada sobre ela ter aparecido; depois de carregar, o aviso diz que o Tab leva aos resultados.
- O foco não sai mais do lugar quando os dados carregam, a árvore só seleciona um item quando recebe o foco e o "Atualizar dados" mantém o item que você estava lendo.
- Resultados das corridas separados em "Corridas principais" e "Corridas sprint", e o "Resultado do fim de semana" mostra, para a etapa em andamento ou mais recente, uma seção para a corrida principal e, se houve, outra para a sprint (cada uma abre com uma seta). Ele substitui os botões "Ver Qualificação da Etapa" e "Ver Corrida da Etapa".
- Os resultados das corridas mostram, para cada piloto, o tempo (ou status) e os pontos ganhos, e uma só seta para a direita sobre a etapa já mostra os pilotos (o vencedor aparece no nome da etapa).
- Nomes das opções curtos, e os avisos não repetem o nome da etapa.
- Qualificações sprint: nova opção "Qualificações sprint" na categoria Resultados (com os tempos de SQ1, SQ2 e SQ3) e nova seção "Qualificação sprint" no Resultado do fim de semana das etapas com sprint. Os dados vêm da parte "alpha" da API Jolpi.
- Removida a opção "Última corrida": o Resultado do fim de semana já reúne a corrida mais recente.
- Corrigido: avisos de falha de carregamento e o aviso de lembrete salvo não eram falados por um erro interno.
- Avisos ao vivo durante corridas e sprints: ultrapassagens, safety car, bandeiras, batidas, abandonos, punições e pit stops, cada um ligado ou desligado nas configurações, com fila de falas e prioridade para os avisos mais importantes.
- Conexão automática ao live timing da Fórmula 1 na hora da corrida, e tela "Avisos da corrida" para conectar na hora ou testar com uma corrida passada.

## [2026.8.25]
- Primeira versão do complemento **Fórmula 1 (f1Acessivel)**.
- Migração completa do projeto anterior (Tabela Brasileirão) para a API Jolpi/Ergast.
- Suporte a classificação de Pilotos, Construtores, Calendário, Sessões e Resultados da Última Corrida.
