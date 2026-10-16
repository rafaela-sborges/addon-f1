# -*- coding: UTF-8 -*-
# Janela principal (f1Acessivel.F1Dialog): caixas Categoria e Opção (a Opção só aparece quando a categoria
# tem mais de uma), setas que só percorrem, Enter que escolhe, avisos de carga e de falha, resultado do fim
# de semana, foco e seleção da árvore de resultados.
# Os métodos reais da janela e o _open_modo_substituindo do plugin rodam sobre caixas, árvore e foco falsos,
# então dá para "apertar as teclas" e conferir o que a pessoa ouviria.
# Rodar da raiz do projeto: python -m unittest discover -s tests

import ast
import importlib.util
import inspect
import json
import os
import re
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
from unittest import mock

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "addon", "globalPlugins")
FALAS = []


class _Qualquer:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, nome):
        return lambda *a, **k: None


class Foco:
    """Quem tem o foco no momento: é o que wx.Window.FindFocus() devolve."""
    atual = None


class _JanelaWx:
    @staticmethod
    def FindFocus():
        return Foco.atual


def _simular_nvda():
    def modulo(nome, **atributos):
        m = types.ModuleType(nome)
        m.__dict__.update(atributos)
        sys.modules[nome] = m
        return m

    modulo("globalPluginHandler", GlobalPlugin=_Qualquer)
    modulo("ui", message=FALAS.append)
    modulo("tones", beep=lambda *a: None)
    modulo("nvwave", playWaveFile=lambda *a: None)
    modulo("gui", mainFrame=None)
    modulo("logHandler", log=_Qualquer())
    modulo("addonHandler", initTranslation=lambda: None)
    modulo("wx", Dialog=_Qualquer, MessageDialog=_Qualquer, CallAfter=lambda f, *a, **k: f(*a, **k),
           CallLater=lambda *a, **k: None, DEFAULT_DIALOG_STYLE=0, MAXIMIZE_BOX=0, RESIZE_BORDER=0, OK=0,
           ICON_WARNING=0, Window=_JanelaWx, WXK_RETURN=13, WXK_NUMPAD_ENTER=370, WXK_F1=340, WXK_ESCAPE=27)
    config = modulo("config", getUserConfigPath=tempfile.gettempdir)
    config.conf = {"f1Acessivel": {"avisos_ao_vivo_auto": True}}
    pacote = types.ModuleType("f1pacote_interface")
    pacote.__path__ = [PASTA]
    sys.modules["f1pacote_interface"] = pacote
    spec = importlib.util.spec_from_file_location("f1pacote_interface.f1Acessivel", os.path.join(PASTA, "f1Acessivel.py"))
    modulo_f1 = importlib.util.module_from_spec(spec)
    sys.modules["f1pacote_interface.f1Acessivel"] = modulo_f1
    spec.loader.exec_module(modulo_f1)
    return modulo_f1


f1 = _simular_nvda()
# as funções que falam com o Windows de verdade: os testes da janela as trocam por versões falsas
LISTA_ABERTA_REAL = f1._lista_do_combo_aberta
ABRIR_LISTA_REAL = f1._abrir_lista_do_combo


# ---------------------------------------------------------------- controles falsos


class Focavel:
    """Controle que pode ter o foco e aparecer ou sumir. `rouba_foco_em` lista operações que, como o Windows
    às vezes faz, levam o foco para outro controle sem que a pessoa tenha pedido."""

    def __init__(self):
        self.rouba_foco_em = set()
        self.rouba_para = None  # para onde o foco vai; por padrão, para este mesmo controle
        self.chamadas_set_focus = 0
        self.set_focus_falha = False
        self.visivel = True
        self.habilitado = True

    def Enable(self, habilitar=True):
        self.habilitado = habilitar

    def IsEnabled(self):
        return self.habilitado

    def Show(self, mostrar=True):
        self.visivel = mostrar

    def IsShown(self):
        return self.visivel

    def HasFocus(self):
        return Foco.atual is self

    def SetFocus(self):
        self.chamadas_set_focus += 1
        if self.set_focus_falha:
            raise RuntimeError("wrapped C/C++ object has been deleted")
        Foco.atual = self

    def _operacao(self, nome):
        if nome in self.rouba_foco_em:
            Foco.atual = self.rouba_para or self

    @property
    def com_foco(self):
        return self.HasFocus()

    @com_foco.setter
    def com_foco(self, valor):
        if valor:
            Foco.atual = self
        elif Foco.atual is self:
            Foco.atual = None


class ComboFalso(Focavel):
    """wx.Choice mínimo: guarda os itens e a seleção, se a lista está aberta e quantas vezes foi reescrito."""

    def __init__(self):
        super().__init__()
        self.itens = []
        self.selecao = -1
        self.vezes_set = 0
        self.aberta = False

    def Set(self, itens):
        self.itens = list(itens)
        self.selecao = -1
        self.vezes_set += 1
        self._operacao("Set")

    def GetSelection(self):
        return self.selecao

    def SetSelection(self, idx):
        self.selecao = idx
        self._operacao("SetSelection")

    def texto(self):
        return self.itens[self.selecao] if 0 <= self.selecao < len(self.itens) else None


class PainelFalso:
    def __init__(self):
        self.layouts = 0
        self.freezes = 0
        self.thaws = 0

    def Layout(self):
        self.layouts += 1

    def Freeze(self):
        self.freezes += 1

    def Thaw(self):
        self.thaws += 1


class ItemFalso:
    def IsOk(self):
        return True


INVALIDO = types.SimpleNamespace(IsOk=lambda: False)


class ArvoreFalsa(Focavel):
    """wx.TreeCtrl mínimo: itens com texto, pai e filhos, seleção, foco e o registro do que foi mexido."""

    def __init__(self):
        super().__init__()
        self.raiz = ItemFalso()
        self.selecionado = None
        self.textos = {}
        self.pais = {}
        self.filhos = {self.raiz: []}
        self.selecoes = []  # texto de cada SelectItem, na ordem
        self.eventos = []  # ordem de SelectItem e do Skip do evento de foco
        self.freezes = 0
        self.thaws = 0

    def limpar(self):
        self.textos.clear()
        self.pais.clear()
        self.filhos = {self.raiz: []}
        self.selecionado = None

    # a parte da API do wx que o _popular_arvore real usa
    def DeleteAllItems(self):
        self.limpar()

    def AddRoot(self, texto):
        return self.raiz

    def AppendItem(self, pai, texto):
        return self.adicionar(texto, pai=pai)

    def adicionar(self, texto, pai=None):
        pai = pai or self.raiz
        item = ItemFalso()
        self.textos[item] = texto
        self.pais[item] = pai
        self.filhos[item] = []
        self.filhos[pai].append(item)
        return item

    def Expand(self, item):
        pass

    def Freeze(self):
        self.freezes += 1
        self._operacao("Freeze")

    def Thaw(self):
        self.thaws += 1
        self._operacao("Thaw")

    def GetSelection(self):
        return self.selecionado if self.selecionado is not None else INVALIDO

    def SelectItem(self, item):
        self.selecionado = item
        self.selecoes.append(self.textos[item])
        self.eventos.append(("select", self.textos[item]))

    def EnsureVisible(self, item):
        pass

    def GetRootItem(self):
        return self.raiz

    def GetItemText(self, item):
        return self.textos[item]

    def GetItemParent(self, item):
        return self.pais[item]

    def GetFirstChild(self, pai):
        filhos = self.filhos[pai]
        return (filhos[0], 0) if filhos else (INVALIDO, 0)

    def GetNextChild(self, pai, cookie):
        filhos = self.filhos[pai]
        return (filhos[cookie + 1], cookie + 1) if cookie + 1 < len(filhos) else (INVALIDO, cookie + 1)


class EventoFalso:
    """Evento de foco da árvore: registra o Skip na ordem em que ele acontece."""

    def __init__(self, arvore):
        self.arvore = arvore

    def Skip(self):
        self.arvore.eventos.append(("skip", None))


class EventoTecla:
    def __init__(self, codigo, ctrl=False):
        self.codigo = codigo
        self.ctrl = ctrl
        self.pulou = False

    def GetKeyCode(self):
        return self.codigo

    def ControlDown(self):
        return self.ctrl

    def AltDown(self):
        return False

    def Skip(self):
        self.pulou = True


# ---------------------------------------------------------------- dados de exemplo

CALENDARIO = [
    {"round": "1", "raceName": "GP A", "date": "2026-03-08",
     "FirstPractice": {"date": "2026-03-06"}, "Qualifying": {"date": "2026-03-07"}},
    {"round": "2", "raceName": "GP B", "date": "2026-03-22",
     "FirstPractice": {"date": "2026-03-20"}, "SprintQualifying": {"date": "2026-03-20"},
     "Sprint": {"date": "2026-03-21"}, "Qualifying": {"date": "2026-03-21"}},
    {"round": "3", "raceName": "GP C", "date": "2026-04-05",
     "FirstPractice": {"date": "2026-04-03"}, "Qualifying": {"date": "2026-04-04"}},
]

CATEGORIAS = ["Campeonato", "Fim de semana", "Temporada", "Resultados"]
OPCOES_CAMPEONATO = ["Pilotos", "Construtores"]
OPCOES_RESULTADOS = ["Corridas principais", "Corridas sprint", "Qualificações", "Qualificações sprint"]
OPCOES_FIM_DE_SEMANA = ["Resultado", "Horários das sessões"]


def _resultado(pos, given, family, equipe, tempo, pontos, status="Finished"):
    r = {"position": str(pos), "Driver": {"givenName": given, "familyName": family},
         "Constructor": {"name": equipe}, "points": pontos, "status": status}
    if tempo is not None:
        r["Time"] = {"time": tempo}
    return r


VENCEDOR = _resultado(1, "Max", "Verstappen", "Red Bull", "33:38.998", "8")
SEGUNDO = _resultado(2, "Lando", "Norris", "McLaren", "+0.674", "7")
ABANDONO = _resultado(3, "Oscar", "Piastri", "McLaren", None, "0", status="Retired")


def _corrida(rd, nome, sprint, resultados):
    return {"round": rd, "raceName": nome, "_is_sprint": sprint, ("SprintResults" if sprint else "Results"): resultados}


def _linha_alpha(posicao, nome, sobrenome, equipe, sq1=None, sq2=None, sq3=None, status="FINISHED", texto=None):
    """Uma linha de resultado como a API alpha da Jolpi devolve em /results/<etapa>/SQ/."""
    componentes = {}
    for chave, tempo in (("SQ1", sq1), ("SQ2", sq2), ("SQ3", sq3)):
        if tempo:
            componentes[chave] = {"key": chave, "position": posicao, "time": tempo}
    return {"position": posicao, "position_text": texto or str(posicao), "status": status, "is_classified": True,
            "driver": {"given_name": nome, "family_name": sobrenome, "abbreviation": sobrenome[:3].upper()},
            "team": {"name": equipe}, "time": sq3 or sq2 or sq1, "components": componentes}


def _rodada(numero, nome, id_, sq1=None, cancelada=False):
    sessoes = [{"type": "FP1", "timestamp": "2026-01-01T00:00:00Z"}]
    if sq1:
        sessoes += [{"type": tipo, "timestamp": sq1, "is_cancelled": False} for tipo in ("SQ1", "SQ2", "SQ3")]
    return {"id": id_, "number": numero, "name": nome, "is_cancelled": cancelada, "sessions": sessoes}


SQ_CHINA_ALPHA = [
    _linha_alpha(1, "George", "Russell", "Mercedes", "1:33.030", "1:32.241", "1:31.520"),
    _linha_alpha(2, "Kimi", "Antonelli", "Mercedes", "1:33.455", "1:32.291", "1:31.809"),
    _linha_alpha(11, "Pierre", "Gasly", "Alpine", "1:34.100"),
]
SQ_MIAMI_ALPHA = [_linha_alpha(1, "Lando", "Norris", "McLaren", "1:28.100", "1:27.900", "1:27.869")]
RODADAS_ALPHA = {"metadata": {"count": 5}, "data": [
    _rodada(1, "Australian Grand Prix", "round_aus"),
    _rodada(2, "Chinese Grand Prix", "round_chn", "2026-03-13T07:30:00Z"),
    _rodada(4, "Miami Grand Prix", "round_mia", "2026-05-01T20:30:00Z"),
    _rodada(8, "Etapa cancelada", "round_can", "2026-06-01T10:00:00Z", cancelada=True),
    _rodada(30, "Grande Prêmio do Futuro", "round_fut", "2999-01-01T00:00:00Z"),
]}
RESULTADOS_ALPHA = {"round_chn": SQ_CHINA_ALPHA, "round_mia": SQ_MIAMI_ALPHA}

LINHAS_SQ_CHINA = [
    "1º George Russell (Mercedes) - SQ1: 1:33.030 | SQ2: 1:32.241 | SQ3: 1:31.520",
    "2º Kimi Antonelli (Mercedes) - SQ1: 1:33.455 | SQ2: 1:32.291 | SQ3: 1:31.809",
    "11º Pierre Gasly (Alpine) - SQ1: 1:34.100",
]


def _qualificacao(numero, nome, linhas_alpha):
    """A qualificação sprint já na forma que o plugin entrega à janela."""
    return f1.normalizar_qualificacao_sprint({"number": numero, "name": nome}, linhas_alpha)


def rede_alpha(url, falham=(), rodadas=RODADAS_ALPHA):
    """O servidor alpha falso: a lista de etapas e o resultado de cada uma; `falham` são ids que dão 404."""
    if "/alpha/core/rounds/" in url:
        return rodadas
    for id_, linhas in RESULTADOS_ALPHA.items():
        if f"/alpha/results/{id_}/SQ/" in url:
            if id_ in falham:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return {"data": {"results": linhas}}
    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


LINHA_VENCEDOR = ("1º Max Verstappen (Red Bull)", [("Tempo/Status: 33:38.998", []), ("Pontos ganhos: 8", [])])
LINHA_SEGUNDO = ("2º Lando Norris (McLaren)", [("Tempo/Status: +0.674", []), ("Pontos ganhos: 7", [])])
LINHA_ABANDONO = ("3º Oscar Piastri (McLaren)", [("Tempo/Status: Retired", []), ("Pontos ganhos: 0", [])])


def _estrutura(arvore, pai=None):
    return [(arvore.textos[f], _estrutura(arvore, f)) for f in arvore.filhos[pai or arvore.raiz]]


def carregou(nome, itens):
    palavra = "1 item" if itens == 1 else f"{itens} itens"
    return f"Carregou {nome}: {palavra}. Pressione Tab para ler os resultados."


# ---------------------------------------------------------------- a janela com métodos reais


class BaseJanela(unittest.TestCase):
    """Monta a F1Dialog com os métodos reais sobre caixas, árvore e foco falsos."""

    METODOS_JANELA = (
        "_calendario_em_cache", "_atualizar_etapa", "_garantir_calendario", "_visao_disponivel",
        "_texto_da_visao", "_nome_da_visao", "_opcoes_da_categoria", "_indice_da_categoria_selecionada",
        "_id_da_opcao_selecionada", "_preencher_opcoes", "_mostrar_combo_opcao", "_sincronizar_combos",
        "_preservando_foco", "_devolver_foco", "_categoria_precisa_confirmar", "_opcao_precisa_confirmar",
        "_enter_no_combo", "_combo_com_foco", "_confirmar_depois", "_confirmar_categoria", "_ir_para_a_opcao", "_confirmar_opcao",
        "_abrir_visao", "_on_click_modo", "_obter_titulo", "mudar_modo_em_lugar", "falha_ao_carregar",
        "_mensagem_carregada", "_instrucao_para_resultados", "_filhos", "_caminho_selecionado",
        "_item_do_caminho", "_atualizar_dados_na_tela", "_aplicar_selecao", "_ao_focar_arvore",
        "_on_click_atualizar", "ao_pressionar_esc",
    )

    def setUp(self):
        FALAS.clear()
        Foco.atual = None
        self.hoje = "2026-03-10"  # etapa 1, sem sprint
        self.cargas = []  # primeiro dado de cada carga, na ordem
        self.dados_por_modo = {}  # dado que o cache devolve, quando o teste quer algo diferente do padrão
        self.sem_cache = set()  # modos sem cache fresco: o plugin precisa baixar
        self.velhos = {}  # cache vencido (também é de onde vem o calendário)
        self.baixados = []  # (modo, ok, fail) dos downloads pedidos
        self.pedidos = []  # modos de dados que o plugin foi buscar no cache
        self.erros_simples = 0
        self.listas_abertas = 0  # quantas vezes o Enter abriu a lista de opções de uma caixa
        self.vigias = []
        self.fila = []  # o que ficou para depois no wx.CallAfter

        for alvo, nome, falso in ((f1, "_lista_do_combo_aberta", lambda combo: combo.aberta),
                                  (f1, "_abrir_lista_do_combo", self._abrir_lista_falsa),
                                  (f1.wx, "CallAfter", lambda f, *a, **k: self.fila.append((f, a, k))),
                                  (f1.wx, "CallLater", self._call_later)):
            patch = mock.patch.object(alvo, nome, falso)
            patch.start()
            self.addCleanup(patch.stop)

        plugin = types.SimpleNamespace(_fetchInProgress=False, config_lembretes={})
        plugin._carregar_cache = self._carregar_cache
        plugin._carregar_cache_stale = lambda modo: (self.velhos.get(modo), 10 if modo in self.velhos else None)
        plugin._baixar_json_em_thread = lambda modo, ok, fail: self.baixados.append((modo, ok, fail))
        plugin._mostrar_erro_simples = lambda: setattr(self, "erros_simples", self.erros_simples + 1)
        plugin._open_modo_substituindo = f1.GlobalPlugin._open_modo_substituindo.__get__(plugin)
        self.plugin = plugin

        self.dlg = dlg = types.SimpleNamespace()
        for nome in self.METODOS_JANELA:
            setattr(dlg, nome, getattr(f1.F1Dialog, nome).__get__(dlg))
        dlg.comboCategoria = ComboFalso()
        dlg.comboCategoria.Set([nome for nome, ids in f1.CATEGORIAS])
        dlg.comboOpcao = ComboFalso()
        dlg.lblOpcao = Focavel()
        dlg.mainPanel = PainelFalso()
        dlg._ids_das_opcoes = []
        dlg._opcao_visivel = True  # nasce visível, como na janela de verdade
        dlg._categoria_confirmada = 0
        dlg._etapa_fim_de_semana = None
        dlg._secoes_com_resultado = 0
        dlg._selecao_pendente = None
        dlg._hoje = lambda: self.hoje
        dlg.plugin_ref = plugin
        dlg._onChangeModo = plugin._open_modo_substituindo
        dlg._onForceRefresh = None
        dlg.arvore = ArvoreFalsa()
        dlg.titulo = None
        dlg.SetTitle = lambda t: setattr(dlg, "titulo", t)
        dlg._popular_arvore = self.popular_arvore_falsa
        dlg._set_atualizando = lambda atualizando: None
        dlg.destruida = False
        dlg.Destroy = lambda: setattr(dlg, "destruida", True)
        dlg.dados = []
        dlg.modo = "pilotos"
        dlg._atualizar_etapa()
        dlg._sincronizar_combos("pilotos")

    def _call_later(self, ms, f, *a, **k):
        if f.__name__ == "_passo_do_vigia":
            self.vigias.append((f, a, k))  # só roda quando o teste pedir
        else:
            self.fila.append((f, a, k))

    def _abrir_lista_falsa(self, combo):
        combo.aberta = True
        self.listas_abertas += 1

    def _carregar_cache(self, modo):
        self.pedidos.append(modo)
        if modo in self.sem_cache:
            return None
        return self.dados_por_modo.get(modo, [f"dado-{modo}"])

    def popular_arvore_falsa(self):
        """Faz o papel de _popular_arvore: um item por dado; ("texto", ["filho", ...]) cria filhos."""
        arvore = self.dlg.arvore
        arvore.limpar()
        for dado in self.dlg.dados:
            texto, filhos = (dado, ()) if isinstance(dado, str) else dado
            pai = arvore.adicionar(texto)
            for filho in filhos:
                arvore.adicionar(filho, pai=pai)
        if self.dlg.dados:
            primeiro = self.dlg.dados[0]
            self.cargas.append(primeiro if isinstance(primeiro, str) else primeiro[0])
        else:
            self.cargas.append(None)

    def usar_arvore_real(self):
        """Troca a árvore falsa pelo _popular_arvore de verdade (dados no formato da API)."""
        self.dlg._adicionar_piloto = f1.F1Dialog._adicionar_piloto.__get__(self.dlg)
        self.dlg._adicionar_qualificacao = f1.F1Dialog._adicionar_qualificacao.__get__(self.dlg)
        self.dlg._popular_fim_de_semana = f1.F1Dialog._popular_fim_de_semana.__get__(self.dlg)
        self.dlg._popular_arvore = f1.F1Dialog._popular_arvore.__get__(self.dlg)

    def com_calendario(self, hoje):
        self.velhos["calendario"] = CALENDARIO
        self.hoje = hoje
        self.dlg._atualizar_etapa()

    def iniciar_em(self, visao_id):
        """A janela já aberta mostrando esta visão (como se tivesse aberto assim)."""
        self.dlg.modo = visao_id
        self.dlg._sincronizar_combos(visao_id)
        painel = self.dlg.mainPanel
        painel.layouts = painel.freezes = painel.thaws = 0

    # ---- o que a pessoa faz

    def processar_fila(self):
        while self.fila:
            funcao, args, kwargs = self.fila.pop(0)
            funcao(*args, **kwargs)

    def apertar(self, codigo=None, processar=True):
        evento = EventoTecla(codigo or f1.wx.WXK_RETURN)
        self.dlg.ao_pressionar_esc(evento)
        if processar:
            self.processar_fila()
        return evento

    def seta_categoria(self, nome):
        """Foco na categoria e seta até ela: só muda a seleção da caixa, como o wx faz."""
        self.dlg.comboCategoria.com_foco = True
        self.dlg.comboCategoria.SetSelection(CATEGORIAS.index(nome))

    def seta_opcao(self, visao_id):
        self.dlg.comboOpcao.com_foco = True
        self.dlg.comboOpcao.SetSelection(self.dlg._ids_das_opcoes.index(visao_id))

    def escolher_categoria(self, nome, processar=True):
        self.seta_categoria(nome)
        return self.apertar(processar=processar)

    def abrir_opcao(self, visao_id):
        self.seta_opcao(visao_id)
        return self.apertar()

    def abrir(self, visao_id):
        """Todo o caminho até a visão: categoria (se mudou) e opção (se a caixa Opção está na tela)."""
        indice = f1._indice_da_categoria(visao_id)
        if indice != self.dlg._categoria_confirmada:
            self.escolher_categoria(CATEGORIAS[indice])
        if self.dlg.modo != visao_id and self.dlg._opcao_visivel:
            self.abrir_opcao(visao_id)

    def entrar_na_arvore(self):
        """Tab até a árvore: o foco chega e o handler de foco roda."""
        self.dlg.arvore.com_foco = True
        self.dlg._ao_focar_arvore(EventoFalso(self.dlg.arvore))

    def sair_da_arvore(self):
        self.dlg.arvore.com_foco = False


# ---------------------------------------------------------------- o registro e o calendário


class TestRegistro(unittest.TestCase):
    def test_registro_e_consistente(self):
        ids = [v[0] for v in f1.VISOES]
        self.assertEqual(len(ids), len(set(ids)), "ids de visão repetidos")
        for visao in f1.VISOES:
            self.assertEqual(len(visao), 4)
            self.assertTrue(all(isinstance(campo, str) and campo for campo in visao), visao)
            self.assertIn(visao[0], f1.MODOS, f"{visao[0]}: o id é o modo de dados e precisa de URL em MODOS")

    def test_toda_visao_esta_em_uma_categoria_so(self):
        todas = [i for nome, ids in f1.CATEGORIAS for i in ids]
        self.assertEqual(sorted(todas), sorted(v[0] for v in f1.VISOES))

    def test_nomes_das_categorias(self):
        self.assertEqual([nome for nome, ids in f1.CATEGORIAS], CATEGORIAS)

    def test_nomes_curtos_nao_se_repetem_na_categoria_e_nao_levam_prefixo(self):
        for nome, ids in f1.CATEGORIAS:
            curtos = [f1._visao_por_modo(i)[2] for i in ids]
            self.assertEqual(len(curtos), len(set(curtos)), nome)
            for curto in curtos:
                self.assertNotIn(":", curto)
                self.assertLessEqual(len(curto), 30)

    def test_so_o_titulo_do_fim_de_semana_traz_a_etapa(self):
        for visao in f1.VISOES:
            for texto in visao[1:3]:
                self.assertNotIn("{", texto, "os nomes não levam a etapa: cada um sabe qual quer ver")
            self.assertEqual("{rd}" in visao[3], visao[0] == f1.VISAO_FIM_DE_SEMANA, visao[0])

    def test_a_opcao_ultima_corrida_foi_removida(self):
        """O resultado do fim de semana já reúne a corrida mais recente."""
        self.assertNotIn("ultima_corrida", [v[0] for v in f1.VISOES])
        self.assertNotIn("ultima_corrida", f1.MODOS)
        self.assertNotIn("ultima_corrida", inspect.getsource(f1))

    def test_as_qualificacoes_sprint_ficam_na_caixa_das_qualificacoes(self):
        ids = dict(f1.CATEGORIAS)["Resultados"] if "Resultados" in dict(f1.CATEGORIAS) else None
        categoria = next(ids for nome, ids in f1.CATEGORIAS if nome == "Resultados")
        self.assertEqual(categoria, ["resultados", "resultados_sprint", "qualifying", "qualifying_sprint"])
        self.assertEqual(f1.MODOS["qualifying_sprint"], [], "vem da API alpha, sem URL Ergast")

    def test_indice_da_categoria(self):
        self.assertEqual(f1._indice_da_categoria("pilotos"), 0)
        self.assertEqual(f1._indice_da_categoria("proxima"), 1)
        self.assertEqual(f1._indice_da_categoria("calendario"), 2)
        self.assertEqual(f1._indice_da_categoria("qualifying"), 3)
        self.assertEqual(f1._indice_da_categoria("inexistente"), 0)


class TestEtapaDoFimDeSemana(unittest.TestCase):
    def rd(self, hoje, calendario=CALENDARIO):
        corrida = f1.etapa_do_fim_de_semana(calendario, hoje)
        return corrida["round"] if corrida else None

    def test_antes_da_primeira_etapa_nao_ha_fim_de_semana(self):
        self.assertIsNone(self.rd("2026-03-05"))

    def test_comeca_no_dia_do_primeiro_treino(self):
        self.assertEqual(self.rd("2026-03-06"), "1")

    def test_continua_na_mesma_etapa_ate_a_proxima_comecar(self):
        for dia in range(7, 20):
            self.assertEqual(self.rd(f"2026-03-{dia:02d}"), "1", dia)

    def test_etapa_de_sprint_vale_desde_a_sexta_e_depois_do_domingo(self):
        for dia in ("2026-03-20", "2026-03-21", "2026-03-22", "2026-03-23", "2026-04-02"):
            self.assertEqual(self.rd(dia), "2", dia)

    def test_a_ultima_etapa_continua_valendo_depois_do_fim(self):
        self.assertEqual(self.rd("2026-12-31"), "3")

    def test_calendario_fora_de_ordem(self):
        self.assertEqual(self.rd("2026-03-21", list(reversed(CALENDARIO))), "2")

    def test_sem_sessoes_no_calendario_vale_a_data_da_corrida(self):
        so_corrida = [{"round": "1", "date": "2026-03-08"}]
        self.assertIsNone(self.rd("2026-03-07", so_corrida))
        self.assertEqual(self.rd("2026-03-08", so_corrida), "1")

    def test_etapas_acima_de_nove_seguem_a_ordem_numerica(self):
        calendario = [{"round": "9", "date": "2026-09-06"}, {"round": "10", "date": "2026-09-20"}]
        self.assertEqual(self.rd("2026-10-01", calendario), "10")

    def test_calendario_vazio(self):
        self.assertIsNone(self.rd("2026-03-10", []))
        self.assertIsNone(self.rd("2026-03-10", None))


# ---------------------------------------------------------------- o estado das duas caixas


class TestEstadoInicial(BaseJanela):
    def test_abre_em_campeonato_com_a_caixa_opcao_mostrando_pilotos(self):
        d = self.dlg
        self.assertEqual(d.comboCategoria.itens, CATEGORIAS)
        self.assertEqual(d.comboCategoria.texto(), "Campeonato")
        self.assertTrue(d._opcao_visivel and d.comboOpcao.IsShown() and d.lblOpcao.IsShown())
        self.assertEqual(d.comboOpcao.itens, OPCOES_CAMPEONATO)
        self.assertEqual(d.comboOpcao.texto(), "Pilotos")

    def test_enter_na_categoria_campeonato_logo_ao_abrir_leva_o_foco_para_a_opcao(self):
        d = self.dlg
        d.comboCategoria.com_foco = True
        self.apertar()  # sem abrir lista nenhuma: o Enter já confirma
        self.assertFalse(d.comboCategoria.aberta)
        self.assertIs(Foco.atual, d.comboOpcao)
        self.assertEqual((self.cargas, self.pedidos), ([], []))

    def test_categoria_de_uma_opcao_abre_com_a_caixa_opcao_escondida(self):
        self.iniciar_em("calendario")
        d = self.dlg
        self.assertEqual(d.comboCategoria.texto(), "Temporada")
        self.assertFalse(d._opcao_visivel)
        self.assertFalse(d.comboOpcao.IsShown())
        self.assertFalse(d.lblOpcao.IsShown())
        self.assertFalse(d.comboOpcao.IsEnabled(), "escondida e desabilitada: o Tab não chega nela")

    def test_fim_de_semana_sem_calendario_so_tem_as_sessoes_e_nao_mostra_a_caixa_opcao(self):
        self.iniciar_em("proxima")
        self.assertEqual(self.dlg.comboCategoria.texto(), "Fim de semana")
        self.assertFalse(self.dlg._opcao_visivel)

    def test_fim_de_semana_com_calendario_tem_duas_opcoes(self):
        self.com_calendario("2026-03-21")
        self.iniciar_em("proxima")
        self.assertTrue(self.dlg._opcao_visivel)
        self.assertEqual(self.dlg.comboOpcao.itens, OPCOES_FIM_DE_SEMANA)
        self.assertEqual(self.dlg.comboOpcao.texto(), "Horários das sessões")

    def test_titulos_vem_do_registro(self):
        for visao in f1.VISOES:
            if visao[0] != f1.VISAO_FIM_DE_SEMANA:
                self.assertEqual(self.dlg._obter_titulo(visao[0]), visao[3])
        self.assertEqual(self.dlg._obter_titulo("inexistente"), "Fórmula 1")

    def test_titulo_do_fim_de_semana_leva_a_etapa(self):
        self.com_calendario("2026-03-21")
        self.assertEqual(self.dlg._obter_titulo("fim_de_semana"), "Fórmula 1 - Etapa 2, GP B - Resultado do fim de semana")

    def test_rotulos_curtos_e_claros(self):
        fonte = inspect.getsource(f1.F1Dialog.__init__)
        rotulos = re.findall(r'wx\.StaticText\(self\.mainPanel, label=_\("([^"]*)"\)\)', fonte)
        self.assertEqual(rotulos, [
            "Categoria (pressione Enter na categoria desejada e depois no item que deseja visualizar):", "Opção:"], "a instrução fica uma vez só, no rótulo da Categoria")
        instrucao = rotulos[0]
        self.assertEqual(instrucao.count("Enter"), 1)
        self.assertIn("na categoria desejada", instrucao)
        self.assertIn("depois no item que deseja visualizar", instrucao)
        self.assertLessEqual(len(instrucao), 100, "curta o bastante para não cansar")
        self.assertNotIn("Enter", rotulos[1], "a Opção é só o nome: a instrução não se repete a cada visita")

    def test_a_janela_cria_as_caixas_certas_com_rotulos_simples(self):
        fonte = inspect.getsource(f1.F1Dialog.__init__)
        rotulos = re.findall(r'label=_\("([^"]*)"\)', fonte.split("self.arvore = wx.TreeCtrl")[0])
        self.assertEqual(sum("Enter" in rotulo for rotulo in rotulos), 1, "a instrução do Enter aparece uma vez só")
        self.assertIn("self.comboCategoria = wx.Choice(", fonte)
        self.assertIn("self.comboOpcao = wx.Choice(self.mainPanel)", fonte)
        self.assertNotIn("ListBox", fonte)
        self.assertIn("self._sincronizar_combos(self.modo)", fonte)
        self.assertIn("self.comboCategoria.SetFocus()", fonte)
        self.assertIn("self._garantir_calendario()", fonte)


class TestSetasSoPercorrem(BaseJanela):
    def tudo_quieto(self):
        self.processar_fila()
        self.assertEqual((self.cargas, self.pedidos, self.baixados, FALAS), ([], [], [], []))
        self.assertEqual(self.dlg.modo, "pilotos")

    def test_percorrer_as_categorias_nao_mexe_em_nada_mais(self):
        d = self.dlg
        itens, vezes = list(d.comboOpcao.itens), d.comboOpcao.vezes_set
        for nome in CATEGORIAS:
            self.seta_categoria(nome)
        self.assertEqual(d.comboOpcao.itens, itens)
        self.assertEqual(d.comboOpcao.vezes_set, vezes)
        self.assertTrue(d._opcao_visivel)
        self.assertEqual((d.mainPanel.layouts, d.mainPanel.freezes), (0, 0))
        self.assertIs(Foco.atual, d.comboCategoria)
        self.tudo_quieto()

    def test_percorrer_as_opcoes_nao_carrega(self):
        for visao_id in list(self.dlg._ids_das_opcoes):
            self.seta_opcao(visao_id)
        self.assertIs(Foco.atual, self.dlg.comboOpcao)
        self.tudo_quieto()

    def test_ir_para_categoria_de_uma_opcao_nao_esconde_a_caixa_opcao(self):
        self.seta_categoria("Temporada")
        self.assertTrue(self.dlg._opcao_visivel)
        self.assertEqual(self.dlg.mainPanel.layouts, 0)
        self.tudo_quieto()


# ---------------------------------------------------------------- Enter na categoria


class TestEnterNaCategoria(BaseJanela):
    def test_categoria_com_varias_opcoes_leva_o_foco_para_a_opcao_em_silencio(self):
        d = self.dlg
        self.escolher_categoria("Resultados")
        self.assertEqual(d.comboOpcao.itens, OPCOES_RESULTADOS)
        self.assertEqual(d.comboOpcao.texto(), "Corridas principais")
        self.assertIs(Foco.atual, d.comboOpcao)
        self.assertEqual(d.comboOpcao.chamadas_set_focus, 1, "o foco se move uma vez só")
        self.assertEqual(FALAS, [], "o foco vai para a caixa e o leitor lê o rótulo dela; nada é dito sobre ela ter aparecido")
        self.assertEqual((self.cargas, self.pedidos), ([], []), "nada carregou ainda")
        self.assertEqual(d.modo, "pilotos")

    def test_caixa_opcao_escondida_aparece_de_uma_vez_e_em_silencio(self):
        self.iniciar_em("calendario")
        d = self.dlg
        self.escolher_categoria("Campeonato")
        self.assertTrue(d._opcao_visivel and d.comboOpcao.IsShown() and d.lblOpcao.IsShown())
        self.assertEqual((d.mainPanel.layouts, d.mainPanel.freezes, d.mainPanel.thaws), (1, 1, 1), "uma mudança só, congelada")
        self.assertIs(Foco.atual, d.comboOpcao)
        self.assertEqual(FALAS, [], "aparecer não é falado")

    def test_o_foco_so_vai_para_a_opcao_depois_que_tudo_foi_montado(self):
        self.escolher_categoria("Resultados", processar=False)
        self.assertIsNot(Foco.atual, self.dlg.comboOpcao, "o movimento do foco é o último passo, depois da tela pronta")
        self.processar_fila()
        self.assertIs(Foco.atual, self.dlg.comboOpcao)
        self.assertEqual(FALAS, [])

    def test_a_caixa_opcao_so_fica_habilitada_enquanto_aparece(self):
        d = self.dlg
        self.assertTrue(d.comboOpcao.IsEnabled())
        self.escolher_categoria("Temporada")
        self.assertFalse(d.comboOpcao.IsEnabled())
        self.assertFalse(d.comboOpcao.IsShown())
        self.escolher_categoria("Resultados")
        self.assertTrue(d.comboOpcao.IsEnabled())
        self.assertTrue(d.comboOpcao.IsShown())

    def test_nenhum_aviso_fala_das_caixas_aparecerem_ou_nao_existirem(self):
        """Percorre todas as categorias: só o aviso de carga é falado, nunca nada sobre a caixa Opção."""
        self.com_calendario("2026-03-21")
        for nome in CATEGORIAS + CATEGORIAS[::-1][1:]:  # ida e volta, sem repetir a última
            FALAS.clear()
            self.escolher_categoria(nome)
            self.assertFalse(any("caixa" in fala.lower() or "só tem uma opção" in fala or "Apareceu" in fala for fala in FALAS), (nome, FALAS))
            if self.dlg._opcao_visivel:
                self.abrir_opcao(self.dlg._ids_das_opcoes[-1])
                self.assertEqual(len(FALAS), 1, (nome, FALAS))
                self.assertTrue(FALAS[0].startswith("Carregou "), FALAS)

    def test_o_codigo_nao_tem_mais_os_avisos_das_caixas(self):
        fonte = inspect.getsource(f1)
        for frase in ("Apareceu a caixa", "só tem uma opção", "A caixa Opção agora tem"):
            self.assertNotIn(frase, fonte)

    def test_categoria_de_uma_opcao_abre_direto_e_esconde_a_caixa_opcao(self):
        d = self.dlg
        self.escolher_categoria("Temporada")
        self.assertEqual(d.modo, "calendario")
        self.assertFalse(d._opcao_visivel)
        self.assertFalse(d.comboOpcao.IsShown())
        self.assertIs(Foco.atual, d.comboCategoria, "o foco fica onde estava")
        self.assertEqual(d.comboOpcao.chamadas_set_focus, 0)
        self.assertEqual(FALAS, [carregou("Calendário", 1)], "só o aviso de carga: não se fala que a caixa não existe")

    def test_a_opcao_atual_vem_marcada_quando_a_categoria_a_contem(self):
        self.abrir("qualifying")
        self.escolher_categoria("Campeonato")
        self.assertEqual(self.dlg.comboOpcao.texto(), "Pilotos", "o que está na tela não é do Campeonato: começa pela primeira")
        self.escolher_categoria("Resultados")
        self.assertEqual(self.dlg.comboOpcao.texto(), "Qualificações", "o que está na tela é desta categoria")

    def test_enter_na_categoria_que_ja_esta_escolhida_leva_a_opcao_sem_carregar(self):
        self.dlg.comboCategoria.com_foco = True
        self.apertar()
        self.assertFalse(self.dlg.comboCategoria.aberta)
        self.assertIs(Foco.atual, self.dlg.comboOpcao)
        self.assertEqual((self.cargas, self.pedidos, FALAS), ([], [], []))

    def test_falha_em_categoria_de_uma_opcao_e_tentada_de_novo_pelo_enter(self):
        self.sem_cache = {"calendario"}
        self.escolher_categoria("Temporada")
        self.baixados[0][2]()  # o download falhou
        self.assertTrue(FALAS[-1].startswith("Não foi possível carregar Calendário."))
        self.assertEqual(self.dlg.modo, "pilotos")
        self.apertar()  # a categoria continua escolhida: o Enter tenta de novo, não abre a lista
        self.assertEqual(len(self.baixados), 2)
        self.assertEqual(self.listas_abertas, 0)
        self.baixados[1][1](["Etapa 1"])
        self.assertEqual(self.dlg.modo, "calendario")

    def test_enter_sem_categoria_selecionada_nao_faz_nada(self):
        self.dlg.comboCategoria.selecao = -1
        self.dlg.comboCategoria.com_foco = True
        self.apertar()
        self.assertEqual((self.cargas, self.pedidos, FALAS), ([], [], []))

    def test_fim_de_semana_sem_calendario_abre_as_sessoes_direto(self):
        self.escolher_categoria("Fim de semana")
        self.assertEqual(self.dlg.modo, "proxima")
        self.assertEqual(FALAS, [carregou("Sessões do fim de semana", 1)])

    def test_fim_de_semana_com_calendario_oferece_o_resultado_primeiro(self):
        self.com_calendario("2026-03-21")
        self.escolher_categoria("Fim de semana")
        self.assertEqual(self.dlg.comboOpcao.itens, OPCOES_FIM_DE_SEMANA)
        self.assertEqual(self.dlg.comboOpcao.texto(), "Resultado")
        self.assertEqual(self.dlg.modo, "pilotos", "só escolheu a categoria")


# ---------------------------------------------------------------- Enter na opção


class TestEnterNaOpcao(BaseJanela):
    def test_abre_a_opcao_escolhida_e_o_foco_continua_na_caixa(self):
        self.abrir("construtores")
        d = self.dlg
        self.assertEqual(d.modo, "construtores")
        self.assertEqual(d.titulo, "Fórmula 1 - Classificação de Construtores")
        self.assertEqual(self.cargas, ["dado-construtores"])
        self.assertEqual(FALAS[-1], carregou("Campeonato de construtores", 1))
        self.assertIs(Foco.atual, d.comboOpcao)
        self.assertEqual(d.comboOpcao.chamadas_set_focus, 0)

    def test_enter_na_opcao_que_ja_esta_aberta_avisa_que_ja_esta_mostrando(self):
        self.abrir("construtores")
        FALAS.clear()
        self.apertar()
        self.assertFalse(self.dlg.comboOpcao.aberta)
        self.assertEqual(FALAS, ["Já está mostrando Campeonato de construtores. Use Atualizar dados para buscar dados novos."])

    def test_enter_com_plugin_ocupado_avisa_e_nao_muda_nada(self):
        self.plugin._fetchInProgress = True
        self.abrir("construtores")
        self.assertEqual(FALAS[-1], "Aguarde, buscando dados.")
        self.assertEqual(self.dlg.modo, "pilotos")
        self.assertEqual(self.cargas, [])

    def test_seguir_andando_pelas_opcoes_durante_o_download_nao_muda_a_escolha(self):
        self.sem_cache = {"construtores"}
        self.abrir("construtores")
        self.assertEqual(FALAS[-1], "Buscando dados da Fórmula 1.")
        self.seta_opcao("pilotos")  # a pessoa seguiu andando enquanto baixava
        self.baixados[0][1](["Equipe A", "Equipe B"])
        self.assertEqual(self.dlg.modo, "construtores", "a janela mostra o que foi pedido")
        self.assertEqual(self.dlg._id_da_opcao_selecionada(), "pilotos", "a seleção da caixa continua onde a pessoa deixou")

    def test_a_caixa_opcao_nao_e_reescrita_quando_os_dados_chegam(self):
        vezes = self.dlg.comboOpcao.vezes_set
        self.abrir("construtores")
        self.assertEqual(self.dlg.comboOpcao.vezes_set, vezes)
        self.assertEqual(self.dlg.mainPanel.layouts, 0)

    def test_toda_visao_e_alcancavel_e_pede_os_dados_certos(self):
        self.com_calendario("2026-03-21")
        for visao in f1.VISOES:
            visao_id = visao[0]
            if visao_id == self.dlg.modo:
                continue
            self.pedidos.clear()
            self.abrir(visao_id)
            self.assertEqual(self.dlg.modo, visao_id, visao_id)
            self.assertEqual(self.pedidos[-1], visao_id, "o id da visão é o modo de dados")
            self.assertEqual(self.dlg.comboCategoria.texto(), CATEGORIAS[f1._indice_da_categoria(visao_id)])
            if self.dlg._opcao_visivel:
                self.assertEqual(self.dlg.comboOpcao.texto(), visao[2], visao_id)


# ---------------------------------------------------------------- a lista aberta de cada caixa


class TestListaAbertaDoCombo(BaseJanela):
    """Lista aberta à mão (Alt+Seta): as setas só percorrem e Enter escolhe; Esc só fecha a lista."""

    def escolher_na_lista_nativa(self, combo, indice):
        """O que o Windows faz quando o Enter chega à lista aberta: fica com a opção e fecha a lista."""
        combo.SetSelection(indice)
        combo.aberta = False

    def test_setas_com_a_lista_aberta_so_percorrem(self):
        self.dlg.comboOpcao.com_foco = True
        self.dlg.comboOpcao.aberta = True
        self.seta_opcao("construtores")
        self.seta_opcao("pilotos")
        self.processar_fila()
        self.assertEqual((self.cargas, self.pedidos, FALAS), ([], [], []))

    def test_enter_com_a_lista_da_opcao_aberta_deixa_o_combo_escolher_e_abre_depois(self):
        self.dlg.comboOpcao.com_foco = True
        self.dlg.comboOpcao.aberta = True  # a pessoa abriu a lista (Alt+Seta)
        self.seta_opcao("construtores")
        evento = self.apertar(processar=False)  # escolhe
        self.assertTrue(evento.pulou, "a tecla segue para o combo, que fecha a lista")
        self.assertEqual(self.dlg.modo, "pilotos", "ainda não abriu: o combo ainda não fechou a lista")
        self.dlg.comboOpcao.aberta = False
        self.processar_fila()
        self.assertEqual(self.dlg.modo, "construtores")
        self.assertEqual(FALAS[-1], carregou("Campeonato de construtores", 1))

    def test_escolher_a_mesma_opcao_na_lista_avisa_que_ja_esta_mostrando(self):
        self.abrir("construtores")
        FALAS.clear()
        self.dlg.comboOpcao.aberta = True
        self.apertar(processar=False)  # escolhe a mesma
        self.dlg.comboOpcao.aberta = False
        self.processar_fila()
        self.assertEqual(FALAS, ["Já está mostrando Campeonato de construtores. Use Atualizar dados para buscar dados novos."])

    def test_enter_com_a_lista_da_categoria_aberta_confirma_depois_e_leva_o_foco_para_a_opcao(self):
        self.dlg.comboCategoria.com_foco = True
        self.dlg.comboCategoria.aberta = True
        self.dlg.comboCategoria.SetSelection(CATEGORIAS.index("Resultados"))
        evento = self.apertar(processar=False)
        self.assertTrue(evento.pulou)
        self.assertEqual(self.dlg.comboOpcao.itens, OPCOES_CAMPEONATO, "ainda não mudou")
        self.dlg.comboCategoria.aberta = False
        self.processar_fila()
        self.assertEqual(self.dlg.comboOpcao.itens, OPCOES_RESULTADOS)
        self.assertIs(Foco.atual, self.dlg.comboOpcao)

    def test_esc_com_a_lista_aberta_so_fecha_a_lista(self):
        for combo in (self.dlg.comboCategoria, self.dlg.comboOpcao):
            combo.com_foco = True
            combo.aberta = True
            evento = self.apertar(f1.wx.WXK_ESCAPE)
            self.assertTrue(evento.pulou, "o Esc segue para o combo")
            self.assertFalse(self.dlg.destruida, "a janela não fecha")
            combo.aberta = False

    def test_esc_com_as_listas_fechadas_fecha_a_janela(self):
        self.dlg.comboOpcao.com_foco = True
        evento = self.apertar(f1.wx.WXK_ESCAPE)
        self.assertTrue(self.dlg.destruida)
        self.assertFalse(evento.pulou)

    def test_esc_fora_das_caixas_fecha_a_janela_mesmo_com_uma_lista_aberta(self):
        self.dlg.comboOpcao.aberta = True
        self.dlg.arvore.com_foco = True
        self.apertar(f1.wx.WXK_ESCAPE)
        self.assertTrue(self.dlg.destruida)

    def test_enter_fora_das_caixas_segue_para_o_controle(self):
        self.dlg.arvore.com_foco = True
        self.seta_opcao("construtores")
        self.dlg.arvore.com_foco = True
        evento = self.apertar()
        self.assertTrue(evento.pulou, "a tecla segue para a árvore")
        self.assertEqual((self.dlg.modo, self.cargas), ("pilotos", []))

    def test_enter_numerico_funciona_igual(self):
        self.seta_opcao("construtores")
        evento = self.apertar(f1.wx.WXK_NUMPAD_ENTER)
        self.assertEqual(self.dlg.modo, "construtores")
        self.assertFalse(evento.pulou)

    def test_janela_fechada_antes_da_confirmacao_nao_quebra(self):
        def janela_destruida():
            raise RuntimeError("wrapped C/C++ object has been deleted")

        self.dlg._confirmar_depois(janela_destruida)  # não pode levantar
        self.dlg.comboOpcao.set_focus_falha = True
        self.dlg._ir_para_a_opcao()  # não pode levantar
        self.assertEqual(FALAS, [])


class TestMensagensDoWindowsParaOCombo(unittest.TestCase):
    """As duas funções que falam com o Windows, sem o combo falso."""

    def test_combo_invalido_nao_derruba(self):
        sem_janela = types.SimpleNamespace(GetHandle=lambda: 0)
        self.assertFalse(LISTA_ABERTA_REAL(sem_janela))
        ABRIR_LISTA_REAL(sem_janela)  # não pode levantar

    def test_objeto_sem_handle_nao_derruba(self):
        self.assertFalse(LISTA_ABERTA_REAL(object()))
        ABRIR_LISTA_REAL(object())

    @unittest.skipUnless(sys.platform == "win32", "o combo nativo só existe no Windows")
    def test_com_um_combo_nativo_de_verdade(self):
        import ctypes
        from ctypes import wintypes

        u = ctypes.windll.user32
        u.CreateWindowExW.restype = wintypes.HWND
        u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                      wintypes.HINSTANCE, wintypes.LPVOID]
        u.SendMessageW.restype = ctypes.c_ssize_t
        u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.DestroyWindow.argtypes = [wintypes.HWND]
        pai = u.CreateWindowExW(0, "STATIC", "", 0x80000000 | 0x10000000, -32000, -32000, 300, 300, None, None, None, None)
        if not pai:
            self.skipTest("não foi possível criar uma janela de teste")
        try:
            handle = u.CreateWindowExW(0, "COMBOBOX", "", 0x40000000 | 0x10000000 | 0x0003 | 0x00200000, 0, 0, 200, 200,
                                       pai, None, None, None)
            if not handle:
                self.skipTest("não foi possível criar um combo de teste")
            combo = types.SimpleNamespace(GetHandle=lambda: handle)
            self.assertFalse(LISTA_ABERTA_REAL(combo))
            ABRIR_LISTA_REAL(combo)
            self.assertTrue(LISTA_ABERTA_REAL(combo), "a lista de opções abriu")
            u.SendMessageW(handle, 0x014F, 0, 0)  # CB_SHOWDROPDOWN: fecha
            self.assertFalse(LISTA_ABERTA_REAL(combo))
        finally:
            u.DestroyWindow(pai)


# ---------------------------------------------------------------- calendário em segundo plano


class TestCalendarioEmSegundoPlano(BaseJanela):
    def test_sem_calendario_busca_em_silencio_sem_mexer_em_nenhuma_caixa(self):
        self.hoje = "2026-03-21"
        d = self.dlg
        itens, vezes, visivel = list(d.comboOpcao.itens), d.comboOpcao.vezes_set, d._opcao_visivel
        self.dlg._garantir_calendario()
        self.assertEqual([b[0] for b in self.baixados], ["calendario"])
        self.velhos["calendario"] = CALENDARIO  # o plugin grava o cache antes de avisar
        self.baixados[0][1](CALENDARIO)
        self.assertIsNotNone(d._etapa_fim_de_semana, "passou a saber qual é a etapa")
        self.assertEqual((d.comboOpcao.itens, d.comboOpcao.vezes_set, d._opcao_visivel), (itens, vezes, visivel))
        self.assertEqual((d.mainPanel.layouts, d.mainPanel.freezes), (0, 0))
        self.assertEqual(FALAS, [], "buscar o calendário não fala nada")
        self.processar_fila()
        self.assertEqual(Foco.atual, None)

    def test_o_resultado_do_fim_de_semana_aparece_na_proxima_vez_que_a_categoria_e_escolhida(self):
        self.hoje = "2026-03-21"
        self.dlg._garantir_calendario()
        self.velhos["calendario"] = CALENDARIO
        self.baixados[0][1](CALENDARIO)
        self.escolher_categoria("Fim de semana")
        self.assertEqual(self.dlg.comboOpcao.itens, OPCOES_FIM_DE_SEMANA)

    def test_com_calendario_em_cache_nao_baixa(self):
        self.com_calendario("2026-03-21")
        self.dlg._garantir_calendario()
        self.assertEqual(self.baixados, [])

    def test_calendario_em_cache_antes_da_temporada_tambem_nao_baixa(self):
        self.com_calendario("2026-01-01")
        self.dlg._garantir_calendario()
        self.assertEqual(self.baixados, [])

    def test_com_o_plugin_ocupado_nao_baixa(self):
        self.plugin._fetchInProgress = True
        self.dlg._garantir_calendario()
        self.assertEqual(self.baixados, [])

    def test_sem_plugin_nao_baixa(self):
        self.dlg.plugin_ref = None
        self.dlg._garantir_calendario()
        self.assertEqual(self.baixados, [])

    def test_falha_ao_baixar_o_calendario_e_silenciosa(self):
        self.dlg._garantir_calendario()
        self.baixados[0][2]()
        self.assertEqual(FALAS, [])
        self.assertIsNone(self.dlg._etapa_fim_de_semana)


# ---------------------------------------------------------------- avisos de carga e de falha


class TestAvisos(BaseJanela):
    def test_aviso_diz_quantos_itens_carregaram(self):
        self.dados_por_modo["construtores"] = [f"Equipe {i}" for i in range(10)]
        self.abrir("construtores")
        self.assertEqual(FALAS[-1], carregou("Campeonato de construtores", 10))
        self.dados_por_modo["calendario"] = ["Etapa 1"]
        self.abrir("calendario")
        self.assertEqual(FALAS[-1], carregou("Calendário", 1))

    def test_na_arvore_o_aviso_nao_manda_ir_para_ela(self):
        self.dlg.arvore.com_foco = True
        self.dlg.comboOpcao.SetSelection(1)
        self.dlg._confirmar_opcao()
        self.processar_fila()
        self.assertEqual(FALAS[-1], "Carregou Campeonato de construtores: 1 item.")

    def test_sem_resultados_o_aviso_diz_que_ainda_nao_ha(self):
        self.dados_por_modo["resultados_sprint"] = []
        self.abrir("resultados_sprint")
        self.assertEqual(FALAS[-1], "Resultados das corridas sprint: ainda não há resultados nesta temporada.")

    def test_download_primeiro_avisa_que_busca_e_depois_que_carregou(self):
        self.sem_cache = {"construtores"}
        self.abrir("construtores")
        self.assertEqual(FALAS, ["Buscando dados da Fórmula 1."])
        self.assertEqual(self.dlg.modo, "pilotos", "ainda não mudou")
        self.baixados[0][1](["Equipe A", "Equipe B"])
        self.assertEqual(FALAS[-1], carregou("Campeonato de construtores", 2))
        self.assertEqual(self.dlg.modo, "construtores")

    def test_falha_sem_cache_avisa_o_que_nao_carregou_e_o_que_continua(self):
        self.sem_cache = {"construtores"}
        self.abrir("construtores")
        self.baixados[0][2]()
        self.assertEqual(FALAS[-1], "Não foi possível carregar Campeonato de construtores. "
                                    "A janela continua mostrando Campeonato de pilotos. Pressione Enter para tentar de novo.")
        self.assertEqual(self.dlg.modo, "pilotos")
        self.assertEqual(self.dlg.titulo, None, "o título não mudou")
        self.assertEqual(self.dlg._id_da_opcao_selecionada(), "construtores", "a escolha fica, para o Enter tentar de novo")
        self.assertEqual(self.erros_simples, 0, "o aviso falado substitui o diálogo de erro genérico")

    def test_enter_de_novo_depois_da_falha_tenta_outra_vez(self):
        self.sem_cache = {"construtores"}
        self.abrir("construtores")
        self.baixados[0][2]()
        self.apertar()
        self.assertEqual(len(self.baixados), 2)
        self.baixados[1][1](["Equipe A"])
        self.assertEqual(self.dlg.modo, "construtores")

    def test_falha_com_cache_antigo_mostra_o_cache_e_avisa(self):
        self.sem_cache = {"construtores"}
        self.velhos["construtores"] = ["Equipe A", "Equipe B"]
        self.abrir("construtores")
        self.baixados[0][2]()
        self.assertIn("Mostrando dados do cache.", FALAS)
        self.assertEqual(FALAS[-1], carregou("Campeonato de construtores", 2))
        self.assertEqual(self.dlg.modo, "construtores")

    def test_atualizar_dados_avisa_quando_termina(self):
        self.abrir("construtores")
        self.dlg._onForceRefresh = lambda modo, ok, fail: ok(["Equipe A"])
        self.dlg._on_click_atualizar(None)
        self.assertEqual(FALAS[-2:], ["Atualizando dados da tabela...", "Tabela atualizada."])


# ---------------------------------------------------------------- resultado do fim de semana


class TestResultadoDoFimDeSemana(BaseJanela):
    def setUp(self):
        super().setUp()
        self.usar_arvore_real()
        self.com_calendario("2026-03-21")  # etapa 2, com sprint

    def abrir_resultado(self, dados):
        self.dados_por_modo["fim_de_semana"] = dados
        self.abrir("fim_de_semana")

    def test_sprint_e_principal_viram_duas_secoes_da_etapa(self):
        self.abrir_resultado([_corrida("1", "GP A", False, [SEGUNDO]),
                              _corrida("2", "GP B", False, [VENCEDOR, SEGUNDO, ABANDONO]),
                              _corrida("2", "GP B", True, [SEGUNDO, VENCEDOR])])
        self.assertEqual(_estrutura(self.dlg.arvore), [
            ("Corrida principal (vencedor: Max Verstappen)", [LINHA_VENCEDOR, LINHA_SEGUNDO, LINHA_ABANDONO]),
            ("Corrida sprint (vencedor: Lando Norris)", [LINHA_SEGUNDO, LINHA_VENCEDOR]),
            ("Qualificação sprint: resultado ainda não disponível", []),
        ])
        self.assertEqual(FALAS[-1], carregou("Resultado do fim de semana", 3))

    def test_os_dados_vem_das_duas_urls_de_uma_vez(self):
        self.abrir_resultado([_corrida("2", "GP B", False, [VENCEDOR])])
        self.assertEqual(self.pedidos[-1], "fim_de_semana")
        self.assertEqual(f1.MODOS["fim_de_semana"], [f1.URL_RESULTADOS, f1.URL_SPRINTS])

    def test_o_titulo_traz_a_etapa(self):
        self.abrir_resultado([_corrida("2", "GP B", False, [VENCEDOR])])
        self.assertEqual(self.dlg.titulo, "Fórmula 1 - Etapa 2, GP B - Resultado do fim de semana")

    def test_etapa_sem_sprint_so_tem_a_secao_da_principal(self):
        self.com_calendario("2026-03-10")  # etapa 1
        self.abrir_resultado([_corrida("1", "GP A", False, [VENCEDOR])])
        self.assertEqual(_estrutura(self.dlg.arvore), [("Corrida principal (vencedor: Max Verstappen)", [LINHA_VENCEDOR])])
        self.assertEqual(FALAS[-1], carregou("Resultado do fim de semana", 1))

    def test_sprint_ja_saiu_mas_a_principal_ainda_nao(self):
        self.abrir_resultado([_corrida("2", "GP B", True, [VENCEDOR])])
        self.assertEqual(_estrutura(self.dlg.arvore), [
            ("Corrida principal: resultado ainda não disponível", []),
            ("Corrida sprint (vencedor: Max Verstappen)", [LINHA_VENCEDOR]),
            ("Qualificação sprint: resultado ainda não disponível", []),
        ])
        self.assertEqual(FALAS[-1], carregou("Resultado do fim de semana", 3))

    def test_nenhum_resultado_saiu_avisa_no_lugar_da_contagem(self):
        self.abrir_resultado([_corrida("1", "GP A", False, [SEGUNDO])])
        self.assertEqual(_estrutura(self.dlg.arvore), [
            ("Corrida principal: resultado ainda não disponível", []),
            ("Corrida sprint: resultado ainda não disponível", []),
            ("Qualificação sprint: resultado ainda não disponível", []),
        ])
        self.assertEqual(FALAS[-1], "Resultado do fim de semana: os resultados ainda não estão disponíveis. Use Atualizar dados mais tarde.")

    def test_as_tres_secoes_de_uma_etapa_com_sprint_da_mais_recente_para_a_mais_antiga(self):
        self.abrir_resultado([_corrida("2", "GP B", False, [VENCEDOR]), _corrida("2", "GP B", True, [VENCEDOR]),
                              _qualificacao(2, "GP B", SQ_CHINA_ALPHA)])
        self.assertEqual(_estrutura(self.dlg.arvore), [
            ("Corrida principal (vencedor: Max Verstappen)", [LINHA_VENCEDOR]),
            ("Corrida sprint (vencedor: Max Verstappen)", [LINHA_VENCEDOR]),
            ("Qualificação sprint (pole: George Russell)", [(linha, []) for linha in LINHAS_SQ_CHINA]),
        ])
        self.assertEqual(FALAS[-1], carregou("Resultado do fim de semana", 3))

    def test_na_sexta_so_a_qualificacao_sprint_tem_resultado(self):
        self.abrir_resultado([_qualificacao(2, "GP B", SQ_CHINA_ALPHA)])
        arvore = _estrutura(self.dlg.arvore)
        self.assertEqual([secao[0] for secao in arvore], [
            "Corrida principal: resultado ainda não disponível",
            "Corrida sprint: resultado ainda não disponível",
            "Qualificação sprint (pole: George Russell)"])
        self.assertTrue(FALAS[-1].startswith("Carregou Resultado do fim de semana: 3 itens."), FALAS[-1])

    def test_a_qualificacao_de_outra_etapa_nao_entra(self):
        self.abrir_resultado([_corrida("2", "GP B", False, [VENCEDOR]), _qualificacao(4, "Miami", SQ_MIAMI_ALPHA)])
        self.assertEqual(_estrutura(self.dlg.arvore)[-1], ("Qualificação sprint: resultado ainda não disponível", []))

    def test_etapa_sem_sprint_nao_tem_qualificacao_sprint(self):
        self.com_calendario("2026-03-10")  # etapa 1
        self.abrir_resultado([_corrida("1", "GP A", False, [VENCEDOR])])
        self.assertEqual([secao[0] for secao in _estrutura(self.dlg.arvore)], ["Corrida principal (vencedor: Max Verstappen)"])

    def test_lista_vazia_tambem_avisa(self):
        self.abrir_resultado([])
        self.assertTrue(FALAS[-1].startswith("Resultado do fim de semana: os resultados ainda não estão disponíveis."))

    def test_uma_seta_sobre_a_secao_ja_mostra_os_pilotos(self):
        self.abrir_resultado([_corrida("2", "GP B", False, [VENCEDOR, SEGUNDO]), _corrida("2", "GP B", True, [VENCEDOR])])
        for _titulo, filhos in _estrutura(self.dlg.arvore):
            for _piloto, detalhes in filhos:
                self.assertEqual([d[0].split(":")[0] for d in detalhes], ["Tempo/Status", "Pontos ganhos"])

    def test_ao_entrar_na_arvore_comeca_na_primeira_secao(self):
        self.abrir_resultado([_corrida("2", "GP B", False, [VENCEDOR])])
        self.assertEqual(self.dlg.arvore.selecoes, [])
        self.entrar_na_arvore()
        self.assertEqual(self.dlg.arvore.selecoes, ["Corrida principal (vencedor: Max Verstappen)"])

    def test_atualizar_busca_os_dados_do_fim_de_semana(self):
        self.abrir_resultado([_corrida("2", "GP B", False, [VENCEDOR])])
        pedidos = []
        self.dlg._onForceRefresh = lambda modo, ok, fail: (pedidos.append(modo), ok([_corrida("2", "GP B", False, [VENCEDOR, SEGUNDO])]))
        self.dlg._on_click_atualizar(None)
        self.assertEqual(pedidos, ["fim_de_semana"])
        secao = _estrutura(self.dlg.arvore)[0]
        self.assertEqual([p[0] for p in secao[1]], ["1º Max Verstappen (Red Bull)", "2º Lando Norris (McLaren)"])

    def test_etapa_numerica_e_texto_batem(self):
        self.abrir_resultado([{"round": 2, "raceName": "GP B", "_is_sprint": False, "Results": [VENCEDOR]}])
        self.assertEqual(_estrutura(self.dlg.arvore)[0][0], "Corrida principal (vencedor: Max Verstappen)")


# ---------------------------------------------------------------- foco e seleção da árvore


class TestFocoESelecaoDaArvore(BaseJanela):
    """A árvore só é tocada quando tem o foco: é isso que evita o leitor de tela pular para ela."""

    def carregar(self, visao, dados):
        self.dados_por_modo[visao] = dados
        self.abrir(visao)

    def test_carregar_com_foco_nas_caixas_nao_seleciona_nada_na_arvore(self):
        self.carregar("construtores", ["Equipe A", "Equipe B"])
        self.carregar("pilotos", ["Piloto 1", "Piloto 2"])
        self.assertEqual(self.dlg.arvore.selecoes, [])

    def test_arvore_e_reconstruida_congelada(self):
        self.carregar("construtores", ["Equipe A"])
        self.carregar("pilotos", ["Piloto 1"])
        self.assertEqual(self.dlg.arvore.freezes, 2)
        self.assertEqual(self.dlg.arvore.thaws, 2, "todo Freeze precisa de um Thaw")

    def test_entrar_na_arvore_seleciona_o_primeiro_antes_do_foco_seguir(self):
        self.carregar("construtores", ["Equipe A", "Equipe B"])
        self.entrar_na_arvore()
        self.assertEqual(self.dlg.arvore.eventos, [("select", "Equipe A"), ("skip", None)])

    def test_voltar_a_arvore_nao_muda_o_que_a_pessoa_ja_escolheu(self):
        self.carregar("construtores", ["Equipe A", "Equipe B"])
        self.entrar_na_arvore()
        itens = self.dlg._filhos(self.dlg.arvore.GetRootItem())
        self.dlg.arvore.SelectItem(itens[1])  # seta para baixo
        self.sair_da_arvore()
        self.entrar_na_arvore()
        self.assertEqual(self.dlg.arvore.selecoes, ["Equipe A", "Equipe B"])

    def test_arvore_vazia_nao_quebra_ao_receber_o_foco(self):
        self.dlg.dados = []
        self.dlg.arvore.limpar()
        self.entrar_na_arvore()
        self.assertEqual(self.dlg.arvore.selecoes, [])

    # ---- Atualizar dados

    def pilotos(self, n):
        return [f"{i + 1}º Piloto" for i in range(n)]

    def ler_ate_o_item(self, indice):
        """A pessoa entra na árvore, desce até o item e vai para o botão Atualizar."""
        self.entrar_na_arvore()
        itens = self.dlg._filhos(self.dlg.arvore.GetRootItem())
        self.dlg.arvore.SelectItem(itens[indice])
        self.sair_da_arvore()

    def atualizar_pelo_botao(self, novos):
        self.dlg._onForceRefresh = lambda modo, ok, fail: ok(novos)
        self.dlg._on_click_atualizar(None)

    def test_atualizar_volta_para_o_item_que_a_pessoa_estava_lendo(self):
        self.carregar("construtores", self.pilotos(20))
        self.ler_ate_o_item(14)
        antes = len(self.dlg.arvore.selecoes)
        self.atualizar_pelo_botao(self.pilotos(20))
        self.assertEqual(len(self.dlg.arvore.selecoes), antes, "com o foco no botão a árvore não é tocada")
        self.entrar_na_arvore()
        self.assertEqual(self.dlg.arvore.selecoes[-1], "15º Piloto")
        self.assertEqual(FALAS[-1], "Tabela atualizada.")

    def test_atualizar_com_a_lista_menor_cai_no_ultimo_item(self):
        self.carregar("construtores", self.pilotos(20))
        self.ler_ate_o_item(14)
        self.atualizar_pelo_botao(self.pilotos(10))
        self.entrar_na_arvore()
        self.assertEqual(self.dlg.arvore.selecoes[-1], "10º Piloto")

    def test_atualizar_preserva_item_filho(self):
        self.carregar("calendario", [("1º A", ["Equipe: X", "Vitórias: 3"]), ("2º B", ["Equipe: Y", "Vitórias: 1"])])
        self.dlg.arvore.com_foco = True
        segundo = self.dlg._filhos(self.dlg.arvore.GetRootItem())[1]
        vitorias = self.dlg._filhos(segundo)[1]
        self.dlg.arvore.SelectItem(vitorias)
        self.sair_da_arvore()
        self.atualizar_pelo_botao([("1º A", ["Equipe: X", "Vitórias: 4"]), ("2º B", ["Equipe: Y", "Vitórias: 2"])])
        self.entrar_na_arvore()
        self.assertEqual(self.dlg.arvore.selecoes[-1], "Vitórias: 2")

    def test_atualizar_com_a_arvore_em_foco_restaura_na_hora(self):
        self.carregar("construtores", self.pilotos(20))
        self.ler_ate_o_item(6)
        self.dlg.arvore.com_foco = True
        self.dlg._atualizar_dados_na_tela(self.pilotos(20), preservar_posicao=True)
        self.assertEqual(self.dlg.arvore.selecoes[-1], "7º Piloto")

    def test_abrir_outra_opcao_nao_herda_a_posicao_da_anterior(self):
        self.carregar("construtores", self.pilotos(20))
        self.ler_ate_o_item(14)
        self.carregar("pilotos", [f"Piloto {i}" for i in range(1, 25)])
        self.entrar_na_arvore()
        self.assertEqual(self.dlg.arvore.selecoes[-1], "Piloto 1")

    def test_atualizar_sem_nada_selecionado_cai_no_primeiro(self):
        self.carregar("construtores", self.pilotos(5))
        self.atualizar_pelo_botao(self.pilotos(5))
        self.entrar_na_arvore()
        self.assertEqual(self.dlg.arvore.selecoes, ["1º Piloto"])

    def test_instrucao_depende_de_onde_esta_o_foco(self):
        self.carregar("construtores", ["Equipe A"])
        self.assertTrue(FALAS[-1].endswith("Pressione Tab para ler os resultados."), FALAS[-1])
        self.dlg.arvore.com_foco = True
        self.dlg.comboOpcao.SetSelection(0)
        self.dlg._confirmar_opcao()
        self.processar_fila()
        self.assertEqual(FALAS[-1], "Carregou Campeonato de pilotos: 1 item.", "já está nos resultados: sem instrução")


class TestFocoPreservado(BaseJanela):
    """O foco fica onde a pessoa estava, mesmo que o Windows o leve para outro controle durante a atualização."""

    def test_foco_na_opcao_continua_nela_se_a_arvore_roubar(self):
        self.dlg.arvore.rouba_foco_em = {"Freeze", "Thaw"}
        self.abrir("construtores")
        self.assertIs(Foco.atual, self.dlg.comboOpcao)

    def test_foco_na_categoria_continua_nela_quando_a_carga_chega(self):
        self.dlg.arvore.rouba_foco_em = {"Freeze", "Thaw"}
        self.escolher_categoria("Temporada")
        self.assertIs(Foco.atual, self.dlg.comboCategoria)

    def test_foco_nos_resultados_continua_neles_se_uma_caixa_roubar(self):
        self.dlg.comboOpcao.rouba_foco_em = {"SetSelection", "Set"}
        self.dlg.arvore.com_foco = True
        self.dlg.comboOpcao.selecao = 1
        self.dlg._confirmar_opcao()
        self.processar_fila()
        self.assertIs(Foco.atual, self.dlg.arvore)

    def test_atualizar_com_foco_nos_resultados_continua_nos_resultados(self):
        self.dados_por_modo["construtores"] = ["Equipe A", "Equipe B"]
        self.abrir("construtores")
        self.entrar_na_arvore()
        self.dlg.arvore.rouba_foco_em = {"Freeze", "Thaw"}
        self.dlg.arvore.rouba_para = self.dlg.comboCategoria
        self.dlg._atualizar_dados_na_tela(["Equipe A", "Equipe B"], preservar_posicao=True)
        self.processar_fila()
        self.assertIs(Foco.atual, self.dlg.arvore)

    def test_sem_foco_na_janela_nada_e_forcado(self):
        self.dlg.comboOpcao.selecao = 1  # a pessoa está em outro programa: foco None
        self.dlg._confirmar_opcao()
        self.processar_fila()
        for controle in (self.dlg.comboCategoria, self.dlg.comboOpcao, self.dlg.arvore):
            self.assertEqual(controle.chamadas_set_focus, 0)

    def test_foco_devolvido_so_quando_saiu_do_lugar(self):
        self.abrir("construtores")
        self.assertEqual(self.dlg.comboOpcao.chamadas_set_focus, 0, "o foco não saiu: não há o que devolver")

    def test_controle_destruido_nao_derruba_a_atualizacao(self):
        self.dlg.comboOpcao.com_foco = True
        self.dlg.comboOpcao.set_focus_falha = True
        self.dlg.arvore.rouba_foco_em = {"Freeze"}
        self.dlg.comboOpcao.selecao = 1
        self.dlg._confirmar_opcao()  # SetFocus levanta RuntimeError: é ignorado
        self.processar_fila()
        self.assertEqual(self.dlg.modo, "construtores")
        self.assertTrue(FALAS[-1].startswith("Carregou Campeonato de construtores"))


# ---------------------------------------------------------------- a árvore de resultados


class TestArvoreDeResultados(unittest.TestCase):
    def montar(self, modo, dados, etapa=None):
        dlg = types.SimpleNamespace(modo=modo, dados=dados, arvore=ArvoreFalsa(), _etapa_fim_de_semana=etapa,
                                    _secoes_com_resultado=0, plugin_ref=types.SimpleNamespace(config_lembretes={}))
        dlg._adicionar_piloto = f1.F1Dialog._adicionar_piloto.__get__(dlg)
        dlg._adicionar_qualificacao = f1.F1Dialog._adicionar_qualificacao.__get__(dlg)
        dlg._popular_fim_de_semana = f1.F1Dialog._popular_fim_de_semana.__get__(dlg)
        f1.F1Dialog._popular_arvore(dlg)
        return _estrutura(dlg.arvore)

    def test_corrida_principal_mostra_vencedor_tempo_e_pontos(self):
        arvore = self.montar("resultados", [_corrida("2", "GP B", False, [VENCEDOR, SEGUNDO])])
        self.assertEqual(arvore, [("Etapa 2 - GP B (vencedor: Max Verstappen)", [LINHA_VENCEDOR, LINHA_SEGUNDO])])

    def test_corrida_sprint_mostra_tempo_e_pontos_como_a_principal(self):
        arvore = self.montar("resultados_sprint", [_corrida("2", "GP B", True, [VENCEDOR, SEGUNDO])])
        self.assertEqual(arvore, [("Etapa 2 - GP B (vencedor: Max Verstappen)", [LINHA_VENCEDOR, LINHA_SEGUNDO])])

    def test_quem_nao_terminou_mostra_o_status_no_lugar_do_tempo(self):
        arvore = self.montar("resultados_sprint", [_corrida("2", "GP B", True, [VENCEDOR, ABANDONO])])
        self.assertEqual(arvore[0][1][1], LINHA_ABANDONO)

    def test_dados_incompletos_nao_derrubam_a_arvore(self):
        arvore = self.montar("resultados", [_corrida("1", "GP A", False, [{"Driver": {"familyName": "Sem Nome"}}])])
        self.assertEqual(arvore[0][0], "Etapa 1 - GP A (vencedor: Sem Nome)")
        piloto = arvore[0][1][0]
        self.assertEqual(piloto[0], "?º  Sem Nome ()")
        self.assertEqual(piloto[1], [("Tempo/Status: ", []), ("Pontos ganhos: 0", [])])

    def test_uma_seta_sobre_a_etapa_ja_mostra_os_pilotos(self):
        """Etapa -> pilotos -> tempo e pontos: o primeiro nível expandido já é o dos pilotos, sem nó no meio."""
        for modo, sprint in (("resultados", False), ("resultados_sprint", True)):
            arvore = self.montar(modo, [_corrida("2", "GP B", sprint, [VENCEDOR, SEGUNDO])])
            etapa = arvore[0]
            self.assertEqual([filho[0] for filho in etapa[1]], ["1º Max Verstappen (Red Bull)", "2º Lando Norris (McLaren)"], modo)
            for _piloto, detalhes in etapa[1]:
                self.assertEqual([d[0].split(":")[0] for d in detalhes], ["Tempo/Status", "Pontos ganhos"])

    def test_cache_antigo_com_as_duas_corridas_misturadas_e_separado_por_modo(self):
        misturado = [_corrida("2", "GP B", False, [VENCEDOR, SEGUNDO]), _corrida("2", "GP B", True, [SEGUNDO, VENCEDOR])]
        principal = self.montar("resultados", misturado)
        sprint = self.montar("resultados_sprint", misturado)
        self.assertEqual(len(principal), 1)
        self.assertEqual(len(sprint), 1)
        self.assertEqual(principal[0][0], "Etapa 2 - GP B (vencedor: Max Verstappen)")
        self.assertEqual(sprint[0][1][0][0], "2º Lando Norris (McLaren)", "a lista da sprint vem só dos dados da sprint")

    def test_etapas_em_ordem_numerica(self):
        dados = [_corrida("10", "GP J", False, [VENCEDOR]), _corrida("2", "GP B", False, [VENCEDOR])]
        etapas = [no[0] for no in self.montar("resultados", dados)]
        self.assertEqual(etapas, ["Etapa 2 - GP B (vencedor: Max Verstappen)", "Etapa 10 - GP J (vencedor: Max Verstappen)"])

    def test_etapa_sem_resultado_nao_aparece(self):
        vazia = {"round": "3", "raceName": "GP C", "_is_sprint": False, "Results": []}
        self.assertEqual(self.montar("resultados", [vazia]), [])

    def test_qualificacoes_sprint_mostram_a_pole_e_os_tempos_de_cada_fase(self):
        arvore = self.montar("qualifying_sprint", [_qualificacao(4, "Miami Grand Prix", SQ_MIAMI_ALPHA),
                                                  _qualificacao(2, "Chinese Grand Prix", SQ_CHINA_ALPHA)])
        self.assertEqual(arvore, [
            ("Etapa 2 - Chinese Grand Prix (pole: George Russell)", [(linha, []) for linha in LINHAS_SQ_CHINA]),
            ("Etapa 4 - Miami Grand Prix (pole: Lando Norris)",
             [("1º Lando Norris (McLaren) - SQ1: 1:28.100 | SQ2: 1:27.900 | SQ3: 1:27.869", [])]),
        ])

    def test_quem_nao_marcou_tempo_e_quem_nao_foi_classificado(self):
        linhas = [_linha_alpha(1, "A", "Primeiro", "Eq", "1:30.000"),
                  _linha_alpha(2, "B", "Sem Tempo", "Eq", status="DNS", texto="R"),
                  _linha_alpha(3, "C", "Desclassificado", "Eq", "1:31.000", status="DISQUALIFIED", texto="DQ")]
        etapa = self.montar("qualifying_sprint", [_qualificacao(2, "GP B", linhas)])[0][1]
        self.assertEqual([l[0] for l in etapa], ["1º A Primeiro (Eq) - SQ1: 1:30.000", "R B Sem Tempo (Eq) - Sem tempo",
                                                 "DQ C Desclassificado (Eq) - SQ1: 1:31.000"])

    def test_uma_seta_sobre_a_etapa_ja_mostra_os_pilotos_da_qualificacao_sprint(self):
        etapa = self.montar("qualifying_sprint", [_qualificacao(2, "GP B", SQ_CHINA_ALPHA)])[0]
        self.assertEqual(len(etapa[1]), 3)
        self.assertTrue(all(filho[1] == [] for filho in etapa[1]), "os tempos já estão na linha do piloto")

    def test_qualificacao_sprint_sem_dados_deixa_a_arvore_vazia(self):
        self.assertEqual(self.montar("qualifying_sprint", []), [])
        self.assertEqual(self.montar("qualifying_sprint", [{"round": "2", "raceName": "GP B", "SprintQualifyingResults": []}]), [])

    def test_lista_vazia_deixa_a_arvore_vazia(self):
        self.assertEqual(self.montar("resultados_sprint", []), [])

    def test_fim_de_semana_sem_etapa_conhecida_fica_vazio(self):
        self.assertEqual(self.montar("fim_de_semana", [_corrida("2", "GP B", False, [VENCEDOR])]), [])


# ---------------------------------------------------------------- dados e download


def baixar_com_rede_falsa(caso, modo, corpo, velhos=None):
    """Roda o download de um modo com a rede falsa. `corpo` é o JSON da resposta, ou uma função url -> JSON
    (que pode levantar erro, como um 404). `velhos` é o cache vencido: dele vêm o calendário e a temporada."""
    velhos = velhos or {}
    plugin = types.SimpleNamespace(_fetchInProgress=False, salvos=[], urls=[])
    for nome in ("_baixar_json_em_thread", "_url_for_modo", "_extrair_dados", "_buscar_json", "_baixar_urls",
                 "_ano_da_temporada", "_baixar_qualificacoes_sprint", "_qualificacao_sprint_do_fim_de_semana"):
        setattr(plugin, nome, getattr(f1.GlobalPlugin, nome).__get__(plugin))
    plugin._salvar_cache = lambda m, d: plugin.salvos.append((m, d))
    plugin._carregar_cache_stale = lambda m: (velhos.get(m), 1 if m in velhos else None)
    plugin._start_loading_timer = lambda: None
    plugin._stop_loading_timer = lambda: None
    pronto = threading.Event()
    resultado = {}

    class Resposta:
        def __init__(self, url):
            self.url = url
            plugin.urls.append(url)

        def read(self):
            return json.dumps(corpo(self.url) if callable(corpo) else corpo).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def ok(dados):
        resultado["ok"] = dados
        pronto.set()

    def falha():
        resultado["falha"] = True
        pronto.set()

    with mock.patch.object(f1.urllib.request, "urlopen", lambda req, timeout=None: Resposta(req.full_url)), \
            mock.patch.object(f1.time, "sleep", lambda s: None):
        plugin._baixar_json_em_thread(modo, ok, falha)
        caso.assertTrue(pronto.wait(5), "o download não terminou")
    return resultado, plugin


class TestExtracaoEDownloadDosResultados(unittest.TestCase):
    def test_cada_modo_usa_a_sua_url(self):
        self.assertEqual(f1.MODOS["resultados"], [f1.URL_RESULTADOS])
        self.assertEqual(f1.MODOS["resultados_sprint"], [f1.URL_SPRINTS])

    def test_extracao_marca_de_que_corrida_e_cada_resultado(self):
        extrair = f1.GlobalPlugin._extrair_dados.__get__(types.SimpleNamespace())
        corpo = {"MRData": {"RaceTable": {"Races": [{"round": "1"}]}}}
        self.assertFalse(extrair(corpo, "resultados")[0]["_is_sprint"])
        self.assertTrue(extrair(corpo, "resultados_sprint")[0]["_is_sprint"])

    def test_no_fim_de_semana_a_marca_vem_da_url(self):
        extrair = f1.GlobalPlugin._extrair_dados.__get__(types.SimpleNamespace())
        corpo = {"MRData": {"RaceTable": {"Races": [{"round": "1"}]}}}
        self.assertFalse(extrair(corpo, "fim_de_semana", f1.URL_RESULTADOS)[0]["_is_sprint"])
        self.assertTrue(extrair(corpo, "fim_de_semana", f1.URL_SPRINTS)[0]["_is_sprint"])

    def baixar(self, modo, corpo, velhos=None):
        return baixar_com_rede_falsa(self, modo, corpo, velhos)

    VAZIO = {"MRData": {"total": "0", "limit": "1000", "RaceTable": {"Races": []}}}

    def test_sprint_vazia_e_um_resultado_valido_e_vai_para_o_cache(self):
        resultado, plugin = self.baixar("resultados_sprint", self.VAZIO)
        self.assertEqual(resultado, {"ok": []})
        self.assertEqual(plugin.salvos, [("resultados_sprint", [])])

    def test_corrida_principal_vazia_continua_sendo_erro(self):
        resultado, plugin = self.baixar("resultados", self.VAZIO)
        self.assertEqual(resultado, {"falha": True})
        self.assertEqual(plugin.salvos, [])

    def test_sprint_com_dados_vem_marcada(self):
        corpo = {"MRData": {"total": "1", "limit": "1000", "RaceTable": {"Races": [{"round": "2"}]}}}
        resultado, _plugin = self.baixar("resultados_sprint", corpo)
        self.assertEqual(resultado["ok"], [{"round": "2", "_is_sprint": True}])

    def test_fim_de_semana_junta_a_principal_e_a_sprint_cada_uma_com_a_sua_marca(self):
        def corpo(url):
            return {"MRData": {"total": "1", "limit": "1000", "RaceTable": {"Races": [{"round": "2", "de": "sprint" if "sprint" in url else "principal"}]}}}

        resultado, plugin = self.baixar("fim_de_semana", corpo)
        self.assertEqual(resultado["ok"], [{"round": "2", "de": "principal", "_is_sprint": False},
                                           {"round": "2", "de": "sprint", "_is_sprint": True}])
        self.assertEqual(plugin.salvos[0][0], "fim_de_semana")

    def test_fim_de_semana_sem_nenhum_resultado_ainda_nao_e_erro(self):
        resultado, _plugin = self.baixar("fim_de_semana", self.VAZIO)
        self.assertEqual(resultado, {"ok": []})


# ---------------------------------------------------------------- qualificação sprint: funções puras e rede


class TestQualificacaoSprintPura(unittest.TestCase):
    AGORA = f1.datetime.datetime(2026, 10, 16, 12, 0, tzinfo=f1.datetime.timezone.utc)

    def test_normaliza_para_a_forma_das_corridas(self):
        etapa = f1.normalizar_qualificacao_sprint({"number": 2, "name": "Chinese Grand Prix"}, SQ_CHINA_ALPHA)
        self.assertEqual((etapa["round"], etapa["raceName"]), ("2", "Chinese Grand Prix"))
        primeiro = etapa["SprintQualifyingResults"][0]
        self.assertEqual(primeiro, {
            "position": "1", "Driver": {"givenName": "George", "familyName": "Russell"}, "Constructor": {"name": "Mercedes"},
            "status": "FINISHED", "SQ1": "1:33.030", "SQ2": "1:32.241", "SQ3": "1:31.520"})

    def test_quem_caiu_no_sq1_so_tem_o_sq1(self):
        gasly = f1.normalizar_qualificacao_sprint({"number": 2, "name": "x"}, SQ_CHINA_ALPHA)["SprintQualifyingResults"][2]
        self.assertEqual((gasly["position"], gasly["SQ1"]), ("11", "1:34.100"))
        self.assertNotIn("SQ2", gasly)
        self.assertNotIn("SQ3", gasly)

    def test_posicao_de_quem_nao_foi_classificado_vem_do_texto(self):
        linha = f1.normalizar_qualificacao_sprint({"number": 1}, [_linha_alpha(20, "A", "B", "C", texto="DQ")])["SprintQualifyingResults"][0]
        self.assertEqual(linha["position"], "DQ")

    def test_dados_ausentes_nao_derrubam(self):
        etapa = f1.normalizar_qualificacao_sprint({}, [{}])
        self.assertEqual(etapa["SprintQualifyingResults"][0]["Driver"], {"givenName": "", "familyName": ""})
        self.assertEqual(f1.normalizar_qualificacao_sprint({"number": 3}, None)["SprintQualifyingResults"], [])

    def numeros(self, **kwargs):
        return [r["number"] for r in f1.rodadas_com_qualificacao_sprint(RODADAS_ALPHA["data"], self.AGORA, **kwargs)]

    def test_so_as_etapas_com_qualificacao_sprint_ja_disputada(self):
        self.assertEqual(self.numeros(), [2, 4], "sem SQ1 (Austrália), cancelada (8) e futura (30) ficam de fora")

    def test_filtra_pelos_numeros(self):
        self.assertEqual(self.numeros(numeros={4}), [4])
        self.assertEqual(self.numeros(numeros=set()), [])

    def test_sessao_sem_data_valida_conta_como_ja_disputada(self):
        rodada = _rodada(9, "x", "r", "isto-nao-e-data")
        self.assertEqual(f1.rodadas_com_qualificacao_sprint([rodada], self.AGORA), [rodada])


class TestDownloadDaQualificacaoSprint(unittest.TestCase):
    # uma temporada que não é a do relógio: assim o teste distingue de onde vem o ano
    CALENDARIO_OUTRA_TEMPORADA = [{"season": "2025", "round": "1"}]

    def baixar(self, modo="qualifying_sprint", corpo=None, velhos=None):
        return baixar_com_rede_falsa(self, modo, corpo or rede_alpha, velhos)

    def test_baixa_as_etapas_ja_disputadas_na_forma_das_corridas(self):
        resultado, plugin = self.baixar()
        self.assertEqual([c["round"] for c in resultado["ok"]], ["2", "4"])
        self.assertEqual(resultado["ok"][0]["raceName"], "Chinese Grand Prix")
        self.assertEqual(resultado["ok"][0]["SprintQualifyingResults"][0]["SQ3"], "1:31.520")
        self.assertEqual(plugin.salvos[0][0], "qualifying_sprint")

    def test_nao_pede_as_etapas_sem_sprint_nem_as_futuras_nem_as_canceladas(self):
        _resultado, plugin = self.baixar()
        pedidas = [u for u in plugin.urls if "/alpha/results/" in u]
        self.assertEqual(len(pedidas), 2)
        self.assertTrue(all("round_chn" in u or "round_mia" in u for u in pedidas))

    def test_o_ano_vem_da_temporada_do_calendario_ou_do_relogio(self):
        _r, plugin = self.baixar(velhos={"calendario": self.CALENDARIO_OUTRA_TEMPORADA})
        self.assertIn("year=2025", plugin.urls[0])
        _r, plugin = self.baixar()
        self.assertIn(f"year={f1.datetime.datetime.now(f1.datetime.timezone.utc).year}", plugin.urls[0])

    def test_uma_etapa_que_falha_e_pulada_e_as_outras_ficam(self):
        resultado, _plugin = self.baixar(corpo=lambda url: rede_alpha(url, falham={"round_mia"}))
        self.assertEqual([c["round"] for c in resultado["ok"]], ["2"])

    def test_se_todas_falham_e_erro(self):
        resultado, plugin = self.baixar(corpo=lambda url: rede_alpha(url, falham={"round_chn", "round_mia"}))
        self.assertEqual(resultado, {"falha": True})
        self.assertEqual(plugin.salvos, [])

    def test_sem_conseguir_listar_as_etapas_e_erro(self):
        def sem_lista(url):
            raise urllib.error.HTTPError(url, 500, "erro", {}, None)

        self.assertEqual(self.baixar(corpo=sem_lista)[0], {"falha": True})

    def test_nenhuma_qualificacao_sprint_ainda_nao_e_erro(self):
        sem_sprint = {"data": [_rodada(1, "Australian Grand Prix", "round_aus")]}
        resultado, plugin = self.baixar(corpo=lambda url: rede_alpha(url, rodadas=sem_sprint))
        self.assertEqual(resultado, {"ok": []})
        self.assertEqual(plugin.salvos, [("qualifying_sprint", [])])

    def test_etapa_ja_disputada_mas_ainda_sem_resultado_e_pulada_sem_erro(self):
        def sem_resultado_ainda(url):
            return {"data": {"results": []}} if "round_mia" in url else rede_alpha(url)

        resultado, _plugin = self.baixar(corpo=sem_resultado_ainda)
        self.assertEqual([c["round"] for c in resultado["ok"]], ["2"])


class TestQualificacaoSprintDoFimDeSemana(unittest.TestCase):
    """No modo fim_de_semana, a qualificação sprint entra junto das duas URLs Ergast, só em etapa com sprint."""

    def etapa_de_hoje(self, com_sprint):
        hoje = f1.datetime.datetime.now(f1.datetime.timezone.utc).date()
        etapa = {"season": "2026", "round": "2", "raceName": "GP B", "date": (hoje + f1.datetime.timedelta(days=2)).isoformat(),
                 "FirstPractice": {"date": hoje.isoformat()}}
        if com_sprint:
            etapa["Sprint"] = {"date": (hoje + f1.datetime.timedelta(days=1)).isoformat()}
        return {"calendario": [etapa]}

    def rede(self, falham=()):
        ergast = {"MRData": {"total": "1", "limit": "1000", "RaceTable": {"Races": [{"round": "2", "raceName": "GP B"}]}}}
        return lambda url: ergast if "/ergast/" in url else rede_alpha(url, falham=falham)

    def baixar(self, com_sprint=True, falham=()):
        return baixar_com_rede_falsa(self, "fim_de_semana", self.rede(falham), self.etapa_de_hoje(com_sprint))

    def test_etapa_com_sprint_junta_a_qualificacao_depois_das_corridas(self):
        resultado, plugin = self.baixar()
        self.assertEqual(len(resultado["ok"]), 3, "principal e sprint do Ergast e a qualificação")
        self.assertIn("SprintQualifyingResults", resultado["ok"][-1])
        self.assertEqual(resultado["ok"][-1]["round"], "2")
        self.assertEqual(plugin.salvos[0][0], "fim_de_semana")

    def test_so_pede_a_etapa_do_fim_de_semana(self):
        _resultado, plugin = self.baixar()
        self.assertEqual(len([u for u in plugin.urls if "/alpha/results/" in u]), 1)
        self.assertTrue(any("round_chn" in u for u in plugin.urls))

    def test_etapa_sem_sprint_nem_chama_a_api_alpha(self):
        resultado, plugin = self.baixar(com_sprint=False)
        self.assertEqual(len(resultado["ok"]), 2)
        self.assertFalse(any("/alpha/" in u for u in plugin.urls))

    def test_se_a_api_alpha_falhar_o_resto_do_resultado_nao_se_perde(self):
        resultado, _plugin = self.baixar(falham={"round_chn"})
        self.assertEqual(len(resultado["ok"]), 2)
        self.assertFalse(any("SprintQualifyingResults" in r for r in resultado["ok"]))

    def test_sem_calendario_em_cache_nao_busca_a_qualificacao(self):
        resultado, plugin = baixar_com_rede_falsa(self, "fim_de_semana", self.rede(), {})
        self.assertFalse(any("/alpha/" in u for u in plugin.urls))
        self.assertEqual(len(resultado["ok"]), 2)


# ---------------------------------------------------------------- o menu Ferramentas do NVDA


class ItemDeMenuFalso:
    def __init__(self, texto, ajuda="", submenu=None):
        self.texto, self.ajuda, self.submenu = texto, ajuda, submenu
        self.destruido = False

    def Destroy(self):
        self.destruido = True


class MenuFalso:
    def __init__(self):
        self.itens = []
        self.removidos = []
        self.falha_ao_remover = False
        self.falha_ao_anexar = False

    def Append(self, id_, texto, ajuda=""):
        item = ItemDeMenuFalso(texto, ajuda)
        self.itens.append(item)
        return item

    def AppendSubMenu(self, submenu, texto, ajuda=""):
        if self.falha_ao_anexar:
            raise RuntimeError("falha do wx")
        item = ItemDeMenuFalso(texto, ajuda, submenu)
        self.itens.append(item)
        return item

    def Remove(self, item):
        if self.falha_ao_remover:
            raise RuntimeError("falha do wx")
        self.itens.remove(item)
        self.removidos.append(item)


class BandejaFalsa:
    def __init__(self):
        self.toolsMenu = MenuFalso()
        self.ligacoes = []  # (função, item) de cada Bind ainda valido
        self.falha_ao_soltar = False

    def Bind(self, evento, handler, item):
        self.ligacoes.append((handler, item))

    def Unbind(self, evento, handler=None, source=None):
        if self.falha_ao_soltar:
            raise RuntimeError("falha do wx")
        self.ligacoes = [l for l in self.ligacoes if not (l[0] == handler and l[1] is source)]


class TestMenuFerramentas(unittest.TestCase):
    """Os dois itens soltos do menu Ferramentas viram um submenu "Fórmula 1" com o painel e as configurações."""

    def setUp(self):
        self.bandeja = BandejaFalsa()
        self.chamadas = []
        for alvo, nome, valor in ((f1.gui, "mainFrame", types.SimpleNamespace(sysTrayIcon=self.bandeja)),
                                  (f1.wx, "Menu", MenuFalso), (f1.wx, "ID_ANY", -1), (f1.wx, "EVT_MENU", "EVT_MENU")):
            patch = mock.patch.object(alvo, nome, valor, create=True)
            patch.start()
            self.addCleanup(patch.stop)
        self.plugin = types.SimpleNamespace(_toolsMenu=None, _toolsMenuItemOpen=None, _toolsMenuConfig=None,
                                            _toolsMenuSub=None, _f1Submenu=None)
        for nome in ("_add_tools_menu_items", "_remove_tools_menu_items", "_on_tools_menu_open"):
            setattr(self.plugin, nome, getattr(f1.GlobalPlugin, nome).__get__(self.plugin))
        self.plugin.script_f1_tabela = lambda gesto: self.chamadas.append("painel")
        self.plugin._on_tools_menu_config = lambda evento: self.chamadas.append("configuracoes")

    def submenu(self):
        return self.bandeja.toolsMenu.itens[0].submenu

    def test_um_so_item_no_menu_ferramentas_e_ele_e_um_submenu(self):
        self.plugin._add_tools_menu_items()
        itens = self.bandeja.toolsMenu.itens
        self.assertEqual([i.texto for i in itens], ["Fórmula 1"])
        self.assertIsNotNone(itens[0].submenu)
        self.assertEqual(itens[0].ajuda, "Painel e configurações da Fórmula 1")

    def test_o_submenu_tem_o_painel_e_as_configuracoes_nessa_ordem(self):
        self.plugin._add_tools_menu_items()
        self.assertEqual([i.texto for i in self.submenu().itens], ["Abrir painel", "Configurações"])
        self.assertEqual([i.ajuda for i in self.submenu().itens],
                         ["Abre o painel da Fórmula 1", "Abre as configurações do complemento"])

    def test_os_itens_soltos_antigos_nao_existem_mais(self):
        self.plugin._add_tools_menu_items()
        textos = [i.texto for i in self.bandeja.toolsMenu.itens]
        self.assertNotIn("Configurações - Fórmula 1", textos)
        self.assertEqual(len(textos), 1)
        self.assertNotIn("Configurações - Fórmula 1", inspect.getsource(f1), "nem na mensagem que manda ir às configurações")

    def test_escolher_cada_item_faz_a_coisa_certa(self):
        self.plugin._add_tools_menu_items()
        for item in self.submenu().itens:
            (funcao,) = [f for f, i in self.bandeja.ligacoes if i is item]
            funcao(None)
        self.assertEqual(self.chamadas, ["painel", "configuracoes"])

    def test_remover_tira_o_submenu_e_solta_as_ligacoes(self):
        self.plugin._add_tools_menu_items()
        submenu_item = self.bandeja.toolsMenu.itens[0]
        self.plugin._remove_tools_menu_items()
        self.assertEqual(self.bandeja.toolsMenu.itens, [])
        self.assertEqual(self.bandeja.toolsMenu.removidos, [submenu_item])
        self.assertTrue(submenu_item.destruido)
        self.assertEqual(self.bandeja.ligacoes, [])
        self.assertEqual((self.plugin._toolsMenu, self.plugin._toolsMenuSub, self.plugin._f1Submenu,
                          self.plugin._toolsMenuItemOpen, self.plugin._toolsMenuConfig), (None,) * 5)

    def test_remover_duas_vezes_ou_sem_ter_adicionado_nao_quebra(self):
        self.plugin._remove_tools_menu_items()
        self.plugin._add_tools_menu_items()
        self.plugin._remove_tools_menu_items()
        self.plugin._remove_tools_menu_items()
        self.assertEqual(self.bandeja.toolsMenu.itens, [])

    def test_pode_adicionar_de_novo_depois_de_remover(self):
        self.plugin._add_tools_menu_items()
        self.plugin._remove_tools_menu_items()
        self.plugin._add_tools_menu_items()
        self.assertEqual([i.texto for i in self.bandeja.toolsMenu.itens], ["Fórmula 1"])
        self.assertEqual(len(self.bandeja.ligacoes), 2)

    def test_sem_a_bandeja_ou_o_menu_do_nvda_nao_adiciona_nada(self):
        for principal in (None, types.SimpleNamespace(), types.SimpleNamespace(sysTrayIcon=None),
                          types.SimpleNamespace(sysTrayIcon=types.SimpleNamespace(toolsMenu=None))):
            with mock.patch.object(f1.gui, "mainFrame", principal):
                self.plugin._add_tools_menu_items()  # não pode levantar
        self.assertEqual(self.bandeja.toolsMenu.itens, [])
        self.assertEqual(self.bandeja.ligacoes, [])

    def test_erro_do_wx_ao_adicionar_nao_derruba_o_nvda(self):
        self.bandeja.toolsMenu.falha_ao_anexar = True
        self.plugin._add_tools_menu_items()  # não pode levantar
        self.assertEqual(self.bandeja.toolsMenu.itens, [])

    def test_erros_do_wx_ao_remover_nao_derrubam_e_a_limpeza_termina(self):
        self.plugin._add_tools_menu_items()
        self.bandeja.falha_ao_soltar = True
        self.bandeja.toolsMenu.falha_ao_remover = True
        self.plugin._remove_tools_menu_items()  # não pode levantar
        self.assertIsNone(self.plugin._toolsMenu)
        self.assertIsNone(self.plugin._toolsMenuSub)


# ---------------------------------------------------------------- configurações: a pergunta das ultrapassagens


class ListaDeMarcacaoFalsa:
    """wx.CheckListBox mínimo."""

    def __init__(self, marcados=()):
        self.marcados = set(marcados)

    def IsChecked(self, indice):
        return indice in self.marcados

    def alternar(self, indice):
        """O que o wx faz ao apertar a barra de espaço: troca o estado e só então avisa."""
        self.marcados ^= {indice}


class EventoDaLista:
    def __init__(self, indice):
        self.indice = indice
        self.pulou = False

    def GetInt(self):
        return self.indice

    def Skip(self):
        self.pulou = True


class TestPerguntaDasUltrapassagens(unittest.TestCase):
    """Na aba Ao Vivo das configurações, "Quais ultrapassagens anunciar" só aparece com as ultrapassagens ligadas."""

    def setUp(self):
        self.pagina = PainelFalso()
        self.lista = ListaDeMarcacaoFalsa()
        self.dlg = dlg = types.SimpleNamespace(
            lista_avisos=self.lista, page_aovivo=self.pagina, lbl_alcance=Focavel(), combo_alcance=ComboFalso(),
            _alcance_visivel=True,  # nasce visível, como na janela de verdade
            _indice_ultrapassagens=[tipo for tipo, nome in f1.TIPOS_DE_AVISO].index("ultrapassagens"))
        dlg.combo_alcance.Set([nome for valor, nome in f1.ALCANCES_ULTRAPASSAGEM])
        dlg.combo_alcance.SetSelection(2)
        for nome in ("_ao_marcar_item_lista", "_ao_alternar_item_lista", "_mostrar_alcance"):
            setattr(dlg, nome, getattr(f1.ConfiguracoesGeraisDialog, nome).__get__(dlg))

    def pergunta_aparece(self):
        self.assertEqual(self.dlg.lbl_alcance.IsShown(), self.dlg.combo_alcance.IsShown(), "rótulo e caixa juntos")
        return self.dlg.combo_alcance.IsShown()

    def marcar(self, indice):
        """A pessoa aperta a barra de espaço no item."""
        self.lista.alternar(indice)
        evento = EventoDaLista(indice)
        self.dlg._ao_marcar_item_lista(evento)
        return evento

    def test_a_ultrapassagens_e_o_primeiro_item_da_lista(self):
        self.assertEqual(self.dlg._indice_ultrapassagens, 0)

    def test_com_as_ultrapassagens_desligadas_ao_abrir_a_pergunta_some(self):
        self.dlg._mostrar_alcance(self.lista.IsChecked(self.dlg._indice_ultrapassagens))  # o que o construtor faz
        self.assertFalse(self.pergunta_aparece())

    def test_com_as_ultrapassagens_ligadas_ao_abrir_a_pergunta_fica(self):
        self.lista.marcados = {0}
        self.dlg._mostrar_alcance(self.lista.IsChecked(self.dlg._indice_ultrapassagens))
        self.assertTrue(self.pergunta_aparece())
        self.assertEqual(self.pagina.layouts, 0, "nada mudou na tela")

    def test_marcar_as_ultrapassagens_mostra_a_pergunta_e_desmarcar_esconde(self):
        self.dlg._mostrar_alcance(False)  # abriu com elas desligadas
        self.marcar(0)
        self.assertTrue(self.pergunta_aparece())
        self.marcar(0)
        self.assertFalse(self.pergunta_aparece())

    def test_a_mudanca_e_feita_de_uma_vez_so_e_congelada(self):
        self.dlg._mostrar_alcance(False)
        self.pagina.layouts = self.pagina.freezes = self.pagina.thaws = 0
        self.marcar(0)
        self.assertEqual((self.pagina.layouts, self.pagina.freezes, self.pagina.thaws), (1, 1, 1))

    def test_repetir_o_mesmo_estado_nao_mexe_na_tela(self):
        self.dlg._mostrar_alcance(True)
        self.dlg._mostrar_alcance(True)
        self.assertEqual((self.pagina.layouts, self.pagina.freezes), (0, 0))

    def test_marcar_qualquer_outro_item_nao_mexe_na_pergunta(self):
        self.dlg._mostrar_alcance(False)
        self.pagina.layouts = 0
        for indice in range(1, len(f1.TIPOS_DE_AVISO)):
            self.marcar(indice)
        self.assertFalse(self.pergunta_aparece())
        self.assertEqual(self.pagina.layouts, 0)

    def test_com_as_ultrapassagens_ligadas_marcar_e_desmarcar_outros_itens_nao_esconde_a_pergunta(self):
        self.lista.marcados = {0}
        self.pagina.layouts = 0
        for indice in range(1, len(f1.TIPOS_DE_AVISO)):
            self.marcar(indice)  # liga
            self.marcar(indice)  # desliga
        self.assertTrue(self.pergunta_aparece())
        self.assertEqual(self.pagina.layouts, 0)

    def test_andar_pela_lista_nao_mexe_na_pergunta(self):
        """As setas disparam EVT_LISTBOX, que só fala o estado do item."""
        self.dlg._mostrar_alcance(False)
        self.pagina.layouts = 0
        evento = EventoDaLista(0)
        self.dlg._ao_alternar_item_lista(evento)
        self.assertTrue(evento.pulou)
        self.assertFalse(self.pergunta_aparece())
        self.assertEqual(self.pagina.layouts, 0)

    def test_o_valor_escolhido_nao_se_perde_ao_esconder_e_mostrar(self):
        self.marcar(0)  # desliga
        self.marcar(0)  # liga de novo
        self.assertEqual(self.dlg.combo_alcance.GetSelection(), 2)
        self.dlg._mostrar_alcance(False)
        self.assertEqual(self.dlg.combo_alcance.GetSelection(), 2, "escondida, a caixa guarda o valor que será salvo")

    def test_o_evento_da_lista_ainda_e_repassado(self):
        self.assertTrue(self.marcar(3).pulou)

    def test_ligacoes_da_janela_de_configuracoes(self):
        fonte = inspect.getsource(f1.ConfiguracoesGeraisDialog.__init__)
        self.assertIn("self.lista_avisos.Bind(wx.EVT_CHECKLISTBOX, self._ao_marcar_item_lista)", fonte, "marcar mexe na pergunta")
        self.assertIn("self.lista_avisos.Bind(wx.EVT_LISTBOX, self._ao_alternar_item_lista)", fonte, "andar pela lista não mexe")
        self.assertIn('.index("ultrapassagens")', fonte, "o item é achado pelo nome, não por um número fixo")
        self.assertIn("self.lbl_alcance = wx.StaticText(", fonte)
        self.assertLess(fonte.index("self.SetSizerAndFit(dlgSizer)"), fonte.index("self._mostrar_alcance("),
                        "a pergunta só se esconde depois da janela ser dimensionada com ela")


# ---------------------------------------------------------------- o `_` das traduções


class TestTraducoesNaoSaoSobrescritas(unittest.TestCase):
    """`_` é a função de tradução. Atribuir a ela (por exemplo `dados, _ = f()`) a torna uma variável local
    da função inteira e quebra todo `_("...")` dela: os avisos falados deixam de sair."""

    def test_nenhum_arquivo_do_complemento_atribui_a_underscore(self):
        for nome in ("f1Acessivel.py", "f1AoVivo.py", "f1Updater.py"):
            caminho = os.path.join(PASTA, nome)
            with open(caminho, encoding="utf-8") as arquivo:
                arvore = ast.parse(arquivo.read())
            for no in ast.walk(arvore):
                if isinstance(no, ast.Name) and no.id == "_" and isinstance(no.ctx, ast.Store):
                    self.fail(f"{nome}:{no.lineno} atribui a `_`; use outro nome (por exemplo `_idade`)")


if __name__ == "__main__":
    unittest.main()
