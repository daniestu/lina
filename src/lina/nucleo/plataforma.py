#!/usr/bin/env python3
"""Plataforma: en qué Linux estamos y cómo se gestionan sus paquetes.

Es el ÚNICO sitio que conoce pacman, apt, dnf y zypper. El resto del asistente pide cosas por un nombre LÓGICO («gtk-layer-shell», «ydotool»…) o
por una operación (instalar, quitar, actualizar, buscar, comprobar) y este módulo las traduce a la familia de distribuciones del equipo. Además
detecta lo que hay (arranque, audio, snapshots, GPU, escritorio, juegos…) en vez de suponerlo.
Para añadir una distribución o un paquete basta con tocar las tablas FAMILIAS, _IDS y PAQUETES.

Se puede forzar la familia con la variable LINA_DISTRO=arch|debian|fedora|suse (para derivadas que no se reconocen y para las pruebas).
"""
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# Todo lo que cambia de una familia a otra. Las órdenes van SIN sudo.
FAMILIAS = {
    "arch": {
        "gestor": "pacman",
        "instalar": ["pacman", "-S", "--noconfirm", "--needed", "--noprogressbar"],
        "quitar": ["pacman", "-Rns", "--noconfirm"],
        "actualizar": [["pacman", "-Syu", "--noconfirm"]],
        "refrescar": [["pacman", "-Sy"]],
        "buscar": ["pacman", "-Ss"],
        "texto_consultar": "pacman -Qs", "texto_buscar": "pacman -Ss", "texto_actualizar": "sudo pacman -Syu --noconfirm",
        "texto_refrescar": "sudo pacman -Syu --noconfirm", "texto_instalar": "sudo pacman -S --noconfirm --needed",
        "texto_externo": "AUR (paru)",
    },
    "debian": {
        "gestor": "apt-get",
        "instalar": ["apt-get", "install", "-y", "--no-install-recommends", "--no-remove"],
        "quitar": ["apt-get", "purge", "-y"],
        "actualizar": [["apt-get", "update"], ["apt-get", "upgrade", "-y"]],
        "refrescar": [["apt-get", "update"]],
        "buscar": ["apt-cache", "search"],
        "texto_consultar": "dpkg -l", "texto_buscar": "apt-cache search", "texto_actualizar": "sudo apt-get update && sudo apt-get upgrade -y",
        "texto_refrescar": "sudo apt-get update", "texto_instalar": "sudo apt-get install -y --no-install-recommends",
        "texto_externo": "PPA o repositorios de terceros",
    },
    "fedora": {
        "gestor": "dnf",
        "instalar": ["dnf", "install", "-y"],
        "quitar": ["dnf", "remove", "-y"],
        "actualizar": [["dnf", "upgrade", "-y", "--refresh"]],
        "refrescar": [["dnf", "makecache"]],
        "buscar": ["dnf", "search"],
        "texto_consultar": "rpm -qa", "texto_buscar": "dnf search", "texto_actualizar": "sudo dnf upgrade -y --refresh",
        "texto_refrescar": "sudo dnf makecache", "texto_instalar": "sudo dnf install -y",
        "texto_externo": "COPR o repositorios de terceros",
    },
    "suse": {
        "gestor": "zypper",
        "instalar": ["zypper", "--non-interactive", "install", "--no-recommends"],
        "quitar": ["zypper", "--non-interactive", "remove", "--clean-deps"],
        "actualizar": [["zypper", "--non-interactive", "update"]],
        "refrescar": [["zypper", "--non-interactive", "refresh"]],
        "buscar": ["zypper", "search"],
        "texto_consultar": "rpm -qa", "texto_buscar": "zypper search", "texto_actualizar": "sudo zypper --non-interactive update",
        "texto_refrescar": "sudo zypper --non-interactive refresh", "texto_instalar": "sudo zypper --non-interactive install --no-recommends",
        "texto_externo": "OBS o repositorios de terceros",
    },
}
# Sin familia reconocida, el texto para la IA habla en general
_GENERICO = {"texto_consultar": "el gestor de paquetes", "texto_buscar": "el gestor de paquetes", "texto_actualizar": "la actualización del sistema",
             "texto_refrescar": "refrescar las listas de paquetes", "texto_instalar": "el gestor de paquetes de tu distribución (con sudo)",
             "texto_externo": "repositorios de terceros"}

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
    "xclip":           {"arch": "xclip", "debian": "xclip", "fedora": "xclip", "suse": "xclip"},
    "xdotool":         {"arch": "xdotool", "debian": "xdotool", "fedora": "xdotool", "suse": "xdotool"},
    "xprop":           {"arch": "xorg-xprop", "debian": "x11-utils", "fedora": "xorg-x11-utils", "suse": "xprop"},
    "grim":            {"arch": "grim", "debian": "grim", "fedora": "grim", "suse": "grim"},
    "scrot":           {"arch": "scrot", "debian": "scrot", "fedora": "scrot", "suse": "scrot"},
    "gnome-screenshot": {"arch": "gnome-screenshot", "debian": "gnome-screenshot", "fedora": "gnome-screenshot", "suse": "gnome-screenshot"},
    "xfce4-screenshooter": {"arch": "xfce4-screenshooter", "debian": "xfce4-screenshooter", "fedora": "xfce4-screenshooter", "suse": "xfce4-screenshooter"},
    "wl-clipboard":    {"arch": "wl-clipboard", "debian": "wl-clipboard", "fedora": "wl-clipboard", "suse": "wl-clipboard"},
    "libreoffice":     {"arch": "libreoffice-fresh", "debian": "libreoffice-writer", "fedora": "libreoffice-writer", "suse": "libreoffice-writer"},
    "weasyprint":      {"arch": "python-weasyprint", "debian": "weasyprint", "fedora": "weasyprint", "suse": "python3-WeasyPrint"},
    "yt-dlp":          {"arch": "yt-dlp", "debian": "yt-dlp", "fedora": "yt-dlp", "suse": "yt-dlp"},
    "chromium":        {"arch": "chromium", "debian": "chromium", "fedora": "chromium", "suse": "chromium"},
    "nodejs":          {"arch": "nodejs", "debian": "nodejs", "fedora": "nodejs", "suse": "nodejs-default"},
    "npm":             {"arch": "npm", "debian": "npm", "fedora": "npm", "suse": "npm-default"},
    "libsecret":       {"arch": "libsecret", "debian": "libsecret-tools", "fedora": "libsecret", "suse": "libsecret-tools"},
    "portaudio":       {"arch": "portaudio", "debian": "libportaudio2", "fedora": "portaudio", "suse": "libportaudio2"},
    "flatpak":         {"arch": "flatpak", "debian": "flatpak", "fedora": "flatpak", "suse": "flatpak"},
    "mangohud":        {"arch": "mangohud", "debian": "mangohud", "fedora": "mangohud", "suse": "mangohud"},
    "gamemode":        {"arch": "gamemode", "debian": "gamemode", "fedora": "gamemode", "suse": "gamemode"},
    "python-venv":     {"arch": "python", "debian": "python3-venv", "fedora": "python3", "suse": "python3"},
    "python-pip":      {"arch": "python-pip", "debian": "python3-pip", "fedora": "python3-pip", "suse": "python3-pip"},
    "python-dev":      {"arch": "python", "debian": "python3-dev", "fedora": "python3-devel", "suse": "python3-devel"},
    "gcc":             {"arch": "gcc", "debian": "build-essential", "fedora": "gcc", "suse": "gcc"},
    "git":             {"arch": "git", "debian": "git", "fedora": "git", "suse": "git"},
    "snapper":         {"arch": "snapper", "debian": "snapper", "fedora": "snapper", "suse": "snapper"},
}


_cache_osr: dict = {}


def leer_os_release(ruta="/etc/os-release"):
    """Lo que dice /etc/os-release (se lee de nuevo solo si el archivo cambia: se pregunta mucho por la familia)."""
    try:
        marca = os.stat(ruta).st_mtime_ns
    except OSError:
        marca = None
    if _cache_osr.get(ruta, (None,))[0] == marca and ruta in _cache_osr:
        return dict(_cache_osr[ruta][1])
    d = _leer_os_release(ruta)
    _cache_osr[ruta] = (marca, d)
    return dict(d)


def _leer_os_release(ruta):
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
    forzada = (env.get("LINA_DISTRO") or "").strip().lower()
    if forzada in FAMILIAS:
        fam = forzada                                   # derivada no reconocida, o pruebas
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


# Lo que hace falta del sistema para instalar Lina (los compiladores son para `evdev`, que se compila al instalarlo)
PAQUETES_BASE = ("python-venv", "python-pip", "python-dev", "gcc", "git", "portaudio", "libnotify")


def faltan(logicos, familia=None, ejecutar=None):
    """Los nombres lógicos cuyo paquete NO está instalado (lo comprueba con el gestor de la familia). Los que esta familia no tiene se ignoran."""
    fam = familia or familia_actual()
    ejecutar = ejecutar or (lambda a: _correr(a, 15))
    out = []
    for n in logicos:
        real = PAQUETES.get(n, {}).get(fam, n) if n in PAQUETES else n
        c = consulta_instalado(real, fam)
        if c and interpreta_instalado(*ejecutar(c), familia=fam) is not True:
            out.append(n)
    return out


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


# ======================= OPERACIONES DE PAQUETES =======================
def familia_actual(entorno=None):
    """La familia de este equipo ('arch'|'debian'|'fedora'|'suse'|None)."""
    return detectar(entorno=entorno, which=lambda _: None)["familia"]


def orden(operacion, nombres=(), familia=None):
    """Orden (sin sudo) de una operación de paquetes: 'instalar', 'quitar', 'buscar' o 'refrescar'. Una lista de argumentos, o None si la familia
    no se conoce. 'actualizar' devuelve LISTA de órdenes (apt necesita dos), así que va en ordenes_actualizar."""
    fam = familia or familia_actual()
    if fam not in FAMILIAS or operacion not in ("instalar", "quitar", "buscar"):
        return None
    reales, _ = nombres_reales(list(nombres), fam) if operacion == "instalar" else (list(nombres), [])
    return [*FAMILIAS[fam][operacion], *reales]


def ordenes_actualizar(familia=None, refrescar_solo=False):
    """[[orden], …] (sin sudo) para actualizar todo el sistema, o solo refrescar las listas."""
    fam = familia or familia_actual()
    if fam not in FAMILIAS:
        return None
    return [list(o) for o in FAMILIAS[fam]["refrescar" if refrescar_solo else "actualizar"]]


def texto_para_ia(texto, familia=None):
    """Sustituye en un texto de instrucciones los marcadores @@instalar@@, @@buscar@@, @@consultar@@, @@actualizar@@, @@refrescar@@ y @@externo@@
    por las órdenes de ESTA distribución (así los prompts no hablan de pacman en una Fedora)."""
    fam = familia if familia is not None else familia_actual()
    tabla = FAMILIAS.get(fam, _GENERICO)
    return re.sub(r"@@(\w+)@@", lambda m: tabla.get("texto_" + m.group(1), m.group(0)), texto)


# gestor -> (familia, rol): lo que Lina reconoce en una orden escrita por la IA
_GESTORES = {"pacman": "arch", "paru": "arch", "yay": "arch", "pikaur": "arch", "aurman": "arch",
             "apt": "debian", "apt-get": "debian", "aptitude": "debian", "dpkg": "debian",
             "dnf": "fedora", "dnf5": "fedora", "yum": "fedora", "microdnf": "fedora", "rpm": "fedora",
             "zypper": "suse"}
GESTORES_PAQUETES = frozenset(_GESTORES)
AYUDANTES_AUR = frozenset({"paru", "yay", "pikaur", "aurman"})
_ENTRADA_INSTALAR = {"arch": {"pacman"}, "debian": {"apt", "apt-get"}, "fedora": {"dnf", "dnf5", "yum"}, "suse": {"zypper"}}
_BANDERAS_INSTALAR = {
    "arch": {"-S", "--noconfirm", "--needed", "--noprogressbar", "--color=never"},
    "debian": {"install", "-y", "--yes", "--assume-yes", "-q", "-qq", "--no-install-recommends"},
    "fedora": {"install", "-y", "--assumeyes", "-q"},
    "suse": {"install", "in", "-y", "--no-confirm", "--non-interactive", "-n", "--no-recommends"},
}
_VERBO_INSTALAR = {"arch": "-S", "debian": "install", "fedora": "install", "suse": "install"}
_NOMBRE_PAQUETE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}")
_NOMBRE_ARCH = re.compile(r"([a-z][a-z0-9_-]*/)?[a-z0-9@._+-]+")


def paquetes_a_instalar(tokens, familia=None):
    """Si estas palabras (SIN 'sudo') son una instalación sencilla con el gestor de esta distribución, la lista de nombres; si no, None.
    Solo nombres de los repositorios: nada de archivos, URLs, versiones, grupos ni opciones raras."""
    fam = familia or familia_actual()
    if fam not in FAMILIAS or not tokens or tokens[0] not in _ENTRADA_INSTALAR[fam]:
        return None
    resto = tokens[1:]
    if fam == "arch":
        if resto.count("-S") != 1:
            return None
    elif sum(1 for a in resto if a in ("install", "in")) != 1:
        return None
    if fam in ("debian", "fedora", "suse"):                     # el verbo, antes que los nombres (zypper admite opciones globales delante)
        pos = next(i for i, a in enumerate(resto) if a in ("install", "in"))
        if any(not a.startswith("-") for a in resto[:pos]):
            return None
    nombres = []
    for a in resto:
        if a in _BANDERAS_INSTALAR[fam]:
            continue
        if a.startswith("-"):
            return None
        patron = _NOMBRE_ARCH if fam == "arch" else _NOMBRE_PAQUETE
        if not patron.fullmatch(a) or (fam != "arch" and (a.endswith("-") or ".." in a)):
            return None
        nombres.append(a)
    return nombres or None


def orden_canonica_instalar(nombres, familia=None):
    """La orden de instalación 'de siempre' (con sudo), en forma que paquetes_a_instalar vuelve a reconocer."""
    fam = familia or familia_actual()
    if fam not in FAMILIAS:
        return "sudo " + " ".join(nombres)
    return "sudo " + " ".join([*FAMILIAS[fam]["instalar"], *nombres]).replace(" --no-remove", "")


_CONSULTAS = {      # verbos / opciones que solo MIRAN
    "apt": {"search", "show", "list", "policy", "depends", "rdepends", "showpkg", "madison", "changelog"},
    "dnf": {"search", "info", "list", "repoquery", "provides", "whatprovides", "check-update", "repolist", "deplist", "help", "updateinfo"},
    "zypper": {"search", "se", "info", "if", "what-provides", "wp", "packages", "pa", "patterns", "pt", "products", "pd", "lr", "repos", "list-updates", "lu",
               "patch-check", "pchk", "versioncmp", "vcmp", "licenses", "needs-rebooting", "ps", "help"},
}


def interpretar(base, args):
    """(operación, nombres) de una orden de un gestor de paquetes: 'instalar', 'quitar', 'actualizar' (todo el sistema), 'refrescar', 'local' (un archivo
    suelto), 'consulta' o None si no se entiende. Sirve para pacman/paru/yay, apt/apt-get/aptitude/dpkg, dnf/yum y zypper/rpm."""
    base = os.path.basename(str(base))
    fam = _GESTORES.get(base)
    args = [str(a) for a in args]
    if fam is None:
        return None, []
    sin_opc = [a for a in args if not a.startswith("-")]
    letras = "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))
    if fam == "arch":
        nombres = [re.sub(r"^[\w.-]+/", "", a) for a in sin_opc]
        if "R" in letras or "--remove" in args:
            return "quitar", nombres
        if "U" in letras or "--upgrade" in args:
            return "local", nombres
        if "S" in letras or "--sync" in args:
            if "u" in letras and not nombres or "--sysupgrade" in args and not nombres:
                return "actualizar", []
            if "s" in letras or "i" in letras or "l" in letras or "g" in letras:
                return "consulta", nombres
            return "instalar", nombres
        if "F" in letras and "y" in letras:
            return "refrescar", []
        if "Q" in letras or "F" in letras or "T" in letras or "--query" in args or "--files" in args:
            return "consulta", nombres
        return None, []
    if base == "dpkg":
        if any(a in ("-i", "--install", "--unpack") for a in args):
            return "local", sin_opc
        if any(a in ("-r", "--remove", "-P", "--purge") for a in args):
            return "quitar", sin_opc
        if any(a in ("-l", "-L", "-s", "-S", "-p", "--list", "--listfiles", "--status", "--search", "--print-avail", "--get-selections") for a in args):
            return "consulta", sin_opc
        return None, []
    if base == "rpm":
        if any(re.fullmatch(r"-[a-zA-Z]*[qV][a-zA-Z]*", a) or a.startswith(("--query", "--verify")) for a in args):
            return "consulta", sin_opc                      # «rpm -qi» pregunta, no instala
        if any(re.fullmatch(r"-[a-zA-Z]*[iUF][a-zA-Z]*", a) or a in ("--install", "--upgrade", "--freshen") for a in args):
            return "local", sin_opc
        if any(re.fullmatch(r"-[a-zA-Z]*e[a-zA-Z]*", a) or a == "--erase" for a in args):
            return "quitar", sin_opc
        return None, []
    verbo = sin_opc[0] if sin_opc else ""
    nombres = sin_opc[1:]
    if any("/" in n or n.endswith((".deb", ".rpm")) or n.startswith(("http:", "https:", "ftp:")) for n in nombres) and verbo in ("install", "in", "reinstall", "localinstall", "upgrade", "update", "up"):
        return "local", nombres
    if fam == "debian":
        limpios = [re.split(r"[=/]", n)[0].rstrip("+-") for n in nombres]          # «paquete=versión», «paquete/rama», «paquete-» (quita), «paquete+» (instala)
        if verbo in ("install", "reinstall"):
            if any(n.endswith("-") for n in nombres):
                return "quitar", limpios                    # «apt install a b-» QUITA b: se trata como lo más delicado
            return "instalar", limpios
        if verbo in ("remove", "purge", "autoremove", "autopurge", "erase"):
            return "quitar", limpios
        if verbo in ("upgrade", "full-upgrade", "dist-upgrade", "safe-upgrade") and not nombres:
            return "actualizar", []
        if verbo == "update" and base != "aptitude":
            return "refrescar", []
        if verbo in _CONSULTAS["apt"]:
            return "consulta", nombres
        return None, []
    if fam == "fedora":
        if verbo in ("install", "reinstall", "localinstall", "swap", "downgrade"):
            return "instalar", nombres
        if verbo in ("remove", "erase", "autoremove", "rm"):
            return "quitar", nombres
        if verbo in ("upgrade", "update", "distro-sync", "dsync", "system-upgrade", "upgrade-minimal") and not nombres:
            return "actualizar", []
        if verbo in ("upgrade", "update"):
            return "instalar", nombres
        if verbo in ("makecache", "clean"):
            return "refrescar", []
        if verbo in _CONSULTAS["dnf"]:
            return "consulta", nombres
        return None, []
    if fam == "suse":
        if verbo in ("install", "in"):
            return "instalar", nombres
        if verbo in ("remove", "rm"):
            return "quitar", nombres
        if verbo in ("update", "up", "dist-upgrade", "dup", "patch") and not nombres:
            return "actualizar", []
        if verbo in ("update", "up"):
            return "instalar", nombres
        if verbo in ("refresh", "ref"):
            return "refrescar", []
        if verbo in _CONSULTAS["zypper"]:
            return "consulta", nombres
        return None, []
    return None, []


def es_consulta(base, args):
    """¿Solo mira (buscar, listar, comprobar)? Entonces no pide confirmación ni snapshot."""
    return interpretar(base, args)[0] == "consulta"


_ACTUALIZAR_TODO = re.compile(
    r"\b(?:pacman|paru|yay)\s+(?:--\w+\s+)*-\w*S\w*u|\b(?:pacman|paru|yay)\s+(?:--\w+\s+)*(?:-\w*u\w*S|--sysupgrade)|"
    r"\b(?:apt|apt-get|aptitude)\s+(?:-\S+\s+)*(?:full-upgrade|dist-upgrade|safe-upgrade|upgrade)\s*(?:-\S+\s*)*(?:$|[;&|])|"
    r"\b(?:dnf|dnf5|yum|microdnf)\s+(?:-\S+\s+)*(?:upgrade|update|distro-sync|upgrade-minimal)\s*(?:-\S+\s*)*(?:$|[;&|])|"
    r"\bzypper\s+(?:-\S+\s+)*(?:update|up|dist-upgrade|dup)\s*(?:-\S+\s*)*(?:$|[;&|])")


def es_actualizacion_completa(comando):
    """¿Actualiza TODO el sistema? (pacman -Syu, apt upgrade, dnf upgrade, zypper dup…)"""
    return bool(_ACTUALIZAR_TODO.search(str(comando)))


# ----- comprobar e investigar paquetes -----
def consulta_instalado(nombre, familia=None):
    """Orden (sin sudo) que dice si un paquete está instalado; se interpreta con interpreta_instalado."""
    fam = familia or familia_actual()
    if fam == "arch":
        return ["pacman", "-Qq", nombre]
    if fam == "debian":
        return ["dpkg-query", "-W", "-f=${db:Status-Abbrev}", nombre]
    if fam in ("fedora", "suse"):
        return ["rpm", "-q", nombre]
    return None


def interpreta_instalado(codigo, salida, familia=None):
    """True / False / None (no se sabe) según la salida de consulta_instalado."""
    fam = familia or familia_actual()
    if codigo is None or fam not in FAMILIAS:
        return None
    if fam == "debian":
        return codigo == 0 and salida.strip().startswith("ii")
    return codigo == 0


def esta_instalado(nombre, ejecutar):
    """ejecutar(argv) -> (codigo, salida). True/False/None."""
    c = consulta_instalado(nombre)
    if not c:
        return None
    codigo, salida = ejecutar(c)
    return interpreta_instalado(codigo, salida or "")


def consulta_quien_trae(regex_programa, familia=None):
    """(orden, necesita_sincronizar) para saber qué paquete trae un programa, o None si esta distribución no tiene forma sencilla.
    regex_programa es una expresión regular (ya escapada) del nombre del ejecutable."""
    fam = familia or familia_actual()
    if fam == "arch":
        return ["pacman", "-Fx", rf"^usr/(local/)?s?bin/{regex_programa}$"]
    if fam == "debian":
        return ["apt-file", "search", "--regexp", rf"^/usr/(local/)?s?bin/{regex_programa}$"] if shutil.which("apt-file") else None
    if fam in ("fedora", "suse"):
        return None
    return None


def sincronizar_archivos(familia=None):
    """Orden (con privilegios) que baja la lista de archivos de los paquetes, o None."""
    fam = familia or familia_actual()
    return {"arch": ["pacman", "-Fy"], "debian": ["apt-file", "update"]}.get(fam)


def pares_que_traen(salida, familia=None):
    """[(paquete, programa)] a partir de la salida de consulta_quien_trae."""
    fam = familia or familia_actual()
    pares, paquete = [], None
    for linea in salida.splitlines():
        if fam == "arch":
            m = re.match(r"^([\w.+-]+)/([\w.@+-]+) ", linea)
            if m:
                paquete = m.group(2)
                continue
            m = re.match(r"^\s+usr/(?:local/)?s?bin/([\w.+-]+)\s*$", linea)
            if m and paquete:
                pares.append((paquete, m.group(1)))
        elif fam == "debian":
            m = re.match(r"^([\w.+-]+): /usr/(?:local/)?s?bin/([\w.+-]+)\s*$", linea)
            if m:
                pares.append((m.group(1), m.group(2)))
    return list(dict.fromkeys(pares))[:8]


# ======================= CAPACIDADES DEL EQUIPO =======================
def _existe(ruta):
    return os.path.exists(ruta)


def detectar_init(existe=_existe, leer=lambda r: Path(r).read_text(encoding="utf-8", errors="replace")):
    """'systemd' | 'openrc' | 'runit' | 's6' | 'otro'."""
    if existe("/run/systemd/system"):
        return "systemd"
    try:
        comm = leer("/proc/1/comm").strip()
    except OSError:
        comm = ""
    if comm == "systemd":
        return "systemd"
    if existe("/run/openrc") or comm == "openrc-init":
        return "openrc"
    if comm == "runit" or existe("/run/runit"):
        return "runit"
    return "otro"


def detectar_audio(which=shutil.which, ejecutar=None):
    """'pipewire' | 'pulseaudio' | None."""
    ejecutar = ejecutar or (lambda a: _correr(a, 5))
    if which("pactl"):
        codigo, salida = ejecutar(["pactl", "info"])
        if codigo == 0:
            return "pipewire" if "pipewire" in salida.lower() else "pulseaudio"
    if which("wpctl") or which("pw-cli"):
        return "pipewire"
    if which("pulseaudio"):
        return "pulseaudio"
    return None


def detectar_snapshots(which=shutil.which, existe=_existe):
    """'snapper' | 'timeshift' | None."""
    if which("snapper") and existe("/etc/snapper/configs/root"):
        return "snapper"
    if which("timeshift"):
        return "timeshift"
    return None


def detectar_arranque(existe=_existe):
    """'limine' | 'grub' | 'systemd-boot' | 'refind' | None."""
    if existe("/etc/default/limine") or existe("/boot/limine.conf") or existe("/boot/EFI/limine"):
        return "limine"
    if existe("/boot/loader/loader.conf") or existe("/efi/loader/loader.conf") or existe("/boot/efi/loader/loader.conf"):
        return "systemd-boot"
    if existe("/boot/grub/grub.cfg") or existe("/boot/grub2/grub.cfg") or existe("/etc/default/grub"):
        return "grub"
    if existe("/boot/EFI/refind") or existe("/boot/efi/EFI/refind") or existe("/efi/EFI/refind"):
        return "refind"
    return None


_VENDEDORES_GPU = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}


def detectar_gpu(listar=None, leer=None):
    """Lista de GPUs ('nvidia', 'amd', 'intel'…) leyendo /sys/class/drm."""
    base = Path("/sys/class/drm")
    try:
        tarjetas = sorted(listar() if listar else [p for p in base.iterdir() if re.fullmatch(r"card\d+", p.name)])
    except OSError:
        return []
    out = []
    for t in tarjetas:
        try:
            v = (leer(t) if leer else (Path(t) / "device" / "vendor").read_text()).strip().lower()
        except OSError:
            continue
        nombre = _VENDEDORES_GPU.get(v, v)
        if nombre not in out:
            out.append(nombre)
    return out


OPCIONALES = {          # módulo opcional -> programa que lo delata
    "steam": "steam", "heroic": "heroic", "lutris": "lutris", "mangohud": "mangohud", "gamemode": "gamemoderun",
    "flatpak": "flatpak", "copias": None,
}
_COPIAS = ("restic", "borg", "timeshift", "kopia", "rsnapshot")


def detectar_opcionales(which=shutil.which):
    """{'steam': True, …}: qué módulos opcionales hay. Lo que no está se omite sin quejarse."""
    out = {k: bool(v and which(v)) for k, v in OPCIONALES.items() if k != "copias"}
    out["copias"] = [c for c in _COPIAS if which(c)]
    return out


def _correr(argv, tiempo=5):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=tiempo, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return None, ""


def capacidades(os_release=None, entorno=None, which=shutil.which, existe=_existe):
    """Todo lo que Lina necesita saber del equipo, leído (no supuesto)."""
    d = detectar(os_release=os_release, entorno=entorno, which=which)
    d.update({"init": detectar_init(existe=existe), "audio": detectar_audio(which=which), "snapshots": detectar_snapshots(which=which, existe=existe),
              "arranque": detectar_arranque(existe=existe), "gpu": detectar_gpu(), "opcionales": detectar_opcionales(which=which),
              "ayudante_aur": next((h for h in ("paru", "yay") if d["familia"] == "arch" and which(h)), None)})
    return d


def describir(caps=None):
    """Líneas de texto con los datos del sistema para la IA (sin suponer distribución ni escritorio)."""
    c = caps or capacidades()
    l = [f"Distribución: {c['distro']}" + (f" (familia {c['familia']})" if c["familia"] else " (familia no reconocida)") + "."]
    if c.get("gestor"):
        extra = [] if not c.get("ayudante_aur") else [f"{c['ayudante_aur']} para el AUR"]
        if c["opcionales"].get("flatpak"):
            extra.append("flatpak")
        l.append(f"Gestores de paquetes: {c['gestor']} (repositorios oficiales) es el principal" + "".join(", " + e for e in extra) + ".")
    if c.get("escritorio") or c.get("sesion"):
        l.append(f"Escritorio: {c.get('escritorio') or 'desconocido'}; sesión: {c.get('sesion') or 'desconocida'}.")
    l.append(f"Servicios: {c['init']}" + (f"; audio: {c['audio']}" if c.get("audio") else "") + (f"; arranque: {c['arranque']}" if c.get("arranque") else "")
             + (f"; gráfica: {', '.join(c['gpu'])}" if c.get("gpu") else "") + ".")
    l.append("Snapshots: " + (c["snapshots"] if c.get("snapshots") else "ninguna herramienta (ni snapper ni Timeshift): sin red de seguridad automática") + ".")
    hay = [k for k, v in c["opcionales"].items() if v and k != "copias"]
    if hay:
        l.append("Instalado: " + ", ".join(hay) + ".")
    if c["opcionales"].get("copias"):
        l.append("Copias de seguridad: " + ", ".join(c["opcionales"]["copias"]) + ".")
    return l


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["base"]:          # lo usa install.sh: imprime la orden para instalar lo que falta del sistema (o nada, si no falta nada)
        _f = familia_actual()
        from lina.escritorio import sesion as _ses
        _faltan = faltan(PAQUETES_BASE + tuple(_ses.Sesion().paquetes_que_faltan()), _f) if _f else []     # lo del sistema y lo que falta para el escritorio de este equipo
        if _faltan:
            print(manual(_faltan, _f))
        sys.exit(0 if _f else 3)
    d = detectar()
    print(f"Distribución: {d['distro']} · familia: {d['familia'] or 'desconocida'} · gestor: {d['gestor'] or '—'} ({'instalado' if d['tiene_gestor'] else 'no encontrado'})")
    print(f"Escritorio: {d['escritorio'] or '—'} · sesión: {d['sesion'] or '—'}")
