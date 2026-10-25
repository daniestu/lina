# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Alias de voz: la IA solo los lista; apuntarlos y borrarlos lo hace el código ante una frase del usuario, y apuntarlos solo con el atajo."""
import shutil
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import comandos as C
from lina.nucleo import rutas as RUT

A = None


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    """alias.txt y comandos.txt en una carpeta temporal: nada del equipo real."""
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
    monkeypatch.setattr(C, "ARCHIVO_ALIAS", tmp_path / "alias.txt")
    return tmp_path


def _asistente(voz_libre=False, pregunta=""):
    a = A.Asistente.__new__(A.Asistente)
    a.modo_privado = False
    a.origen_voz_libre = voz_libre
    a.pregunta_pura = pregunta
    a.historial = [{"rol": "user", "texto": pregunta}]
    a.dicho = []
    a.decir = a.dicho.append
    a.ejecutor = MagicMock()
    a.responder = MagicMock(side_effect=AssertionError("no debía llamar a la IA"))
    return a


def test_la_ia_no_apunta_aunque_lo_oido_este_en_la_frase(aislado):
    a = _asistente(pregunta="conecta mis auriculares")
    for accion in ("añadir", "anadir", "apuntar"):
        r = a._ejecutar_herramienta("alias_de_voz", {"accion": accion, "oido": "conecta", "significa": "desconecta"})
        assert "No lo apunto" in r, accion
    assert not C.ARCHIVO_ALIAS.exists() and C.listar_alias() == []


def test_la_ia_no_borra_un_alias_del_usuario(aislado):
    assert C.guardar_alias("cait", "Kate")[0]
    a = _asistente(pregunta="olvida lo de cait")
    for accion in ("borrar", "quitar", "olvidar"):
        assert "No lo apunto ni lo borro" in a._ejecutar_herramienta("alias_de_voz", {"accion": accion, "oido": "cait"}), accion
    assert C.listar_alias() == [("cait", "Kate")]


def test_la_ia_si_puede_listarlos(aislado):
    a = _asistente()
    assert "No hay ningún alias" in a._ejecutar_herramienta("alias_de_voz", {"accion": "listar"})
    C.guardar_alias("cait", "Kate")
    assert "«cait» = «Kate»" in a._ejecutar_herramienta("alias_de_voz", {"accion": "listar"})


def test_la_declaracion_solo_ofrece_listar():
    from lina.nucleo import herramientas as H
    decl = next(d for d in H.DECLARACIONES if d["name"] == "alias_de_voz")
    assert decl["parameters"]["properties"]["accion"]["enum"] == ["listar"]
    assert set(decl["parameters"]["properties"]) == {"accion"}


def test_el_usuario_lo_apunta_y_lo_olvida_con_el_atajo_sin_ia(aislado):
    a = _asistente()
    a._atender("Cuando oigas cait quiero decir Kate", 0.0, origen="atajo")
    assert C.listar_alias() == [("cait", "Kate")] and "Apuntado" in a.dicho[-1]
    a._atender("olvida el alias cait", 0.0, origen="atajo")
    assert C.listar_alias() == []
    a.responder.assert_not_called()


def test_por_manos_libres_no_se_apunta_pero_si_se_olvida(aislado):
    a = _asistente(voz_libre=True)
    a._atender("cuando oigas sube quiero decir apaga el equipo", 0.0, origen="voz_libre")
    assert C.listar_alias() == [] and not C.ARCHIVO_ALIAS.exists()
    assert "atajo" in a.dicho[-1]
    C.guardar_alias("cait", "Kate")
    a._atender("olvida el alias cait", 0.0, origen="voz_libre")
    assert C.listar_alias() == []
    a.responder.assert_not_called()
