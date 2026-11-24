# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9g (4): las recetas de pasos llevan el nombre general de R2 y el hueco {valor} que señala la IA (verificado por el código), y «dada por cumplida»
se decide por los hechos del cambio, no por si Gemini contestó al final. Sin IA ni red: la mini-consulta va simulada."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lina.nucleo import asistente_interfaz as AI
from lina.nucleo import recetas as REC

ORDEN = "printf '[Desktop Entry]\\nHidden=true\\n' > ~/.config/autostart/org.kde.kdeconnect.daemon.desktop"


@pytest.fixture
def recetas(tmp_path, monkeypatch):
    monkeypatch.setattr(REC, "ARCHIVO", tmp_path / "recetas.json")
    monkeypatch.setattr(REC, "_en_privado", lambda: False)
    return tmp_path


def test_la_receta_de_pasos_lleva_nombre_general_y_hueco(recetas):
    pasos = [{"herr": "ejecutar_comando", "args": {"comando": ORDEN, "motivo": "ocultarla"}}]
    REC.aprender_pasos("Quita KDE Connect del arranque", pasos, nombre="quitar una app del inicio automático",
                       valor="org.kde.kdeconnect.daemon")
    [r] = REC._cargar()
    assert r["ajuste"] == "quitar una app del inicio automático" and r["valor_usado"] == "org.kde.kdeconnect.daemon"
    assert r["pasos"][0]["args"]["comando"] == ORDEN.replace("org.kde.kdeconnect.daemon", "{valor}")
    assert "{valor} va lo que pida el usuario" in REC._como_se_hace(r)


def test_sin_nombre_general_queda_como_siempre(recetas):
    pasos = [{"herr": "ejecutar_comando", "args": {"comando": ORDEN, "motivo": "ocultarla"}}]
    REC.aprender_pasos("Quita KDE Connect del arranque", pasos, valor="no-esta-en-la-orden")
    [r] = REC._cargar()
    assert r["ajuste"] == "Quita KDE Connect del arranque" and "{valor}" not in r["pasos"][0]["args"]["comando"] and r["valor_usado"] == ""


def _asistente(**ej):
    datos = {"cambio_comprobado": True, "duda": "", "contaminado": "", "recetas_diferidas": []}
    datos.update(ej)
    e = SimpleNamespace(**datos)
    e.guardar_diferidas = MagicMock(return_value=[{"id": "r0001"}])
    return SimpleNamespace(ejecutor=e, modo_privado=False, _peticion_de_receta=lambda: "x")


@pytest.mark.parametrize("cambio, cumplida", [({}, True), ({"cambio_comprobado": False}, False), ({"duda": "algo falló"}, False),
                                              ({"contaminado": "página web"}, False)])
def test_cumplida_por_los_hechos_del_cambio(cambio, cumplida):
    assert AI.cumplida_por_hechos(_asistente(**cambio)) is cumplida
    privado = _asistente(**cambio)
    privado.modo_privado = True
    assert AI.cumplida_por_hechos(privado) is False


def test_por_hechos_se_guarda_aunque_la_respuesta_no_se_diera_por_buena():
    a = _asistente()
    AI.guardar_por_hechos(a, [{"cambiar": ORDEN, "generalizar": True}, {"cambiar": "otra", "ajuste": "de la IA"}])
    a.ejecutor.guardar_diferidas.assert_called_once()
    assert a.ejecutor.recetas_diferidas == []


def test_sin_hechos_se_descarta_como_antes():
    a = _asistente(cambio_comprobado=False)
    AI.guardar_por_hechos(a, [{"cambiar": ORDEN, "generalizar": True}])
    a.ejecutor.guardar_diferidas.assert_not_called()


def test_la_de_pasos_se_aprende_por_hechos_aunque_gemini_no_contestara_y_quede_algo_pendiente(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    aprender = MagicMock(return_value={"id": "r0002"})
    monkeypatch.setattr(REC, "aprender_pasos", aprender)
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = SimpleNamespace(cambio_comprobado=True, duda="", contaminado="", receta_turno=False, pendientes=[{"comando": "otra cosa"}])
    a.modo_privado, a.turno_aceptado, a.insistiendo = False, False, False
    a.acciones_turno = [("ejecutar_comando", {"comando": ORDEN, "motivo": "ocultarla"}, "código de salida: 0 (0 s)\n\n✔ existe el archivo")]
    a._recetas_de_pasos_activas = lambda: True
    a._frase_para_receta = lambda: "Quita KDE Connect del arranque"
    a._generalizar_receta = lambda frase, ordenes: ("quitar una app del inicio automático", "org.kde.kdeconnect.daemon")
    monkeypatch.setattr(A.Asistente, "_REC", lambda self: REC)
    a._aprender_pasos()
    assert aprender.called
    assert aprender.call_args.kwargs == {"nombre": "quitar una app del inicio automático", "valor": "org.kde.kdeconnect.daemon", "atajo": True,
                                        "por_nombrar": False}
    a.ejecutor.cambio_comprobado = False                         # sin el hecho, como antes: hace falta el visto bueno y nada pendiente
    aprender.reset_mock()
    a._aprender_pasos()
    assert not aprender.called
