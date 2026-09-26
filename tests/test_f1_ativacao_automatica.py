# -*- coding: UTF-8 -*-
# Ativação automática dos avisos ao vivo (f1Acessivel.GlobalPlugin._checar_ao_vivo), com o NVDA e o
# wx simulados: passa os minutos de uma corrida e confere quando o complemento conecta e desconecta.
# Rodar da raiz do projeto: python -m unittest discover -s tests

import datetime
import importlib.util
import os
import sys
import tempfile
import types
import unittest

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "addon", "globalPlugins")
FALAS = []


class _Qualquer:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, nome):
        return lambda *a, **k: None


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
           CallLater=lambda *a, **k: None, DEFAULT_DIALOG_STYLE=0, MAXIMIZE_BOX=0, RESIZE_BORDER=0, OK=0, ICON_WARNING=0)
    config = modulo("config", getUserConfigPath=tempfile.gettempdir)
    config.conf = {"f1Acessivel": {"avisos_ao_vivo_auto": True}}
    pacote = types.ModuleType("f1pacote")
    pacote.__path__ = [PASTA]
    sys.modules["f1pacote"] = pacote
    spec = importlib.util.spec_from_file_location("f1pacote.f1Acessivel", os.path.join(PASTA, "f1Acessivel.py"))
    modulo_f1 = importlib.util.module_from_spec(spec)
    sys.modules["f1pacote.f1Acessivel"] = modulo_f1
    spec.loader.exec_module(modulo_f1)
    return modulo_f1


f1 = _simular_nvda()


class ClienteFalso:
    criados = 0

    def __init__(self, estado, *a, **k):
        self.estado = estado
        ClienteFalso.criados += 1

    def start(self):
        pass

    def parar(self):
        pass


class TestAtivacaoAutomatica(unittest.TestCase):
    LARGADA = datetime.datetime(2026, 10, 4, 7, 0, tzinfo=datetime.timezone.utc)

    def setUp(self):
        f1.f1AoVivo.ClienteLiveTiming = ClienteFalso
        ClienteFalso.criados = 0
        FALAS.clear()
        self.plugin = types.SimpleNamespace()
        for nome in ("_checar_ao_vivo", "ao_vivo_ativo", "iniciar_ao_vivo", "parar_ao_vivo", "_status_ao_vivo"):
            setattr(self.plugin, nome, getattr(f1.GlobalPlugin, nome).__get__(self.plugin))
        self.plugin.fila_avisos = types.SimpleNamespace(adicionar=lambda aviso: None)
        self.plugin._cliente_ao_vivo = None
        self.plugin._ao_vivo_manual = False
        self.plugin._auto_suspenso = False
        self.corrida = {"date": "2026-10-04", "time": "07:00:00Z"}

    def minuto(self, m):
        self.plugin._checar_ao_vivo(self.corrida, self.LARGADA + datetime.timedelta(minutes=m))
        return self.plugin.ao_vivo_ativo()

    def test_liga_na_hora_da_corrida(self):
        self.assertFalse(self.minuto(-30))
        self.assertTrue(self.minuto(-5))
        self.assertTrue(self.minuto(60))
        self.assertEqual(ClienteFalso.criados, 1)
        self.assertFalse(self.minuto(200), "desliga quando o horário da corrida passa")

    def test_desconectar_na_mao_vale_ate_o_fim_da_corrida(self):
        self.minuto(10)
        self.plugin.parar_ao_vivo(manual=True)
        self.assertEqual(FALAS[-1], "Avisos ao vivo desligados. Eles voltam a ligar sozinhos na próxima corrida.")
        self.assertFalse(self.minuto(11))
        self.assertFalse(self.minuto(90))
        self.assertEqual(ClienteFalso.criados, 1)
        self.minuto(200)
        self.corrida = {"date": "2026-10-11", "time": "07:00:00Z"}
        self.assertTrue(self.minuto(7 * 24 * 60), "na corrida seguinte liga de novo")

    def test_sessao_terminada_nao_reconecta(self):
        self.minuto(0)
        self.plugin._estado_ao_vivo.status_sessao = "Finalised"
        self.assertFalse(self.minuto(110))
        self.assertFalse(self.minuto(111))
        self.assertFalse(self.minuto(150))
        self.assertEqual(ClienteFalso.criados, 1)

    def test_conexao_manual_nao_e_desligada_pela_automatica(self):
        self.plugin.iniciar_ao_vivo(manual=True)
        self.assertTrue(self.minuto(60))
        self.plugin._estado_ao_vivo.status_sessao = "Finalised"
        self.assertTrue(self.minuto(110), "quem ligou na mão decide quando desligar")


if __name__ == "__main__":
    unittest.main()
