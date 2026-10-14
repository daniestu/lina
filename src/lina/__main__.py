"""Punto de entrada:  lina [orden]   (o  python -m lina [orden])"""
import os
import runpy
import signal
import subprocess
import sys

from lina import __version__
from lina.nucleo import rutas as RUT

AYUDA = f"""Lina {__version__}: asistente de voz para el escritorio Linux.

  lina                       arranca a Lina (lo normal es que lo haga sola el servicio de usuario)
  lina pulsar                equivale a pulsar el atajo (hablar / terminar de hablar / callarla). Ponlo en el atajo de teclado
  lina voz [NOMBRE]          lista las voces o elige una (la descarga si hace falta)
  lina clave NOMBRE          guarda una clave (por ejemplo de un servidor MCP) sin que se vea ni se dicte
  lina manos-libres ORDEN    probar "frase" · eco · nivel   (ajustes del manos libres)
  lina indicador probar      enseña el resplandor de escucha
  lina interfaz ORDEN        diagnostico · preparar · estado   (control de programas con la pantalla)
  lina sistema               qué distribución, gestor de paquetes y escritorio detecta
  lina mcp [--config]        servidor MCP de Lina para otras IAs
  lina --version
"""


def _pulsar():
    try:
        pid = int(RUT.PID.read_text().strip())
        os.kill(pid, signal.SIGUSR1)
    except (OSError, ValueError):
        print("Lina no está arrancada (no encuentro su proceso). Arráncala con:  systemctl --user start lina", file=sys.stderr)
        return 1
    return 0


def _modulo(nombre, args):
    sys.argv = [nombre] + list(args)
    runpy.run_module(nombre, run_name="__main__")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    orden, resto = (argv[0], argv[1:]) if argv else ("run", [])
    if orden in ("-h", "--help", "ayuda", "help"):
        print(AYUDA)
        return 0
    if orden in ("-V", "--version", "version"):
        print(__version__)
        return 0
    if orden == "run":
        from lina.nucleo import asistente
        asistente.main()
        return 0
    if orden == "pulsar":
        return _pulsar()
    if orden == "clave":
        from lina.nucleo import claves
        return claves.principal(resto)
    if orden == "voz":
        from lina.voz import voces
        return voces.principal(resto)
    if orden == "manos-libres":
        return _modulo("lina.voz.manos_libres", resto)
    if orden == "indicador":
        return _modulo("lina.voz.indicador", resto)
    if orden == "sistema":
        return _modulo("lina.nucleo.plataforma", resto)
    if orden == "mcp":
        return _modulo("lina.mcp.servidor", resto)
    if orden == "interfaz":
        guion = RUT.PAQUETE / "escritorio" / "interfaz.sh"
        return subprocess.call(["bash", str(guion), *(resto or ["diagnostico"])])
    print(AYUDA)
    return 2


if __name__ == "__main__":
    sys.exit(main())
