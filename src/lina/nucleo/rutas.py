"""Dónde guarda Lina sus cosas.

Sigue la convención XDG (la de cualquier programa de escritorio en Linux):

  CONFIG     ~/.config/lina          lo que el usuario edita: ajustes, claves, listas de palabras
  DATOS      ~/.local/share/lina     lo que Lina aprende y guarda: recetas, diario, gasto, voces
  ESTADO     ~/.local/state/lina     registros y cosas que se pueden perder sin drama
  CACHE      ~/.cache/lina           lo que se puede volver a generar
  EJECUCION  $XDG_RUNTIME_DIR/lina   ficheros temporales del proceso (pid, capturas, audio)

Los archivos con valores de fábrica viajan dentro del paquete (carpeta ``datos/``). La primera vez que se pide uno con
``editable()`` se copia a CONFIG, y desde entonces manda la copia del usuario: las actualizaciones no la pisan.
"""
import os
import shutil
import tempfile
from pathlib import Path

APP = "lina"
PAQUETE = Path(__file__).resolve().parents[1]
DEFECTOS = PAQUETE / "datos"


def _xdg(variable, relativo):
    base = os.environ.get(variable)
    return Path(base) if base and os.path.isabs(base) else Path.home() / relativo


def _ejecucion():
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base and os.path.isdir(base):
        return Path(base) / APP
    return Path(tempfile.gettempdir()) / f"{APP}-{os.getuid()}"


CONFIG = _xdg("XDG_CONFIG_HOME", ".config") / APP
DATOS = _xdg("XDG_DATA_HOME", ".local/share") / APP
ESTADO = _xdg("XDG_STATE_HOME", ".local/state") / APP
CACHE = _xdg("XDG_CACHE_HOME", ".cache") / APP
EJECUCION = _ejecucion()

VOCES = DATOS / "voces"
PID = EJECUCION / "lina.pid"
REGISTRO_ACCIONES = ESTADO / "acciones.log"


def asegurar(ruta, modo=0o700):
    """Crea la carpeta (con permisos privados) si no existe y la devuelve. Si no se puede, no falla: devuelve la ruta igualmente."""
    try:
        Path(ruta).mkdir(parents=True, exist_ok=True, mode=modo)
    except OSError:
        pass
    return Path(ruta)


def temporal(nombre):
    """Ruta de un fichero temporal propio (dentro de la carpeta de ejecución del usuario, no en /tmp compartido)."""
    return asegurar(EJECUCION) / nombre


def editable(nombre):
    """Ruta de un archivo de ajustes del usuario. Si aún no existe, copia el de fábrica. Si no hay de fábrica, solo devuelve la ruta."""
    destino = CONFIG / nombre
    if not destino.exists():
        origen = DEFECTOS / nombre
        if origen.is_file():
            asegurar(CONFIG)
            try:
                shutil.copyfile(origen, destino)
            except OSError:
                return origen                                  # carpeta de solo lectura: se lee el de fábrica
    return destino


def carpeta_usuario(clave, defecto):
    """Carpeta del usuario según XDG (DOCUMENTS, DOWNLOAD, DESKTOP…), que cambia de nombre con el idioma (Documentos, Documents…)."""
    casa = Path.home()
    try:
        for linea in (_xdg("XDG_CONFIG_HOME", ".config") / "user-dirs.dirs").read_text(encoding="utf-8").splitlines():
            if linea.startswith(f"XDG_{clave}_DIR="):
                valor = linea.split("=", 1)[1].strip().strip('"').replace("$HOME", str(casa))
                if valor and valor != str(casa):
                    return Path(valor)
    except OSError:
        pass
    return casa / defecto


def de_fabrica(nombre):
    """Ruta del archivo de fábrica (el que viaja con el programa)."""
    return DEFECTOS / nombre
