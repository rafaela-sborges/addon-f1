# -*- coding: UTF-8 -*-
# Testes dos avisos da corrida (addon/globalPlugins/f1AoVivo.py), fora do NVDA.
# As mensagens seguem o formato real do live timing da F1, copiadas de corridas de 2026.
# Rodar da raiz do projeto: python -m unittest discover -s tests

import datetime
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins"))
import f1AoVivo as av  # noqa: E402

PILOTOS = {
    "1": {"RacingNumber": "1", "FullName": "Lando NORRIS", "Tla": "NOR", "TeamName": "McLaren"},
    "3": {"RacingNumber": "3", "FullName": "Max VERSTAPPEN", "Tla": "VER", "TeamName": "Red Bull Racing"},
    "12": {"RacingNumber": "12", "FullName": "Kimi ANTONELLI", "Tla": "ANT", "TeamName": "Mercedes"},
    "44": {"RacingNumber": "44", "FullName": "Lewis HAMILTON", "Tla": "HAM", "TeamName": "Ferrari"},
    "55": {"RacingNumber": "55", "FullName": "Carlos SAINZ", "Tla": "SAI", "TeamName": "Williams"},
    "22": {"RacingNumber": "22", "FullName": "Yuki TSUNODA", "Tla": "TSU", "TeamName": "Red Bull Racing"},
}
T0 = datetime.datetime(2026, 9, 13, 13, 0, tzinfo=datetime.timezone.utc)


def seg(n):
    return T0 + datetime.timedelta(seconds=n)


def pilotos():
    p = av.Pilotos()
    p.atualizar(PILOTOS)
    return p


def classificar(texto, categoria="Other", bandeira=None, escopo=None, setor=None):
    msg = {"Utc": "2026-09-13T13:09:49", "Lap": 4, "Category": categoria, "Message": texto}
    if bandeira:
        msg["Flag"] = bandeira
    if escopo:
        msg["Scope"] = escopo
    if setor:
        msg["Sector"] = setor
    return av.classificar_direcao_de_prova(msg, pilotos())


class TestPilotos(unittest.TestCase):
    def test_nome_legivel(self):
        self.assertEqual(pilotos().nome(3), "Max Verstappen")

    def test_numero_desconhecido(self):
        self.assertEqual(pilotos().nome(99), "carro 99")


class TestDirecaoDeProva(unittest.TestCase):
    def test_largada(self):
        aviso = classificar("RACE START")
        self.assertEqual((aviso.tipo, aviso.texto), (av.TIPO_CORRIDA, "Largada!"))

    def test_safety_car(self):
        aviso = classificar("SAFETY CAR DEPLOYED", categoria="SafetyCar")
        self.assertEqual((aviso.tipo, aviso.texto, aviso.prioridade), (av.TIPO_SAFETY_CAR, "Safety car na pista!", True))
        self.assertEqual(classificar("SAFETY CAR IN THIS LAP", categoria="SafetyCar").texto, "Safety car recolhe nesta volta: a corrida vai ser retomada.")

    def test_safety_car_virtual_vem_como_vsc(self):
        self.assertEqual(classificar("VSC DEPLOYED", categoria="SafetyCar").texto, "Safety car virtual acionado.")
        self.assertEqual(classificar("VSC ENDING", categoria="SafetyCar").texto, "Safety car virtual terminando: a corrida vai ser retomada.")

    def test_bandeiras(self):
        vermelha = classificar("RED FLAG", categoria="Flag", bandeira="RED", escopo="Track")
        self.assertEqual((vermelha.tipo, vermelha.prioridade), (av.TIPO_BANDEIRA, True))
        amarela = classificar("YELLOW IN TRACK SECTOR 23", categoria="Flag", bandeira="YELLOW", escopo="Sector", setor=23)
        self.assertEqual(amarela.texto, "Bandeira amarela.")
        self.assertEqual(classificar("DOUBLE YELLOW IN TRACK SECTOR 5", categoria="Flag", bandeira="DOUBLE YELLOW", escopo="Sector", setor=5).texto,
                         "Bandeira amarela dupla.")
        self.assertEqual(classificar("TRACK CLEAR", categoria="Flag", bandeira="CLEAR", escopo="Track").texto, "Bandeira verde, pista liberada.")
        self.assertIsNone(classificar("CLEAR IN TRACK SECTOR 7", categoria="Flag", bandeira="CLEAR", escopo="Sector", setor=7))
        self.assertIsNone(classificar("GREEN LIGHT - PIT EXIT OPEN", categoria="Flag", bandeira="GREEN", escopo="Track"))

    def test_quadriculada(self):
        self.assertEqual(classificar("CHEQUERED FLAG", categoria="Flag", bandeira="CHEQUERED", escopo="Track").tipo, av.TIPO_CORRIDA)

    def test_bandeira_azul_e_preta_e_branca(self):
        azul = classificar("WAVED BLUE FLAG FOR CAR 44 (HAM) TIMED AT 13:10:12", categoria="Flag", bandeira="BLUE", escopo="Driver")
        self.assertEqual((azul.tipo, azul.texto), (av.TIPO_BANDEIRA_AZUL, "Bandeira azul para Lewis Hamilton."))
        pb = classificar("BLACK AND WHITE FLAG FOR CAR 44 (HAM) - TRACK LIMITS", categoria="Flag", bandeira="BLACK AND WHITE", escopo="Driver")
        self.assertEqual((pb.tipo, pb.texto), (av.TIPO_PUNICAO, "Bandeira preta e branca para Lewis Hamilton."))

    def test_batida_so_no_noted(self):
        toque = classificar("TURN 1 INCIDENT INVOLVING CARS 55 (SAI) AND 22 (TSU) NOTED - CAUSING A COLLISION (15:04:12)")
        self.assertEqual((toque.tipo, toque.texto), (av.TIPO_INCIDENTE, "Toque entre Carlos Sainz e Yuki Tsunoda."))
        self.assertIsNone(classificar("FIA STEWARDS: TURN 1 INCIDENT INVOLVING CARS 55 (SAI) AND 22 (TSU) REVIEWED NO FURTHER INVESTIGATION - CAUSING A COLLISION (15:04:12)"))
        self.assertIsNone(classificar("FIA STEWARDS: TURN 5 INCIDENT INVOLVING CARS 55 (SAI) AND 22 (TSU) UNDER INVESTIGATION (15:23:42)"))

    def test_incidente_de_dois_carros_sem_motivo(self):
        aviso = classificar("TURN 5 INCIDENT INVOLVING CARS 55 (SAI) AND 22 (TSU) NOTED (15:23:42)")
        self.assertEqual((aviso.tipo, aviso.texto), (av.TIPO_INCIDENTE, "Incidente entre Carlos Sainz e Yuki Tsunoda."))

    def test_infracao_vira_investigacao(self):
        aviso = classificar("TURN 1 INCIDENT INVOLVING CAR 3 (VER) NOTED - LEAVING THE TRACK AND GAINING AN ADVANTAGE (15:04:12)")
        self.assertEqual((aviso.tipo, aviso.texto), (av.TIPO_PUNICAO, "Comissários analisam Max Verstappen."))

    def test_punicoes(self):
        aviso = classificar("FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 55 (SAI) (15:23:42)")
        self.assertEqual((aviso.tipo, aviso.texto), (av.TIPO_PUNICAO, "Carlos Sainz punido em 5 segundos."))
        self.assertIsNone(classificar("FIA STEWARDS: PENALTY SERVED - 5 SECOND TIME PENALTY FOR CAR 55 (SAI) (15:23:42)"))
        self.assertEqual(classificar("FIA STEWARDS: DRIVE THROUGH PENALTY FOR CAR 44 (HAM)").texto, "Lewis Hamilton recebeu drive-through.")

    def test_mensagens_sem_interesse(self):
        for texto in ("CAR 44 (HAM) TIME 1:43.055 DELETED - TRACK LIMITS AT TURN 1 LAP 4 15:09:18", "RISK OF RAIN FOR THE F1 RACE IS 0%",
                      "OVERTAKE ENABLED", "PIT EXIT CLOSED", "MARSHALS ON TRACK AT TURN 20"):
            self.assertIsNone(classificar(texto), texto)


def linhas(**carros):
    return {"Lines": {numero: campos for numero, campos in carros.items()}}


class TestEstadoCorrida(unittest.TestCase):
    def estado_largado(self, alcance=av.ULTRAPASSAGENS_TODAS):
        """Corrida já na volta 3, com Norris, Verstappen, Antonelli e Hamilton nessa ordem."""
        estado = av.EstadoCorrida(alcance)
        estado.aplicar("DriverList", PILOTOS, seg(0), silencioso=True)
        estado.aplicar("SessionStatus", {"Status": "Started"}, seg(0), silencioso=True)
        estado.aplicar("LapCount", {"CurrentLap": 3, "TotalLaps": 57}, seg(0), silencioso=True)
        grid = {"1": "1", "3": "2", "12": "3", "44": "4"}
        estado.aplicar("TimingData", {"Lines": {n: {"Position": p, "InPit": False, "PitOut": False, "Retired": False, "Stopped": False}
                                                for n, p in grid.items()}}, seg(0), silencioso=True)
        estado.avaliar_posicoes(seg(5), forcar=True)
        return estado

    def trocar(self, estado, instante, **posicoes):
        # As duas posições chegam em mensagens separadas, como no feed.
        for numero, posicao in posicoes.items():
            estado.aplicar("TimingData", {"Lines": {numero.lstrip("c"): {"Position": str(posicao)}}}, instante)

    def test_ultrapassagem_espera_as_posicoes_fecharem(self):
        estado = self.estado_largado()
        self.trocar(estado, seg(10), c12="2")
        self.assertEqual(estado.avaliar_posicoes(seg(10.5)), [], "com duas posições iguais nada é lido")
        self.trocar(estado, seg(10.2), c3="3")
        self.assertEqual(estado.avaliar_posicoes(seg(10.6)), [], "ainda dentro da espera")
        avisos = estado.avaliar_posicoes(seg(12))
        self.assertEqual([a.texto for a in avisos], ["Kimi Antonelli passa Max Verstappen e sobe para 2º."])

    def test_troca_de_lideranca_tem_prioridade(self):
        estado = self.estado_largado()
        self.trocar(estado, seg(10), c3="1", c1="2")
        aviso = estado.avaliar_posicoes(seg(12))[0]
        self.assertEqual((aviso.texto, aviso.prioridade), ("Max Verstappen passa Lando Norris e assume a liderança!", True))

    def test_alcance(self):
        estado = self.estado_largado(av.ULTRAPASSAGENS_LIDERANCA)
        self.trocar(estado, seg(10), c44="3", c12="4")
        self.assertEqual(estado.avaliar_posicoes(seg(12)), [])

    def test_troca_pelos_boxes_nao_e_ultrapassagem(self):
        estado = self.estado_largado()
        avisos = estado.aplicar("TimingData", linhas(**{"3": {"InPit": True}}), seg(10))
        self.assertEqual([a.texto for a in avisos], ["Max Verstappen foi para os boxes."])
        self.trocar(estado, seg(20), c12="2", c44="3", c3="4")
        self.assertEqual(estado.avaliar_posicoes(seg(25)), [])

    def test_sem_ultrapassagem_com_safety_car_ou_na_primeira_volta(self):
        estado = self.estado_largado()
        estado.aplicar("TrackStatus", {"Status": "4", "Message": "SCDeployed"}, seg(8))
        self.trocar(estado, seg(10), c12="2", c3="3")
        self.assertEqual(estado.avaliar_posicoes(seg(12)), [])
        estado = self.estado_largado()
        estado.volta_atual = 1
        self.trocar(estado, seg(10), c12="2", c3="3")
        self.assertEqual(estado.avaliar_posicoes(seg(12)), [])

    def test_resumo_da_primeira_volta(self):
        estado = self.estado_largado()
        estado.volta_atual = 1
        avisos = estado.aplicar("LapCount", {"CurrentLap": 2}, seg(90))
        self.assertEqual([a.texto for a in avisos], ["Fim da primeira volta: Lando Norris lidera, seguido de Max Verstappen e Kimi Antonelli."])

    def test_ultima_volta(self):
        estado = self.estado_largado()
        avisos = estado.aplicar("LapCount", {"CurrentLap": 57}, seg(90))
        self.assertEqual([(a.tipo, a.texto) for a in avisos], [(av.TIPO_CORRIDA, "Última volta!")])

    def test_abandono_e_carro_parado(self):
        estado = self.estado_largado()
        parado = estado.aplicar("TimingData", linhas(**{"44": {"Stopped": True}}), seg(30))
        self.assertEqual([a.texto for a in parado], ["Lewis Hamilton parou na pista."])
        abandono = estado.aplicar("TimingData", linhas(**{"44": {"Retired": True}}), seg(40))
        self.assertEqual([a.texto for a in abandono], ["Lewis Hamilton abandonou a corrida."])

    def test_carro_caindo_pelo_pelotao_vira_um_aviso(self):
        estado = self.estado_largado()
        estado.aplicar("DriverList", {"55": PILOTOS["55"], "22": PILOTOS["22"]}, seg(0), silencioso=True)
        estado.aplicar("TimingData", linhas(**{"55": {"Position": "5", "InPit": False}, "22": {"Position": "6", "InPit": False}}), seg(1), silencioso=True)
        estado.avaliar_posicoes(seg(5), forcar=True)
        textos = []
        # Norris cai de 1º para 5º, um carro de cada vez.
        ordem = [("3", "12", "44", "1", "55"), ("3", "12", "44", "55", "1"), ("3", "12", "44", "55", "22", "1")]
        t = 10
        self.trocar(estado, seg(t), c3="1", c1="2"); textos += [a.texto for a in estado.avaliar_posicoes(seg(t + 2))]; t += 10
        self.trocar(estado, seg(t), c12="2", c1="3"); textos += [a.texto for a in estado.avaliar_posicoes(seg(t + 2))]; t += 10
        self.trocar(estado, seg(t), c44="3", c1="4"); textos += [a.texto for a in estado.avaliar_posicoes(seg(t + 2))]; t += 10
        self.trocar(estado, seg(t), c55="4", c1="5"); textos += [a.texto for a in estado.avaliar_posicoes(seg(t + 2))]
        self.assertEqual(textos, [
            "Max Verstappen passa Lando Norris e assume a liderança!",
            "Kimi Antonelli passa Lando Norris e sobe para 2º.",
            "Lando Norris está perdendo várias posições, agora em 4º.",
        ])

    def test_depois_da_quadriculada(self):
        estado = self.estado_largado()
        mensagens = {"Messages": {"1": {"Utc": "2026-09-13T14:38:28", "Category": "Flag", "Flag": "CHEQUERED", "Scope": "Track", "Message": "CHEQUERED FLAG"},
                                  "2": {"Utc": "2026-09-13T14:47:33", "Category": "Flag", "Flag": "YELLOW", "Scope": "Sector", "Sector": 3, "Message": "YELLOW IN TRACK SECTOR 3"},
                                  "3": {"Utc": "2026-09-13T14:43:38", "Category": "Other", "Message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 44 (HAM)"}}}
        avisos = estado.aplicar("RaceControlMessages", mensagens, seg(100))
        self.assertEqual([a.texto for a in avisos], ["Bandeira quadriculada!", "Lewis Hamilton punido em 5 segundos."])
        self.trocar(estado, seg(110), c12="2", c3="3")
        self.assertEqual(estado.avaliar_posicoes(seg(120)), [])

    def test_amarelas_com_safety_car_ficam_caladas(self):
        # Sequência real de Baku, 26/09/2026: a batida, o safety car e o guincho.
        estado = self.estado_largado()
        def rc(i, hora, texto, categoria="Other", bandeira=None, escopo=None, setor=None):
            m = {"Utc": f"2026-09-26T{hora}", "Category": categoria, "Message": texto}
            if bandeira:
                m.update({"Flag": bandeira, "Scope": escopo, "Sector": setor})
            return {"Messages": {str(i): m}}
        falas = []
        falas += estado.aplicar("RaceControlMessages", rc(1, "11:57:46", "DOUBLE YELLOW IN TRACK SECTOR 7", "Flag", "DOUBLE YELLOW", "Sector", 7), seg(10))
        falas += estado.aplicar("RaceControlMessages", rc(2, "11:57:46", "YELLOW IN TRACK SECTOR 6", "Flag", "YELLOW", "Sector", 6), seg(10.1))
        falas += estado.aplicar("RaceControlMessages", rc(3, "11:58:05", "SAFETY CAR DEPLOYED", "SafetyCar"), seg(30))
        falas += estado.aplicar("RaceControlMessages", rc(4, "12:01:22", "RECOVERY VEHICLE ON TRACK AT TURN 6"), seg(200))
        falas += estado.aplicar("RaceControlMessages", rc(5, "12:01:49", "DOUBLE YELLOW IN TRACK SECTOR 10", "Flag", "DOUBLE YELLOW", "Sector", 10), seg(230))
        falas += estado.aplicar("RaceControlMessages", rc(6, "12:01:49", "YELLOW IN TRACK SECTOR 9", "Flag", "YELLOW", "Sector", 9), seg(230.1))
        falas += estado.aplicar("RaceControlMessages", rc(7, "12:09:15", "SAFETY CAR IN THIS LAP", "SafetyCar"), seg(600))
        falas += estado.aplicar("RaceControlMessages", rc(8, "12:11:14", "TRACK CLEAR", "Flag", "CLEAR", "Track"), seg(720))
        falas += estado.aplicar("RaceControlMessages", rc(9, "12:11:36", "DOUBLE YELLOW IN TRACK SECTOR 2", "Flag", "DOUBLE YELLOW", "Sector", 2), seg(740))
        self.assertEqual([a.texto for a in falas], [
            "Bandeira amarela dupla.",
            "Safety car na pista!",
            "Veículo de resgate na pista, curva 6.",
            "Safety car recolhe nesta volta: a corrida vai ser retomada.",
            "Pista liberada, corrida retomada!",
            "Bandeira amarela dupla.",
        ])

    def test_amarela_dupla_e_simples_juntas_viram_um_aviso(self):
        estado = self.estado_largado()
        juntas = {"Messages": {
            "1": {"Utc": "2026-09-26T12:10:00", "Category": "Flag", "Flag": "DOUBLE YELLOW", "Scope": "Sector", "Sector": 3, "Message": "DOUBLE YELLOW IN TRACK SECTOR 3"},
            "2": {"Utc": "2026-09-26T12:10:00", "Category": "Flag", "Flag": "YELLOW", "Scope": "Sector", "Sector": 2, "Message": "YELLOW IN TRACK SECTOR 2"}}}
        self.assertEqual([a.texto for a in estado.aplicar("RaceControlMessages", juntas, seg(10))], ["Bandeira amarela dupla."])

    def test_retrato_inicial_nao_anuncia_o_passado(self):
        estado = av.EstadoCorrida()
        velhas = {"Messages": [{"Utc": "2026-09-13T13:04:04", "Category": "Other", "Message": "RACE START"}]}
        self.assertEqual(estado.aplicar("RaceControlMessages", velhas, seg(0), silencioso=True), [])
        # A mesma mensagem chegando de novo numa atualização também não é repetida.
        self.assertEqual(estado.aplicar("RaceControlMessages", {"Messages": {"0": velhas["Messages"][0]}}, seg(1)), [])


class TestFiltroEArquivo(unittest.TestCase):
    def test_filtro(self):
        avisos = [av.Aviso(None, av.TIPO_SAFETY_CAR, "sc"), av.Aviso(None, av.TIPO_PIT, "pit"), av.Aviso(None, av.TIPO_CORRIDA, "largada")]
        self.assertEqual([a.texto for a in av.filtrar_por_preferencia(avisos, {av.TIPO_SAFETY_CAR: True})], ["sc", "largada"])

    def test_json_stream_e_inicio(self):
        textos = {
            "SessionStatus": "﻿00:00:04.188{\"Status\":\"Inactive\"}\r\n00:58:13.809{\"Status\":\"Started\"}\r\n",
            "LapCount": "00:01:14.590{\"CurrentLap\":1,\"TotalLaps\":57}\r\nlixo\r\n",
        }
        eventos = av.montar_eventos(textos)
        self.assertEqual([(round(d, 3), t) for d, t, _dados in eventos], [(4.188, "SessionStatus"), (74.59, "LapCount"), (3493.809, "SessionStatus")])
        self.assertAlmostEqual(av.inicio_da_corrida(eventos), 3493.809)


class TestIndice(unittest.TestCase):
    INDICE = {"Meetings": [
        {"Name": "Spanish Grand Prix", "Sessions": [
            {"Type": "Qualifying", "Name": "Qualifying", "StartDate": "2026-09-12T16:00:00", "GmtOffset": "02:00:00", "Path": "q/"},
            {"Type": "Race", "Name": "Race", "StartDate": "2026-09-13T15:00:00", "EndDate": "2026-09-13T17:00:00", "GmtOffset": "02:00:00", "Path": "espanha/"}]},
        {"Name": "Azerbaijan Grand Prix", "Sessions": [
            {"Type": "Race", "Name": "Race", "StartDate": "2026-09-26T15:00:00", "EndDate": "2026-09-26T17:00:00", "GmtOffset": "04:00:00", "Path": None}]},
    ]}

    def test_corrida_em_andamento_vem_primeiro_e_sem_caminho(self):
        # 15h em Baku (UTC+4) são 11h UTC.
        durante = datetime.datetime(2026, 9, 26, 11, 50, tzinfo=datetime.timezone.utc)
        sessoes = av.sessoes_do_indice(self.INDICE, durante)
        self.assertEqual(sessoes, [(None, "Azerbaijan Grand Prix - Corrida (ao vivo agora)"), ("espanha/", "Spanish Grand Prix - Corrida (2026-09-13)")])

    def test_fora_do_horario_a_corrida_sem_gravacao_nao_aparece(self):
        antes = datetime.datetime(2026, 9, 26, 10, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual([c for c, _n in av.sessoes_do_indice(self.INDICE, antes)], ["espanha/"])
        comecando = datetime.datetime(2026, 9, 26, 10, 50, tzinfo=datetime.timezone.utc)
        self.assertEqual([c for c, _n in av.sessoes_do_indice(self.INDICE, comecando)], [None, "espanha/"])


class TestReplayECliente(unittest.TestCase):
    def test_replay_monta_em_silencio_e_avisa_depois_da_largada(self):
        textos = {
            "DriverList": "00:00:01.000" + '{"44": {"FullName": "Lewis HAMILTON"}}',
            "SessionStatus": "00:00:02.000{\"Status\":\"Started\"}",
            "RaceControlMessages": "00:00:00.500{\"Messages\":[{\"Utc\":\"2026-09-13T12:20:01\",\"Category\":\"Other\",\"Message\":\"RACE START\"}]}\n"
                                   "00:00:03.000{\"Messages\":{\"1\":{\"Utc\":\"2026-09-13T13:04:04\",\"Category\":\"Other\",\"Message\":\"CAR 44 (HAM) STOPPED\"}}}",
        }
        eventos = av.montar_eventos(textos)
        falados, motivo, fim = [], [], threading.Event()
        replay = av.Replay(eventos, av.EstadoCorrida(), 1000, lambda a: falados.append(a.texto),
                           lambda m: (motivo.append(m), fim.set()), antecedencia=0.5)
        replay.start()
        self.assertTrue(fim.wait(5))
        self.assertEqual((falados, motivo), (["Lewis Hamilton parou na pista."], ["fim"]))

    def test_replay_pode_parar(self):
        textos = {"SessionStatus": "00:00:01.000{\"Status\":\"Started\"}\n01:00:00.000{\"Status\":\"Finished\"}"}
        fim, motivo = threading.Event(), []
        replay = av.Replay(av.montar_eventos(textos), av.EstadoCorrida(), 1, lambda a: None, lambda m: (motivo.append(m), fim.set()))
        replay.start()
        replay.parar()
        self.assertTrue(fim.wait(5))
        self.assertEqual(motivo, ["parado"])

    def test_cliente_trata_retrato_e_atualizacao(self):
        falados = []
        cliente = av.ClienteLiveTiming(av.EstadoCorrida(), lambda a: falados.append(a.texto))
        retrato = {"type": 3, "invocationId": "1", "result": {
            "DriverList": PILOTOS, "SessionStatus": {"Status": "Started"},
            "RaceControlMessages": {"Messages": [{"Utc": "2026-09-26T11:03:51", "Category": "Other", "Message": "RACE START"}]}}}
        cliente.tratar(retrato, agora=seg(0))
        self.assertEqual(falados, [], "o retrato do momento da conexão não repete o que já passou")
        atualizacao = {"type": 1, "target": "feed", "arguments": [
            "RaceControlMessages", {"Messages": {"22": {"Utc": "2026-09-26T11:40:00", "Category": "SafetyCar", "Message": "SAFETY CAR DEPLOYED"}}},
            "2026-09-26T11:40:00.123Z"]}
        cliente.tratar(atualizacao, agora=seg(60))
        self.assertEqual(falados, ["Safety car na pista!"])


if __name__ == "__main__":
    unittest.main()
