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
O painel também abre pelo menu do NVDA: Ferramentas -> Fórmula 1 -> Abrir painel. As configurações ficam no mesmo submenu: Ferramentas -> Fórmula 1 -> Configurações.

Ao abrir o painel, o foco fica na caixa **Categoria**. As setas só percorrem as categorias e não abrem nada. **Pressione Enter** para confirmar a categoria que está selecionada.

- Se a categoria tem **uma opção só**, o Enter na categoria já carrega os dados.
- Se tem **mais de uma**, o Enter na categoria faz aparecer a caixa **Opção** e leva o foco para ela, sem avisar nada além do nome da caixa. (A instrução curta "pressione Enter na categoria desejada e depois no item que deseja visualizar" faz parte do rótulo da Categoria, lido ao abrir o painel.) Na caixa Opção, as setas percorrem e o Enter abre a opção escolhida. Na categoria Campeonato, que já abre selecionada, o Enter leva direto à caixa Opção.

Quando os dados chegam, o complemento diz o que carregou e quantos itens vieram e avisa que o **Tab** leva aos resultados. Se não for possível carregar, ele avisa, diz o que continua na tela e lembra que o Enter tenta de novo. A caixa Opção só aparece quando é necessária, e o complemento não fala quando ela aparece ou some.

As categorias e opções:
- Campeonato: Pilotos e Construtores (a classificação atual).
- Fim de semana: Resultado (a etapa em andamento ou a mais recente) e Horários das sessões (treinos livres, sprint e corrida da próxima etapa). O Resultado mostra uma seção para a Corrida principal e, se a etapa teve sprint, outra para a Corrida sprint e outra para a Qualificação sprint (da mais recente para a mais antiga). Cada seção abre com uma seta e mostra os pilotos; na qualificação sprint, cada piloto aparece com os tempos de SQ1, SQ2 e SQ3. Se um resultado ainda não saiu na API, a seção avisa.
- Temporada: Calendário completo do ano, com circuitos e datas.
- Resultados: Corridas principais e Corridas sprint (o ano inteiro, uma etapa por item), Qualificações e Qualificações sprint (só as etapas com sprint, com os tempos de SQ1, SQ2 e SQ3).

Nos resultados das corridas, uma seta para a direita sobre a etapa (ou sobre a seção do fim de semana) já mostra os pilotos (o vencedor aparece no nome), e outra sobre um piloto mostra o tempo (ou o status, para quem não terminou) e os pontos ganhos.
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
A largada, o resumo do fim da primeira volta, a última volta, a bandeira quadriculada com o vencedor e, logo depois, o pódio são sempre anunciados. Depois da quadriculada, só punições e incidentes continuam sendo avisados.

Ao conectar no meio de uma corrida, o complemento diz onde ela está, por exemplo: "Avisos ao vivo conectados na volta 34 de 51. Safety car na pista. George Russell lidera."

Cada aviso toca o som de rádio e é falado um de cada vez, sem que um corte o outro. Os mais importantes (bandeira vermelha, safety car, abandono, troca de liderança) passam na frente dos que estão esperando.

### Como ligar e escolher os avisos
- Em Menu NVDA -> Ferramentas -> Fórmula 1 -> Configurações, na aba "Ao Vivo (Live Timing)", marque os avisos que deseja ouvir. Ao marcar "Ultrapassagens", aparece logo abaixo a pergunta "Quais ultrapassagens anunciar" (todas, só dentro dos pontos, só os 5 primeiros, só o pódio ou só a liderança); com as ultrapassagens desmarcadas, a pergunta não aparece. O que você escolheu fica guardado.
- Com a opção "Ativar os avisos sozinho quando uma corrida ou sprint estiver acontecendo" marcada, o complemento se conecta sozinho na hora da largada e se desconecta ao fim da corrida.
- Na mesma aba, o botão "Conectar à sessão ao vivo agora" (que vira "Desconectar da sessão ao vivo" quando já está conectado) liga ou desliga os avisos na hora.

### De onde vêm os dados ao vivo (Importante)
Os avisos ao vivo usam o live timing da Fórmula 1, o mesmo que alimenta o site e o aplicativo oficiais. Ele não é um serviço oficial para outros aplicativos e pode mudar ou deixar de funcionar sem aviso. Resultados, classificação e calendário continuam vindo da API Jolpi, como antes. A única exceção são as qualificações sprint, que a Jolpi só oferece na sua parte "alpha": ela ainda está em desenvolvimento e o formato pode mudar sem aviso. O tempo parado em cada pit stop não é informado, porque a Fórmula 1 o reserva para assinantes do F1 TV.
## Cache Inteligente
Para evitar que a API bloqueie seu IP por excesso de acessos, o complemento salva os resultados no seu computador (cache) por 1 hora. Isso também faz a tela abrir instantaneamente. Se quiser forçar a busca de novos resultados antes desse tempo acabar, basta usar o botão Atualizar dados.
## Personalizar o atalho
Você pode alterar o atalho de ativação padrão no NVDA indo em:
Menu NVDA -> Preferências -> Definir comandos -> Fórmula 1