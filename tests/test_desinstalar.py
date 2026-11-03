# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Bloque B: desinstalar paquetes pide confirmación, aunque el perfil sea autónomo, si el nombre no lo dijiste tú tal cual o si arrastra dependencias.
El caso real: «Quita las fuentes F3 y F4» acabó en «sudo pacman -R --noconfirm ttf-f3 ttf-f4» sin preguntar. Sin ejecutar nada."""
from unittest.mock import MagicMock

import pytest

from lina.nucleo import herramientas as H


@pytest.mark.parametrize("comando, peticion", [
    ("sudo pacman -R --noconfirm ttf-f3 ttf-f4", "Quita las fuentes F3 y F4"),
    ("sudo pacman -Rns vlc gimp", "desinstala vlc"),
    ("flatpak uninstall org.videolan.VLC", "quita vlc"),
    ("sudo apt purge libreoffice-core", "quita libreoffice"),
    ("sudo dnf remove gimp", ""),
    ("sudo zypper rm vlc", "quita el reproductor"),
    ("snap remove firefox", "quita el navegador"),
])
def test_sin_nombrarlo_tal_cual_pide_confirmacion(comando, peticion):
    assert "pide confirmación" in H.desinstala_sin_nombrar(comando, peticion)


@pytest.mark.parametrize("comando", ["sudo pacman -Rdd vlc", "sudo pacman -Rc vlc", "sudo pacman -Rnsc vlc", "sudo rpm -e --nodeps vlc"])
def test_arrastrar_o_romper_dependencias_pide_confirmacion_siempre(comando):
    assert "dependencias" in (H.desinstala_sin_nombrar(comando, "desinstala vlc") or "")


@pytest.mark.parametrize("comando, peticion", [
    ("sudo pacman -Rns --noconfirm vlc", "Desinstala VLC, por favor"),
    ("sudo apt remove libreoffice-writer", "quita libreoffice writer"),
    ("sudo dnf remove gimp", "borra el programa GIMP"),
    ("flatpak uninstall -y org.videolan.VLC", "quita org.videolan.VLC"),
    ("sudo pacman -S vlc", "lo que sea"), ("pacman -Qi vlc", ""), ("ls ~", ""),
])
def test_si_lo_nombraste_o_no_es_desinstalar_sigue_como_siempre(comando, peticion):
    assert H.desinstala_sin_nombrar(comando, peticion) is None


def test_en_modo_autonomo_el_caso_real_queda_pendiente_y_no_se_ejecuta(monkeypatch):
    ej = H.Ejecutor(confirmar=True)
    ej.nueva_tarea()
    ej.pregunta_pura = "Quita las fuentes F3 y F4"
    monkeypatch.setattr(H, "clasificar", lambda c: ("autonomo", ""))
    ejecutar = MagicMock(side_effect=AssertionError("no debía ejecutarse"))
    monkeypatch.setattr(ej, "ejecutar", ejecutar)
    monkeypatch.setattr(ej, "_con_red", ejecutar)
    r = ej.herramienta({"comando": "sudo pacman -R --noconfirm ttf-f3 ttf-f4", "motivo": "quitar fuentes"})
    assert ej.pendientes and "ttf-f3" in ej.pendientes[0]["comando"] and "no ha dicho ese nombre" in r


def test_sin_confirmaciones_activadas_no_cambia(monkeypatch):
    ej = H.Ejecutor(confirmar=False)
    ej.nueva_tarea()
    monkeypatch.setattr(H, "clasificar", lambda c: ("autonomo", ""))
    monkeypatch.setattr(ej, "_con_red", MagicMock(return_value="hecho"))
    monkeypatch.setattr(ej, "ejecutar", MagicMock(return_value="hecho"))
    assert ej.herramienta({"comando": "sudo pacman -R ttf-f3", "motivo": "x"}) == "hecho" and not ej.pendientes
