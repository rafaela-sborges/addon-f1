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
- Ctrl+C: Copia o item atualmente selecionado.
- Ctrl+A: Copia todas as informações que estão na árvore.
- Ctrl+S: Salva todas as informações em um arquivo de texto.
- Esc: Fecha a janela do complemento.
## Avisos durante a corrida (ao vivo)
Durante as corridas e sprints, o complemento pode anunciar o que acontece na pista, em tempo real:
- Ultrapassagens, dizendo quem passou quem. Por padrão só entre os 5 primeiros; dá para escolher todas, só dentro dos pontos, só pelo pódio ou só pela liderança.
- Safety car e safety car virtual.
- Bandeiras (amarela, vermelha, verde) e, se quiser, bandeiras azuis.
- Batidas e incidentes.
- Abandonos e carros parados na pista.
- Punições e pit stops, se quiser.
A largada, o resumo do fim da primeira volta, a última volta e a bandeira quadriculada são sempre anunciados.

Ao conectar no meio de uma corrida, o complemento diz onde ela está, por exemplo: "Avisos ao vivo conectados na volta 34 de 51. Safety car na pista. George Russell lidera."

Cada aviso toca o som de rádio e é falado um de cada vez, sem que um corte o outro. Os mais importantes (bandeira vermelha, safety car, abandono, troca de liderança) passam na frente dos que estão esperando.

### Como ligar e escolher os avisos
- Em Menu NVDA -> Ferramentas -> Configurações - Fórmula 1, na seção "Avisos durante a corrida", marque os avisos que deseja ouvir e escolha quais ultrapassagens anunciar.
- Com a opção "Ativar os avisos sozinho quando uma corrida ou sprint estiver acontecendo" marcada, o complemento se conecta sozinho na hora da largada e se desconecta ao fim da corrida.
- Em Menu NVDA -> Ferramentas -> Avisos da corrida - Fórmula 1, dá para conectar ou desconectar na hora e testar os avisos com uma corrida já disputada, acelerada, para escolher o que ouvir. Se houver uma corrida acontecendo, ela aparece no topo da lista como "ao vivo agora"; escolhê-la e apertar Iniciar liga os avisos ao vivo.

### De onde vêm os dados ao vivo (Importante)
Os avisos ao vivo usam o live timing da Fórmula 1, o mesmo que alimenta o site e o aplicativo oficiais. Ele não é um serviço oficial para outros aplicativos e pode mudar ou deixar de funcionar sem aviso. Resultados, classificação e calendário continuam vindo da API Jolpi, como antes. O tempo parado em cada pit stop não é informado, porque a Fórmula 1 o reserva para assinantes do F1 TV.
## Cache Inteligente
Para evitar que a API bloqueie seu IP por excesso de acessos, o complemento salva os resultados no seu computador (cache) por 1 hora. Isso também faz a tela abrir instantaneamente. Se quiser forçar a busca de novos resultados antes desse tempo acabar, basta usar o botão Atualizar dados.
## Personalizar o atalho
Você pode alterar o atalho de ativação padrão no NVDA indo em:
Menu NVDA -> Preferências -> Definir comandos -> Fórmula 1