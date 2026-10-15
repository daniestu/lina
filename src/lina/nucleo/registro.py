"""Registro de acciones (acciones.log) y avisos del escritorio. Todo lo que hace el asistente queda anotado aquí, con las claves tapadas."""
import os
import shutil
import subprocess
import time

from lina.nucleo import rutas as RUT

ARCHIVO_ACCIONES = RUT.REGISTRO_ACCIONES


def log(mensaje):
    print(f"[{time.strftime('%H:%M:%S')}] {mensaje}", flush=True)


MAX_REGISTRO_ACCIONES = 1_000_000          # al pasar de ~1 MB el registro de acciones se rota: se guarda la mitad vieja como .1 (una sola copia)


def _rotar(ruta, maximo):
    try:
        if ruta.stat().st_size > maximo:
            ruta.replace(ruta.with_name(ruta.name + ".1"))
    except OSError:
        pass


def anotar(linea):
    """Cada acción queda escrita en acciones.log (con las claves tapadas y rotando el archivo para que no crezca sin fin)."""
    try:
        from lina.nucleo import claves as _claves
        linea = _claves.limpiar(str(linea))
    except Exception:
        pass
    try:
        _rotar(ARCHIVO_ACCIONES, MAX_REGISTRO_ACCIONES)
        fd = os.open(ARCHIVO_ACCIONES, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {linea}\n")
    except OSError:
        pass


def notificar(titulo, cuerpo=""):
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", "-a", "Asistente", titulo, cuerpo[:400]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
