# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9g: el vigía de las medidas. Con una carpeta personal de prueba y un systemctl simulado: nada de tu sistema real (el de verdad lo apaga conftest)."""
import os
from types import SimpleNamespace

import pytest

from lina.nucleo import vigia_medida as VIG


class Systemd:
    def __init__(self):
        self.unidades = {"app-ejemplo-al-arrancar.service": "generated", "sincronizar.timer": "enabled"}
        self.temporizadores = {"sincronizar.timer": "active waiting"}

    def __call__(self, orden, **k):
        if "list-unit-files" in orden:
            texto = "\n".join(f"{u} {e} enabled" for u, e in self.unidades.items())
        else:
            texto = "\n".join(f"{t} loaded {e}" for t, e in self.temporizadores.items())
        return SimpleNamespace(returncode=0, stdout=texto)


@pytest.fixture
def casa(tmp_path):
    (tmp_path / ".config" / "autostart").mkdir(parents=True)
    (tmp_path / ".config" / "systemd" / "user").mkdir(parents=True)
    (tmp_path / ".config" / "kdeglobals").write_text("[General]\nx=1\n")
    (tmp_path / ".config" / "kwinrc").write_text("[Ventanas]\nposicion=1\n")
    return tmp_path


def _vigia(casa, sistemd, cambia_solo=None):
    return VIG.VigiaReal(casa=str(casa), ejecutar=sistemd, espera=0, dormir=lambda s: cambia_solo() if cambia_solo else None)


def test_sin_cambios_no_para(casa):
    v = _vigia(casa, Systemd())
    v.empezar(lambda m: None)
    assert v.parar_si_cambio(lambda m: None) is False


@pytest.mark.parametrize("cambio", ["enmascarar", "parar_temporizador", "autoarranque", "configuracion", "carpeta_nueva"])
def test_lo_que_cambia_la_medida_la_para_y_lo_dice(casa, cambio):
    sistemd = Systemd()
    v = _vigia(casa, sistemd)
    v.empezar(lambda m: None)
    if cambio == "enmascarar":
        sistemd.unidades["app-ejemplo-al-arrancar.service"] = "masked"
        os.symlink("/dev/null", casa / ".config" / "systemd" / "user" / "app-ejemplo-al-arrancar.service")
    elif cambio == "parar_temporizador":
        sistemd.temporizadores["sincronizar.timer"] = "inactive dead"
    elif cambio == "autoarranque":
        (casa / ".config" / "autostart" / "otra.desktop").write_text("[Desktop Entry]\nHidden=true\n")
    elif cambio == "configuracion":
        (casa / ".config" / "kdeglobals").write_text("[General]\nx=2\n")
    else:
        (casa / ".config" / "nuevo-programa").mkdir()
    dicho = []
    assert v.parar_si_cambio(dicho.append) is True
    assert dicho[0].startswith("ME PARO: la medida ha cambiado tu sistema real") and "No deshago nada" in dicho[0]


def test_lo_que_cambia_solo_antes_de_empezar_no_para(casa):
    contador = {"n": 0}

    def el_escritorio_escribe():
        contador["n"] += 1
        (casa / ".config" / "kwinrc").write_text(f"[Ventanas]\nposicion={contador['n'] + 1}\n")
    v = _vigia(casa, Systemd(), cambia_solo=el_escritorio_escribe)
    dicho = []
    v.empezar(dicho.append)
    assert any("kwinrc" in d for d in dicho)                              # se enseña
    (casa / ".config" / "kwinrc").write_text("[Ventanas]\nposicion=99\n")
    assert v.parar_si_cambio(lambda m: None) is False                     # y no para
    (casa / ".config" / "kdeglobals").write_text("[General]\nx=3\n")
    assert v.parar_si_cambio(lambda m: None) is True                      # lo demás, sí


def test_si_systemd_no_responde_se_ve_y_no_se_inventa(casa):
    caido = lambda orden, **k: SimpleNamespace(returncode=1, stdout="")
    assert VIG.foto(str(casa), caido)["unidad:(systemd)"] == "no responde"


def test_las_medidas_que_ejecutan_ordenes_usan_el_vigia():
    import inspect
    from lina.nucleo import probar_busqueda as PB
    from lina.nucleo import probar_ponme as PON
    for modulo in (PB, PON):
        fuente = inspect.getsource(modulo.principal)
        assert "vigia.empezar(salida)" in fuente and "vigia.parar_si_cambio(salida)" in fuente, modulo.__name__


def test_probar_busqueda_escribe_su_registro_en_su_carpeta(monkeypatch):
    from lina.nucleo import probar_busqueda as PB
    from lina.nucleo import registro as REG
    antes = REG.ARCHIVO_ACCIONES
    with PB.usuario_nuevo("gratis", obtener_real=lambda n: ""):
        assert REG.ARCHIVO_ACCIONES != antes and "lina-probar-busqueda-" in str(REG.ARCHIVO_ACCIONES)
    assert REG.ARCHIVO_ACCIONES == antes
