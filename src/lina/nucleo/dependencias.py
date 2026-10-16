"""Programas que solo hacen falta para una función concreta (copiar al portapapeles, buscar en YouTube…).

Lina no los exige al instalar: los pide cuando se usan por primera vez. Si el usuario eligió el perfil «prudente», no instala nada sola y
solo dice qué orden haría falta; con los otros perfiles intenta instalarlos de los repositorios oficiales de su distribución (con
`sudo -n`, es decir, solo si tiene permiso sin contraseña) y, si no puede, explica cómo hacerlo a mano. Nunca insiste más de una vez al día.
"""
import shutil

from lina.nucleo import ajustes as AJ
from lina.nucleo import plataforma as PL
from lina.nucleo import rutas as RUT

# función → (programa que se busca en el PATH, paquete lógico de plataforma.PAQUETES, para qué sirve)
REGISTRO = {
    "portapapeles": ("wl-copy", "wl-clipboard", "copiar al portapapeles"),     # (en X11 es xclip: ver `_segun_sesion`)
    "pdf_html": ("weasyprint", "weasyprint", "crear documentos con diseño en PDF"),     # solo si no hay navegador (Chromium, Chrome, Brave…)
    "youtube": ("yt-dlp", "yt-dlp", "buscar vídeos de YouTube"),
}


def _segun_sesion(funcion):
    """El programa que toca en esta sesión: el portapapeles es wl-clipboard en Wayland y xclip en X11."""
    programa, logico, para = REGISTRO[funcion]
    if funcion == "portapapeles":
        from lina.escritorio import sesion as SES
        if SES.actual().tipo != "wayland":
            return "xclip", "xclip", para
    return programa, logico, para


def asegurar(funcion, which=shutil.which, perfil=None, instalar=PL.instalar, log=lambda m: None):
    """(True, '') si el programa ya está o se acaba de instalar; (False, mensaje para el usuario o la IA) si no."""
    programa, logico, para = _segun_sesion(funcion)
    if funcion == "portapapeles":
        from lina.escritorio import sesion as SES
        if SES.actual().programa_portapapeles():              # cualquiera de los programas de portapapeles vale
            return True, ""
    if which(programa):
        return True, ""
    orden = PL.orden_canonica_instalar([logico])
    perfil = perfil or _perfil()
    if perfil == "prudente":
        return False, f"Falta {programa} para {para}. Estás en el perfil prudente, así que no instalo nada sola: propón al usuario ejecutar ({orden})."
    if instalar([logico], log, marca=RUT.ESTADO / f"dependencia_{funcion}"):
        if which(programa):
            return True, ""
        return False, f"He instalado el paquete de {programa}, pero no lo encuentro todavía: prueba de nuevo en un momento."
    return False, f"Falta {programa} para {para} y no he podido instalarlo sola. Propón al usuario instalarlo ({orden})."


def _perfil():
    try:
        return AJ.solo_lectura().get("autonomia", "perfil")
    except Exception:
        return "equilibrado"
