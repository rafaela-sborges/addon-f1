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
import nvwave

addonHandler.initTranslation()
from gettext import gettext as _

CACHE_TTL_SECONDS = 3600
HTTP_TIMEOUT_SECONDS = 15
LOADING_BEEP_INTERVAL_MS = 1800

URL_PILOTOS = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json?limit=1000"
URL_CONSTRUTORES = "https://api.jolpi.ca/ergast/f1/current/constructorStandings.json?limit=1000"
URL_CALENDARIO = "https://api.jolpi.ca/ergast/f1/current.json?limit=1000"
URL_ULTIMA_CORRIDA = "https://api.jolpi.ca/ergast/f1/current/last/results.json?limit=1000"
URL_RESULTADOS = "https://api.jolpi.ca/ergast/f1/current/results.json?limit=1000"
URL_SPRINTS = "https://api.jolpi.ca/ergast/f1/current/sprint.json?limit=1000"
URL_QUALIFYING = "https://api.jolpi.ca/ergast/f1/current/qualifying.json?limit=1000"

MODOS = {
    "pilotos": [URL_PILOTOS],
    "construtores": [URL_CONSTRUTORES],
    "calendario": [URL_CALENDARIO],
    "proxima": [URL_CALENDARIO],
    "ultima_corrida": [URL_ULTIMA_CORRIDA],
    "resultados": [URL_RESULTADOS, URL_SPRINTS],
    "qualifying": [URL_QUALIFYING]
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

def _formatar_data_hora_local(date_str, time_str):
    if not date_str or not time_str:
        return date_str, time_str.replace("Z", "") if time_str else ""
    hora_limpa = time_str.replace("Z", "")
    try:
        dt_utc = datetime.datetime.strptime(f"{date_str}T{hora_limpa}", "%Y-%m-%dT%H:%M:%S")
        dt_utc = dt_utc.replace(tzinfo=datetime.timezone.utc)
        dt_local = dt_utc.astimezone()
        return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M:%S")
    except Exception:
        return date_str, hora_limpa

try:
    import config
    BASE_DIR = os.path.join(config.getUserConfigPath(), "cache_tabela_f1")
    try:
        config.conf.spec["f1Acessivel"] = { 
            "anunciar_resultados_auto": "boolean(default=True)",
            "verificar_atualizacoes_auto": "boolean(default=True)"
        }
    except:
        pass
except Exception:
    BASE_DIR = os.path.join(os.environ.get("APPDATA", ""), "nvda", "cache_tabela_f1")

BASE_DIR = _safe_makedirs(BASE_DIR)

def _get_config_lembretes_path():
    return os.path.join(BASE_DIR, "config_lembretes.json")

def _carregar_config_lembretes():
    caminho = _get_config_lembretes_path()
    padrao = {
        "minutos_antecedencia": 5,
        "tempos_lembretes": "60, 30, 15, 5",
        "fuso_horario": "local",
        "corridas": {}
    }
    try:
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
                for key in padrao:
                    if key in dados:
                        padrao[key] = dados[key]
    except Exception:
        pass
    return padrao

def _salvar_config_lembretes(dados):
    caminho = _get_config_lembretes_path()
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

class ConfiguracoesGeraisDialog(wx.Dialog):
    def __init__(self, parent, plugin_ref):
        super().__init__(parent, title=_("Configurações Gerais - Fórmula 1"), style=wx.DEFAULT_DIALOG_STYLE)
        self.plugin = plugin_ref
        
        self.panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl_fuso = wx.StaticText(self.panel, label=_("Fuso horário preferido para exibição na tabela:"))
        mainSizer.Add(lbl_fuso, 0, wx.ALL, 5)
        
        opcoes_fuso = [
            _("Apenas Horário Local (Computador)"),
            _("Apenas Horário Universal (UTC)"),
            _("Ambos os Horários (Local e UTC)")
        ]
        self.combo_fuso = wx.Choice(self.panel, choices=opcoes_fuso)
        fuso_salvo = self.plugin.config_lembretes.get("fuso_horario", "local")
        if fuso_salvo == "utc": self.combo_fuso.SetSelection(1)
        elif fuso_salvo == "ambos": self.combo_fuso.SetSelection(2)
        else: self.combo_fuso.SetSelection(0)
            
        mainSizer.Add(self.combo_fuso, 0, wx.ALL | wx.EXPAND, 5)
        
        lbl_tempos = wx.StaticText(self.panel, label=_("Minutos de antecedência para múltiplos lembretes (separados por vírgula):"))
        mainSizer.Add(lbl_tempos, 0, wx.ALL, 5)
        
        texto_tempos = self.plugin.config_lembretes.get("tempos_lembretes", "60, 30, 15, 5")
        self.txt_tempos = wx.TextCtrl(self.panel, value=str(texto_tempos))
        mainSizer.Add(self.txt_tempos, 0, wx.ALL | wx.EXPAND, 5)
        
        self.chkAnunciar = wx.CheckBox(self.panel, label=_("Anunciar resultados automaticamente após o fim da sessão (Nota: O anúncio não é imediato. Ele ocorrerá algumas horas após a sessão, assim que o resultado oficial for publicado)"))
        try:
            import config
            val = config.conf["f1Acessivel"]["anunciar_resultados_auto"]
            self.chkAnunciar.SetValue(val)
        except:
            self.chkAnunciar.SetValue(True)
        mainSizer.Add(self.chkAnunciar, 0, wx.ALL, 5)

        self.chkAtualizarAuto = wx.CheckBox(self.panel, label=_("Verificar atualizações automaticamente ao iniciar o NVDA"))
        try:
            import config
            val_upd = config.conf["f1Acessivel"]["verificar_atualizacoes_auto"]
            self.chkAtualizarAuto.SetValue(val_upd)
        except:
            self.chkAtualizarAuto.SetValue(True)
        mainSizer.Add(self.chkAtualizarAuto, 0, wx.ALL, 5)
        
        self.btn_update = wx.Button(self.panel, label=_("Verificar atualizações do complemento..."))
        self.btn_update.Bind(wx.EVT_BUTTON, self._ao_verificar_atualizacao)
        mainSizer.Add(self.btn_update, 0, wx.ALL, 5)
        
        bottomSizer = wx.BoxSizer(wx.HORIZONTAL)
        bottomSizer.AddStretchSpacer()
        
        btnSizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self.panel, wx.ID_OK, label=_("Salvar"))
        btn_ok.SetDefault()
        btnSizer.AddButton(btn_ok)
        
        btn_cancel = wx.Button(self.panel, wx.ID_CANCEL, label=_("Cancelar"))
        btnSizer.AddButton(btn_cancel)
        btnSizer.Realize()
        
        bottomSizer.Add(btnSizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        mainSizer.Add(bottomSizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.panel.SetSizer(mainSizer)
        dlgSizer = wx.BoxSizer(wx.VERTICAL)
        dlgSizer.Add(self.panel, 1, wx.EXPAND | wx.ALL, 0)
        self.SetSizerAndFit(dlgSizer)
        self.CentreOnParent()

    def _ao_verificar_atualizacao(self, event):
        # Chama a função de update que já existe no plugin
        try:
            self.plugin._on_check_updates(None)
        except Exception:
            pass

class ConfiguracaoLembretesDialog(wx.Dialog):
    def __init__(self, parent, plugin_ref, corrida_alvo):
        rd = corrida_alvo.get("round", "?")
        super().__init__(parent, title=_("Configurações de Lembretes - Etapa ") + rd, style=wx.DEFAULT_DIALOG_STYLE)
        self.plugin = plugin_ref
        
        self.panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        
        config_etapa = self.plugin.config_lembretes.get("corridas", {}).get(str(rd), {})
        
        self.cb_usar_intervalos = wx.CheckBox(self.panel, label=_("Usar múltiplos lembretes (configurações gerais)"))
        self.cb_usar_intervalos.SetValue(config_etapa.get("usar_intervalos", False))
        mainSizer.Add(self.cb_usar_intervalos, 0, wx.ALL, 5)
        
        lbl_minutos = wx.StaticText(self.panel, label=_("Ou avisar quantos minutos antes (tempo único)?"))
        mainSizer.Add(lbl_minutos, 0, wx.ALL, 5)
        
        self.spin_minutos = wx.SpinCtrl(self.panel, min=1, max=120, initial=self.plugin.config_lembretes.get("minutos_antecedencia", 5))
        mainSizer.Add(self.spin_minutos, 0, wx.ALL | wx.EXPAND, 5)
        
        lbl_sessoes = wx.StaticText(self.panel, label=_("Selecione quais sessões deseja ser lembrado:"))
        mainSizer.Add(lbl_sessoes, 0, wx.ALL, 5)
        
        self.checkboxes = {}
        
        sessoes_api = {
            "FirstPractice": "Treino Livre 1",
            "SecondPractice": "Treino Livre 2",
            "ThirdPractice": "Treino Livre 3",
            "SprintQualifying": "Qualificação Sprint",
            "Sprint": "Corrida Sprint",
            "Qualifying": "Classificação Principal"
        }
        
        sessoes_para_exibir = []
        for chave, nome in sessoes_api.items():
            if chave in corrida_alvo:
                sessoes_para_exibir.append(nome)
        sessoes_para_exibir.append("Corrida Principal")
        
        config_etapa = self.plugin.config_lembretes.get("corridas", {}).get(str(rd), {})
        
        for sessao in sessoes_para_exibir:
            cb = wx.CheckBox(self.panel, label=sessao)
            cb.SetValue(config_etapa.get(sessao, False))
            mainSizer.Add(cb, 0, wx.ALL, 2)
            self.checkboxes[sessao] = cb
            
        # Sizer para os botões do final
        bottomSizer = wx.BoxSizer(wx.HORIZONTAL)
        
        bottomSizer.AddStretchSpacer()
        
        btnSizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self.panel, wx.ID_OK, label=_("Salvar"))
        btn_ok.SetDefault()
        btnSizer.AddButton(btn_ok)
        
        btn_cancel = wx.Button(self.panel, wx.ID_CANCEL, label=_("Cancelar"))
        btnSizer.AddButton(btn_cancel)
        btnSizer.Realize()
        
        bottomSizer.Add(btnSizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        mainSizer.Add(bottomSizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.panel.SetSizer(mainSizer)
        
        dlgSizer = wx.BoxSizer(wx.VERTICAL)
        dlgSizer.Add(self.panel, 1, wx.EXPAND | wx.ALL, 0)
        self.SetSizerAndFit(dlgSizer)
        self.CentreOnParent()

class ErrorDialog(wx.MessageDialog):
    def __init__(self, parent=None):
        super().__init__(
            parent or gui.mainFrame,
            _("Não foi possível carregar os dados da Fórmula 1.\nTente mais tarde."),
            _("Fórmula 1"),
            wx.OK | wx.ICON_WARNING
        )

class MonitorDeResultados(threading.Thread):
    def __init__(self, tipo_sessao, dt_inicio_utc, url_busca, plugin_ref, rd_alvo):
        super().__init__()
        self.tipo_sessao = tipo_sessao
        self.dt_inicio_utc = dt_inicio_utc
        self.url_busca = url_busca
        self.plugin = plugin_ref
        self.rd_alvo = rd_alvo
        self.daemon = True
        self._parar = threading.Event()

    def parar(self):
        self._parar.set()

    def run(self):
        horas_duracao = 2.0 if self.tipo_sessao.lower() == "corrida" else 1.25
        dt_fim_estimado = self.dt_inicio_utc + datetime.timedelta(hours=horas_duracao)
        
        while True:
            agora_utc = datetime.datetime.now(datetime.timezone.utc)
            if agora_utc >= dt_fim_estimado:
                break
            segundos_espera = (dt_fim_estimado - agora_utc).total_seconds()
            if self._parar.wait(min(segundos_espera, 3600)):
                return
                
        tentativas = 0
        limite_tentativas = 20
        intervalo_checagem = 900
        
        while not self._parar.is_set() and tentativas < limite_tentativas:
            try:
                import urllib.request
                import json
                req = urllib.request.Request(self.url_busca, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    payload = resp.read().decode("utf-8", errors="replace")
                obj = json.loads(payload)
                
                races = obj.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                encontrou = False
                corrida_result = None
                for r in races:
                    if str(r.get("round")) == str(self.rd_alvo):
                        encontrou = True
                        corrida_result = r
                        break
                
                if encontrou and corrida_result:
                    wx.CallAfter(self.anunciar, corrida_result)
                    break 
            except Exception:
                pass
                
            tentativas += 1
            self._parar.wait(intervalo_checagem)
            
    def anunciar(self, corrida_result):
        try:
            import config
            if not config.conf["f1Acessivel"].get("anunciar_resultados_auto", True):
                return
        except:
            pass
            
        import nvwave
        import os
        import ui
        import tones
        
        caminho_audio = os.path.join(os.path.dirname(__file__), "Alerta_radio_f1.wav")
        if os.path.exists(caminho_audio):
            nvwave.playWaveFile(caminho_audio)
        else:
            tones.beep(1000, 500)
            
        data_api = corrida_result.get("date", "")
        hora_api = corrida_result.get("time", "")
        d_loc, h_loc = _formatar_data_hora_local(data_api, hora_api)
        
        if self.tipo_sessao.lower() == "corrida":
            vencedor = _("Desconhecido")
            try:
                resultados = corrida_result.get("Results", [])
                if resultados:
                    p1 = resultados[0]
                    vencedor = f"{p1['Driver']['givenName']} {p1['Driver']['familyName']}"
            except: pass
            msg = _("Atenção: Os resultados da Corrida que ocorreu dia {d} às {h} já estão disponíveis. Vencedor: {v}.").format(d=d_loc, h=h_loc, v=vencedor)
        else:
            pole = _("Desconhecido")
            equipe = ""
            try:
                resultados = corrida_result.get("QualifyingResults", [])
                if resultados:
                    p1 = resultados[0]
                    pole = f"{p1['Driver']['givenName']} {p1['Driver']['familyName']}"
                    eq = p1.get("Constructor", {}).get("name", "")
                    if eq:
                        equipe = f" pela equipe {eq}"
            except: pass
            msg = _("Atenção: Os resultados da Classificação que ocorreu dia {d} às {h} já estão disponíveis. Pole position para {p}{e}.").format(d=d_loc, h=h_loc, p=pole, e=equipe)
            
        ui.message(msg)

class F1Dialog(wx.Dialog):
    def __init__(self, dados, modo="pilotos", onForceRefresh=None, onChangeModo=None, plugin_ref=None):
        super(F1Dialog, self).__init__(
            gui.mainFrame,
            title=self._obter_titulo(modo),
            style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
        )
        self.dados = dados or []
        self.modo = modo
        self._onForceRefresh = onForceRefresh
        self._onChangeModo = onChangeModo
        self.plugin_ref = plugin_ref

        self.mainPanel = wx.Panel(self)
        panelSizer = wx.BoxSizer(wx.VERTICAL)

        comboSizer = wx.BoxSizer(wx.HORIZONTAL)
        lblModo = wx.StaticText(self.mainPanel, label=_("Selecione o que deseja ver:"))
        comboSizer.Add(lblModo, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)

        self.modos_opcoes = [
            ("pilotos", _("Classificação de Pilotos")),
            ("construtores", _("Classificação de Construtores")),
            ("calendario", _("Calendário Completo")),
            ("proxima", _("Sessões do Fim de Semana")),
            ("resultados", _("Resultados das Corridas")),
            ("qualifying", _("Resultados das Qualificações")),
            ("ultima_corrida", _("Resultado da Última Corrida"))
        ]

        opcoes_texto = [op[1] for op in self.modos_opcoes]
        self.comboModos = wx.Choice(self.mainPanel, choices=opcoes_texto)
        
        idx = next((i for i, op in enumerate(self.modos_opcoes) if op[0] == self.modo), 0)
        self.comboModos.SetSelection(idx)
        
        comboSizer.Add(self.comboModos, 0, wx.ALL, 2)
        
        self._debounce_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_debounce_timer, self._debounce_timer)
        self.comboModos.Bind(wx.EVT_CHOICE, self._on_combo_change)
        
        panelSizer.Add(comboSizer, 0, wx.EXPAND | wx.ALL, 10)

        self.arvore = wx.TreeCtrl(self.mainPanel, style=wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT | wx.TR_HIDE_ROOT | wx.BORDER_SIMPLE | wx.TR_SINGLE | wx.TR_ROW_LINES)
        panelSizer.Add(self.arvore, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

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
        
        self.btnVerQuali = wx.Button(self.mainPanel, wx.ID_ANY, _("Ver Qualificação da Etapa"))
        btnSizer.Add(self.btnVerQuali, 0, wx.ALL, 2)
        
        self.btnVerCorrida = wx.Button(self.mainPanel, wx.ID_ANY, _("Ver Corrida da Etapa"))
        btnSizer.Add(self.btnVerCorrida, 0, wx.ALL, 2)
        
        self.btnAtualizar = wx.Button(self.mainPanel, wx.ID_ANY, _("Atualizar dados"))
        btnSizer.Add(self.btnAtualizar, 0, wx.ALL, 2)

        self.btnCopiar = wx.Button(self.mainPanel, wx.ID_ANY, _("Copiar tabela"))
        btnSizer.Add(self.btnCopiar, 0, wx.ALL, 2)

        self.btnSalvar = wx.Button(self.mainPanel, wx.ID_ANY, _("Salvar em TXT"))
        btnSizer.Add(self.btnSalvar, 0, wx.ALL, 2)

        self.btnFechar = wx.Button(self.mainPanel, wx.ID_CANCEL, _("Fechar"))
        btnSizer.Add(self.btnFechar, 0, wx.ALL, 2)

        panelSizer.Add(btnSizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.btnVerQuali.Bind(wx.EVT_BUTTON, self._on_click_ver_quali)
        self.btnVerCorrida.Bind(wx.EVT_BUTTON, self._on_click_ver_corrida)
        self.btnAtualizar.Bind(wx.EVT_BUTTON, self._on_click_atualizar)
        self.btnCopiar.Bind(wx.EVT_BUTTON, lambda evt: self._copiar_tabela_para_area_de_transferencia())
        self.btnSalvar.Bind(wx.EVT_BUTTON, lambda evt: self._salvar_tabela_em_txt())
        self.btnFechar.Bind(wx.EVT_BUTTON, lambda evt: self.Destroy())

        if not callable(self._onForceRefresh):
            self.btnAtualizar.Disable()

        self.mainPanel.SetSizer(panelSizer)
        dlgSizer = wx.BoxSizer(wx.VERTICAL)
        dlgSizer.Add(self.mainPanel, 1, wx.EXPAND | wx.ALL, 0)
        self.SetSizer(dlgSizer)
        
        self.Maximize(True)
        self.Raise()

        root = self.arvore.GetRootItem()
        if root and root.IsOk():
            primeiro, cookie = self.arvore.GetFirstChild(root)
            if primeiro.IsOk():
                self.comboModos.SetFocus()
                self.arvore.SelectItem(primeiro)
        else:
            self.comboModos.SetFocus()

    def _on_combo_change(self, event):
        self._debounce_timer.Start(500, wx.TIMER_ONE_SHOT)

    def _on_debounce_timer(self, event):
        idx = self.comboModos.GetSelection()
        if idx >= 0 and idx < len(self.modos_opcoes):
            novo_modo = self.modos_opcoes[idx][0]
            if novo_modo != self.modo:
                self._on_click_modo(novo_modo)

    def _on_click_ver_quali(self, event):
        self._ver_resultado_etapa("qualifying")
        
    def _on_click_ver_corrida(self, event):
        self._ver_resultado_etapa("resultados")
        
    def _ver_resultado_etapa(self, modo_destino):
        item = self.arvore.GetSelection()
        if not item.IsOk():
            ui.message(_("Selecione uma etapa na árvore primeiro."))
            return
            
        import re
        rd = None
        atual = item
        while atual.IsOk() and atual != self.arvore.GetRootItem():
            texto = self.arvore.GetItemText(atual)
            match = re.search(r"Etapa (\d+)", texto)
            if match:
                rd = match.group(1)
                break
            atual = self.arvore.GetItemParent(atual)
            
        if not rd:
            ui.message(_("Não foi possível identificar a etapa selecionada. Fique em cima do nome de uma etapa."))
            return
            
        self._focar_etapa_rd = rd
        idx = next((i for i, op in enumerate(self.modos_opcoes) if op[0] == modo_destino), -1)
        if idx != -1:
            self.comboModos.SetSelection(idx)
            self._on_click_modo(modo_destino)

    def _obter_titulo(self, modo):
        titulos = {
            "pilotos": _("Fórmula 1 - Classificação de Pilotos"),
            "construtores": _("Fórmula 1 - Classificação de Construtores"),
            "calendario": _("Fórmula 1 - Calendário de Corridas"),
            "proxima": _("Fórmula 1 - Treinos e Sessões do Fim de Semana"),
            "resultados": _("Fórmula 1 - Resultados do Ano"),
            "ultima_corrida": _("Fórmula 1 - Resultado da Última Corrida"),
            "qualifying": _("Fórmula 1 - Resultados das Qualificações")
        }
        return titulos.get(modo, "Fórmula 1")

    def _popular_arvore(self):
        try:
            self.arvore.DeleteAllItems()
        except Exception:
            pass
            
        root = self.arvore.AddRoot("Raiz")
        
        fuso_pref = self.plugin_ref.config_lembretes.get("fuso_horario", "local") if hasattr(self, "plugin_ref") and self.plugin_ref else "local"
        
        def formatar_fuso(d_api, t_api):
            d_loc, t_loc = _formatar_data_hora_local(d_api, t_api)
            if fuso_pref == "utc": return f"{d_api} {t_api}".strip()
            elif fuso_pref == "ambos": return f"{d_loc} {t_loc} (Local) | {d_api} {t_api} (UTC)".strip()
            else: return f"{d_loc} {t_loc}".strip()

        if self.modo == "proxima":
            hoje = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
            corridas_futuras = [r for r in self.dados if r.get("date", "") >= hoje]
            corrida = corridas_futuras[0] if corridas_futuras else (self.dados[-1] if self.dados else {})
            
            rd = corrida.get("round", "?")
            nome = corrida.get("raceName", "")
            pai = self.arvore.AppendItem(root, f"Etapa {rd} - {nome}")
            
            sessoes = [("FirstPractice", "Treino Livre 1"), ("SecondPractice", "Treino Livre 2"), ("ThirdPractice", "Treino Livre 3"), ("SprintQualifying", "Qualificação Sprint"), ("Sprint", "Corrida Sprint"), ("Qualifying", "Classificação Principal")]
            for sessao, titulo in sessoes:
                if sessao in corrida:
                    d_api = corrida[sessao].get("date", "")
                    t_api = corrida[sessao].get("time", "")
                    texto_data = formatar_fuso(d_api, t_api)
                    self.arvore.AppendItem(pai, f"{titulo}: {texto_data}")
            
            d_api = corrida.get("date", "")
            t_api = corrida.get("time", "")
            texto_data = formatar_fuso(d_api, t_api)
            self.arvore.AppendItem(pai, f"Corrida Principal: {texto_data}")
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
                        corridas[rd]["sprint"].extend(resultados)
                    else:
                        corridas[rd]["principal"].extend(resultados)
                        
            for rd in sorted(corridas.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                c = corridas[rd]
                pai = self.arvore.AppendItem(root, f"Etapa {rd} - {c['nome']}")
                
                if c["principal"]:
                    p1 = c["principal"][0]
                    vencedor = f"{p1['Driver']['givenName']} {p1['Driver']['familyName']}"
                    no_principal = self.arvore.AppendItem(pai, f"Resultado Corrida Principal (Vencedor: {vencedor})")
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
                
                d_api = item.get("date", "")
                t_api = item.get("time", "")
                texto_data_principal = formatar_fuso(d_api, t_api)
                
                # Exibir a data apenas se fuso for UTC ou Local. 
                # (Extrair apenas a parte da data de texto_data_principal)
                data_exibicao = texto_data_principal.split(" ")[0] if " | " not in texto_data_principal else texto_data_principal
                
                pai = self.arvore.AppendItem(root, f"Etapa {rd} - {nome} no circuito {circuito} ({data_exibicao})")
                
                sessoes = [("FirstPractice", "Treino Livre 1"), ("SecondPractice", "Treino Livre 2"), ("ThirdPractice", "Treino Livre 3"), ("SprintQualifying", "Qualificação Sprint"), ("Sprint", "Corrida Sprint"), ("Qualifying", "Classificação Principal")]
                for sessao, titulo in sessoes:
                    if sessao in item:
                        d_api_s = item[sessao].get("date", "")
                        t_api_s = item[sessao].get("time", "")
                        texto_data_s = formatar_fuso(d_api_s, t_api_s)
                        self.arvore.AppendItem(pai, f"{titulo}: {texto_data_s}")
                
                self.arvore.AppendItem(pai, f"Corrida Principal: {texto_data_principal}")
                
            elif self.modo == "qualifying":
                rd = item.get("round", "?")
                nome = item.get("raceName", "")
                
                pai = self.arvore.AppendItem(root, f"Etapa {rd} - Qualificação: {nome}")
                
                resultados = item.get("QualifyingResults", [])
                if resultados:
                    p1 = resultados[0]
                    vencedor = f"{p1.get('Driver', {}).get('givenName', '')} {p1.get('Driver', {}).get('familyName', '')}"
                    self.arvore.AppendItem(pai, f"Pole Position: {vencedor}")
                    
                    for p in resultados:
                        pos = p.get("position", "?")
                        driver = p.get("Driver", {})
                        nome_piloto = f"{driver.get('givenName', '')} {driver.get('familyName', '')}"
                        eq = p.get("Constructor", {}).get("name", "")
                        
                        tempos = []
                        if "Q1" in p: tempos.append(f"Q1: {p['Q1']}")
                        if "Q2" in p: tempos.append(f"Q2: {p['Q2']}")
                        if "Q3" in p: tempos.append(f"Q3: {p['Q3']}")
                        tempos_str = " | ".join(tempos) if tempos else "Sem tempo"
                        
                        self.arvore.AppendItem(pai, f"{pos}º {nome_piloto} ({eq}) - {tempos_str}")
                        
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

    def mudar_modo_em_lugar(self, novo_modo, novos_dados):
        self.modo = novo_modo
        self.SetTitle(self._obter_titulo(novo_modo))
        self._atualizar_dados_na_tela(novos_dados)
        ui.message(_("Resultados carregados."))

    def _atualizar_dados_na_tela(self, novos_dados):
        self.dados = novos_dados or []
        self._popular_arvore()
        
        rd_alvo = getattr(self, "_focar_etapa_rd", None)
        if rd_alvo:
            self._focar_etapa_rd = None
            import re
            root = self.arvore.GetRootItem()
            child, cookie = self.arvore.GetFirstChild(root)
            encontrou = False
            while child.IsOk():
                texto = self.arvore.GetItemText(child)
                match = re.search(r"Etapa (\d+)", texto)
                if match and match.group(1) == rd_alvo:
                    self.arvore.SelectItem(child)
                    self.arvore.Expand(child)
                    encontrou = True
                    break
                child, cookie = self.arvore.GetNextChild(root, cookie)
            
            if not encontrou:
                ui.message(_("Os resultados da etapa {rd} ainda não estão disponíveis.").format(rd=rd_alvo))
                child, cookie = self.arvore.GetFirstChild(root)
                if child.IsOk():
                    self.arvore.SelectItem(child)
        else:
            root = self.arvore.GetRootItem()
            if root.IsOk():
                primeiro = self.arvore.GetFirstChild(root)[0]
                if primeiro.IsOk():
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
            _("""Atalhos disponíveis:

- Alt Gr + F: abre o painel da Fórmula 1 (atalho global do NVDA).
- Esc: fecha a janela.
- Setas para cima/baixo: navega pela lista.
- Setas para esquerda/direita: expande e recolhe os detalhes de um item.
- F1: abre esta ajuda.
- Ctrl+C: copia a linha selecionada.
- Ctrl+A: copia todos os dados da tela.
- Ctrl+S: salva os dados em TXT.
- Ctrl+L: abre a configuração de lembretes em qualquer evento.

Pressione Esc para voltar."""),
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
                self.arvore.SetFocus()
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
        return "\n".join(linhas)

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

    def _abrir_configuracoes_lembretes(self):
        if self.modo not in ["calendario", "proxima"]:
            ui.message(_("A configuração de lembretes só está disponível nas telas de Calendário e Sessões."))
            return
            
        corrida_alvo = None
        rd = None
        if self.modo in ["calendario", "proxima"]:
            item = self.arvore.GetSelection()
            if item.IsOk():
                # Procura a raiz do item se necessário para achar o Round
                parent = item
                while parent.IsOk() and parent != self.arvore.GetRootItem():
                    texto_parent = self.arvore.GetItemText(parent)
                    import re
                    match_rd = re.search(r"Etapa (\d+)", texto_parent)
                    if match_rd:
                        rd = match_rd.group(1)
                        break
                    parent = self.arvore.GetItemParent(parent)

        if not rd:
            ui.message(_("Não foi possível identificar a etapa selecionada."))
            return
            
        for c in self.dados:
            if str(c.get("round", "")) == str(rd):
                corrida_alvo = c
                break
                
        if not corrida_alvo:
            ui.message(_("Dados da etapa não encontrados."))
            return

        # Verifica se a corrida já passou usando a conversão para o fuso local
        d_api = corrida_alvo.get("date", "")
        t_api = corrida_alvo.get("time", "")
        d_loc, _ = _formatar_data_hora_local(d_api, t_api)
        
        import datetime
        hoje = datetime.datetime.now().date().isoformat()
        if d_loc and d_loc < hoje:
            ui.message(_("Atenção! Você não precisa configurar lembretes para um evento que já passou."))
            return

        if not self.plugin_ref:
            ui.message(_("Não foi possível abrir as configurações."))
            return
            
        dlg = ConfiguracaoLembretesDialog(self, self.plugin_ref, corrida_alvo)
        if dlg.ShowModal() == wx.ID_OK:
            self.plugin_ref.config_lembretes["minutos_antecedencia"] = dlg.spin_minutos.GetValue()
            if "corridas" not in self.plugin_ref.config_lembretes:
                self.plugin_ref.config_lembretes["corridas"] = {}
            rd_str = str(rd)
            if rd_str not in self.plugin_ref.config_lembretes["corridas"]:
                self.plugin_ref.config_lembretes["corridas"][rd_str] = {}
                
            usar_intervalos = dlg.cb_usar_intervalos.GetValue()
            self.plugin_ref.config_lembretes["corridas"][rd_str]["usar_intervalos"] = usar_intervalos
            
            marcadas = []
            for sessao, cb in dlg.checkboxes.items():
                is_checked = cb.GetValue()
                self.plugin_ref.config_lembretes["corridas"][rd_str][sessao] = is_checked
                if is_checked:
                    marcadas.append(sessao)
            _salvar_config_lembretes(self.plugin_ref.config_lembretes)
            
            if not marcadas:
                msg = _("Lembrete salvo! Nenhum aviso ativado para a etapa {rd}.").format(rd=rd)
            elif usar_intervalos:
                msg = _("Lembrete salvo! Múltiplos avisos ativados para a etapa {rd}. Para alterar os minutos dos intervalos, acesse o menu do NVDA, vá em Ferramentas e depois em Configurações - Fórmula 1.").format(rd=rd)
            else:
                msg = _("Lembrete salvo! Você será avisado para as seguintes sessões da etapa {rd}: {lista}.").format(
                    rd=rd, lista=", ".join(marcadas)
                )
            
            ui.message(msg)
        dlg.Destroy()
        self.arvore.SetFocus()

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
            if keyCode in (ord("L"), ord("l")):
                self._abrir_configuracoes_lembretes()
                return
        if keyCode == wx.WXK_F1:
            self._mostrar_ajuda()
            return
        if keyCode == wx.WXK_ESCAPE:
            self.Destroy()
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
        
        self._lembreteTimer = None
        self.lembretes_disparados = []
        
        self.config_lembretes = _carregar_config_lembretes()
        
        wx.CallAfter(self._add_tools_menu_items)
        wx.CallAfter(self._iniciar_temporizador_lembretes)
        
        try:
            import config
            auto_update = config.conf["f1Acessivel"].get("verificar_atualizacoes_auto", True)
            if auto_update:
                def _do_auto_update():
                    try:
                        from . import f1Updater
                        f1Updater.check_for_updates(manual=False)
                    except Exception:
                        pass
                wx.CallLater(15000, _do_auto_update)
        except Exception:
            pass

    def terminate(self):
        self._stop_loading_timer()
        self._remove_tools_menu_items()
        self._parar_temporizador_lembretes()
        if hasattr(self, "_threads_monitoramento"):
            for t in self._threads_monitoramento.values():
                try: t.parar()
                except: pass
            self._threads_monitoramento.clear()
        super(GlobalPlugin, self).terminate()
        
    def _iniciar_temporizador_lembretes(self):
        mainFrame = getattr(gui, "mainFrame", None)
        if not mainFrame: return
        self._lembreteTimer = wx.Timer(mainFrame)
        mainFrame.Bind(wx.EVT_TIMER, self._verificar_agora, self._lembreteTimer)
        self._lembreteTimer.Start(60000)

    def _parar_temporizador_lembretes(self):
        mainFrame = getattr(gui, "mainFrame", None)
        if self._lembreteTimer and mainFrame:
            try: mainFrame.Unbind(wx.EVT_TIMER, handler=self._verificar_agora, source=self._lembreteTimer)
            except Exception: pass
            try: self._lembreteTimer.Stop()
            except Exception: pass
        self._lembreteTimer = None

    def _verificar_agora(self, event):
        dados_cache, _ = self._carregar_cache_stale("proxima")
        if not dados_cache: return
            
        hoje = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        corridas_futuras = [r for r in dados_cache if r.get("date", "") >= hoje]
        if not corridas_futuras: return
            
        proxima_corrida = corridas_futuras[0]
        nome_gp = proxima_corrida.get("raceName", "Grande Prêmio")
        rd = proxima_corrida.get("round", "?")
        
        sessoes_api = {
            "FirstPractice": "Treino Livre 1",
            "SecondPractice": "Treino Livre 2",
            "ThirdPractice": "Treino Livre 3",
            "SprintQualifying": "Qualificação Sprint",
            "Sprint": "Corrida Sprint",
            "Qualifying": "Classificação Principal"
        }
        
        agora_utc = datetime.datetime.now(datetime.timezone.utc)
        
        for chave_api, nome_amigavel in sessoes_api.items():
            if chave_api in proxima_corrida:
                self._checar_horario_disparar(
                    proxima_corrida[chave_api], 
                    nome_amigavel, 
                    nome_gp, 
                    agora_utc,
                    rd
                )
                self._checar_monitor_resultado(proxima_corrida[chave_api], nome_amigavel, rd)
                
        self._checar_horario_disparar(proxima_corrida, "Corrida Principal", nome_gp, agora_utc, rd)
        self._checar_monitor_resultado(proxima_corrida, "Corrida Principal", rd)

    def _checar_monitor_resultado(self, sessao_dict, nome_sessao, rd):
        try:
            import config
            if not config.conf["f1Acessivel"].get("anunciar_resultados_auto", True):
                return
        except:
            pass

        if nome_sessao not in ["Corrida Principal", "Classificação Principal"]:
            return
            
        chave_thread = f"{rd}_{nome_sessao}"
        if chave_thread in getattr(self, "_threads_monitoramento", {}):
            return
            
        data_str = sessao_dict.get("date")
        hora_str = sessao_dict.get("time")
        if not data_str or not hora_str: return
        
        hora_str = hora_str.replace("Z", "")
        dt_sessao_str = f"{data_str}T{hora_str}"
        try:
            dt_sessao_utc = datetime.datetime.strptime(dt_sessao_str, "%Y-%m-%dT%H:%M:%S")
            dt_sessao_utc = dt_sessao_utc.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            return
            
        agora_utc = datetime.datetime.now(datetime.timezone.utc)
        if agora_utc > dt_sessao_utc + datetime.timedelta(hours=8):
            return
            
        tipo = "corrida" if nome_sessao == "Corrida Principal" else "qualifying"
        url = URL_RESULTADOS if tipo == "corrida" else URL_QUALIFYING
        
        if not hasattr(self, "_threads_monitoramento"):
            self._threads_monitoramento = {}
            
        t = MonitorDeResultados(tipo, dt_sessao_utc, url, self, rd)
        self._threads_monitoramento[chave_thread] = t
        t.start()

    def _checar_horario_disparar(self, sessao_dict, nome_sessao, nome_gp, agora_utc, rd):
        config_etapa = self.config_lembretes.get("corridas", {}).get(str(rd), {})
        if not config_etapa.get(nome_sessao, False):
            return 
            
        data_str = sessao_dict.get("date")
        hora_str = sessao_dict.get("time")
        
        if not data_str or not hora_str: return
        
        hora_str = hora_str.replace("Z", "")
        dt_sessao_str = f"{data_str}T{hora_str}"
        try:
            dt_sessao_utc = datetime.datetime.strptime(dt_sessao_str, "%Y-%m-%dT%H:%M:%S")
            dt_sessao_utc = dt_sessao_utc.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            return

        tempo_restante = dt_sessao_utc - agora_utc
        minutos_restantes = tempo_restante.total_seconds() / 60.0
        
        usar_intervalos = config_etapa.get("usar_intervalos", False)
        
        if usar_intervalos:
            texto_tempos = self.config_lembretes.get("tempos_lembretes", "60, 30, 15, 5")
            try:
                tempos_lista = [int(x.strip()) for x in str(texto_tempos).split(",") if x.strip().isdigit()]
            except:
                tempos_lista = [5]
            if not tempos_lista: tempos_lista = [5]
        else:
            tempos_lista = [self.config_lembretes.get("minutos_antecedencia", 5)]

        tempos_lista = sorted(tempos_lista, reverse=True)
        disparou_agora = False

        for antecedencia in tempos_lista:
            id_lembrete = f"{nome_sessao}-{data_str}-{antecedencia}"
            if id_lembrete in self.lembretes_disparados: continue
            
            if 0 < minutos_restantes <= antecedencia:
                self.lembretes_disparados.append(id_lembrete)
                if not disparou_agora:
                    self._disparar_alarme(nome_sessao, nome_gp, int(minutos_restantes))
                    disparou_agora = True

    def _disparar_alarme(self, nome_sessao, nome_gp, minutos):
        wav_path = os.path.join(os.path.dirname(__file__), "Alerta_radio_f1.wav")
        
        if os.path.exists(wav_path):
            nvwave.playWaveFile(wav_path)
        else:
            tones.beep(1000, 500)
            
        mensagem = _(f"Atenção, Fórmula 1! {nome_sessao} do {nome_gp} começará em {minutos} minutos.")
        ui.message(mensagem)

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
            
            self._toolsMenuConfig = toolsMenu.Append(
                wx.ID_ANY,
                _("Configurações - Fórmula 1"),
                _("Abre as configurações gerais do complemento")
            )
            sysTray.Bind(wx.EVT_MENU, self._on_tools_menu_config, self._toolsMenuConfig)
        except Exception:
            log.exception("Falha ao adicionar itens no menu Ferramentas")

    def _remove_tools_menu_items(self):
        try:
            mainFrame = getattr(gui, "mainFrame", None)
            sysTray = getattr(mainFrame, "sysTrayIcon", None) if mainFrame else None
            handlers = [
                (self._toolsMenuItemOpen, self._on_tools_menu_open),
                (getattr(self, "_toolsMenuConfig", None), getattr(self, "_on_tools_menu_config", None))
            ]
            for item, handler in handlers:
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
            self._toolsMenuConfig = None
            self._toolsMenuUpdate = None

    def _on_tools_menu_open(self, event):
        self.script_f1_tabela(None)
        
    def _on_tools_menu_config(self, event):
        def show_dialog():
            try:
                mainFrame = getattr(gui, "mainFrame", None)
                dlg = ConfiguracoesGeraisDialog(mainFrame, self)
                if dlg.ShowModal() == wx.ID_OK:
                    idx_fuso = dlg.combo_fuso.GetSelection()
                    if idx_fuso == 1:
                        fuso = "utc"
                    elif idx_fuso == 2:
                        fuso = "ambos"
                    else:
                        fuso = "local"
                        
                    self.config_lembretes["fuso_horario"] = fuso
                    self.config_lembretes["tempos_lembretes"] = dlg.txt_tempos.GetValue()
                    
                    try:
                        import config
                        config.conf["f1Acessivel"]["anunciar_resultados_auto"] = dlg.chkAnunciar.GetValue()
                        config.conf["f1Acessivel"]["verificar_atualizacoes_auto"] = dlg.chkAtualizarAuto.GetValue()
                    except:
                        pass
                        
                    _salvar_config_lembretes(self.config_lembretes)
                    ui.message(_("Configurações da Fórmula 1 salvas com sucesso."))
                dlg.Destroy()
            except Exception as e:
                log.exception("Erro ao abrir ConfiguracoesGeraisDialog")
        wx.CallAfter(show_dialog)
        
    def _on_check_updates(self, event):
        try:
            from . import f1Updater
            f1Updater.check_for_updates(manual=True)
        except Exception as e:
            import wx
            import gui
            wx.CallAfter(gui.messageBox, _("Erro interno ao iniciar o atualizador: ") + str(e), _("Erro de Atualização"), wx.ICON_ERROR)

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
            elif modo == "calendario" or modo == "proxima" or modo == "qualifying":
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

    def _baixar_json_em_thread(self, modo: str, on_ok, on_fail):
        urls = self._url_for_modo(modo)
        def worker():
            try:
                todos_dados = []
                for u in urls:
                    offset = 0
                    while True:
                        if "?" in u:
                            url_fetch = f"{u}&offset={offset}"
                        else:
                            url_fetch = f"{u}?offset={offset}"
                        req = urllib.request.Request(
                            url_fetch,
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
                            
                        mrdata = obj.get("MRData", {})
                        try:
                            total = int(mrdata.get("total", 0))
                            limit = int(mrdata.get("limit", 100))
                        except (ValueError, TypeError):
                            break
                            
                        offset += limit
                        if offset >= total or not dados:
                            break
                        time.sleep(0.2) # Pausa leve entre requisições para evitar rate limit
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
                onChangeModo=self._open_modo_substituindo,
                plugin_ref=self
            )
            dlg.ShowModal()
        except Exception as e:
            log.error(f"Erro ao mostrar F1Dialog: {e}", exc_info=True)
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
            if dlgAtual:
                wx.CallAfter(lambda: dlgAtual.mudar_modo_em_lugar(modo, dados_cache))
            else:
                wx.CallAfter(lambda: self._mostrar_tabela(dados_cache, modo))
            return

        tones.beep(880, 50)
        ui.message(_("Buscando dados da Fórmula 1."))

        def ok(dados):
            if dlgAtual:
                dlgAtual.mudar_modo_em_lugar(modo, dados)
            else:
                self._mostrar_tabela(dados, modo)

        def fail():
            dados_cache_stale, _ = self._carregar_cache_stale(modo)
            if dados_cache_stale is not None:
                ui.message(_("Mostrando dados do cache."))
                if dlgAtual:
                    dlgAtual.mudar_modo_em_lugar(modo, dados_cache_stale)
                else:
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

    def script_f1_tabela(self, gesture):
        # Translators: Descrição do atalho nas configurações do NVDA
        """Abre a janela da Fórmula 1."""
        self._open_modo("pilotos")

    __gestures = {
        "kb:control+alt+f": "f1_tabela",
        "kb:rightAlt+f": "f1_tabela",
    }
