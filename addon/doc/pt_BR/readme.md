# Fórmula 1 (f1Acessivel)
Autor: Rafaela Borges
## O que é
O Fórmula 1 é um complemento para o NVDA que permite consultar, com acessibilidade, informações atualizadas da temporada de Fórmula 1. 
Os dados são obtidos gratuitamente através da API Jolpi (Ergast).
### Sobre a atualização dos dados (Importante)
Atenção: Os dados deste complemento não são atualizados em tempo real durante as corridas. 
A base de dados da API costuma ser atualizada apenas algumas horas após o fim oficial do evento (geralmente aguardando a publicação oficial da FIA para contabilizar possíveis punições). Portanto, os resultados da corrida de domingo e a pontuação atualizada do campeonato podem levar até o final do dia ou a segunda-feira para aparecerem no complemento.
## Como usar
### Abrir o painel da Fórmula 1
Atalho padrão: Control + Alt + F
Ao abrir o painel, você terá acesso aos seguintes botões para alternar as informações:
- Pilotos: Classificação atual do campeonato de pilotos.
- Construtores: Classificação atual do campeonato de construtores.
- Calendário: Calendário completo do ano, com circuitos e datas.
- Sessões (Fim de Semana): Horários dos treinos livres, sprint e corrida da próxima etapa.
- Resultado da Última Corrida: Resultados finais (posições, tempos e pontos) da última corrida disputada.
- Resultados do Ano: Resumo das etapas, vencedores e pódios de todo o campeonato atual.
### Atualizar os dados
Dentro da janela, use o botão Atualizar dados para baixar informações recentes da API na mesma hora.
## Atalhos dentro da árvore de informações
Ao navegar na árvore com os dados, você pode pressionar:
- Setas para cima e para baixo: Navega pelos itens e expande os resultados.
- F1: Abre a tela de ajuda listando estes atalhos.
- P: Ouvir os Pontos.
- V: Ouvir o número de Vitórias.
- E: Ouvir a Equipe / Construtor.
- D: Ouvir a Data da Corrida (no modo calendário).
- Ctrl+C: Copia o item atualmente selecionado.
- Ctrl+A: Copia todas as informações que estão na árvore.
- Ctrl+S: Salva todas as informações em um arquivo de texto.
- Esc: Fecha a janela do complemento.
## Cache Inteligente
Para evitar que a API bloqueie seu IP por excesso de acessos, o complemento salva os resultados no seu computador (cache) por 1 hora. Isso também faz a tela abrir instantaneamente. Se quiser forçar a busca de novos resultados antes desse tempo acabar, basta usar o botão Atualizar dados.
## Personalizar o atalho
Você pode alterar o atalho de ativação padrão no NVDA indo em:
Menu NVDA -> Preferências -> Definir comandos -> Fórmula 1