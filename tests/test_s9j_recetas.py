# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9j: una petición que siguió una receta la refuerza en vez de apuntar otra; dos recetas con la misma orden se unen aunque cambie el motivo o el
programa del hueco; y no se guarda una receta que tapa en tu carpeta algo que no existe en el sistema. Caso real (medida de A16b, 2026-11-23): 15
recetas para 3 tareas, y una que ocultaba además un archivo con el nombre mal. Todo en carpetas temporales (también el «sistema»)."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lina.nucleo import ejecucion as EJ
from lina.nucleo import herramientas as H
from lina.nucleo import recetas as REC

CP = "mkdir -p ~/.config/autostart && cp /etc/xdg/autostart/{valor} ~/.config/autostart/ && echo Hidden=true >> ~/.config/autostart/{valor}"


def pasos(comando, motivo="ocultarla"):
    return [{"herr": "ejecutar_comando", "args": {"comando": comando, "motivo": motivo}}]


@pytest.fixture(autouse=True)
def recetas(tmp_path, monkeypatch):
    monkeypatch.setattr(REC, "ARCHIVO", tmp_path / "recetas.json")
    monkeypatch.setattr(REC, "_en_privado", lambda: False)


# ---------------------------------------------------------------- la misma receta
def test_encaja_sin_contar_el_motivo_y_con_el_hueco_relleno_igual_en_todas_partes():
    concreta = CP.replace("{valor}", "a.desktop")
    assert REC.encaja(pasos(concreta, "uno"), pasos(concreta, "otro")) == (True, None)
    assert REC.encaja(pasos(CP), pasos(concreta)) == (True, "a.desktop")
    mezclada = CP.replace("{valor}", "a.desktop", 1).replace("{valor}", "b.desktop")
    assert REC.encaja(pasos(CP), pasos(mezclada))[0] is False
    assert REC.encaja(pasos(CP), pasos("rm -f ~/.config/autostart/a.desktop"))[0] is False


def test_dos_recetas_con_la_misma_orden_y_otro_motivo_se_unen():
    orden = CP.replace("{valor}", "a.desktop")
    REC.aprender_pasos("quita a del arranque", pasos(orden, "ocultar a"), nombre="quitar una app del inicio automático", valor="a.desktop")
    REC.aprender_pasos("quita b del arranque", pasos(CP.replace("{valor}", "b.desktop"), "deshabilitar b"), nombre="desactivar el arranque de una app",
                       valor="b.desktop")
    [r] = REC._cargar()
    assert r["ajuste"] == "quitar una app del inicio automático" and r["exitos"] == 2 and r["valor_usado"] == "b.desktop"


def test_una_concreta_y_la_misma_con_hueco_se_unen():
    REC.aprender_pasos("quita a del arranque", pasos(CP.replace("{valor}", "a.desktop")), por_nombrar=True)
    REC.aprender_pasos("quita a del arranque", pasos(CP.replace("{valor}", "a.desktop")), nombre="quitar una app del inicio automático",
                       valor="a.desktop")
    [r] = REC._cargar()
    assert r["ajuste"] == "quitar una app del inicio automático" and "{valor}" in r["pasos"][0]["args"]["comando"]


def test_ya_hecha_la_encuentra_con_otro_programa():
    REC.aprender_pasos("quita a del arranque", pasos(CP.replace("{valor}", "a.desktop")), nombre="quitar una app del inicio automático",
                       valor="a.desktop")
    r, valor = REC.ya_hecha(pasos(CP.replace("{valor}", "b.desktop"), "otro motivo"))
    assert valor == "b.desktop" and r["id"] == "r0001"
    REC.reforzar(r["id"])
    assert REC._cargar()[0]["exitos"] == 2


# ---------------------------------------------------------------- reforzar al terminar
def _asistente(comando, general=("quitar una app del inicio automático", "b.desktop")):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = SimpleNamespace(cambio_comprobado=True, duda="", contaminado="", receta_turno=False, pendientes=[])
    a.modo_privado, a.turno_aceptado, a.insistiendo, a.historial = False, True, False, []
    a.pregunta_pura = "Quita b del arranque"
    a.acciones_turno = [("ejecutar_comando", {"comando": comando, "motivo": "otro motivo"}, "código de salida: 0 (0 s)\n\n✔ existe el archivo")]
    a._recetas_de_pasos_activas = lambda: True
    a._generalizar_receta = MagicMock(return_value=general)
    a._REC = lambda: REC
    return a


def test_la_peticion_que_siguio_la_receta_la_refuerza_y_no_apunta_otra(sistema):
    REC.aprender_pasos("quita a del arranque", pasos(CP.replace("{valor}", "a.desktop")), nombre="quitar una app del inicio automático",
                       valor="a.desktop")
    a = _asistente(CP.replace("{valor}", "b.desktop"))
    a._aprender_pasos()
    [r] = REC._cargar()
    assert r["exitos"] == 2 and a.ejecutor.receta_turno is True and not a._generalizar_receta.called


def test_las_que_apunta_el_codigo_se_refuerzan_al_darse_por_cumplida(sistema, monkeypatch):
    orden = CP.replace("{valor}", "b.desktop")
    REC.aprender_comando("quitar una app del inicio automático", "", "x", CP, "a.desktop", "", "✔")       # con el hueco, como _guardar_general
    ej = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    monkeypatch.setattr(H, "anotar", lambda *a: None)
    ej.ordenes_peticion = 3
    ej._receta_por_hechos(orden, "autonomo", "✔")
    assert ej.recetas_diferidas == [{"reforzar": "r0001", "cambiar": orden, "generalizar": True}]
    ej.guardar_diferidas("Quita b del arranque")
    [r] = REC._cargar()
    assert r["exitos"] == 2 and ej.receta_turno


# ---------------------------------------------------------------- lo que se oculta tiene que existir
@pytest.fixture
def sistema(tmp_path, monkeypatch):
    """Un «sistema» de prueba: /etc/xdg/autostart con a.desktop y b.desktop, y tu carpeta en tmp."""
    casa = tmp_path / "casa"
    (casa / ".config" / "autostart").mkdir(parents=True)
    xdg = tmp_path / "etc-xdg"
    (xdg / "autostart").mkdir(parents=True)
    for n in ("a.desktop", "b.desktop"):
        (xdg / "autostart" / n).write_text("[Desktop Entry]\nExec=x\n")
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(xdg))
    monkeypatch.setattr(H, "_HOME", str(casa))
    monkeypatch.setattr(EJ, "_HOME", str(casa))
    return casa


OCULTAR = "printf '[Desktop Entry]\\nHidden=true\\n' > ~/.config/autostart/{n}"


def test_tapa_uno_que_existe_y_otro_mal_nombrado_en_la_misma_carpeta(sistema):
    orden = OCULTAR.format(n="a.desktop") + " && " + OCULTAR.format(n="a-mal-escrito.desktop")
    assert H.sombras_sin_original(orden) == [str(sistema / ".config/autostart/a-mal-escrito.desktop")]


@pytest.mark.parametrize("orden", [OCULTAR.format(n="a.desktop"), OCULTAR.format(n="a.desktop") + " && " + OCULTAR.format(n="b.desktop"),
                                   OCULTAR.format(n="mio.desktop"),               # no tapa nada que exista: puede ser tuyo, no se juzga
                                   "mkdir -p ~/.config/autostart && cp /etc/xdg/autostart/a.desktop ~/.config/autostart/a.desktop"])
def test_lo_demas_no_se_juzga(sistema, orden):
    assert H.sombras_sin_original(orden.replace("/etc/xdg", str(sistema.parent / "etc-xdg"))) == []


def test_una_receta_que_tapa_lo_que_no_existe_no_se_guarda(sistema):
    orden = OCULTAR.format(n="a.desktop") + " && " + OCULTAR.format(n="a-mal-escrito.desktop")
    _asistente(orden)._aprender_pasos()
    assert REC._cargar() == []
    ej = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    ej.ordenes_peticion = 3
    ej._receta_por_hechos(orden, "autonomo", "✔")
    assert not ej.recetas_diferidas


def test_las_de_pasos_llevan_tu_carpeta_como_tilde(sistema):
    _asistente(f"printf 'x' > {sistema}/.config/autostart/mio.desktop", general=None)._aprender_pasos()
    [r] = REC._cargar()
    assert r["pasos"][0]["args"]["comando"] == "printf 'x' > ~/.config/autostart/mio.desktop"
