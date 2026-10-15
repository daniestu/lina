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

AYUDANTE_PAQUETE = RUT.PAQUETE / "datos" / "privilegios" / "lina-instalar"
FRASE_TOTAL = "DAR ACCESO TOTAL"
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
                return f"inseguro: {c} no es solo de root"
        return "al día" if hashlib.sha256(ruta.read_bytes()).hexdigest() == hash_ayudante() else "distinto"
    except OSError as e:
        return f"no se puede comprobar ({e})"


def descripcion(n):
    return {"ninguno": "Sin permisos de administrador: lo que los necesite se confirma con el atajo y te pide la contraseña el sistema.",
            "instalar": "Puedo instalar paquetes de los repositorios de tu sistema sin pedirte la contraseña (solo eso; lo demás se confirma).",
            "total": "Tengo sudo sin contraseña para todo (nivel total). Lo crítico se sigue confirmando con el atajo."}[n]


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
AYUDA = """lina privilegios                  qué permisos de administrador tiene Lina ahora
lina privilegios instalar         permite a Lina instalar paquetes sin contraseña (solo eso). Antes enseña todo lo que escribirá
lina privilegios total            sudo sin contraseña para todo (nivel total, con aviso)
lina privilegios quitar           quita todo lo anterior
Las tres últimas piden tu contraseña de administrador al sistema (sudo/pkexec): Lina nunca la ve."""


def _usuario():
    return os.environ.get("USER") or os.environ.get("LOGNAME") or ""


def _vista_previa(accion, usuario, contenido):
    lineas = ["Esto es TODO lo que se va a escribir, como administrador:", ""]
    if accion == "quitar":
        return "Se borrarán, si existen:\n  " + "\n  ".join([RAIZ.SUDOERS_TOTAL, RAIZ.SUDOERS_INSTALAR, RAIZ.POLKIT, RAIZ.AYUDANTE])
    lineas += [f"1) {RAIZ.AYUDANTE}   (root:root, 755)", "   El ayudante: un solo archivo corto que solo instala paquetes de los repositorios de tu sistema.",
               f"   Léelo entero antes de aceptar:  less {AYUDANTE_PAQUETE}", f"   Huella (sha256): {hashlib.sha256(contenido).hexdigest()}", "",
               f"2) {RAIZ.SUDOERS_INSTALAR}   (root, 440)   — se valida con visudo antes de activarse", ""]
    lineas += ["   | " + l for l in RAIZ.sudoers_instalar(usuario).splitlines()]
    lineas += ["", f"3) {RAIZ.POLKIT}   (política de polkit, para que el diálogo de contraseña diga qué se pide)"]
    if accion == "total":
        lineas += ["", f"4) {RAIZ.SUDOERS_TOTAL}   (root, 440)", ""] + ["   | " + l for l in RAIZ.sudoers_total(usuario).splitlines()]
    lineas += ["", "Quitarlo todo más tarde:  lina privilegios quitar"]
    return "\n".join(lineas)


AVISO_TOTAL = """AVISO: el nivel total es el más peligroso.
Con él, cualquier programa que se ejecute como tú (Lina, o un fallo suyo, una página web que la engañe, un programa malicioso) podrá hacer CUALQUIER
cosa en este equipo como administrador, sin pedirte nada: borrar el sistema, leer todo, instalar programas. Lina seguirá confirmando con el atajo lo crítico,
pero esa protección es del propio programa, no del sistema.
El nivel «instalar» ya cubre lo habitual (instalar paquetes). Usa el total solo si sabes por qué lo quieres."""


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
        return 1, "No encuentro ni sudo ni pkexec para pedir permisos."
    r = ejecutar([*puerta, RAIZ.PYTHON, "-I", "-c", codigo], input=carga, capture_output=True, timeout=300)
    salida = (r.stdout or b"").decode(errors="replace") + (r.stderr or b"").decode(errors="replace")
    return r.returncode, salida.strip()


def principal(argv, entrada=input, salida=print, ejecutar=subprocess.run, es_terminal=None, existe=shutil.which):
    accion = argv[0] if argv else "estado"
    if accion in ("ayuda", "-h", "--help"):
        salida(AYUDA)
        return 0
    if accion == "estado":
        n = nivel(ejecutar, usar_cache=False)
        salida(descripcion(n))
        a = estado_ayudante()
        salida(f"Ayudante {RAIZ.AYUDANTE}: {a}" + ("  (actualízalo con:  lina privilegios instalar)" if a in ("distinto",) else ""))
        if n == "total":
            salida("Para volver a pedir permiso en cada cosa:  lina privilegios quitar")
        return 0
    if accion not in ("instalar", "total", "quitar"):
        salida(AYUDA)
        return 2
    terminal = sys.stdin.isatty() if es_terminal is None else es_terminal
    if not terminal:
        salida("Esto se hace en una terminal, tecleándolo tú: es el consentimiento.")
        return 2
    usuario = _usuario()
    if accion != "quitar" and not RAIZ.USUARIO_VALIDO.fullmatch(usuario):
        salida("No sé tu nombre de usuario (variable USER).")
        return 2
    if not AYUDANTE_PAQUETE.is_file() and accion != "quitar":
        salida("Falta el ayudante dentro de la instalación de Lina.")
        return 1
    contenido = AYUDANTE_PAQUETE.read_bytes() if accion != "quitar" else b""
    salida(_vista_previa(accion, usuario, contenido))
    if accion == "total":
        salida("\n" + AVISO_TOTAL)
        if _preguntar(f"\nPara aceptar escribe exactamente «{FRASE_TOTAL}»: ", entrada) != FRASE_TOTAL:
            salida("No se ha cambiado nada.")
            return 1
    elif _preguntar("\n¿Lo hago? Te pedirá tu contraseña de administrador. Escribe «sí» para continuar: ", entrada).lower() not in ("si", "sí", "s"):
        salida("No se ha cambiado nada.")
        return 1
    datos = {"accion": accion, "usuario": usuario, "ayudante": contenido.decode("utf-8"), "sha256": hashlib.sha256(contenido).hexdigest()}
    codigo, texto = _lanzar(datos, ejecutar, existe, terminal)
    olvidar()
    salida(texto or ("Hecho." if codigo == 0 else "No se pudo."))
    if codigo == 0 and accion != "quitar":
        salida("\nListo. Comprueba cuando quieras con:  lina privilegios")
    return codigo
