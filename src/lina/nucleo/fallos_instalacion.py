# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A15: cuando falla una instalación, por qué, en una frase que escribe el código.

Las instalaciones se lanzan con el idioma forzado a inglés (LC_ALL=C), así que la salida es la misma en cualquier sistema; aun así se reconocen las
frases en español de pacman por si algún paso (el ayudante de root) no hereda el idioma. Se miran HECHOS de la salida de la orden, nunca lo que dijo
el usuario. Caso real (2026-11-20): paru no podía bajar python-click (404 en todos los espejos) porque la lista de paquetes estaba desactualizada, y
Lina solo dijo «ha fallado una tarea»."""
import re
import shlex

from lina.nucleo.idioma import N_

LINEAS_DE_COLA = 40
MAX_COLA = 4000

# El gestor de cada orden de instalación: el primer programa (sin sudo ni rutas) que instala algo.
_INSTALA = {
    "pacman": lambda a: any(re.fullmatch(r"-S[a-z]*", x) and "s" not in x[2:] and "i" not in x[2:] for x in a) or "--sync" in a,
    "paru": lambda a: any(re.fullmatch(r"-S[a-z]*", x) and "s" not in x[2:] and "i" not in x[2:] for x in a),
    "yay": lambda a: any(re.fullmatch(r"-S[a-z]*", x) and "s" not in x[2:] and "i" not in x[2:] for x in a),
    "apt": lambda a: "install" in a, "apt-get": lambda a: "install" in a,
    "dnf": lambda a: "install" in a, "dnf5": lambda a: "install" in a,
    "zypper": lambda a: "install" in a or "in" in a,
    "flatpak": lambda a: "install" in a,
}
_PREFIJOS = {"sudo", "doas", "pkexec", "env", "nice", "ionice", "timeout"}


def gestor(comando):
    """El gestor de paquetes con el que instala esta orden («pacman», «paru», «apt»…), o None si no es una instalación. El ayudante de root de Lina
    («sudo -n /usr/lib/lina/lina-instalar instalar …») instala con el gestor del sistema: cuenta como el de la distribución."""
    for trozo in re.split(r"&&|\|\||;|\|", str(comando)):
        try:
            palabras = shlex.split(trozo)
        except ValueError:
            continue
        while palabras and (palabras[0] in _PREFIJOS or palabras[0].startswith("-") or re.match(r"^[A-Za-z_]\w*=", palabras[0])):
            palabras.pop(0)
        if len(palabras) >= 2 and palabras[1] == "instalar" and palabras[0].endswith("/lina-instalar"):
            from lina.nucleo import plataforma as PL
            return {"arch": "pacman", "debian": "apt", "fedora": "dnf", "suse": "zypper"}.get(PL.familia_actual())
        if not palabras:
            continue
        prog = palabras[0].rsplit("/", 1)[-1]
        if prog in _INSTALA and _INSTALA[prog](palabras[1:]):
            return prog
    return None


# (clave, expresión, frase con {paquete} si lo sabe). En orden: lo primero que encaje es el motivo.
_FALLOS = [
    ("bloqueada", r"unable to lock database|could not get lock|database is locked|holding the (?:yum|dnf) lock|system management is locked|"
                  r"no se pudo bloquear la base de datos",
     N_("otra instalación está en marcha, o se quedó a medias, y tiene bloqueado el sistema de paquetes")),
    ("espacio", r"not enough free disk space|no space left on device|you don't have enough free space|no hay suficiente espacio",
     N_("no queda espacio libre suficiente en el disco")),
    ("desactualizada", r"failed retrieving file|the requested url returned error: 404|404\s+not found|failed to retrieve some files|failed to fetch|"
                       r"status code: 404|curl error.*404|no se pudo obtener el archivo",
     N_("no se ha podido descargar {paquete}: casi siempre es porque la lista de paquetes del sistema está desactualizada")),
    ("no_existe", r"target not found|unable to locate package|no match for argument|no provider of|not found in (?:aur|repos)|"
                  r"no se encontró el objetivo",
     N_("{paquete} no está en los repositorios")),
    ("conflicto", r"conflicting files|exists in filesystem|trying to overwrite|conflictos de archivos|existe en el sistema de archivos",
     N_("un archivo del paquete ya existe en el sistema y choca con otro paquete")),
    ("dependencias", r"could not satisfy dependencies|unable to satisfy dependency|unresolvable package conflicts|held broken packages|nothing provides|"
                     r"no se pudieron satisfacer las dependencias",
     N_("sus dependencias no se pueden resolver con lo que hay instalado")),
    ("firma", r"invalid or corrupted package|signature from .* is (?:unknown trust|invalid|marginal trust)|could not be looked up remotely|"
              r"gpg check failed|no_pubkey|el paquete no es válido o está dañado",
     N_("la firma de un paquete no es válida; puede que falten o estén caducadas las claves de los repositorios")),
    ("compilacion", r"a failure occurred in (?:build|prepare|package|check)\(\)|error making:|failed to build",
     N_("ha fallado la compilación de un paquete del AUR")),
]
_PAQUETE = [r"failed retrieving file '([^']+)'", r"no se pudo obtener el archivo «([^»]+)»", r"target not found: (\S+)", r"no se encontró el objetivo: (\S+)",
            r"unable to locate package (\S+)", r"no match for argument: (\S+)", r"error making: (\S+)", r"failed to build (\S+)",
            r"Failed to fetch \S+/(\S+?\.deb)"]


def _nombre_de_paquete(archivo):
    """«python-click-8.5.0-1-any.pkg.tar.zst» → «python-click 8.5.0-1»; un nombre suelto, tal cual."""
    archivo = re.sub(r"\.sig$", "", archivo.strip().strip("'\""))
    m = re.fullmatch(r"(.+?)-(\d[^-]*-\d+)-(?:any|x86_64|aarch64|i686)\.pkg\.tar\.\w+", archivo)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = re.fullmatch(r"(.+?)_([^_]+)_\w+\.deb", archivo)
    return f"{m.group(1)} {m.group(2)}" if m else archivo


def motivo(salida):
    """(clave, frase en español sin traducir, paquete o «») del primer fallo conocido de la salida, o None si no reconoce ninguno."""
    texto = str(salida or "")
    bajo = texto.lower()
    for clave, patron, frase in _FALLOS:
        if re.search(patron, bajo):
            paquete = ""
            for p in _PAQUETE:
                m = re.search(p, texto, re.I)
                if m:
                    paquete = _nombre_de_paquete(m.group(1))
                    break
            return clave, frase, paquete
    return None


def cola(salida, lineas=LINEAS_DE_COLA, maximo=MAX_COLA):
    """Las últimas líneas de la salida, para el registro, sin pasar de `maximo` caracteres."""
    ultimas = "\n".join(str(salida or "").rstrip().splitlines()[-lineas:])
    return ultimas[-maximo:]


def orden_de_actualizar(gestor_de_la_orden):
    """La orden COMPLETA que refresca la lista de paquetes en cada sistema (en Arch, nunca -Sy a secas: dejaría el sistema a medias), o None."""
    return {"pacman": "sudo pacman -Syu --noconfirm", "paru": "sudo pacman -Syu --noconfirm", "yay": "sudo pacman -Syu --noconfirm",
            "apt": "sudo apt-get update", "apt-get": "sudo apt-get update", "dnf": "sudo dnf makecache --refresh",
            "dnf5": "sudo dnf makecache --refresh", "zypper": "sudo zypper --non-interactive refresh"}.get(gestor_de_la_orden)
