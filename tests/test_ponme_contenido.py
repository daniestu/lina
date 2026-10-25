# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""«Ponme el partido»: es abrirlo para verlo (en la plataforma oficial), no informar; si solo se informó, el código lo reintenta; al insistir, un nombre
que no existe se trata primero como mal oído («rayador» = «navegador»). HOME aislado; la IA, simulada."""
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import constantes as K
from lina.nucleo import turnos as TU


def test_las_instrucciones_dicen_que_ponme_es_abrirlo_en_la_plataforma_oficial():
    assert "PONGAS un partido" in K.INSTRUCCIONES and "plataforma OFICIAL" in K.INSTRUCCIONES and "emisiones no oficiales" in K.INSTRUCCIONES
    assert "nunca escribes contraseñas" in K.INSTRUCCIONES
    assert "PUT ON a match" in K.INSTRUCCIONES_EN and "OFFICIAL platform" in K.INSTRUCCIONES_EN and "unofficial streams" in K.INSTRUCCIONES_EN


@pytest.mark.parametrize("frase", ["Ponme el partido del Barça contra el Sevilla.", "Pon el partido en el navegador", "ponme el partido en el rayador",
                                   "Abre Steam", "Reproduce el último vídeo de mi canal", "Quiero ver el Clásico"])
def test_pide_accion(frase):
    assert TU.pide_accion(frase), frase


@pytest.mark.parametrize("frase", ["¿A qué hora es el partido?", "¿Dónde echan el Barça - Sevilla?", "Dime quién ganó ayer", "¿Qué tiempo hace?",
                                   "pongamos que sí"])
def test_no_pide_accion(frase):
    assert not TU.pide_accion(frase), frase


def test_solo_se_informo():
    leer = lambda c: c.startswith(("ls", "cat", "xdg-settings get"))
    assert TU.solo_se_informo([("buscar_web", {"consulta": "x"}, "r"), ("mas_herramientas", {}, "r")], leer)
    assert TU.solo_se_informo([("ejecutar_comando", {"comando": "xdg-settings get default-web-browser"}, "r")], leer)
    assert not TU.solo_se_informo([("buscar_web", {}, "r"), ("ejecutar_comando", {"comando": "xdg-open https://www.dazn.com"}, "r")], leer)
    assert not TU.solo_se_informo([("abrir_app", {"nombre": "Brave"}, "r")], leer)


def _asistente(pregunta, acciones, respuesta_a_fondo="Te abro DAZN en Brave."):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock()
    a.ejecutor.duda, a.ejecutor.pendientes, a.ejecutor.recetas_diferidas, a.ejecutor.efecto_sin_comprobar = "", [], [], False
    a.clave, a.pregunta_pura, a.historial, a.acciones_turno = "clave", pregunta, [], acciones
    a.pedir_profundo, a.obstaculo, a.insistiendo, a.pantalla_adjunta = "", "", False, False
    a._cerrar_receta_interfaz = lambda bueno: None
    a._avisar_voz = lambda t: None
    a._acciones_comprobadas = lambda: False
    enviadas = []
    a._gemini = lambda modo, modelo, texto, *x, **k: (enviadas.append(texto), respuesta_a_fondo)[1]
    return A, a, enviadas


def test_si_pidio_ponerlo_y_solo_se_informo_se_reintenta_sin_revisor(monkeypatch):
    A, a, enviadas = _asistente("Ponme el partido del Barça contra el Sevilla.", [("buscar_web", {"consulta": "barça sevilla"}, "…")])
    monkeypatch.setattr(A, "verificar_cumplimiento", MagicMock(side_effect=AssertionError("no hace falta el revisor")))
    r, _ = a._insistir_si_hace_falta("Según Marca, se emite por DAZN a las 21:00.", "m", "rapido", "p", None, [], "s")
    assert r == "Te abro DAZN en Brave." and enviadas
    assert "HICIERAS" in enviadas[0] and "rayador" in enviadas[0]       # y al insistir sabe que un nombre que no existe puede estar mal oído


def test_una_pregunta_con_solo_busqueda_no_se_reintenta(monkeypatch):
    A, a, enviadas = _asistente("¿A qué hora es el partido del Barça?", [("buscar_web", {"consulta": "x"}, "…")])
    monkeypatch.setattr(A, "verificar_cumplimiento", lambda *x, **k: False)
    r, _ = a._insistir_si_hace_falta("Según Marca, a las 21:00.", "m", "rapido", "p", None, [], "s")
    assert r == "Según Marca, a las 21:00." and not enviadas


def test_si_ya_lo_abrio_no_se_reintenta(monkeypatch):
    A, a, enviadas = _asistente("Ponme el partido del Barça", [("buscar_web", {}, "…"), ("ejecutar_comando", {"comando": "xdg-open https://www.dazn.com"}, "código de salida: 0")])
    monkeypatch.setattr(A, "verificar_cumplimiento", lambda *x, **k: False)
    r, _ = a._insistir_si_hace_falta("Te abro DAZN en Brave.", "m", "rapido", "p", None, [], "s")
    assert r == "Te abro DAZN en Brave." and not enviadas


def test_la_pista_de_whisper_lleva_navegador():
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    assert "navegador" in A.prompt_whisper()
