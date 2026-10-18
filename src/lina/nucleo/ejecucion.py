# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Ejecución sencilla de órdenes (sin shell) y utilidades de rutas; lo comparten la red de seguridad y las herramientas."""
import os
import re
import subprocess

from lina.nucleo.clasificador import _HOME, _normalizar_ruta


def _abs(ruta):
    """Ruta absoluta y limpia (~, $HOME, relativas a tu carpeta personal, '..')."""
    ruta = _normalizar_ruta(str(ruta))
    if not ruta.startswith("/"):
        ruta = _HOME + "/" + ruta
    return os.path.normpath(ruta)


def _privilegios():
    return [] if os.geteuid() == 0 else ["sudo", "-n"]


def _ejecutar_simple(argv, timeout=15, entrada=None):
    """Un comando de comprobación o de deshacer, sin shell. Devuelve (código, salida) o (None, motivo) si no se pudo ejecutar."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=entrada, errors="replace",
                           env=dict(os.environ, LC_ALL="C.UTF-8", TERM="dumb"))
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)


def _como_root(argv, **k):
    return _ejecutar_simple([*_privilegios(), *argv], **k)


def _codigo_de_salida(resultado):
    m = re.match(r"código de salida: (-?\d+)", str(resultado))
    return int(m.group(1)) if m else None
