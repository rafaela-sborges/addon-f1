# -*- coding: UTF-8 -*-
import urllib.request
import json
import threading
import wx
import os
import gui
import addonHandler
import tempfile

addonHandler.initTranslation()
from gettext import gettext as _

REPO_API_URL = "https://api.github.com/repos/rafaela-sborges/addon-f1/releases/latest"

def get_current_addon_version():
    try:
        # Pega a versão do addon ativo
        for addon in addonHandler.getAvailableAddons():
            if addon.name == "f1Acessivel":
                return addon.version
    except Exception:
        pass
    return "2026.9.10" # Fallback

def check_for_updates(manual=False):
    def worker():
        try:
            req = urllib.request.Request(
                REPO_API_URL,
                headers={"User-Agent": "NVDA-F1-Updater"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            
            latest_version = data.get("tag_name", "").lstrip("v")
            current_version = get_current_addon_version().lstrip("v")
            
            if _is_newer(latest_version, current_version):
                assets = data.get("assets", [])
                download_url = None
                for asset in assets:
                    if asset.get("name", "").endswith(".nvda-addon"):
                        download_url = asset.get("browser_download_url")
                        break
                
                if download_url:
                    wx.CallAfter(_prompt_update, latest_version, download_url)
                elif manual:
                    wx.CallAfter(gui.messageBox, _("Nova versão encontrada, mas nenhum arquivo de instalação disponível no GitHub."), _("Atualização F1"))
            elif manual:
                wx.CallAfter(gui.messageBox, _("Você já está usando a versão mais recente ({}).").format(current_version), _("Atualização F1"))
        except Exception as e:
            if manual:
                wx.CallAfter(gui.messageBox, _("Erro ao buscar atualizações: ") + str(e), _("Erro de Atualização", style=wx.ICON_ERROR))
                
    threading.Thread(target=worker, daemon=True).start()

def _is_newer(latest, current):
    def parse_ver(v):
        try:
            return [int(x) for x in v.split(".")]
        except ValueError:
            return [0]
            
    return parse_ver(latest) > parse_ver(current)

def _prompt_update(version, url):
    msg = _("Uma nova versão ({}) do F1 Acessível está disponível.\nDeseja baixar e instalar agora?").format(version)
    res = gui.messageBox(
        msg,
        _("Atualização Disponível"),
        wx.YES_NO | wx.ICON_QUESTION
    )
    if res == wx.YES:
        _download_and_install(url)

def _download_and_install(url):
    def worker():
        try:
            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, "f1Acessivel_update.nvda-addon")
            
            req = urllib.request.Request(url, headers={"User-Agent": "NVDA-F1-Updater"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(file_path, "wb") as f:
                f.write(resp.read())
                
            wx.CallAfter(os.startfile, file_path)
        except Exception as e:
            wx.CallAfter(gui.messageBox, _("Erro ao baixar atualização: ") + str(e), _("Erro de Download", style=wx.ICON_ERROR))
            
    threading.Thread(target=worker, daemon=True).start()
