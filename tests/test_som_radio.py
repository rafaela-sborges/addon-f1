import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# To allow importing the addon files
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../addon/globalPlugins')))

# Mock nvwave and ui BEFORE importing f1Acessivel
sys.modules['nvwave'] = MagicMock()
sys.modules['globalPluginHandler'] = MagicMock()
sys.modules['wx'] = MagicMock()
sys.modules['ui'] = MagicMock()
sys.modules['tones'] = MagicMock()
sys.modules['logHandler'] = MagicMock()
sys.modules['addonHandler'] = MagicMock()
sys.modules['gui'] = MagicMock()

# Mock config
mock_config = MagicMock()
mock_config.conf = {"f1Acessivel": {"som_radio": "todos"}}
sys.modules['config'] = mock_config

import f1Acessivel
import f1AoVivo

class TestSomRadio(unittest.TestCase):
    
    def setUp(self):
        # Reset mocks
        sys.modules['nvwave'].playWaveFile.reset_mock()
        sys.modules['ui'].message.reset_mock()
        
    @patch('os.path.exists', return_value=True)
    def test_radio_ao_vivo_modo_todos(self, mock_exists):
        mock_config.conf["f1Acessivel"]["som_radio"] = "todos"
        
        fila = f1Acessivel.FilaDeAvisos()
        aviso = f1AoVivo.Aviso(None, f1AoVivo.TIPO_PIT, "Teste")
        
        # Testar chamada sem wx.CallAfter e wx.CallLater real, mockando eles
        with patch('wx.CallAfter', side_effect=lambda func, *args: func(*args)), \
             patch('wx.CallLater'):
            fila.adicionar(aviso)
            
        sys.modules['nvwave'].playWaveFile.assert_called_once()
        
    @patch('os.path.exists', return_value=True)
    def test_radio_ao_vivo_modo_resultados(self, mock_exists):
        mock_config.conf["f1Acessivel"]["som_radio"] = "resultados"
        
        fila = f1Acessivel.FilaDeAvisos()
        aviso = f1AoVivo.Aviso(None, f1AoVivo.TIPO_PIT, "Teste")
        
        with patch('wx.CallAfter', side_effect=lambda func, *args: func(*args)), \
             patch('wx.CallLater'):
            fila.adicionar(aviso)
            
        # O som NÃO deve tocar porque a conf é "resultados"
        sys.modules['nvwave'].playWaveFile.assert_not_called()
        
    @patch('os.path.exists', return_value=True)
    def test_radio_resultados_modo_todos(self, mock_exists):
        mock_config.conf["f1Acessivel"]["som_radio"] = "todos"
        
        monitor = f1Acessivel.MonitorDeResultados("Corrida", None, "", None, "1")
        corrida_result = {"date": "2026-10-10", "time": "12:00:00Z"}
        
        monitor.anunciar(corrida_result)
        
        sys.modules['nvwave'].playWaveFile.assert_called_once()
        
    @patch('os.path.exists', return_value=True)
    def test_radio_resultados_modo_ao_vivo(self, mock_exists):
        mock_config.conf["f1Acessivel"]["som_radio"] = "ao_vivo"
        
        monitor = f1Acessivel.MonitorDeResultados("Corrida", None, "", None, "1")
        corrida_result = {"date": "2026-10-10", "time": "12:00:00Z"}
        
        monitor.anunciar(corrida_result)
        
        # O som NÃO deve tocar para resultados se está confinado para 'ao_vivo'
        sys.modules['nvwave'].playWaveFile.assert_not_called()

    @patch('os.path.exists', return_value=True)
    def test_radio_modo_nunca(self, mock_exists):
        mock_config.conf["f1Acessivel"]["som_radio"] = "nunca"
        
        fila = f1Acessivel.FilaDeAvisos()
        aviso = f1AoVivo.Aviso(None, f1AoVivo.TIPO_PIT, "Teste")
        with patch('wx.CallAfter', side_effect=lambda func, *args: func(*args)), \
             patch('wx.CallLater'):
            fila.adicionar(aviso)
            
        monitor = f1Acessivel.MonitorDeResultados("Corrida", None, "", None, "1")
        corrida_result = {"date": "2026-10-10", "time": "12:00:00Z"}
        monitor.anunciar(corrida_result)
        
        # O som NÃO deve tocar de jeito nenhum
        sys.modules['nvwave'].playWaveFile.assert_not_called()

if __name__ == "__main__":
    unittest.main()
