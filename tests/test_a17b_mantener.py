# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A17b: mantener pulsado. La combinación elegida y el botón Home de los mandos activan a Lina solo si se mantienen `activacion.boton_mantener`
segundos (1 de fábrica); soltar antes no hace nada, y con 0 basta pulsar (Home vuelve a la pulsación corta de siempre). General: códigos y tiempos,
nada de ningún dispositivo. Con dispositivos simulados (FIFO y un mando de evdev falso); nunca uno de verdad."""
import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lina.nucleo import boton as BOT
from test_a17_boton import L3, R3, A, _pulsar, _vigilar, sistema  # noqa: F401  (la fixture)


class Reloj:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_hay_que_mantenerla_el_tiempo_pedido():
    reloj = Reloj()
    c = BOT.Combinacion([L3, R3], mantener=1.0, ahora=reloj)
    assert not c.ver(L3, 1) and not c.ver(R3, 1) and c.falta() == 1.0
    reloj.t += 0.6
    assert not c.vencida() and c.falta() == pytest.approx(0.4)
    reloj.t += 0.4
    assert c.vencida() is True and c.vencida() is False          # una sola vez por pulsación


def test_soltar_antes_no_activa_y_volver_a_empezar_cuenta_de_cero():
    reloj = Reloj()
    c = BOT.Combinacion([L3, R3], mantener=1.0, ahora=reloj)
    c.ver(L3, 1), c.ver(R3, 1)
    reloj.t += 0.8
    c.ver(R3, 0)
    assert c.falta() is None
    c.ver(R3, 1)
    reloj.t += 0.5
    assert not c.vencida()
    reloj.t += 0.5
    assert c.vencida()


def test_exclusivo_otro_boton_a_la_vez_la_anula():
    reloj = Reloj()
    home = BOT.Combinacion([316], mantener=1.0, exclusivo=True, ahora=reloj)
    home.ver(316, 1)
    home.ver(A, 1)                                               # Home + A: un atajo de Steam, no para Lina
    reloj.t += 2
    assert not home.vencida()


def test_con_cero_basta_pulsar():
    c = BOT.Combinacion([L3, R3], mantener=0)
    assert not c.ver(L3, 1) and c.ver(R3, 1) is True


def test_lina_en_marcha_mantenida_si_y_suelta_antes_no(sistema):  # noqa: F811
    pulsado, log = [], []
    ajuste = BOT.escribir_ajuste("1234", "abcd", "Mando de prueba", [L3, R3])
    parar, hilo = _vigilar(sistema, lambda: ajuste, lambda: pulsado.append(1), log, mantener=0.3)
    fd = _pulsar(sistema.mando, [(L3, 1), (R3, 1)])              # suelta antes de tiempo
    time.sleep(0.1)
    os.write(fd, BOT.EVENTO.pack(0, 0, BOT.EV_KEY, R3, 0) + BOT.EVENTO.pack(0, 0, BOT.EV_KEY, L3, 0))
    time.sleep(0.5)
    assert pulsado == []
    os.write(fd, BOT.EVENTO.pack(0, 0, BOT.EV_KEY, L3, 1) + BOT.EVENTO.pack(0, 0, BOT.EV_KEY, R3, 1))   # y ahora la mantiene
    time.sleep(0.6)
    parar.set()
    hilo.join(2)
    os.close(fd)
    assert pulsado == [1] and log.count("Botón de activación pulsado") == 1


def test_el_asistente_no_acepta_un_tiempo_que_no_vale(sistema, monkeypatch):  # noqa: F811
    assert BOT._segundos("", 1.0) == 1.0 and BOT._segundos("0", 1.0) == 0 and BOT._segundos("2,5 s", 1.0) == 2.5
    assert BOT._segundos("9", 1.0) is None and BOT._segundos("mucho", 1.0) is None


# ---------------------------------------------------------------- el botón Home, con un mando de evdev simulado
class Mando:
    def __init__(self, eventos):
        self.path, self.name, self.eventos = "/dev/input/event-prueba", "Mando de prueba", eventos

    def capabilities(self):
        from evdev import ecodes
        return {ecodes.EV_KEY: [ecodes.BTN_MODE, ecodes.BTN_SOUTH]}

    def read_loop(self):
        for espera, tipo, codigo, valor in self.eventos:
            time.sleep(espera)
            yield SimpleNamespace(type=tipo, code=codigo, value=valor)
        time.sleep(5)                                            # el mando sigue conectado, quieto

    def close(self):
        pass


def _home(monkeypatch, eventos, mantener):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    evdev = pytest.importorskip("evdev")
    from lina.nucleo import asistente as A
    mando = Mando(eventos)
    monkeypatch.setattr(A, "evdev", SimpleNamespace(list_devices=lambda: [mando.path], InputDevice=lambda ruta: mando))
    monkeypatch.setattr(A, "ecodes", evdev.ecodes)
    monkeypatch.setattr(A, "log", lambda m: None)
    pulsado = []
    threading.Thread(target=A.escuchar_mandos, args=(lambda: pulsado.append(1),), kwargs={"mantener": lambda: mantener}, daemon=True).start()
    return pulsado, evdev.ecodes


def test_home_mantenido_activa_y_corto_no(monkeypatch):
    from evdev import ecodes as E
    pulsado, _ = _home(monkeypatch, [(0.05, E.EV_KEY, E.BTN_MODE, 1), (0.1, E.EV_KEY, E.BTN_MODE, 0),        # corto: con 0,3 s no vale
                                     (0.05, E.EV_KEY, E.BTN_MODE, 1), (0.5, E.EV_KEY, E.BTN_MODE, 0)], 0.3)   # mantenido: sí
    time.sleep(1.0)
    assert pulsado == [1]


def test_home_con_cero_es_la_pulsacion_corta_de_siempre(monkeypatch):
    from evdev import ecodes as E
    pulsado, _ = _home(monkeypatch, [(0.05, E.EV_KEY, E.BTN_MODE, 1), (0.1, E.EV_KEY, E.BTN_MODE, 0)], 0)
    time.sleep(0.5)
    assert pulsado == [1]


def test_home_con_otro_boton_no_activa(monkeypatch):
    from evdev import ecodes as E
    pulsado, _ = _home(monkeypatch, [(0.05, E.EV_KEY, E.BTN_MODE, 1), (0.05, E.EV_KEY, E.BTN_SOUTH, 1), (0.5, E.EV_KEY, E.BTN_MODE, 0)], 0.3)
    time.sleep(1.0)
    assert pulsado == []
