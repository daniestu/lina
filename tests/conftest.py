# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Aislamiento de TODAS las pruebas: una casa temporal propia antes de importar nada de Lina.

rutas.py calcula CONFIG, DATOS, ESTADO, CACHE y EJECUCION al importarse, así que el aislamiento no puede ser una fixture por prueba: se fija aquí,
al cargar este archivo, que pytest lee antes que cualquier prueba. Ninguna prueba puede tocar tu carpeta personal, tu llavero, tu bus de sesión
ni tu escritorio. La casa va en tests/.casa-pruebas/ (ignorada en git), FUERA de las zonas desechables (/tmp…): ahí cualquier ruta ~/… contaría como
desechable y un borrado que debe pedir confirmación pasaría solo sin que ninguna prueba lo notara.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ---- La casa de las pruebas (antes de importar nada de Lina) ----
BASE = Path(os.path.expanduser(os.environ.get("LINA_PRUEBAS_BASE") or "") or Path(__file__).resolve().parent / ".casa-pruebas").resolve()
BASE.mkdir(mode=0o700, exist_ok=True)


def _vivo(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def limpiar_casas_viejas(base):
    """Borra las casas que dejó una ejecución cortada (Ctrl+C, un cuelgue); la de otra batería que sigue en marcha, no (su proceso vive)."""
    for vieja in Path(base).glob("casa-*"):
        try:
            pid = int((vieja / ".pid").read_text())
        except (OSError, ValueError):
            pid = 0
        if not pid or not _vivo(pid):
            shutil.rmtree(vieja, ignore_errors=True)


limpiar_casas_viejas(BASE)

CASA = Path(tempfile.mkdtemp(prefix="casa-", dir=BASE))
(CASA / ".pid").write_text(str(os.getpid()))
(CASA / "run").mkdir(mode=0o700)

os.environ.setdefault("LINA_PRUEBAS_HOME_REAL", os.path.expanduser("~"))      # para que test_aislamiento compruebe que no se usa
for _k in ("DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "WAYLAND_DISPLAY"):
    os.environ.pop(_k, None)
os.environ.update(
    HOME=str(CASA),
    XDG_CONFIG_HOME=str(CASA / ".config"),
    XDG_DATA_HOME=str(CASA / ".local/share"),
    XDG_STATE_HOME=str(CASA / ".local/state"),
    XDG_CACHE_HOME=str(CASA / ".cache"),
    XDG_RUNTIME_DIR=str(CASA / "run"),
    LINA_PRUEBAS_BASE=str(BASE),                     # las suites (procesos aparte) crean su casa en la misma base
)

# Las pruebas son de Arch salvo que digan otra cosa (así dan lo mismo en el equipo de cada uno y en la CI, que es Ubuntu).
# Las que prueban otra familia la fijan con monkeypatch.setenv("LINA_DISTRO", ...).
os.environ.setdefault("LINA_DISTRO", "arch")
# Y de KDE Plasma con Wayland, que es para lo que están escritas las pruebas de ventanas (las de otros escritorios pasan su propio entorno).
os.environ.setdefault("XDG_CURRENT_DESKTOP", "KDE")
os.environ.setdefault("XDG_SESSION_TYPE", "wayland")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(CASA, ignore_errors=True)
