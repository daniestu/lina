# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Privilegios de Lina: qué puede hacer como administrador y cómo se le da (o se le quita) ese permiso.

Tres niveles, de menos a más:
  ninguno   no hay regla: lo que necesita permisos de administrador se confirma con el atajo y te pide la contraseña el propio sistema (polkit/pkexec).
            Lina no ve ni guarda la contraseña.
  instalar  una regla de sudoers permite UN solo programa, el ayudante `lina-instalar`, que solo instala paquetes de los repositorios del sistema.
  total     opcional: sudo sin contraseña para todo. Con aviso, y solo tecleando una frase.
Lo cambia el usuario en una terminal con `lina privilegios`; la IA no puede (está bloqueado en herramientas.py).
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from lina.nucleo import raiz as RAIZ
from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T

AYUDANTE_PAQUETE = RUT.PAQUETE / "datos" / "privilegios" / "lina-instalar"
FRASE_TOTAL = N_("DAR ACCESO TOTAL")
COMPROBAR = False                      # asistente.main() lo activa: solo entonces las órdenes con sudo se adaptan al nivel que haya
_cache = {"cuando": 0.0, "nivel": None}


# ----------------------------------------------------------------------------------------------------------------------
# Qué nivel hay ahora mismo
# ----------------------------------------------------------------------------------------------------------------------
def _ok(orden, ejecutar):
    try:
        return ejecutar(orden, capture_output=True, timeout=10, stdin=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def nivel(ejecutar=subprocess.run, ahora=time.time, usar_cache=True):
    """'total' | 'instalar' | 'ninguno'. Se mira con `sudo -n` (nunca pide contraseña) y se recuerda un minuto."""
    if usar_cache and _cache["nivel"] and ahora() - _cache["cuando"] < 60:
        return _cache["nivel"]
    if os.geteuid() == 0 or _ok(["sudo", "-n", "true"], ejecutar):
        n = "total"
    elif _ok(["sudo", "-n", "-l", RAIZ.AYUDANTE, "instalar", "paquete"], ejecutar):
        n = "instalar"
    else:
        n = "ninguno"
    _cache.update(cuando=ahora(), nivel=n)
    return n


def olvidar():
    _cache.update(cuando=0.0, nivel=None)


def hash_ayudante():
    return hashlib.sha256(AYUDANTE_PAQUETE.read_bytes()).hexdigest()


_ESTADOS_AYUDANTE = (N_("no instalado"), N_("al día"), N_("distinto"))        # para el catálogo: se traducen al mostrarlos


def estado_ayudante():
    """Cómo está el ayudante instalado: 'no instalado' | 'al día' | 'distinto' (versión vieja o cambiada) | 'inseguro: motivo'."""
    ruta = Path(RAIZ.AYUDANTE)
    if not ruta.exists():
        return "no instalado"
    try:
        for c in [ruta, *ruta.parents]:
            if str(c) == "/":
                break
            st = c.lstat()
            if c.is_symlink() or st.st_uid != 0 or st.st_mode & 0o022:
                return T("inseguro: {c} no es solo de root", c=c)
        return "al día" if hashlib.sha256(ruta.read_bytes()).hexdigest() == hash_ayudante() else "distinto"
    except OSError as e:
        return T("no se puede comprobar ({e})", e=e)


def descripcion(n):
    return {"ninguno": T("Sin permisos de administrador: lo que los necesite se confirma con el atajo y te pide la contraseña el sistema."),
            "instalar": T("Puedo instalar paquetes de los repositorios de tu sistema sin pedirte la contraseña (solo eso; lo demás se confirma)."),
            "total": T("Tengo sudo sin contraseña para todo (nivel total). Lo crítico se sigue confirmando con el atajo.")}[n]


# ----------------------------------------------------------------------------------------------------------------------
# Adaptar las órdenes con sudo al nivel que hay
# ----------------------------------------------------------------------------------------------------------------------
def adaptar(comando, paquetes=None, n=None, existe=shutil.which):
    """`comando` ya viene con 'sudo -n'. Con nivel total no se toca. Con 'instalar', las instalaciones van por el ayudante. Sin regla, la orden sencilla
    pasa a pkexec (el sistema pide la contraseña en su propio diálogo)."""
    if not COMPROBAR:
        return comando
    n = n or nivel()
    if n == "total":
        return comando
    if paquetes and n == "instalar":
        return "sudo -n " + RAIZ.AYUDANTE + " instalar " + " ".join(paquetes)
    if n == "ninguno" and existe("pkexec") and re.match(r"^sudo -n [A-Za-z0-9_./-]+( [A-Za-z0-9_.,:=/@+-]+)*$", comando.strip()):
        return "pkexec" + comando.strip()[len("sudo -n"):]
    return comando


def pide_contrasena(comando, paquetes=None, n=None):
    """¿Esta orden con sudo se quedaría sin poder ejecutarse sin la contraseña? (Entonces se confirma antes con el atajo.)"""
    if not COMPROBAR or not re.match(r"^\s*(?:sudo|doas)\b", comando):
        return False
    n = n or nivel()
    if n == "total":
        return False
    if n == "instalar" and paquetes:                      # instalar paquetes oficiales va por el ayudante, sin contraseña
        return False
    return True


# ----------------------------------------------------------------------------------------------------------------------
# lina privilegios
# ----------------------------------------------------------------------------------------------------------------------
AYUDA = N_("""lina privilegios                  qué permisos de administrador tiene Lina ahora
lina privilegios instalar         permite a Lina instalar paquetes sin contraseña (solo eso). Antes enseña todo lo que escribirá
lina privilegios total            sudo sin contraseña para todo (nivel total, con aviso)
lina privilegios quitar           quita todo lo anterior
Las tres últimas piden tu contraseña de administrador al sistema (sudo/pkexec): Lina nunca la ve.""")


def _usuario():
    return os.environ.get("USER") or os.environ.get("LOGNAME") or ""


def _vista_previa(accion, usuario, contenido):
    lineas = [T("Esto es TODO lo que se va a escribir, como administrador:"), ""]
    if accion == "quitar":
        return T("Se borrarán, si existen:\n  ") + "\n  ".join([RAIZ.SUDOERS_TOTAL, RAIZ.SUDOERS_INSTALAR, RAIZ.POLKIT, RAIZ.AYUDANTE])
    lineas += [f"1) {RAIZ.AYUDANTE}   (root:root, 755)", T("   El ayudante: un solo archivo corto que solo instala paquetes de los repositorios de tu sistema."),
               T("   Léelo entero antes de aceptar:  less {AYUDANTE_PAQUETE}", AYUDANTE_PAQUETE=AYUDANTE_PAQUETE), f"   Huella (sha256): {hashlib.sha256(contenido).hexdigest()}", "",
               T("2) {v1}   (root, 440)   — se valida con visudo antes de activarse", v1=RAIZ.SUDOERS_INSTALAR), ""]
    lineas += ["   | " + l for l in RAIZ.sudoers_instalar(usuario).splitlines()]
    lineas += ["", T("3) {v1}   (política de polkit, para que el diálogo de contraseña diga qué se pide)", v1=RAIZ.POLKIT)]
    if accion == "total":
        lineas += ["", f"4) {RAIZ.SUDOERS_TOTAL}   (root, 440)", ""] + ["   | " + l for l in RAIZ.sudoers_total(usuario).splitlines()]
    lineas += ["", T("Quitarlo todo más tarde:  lina privilegios quitar")]
    return "\n".join(lineas)


AVISO_TOTAL = N_("""AVISO: el nivel total es el más peligroso.
Con él, cualquier programa que se ejecute como tú (Lina, o un fallo suyo, una página web que la engañe, un programa malicioso) podrá hacer CUALQUIER
cosa en este equipo como administrador, sin pedirte nada: borrar el sistema, leer todo, instalar programas. Lina seguirá confirmando con el atajo lo crítico,
pero esa protección es del propio programa, no del sistema.
El nivel «instalar» ya cubre lo habitual (instalar paquetes). Usa el total solo si sabes por qué lo quieres.""")


def _preguntar(texto, entrada):
    try:
        return entrada(texto).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _lanzar(datos, ejecutar=subprocess.run, existe=shutil.which, es_terminal=None):
    """Ejecuta raiz.py como administrador con los datos por la entrada estándar. Con terminal usa sudo; sin ella, pkexec."""
    codigo = Path(RAIZ.__file__).read_text(encoding="utf-8") + "\nsys.exit(main())\n"
    import json
    carga = json.dumps(datos).encode("utf-8")
    terminal = sys.stdin.isatty() if es_terminal is None else es_terminal
    puerta = ["sudo"] if (existe("sudo") and terminal) else (["pkexec"] if existe("pkexec") else (["sudo"] if existe("sudo") else None))
    if not puerta:
        return 1, T("No encuentro ni sudo ni pkexec para pedir permisos.")
    r = ejecutar([*puerta, RAIZ.PYTHON, "-I", "-c", codigo], input=carga, capture_output=True, timeout=300)
    salida = (r.stdout or b"").decode(errors="replace") + (r.stderr or b"").decode(errors="replace")
    return r.returncode, salida.strip()


def principal(argv, entrada=input, salida=print, ejecutar=subprocess.run, es_terminal=None, existe=shutil.which):
    accion = argv[0] if argv else "estado"
    if accion in ("ayuda", "-h", "--help"):
        salida(T(AYUDA))
        return 0
    if accion == "estado":
        n = nivel(ejecutar, usar_cache=False)
        salida(descripcion(n))
        a = estado_ayudante()
        salida(T("Ayudante {ruta}: {estado}", ruta=RAIZ.AYUDANTE, estado=T(a)) + (T("  (actualízalo con:  lina privilegios instalar)") if a in ("distinto",) else ""))
        if n == "total":
            salida(T("Para volver a pedir permiso en cada cosa:  lina privilegios quitar"))
        return 0
    if accion not in ("instalar", "total", "quitar"):
        salida(T(AYUDA))
        return 2
    terminal = sys.stdin.isatty() if es_terminal is None else es_terminal
    if not terminal:
        salida(T("Esto se hace en una terminal, tecleándolo tú: es el consentimiento."))
        return 2
    usuario = _usuario()
    if accion != "quitar" and not RAIZ.USUARIO_VALIDO.fullmatch(usuario):
        salida(T("No sé tu nombre de usuario (variable USER)."))
        return 2
    if not AYUDANTE_PAQUETE.is_file() and accion != "quitar":
        salida(T("Falta el ayudante dentro de la instalación de Lina."))
        return 1
    contenido = AYUDANTE_PAQUETE.read_bytes() if accion != "quitar" else b""
    salida(_vista_previa(accion, usuario, contenido))
    if accion == "total":
        salida("\n" + T(AVISO_TOTAL))
        if _preguntar(T("\nPara aceptar escribe exactamente «{frase}»: ", frase=T(FRASE_TOTAL)), entrada).strip() not in (FRASE_TOTAL, T(FRASE_TOTAL)):
            salida(T("No se ha cambiado nada."))
            return 1
    elif _preguntar(T("\n¿Lo hago? Te pedirá tu contraseña de administrador. Escribe «sí» para continuar: "), entrada).lower() not in ("si", "sí", "s", "y", "yes"):
        salida(T("No se ha cambiado nada."))
        return 1
    datos = {"accion": accion, "usuario": usuario, "ayudante": contenido.decode("utf-8"), "sha256": hashlib.sha256(contenido).hexdigest()}
    codigo, texto = _lanzar(datos, ejecutar, existe, terminal)
    olvidar()
    salida(texto or (T("Hecho.") if codigo == 0 else T("No se pudo.")))
    if codigo == 0 and accion != "quitar":
        salida(T("\nListo. Comprueba cuando quieras con:  lina privilegios"))
    return codigo
