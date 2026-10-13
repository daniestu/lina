#!/usr/bin/env python3
"""Plataforma: en qué Linux estamos y cómo se instala algo en él.

El resto del asistente pide paquetes por un nombre LÓGICO («gtk-layer-shell», «ydotool»…) y este módulo lo traduce al paquete real de cada
familia de distribuciones y usa su gestor (pacman, apt, dnf, zypper). Así el asistente puede instalar lo que necesita en cualquier Linux.
Para añadir una distribución o un paquete basta con tocar las tablas FAMILIAS y PAQUETES.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

# gestor de paquetes y orden para instalar sin preguntar, por familia
FAMILIAS = {
    "arch":   {"gestor": "pacman", "instalar": ["pacman", "-S", "--noconfirm", "--needed", "--noprogressbar"]},
    "debian": {"gestor": "apt-get", "instalar": ["apt-get", "install", "-y", "--no-install-recommends"]},
    "fedora": {"gestor": "dnf", "instalar": ["dnf", "install", "-y"]},
    "suse":   {"gestor": "zypper", "instalar": ["zypper", "--non-interactive", "install", "--no-recommends"]},
}
# ID de /etc/os-release (o de ID_LIKE) -> familia
_IDS = {"arch": "arch", "cachyos": "arch", "endeavouros": "arch", "manjaro": "arch", "garuda": "arch", "artix": "arch", "arcolinux": "arch",
        "debian": "debian", "ubuntu": "debian", "linuxmint": "debian", "pop": "debian", "elementary": "debian", "zorin": "debian", "kali": "debian", "neon": "debian",
        "fedora": "fedora", "rhel": "fedora", "centos": "fedora", "rocky": "fedora", "almalinux": "fedora", "nobara": "fedora",
        "opensuse": "suse", "suse": "suse", "opensuse-tumbleweed": "suse", "opensuse-leap": "suse"}

# nombre lógico -> paquete de cada familia (None = no existe en los repositorios oficiales de esa familia)
PAQUETES = {
    "gtk3":            {"arch": "gtk3", "debian": "gir1.2-gtk-3.0", "fedora": "gtk3", "suse": "typelib-1_0-Gtk-3_0"},
    "gtk-layer-shell": {"arch": "gtk-layer-shell", "debian": "gir1.2-gtklayershell-0.1", "fedora": "gtk-layer-shell", "suse": "typelib-1_0-GtkLayerShell-0_1"},
    "pygobject":       {"arch": "python-gobject", "debian": "python3-gi", "fedora": "python3-gobject", "suse": "python3-gobject"},
    "pycairo":         {"arch": "python-cairo", "debian": "python3-gi-cairo", "fedora": "python3-cairo", "suse": "python3-cairo"},
    "ydotool":         {"arch": "ydotool", "debian": "ydotool", "fedora": "ydotool", "suse": "ydotool"},
    "spectacle":       {"arch": "spectacle", "debian": "kde-spectacle", "fedora": "spectacle", "suse": "spectacle"},
    "playerctl":       {"arch": "playerctl", "debian": "playerctl", "fedora": "playerctl", "suse": "playerctl"},
    "libnotify":       {"arch": "libnotify", "debian": "libnotify-bin", "fedora": "libnotify", "suse": "libnotify-tools"},
}


def leer_os_release(ruta="/etc/os-release"):
    d = {}
    try:
        for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, _, v = linea.partition("=")
                d[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return d


def familia_de(os_release):
    """'arch' | 'debian' | 'fedora' | 'suse' | None según ID e ID_LIKE."""
    ids = [os_release.get("ID", "").lower()] + os_release.get("ID_LIKE", "").lower().split()
    for i in ids:
        if i in _IDS:
            return _IDS[i]
    return None


def detectar(os_release=None, entorno=None, which=shutil.which):
    """{'distro', 'familia', 'gestor', 'escritorio', 'sesion', 'tiene_gestor'} del sistema actual."""
    osr = os_release if os_release is not None else leer_os_release()
    env = entorno if entorno is not None else os.environ
    fam = familia_de(osr)
    gestor = FAMILIAS[fam]["gestor"] if fam else None
    return {"distro": osr.get("PRETTY_NAME") or osr.get("NAME") or "Linux", "familia": fam, "gestor": gestor,
            "tiene_gestor": bool(gestor and which(gestor)),
            "escritorio": (env.get("XDG_CURRENT_DESKTOP") or "").lower(),
            "sesion": (env.get("XDG_SESSION_TYPE") or "").lower()}


def nombres_reales(logicos, familia):
    """(paquetes_reales, sin_paquete): traduce nombres lógicos; los que no existen en esa familia van aparte."""
    reales, faltan = [], []
    for n in logicos:
        p = PAQUETES.get(n, {}).get(familia) if n in PAQUETES else n      # un nombre que no está en la tabla se toma tal cual
        (reales if p else faltan).append(p or n)
    return list(dict.fromkeys(reales)), faltan


def orden_instalar(logicos, familia):
    """['sudo','-n', …] para instalar esos paquetes sin preguntar, o None si la familia no se conoce."""
    if familia not in FAMILIAS:
        return None
    reales, _ = nombres_reales(logicos, familia)
    return ["sudo", "-n", *FAMILIAS[familia]["instalar"], *reales]


def manual(logicos, familia):
    """La orden para que el usuario lo haga a mano (sale en los avisos)."""
    o = orden_instalar(logicos, familia)
    if not o:
        return "instala con el gestor de tu distribución: " + ", ".join(logicos)
    return "sudo " + " ".join(o[2:])


def instalar(logicos, log=print, ejecutar=subprocess.run, plataforma=None, marca=None, ahora=time.time, horas=24, tiempo=600):
    """Instala esos paquetes con el gestor de la distribución (sudo sin contraseña). Devuelve True si lo ha conseguido.
    No insiste: si lo intentó hace menos de «horas», no lo repite (la marca es un archivo con la hora del último intento)."""
    p = plataforma or detectar()
    fam = p.get("familia")
    if not fam or not p.get("tiene_gestor", True):
        log("Faltan paquetes (" + ", ".join(logicos) + ") y no reconozco el gestor de esta distribución: instálalos a mano")
        return False
    if marca is not None:
        try:
            if ahora() - float(Path(marca).read_text().strip()) < horas * 3600:
                return False
        except (OSError, ValueError):
            pass
        try:
            Path(marca).parent.mkdir(parents=True, exist_ok=True)
            Path(marca).write_text(str(ahora()))
        except OSError:
            pass
    reales, sin = nombres_reales(logicos, fam)
    if sin:
        log("En " + p.get("distro", fam) + " no hay paquete oficial para: " + ", ".join(sin))
    try:
        if ejecutar(["sudo", "-n", "true"], capture_output=True, timeout=10).returncode != 0:
            log("Faltan paquetes y sudo pide contraseña, así que no puedo instalarlos solo. A mano:  " + manual(logicos, fam))
            return False
        log("Instalando " + ", ".join(reales) + " con " + FAMILIAS[fam]["gestor"] + "…")
        r = ejecutar(orden_instalar(logicos, fam), capture_output=True, text=True, timeout=tiempo)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"No he podido instalar los paquetes ({e})")
        return False
    if r.returncode != 0:
        log(FAMILIAS[fam]["gestor"] + " no ha podido instalarlos: " + ((r.stderr or r.stdout or "").strip().splitlines() or ["sin detalle"])[-1][:200])
        return False
    log("Paquetes instalados")
    return True


if __name__ == "__main__":
    d = detectar()
    print(f"Distribución: {d['distro']} · familia: {d['familia'] or 'desconocida'} · gestor: {d['gestor'] or '—'} ({'instalado' if d['tiene_gestor'] else 'no encontrado'})")
    print(f"Escritorio: {d['escritorio'] or '—'} · sesión: {d['sesion'] or '—'}")
