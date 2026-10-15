"""La parte de `lina privilegios` que se ejecuta COMO ADMINISTRADOR. Es corta a propósito, para que se pueda leer entera antes de dar permiso.

Cómo se lanza: el usuario ve primero la vista previa de todo lo que se va a escribir y, solo si acepta, Lina ejecuta
    sudo (o pkexec) /usr/bin/python3 -I -c "<el texto de este archivo>; main()"      con los datos por la entrada estándar.
Así lo que se ejecuta es el texto que se mostró (no un archivo que otro proceso pudiera cambiar mientras escribes tu contraseña).

Solo puede hacer tres cosas, siempre en estas rutas fijas:
  instalar  →  el ayudante /usr/lib/lina/lina-instalar (root:root 755), la regla de sudoers que solo permite ese ayudante
               (/etc/sudoers.d/lina-instalar) y la política de polkit (/usr/share/polkit-1/actions/org.lina.instalar.policy)
  total     →  además, /etc/sudoers.d/lina-total: sudo sin contraseña para todo (nivel opcional, con aviso)
  quitar    →  borra esos archivos
Los textos de sudoers y de polkit los genera este archivo, nunca vienen en los datos. Antes de activar una regla de sudoers se valida con `visudo`.
"""
import hashlib
import json
import os
import pwd
import re
import subprocess
import sys

DIR_AYUDANTE = "/usr/lib/lina"
AYUDANTE = DIR_AYUDANTE + "/lina-instalar"
SUDOERS_INSTALAR = "/etc/sudoers.d/lina-instalar"
SUDOERS_TOTAL = "/etc/sudoers.d/lina-total"
POLKIT = "/usr/share/polkit-1/actions/org.lina.instalar.policy"
USUARIO_VALIDO = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
PYTHON = "/usr/bin/python3"


class Fallo(Exception):
    pass


def sudoers_instalar(usuario):
    return (f"# Creado por Lina (`lina privilegios instalar`). Permite a {usuario} instalar paquetes de los repositorios del sistema, y NADA más.\n"
            f"# Para quitarlo:  lina privilegios quitar\n"
            f"{usuario} ALL=(root) NOPASSWD: {AYUDANTE} instalar *\n")


def sudoers_total(usuario):
    return (f"# Creado por Lina (`lina privilegios total`). {usuario} puede ejecutar CUALQUIER orden como administrador sin contraseña.\n"
            f"# Para quitarlo:  lina privilegios quitar\n"
            f"{usuario} ALL=(root) NOPASSWD: ALL\n")


def politica_polkit():
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE policyconfig PUBLIC "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN" '
            '"http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">\n'
            '<policyconfig>\n'
            '  <action id="org.lina.instalar">\n'
            '    <description>Instalar paquetes para Lina</description>\n'
            '    <message>Lina quiere instalar paquetes de los repositorios de tu sistema</message>\n'
            '    <defaults><allow_any>no</allow_any><allow_inactive>no</allow_inactive><allow_active>auth_admin_keep</allow_active></defaults>\n'
            f'    <annotate key="org.freedesktop.policykit.exec.path">{AYUDANTE}</annotate>\n'
            '  </action>\n'
            '</policyconfig>\n')


def comprobar_ayudante(contenido):
    primera = contenido.split(b"\n", 1)[0]
    if primera != b"#!/usr/bin/python3 -I":
        raise Fallo("el ayudante no empieza por la línea esperada (#!/usr/bin/python3 -I)")
    if len(contenido) > 20000:
        raise Fallo("el ayudante es sospechosamente grande")


def _carpeta_segura(ruta, raiz, estricto):
    """Cada carpeta del camino (desde la raíz) debe ser de root, no ser un enlace y no poder escribirla nadie más: si no, otro usuario podría cambiar el ayudante."""
    actual = raiz.rstrip("/") or "/"
    partes = [p for p in ruta.strip("/").split("/") if p]
    for i in range(len(partes) + 1):
        c = os.path.join(raiz, *partes[:i]) if i else (raiz or "/")
        if not os.path.lexists(c):
            continue
        st = os.lstat(c)
        if os.path.islink(c):
            raise Fallo(f"{c} es un enlace simbólico")
        if estricto and (st.st_uid != 0 or st.st_mode & 0o022):
            raise Fallo(f"{c} no es solo de root (otro usuario podría cambiar lo que contiene)")


def _escribir(ruta, contenido, modo, raiz, estricto, validar=None):
    destino = os.path.join(raiz, ruta.lstrip("/"))
    carpeta = os.path.dirname(destino)
    _carpeta_segura(os.path.dirname(ruta), raiz, estricto)
    os.makedirs(carpeta, mode=0o755, exist_ok=True)
    _carpeta_segura(os.path.dirname(ruta), raiz, estricto)
    temporal = destino + ".nuevo"               # con punto: sudo ignora los archivos así hasta que se renombran
    if os.path.lexists(temporal):
        os.unlink(temporal)
    fd = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, modo)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporal, modo)
        if validar:
            validar(temporal)
        os.replace(temporal, destino)
    except BaseException:
        if os.path.lexists(temporal):
            os.unlink(temporal)
        raise


def _validar_sudoers(temporal, ejecutar=subprocess.run):
    visudo = next((p for p in ("/usr/sbin/visudo", "/usr/bin/visudo", "/sbin/visudo") if os.path.exists(p)), None)
    if not visudo:
        raise Fallo("no encuentro visudo para validar la regla; no activo nada")
    r = ejecutar([visudo, "-c", "-f", temporal], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise Fallo("visudo no da por buena la regla: " + (r.stdout + r.stderr).strip()[-300:])


def _quitar(ruta, raiz):
    destino = os.path.join(raiz, ruta.lstrip("/"))
    if os.path.lexists(destino):
        os.unlink(destino)
        return True
    return False


def aplicar(datos, raiz="/", estricto=True, validar_sudoers=_validar_sudoers, existe_usuario=None):
    """Hace lo que piden los datos (accion: instalar | total | quitar). Devuelve las líneas que se le cuentan al usuario."""
    accion = datos.get("accion")
    informe = []
    if accion == "quitar":
        for ruta in (SUDOERS_TOTAL, SUDOERS_INSTALAR, POLKIT, AYUDANTE):          # primero lo que da permisos, luego lo demás
            informe.append(("Borrado " if _quitar(ruta, raiz) else "No estaba ") + ruta)
        try:
            os.rmdir(os.path.join(raiz, DIR_AYUDANTE.lstrip("/")))             # la carpeta del ayudante, si ha quedado vacía
        except OSError:
            pass
        return informe
    if accion not in ("instalar", "total"):
        raise Fallo("acción desconocida")
    usuario = str(datos.get("usuario", ""))
    if not USUARIO_VALIDO.fullmatch(usuario):
        raise Fallo("nombre de usuario no válido")
    comprobar = existe_usuario or (lambda u: pwd.getpwnam(u).pw_uid >= 1000)
    try:
        if not comprobar(usuario):
            raise Fallo("ese usuario no es una persona (uid < 1000)")
    except KeyError:
        raise Fallo("ese usuario no existe")
    contenido = datos.get("ayudante", "")
    contenido = contenido.encode("utf-8") if isinstance(contenido, str) else bytes(contenido)
    comprobar_ayudante(contenido)
    if hashlib.sha256(contenido).hexdigest() != datos.get("sha256"):
        raise Fallo("el ayudante recibido no coincide con el que se enseñó")
    if not os.path.exists(os.path.join(raiz, PYTHON.lstrip("/"))):
        raise Fallo(f"no existe {PYTHON}")
    _escribir(AYUDANTE, contenido, 0o755, raiz, estricto)
    informe.append("Instalado " + AYUDANTE)
    try:
        _escribir(POLKIT, politica_polkit().encode(), 0o644, raiz, False)
        informe.append("Instalada la política de polkit " + POLKIT)
    except OSError as e:
        informe.append(f"No se pudo instalar la política de polkit ({e}); no es imprescindible")
    _escribir(SUDOERS_INSTALAR, sudoers_instalar(usuario).encode(), 0o440, raiz, False, validar_sudoers)
    informe.append("Activada la regla " + SUDOERS_INSTALAR + " (solo instalar paquetes)")
    if accion == "total":
        _escribir(SUDOERS_TOTAL, sudoers_total(usuario).encode(), 0o440, raiz, False, validar_sudoers)
        informe.append("ACTIVADO el nivel total: " + SUDOERS_TOTAL)
    return informe


def main():
    try:
        datos = json.loads(sys.stdin.buffer.read())
        if os.geteuid() != 0:
            raise Fallo("hay que ejecutarlo con permisos de administrador")
        for linea in aplicar(datos):
            print(linea)
        return 0
    except (Fallo, OSError, ValueError, subprocess.SubprocessError) as e:
        print(f"No se ha cambiado nada más: {e}", file=sys.stderr)
        return 1
