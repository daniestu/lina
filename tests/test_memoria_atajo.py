# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Memoria de preferencias por voz: «recuerda que…» solo con el atajo; olvidar y «¿qué recuerdas de mí?» también por manos libres."""
import shutil
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import comandos as C
from lina.nucleo import memoria as M
from lina.nucleo import rutas as RUT

A = None


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    """memoria.json y comandos.txt en una carpeta temporal: nada del equipo real."""
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
    monkeypatch.setattr(M, "ARCHIVO", tmp_path / "memoria.json")
    return tmp_path


def _asistente(voz_libre):
    a = A.Asistente.__new__(A.Asistente)
    a.modo_privado = False
    a.origen_voz_libre = voz_libre
    a.dicho = []
    a.decir = a.dicho.append
    a.ejecutor = MagicMock()
    a.responder = MagicMock(side_effect=AssertionError("no debía llamar a la IA"))
    return a


def _textos():
    return [r["texto"] for r in M._cargar()]


def test_por_manos_libres_no_se_apunta():
    a = _asistente(voz_libre=True)
    a._atender("Recuerda que mi navegador favorito es Brave", 0.0)
    assert _textos() == [] and not M.ARCHIVO.exists()
    assert "atajo" in a.dicho[-1]
    a.responder.assert_not_called()


def test_con_el_atajo_se_apunta():
    a = _asistente(voz_libre=False)
    a._atender("Recuerda que mi navegador favorito es Brave", 0.0)
    assert _textos() == ["mi navegador favorito es Brave"]
    a.responder.assert_not_called()


def test_olvidar_y_listar_tambien_por_manos_libres():
    assert M.recordar("mi navegador favorito es Brave")[0]
    a = _asistente(voz_libre=True)
    a._atender("¿Qué recuerdas de mí?", 0.0)
    assert "Brave" in a.dicho[-1]
    a._atender("Olvida lo de Brave", 0.0)
    assert _textos() == []
    a.responder.assert_not_called()
