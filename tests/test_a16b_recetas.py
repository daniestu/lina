# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A16b: la receta la apunta el código cuando hay hechos (un cambio que salió bien y se comprobó, en una tarea que costó, también la del «sí»), con un
nombre general y un hueco {valor} que dan la IA y verifica el código; nunca tras leer contenido de fuera ni en modo privado, y sin tu usuario en la orden.
Sin IA ni red: la mini-consulta va simulada, y lo que se ejecuta va en la carpeta personal de la prueba."""
import os
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import herramientas as H

ORDEN = "mkdir -p ~/.config/autostart && printf '[Desktop Entry]\\nHidden=true\\n' > ~/.config/autostart/org.kde.kdeconnect.daemon.desktop"


@pytest.mark.parametrize("orden, esperado", [
    ("cat /casa/u/.config/x", "cat ~/.config/x"),
    ('echo "hola" > "/casa/u/.config/a b.desktop"', 'echo "hola" > "$HOME/.config/a b.desktop"'),
    ("echo 'x' > '/casa/u/.config/x'", "echo 'x' > '/casa/u/.config/x'"),       # entre comillas simples ~ no se expandiría: se deja (y no se guarda)
])
def test_la_orden_sin_tu_usuario(orden, esperado):
    assert H.sin_carpeta_personal(orden, "/casa/u") == esperado


@pytest.fixture
def ej(monkeypatch):
    e = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    monkeypatch.setattr(H, "anotar", lambda m: None)
    monkeypatch.setattr(H.REC, "para_comando", lambda c: None)
    return e


def test_una_tarea_que_costo_deja_la_receta_pendiente_sin_tu_usuario(ej):
    ej.ordenes_peticion = 3
    ej._receta_por_hechos(ORDEN.replace("~", H._HOME), "autonomo", "✔ existe …/org.kde.kdeconnect.daemon.desktop")
    [d] = ej.recetas_diferidas
    assert d["cambiar"] == ORDEN and d["generalizar"] and H._HOME not in d["cambiar"]


def test_lo_confirmado_con_tu_si_va_a_su_propia_lista(ej):
    ej._receta_por_hechos(ORDEN, "confirmado", "✔")
    assert ej.recetas_de_lo_confirmado and not ej.recetas_diferidas


@pytest.mark.parametrize("caso", ["facil", "fuera", "privado", "usuario_en_comillas", "larga"])
def test_cuando_no_queda_receta(ej, caso):
    ej.ordenes_peticion = 3
    orden = ORDEN
    if caso == "facil":
        ej.ordenes_peticion = 1
    elif caso == "fuera":
        ej.contaminar("página web")
    elif caso == "privado":
        ej.en_privado = lambda: True
    elif caso == "usuario_en_comillas":
        orden = f"echo 'x' > '{H._HOME}/.config/autostart/a.desktop'"
    else:
        orden = ORDEN + " #" + "x" * 300
    ej._receta_por_hechos(orden, "autonomo", "✔")
    assert not ej.recetas_diferidas and not ej.recetas_de_lo_confirmado


def test_al_guardarla_lleva_nombre_general_y_hueco_verificado(ej, monkeypatch):
    aprender = MagicMock(return_value={"id": "r0001"})
    monkeypatch.setattr(H.REC, "aprender_comando", aprender)
    ej.generalizar = MagicMock(return_value=("quitar una app del inicio automático", "org.kde.kdeconnect.daemon"))
    ej.recetas_diferidas = [{"cambiar": ORDEN, "comprobar": "✔", "generalizar": True}]
    assert ej.guardar_diferidas("Que KDE Connect no se inicie solo") == [{"id": "r0001"}]
    ajuste, _, _, cambiar, valor, _, _ = aprender.call_args[0]
    assert ajuste == "quitar una app del inicio automático" and valor == "org.kde.kdeconnect.daemon"
    assert cambiar == ORDEN.replace("org.kde.kdeconnect.daemon", "{valor}") and cambiar.replace("{valor}", valor) == ORDEN


def test_los_saltos_de_linea_van_como_simbolo_y_se_explican(ej, monkeypatch):
    aprender = MagicMock(return_value={"id": "r0002"})
    monkeypatch.setattr(H.REC, "aprender_comando", aprender)
    ej.generalizar = MagicMock(return_value=("ocultar una entrada del arranque", ""))
    heredoc = "cat << 'EOF' > ~/.config/autostart/a.desktop\n[Desktop Entry]\nHidden=true\nEOF"
    ej.recetas_diferidas = [{"cambiar": heredoc, "comprobar": "✔", "generalizar": True}]
    ej.guardar_diferidas("x")
    assert aprender.call_args[0][3] == "cat << 'EOF' > ~/.config/autostart/a.desktop ⏎ [Desktop Entry] ⏎ Hidden=true ⏎ EOF"
    from lina.nucleo import recetas as REC
    assert "salto de línea" in REC._como_se_hace({"tipo": "comando", "ajuste": "x", "cambiar": aprender.call_args[0][3], "ultima": "hoy"})


@pytest.mark.parametrize("general", [None, ("", ""), Exception("la IA no responde")])
def test_sin_nombre_general_no_se_guarda(ej, monkeypatch, general):
    aprender = MagicMock()
    monkeypatch.setattr(H.REC, "aprender_comando", aprender)
    ej.generalizar = MagicMock(side_effect=general) if isinstance(general, Exception) else MagicMock(return_value=general)
    ej.recetas_diferidas = [{"cambiar": ORDEN, "comprobar": "✔", "generalizar": True}]
    assert ej.guardar_diferidas("x") == [] and not aprender.called


def test_tras_leer_de_fuera_tampoco_se_guarda_al_final(ej, monkeypatch):
    aprender = MagicMock()
    monkeypatch.setattr(H.REC, "aprender_comando", aprender)
    ej.generalizar = MagicMock(return_value=("x y z", ""))
    ej.recetas_diferidas = [{"cambiar": ORDEN, "comprobar": "✔", "generalizar": True}]
    ej.contaminar("búsqueda web")
    ej.guardar_diferidas("x")
    assert not aprender.called and not ej.generalizar.called


def test_un_cambio_comprobado_cierra_la_duda_y_apunta_la_receta(ej, monkeypatch):
    """De verdad, en la carpeta personal de la prueba: escribe, se comprueba por hechos y queda la receta."""
    monkeypatch.setattr(H, "modo_aislar", lambda: "no")
    ej.duda, ej.ordenes_peticion = "el comando «gio trash …» terminó con error (código 1)", 3
    r = ej._con_red(ORDEN, "que KDE Connect no arranque solo", "autonomo")
    assert H.EJ.salio_bien(r) and ej.duda == ""
    assert ej.recetas_diferidas and ej.recetas_diferidas[0]["cambiar"] == ORDEN
    assert os.path.exists(os.path.join(H._HOME, ".config/autostart/org.kde.kdeconnect.daemon.desktop"))


def test_lo_de_tu_si_pasa_a_la_peticion_del_si(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(recetas_de_lo_confirmado=[{"cambiar": ORDEN}], recetas_diferidas=[], ordenes_peticion=5)
    a._empezar_recetas_de_la_peticion()
    assert a.ejecutor.recetas_diferidas == [{"cambiar": ORDEN}] and a.ejecutor.recetas_de_lo_confirmado == [] and a.ejecutor.ordenes_peticion == 0


def test_la_receta_usada_vuelve_a_pasar_por_la_comprobacion_de_efecto(ej, monkeypatch):
    """Al usar una receta, su orden es una orden más: si ahora escribiría una clave Exec, pide «sí» como cualquier otra."""
    monkeypatch.setattr(H, "notificar", lambda *a, **k: None)
    monkeypatch.setattr(ej, "_con_red", lambda c, m, k: "código de salida: 0 (0 s)\nhecho")
    os.makedirs(os.path.join(H._HOME, ".config", "autostart"), exist_ok=True)
    receta = "printf '[Desktop Entry]\\n{x}\\n' > ~/.config/autostart/{valor}.desktop"
    sin_si = receta.replace("{x}", "Hidden=true").replace("{valor}", "arch-update-tray")
    con_exec = receta.replace("{x}", "Exec=otra-cosa").replace("{valor}", "arch-update-tray")
    assert not ej.herramienta({"comando": sin_si, "motivo": "receta"}).startswith("PREPARADO")
    assert ej.herramienta({"comando": con_exec, "motivo": "receta"}).startswith("PREPARADO")
