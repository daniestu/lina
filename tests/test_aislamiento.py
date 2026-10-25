# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Las pruebas no tocan tu carpeta personal, tu bus de sesión ni tu escritorio (ver conftest.py). Si esto falla, NO sigas: las demás pruebas podrían
estar escribiendo en tus ajustes, tu memoria o tu diario de verdad."""
import os
from pathlib import Path

import conftest
from lina.nucleo import herramientas as H
from lina.nucleo import rutas as RUT

CASA = Path(os.environ["HOME"]).resolve()
HOME_REAL = Path(os.environ["LINA_PRUEBAS_HOME_REAL"]).resolve()


def _dentro(ruta, carpeta):
    return Path(ruta).resolve().is_relative_to(Path(carpeta).resolve())


def test_la_casa_es_la_temporal_y_no_la_real():
    assert CASA == Path(conftest.CASA).resolve() and CASA != HOME_REAL, (
        f"HOME es {CASA} y no la casa temporal de conftest.py: ¿se ha importado algo de Lina antes que conftest.py?")


def test_las_rutas_de_lina_estan_en_la_casa_temporal():
    for nombre in ("CONFIG", "DATOS", "ESTADO", "CACHE", "EJECUCION"):
        ruta = getattr(RUT, nombre)
        assert _dentro(ruta, CASA), (f"RUT.{nombre} es {ruta}, fuera de la casa temporal de las pruebas ({CASA}): las pruebas tocarían tu carpeta "
                                     f"personal ({HOME_REAL}). rutas.py calcula sus carpetas al importarse: nada de Lina puede importarse antes que conftest.py.")
        assert not _dentro(ruta, HOME_REAL) or _dentro(ruta, conftest.BASE), f"RUT.{nombre} ({ruta}) cae dentro de tu carpeta personal real"


def test_sin_bus_de_sesion_ni_escritorio_real():
    for variable in ("DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "WAYLAND_DISPLAY"):
        assert variable not in os.environ, f"{variable} sigue definida: una prueba podría llegar a tu llavero o a tu escritorio de verdad"
    assert _dentro(os.environ["XDG_RUNTIME_DIR"], CASA)


def test_la_casa_no_esta_en_una_zona_desechable():
    zonas = [os.path.expanduser(z) for z in H._politica()["desechables"]]
    for zona in zonas:
        assert not _dentro(CASA, zona), (
            f"La casa de las pruebas ({CASA}) está dentro de la zona desechable {zona}: ahí cualquier ruta ~/… cuenta como desechable y un borrado que "
            f"debe pedir confirmación pasaría solo, así que las pruebas de seguridad no valdrían. El repositorio (o LINA_PRUEBAS_BASE, si la has definido) está en una zona desechable: clónalo fuera "
            f"de /tmp, /var/tmp, /dev/shm y ~/.cache, o define LINA_PRUEBAS_BASE con una carpeta fuera de ellas (por ejemplo "
            f"LINA_PRUEBAS_BASE=~/lina-pruebas pytest).")


def test_se_borran_las_casas_de_ejecuciones_cortadas_y_no_la_de_una_en_marcha(tmp_path):
    import subprocess
    import sys
    muerto = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True).stdout.strip()
    for nombre, pid in (("casa-cortada", muerto), ("casa-viva", str(os.getpid())), ("casa-sin-pid", None)):
        (tmp_path / nombre).mkdir()
        if pid:
            (tmp_path / nombre / ".pid").write_text(pid)
    (tmp_path / "otra-cosa").mkdir()
    conftest.limpiar_casas_viejas(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["casa-viva", "otra-cosa"]
