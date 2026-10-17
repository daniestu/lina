"""Punto de entrada:  lina [orden]   (o  python -m lina [orden])"""
import os
import runpy
import signal
import subprocess
import sys

from lina import __version__
from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T

AYUDA = N_("""Lina {version}: asistente de voz para el escritorio Linux.

  lina                       arranca a Lina (lo normal es que lo haga sola el servicio de usuario)
  lina pulsar                equivale a pulsar el atajo (hablar / terminar de hablar / callarla). Ponlo en el atajo de teclado
  lina config [ORDEN]        ver y cambiar los ajustes (nombre, voz, perfil de autonomía, gasto…):  lina config ayuda
  lina voz [NOMBRE]          lista las voces o elige una (la descarga si hace falta)
  lina clave [gemini|pago|openai|anthropic|NOMBRE]   guarda una clave (de la IA, de pago, de un servidor MCP…) en el llavero del sistema, sin que se vea ni se dicte
  lina ia [ORDEN]            con qué IA habla Lina (Gemini, Anthropic, OpenAI y compatibles) y cómo cambiarla:  lina ia ayuda
  lina privilegios [instalar|total|quitar]   qué permisos de administrador tiene Lina y cómo dárselos o quitárselos (siempre tras enseñarte lo que se escribe)
  lina privacidad [si|no]    qué se envía a la IA y qué no, y si permites enviar capturas de tu pantalla
  lina olvidar [QUÉ]         borra lo que Lina guarda de ti: diario, registro de acciones, recetas, registro del sistema (antes enseña qué y cuánto)
  lina manos-libres ORDEN    probar "frase" · eco · nivel   (ajustes del manos libres)
  lina indicador probar      enseña el resplandor de escucha
  lina interfaz ORDEN        diagnostico · preparar · estado   (control de programas con la pantalla)
  lina sistema               qué distribución, gestor de paquetes y escritorio detecta
  lina preparar              (lo hace install.sh) comando, modelos, servicio y atajo; --simular dice lo que haría sin tocar nada
  lina escritorio            qué escritorio detecta y qué puede hacer Lina en él (ventana activa, captura de pantalla, portapapeles)
  lina update [--comprobar]  actualiza Lina (te enseña qué trae y pregunta); --volver deshace la última actualización
  lina doctor [--red]        comprueba la instalación y dice cómo arreglar lo que falle; --informe lo da sin datos personales
  lina bienvenida            te guía para dejar a Lina lista: clave de Gemini, micrófono, nombre, autonomía y privacidad
  lina modelos [estado]      descarga (o dice si están) el modelo de voz a texto y la voz de Lina
  lina atajo [TECLA]         crea el atajo de teclado global para hablar con Lina (KDE y GNOME)
  lina uninstall [--todo]    quita lo que instaló Lina; --todo también tus ajustes, claves y datos
  lina mcp [--config]        servidor MCP de Lina para otras IAs
  lina --version
""")


def _pulsar():
    try:
        pid = int(RUT.PID.read_text().strip())
        os.kill(pid, signal.SIGUSR1)
    except (OSError, ValueError):
        print(T("Lina no está arrancada (no encuentro su proceso). Arráncala con:  systemctl --user start lina"), file=sys.stderr)
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
        print(T(AYUDA, version=__version__))
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
    if orden == "config":
        from lina.nucleo import ajustes
        return ajustes.principal(resto)
    if orden == "privilegios":
        from lina.nucleo import privilegios
        return privilegios.principal(resto)
    if orden == "privacidad":
        from lina.nucleo import privacidad
        return privacidad.principal(resto)
    if orden == "olvidar":
        from lina.nucleo import olvidar
        return olvidar.principal(resto)
    if orden == "voz":
        from lina.voz import voces
        return voces.principal(resto)
    if orden == "preparar":
        from lina.nucleo import instalador
        return instalador.preparar(resto)
    if orden in ("uninstall", "desinstalar"):
        from lina.nucleo import instalador
        return instalador.desinstalar(resto)
    if orden == "atajo":
        from lina.nucleo import instalador
        return instalador.atajo_cli(resto)
    if orden == "escritorio":
        from lina.escritorio import sesion
        return sesion.principal(resto)
    if orden in ("update", "actualizar"):
        from lina.nucleo import actualizar
        return actualizar.principal(resto)
    if orden in ("doctor", "diagnostico"):
        from lina.nucleo import doctor
        return doctor.principal(resto)
    if orden in ("bienvenida", "welcome"):
        from lina.nucleo import bienvenida
        return bienvenida.principal(resto)
    if orden == "ia":
        from lina.nucleo import ia_cli
        return ia_cli.principal(resto)
    if orden == "modelos":
        from lina.nucleo import modelos
        return modelos.principal(resto)
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
    print(T(AYUDA, version=__version__))
    return 2


if __name__ == "__main__":
    sys.exit(main())
