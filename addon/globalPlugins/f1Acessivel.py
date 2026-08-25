import globalPluginHandler
import ui
import urllib.request
import json
import tones
import wx
import gui
import time
import os
import threading
from logHandler import log
import addonHandler
import datetime

addonHandler.initTranslation()
from gettext import gettext as _

CACHE_TTL_SECONDS = 3600
HTTP_TIMEOUT_SECONDS = 15
LOADING_BEEP_INTERVAL_MS = 1800

URL_PILOTOS = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"
URL_CONSTRUTORES = "https://api.jolpi.ca/ergast/f1/current/constructorStandings.json"
URL_CALENDARIO = "https://api.jolpi.ca/ergast/f1/current.json"
URL_ULTIMA_CORRIDA = "https://api.jolpi.ca/ergast/f1/current/last/results.json"
URL_RESULTADOS = "https://api.jolpi.ca/ergast/f1/current/results.json"
URL_SPRINTS = "https://api.jolpi.ca/ergast/f1/current/sprint.json"

MODOS = {
    "pilotos": [URL_PILOTOS],
    "construtores": [URL_CONSTRUTORES],
    "calendario": [URL_CALENDARIO],
    "proxima": [URL_CALENDARIO],
    "ultima_corrida": [URL_ULTIMA_CORRIDA],
    "resultados": [URL_RESULTADOS, URL_SPRINTS]
}

def _safe_makedirs(path: str) -> str:
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        fallback = os.path.join(os.path.expanduser("~"), "cache_tabela_f1")
        os.makedirs(fallback, exist_ok=True)
        return fallback

def _read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _write_json_atomic(path: str, data) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)

try:
    import config
    BASE_DIR = os.path.join(config.getUserConfigPath(), "cache_tabela_f1")
except Exception:
    BASE_DIR = os.path.join(os.environ.get("APPDATA", ""), "nvda", "cache_tabela_f1")

BASE_DIR = _safe_makedirs(BASE_DIR)

class ErrorDialog(wx.MessageDialog):
    def __init__(self, parent=None):
        super().__init__(
            parent or gui.mainFrame,
            _("Não foi possível carregar os dados da Fórmula 1.\nTente mais tarde."),
            _("Fórmula 1"),
            wx.OK | wx.ICON_WARNING
        )

class F1Dialog(wx.Dialog):
    def __init__(self, dados, modo="pilotos", onForceRefresh=None, onChangeModo=None):
        super(F1Dialog, self).__init__(
            gui.mainFrame,
            title=self._obter_titulo(modo),
            style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
        )
        self.dados = dados or []
        self.modo = modo
        self._onForceRefresh = onForceRefresh
        self._onChangeModo = onChangeModo

        mainSizer = wx.BoxSizer(wx.VERTICAL)

        listPanel = wx.Panel(self)
        listSizer = wx.BoxSizer(wx.VERTICAL)
        self.arvore = wx.TreeCtrl(listPanel, style=wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT | wx.TR_HIDE_ROOT | wx.BORDER_SIMPLE | wx.TR_SINGLE | wx.TR_ROW_LINES)
        listSizer.Add(self.arvore, 1, wx.EXPAND | wx.ALL, 6)
        listPanel.SetSizer(listSizer)
        mainSizer.Add(listPanel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        try:
            f = self.arvore.GetFont()
            pt = f.GetPointSize()
            if pt and pt > 0:
                f.SetPointSize(pt + 2)
                self.arvore.SetFont(f)
        except Exception:
            pass

        self._popular_arvore()

        self.arvore.Bind(wx.EVT_KEY_DOWN, self.ao_pressionar_setas)
        self.arvore.Bind(wx.EVT_CHAR, self.ao_pressionar_letras)
        self.Bind(wx.EVT_CHAR_HOOK, self.ao_pressionar_esc)

        btnSizer = wx.WrapSizer(wx.HORIZONTAL)

        self.btnAtualizar = wx.Button(self, wx.ID_ANY, _("Atualizar dados"))
        btnSizer.Add(self.btnAtualizar, 0, wx.ALL, 2)

        self.btnPilotos = wx.Button(self, wx.ID_ANY, _("Pilotos"))
        btnSizer.Add(self.btnPilotos, 0, wx.ALL, 2)

        self.btnConstrutores = wx.Button(self, wx.ID_ANY, _("Construtores"))
        btnSizer.Add(self.btnConstrutores, 0, wx.ALL, 2)

        self.btnCalendario = wx.Button(self, wx.ID_ANY, _("Calendário"))
        btnSizer.Add(self.btnCalendario, 0, wx.ALL, 2)

        self.btnProxima = wx.Button(self, wx.ID_ANY, _("Sessões (Fim de Semana)"))
        btnSizer.Add(self.btnProxima, 0, wx.ALL, 2)

        self.btnResultados = wx.Button(self, wx.ID_ANY, _("Resultados do Ano"))
        btnSizer.Add(self.btnResultados, 0, wx.ALL, 2)

        self.btnUltimaCorrida = wx.Button(self, wx.ID_ANY, _("Resultado da Última Corrida"))
        btnSizer.Add(self.btnUltimaCorrida, 0, wx.ALL, 2)
        
        self.btnCopiar = wx.Button(self, wx.ID_ANY, _("Copiar tabela"))
        btnSizer.Add(self.btnCopiar, 0, wx.ALL, 2)

        self.btnSalvar = wx.Button(self, wx.ID_ANY, _("Salvar em TXT"))
        btnSizer.Add(self.btnSalvar, 0, wx.ALL, 2)

        self.btnFechar = wx.Button(self, wx.ID_CANCEL, _("Fechar"))
        btnSizer.Add(self.btnFechar, 0, wx.ALL, 2)

        mainSizer.Add(btnSizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.btnAtualizar.Bind(wx.EVT_BUTTON, self._on_click_atualizar)
        self.btnPilotos.Bind(wx.EVT_BUTTON, lambda e: self._on_click_modo("pilotos"))
        self.btnConstrutores.Bind(wx.EVT_BUTTON, lambda e: self._on_click_modo("construtores"))
        self.btnCalendario.Bind(wx.EVT_BUTTON, lambda e: self._on_click_modo("calendario"))
        self.btnProxima.Bind(wx.EVT_BUTTON, lambda e: self._on_click_modo("proxima"))
        self.btnUltimaCorrida.Bind(wx.EVT_BUTTON, lambda e: self._on_click_modo("ultima_corrida"))
        self.btnResultados.Bind(wx.EVT_BUTTON, lambda e: self._on_click_modo("resultados"))
        self.btnCopiar.Bind(wx.EVT_BUTTON, lambda evt: self._copiar_tabela_para_area_de_transferencia())
        self.btnSalvar.Bind(wx.EVT_BUTTON, lambda evt: self._salvar_tabela_em_txt())
        self.btnFechar.Bind(wx.EVT_BUTTON, lambda evt: self.Close())

        if not callable(self._onForceRefresh):
            self.btnAtualizar.Disable()

        try:
            if self.modo == "pilotos": self.btnPilotos.Disable()
            if self.modo == "construtores": self.btnConstrutores.Disable()
            if self.modo == "calendario": self.btnCalendario.Disable()
            if self.modo == "proxima": self.btnProxima.Disable()
            if self.modo == "ultima_corrida": self.btnUltimaCorrida.Disable()
            if self.modo == "resultados": self.btnResultados.Disable()
        except Exception:
            pass

        self.SetSizer(mainSizer)
        self.Maximize(True)
        self.Raise()

        root = self.arvore.GetRootItem()
        root = self.arvore.GetRootItem()
        if root and root.IsOk():
            primeiro, cookie = self.arvore.GetFirstChild(root)
            if primeiro.IsOk():
                self.arvore.SetFocus()
                self.arvore.SelectItem(primeiro)
        else:
            self.arvore.SetFocus()

    def _obter_titulo(self, modo):
        titulos = {
            "pilotos": _("Fórmula 1 - Classificação de Pilotos"),
            "construtores": _("Fórmula 1 - Classificação de Construtores"),
            "calendario": _("Fórmula 1 - Calendário de Corridas"),
            "proxima": _("Fórmula 1 - Treinos e Sessões do Fim de Semana"),
            "resultados": _("Fórmula 1 - Resultados do Ano"),
            "ultima_corrida": _("Fórmula 1 - Resultado da Última Corrida")
        }
        return titulos.get(modo, "Fórmula 1")

    def _popular_arvore(self):
        try:
            self.arvore.DeleteAllItems()
        except Exception:
            pass
            
        root = self.arvore.AddRoot("Raiz")

        if self.modo == "proxima":
            hoje = datetime.date.today().isoformat()
            corridas_futuras = [r for r in self.dados if r.get("date", "") >= hoje]
            corrida = corridas_futuras[0] if corridas_futuras else (self.dados[-1] if self.dados else {})
            
            rd = corrida.get("round", "?")
            nome = corrida.get("raceName", "")
            pai = self.arvore.AppendItem(root, f"Etapa {rd} - {nome}")
            
            sessoes = [("FirstPractice", "Treino Livre 1"), ("SecondPractice", "Treino Livre 2"), ("ThirdPractice", "Treino Livre 3"), ("SprintQualifying", "Qualificação Sprint"), ("Sprint", "Corrida Sprint"), ("Qualifying", "Classificação Principal")]
            for sessao, titulo in sessoes:
                if sessao in corrida:
                    d = corrida[sessao].get("date", "")
                    t = corrida[sessao].get("time", "").replace("Z", "")
                    self.arvore.AppendItem(pai, f"{titulo}: {d} {t}")
            
            d = corrida.get("date", "")
            t = corrida.get("time", "").replace("Z", "")
            self.arvore.AppendItem(pai, f"Corrida Principal: {d} {t}")
            self.arvore.Expand(pai)
            return

        if self.modo == "resultados":
            # agrupar por corrida
            corridas = {}
            for r in self.dados:
                rd = r.get("round", "?")
                if rd not in corridas:
                    corridas[rd] = {"nome": r.get("raceName", ""), "principal": [], "sprint": []}
                
                is_sprint = r.get("_is_sprint", False)
                resultados = r.get("SprintResults") if is_sprint else r.get("Results")
                if resultados:
                    if is_sprint:
                        corridas[rd]["sprint"] = resultados
                    else:
                        corridas[rd]["principal"] = resultados
                        
            for rd in sorted(corridas.keys(), key=lambda x: int(x)):
                c = corridas[rd]
                pai = self.arvore.AppendItem(root, f"Etapa {rd} - {c['nome']}")
                
                if c["principal"]:
                    p1 = c["principal"][0]
                    vencedor = f"{p1['Driver']['givenName']} {p1['Driver']['familyName']}"
                    no_principal = self.arvore.AppendItem(pai, "Resultado Corrida Principal")
                    for p in c["principal"]:
                        pos = p.get("position", "?")
                        nome = f"{p['Driver']['givenName']} {p['Driver']['familyName']}"
                        eq = p.get("Constructor", {}).get("name", "")
                        self.arvore.AppendItem(no_principal, f"{pos}º {nome} ({eq})")
                
                if c["sprint"]:
                    s1 = c["sprint"][0]
                    no_sprint = self.arvore.AppendItem(pai, "Resultado Corrida Sprint")
                    for p in c["sprint"]:
                        pos = p.get("position", "?")
                        nome = f"{p['Driver']['givenName']} {p['Driver']['familyName']}"
                        eq = p.get("Constructor", {}).get("name", "")
                        self.arvore.AppendItem(no_sprint, f"{pos}º {nome} ({eq})")

            return

        for i, item in enumerate(self.dados):
            if self.modo == "pilotos":
                pos = item.get("position", "?")
                driver = item.get("Driver", {})
                nome = f"{driver.get('givenName', '')} {driver.get('familyName', '')}"
                pts = item.get("points", "0")
                construtores = item.get("Constructors", [])
                equipe = construtores[0].get("name", "") if construtores else ""
                
                pai = self.arvore.AppendItem(root, f"{pos}º {nome} - {pts} pontos")
                self.arvore.AppendItem(pai, f"Equipe: {equipe}")
                self.arvore.AppendItem(pai, f"Vitórias: {item.get('wins', '0')}")
                
            elif self.modo == "construtores":
                pos = item.get("position", "?")
                construtor = item.get("Constructor", {})
                nome = construtor.get("name", "")
                pts = item.get("points", "0")
                pai = self.arvore.AppendItem(root, f"{pos}º {nome} - {pts} pontos")
                self.arvore.AppendItem(pai, f"Vitórias: {item.get('wins', '0')}")
                
            elif self.modo == "calendario":
                rd = item.get("round", "?")
                nome = item.get("raceName", "")
                circuito = item.get("Circuit", {}).get("circuitName", "")
                data_str = item.get("date", "")
                
                pai = self.arvore.AppendItem(root, f"Etapa {rd} - {nome} no circuito {circuito} ({data_str})")
                
                sessoes = [("FirstPractice", "Treino Livre 1"), ("SecondPractice", "Treino Livre 2"), ("ThirdPractice", "Treino Livre 3"), ("SprintQualifying", "Qualificação Sprint"), ("Sprint", "Corrida Sprint"), ("Qualifying", "Classificação Principal")]
                for sessao, titulo in sessoes:
                    if sessao in item:
                        d = item[sessao].get("date", "")
                        t = item[sessao].get("time", "").replace("Z", "")
                        self.arvore.AppendItem(pai, f"{titulo}: {d} {t}")
                
                d = item.get("date", "")
                t = item.get("time", "").replace("Z", "")
                self.arvore.AppendItem(pai, f"Corrida Principal: {d} {t}")
                
            elif self.modo == "ultima_corrida":
                pos = item.get("position", "?")
                driver = item.get("Driver", {})
                nome = f"{driver.get('givenName', '')} {driver.get('familyName', '')}"
                equipe = item.get("Constructor", {}).get("name", "")
                
                status = item.get("status", "")
                tempo = item.get("Time", {}).get("time", status)
                pontos = item.get("points", "0")
                
                pai = self.arvore.AppendItem(root, f"{pos}º {nome} ({equipe})")
                self.arvore.AppendItem(pai, f"Tempo/Status: {tempo}")
                self.arvore.AppendItem(pai, f"Pontos ganhos: {pontos}")

    def _atualizar_dados_na_tela(self, novos_dados):
        self.dados = novos_dados or []
        self._popular_arvore()
        
        root = self.arvore.GetRootItem()
        if root.IsOk():
            primeiro = self.arvore.GetFirstChild(root)[0]
            if primeiro.IsOk():
                self.arvore.SetFocus()
                self.arvore.SelectItem(primeiro)

    def _set_atualizando(self, updating: bool):
        try:
            self.btnAtualizar.Enable(not updating)
            self.btnFechar.Enable(not updating)
            if updating:
                self.btnAtualizar.SetLabel(_("Atualizando..."))
            else:
                self.btnAtualizar.SetLabel(_("Atualizar dados"))
        except Exception:
            pass

    def _on_click_atualizar(self, event):
        if not callable(self._onForceRefresh): return
        self._set_atualizando(True)
        tones.beep(880, 60)
        ui.message(_("Atualizando dados da tabela..."))
        def ok(novos_dados):
            self._set_atualizando(False)
            self._atualizar_dados_na_tela(novos_dados)
            tones.beep(660, 40)
            ui.message(_("Tabela atualizada."))
        def fail():
            self._set_atualizando(False)
            tones.beep(220, 120)
            dlg = ErrorDialog(self)
            try:
                dlg.ShowModal()
            finally:
                dlg.Destroy()
        try:
            self._onForceRefresh(self.modo, ok, fail)
        except Exception:
            fail()

    def _on_click_modo(self, modo_novo):
        if callable(self._onChangeModo):
            try:
                self._onChangeModo(modo_novo, self)
            except Exception:
                pass

    def _ajustar_largura_coluna(self):
        pass

    def _mostrar_ajuda(self):
        dlg = wx.Dialog(self, title=_("Ajuda"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        texto = wx.TextCtrl(
            dlg,
            wx.ID_ANY,
            """Atalhos disponíveis:

- Alt Gr + F: abre o painel da Fórmula 1 (atalho global do NVDA).
- Esc: fecha a janela.
- Setas para cima/baixo: navega pela lista.
- Setas para esquerda/direita: expande e recolhe os detalhes de um item.
- F1: abre esta ajuda.
- Ctrl+C: copia a linha selecionada.
- Ctrl+A: copia todos os dados da tela.
- Ctrl+S: salva os dados em TXT.

Pressione Esc para voltar.""",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
        )
        texto.SetMinSize((520, 320))
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(texto, 1, wx.EXPAND | wx.ALL, 10)
        dlg.SetSizerAndFit(sizer)
        dlg.CentreOnParent()

        def onKey(event):
            if event.GetKeyCode() == wx.WXK_ESCAPE:
                dlg.EndModal(wx.ID_CANCEL)
                return
            event.Skip()

        dlg.Bind(wx.EVT_CHAR_HOOK, onKey)
        texto.SetFocus()
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
            try:
                self.lista.SetFocus()
            except Exception:
                pass

    def _ao_redimensionar_lista(self, event):
        
        event.Skip()

    def _gerar_texto_tabela_simples(self) -> str:
        linhas = []
        def varrer(item, nivel=0):
            if item.IsOk() and item != self.arvore.GetRootItem():
                linhas.append("  " * nivel + self.arvore.GetItemText(item))
            
            child, cookie = self.arvore.GetFirstChild(item)
            while child.IsOk():
                varrer(child, nivel + 1 if item != self.arvore.GetRootItem() else 0)
                child, cookie = self.arvore.GetNextChild(item, cookie)
                
        varrer(self.arvore.GetRootItem())
        return "\\n".join(linhas)

    def _copiar_linha_selecionada(self):
        item = self.arvore.GetSelection()
        if not item.IsOk():
            ui.message(_("Nenhum item selecionado."))
            return
        texto = self.arvore.GetItemText(item)
        try:
            if wx.TheClipboard.Open():
                try:
                    wx.TheClipboard.SetData(wx.TextDataObject(texto))
                    wx.TheClipboard.Flush()
                finally:
                    wx.TheClipboard.Close()
            ui.message(_("Copiado: {linha}").format(linha=texto))
        except Exception:
            ui.message(_("Não foi possível copiar."))

    def _copiar_tabela_para_area_de_transferencia(self):
        texto = self._gerar_texto_tabela_simples()
        try:
            if wx.TheClipboard.Open():
                try:
                    wx.TheClipboard.SetData(wx.TextDataObject(texto))
                    wx.TheClipboard.Flush()
                finally:
                    wx.TheClipboard.Close()
            ui.message(_("Tabela copiada."))
        except Exception:
            ui.message(_("Não foi possível copiar a tabela."))

    def _salvar_tabela_em_txt(self):
        texto = self._gerar_texto_tabela_simples()
        nomePadrao = f"Tabela_F1_{self.modo}.txt"
        try:
            dlg = wx.FileDialog(
                self,
                message=_("Salvar tabela em TXT"),
                defaultDir=os.path.expanduser("~"),
                defaultFile=nomePadrao,
                wildcard=_("Arquivo de texto (*.txt)|*.txt"),
                style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
            )
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                caminho = dlg.GetPath()
            finally:
                dlg.Destroy()
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(texto)
            ui.message(_("Tabela salva em arquivo TXT."))
        except Exception:
            ui.message(_("Não foi possível salvar o arquivo."))

    def ao_pressionar_esc(self, event):
        keyCode = event.GetKeyCode()
        if event.ControlDown() and not event.AltDown():
            if keyCode in (ord("C"), ord("c")):
                self._copiar_linha_selecionada()
                return
            if keyCode in (ord("A"), ord("a")):
                self._copiar_tabela_para_area_de_transferencia()
                return
            if keyCode in (ord("S"), ord("s")):
                self._salvar_tabela_em_txt()
                return
        if keyCode == wx.WXK_F1:
            self._mostrar_ajuda()
            return
        if keyCode == wx.WXK_ESCAPE:
            self.Close()
        else:
            event.Skip()

    def ao_pressionar_setas(self, event):
        codigo = event.GetKeyCode()
        # wx.TreeCtrl already handles arrows very well natively for screen readers.
        # We only pass Skip() so it behaves normally.
        event.Skip()

    def ao_pressionar_letras(self, event):
        event.Skip()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = _("Fórmula 1")

    def __init__(self, *args, **kwargs):
        super(GlobalPlugin, self).__init__(*args, **kwargs)
        self._fetchInProgress = False
        self._toolsMenu = None
        self._toolsMenuItemOpen = None
        self._loadingTimer = None
        self._add_tools_menu_items()

    def terminate(self):
        self._stop_loading_timer()
        self._remove_tools_menu_items()
        super(GlobalPlugin, self).terminate()

    def _add_tools_menu_items(self):
        try:
            mainFrame = getattr(gui, "mainFrame", None)
            if not mainFrame: return
            sysTray = getattr(mainFrame, "sysTrayIcon", None)
            if not sysTray: return
            toolsMenu = getattr(sysTray, "toolsMenu", None)
            if not toolsMenu: return
            self._toolsMenu = toolsMenu
            self._toolsMenuItemOpen = toolsMenu.Append(
                wx.ID_ANY,
                _("Fórmula 1"),
                _("Abrir o painel da Fórmula 1")
            )
            sysTray.Bind(wx.EVT_MENU, self._on_tools_menu_open, self._toolsMenuItemOpen)
        except Exception:
            log.exception("Falha ao adicionar itens no menu Ferramentas")

    def _remove_tools_menu_items(self):
        try:
            mainFrame = getattr(gui, "mainFrame", None)
            sysTray = getattr(mainFrame, "sysTrayIcon", None) if mainFrame else None
            for item, handler in ((self._toolsMenuItemOpen, self._on_tools_menu_open),):
                if self._toolsMenu and item:
                    try:
                        if sysTray: sysTray.Unbind(wx.EVT_MENU, handler=handler, source=item)
                    except Exception: pass
                    try: self._toolsMenu.Remove(item)
                    except Exception: pass
                    try: item.Destroy()
                    except Exception: pass
        finally:
            self._toolsMenu = None
            self._toolsMenuItemOpen = None

    def _on_tools_menu_open(self, event):
        self.script_tabela(None)

    def _start_loading_timer(self):
        def _start():
            try:
                self._stop_loading_timer()
                mainFrame = getattr(gui, "mainFrame", None)
                if not mainFrame: return
                self._loadingTimer = wx.Timer(mainFrame)
                mainFrame.Bind(wx.EVT_TIMER, self._on_loading_timer, self._loadingTimer)
                self._loadingTimer.Start(LOADING_BEEP_INTERVAL_MS)
            except Exception:
                pass
        wx.CallAfter(_start)

    def _stop_loading_timer(self):
        def _stop():
            try:
                mainFrame = getattr(gui, "mainFrame", None)
                if self._loadingTimer and mainFrame:
                    try: mainFrame.Unbind(wx.EVT_TIMER, handler=self._on_loading_timer, source=self._loadingTimer)
                    except Exception: pass
                    try: self._loadingTimer.Stop()
                    except Exception: pass
                    try: self._loadingTimer.Destroy()
                    except Exception: pass
            finally:
                self._loadingTimer = None
        wx.CallAfter(_stop)

    def _on_loading_timer(self, event):
        try:
            if self._fetchInProgress: tones.beep(660, 15)
            else: self._stop_loading_timer()
        except Exception:
            pass

    def _mostrar_erro_simples(self):
        try:
            tones.beep(220, 120)
            dlg = ErrorDialog(gui.mainFrame)
            try: dlg.ShowModal()
            finally: dlg.Destroy()
        except Exception:
            ui.message(_("Não foi possível carregar os dados. Tente mais tarde."))

    def _cache_file_for_modo(self, modo: str) -> str:
        return os.path.join(BASE_DIR, f"cache_{modo}.json")

    def _url_for_modo(self, modo: str):
        return MODOS.get(modo, [URL_PILOTOS])

    def _carregar_cache(self, modo: str):
        cache = _read_json(self._cache_file_for_modo(modo))
        if not isinstance(cache, dict): return None
        timestamp = cache.get("timestamp")
        dados = cache.get("dados")
        if not isinstance(timestamp, (int, float)) or not isinstance(dados, list): return None
        if (time.time() - float(timestamp)) >= CACHE_TTL_SECONDS: return None
        return dados

    def _carregar_cache_stale(self, modo: str):
        cache = _read_json(self._cache_file_for_modo(modo))
        if not isinstance(cache, dict): return (None, None)
        timestamp = cache.get("timestamp")
        dados = cache.get("dados")
        if not isinstance(timestamp, (int, float)) or not isinstance(dados, list): return (None, None)
        idade = max(0, time.time() - float(timestamp))
        return (dados, idade)

    def _salvar_cache(self, modo: str, dados):
        try:
            _write_json_atomic(self._cache_file_for_modo(modo), {"timestamp": time.time(), "dados": dados})
        except Exception:
            pass

    def _extrair_dados(self, obj, modo, url=""):
        try:
            if modo == "pilotos":
                return obj["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
            elif modo == "construtores":
                return obj["MRData"]["StandingsTable"]["StandingsLists"][0]["ConstructorStandings"]
            elif modo == "calendario" or modo == "proxima":
                return obj["MRData"]["RaceTable"]["Races"]
            elif modo == "ultima_corrida":
                return obj["MRData"]["RaceTable"]["Races"][0]["Results"]
            elif modo == "resultados":
                races = obj["MRData"]["RaceTable"]["Races"]
                # Mark them if they are sprint
                is_sprint = "sprint" in url
                for r in races:
                    r["_is_sprint"] = is_sprint
                return races
        except Exception as e:
            return []
        return []
        return []

    def _baixar_json_em_thread(self, modo: str, on_ok, on_fail):
        urls = self._url_for_modo(modo)
        def worker():
            try:
                todos_dados = []
                for u in urls:
                    req = urllib.request.Request(
                        u,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                            "Accept": "application/json",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                        payload = resp.read().decode("utf-8", errors="replace")
                    obj = json.loads(payload)
                    dados = self._extrair_dados(obj, modo, u)
                    if dados:
                        todos_dados.extend(dados)
                if not todos_dados:
                    raise ValueError("Dados vazios")
                self._salvar_cache(modo, todos_dados)
                wx.CallAfter(on_ok, todos_dados)
            except Exception as e:
                wx.CallAfter(on_fail)
            finally:
                self._fetchInProgress = False
                self._stop_loading_timer()
        
        self._fetchInProgress = True
        self._start_loading_timer()
        threading.Thread(target=worker, daemon=True).start()

    def _mostrar_tabela(self, dados, modo: str):
        try:
            dlg = F1Dialog(
                dados,
                modo=modo,
                onForceRefresh=lambda m, ok, fail: self._force_refresh_from_dialog(m, ok, fail),
                onChangeModo=self._open_modo_substituindo
            )
            dlg.ShowModal()
        except Exception as e:
            import traceback
            import logHandler
            logHandler.log.error(f"Erro ao mostrar F1Dialog: {e}", exc_info=True)
            ui.message("Ocorreu um erro interno ao abrir a janela. Verifique o log do NVDA.")

    def _force_refresh_from_dialog(self, modo: str, ok, fail):
        if self._fetchInProgress:
            ui.message(_("Aguarde, já estou buscando dados."))
            fail()
            return
        self._baixar_json_em_thread(modo, ok, fail)

    def _open_modo_substituindo(self, modo: str, dlgAtual=None):
        if self._fetchInProgress:
            ui.message(_("Aguarde, buscando dados."))
            return
        
        dados_cache = self._carregar_cache(modo)
        if dados_cache is not None:
            tones.beep(440, 30)
            try:
                if dlgAtual: dlgAtual.Close()
            except Exception: pass
            wx.CallAfter(lambda: self._mostrar_tabela(dados_cache, modo))
            return

        tones.beep(880, 50)
        ui.message(_("Buscando dados da Fórmula 1."))

        def ok(dados):
            try:
                if dlgAtual: dlgAtual.Close()
            except Exception: pass
            self._mostrar_tabela(dados, modo)

        def fail():
            dados_cache_stale, _ = self._carregar_cache_stale(modo)
            if dados_cache_stale is not None:
                ui.message(_("Mostrando dados do cache."))
                try:
                    if dlgAtual: dlgAtual.Close()
                except Exception: pass
                self._mostrar_tabela(dados_cache_stale, modo)
            else:
                self._mostrar_erro_simples()

        self._baixar_json_em_thread(modo, ok, fail)

    def _open_modo(self, modo: str):
        if self._fetchInProgress:
            ui.message(_("Aguarde, buscando dados."))
            return

        dados_cache = self._carregar_cache(modo)
        if dados_cache is not None:
            tones.beep(440, 30)
            wx.CallAfter(lambda: self._mostrar_tabela(dados_cache, modo))
            return

        tones.beep(880, 50)
        ui.message(_("Buscando dados da Fórmula 1."))

        def ok(dados):
            self._mostrar_tabela(dados, modo)

        def fail():
            dados_cache_stale, _ = self._carregar_cache_stale(modo)
            if dados_cache_stale is not None:
                ui.message(_("Mostrando dados do cache."))
                self._mostrar_tabela(dados_cache_stale, modo)
            else:
                self._mostrar_erro_simples()

        self._baixar_json_em_thread(modo, ok, fail)

    def script_tabela(self, gesture):
        # Translators: Descrição do atalho nas configurações do NVDA
        """Abre a janela da Fórmula 1."""
        self._open_modo("pilotos")

    __gestures = {
        "kb:control+alt+f": "tabela",
        "kb:rightAlt+f": "tabela",
    }
