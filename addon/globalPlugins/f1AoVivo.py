# -*- coding: UTF-8 -*-
# Avisos da corrida em tempo real: lê o live timing da F1 (o mesmo feed do site e do app oficiais) e
# transforma o que acontece na pista em avisos falados, separados por tipo para o usuário escolher.
#
# O feed não é oficial para terceiros e pode mudar sem aviso. Ele é usado só para os avisos ao vivo:
# resultados, classificação e calendário continuam vindo da API Jolpi, no f1Acessivel.py.
#
# Este arquivo não importa nada do NVDA nem do wx: o estado da corrida, a classificação dos avisos e o
# replay podem ser testados fora do leitor de tela (ver tests/test_f1_ao_vivo.py). Quem fala os avisos
# é o f1Acessivel.py.

import datetime
import http.cookiejar
import json
import re
import threading
import urllib.error
import urllib.request

try:
    import addonHandler
    addonHandler.initTranslation()
    from gettext import gettext as _
except Exception:
    # Fora do NVDA (nos testes) não há tradução: a frase sai como está.
    def _(texto):
        return texto

LIVETIMING = "https://livetiming.formula1.com"
HTTP_TIMEOUT_SECONDS = 20
USER_AGENT = "BestHTTP"  # o feed recusa clientes sem um User-Agent que ele conheça

# Tópicos do feed que os avisos usam. Todos chegam sem conta; o que a F1 fechou para assinantes
# (posição no mapa, tempo de pit stop, DRS) não é usado.
TOPICOS = ["SessionInfo", "SessionStatus", "TrackStatus", "LapCount", "DriverList", "TimingData", "RaceControlMessages"]

# Tipos de aviso que o usuário liga e desliga nas configurações.
TIPO_ULTRAPASSAGEM = "ultrapassagens"
TIPO_SAFETY_CAR = "safety_car"
TIPO_BANDEIRA = "bandeiras"
TIPO_BANDEIRA_AZUL = "bandeiras_azuis"
TIPO_INCIDENTE = "incidentes"
TIPO_ABANDONO = "abandonos"
TIPO_PUNICAO = "punicoes"
TIPO_PIT = "pit_stops"
TIPO_CORRIDA = "corrida"  # largada, última volta, bandeira quadriculada: sempre anunciados

# Padrão de cada tipo quando o usuário ainda não escolheu. Bandeira azul e pit stop acontecem o tempo
# todo, e punições incluem as muitas investigações de infração; começam desligados.
TIPOS_PADRAO = {
    TIPO_ULTRAPASSAGEM: True,
    TIPO_SAFETY_CAR: True,
    TIPO_BANDEIRA: True,
    TIPO_BANDEIRA_AZUL: False,
    TIPO_INCIDENTE: True,
    TIPO_ABANDONO: True,
    TIPO_PUNICAO: False,
    TIPO_PIT: False,
}

# Até que posição uma ultrapassagem é anunciada (0 = todas).
ULTRAPASSAGENS_TODAS = 0
ULTRAPASSAGENS_PONTOS = 10
ULTRAPASSAGENS_PODIO = 3
ULTRAPASSAGENS_LIDERANCA = 1

# Uma troca de posição de quem passou pelos boxes neste intervalo não é ultrapassagem na pista.
JANELA_PIT_SEGUNDOS = 45
# Quem é ultrapassado tantas vezes neste intervalo está com problema: vira um aviso só.
QUEDA_ULTRAPASSAGENS = 3
QUEDA_JANELA_SEGUNDOS = 90
# As posições dos dois carros chegam em mensagens separadas: só depois deste silêncio a ordem é lida.
ESPERA_POSICOES_SEGUNDOS = 1.0


class Aviso:
    """Um aviso pronto para ser falado."""

    def __init__(self, instante, tipo, texto, prioridade=False):
        self.instante = instante  # datetime em UTC de quando aconteceu (ou None)
        self.tipo = tipo
        self.texto = texto
        # Avisos de prioridade (bandeira vermelha, safety car, abandono) passam na frente da fila.
        self.prioridade = prioridade

    def __repr__(self):
        return f"Aviso({self.tipo}, {self.texto!r})"


def ler_data(texto):
    """Converte uma data do feed ("2026-09-13T13:04:04" ou com Z/fuso) em datetime UTC."""
    if not texto:
        return None
    try:
        texto = str(texto).replace("Z", "+00:00")
        # O feed às vezes manda sete casas nos segundos; o Python aceita até seis.
        texto = re.sub(r"(\.\d{6})\d+", r"\1", texto)
        data = datetime.datetime.fromisoformat(texto)
        if data.tzinfo is None:
            data = data.replace(tzinfo=datetime.timezone.utc)
        return data.astimezone(datetime.timezone.utc)
    except Exception:
        return None


def _nome_legivel(nome):
    # O feed manda "George RUSSELL": o sobrenome em maiúsculas fica estranho na fala.
    return " ".join(parte.capitalize() if parte.isupper() and len(parte) > 1 else parte for parte in (nome or "").split())


class Pilotos:
    """Nomes dos pilotos da sessão, pelo número do carro."""

    def __init__(self):
        self._por_numero = {}

    def atualizar(self, lista_de_pilotos):
        """Recebe o DriverList do feed: {"63": {"FullName": "George RUSSELL", "Tla": "RUS", ...}}."""
        for numero, info in (lista_de_pilotos or {}).items():
            if not isinstance(info, dict):
                continue
            atual = self._por_numero.setdefault(str(numero), {"nome": str(numero), "sigla": "", "equipe": ""})
            if info.get("FullName"):
                atual["nome"] = _nome_legivel(info["FullName"])
            elif info.get("FirstName") or info.get("LastName"):
                atual["nome"] = _nome_legivel(f"{info.get('FirstName', '')} {info.get('LastName', '')}".strip())
            if info.get("Tla"):
                atual["sigla"] = info["Tla"]
            if info.get("TeamName"):
                atual["equipe"] = info["TeamName"]

    def nome(self, numero):
        info = self._por_numero.get(str(numero))
        return info["nome"] if info else _("carro {n}").format(n=numero)


# "CAR 44 (HAM)" e "CARS 55 (SAI) AND 22 (TSU)" nas mensagens da direção de prova.
_RE_CARROS = re.compile(r"(\d+)\s*\(([A-Z]{3})\)")

# Motivos de investigação que são infração de regra, não batida: entram como punição/investigação.
_INFRACOES = (
    "LEAVING THE TRACK", "TRACK LIMITS", "YELLOW FLAG", "PIT LANE", "SPEEDING", "UNDER BRAKING",
    "START INFRINGEMENT", "RACE DIRECTORS INSTRUCTIONS", "UNSAFE RELEASE", "FALSE START", "SAFETY CAR",
    "VSC", "PARC FERME", "IMPEDING", "BLUE FLAG", "FORCING ANOTHER DRIVER", "MORE THAN ONE CHANGE",
)


def _nomes_na_mensagem(mensagem, pilotos):
    nomes = []
    for numero, _sigla in _RE_CARROS.findall(mensagem or ""):
        nome = pilotos.nome(numero)
        if nome not in nomes:
            nomes.append(nome)
    return nomes


def _juntar_nomes(nomes):
    if not nomes:
        return ""
    if len(nomes) == 1:
        return nomes[0]
    return _("{inicio} e {fim}").format(inicio=", ".join(nomes[:-1]), fim=nomes[-1])


def classificar_direcao_de_prova(msg, pilotos):
    """Transforma uma mensagem de RaceControlMessages em Aviso, ou None se não interessa ao público."""
    categoria = (msg.get("Category") or "").strip()
    bandeira = (msg.get("Flag") or "").strip().upper()
    texto = (msg.get("Message") or "").strip().upper()
    escopo = (msg.get("Scope") or "").strip()
    instante = ler_data(msg.get("Utc"))

    if texto in ("RACE START", "SPRINT START"):
        return Aviso(instante, TIPO_CORRIDA, _("Largada!"), prioridade=True)

    if categoria == "SafetyCar":
        virtual = "VIRTUAL" in texto or "VSC" in texto
        if "DEPLOYED" in texto:
            frase = _("Safety car virtual acionado.") if virtual else _("Safety car na pista!")
            return Aviso(instante, TIPO_SAFETY_CAR, frase, prioridade=True)
        if "ENDING" in texto:
            return Aviso(instante, TIPO_SAFETY_CAR, _("Safety car virtual terminando."))
        if "IN THIS LAP" in texto:
            return Aviso(instante, TIPO_SAFETY_CAR, _("Safety car entra nesta volta."))
        return None

    if categoria == "Flag":
        if bandeira == "RED":
            return Aviso(instante, TIPO_BANDEIRA, _("Bandeira vermelha! Corrida interrompida."), prioridade=True)
        if bandeira == "CHEQUERED":
            return Aviso(instante, TIPO_CORRIDA, _("Bandeira quadriculada!"), prioridade=True)
        if bandeira == "BLUE":
            nomes = _nomes_na_mensagem(texto, pilotos)
            if not nomes:
                return None
            return Aviso(instante, TIPO_BANDEIRA_AZUL, _("Bandeira azul para {p}.").format(p=_juntar_nomes(nomes)))
        if bandeira == "BLACK AND WHITE":
            nomes = _nomes_na_mensagem(texto, pilotos)
            quem = _juntar_nomes(nomes) or _("um piloto")
            return Aviso(instante, TIPO_PUNICAO, _("Bandeira preta e branca para {p}.").format(p=quem))
        # O "setor" do feed é um dos cerca de vinte trechos de marcação da pista, não um dos três
        # setores de tempo: o número não diz nada a quem ouve, então fica de fora.
        if bandeira == "DOUBLE YELLOW":
            return Aviso(instante, TIPO_BANDEIRA, _("Bandeira amarela dupla."))
        if bandeira == "YELLOW":
            return Aviso(instante, TIPO_BANDEIRA, _("Bandeira amarela."))
        if bandeira in ("GREEN", "CLEAR") and escopo == "Track":
            # A luz verde da saída dos boxes antes da largada não é notícia.
            if "PIT EXIT" in texto:
                return None
            return Aviso(instante, TIPO_BANDEIRA, _("Bandeira verde, pista liberada."))
        return None

    # A partir daqui só mensagens de texto ("Other").
    if "PENALTY" in texto and "FIA STEWARDS" in texto:
        if "SERVED" in texto:
            return None
        nomes = _nomes_na_mensagem(texto, pilotos)
        if not nomes:
            return None
        segundos = re.search(r"(\d+)\s*SECOND", texto)
        if "DRIVE THROUGH" in texto:
            frase = _("{p} recebeu drive-through.").format(p=nomes[0])
        elif "STOP AND GO" in texto or "STOP/GO" in texto:
            frase = _("{p} recebeu stop and go.").format(p=nomes[0])
        elif segundos:
            frase = _("{p} punido em {s} segundos.").format(p=nomes[0], s=segundos.group(1))
        else:
            frase = _("{p} foi punido.").format(p=nomes[0])
        return Aviso(instante, TIPO_PUNICAO, frase)

    if "RETIRED" in texto or "STOPPED" in texto:
        nomes = _nomes_na_mensagem(texto, pilotos)
        if nomes:
            if "RETIRED" in texto:
                return Aviso(instante, TIPO_ABANDONO, _("{p} abandonou a corrida.").format(p=_juntar_nomes(nomes)), prioridade=True)
            return Aviso(instante, TIPO_ABANDONO, _("{p} parou na pista.").format(p=_juntar_nomes(nomes)), prioridade=True)

    # Cada incidente gera "NOTED", depois "UNDER INVESTIGATION" ou "REVIEWED NO FURTHER
    # INVESTIGATION", e às vezes a decisão; só o primeiro, o NOTED, vira aviso.
    if "INCIDENT" in texto and "NOTED" in texto and "FIA STEWARDS" not in texto:
        nomes = _nomes_na_mensagem(texto, pilotos)
        if not nomes:
            return None
        motivo = texto.split("NOTED", 1)[1]
        if "COLLISION" in motivo or "CONTACT" in motivo:
            frase = _("Toque entre {p}.").format(p=_juntar_nomes(nomes)) if len(nomes) > 1 else _("Batida de {p}.").format(p=nomes[0])
            return Aviso(instante, TIPO_INCIDENTE, frase)
        if any(infracao in motivo for infracao in _INFRACOES):
            return Aviso(instante, TIPO_PUNICAO, _("Comissários analisam {p}.").format(p=_juntar_nomes(nomes)))
        # Incidente com dois carros e sem motivo de infração costuma ser toque.
        if len(nomes) > 1:
            return Aviso(instante, TIPO_INCIDENTE, _("Incidente entre {p}.").format(p=_juntar_nomes(nomes)))
        return Aviso(instante, TIPO_INCIDENTE, _("Incidente com {p}.").format(p=nomes[0]))

    return None


def filtrar_por_preferencia(avisos, tipos_ligados):
    """Deixa só os tipos que o usuário ligou. Largada, última volta e quadriculada passam sempre."""
    return [a for a in avisos if a.tipo == TIPO_CORRIDA or tipos_ligados.get(a.tipo, False)]


class EstadoCorrida:
    """Acompanha a sessão a partir do feed e diz o que virou aviso.

    `aplicar(topico, dados, instante)` recebe cada atualização e devolve os avisos que ela gerou.
    `avaliar_posicoes(instante)` lê a ordem dos carros depois que as posições param de mudar e devolve
    as ultrapassagens. Com `silencioso=True` (o retrato inicial ao conectar, o que vem antes da
    largada no replay) o estado é montado sem anunciar o que já tinha acontecido.
    """

    def __init__(self, alcance_ultrapassagens=ULTRAPASSAGENS_TODAS):
        self.pilotos = Pilotos()
        self.alcance = alcance_ultrapassagens
        self.carros = {}  # número -> campos do TimingData que interessam
        self.volta_atual = 0
        self.total_voltas = 0
        self.status_pista = "1"
        self.status_sessao = ""
        self.tipo_sessao = "Race"
        self.mensagens_vistas = set()
        self.encerrada = False  # bandeira quadriculada já foi dada
        self._quedas = {}  # número -> instantes em que foi ultrapassado
        self._queda_avisada = {}  # número -> instante do último aviso de "perdendo posições"
        self._ordem_anunciada = None  # última ordem já comparada: {número: posição}
        self._ultima_mudanca_posicao = None
        self._pit_recente = {}  # número -> instante da última entrada ou saída dos boxes
        self._avisos_recentes = {}  # texto -> instante, para não repetir o mesmo aviso

    # ---- entrada

    def aplicar(self, topico, dados, instante, silencioso=False):
        avisos = []
        if not isinstance(dados, dict):
            return avisos
        if topico == "DriverList":
            self.pilotos.atualizar(dados)
        elif topico == "SessionInfo":
            self.tipo_sessao = dados.get("Type") or self.tipo_sessao
        elif topico == "SessionStatus":
            self.status_sessao = dados.get("Status") or self.status_sessao
        elif topico == "LapCount":
            self._aplicar_voltas(dados, instante, silencioso, avisos)
        elif topico == "TrackStatus":
            self.status_pista = str(dados.get("Status", self.status_pista))
        elif topico == "RaceControlMessages":
            self._aplicar_direcao(dados, silencioso, avisos)
        elif topico == "TimingData":
            self._aplicar_tempos(dados, instante, silencioso, avisos)
        return self._sem_repeticao(avisos, instante)

    def _aplicar_voltas(self, dados, instante, silencioso, avisos):
        if "TotalLaps" in dados:
            self.total_voltas = int(dados.get("TotalLaps") or 0)
        if "CurrentLap" in dados:
            volta = int(dados.get("CurrentLap") or 0)
            mudou = volta != self.volta_atual
            self.volta_atual = volta
            if mudou and not silencioso and self.total_voltas and volta == self.total_voltas and self._corrida():
                avisos.append(Aviso(instante, TIPO_CORRIDA, _("Última volta!"), prioridade=True))
            if mudou and not silencioso and volta == 2 and self._corrida():
                resumo = self._resumo_primeira_volta(instante)
                if resumo:
                    avisos.append(resumo)

    def _aplicar_direcao(self, dados, silencioso, avisos):
        mensagens = dados.get("Messages")
        if isinstance(mensagens, list):
            lista = mensagens
        elif isinstance(mensagens, dict):
            lista = list(mensagens.values())
        else:
            return
        for msg in lista:
            if not isinstance(msg, dict):
                continue
            # A mesma mensagem pode chegar no retrato inicial e de novo numa atualização.
            identidade = (msg.get("Utc"), msg.get("Message"))
            if identidade in self.mensagens_vistas:
                continue
            self.mensagens_vistas.add(identidade)
            if silencioso:
                continue
            aviso = classificar_direcao_de_prova(msg, self.pilotos)
            if aviso and aviso.texto == _("Bandeira quadriculada!"):
                if self.encerrada:
                    continue
                self.encerrada = True
            elif aviso and self.encerrada and aviso.tipo not in (TIPO_PUNICAO, TIPO_INCIDENTE):
                # Depois da quadriculada só importa o que ainda muda o resultado.
                continue
            if aviso:
                avisos.append(aviso)

    def _aplicar_tempos(self, dados, instante, silencioso, avisos):
        linhas = dados.get("Lines")
        if not isinstance(linhas, dict):
            return
        for numero, campos in linhas.items():
            if not isinstance(campos, dict):
                continue
            numero = str(numero)
            carro = self.carros.setdefault(numero, {})
            antes = dict(carro)
            for chave in ("Position", "InPit", "PitOut", "Retired", "Stopped"):
                if chave in campos:
                    carro[chave] = campos[chave]
            if "Position" in campos and campos.get("Position") != antes.get("Position"):
                self._ultima_mudanca_posicao = instante
            entrou_box = carro.get("InPit") is True and antes.get("InPit") is not True
            saiu_box = carro.get("PitOut") is True and antes.get("PitOut") is not True
            if entrou_box or saiu_box:
                self._pit_recente[numero] = instante
            if silencioso or not antes or self.encerrada:
                continue
            nome = self.pilotos.nome(numero)
            if carro.get("Retired") is True and antes.get("Retired") is not True:
                avisos.append(Aviso(instante, TIPO_ABANDONO, _("{p} abandonou a corrida.").format(p=nome), prioridade=True))
            elif carro.get("Stopped") is True and antes.get("Stopped") is not True and carro.get("Retired") is not True:
                avisos.append(Aviso(instante, TIPO_ABANDONO, _("{p} parou na pista.").format(p=nome), prioridade=True))
            if entrou_box and self._corrida() and carro.get("Retired") is not True:
                avisos.append(Aviso(instante, TIPO_PIT, _("{p} foi para os boxes.").format(p=nome)))

    def _resumo_primeira_volta(self, instante):
        # Na largada as posições oscilam demais para anunciar troca por troca: no fim da primeira
        # volta sai um resumo de quem ficou na frente.
        ordem = self._ordem_atual()
        if not ordem:
            return None
        primeiros = [numero for numero, _pos in sorted(ordem.items(), key=lambda item: item[1])[:3]]
        nomes = [self.pilotos.nome(n) for n in primeiros]
        if len(nomes) < 3:
            return None
        self._ordem_anunciada = ordem
        return Aviso(instante, TIPO_CORRIDA, _("Fim da primeira volta: {a} lidera, seguido de {b} e {c}.").format(a=nomes[0], b=nomes[1], c=nomes[2]))

    # ---- ultrapassagens

    def _corrida(self):
        return self.tipo_sessao in ("Race", "Sprint")

    def _ordem_atual(self):
        ordem = {}
        for numero, carro in self.carros.items():
            try:
                ordem[numero] = int(carro.get("Position"))
            except (TypeError, ValueError):
                continue
        # Durante a troca de mensagens dois carros podem ter a mesma posição: espera fechar.
        if len(set(ordem.values())) != len(ordem):
            return None
        return ordem

    def avaliar_posicoes(self, instante, forcar=False):
        """Compara a ordem atual com a última lida e devolve as ultrapassagens de pista."""
        if not self._corrida():
            return []
        if not forcar and self._ultima_mudanca_posicao is not None and instante is not None:
            if (instante - self._ultima_mudanca_posicao).total_seconds() < ESPERA_POSICOES_SEGUNDOS:
                return []
        ordem = self._ordem_atual()
        if ordem is None or ordem == self._ordem_anunciada:
            return []
        anterior, self._ordem_anunciada = self._ordem_anunciada, ordem
        # Antes da largada o grid ainda se arruma, e com a pista neutralizada (safety car, VSC,
        # vermelha) ninguém ultrapassa: a ordem muda só por causa dos boxes.
        if anterior is None or self.status_pista not in ("1", "2") or self.status_sessao not in ("Started", ""):
            return []
        if self.encerrada or self.volta_atual <= 1:
            return []
        avisos = []
        for quem, nova in sorted(ordem.items(), key=lambda item: item[1]):
            velha = anterior.get(quem)
            if velha is None or nova >= velha or not self._em_pista(quem, instante):
                continue
            # Quem estava à frente dele e agora ficou atrás, também em ritmo de pista.
            passados = [
                outro for outro, pos_outro in anterior.items()
                if outro != quem and nova <= pos_outro < velha and ordem.get(outro, 0) > nova
                and self._em_pista(outro, instante)
            ]
            if not passados:
                continue
            if self.alcance and nova > self.alcance:
                continue
            passado = min(passados, key=lambda outro: ordem.get(outro, 99))
            nome, nome_passado = self.pilotos.nome(quem), self.pilotos.nome(passado)
            if self._perdendo_posicoes(passado, instante):
                aviso_queda = self._aviso_de_queda(passado, ordem.get(passado), instante)
                if aviso_queda:
                    avisos.append(aviso_queda)
                continue
            if nova == 1:
                frase = _("{a} passa {b} e assume a liderança!").format(a=nome, b=nome_passado)
            else:
                frase = _("{a} passa {b} e sobe para {p}º.").format(a=nome, b=nome_passado, p=nova)
            avisos.append(Aviso(instante, TIPO_ULTRAPASSAGEM, frase, prioridade=nova == 1))
        return self._sem_repeticao(avisos, instante)

    def _perdendo_posicoes(self, numero, instante):
        """Registra que `numero` foi ultrapassado e diz se ele já está caindo pelo pelotão."""
        if instante is None:
            return False
        recentes = [t for t in self._quedas.get(numero, []) if (instante - t).total_seconds() < QUEDA_JANELA_SEGUNDOS]
        recentes.append(instante)
        self._quedas[numero] = recentes
        return len(recentes) >= QUEDA_ULTRAPASSAGENS

    def _aviso_de_queda(self, numero, posicao, instante):
        ultimo = self._queda_avisada.get(numero)
        if ultimo is not None and (instante - ultimo).total_seconds() < QUEDA_JANELA_SEGUNDOS * 2:
            return None
        self._queda_avisada[numero] = instante
        return Aviso(instante, TIPO_ULTRAPASSAGEM, _("{p} está perdendo várias posições, agora em {n}º.").format(p=self.pilotos.nome(numero), n=posicao))

    def _em_pista(self, numero, instante):
        carro = self.carros.get(numero, {})
        if carro.get("InPit") is True or carro.get("PitOut") is True:
            return False
        if carro.get("Retired") is True or carro.get("Stopped") is True:
            return False
        ultimo_pit = self._pit_recente.get(numero)
        if ultimo_pit is not None and instante is not None and (instante - ultimo_pit).total_seconds() < JANELA_PIT_SEGUNDOS:
            return False
        return True

    def _sem_repeticao(self, avisos, instante):
        resultado = []
        for aviso in avisos:
            ultimo = self._avisos_recentes.get(aviso.texto)
            if ultimo is not None and instante is not None and (instante - ultimo).total_seconds() < 60:
                continue
            self._avisos_recentes[aviso.texto] = instante
            resultado.append(aviso)
        return resultado


# ---------------------------------------------------------------- arquivo das sessões passadas


class ErroLiveTiming(Exception):
    pass


def _baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            return resp.read().decode("utf-8-sig", errors="replace")
    except urllib.error.URLError as erro:
        raise ErroLiveTiming(str(erro))


def _data_utc(data_local, deslocamento):
    """O índice da F1 dá a data no horário do circuito e o fuso à parte ("15:00:00", "04:00:00")."""
    data = ler_data(data_local)
    if data is None:
        return None
    try:
        sinal = -1 if str(deslocamento).startswith("-") else 1
        h, m, s = (int(parte) for parte in str(deslocamento).lstrip("+-").split(":"))
        return data - sinal * datetime.timedelta(hours=h, minutes=m, seconds=s)
    except (TypeError, ValueError):
        return data


def sessoes_do_indice(indice, agora=None):
    """Corridas e sprints do índice do ano: lista de (caminho no arquivo, nome para exibir), com a
    sessão em andamento primeiro e as já disputadas da mais recente para a mais antiga. A sessão em
    andamento ainda não está no arquivo: vem com caminho None, e escolhê-la conecta ao vivo."""
    agora = agora or datetime.datetime.now(datetime.timezone.utc)
    ao_vivo, gravadas = [], []
    for evento in indice.get("Meetings", []):
        for sessao in evento.get("Sessions", []):
            if sessao.get("Type") != "Race":
                continue
            nome_sessao = _("Sprint") if "Sprint" in (sessao.get("Name") or "") else _("Corrida")
            data = (sessao.get("StartDate") or "")[:10]
            if sessao.get("Path"):
                nome = f"{evento.get('Name', '')} - {nome_sessao} ({data})"
                gravadas.append((sessao["Path"], nome, sessao.get("StartDate") or ""))
                continue
            inicio = _data_utc(sessao.get("StartDate"), sessao.get("GmtOffset"))
            fim = _data_utc(sessao.get("EndDate"), sessao.get("GmtOffset")) or inicio
            if inicio is None:
                continue
            # A corrida pode passar do horário previsto (bandeira vermelha, atrasos): folga no fim.
            fim = max(fim, inicio + datetime.timedelta(hours=3))
            if inicio - datetime.timedelta(minutes=15) <= agora <= fim:
                ao_vivo.append((None, _("{e} - {s} (ao vivo agora)").format(e=evento.get("Name", ""), s=nome_sessao)))
    gravadas.sort(key=lambda s: s[2], reverse=True)
    return ao_vivo + [(caminho, nome) for caminho, nome, _data in gravadas]


def listar_sessoes(ano):
    """Corridas e sprints do ano no arquivo da F1 (ver sessoes_do_indice)."""
    return sessoes_do_indice(json.loads(_baixar(f"{LIVETIMING}/static/{ano}/Index.json")))


def ler_json_stream(texto):
    """Cada linha é "HH:MM:SS.mmm{json}": o tempo desde o início da gravação e a atualização."""
    eventos = []
    for linha in texto.splitlines():
        linha = linha.strip().lstrip("﻿")
        if len(linha) < 13:
            continue
        try:
            h, m, s = linha[:12].split(":")
            deslocamento = int(h) * 3600 + int(m) * 60 + float(s)
            eventos.append((deslocamento, json.loads(linha[12:])))
        except (ValueError, json.JSONDecodeError):
            continue
    return eventos


def montar_eventos(textos_por_topico):
    """Junta as gravações de cada tópico numa lista única (segundos, tópico, dados), em ordem."""
    eventos = []
    for topico, texto in textos_por_topico.items():
        for deslocamento, dados in ler_json_stream(texto):
            eventos.append((deslocamento, topico, dados))
    eventos.sort(key=lambda e: e[0])
    return eventos


def baixar_sessao_gravada(caminho):
    """Baixa a gravação de uma sessão do arquivo da F1 (a corrida inteira tem uns 7 MB)."""
    textos = {}
    for topico in TOPICOS:
        if topico == "SessionInfo":
            continue
        textos[topico] = _baixar(f"{LIVETIMING}/static/{caminho}{topico}.jsonStream")
    return montar_eventos(textos)


def inicio_da_corrida(eventos):
    """Segundos em que a sessão começou de fato (SessionStatus Started), para o replay pular a espera."""
    for deslocamento, topico, dados in eventos:
        if topico == "SessionStatus" and isinstance(dados, dict) and dados.get("Status") == "Started":
            return deslocamento
    return eventos[0][0] if eventos else 0.0


class Replay(threading.Thread):
    """Reproduz uma sessão gravada no ritmo em que aconteceu, acelerado por `velocidade`.

    O que vem antes da largada é aplicado em silêncio, só para montar o estado. `ao_avisar(aviso)` é
    chamado para cada aviso, fora da thread principal; `ao_terminar(motivo)` no fim ("fim", "parado").
    """

    def __init__(self, eventos, estado, velocidade, ao_avisar, ao_terminar, filtro=None, antecedencia=30.0):
        super().__init__(daemon=True)
        self.eventos = eventos
        self.estado = estado
        self.velocidade = max(1.0, float(velocidade))
        self.ao_avisar = ao_avisar
        self.ao_terminar = ao_terminar
        self.filtro = filtro or (lambda avisos: avisos)
        self.comeco = max(0.0, inicio_da_corrida(eventos) - antecedencia)
        self._parar = threading.Event()

    def parar(self):
        self._parar.set()

    def run(self):
        # A gravação não traz o horário real de cada linha, só o deslocamento: um relógio fictício,
        # só para as janelas de tempo do estado funcionarem.
        base = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)
        anterior = None
        for deslocamento, topico, dados in self.eventos:
            instante = base + datetime.timedelta(seconds=deslocamento)
            silencioso = deslocamento < self.comeco
            if not silencioso and anterior is not None:
                espera = (deslocamento - anterior) / self.velocidade
                if espera > 0 and self._parar.wait(espera):
                    self.ao_terminar("parado")
                    return
            if self._parar.is_set():
                self.ao_terminar("parado")
                return
            if not silencioso:
                anterior = deslocamento
            avisos = self.estado.aplicar(topico, dados, instante, silencioso=silencioso)
            avisos += self.estado.avaliar_posicoes(instante)
            for aviso in self.filtro(avisos):
                self.ao_avisar(aviso)
        for aviso in self.filtro(self.estado.avaliar_posicoes(None, forcar=True)):
            self.ao_avisar(aviso)
        self.ao_terminar("fim")


# ---------------------------------------------------------------- ao vivo


class ClienteLiveTiming(threading.Thread):
    """Conecta ao live timing da F1 (SignalR Core, por Server-Sent Events) e alimenta o estado.

    Não precisa de conta nem de biblioteca de WebSocket: é HTTP comum, que o Python do NVDA já tem.
    Se a conexão cair, tenta de novo com espera crescente até `parar()` ser chamado.
    """

    SEPARADOR = "\x1e"

    def __init__(self, estado, ao_avisar, ao_status=None, filtro=None):
        super().__init__(daemon=True)
        self.estado = estado
        self.ao_avisar = ao_avisar
        self.ao_status = ao_status or (lambda texto: None)
        self.filtro = filtro or (lambda avisos: avisos)
        self._parar = threading.Event()
        self._url = None
        self._abridor = None
        self._resposta = None
        self._ultimo_instante = None

    def parar(self):
        self._parar.set()
        try:
            if self._resposta is not None:
                self._resposta.close()
        except Exception:
            pass

    def _post(self, corpo):
        req = urllib.request.Request(
            self._url, data=corpo.encode("utf-8"), method="POST",
            headers={"User-Agent": USER_AGENT, "Content-Type": "text/plain;charset=UTF-8"},
        )
        with self._abridor.open(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            resp.read()

    def _conectar(self):
        self._abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        req = urllib.request.Request(
            f"{LIVETIMING}/signalrcore/negotiate?negotiateVersion=1", data=b"", method="POST",
            headers={"User-Agent": USER_AGENT},
        )
        with self._abridor.open(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            negociacao = json.loads(resp.read().decode("utf-8"))
        self._url = f"{LIVETIMING}/signalrcore?id={negociacao['connectionToken']}"
        req = urllib.request.Request(self._url, headers={"User-Agent": USER_AGENT, "Accept": "text/event-stream"})
        self._resposta = self._abridor.open(req, timeout=60)
        self._post(json.dumps({"protocol": "json", "version": 1}) + self.SEPARADOR)
        pedido = {"type": 1, "invocationId": "1", "target": "Subscribe", "arguments": [TOPICOS]}
        self._post(json.dumps(pedido) + self.SEPARADOR)

    def _manter_viva(self):
        # O servidor derruba o cliente que fica calado; um ping a cada 15 segundos basta.
        while not self._parar.wait(15):
            try:
                self._post(json.dumps({"type": 6}) + self.SEPARADOR)
            except Exception:
                return

    def run(self):
        espera = 5
        while not self._parar.is_set():
            try:
                self._conectar()
                self.ao_status("conectado")
                espera = 5
                threading.Thread(target=self._manter_viva, daemon=True).start()
                self._ler()
            except Exception as erro:
                if self._parar.is_set():
                    break
                self.ao_status(f"erro: {erro}")
            if self._parar.wait(espera):
                break
            espera = min(espera * 2, 120)
        self.ao_status("desconectado")

    def _ler(self):
        decodificador = json.JSONDecoder()
        acumulado = ""
        for linha in self._resposta:
            if self._parar.is_set():
                return
            linha = linha.decode("utf-8", errors="replace").rstrip("\r\n")
            if not linha.startswith("data:"):
                continue
            acumulado += linha[5:].strip().replace(self.SEPARADOR, "")
            posicao = 0
            while posicao < len(acumulado):
                while posicao < len(acumulado) and acumulado[posicao].isspace():
                    posicao += 1
                if posicao >= len(acumulado):
                    break
                try:
                    mensagem, posicao = decodificador.raw_decode(acumulado, posicao)
                except json.JSONDecodeError:
                    break  # JSON pela metade: espera a próxima linha completar
                self.tratar(mensagem)
            acumulado = acumulado[posicao:]

    def tratar(self, mensagem, agora=None):
        """Aplica uma mensagem do protocolo ao estado e entrega os avisos. Público para os testes."""
        if not isinstance(mensagem, dict):
            return
        agora = agora or datetime.datetime.now(datetime.timezone.utc)
        avisos = []
        if mensagem.get("type") == 3 and isinstance(mensagem.get("result"), dict):
            # Retrato da sessão no momento da conexão: monta o estado sem anunciar o passado.
            retrato = mensagem["result"]
            for topico in TOPICOS:
                if topico in retrato:
                    self.estado.aplicar(topico, retrato[topico], agora, silencioso=True)
            self.estado.avaliar_posicoes(agora, forcar=True)
        elif mensagem.get("type") == 1 and mensagem.get("target") == "feed":
            argumentos = mensagem.get("arguments") or []
            if len(argumentos) >= 2:
                instante = ler_data(argumentos[2]) if len(argumentos) > 2 else None
                # O relógio do feed, não o do computador: as janelas de tempo comparam instantes dele.
                self._ultimo_instante = instante or agora
                avisos += self.estado.aplicar(argumentos[0], argumentos[1], self._ultimo_instante)
        avisos += self.estado.avaliar_posicoes(self._ultimo_instante or agora)
        for aviso in self.filtro(avisos):
            self.ao_avisar(aviso)
