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
import types
from pathlib import Path
from unittest.mock import MagicMock

SRC =Path(__file__).resolve().parents[1] / "src"
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


# ---- El audio de las pruebas (antes de importar nada de Lina) ----
class SustitutoAudio(types.ModuleType):
    """`sounddevice` de mentira, igual en todos los equipos: con PortAudio o sin él, la librería real no llega a cargarse. Sus atributos son reales,
    no los que un MagicMock inventa al pedirlos: desde pytest 9.2, monkeypatch no ve esos y al deshacer los borra del simulacro."""

    def __getattr__(self, nombre):
        if nombre.startswith("__"):                  # lo que Python pregunta a cualquier módulo (__path__, __file__…) no se inventa
            raise AttributeError(nombre)
        valor = MagicMock(name=f"sounddevice.{nombre}")
        setattr(self, nombre, valor)
        return valor


sys.modules["sounddevice"] = SustitutoAudio("sounddevice")      # sin setdefault: los `setdefault` de cada prueba se encuentran este y no hacen nada
for _n in ("InputStream", "OutputStream", "play", "stop", "wait", "rec", "sleep", "query_devices", "default"):
    setattr(sys.modules["sounddevice"], _n, MagicMock(name=f"sounddevice.{_n}"))


def pytest_configure(config):
    """tmp_path, dentro de la casa: en /tmp cualquier ruta contaría como desechable. Nombre corto: en esas carpetas hay sockets, con un límite de ~108 caracteres."""
    if not config.option.basetemp:
        config.option.basetemp = str(CASA / "t")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(CASA, ignore_errors=True)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _registro_sin_modo_privado():
    """S10: el modo privado del registro es del proceso; una prueba que lo activa no lo deja puesto para las siguientes."""
    yield
    from lina.nucleo import registro
    registro.privado(False)


@pytest.fixture(autouse=True)
def _sin_aur_de_verdad(monkeypatch):
    """A15: ninguna prueba consulta el AUR de verdad (las que lo prueban le pasan su propio `http`)."""
    from lina.nucleo import aur

    def sin_red():
        raise RuntimeError("sin red en las pruebas")
    monkeypatch.setattr(aur, "_http", sin_red)


@pytest.fixture(autouse=True)
def _cupo_de_tavily_aparte(monkeypatch, tmp_path):
    """E2: cada prueba empieza con el cupo de Tavily a cero (su archivo, en la carpeta de la prueba): un 432 de una no deja agotada a la siguiente."""
    from lina.nucleo import cupo_tavily
    monkeypatch.setattr(cupo_tavily, "ARCHIVO", tmp_path / "tavily.json")


@pytest.fixture(autouse=True)
def _sin_vigia_de_verdad(monkeypatch):
    """S9g: el vigía de las medidas mira tu sistema real (systemd de tu usuario, ~/.config): en las pruebas, nunca."""
    from lina.nucleo import vigia_medida
    monkeypatch.setattr(vigia_medida, "Vigia", lambda *a, **k: vigia_medida.SinVigia())
