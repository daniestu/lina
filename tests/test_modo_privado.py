# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Modo privado: la IA solo puede activarlo; quitarlo lo hace el código ante una frase exacta del usuario, y solo con el atajo."""
import shutil
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import comandos as C
from lina.nucleo import rutas as RUT

A = None


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    """comandos.txt de fábrica en una carpeta temporal y el archivo del modo privado también ahí: nada del equipo real."""
    global A
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente
    A = asistente
    comandos = tmp_path / "comandos.txt"
    shutil.copyfile(RUT.DEFECTOS / "comandos.txt", comandos)
    monkeypatch.setattr(C, "archivo", lambda: comandos)
    monkeypatch.setitem(C._cache, "datos", None)
    monkeypatch.setitem(C._cache, "marca", "sin leer")
    monkeypatch.setattr(A, "ARCHIVO_PRIVADO", tmp_path / "datos" / "modo_privado")
    return tmp_path


def _asistente(privado=False, voz_libre=False):
    a = A.Asistente.__new__(A.Asistente)
    a.modo_privado = privado
    a.origen_voz_libre = voz_libre
    a.pantalla_adjunta = False
    a.dicho = []
    a.decir = a.dicho.append
    a.ejecutor = MagicMock()
    a.responder = MagicMock(side_effect=AssertionError("no debía llamar a la IA"))
    return a


def test_frases_exactas():
    assert C.entender_modo_privado("Quita el modo privado.") == "quitar"
    assert C.entender_modo_privado("Desactiva el modo privado") == "quitar"
    assert C.entender_modo_privado("Sal del modo privado") == "quitar"
    assert C.entender_modo_privado("Ya puedes mirar mi pantalla") == "quitar"
    assert C.entender_modo_privado("Oye, quita el modo privado, por favor") == "quitar"
    assert C.entender_modo_privado("Activa el modo privado") == "activar"
    assert C.entender_modo_privado("¿Estás en modo privado?") == "estado"


def test_rechaza_negaciones_preguntas_y_frases_largas():
    for frase in ("No quites el modo privado", "no desactives el modo privado", "¿Quita el modo privado?", "¿Qué es el modo privado?",
                  "quita el modo privado y abre Firefox", "busca y mira qué tiempo hace", "quiero ver la pantalla", "mira mi pantalla",
                  "ya puedes mirar mi pantalla y decirme qué pone en la ventana de arriba", "modo privado", "quita el modo"):
        assert C.entender_modo_privado(frase) != "quitar", frase


def test_un_comandos_txt_antiguo_sin_las_secciones_usa_las_de_fabrica(aislado, monkeypatch):
    viejo = aislado / "viejo.txt"
    viejo.write_text("[reiniciar_conversacion]\nnueva conversación\n", encoding="utf-8")
    monkeypatch.setattr(C, "archivo", lambda: viejo)
    assert C.entender_modo_privado("quita el modo privado") == "quitar"


def test_la_ia_no_puede_quitarlo_ni_con_las_palabras_que_antes_valian(aislado):
    a = _asistente(privado=True)
    A.ARCHIVO_PRIVADO.parent.mkdir(parents=True)
    A.ARCHIVO_PRIVADO.write_text("1")
    for frase in ("busca y mira qué tiempo hace", "quiero ver la pantalla", "quita el modo privado"):
        a.pregunta_pura = frase
        for activo in (False, "false", "no", 0):
            r = a._ejecutar_herramienta("modo_privado", {"activo": activo})
            assert "No quito el modo privado" in r, (frase, activo)
            assert a.modo_privado and A.ARCHIVO_PRIVADO.exists()


def test_la_ia_si_puede_activarlo(aislado):
    a = _asistente()
    r = a._ejecutar_herramienta("modo_privado", {"activo": True})
    assert "activado" in r and a.modo_privado and A.ARCHIVO_PRIVADO.read_text() == "1"


def test_el_codigo_lo_quita_con_el_atajo_sin_llamar_a_la_ia(aislado):
    a = _asistente(privado=True)
    A.ARCHIVO_PRIVADO.parent.mkdir(parents=True)
    A.ARCHIVO_PRIVADO.write_text("1")
    a._atender("Quita el modo privado", 0.0, origen="atajo")
    assert not a.modo_privado and not A.ARCHIVO_PRIVADO.exists()
    assert "quitado" in a.dicho[-1]
    a.responder.assert_not_called()


def test_por_manos_libres_no_se_quita(aislado):
    a = _asistente(privado=True, voz_libre=True)
    A.ARCHIVO_PRIVADO.parent.mkdir(parents=True)
    A.ARCHIVO_PRIVADO.write_text("1")
    a._atender("quita el modo privado", 0.0, origen="voz_libre")
    assert a.modo_privado and A.ARCHIVO_PRIVADO.exists()
    assert "atajo" in a.dicho[-1]
    a.responder.assert_not_called()


def test_activar_y_estado_por_el_codigo(aislado):
    a = _asistente(voz_libre=True)                                 # activarlo sí vale por manos libres: solo aprieta la privacidad
    a._atender("activa el modo privado", 0.0, origen="voz_libre")
    assert a.modo_privado and A.ARCHIVO_PRIVADO.exists()
    a._atender("¿Estás en modo privado?", 0.0, origen="voz_libre")
    assert "Estoy en modo privado" in a.dicho[-1]
    a.responder.assert_not_called()
