# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9: aislar las órdenes de la IA con bwrap (diseño en docs/aislamiento.md).

El filtro de texto (clasificador.py, herramientas.py, politica.txt) sigue decidiendo qué se confirma y qué se bloquea; esto es la segunda capa, para lo que
el filtro deja pasar por error. La orden corre con todo el sistema de solo lectura y, en tu carpeta personal:
  · escribible lo normal (documentos, configuración de programas, la papelera, las cachés);
  · TAPADO del todo (ni se lee ni se escribe) lo que tiene claves y los datos de Lina: lo mismo que protege clasificador._RUTAS_PROTEGIDAS;
  · de SOLO LECTURA lo que deja algo arrancando solo (los archivos de inicio de la shell, autostart, servicios de usuario, ~/.local/bin…), salvo en una
    orden que confirmaste: el aislamiento sigue a tu permiso, no lo sustituye.
En una tarea que ha leído contenido de fuera, además, sin red (ni DNS por el socket de systemd-resolved) y sin bus de sesión ni del sistema.

Este módulo solo construye la orden y dice si se puede aislar; quien la usa es Ejecutor.ejecutar (S9c), según ia.aislar (S9b).
"""
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from lina.nucleo.clasificador import _RUTAS_PROTEGIDAS

# Lo que deja algo arrancando solo (sección «persistencia» de politica.txt) y ~/.local/bin (un programa ahí se ejecuta luego por su nombre)
SOLO_LECTURA = (".bashrc", ".bash_profile", ".bash_login", ".profile", ".zshrc", ".zshenv", ".zprofile", ".config/fish", ".config/autostart",
                ".config/systemd/user", ".config/environment.d", ".config/plasma-workspace/env", ".local/share/vulkan", ".config/vulkan", ".local/bin")
# Los datos de Lina siguen tapados incluso en una orden confirmada: la IA no los toca nunca, ni con tu «sí»
DE_LINA = (".config/lina", ".local/state/lina", ".local/share/lina")
# Sin red también hay que cerrar estos sockets: por systemd-resolved se resuelven nombres (un nombre puede llevar datos) y los buses llegan a todo
SIN_RED_TAMBIEN = ("/run/systemd/resolve", "/run/nscd")
BUS_DEL_SISTEMA = "/run/dbus/system_bus_socket"


@dataclass
class Jaula:
    """Cómo se aísla una orden. `casa`: la carpeta personal (escribible salvo lo tapado y lo de solo lectura)."""
    casa: str
    red: bool = True
    bus: bool = True
    confirmada: bool = False
    escribibles: list[str] = field(default_factory=list)        # otras carpetas escribibles (el disco de datos con su papelera, /tmp va siempre)

    def tapadas(self):
        return [os.path.join(self.casa, r) for r in (DE_LINA if self.confirmada else _RUTAS_PROTEGIDAS)]

    def de_solo_lectura(self):
        return [] if self.confirmada else [os.path.join(self.casa, r) for r in SOLO_LECTURA]


def _tapar(ruta, existe=os.path.lexists):
    """Lo que tapa una ruta: una carpeta vacía encima si es carpeta; /dev/null encima si es un archivo o un socket. Si no existe, nada (para taparla habría
    que crearla en tu carpeta; la sigue vigilando el filtro de texto)."""
    if not existe(ruta):
        return []
    if os.path.isdir(ruta) and not os.path.islink(ruta):
        return ["--tmpfs", ruta]
    return ["--ro-bind", "/dev/null", ruta]


def orden(argv, jaula, existe=os.path.lexists):
    """La orden de bwrap que ejecuta `argv` dentro de `jaula`. El orden de los montajes importa: lo de después tapa a lo de antes."""
    o = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--bind", "/tmp", "/tmp", "--die-with-parent",
         "--bind", jaula.casa, jaula.casa]
    for ruta in jaula.escribibles:
        if existe(ruta):
            o += ["--bind", ruta, ruta]
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if jaula.bus and runtime and existe(runtime):
        o += ["--bind", runtime, runtime]                        # como hoy: PipeWire, Wayland y los programas que dejan ahí sus sockets
    for ruta in jaula.de_solo_lectura():
        if existe(ruta):
            o += ["--ro-bind", ruta, ruta]
    for ruta in jaula.tapadas():
        o += _tapar(ruta, existe)
    if not jaula.bus:
        for ruta in ([os.path.join(runtime, "bus")] if runtime else []) + [BUS_DEL_SISTEMA]:
            o += _tapar(ruta, existe)
    if not jaula.red:
        o.append("--unshare-net")
        for ruta in SIN_RED_TAMBIEN:
            o += _tapar(ruta, existe)
    return o + ["--"] + list(argv)


_DISPONIBLE: list = []


def disponible():
    """(sí o no, por qué no): ¿hay bwrap y funciona sin privilegios aquí? Se prueba una vez de verdad (una orden vacía, de solo lectura)."""
    if not _DISPONIBLE:
        _DISPONIBLE.append(_probar())
    return _DISPONIBLE[0]


def _probar():
    if not shutil.which("bwrap"):
        return False, "no está instalado bwrap (el paquete se llama bubblewrap)"
    try:
        r = subprocess.run(["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--", "true"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"bwrap no arranca ({type(e).__name__})"
    if r.returncode != 0:
        return False, ("bwrap no puede crear su espacio aislado: este sistema no deja usar espacios de nombres de usuario sin privilegios "
                       f"({(r.stderr or '').strip()[:120]})")
    return True, ""


def casa():
    return str(Path.home())
