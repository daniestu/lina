# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S13: dar a un programa más acceso a tu equipo pide «sí» siempre; quitarlo (o volver a lo de fábrica) va sin él y queda en el diario. Qué órdenes
cambian permisos lo dice politica.txt ([permisos_de_apps]); el código solo mira si lo que hacen QUITA o DA, por la forma de sus opciones. Y la respuesta
no da por hecho un cambio que nada ha comprobado. Caso real (medida de A16, 2026-11-21): un `flatpak override` sin preguntar y «He configurado Telegram
para que no arranque», que no era cierto."""
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import efectos as EF
from lina.nucleo import herramientas as H


@pytest.mark.parametrize("comando, quita", [
    ("flatpak override --user --nosocket=session-bus org.ejemplo.App", True),
    ("flatpak override --user --nofilesystem=home --nodevice=all org.ejemplo.App", True),
    ("flatpak override --user --unshare=network org.ejemplo.App", True),
    ("flatpak override --user --no-talk-name=org.ejemplo.Otro org.ejemplo.App", True),
    ("flatpak override --user --reset org.ejemplo.App", True),
    ("flatpak permission-reset org.ejemplo.App", True),
    ("snap disconnect ejemplo:camera", True),
    ("flatpak override --user --filesystem=host org.ejemplo.App", False),
    ("flatpak override --user --talk-name=org.freedesktop.Flatpak org.ejemplo.App", False),
    ("flatpak override --user --env=LD_PRELOAD=/tmp/x.so org.ejemplo.App", False),
    ("flatpak override --user --nosocket=x11 --device=all org.ejemplo.App", False),      # quita una cosa y da otra: da
    ("flatpak permission-set background background org.ejemplo.App yes", False),
    ("snap connect ejemplo:camera", False),
    ("flatpak override --user org.ejemplo.App", False),                                 # no dice qué: se confirma
])
def test_quitar_o_dar_por_la_forma_de_la_orden(comando, quita):
    assert EF.solo_quita_permisos(comando) is quita


def test_el_codigo_no_sabe_de_ningun_programa(monkeypatch):
    """Quitar o dar se decide por la forma de las opciones, sea cual sea el programa (qué programas cambian permisos lo dice politica.txt)."""
    assert EF.solo_quita_permisos("cajita permisos --nored miapp") and not EF.solo_quita_permisos("cajita permisos --red miapp")


def test_dar_permisos_se_confirma_siempre():
    assert "permisos_de_apps" in AJ.SIEMPRE_CONFIRMAN


@pytest.fixture
def ej(monkeypatch):
    e = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    e.ejecutados, e.anotado = [], []
    monkeypatch.setattr(e, "_con_red", lambda comando, motivo, clase: e.ejecutados.append((comando, clase)) or "código de salida: 0 (0 s)\n")
    monkeypatch.setattr(H, "notificar", lambda *a, **k: None)
    monkeypatch.setattr(H, "anotar", e.anotado.append)
    return e


def test_quitar_acceso_va_sin_si_y_queda_apuntado(ej):
    orden = "flatpak override --user --nosocket=session-bus org.ejemplo.App"
    r = ej.herramienta({"comando": orden, "motivo": "quitarle el bus"})
    assert not r.startswith("PREPARADO") and ej.ejecutados == [(orden, "autonomo")]
    assert any(a.startswith("[quita-permisos]") for a in ej.anotado)


def test_dar_acceso_pide_si_y_un_si_anterior_no_lo_cubre(ej):
    orden = "flatpak override --user --filesystem=host org.ejemplo.App"
    assert ej.herramienta({"comando": orden, "motivo": "x"}).startswith("PREPARADO") and not ej.ejecutados
    ej.confirmar_pendientes()
    assert ej.permiso is None or "permisos_de_apps" not in ej.permiso["secciones"]      # lo que se confirma siempre nunca queda cubierto
    assert ej.herramienta({"comando": orden.replace("host", "home"), "motivo": "x"}).startswith("PREPARADO")


def test_tras_leer_de_fuera_tambien_quitar_se_confirma(ej):
    ej.contaminar("página web")
    assert ej.herramienta({"comando": "flatpak override --user --reset org.ejemplo.App", "motivo": "x"}).startswith("PREPARADO")


def test_el_diario_anota_lo_que_quita(monkeypatch):
    """Por el camino de siempre (_con_red): una orden que el código no sabe deshacer se anota igual, sin deshacer automático."""
    e = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    anotadas = []
    monkeypatch.setattr(H.diario, "anotar", lambda entrada: anotadas.append(entrada) or entrada)
    monkeypatch.setattr(e, "ejecutar", lambda comando, motivo="", clase="": "código de salida: 0 (0 s)\n")
    r = e._con_red("flatpak override --user --reset org.ejemplo.App", "volver a lo de fábrica", "autonomo")
    assert anotadas and anotadas[0]["comando"].startswith("flatpak override") and "Anotado en el diario" in r


# ---------------------------------------------------------------- la respuesta no da por hecho lo no comprobado
def test_un_cambio_que_nada_comprueba_queda_marcado(monkeypatch):
    e = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    monkeypatch.setattr(e, "ejecutar", lambda comando, motivo="", clase="": "código de salida: 0 (0 s)\n")
    e._con_red("miprograma --modo silencio", "x", "autonomo")
    assert e.cambio_sin_comprobar is True
    e2 = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    monkeypatch.setattr(e2, "ejecutar", lambda comando, motivo="", clase="": "código de salida: 0 (0 s)\n")
    e2._con_red("ls ~", "x", "lectura")
    assert e2.cambio_sin_comprobar is False


def test_la_respuesta_lo_dice(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[], duda="", efecto_sin_comprobar=False, cambio_sin_comprobar=True)
    a.pregunta_pura, a.acciones_turno = "No quiero que Telegram arranque al iniciar sesión", [("ejecutar_comando", {"comando": "x"}, "código de salida: 0")]
    a._fuentes_antes = None
    monkeypatch.setattr(A.FUE, "firma", lambda: None)
    monkeypatch.setattr(a, "_enlace_sin_comprobar", lambda: None)
    r = a._honestidad_de_lo_hecho("He configurado Telegram para que no arranque.")
    assert "He configurado" not in r and r.startswith("La orden ha salido bien, pero no he podido comprobar")     # S9l: se sustituye, no se añade
