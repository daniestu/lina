# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Clasificación de comandos: qué es de solo lectura, qué lanza un programa, qué es hostil y qué se debe bloquear siempre.

Todo son funciones puras sobre texto; la decisión final de ejecutar o pedir confirmación se toma en herramientas.py."""
import os
import re
import shlex
import unicodedata
from pathlib import Path

from lina.nucleo import comandos
from lina.nucleo.idioma import N_
from lina.nucleo import plataforma as PL
from lina.nucleo import raiz as _RAIZ
from lina.nucleo import rutas as RUT

RAIZ_AYUDANTE = _RAIZ.AYUDANTE            # el único programa que Lina ejecuta como administrador sin contraseña (ver privilegios.py)

PROTEGER_DATOS = True          # bloquea borrar/mover/sobrescribir en el disco de datos que el usuario marque


def _disco_de_datos():
    """Un disco secundario (por ejemplo uno compartido con otro sistema) protegido contra borrados: su ruta, en ~/.config/lina/disco_datos.txt. Sin archivo, no hay ninguno."""
    try:
        r = (RUT.CONFIG / "disco_datos.txt").read_text(encoding="utf-8").strip().splitlines()
        if r and r[0].startswith("/") and len(r[0]) > 1:
            return r[0].rstrip("/")
    except OSError:
        pass
    return "/mnt/_sin_disco_de_datos_"


RUTA_DATOS = _disco_de_datos()

# Programas que se pueden abrir sin pedir confirmación (solo con enlaces o archivos de tu carpeta personal)
APPS_PERMITIDAS = {"steam", "firefox", "heroic", "lutris", "kate", "dolphin", "konsole", "discord", "spectacle",
                   "flameshot", "libreoffice", "soffice", "okular", "gwenview", "mpv", "vlc", "code", "obs"}
FLAGS_SEGUROS = {"libreoffice": {"--writer", "--calc", "--impress", "--draw", "--base", "--math"},
                 "soffice": {"--writer", "--calc", "--impress", "--draw", "--base", "--math"},
                 "firefox": {"--new-window", "--new-tab", "--private-window"},
                 "flameshot": {"gui"}}

_INTERPRETES = {"python", "python3", "perl", "ruby", "node", "php", "lua", "bash", "sh", "zsh", "fish", "dash"}
_PROGRAMAS_PANELES = {"kcmshell6", "kcmshell5", "systemsettings", "systemsettings6", "systemsettings5"}


def _es_interprete(base):
    return base in _INTERPRETES or re.fullmatch(r"python3\.\d+", base) is not None



# ======================= CLASIFICAR COMANDOS =======================
_HOME = str(Path.home())

_OBJETIVOS_PELIGROSOS = {"/", "/*", "/home", "/home/*", "/boot", "/boot/*", "/etc", "/etc/*", "/usr", "/usr/*",
                         "/var", "/var/*", "/bin", "/sbin", "/lib", "/lib64", "/opt", "/opt/*", "/root", "/root/*",
                         "/mnt", "/mnt/*", "/sys", "/proc", "/dev", "/srv"}

_SECRETOS = [r"\.config/lina", r"\.ssh\b", r"\.gnupg", r"/etc/shadow", r"/etc/gshadow",
             r"\bid_(rsa|ed25519|ecdsa|dsa)\b", r"\.netrc", r"\.aws/", r"logins\.json", r"key4\.db",
             r"cookies\.sqlite", r"login data", r"\.mozilla", r"\.pgpass", r"\.key\b",
             r"/proc/(?:self|thread-self|\d+|\*)/(?:environ|mem|maps)", r"\bsecret-tool\b", r"\bkwallet(?:cli|-query)\b", r"\bkeyctl\b", r"gnome-keyring"]
_PROPIO = (r"(?:^|/)lina/(?:nucleo|voz|escritorio|modulos|mcp|datos)/|site-packages/lina|/src/lina/|\.config/lina|\.local/share/lina|\.local/state/lina|"
          r"lina\.service|systemd/user/lina|systemctl[^;|&\n]*\blina\b|mcp\.json|mcp_estado|"
          r"\b(?:politica|comandos|activacion|presupuesto|paquetes_confiables|alias|vocabulario|disco_datos)\.txt|config\.toml|mcp_claves|"
          r"\b(?:asistente|herramientas|grupos|sistema|juegoconf|web|notas|recordatorios|oficina|organizacion|interfaz|interfaz_atspi|interfaz_vision|indicador|"
          r"plataforma|manos_libres|comandos|politica|diario|presupuesto|recetas|juegos|rutas|claves|ajustes)\.py|\.config/asistente|\.local/share/asistente")
_SUDOERS = r"/etc/sudoers|\bvisudo\b|sudoers\.d"
# Órdenes de Lina que cambian sus propios permisos, gasto, voz o claves: las da el usuario en su terminal o con el atajo, nunca la IA
_ORDEN_PROPIA = (r"(?:^|[\s;&|(`/])(?:lina|python3?\s+-m\s+lina(?:\.__main__)?)\s+"
                 r"(?:config\s+(?:poner|perfil)\b|clave\b|voz\s+\S|privilegios\s+(?:instalar|total|quitar)\b|privacidad\s+(?:si|no|preguntar|sí)\b|olvidar\b)")
# El ayudante de root y todo lo que lo activa: solo se usa instalando paquetes (la forma exacta que reconoce analizar_instalacion)
_AYUDANTE_ROOT = r"/usr/lib/lina\b|org\.lina\.instalar|sudoers\.d/lina|nucleo/raiz\b|\braiz\.py|\bprivilegios\.py"

# Prefijos que envuelven a otro comando, con las opciones de cada uno que llevan un valor detrás
_PREFIJOS = {"sudo": {"-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U", "-D", "-R"}, "doas": {"-u", "-C"}, "pkexec": {"--user", "-u"},
             "nohup": set(), "time": set(), "nice": {"-n"}, "ionice": {"-c", "-n", "-p"}, "command": set(),
             "exec": set(), "builtin": set(), "setsid": set(), "stdbuf": {"-i", "-o", "-e"},
             "timeout": {"-s", "-k"}, "env": {"-u", "-C", "-S"}}
_HERRAMIENTAS_DISCO = {"wipefs", "blkdiscard", "sgdisk", "sfdisk", "gdisk", "cgdisk", "mke2fs"}


def _sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _segmentos(comando):
    """Parte el comando en trozos por ; | || && y saltos de línea, sin cortar lo que va entre comillas."""
    trozos, actual, comilla, i = [], [], None, 0
    while i < len(comando):
        c = comando[i]
        if comilla:
            actual.append(c)
            if c == comilla:
                comilla = None
            elif c == "\\" and comilla == '"' and i + 1 < len(comando):
                i += 1
                actual.append(comando[i])
        elif c in "'\"":
            comilla = c
            actual.append(c)
        elif c == "\\" and i + 1 < len(comando):
            actual.append(c)
            i += 1
            actual.append(comando[i])
        elif c in ";\n|" or comando.startswith("&&", i):
            trozos.append("".join(actual))
            actual = []
            if comando.startswith(("||", "&&"), i):
                i += 1
        else:
            actual.append(c)
        i += 1
    trozos.append("".join(actual))
    return [t.strip() for t in trozos if t.strip()]


def _tokens(segmento):
    try:
        return shlex.split(segmento)
    except ValueError:
        return None


def _normalizar_ruta(ruta):
    ruta = ruta.replace("${HOME}", _HOME).replace("$HOME", _HOME)
    if ruta == "~" or ruta.startswith("~/"):
        ruta = _HOME + ruta[1:]
    ruta = re.sub(r"/+", "/", ruta)
    if len(ruta) > 1:
        ruta = ruta.rstrip("/")
    return ruta


def _es_objetivo_peligroso(ruta):
    ruta = _normalizar_ruta(ruta)
    return ruta in _OBJETIVOS_PELIGROSOS or ruta in {_HOME, _HOME + "/*", _HOME + "/.*"}


def _quitar_prefijos(t):
    """Quita 'sudo', 'env VAR=1', 'timeout 5'... para ver el programa real."""
    t = list(t)
    while t:
        primero = os.path.basename(t[0])
        if re.match(r"^[A-Za-z_]\w*=", t[0]):      # VARIABLE=valor delante del comando
            t.pop(0)
            continue
        if primero in _PREFIJOS:
            valores = _PREFIJOS[primero]
            t.pop(0)
            while t and t[0].startswith("-"):
                opcion = t.pop(0)
                if opcion in valores and t:
                    t.pop(0)
            if primero == "timeout" and t and re.fullmatch(r"[\d.]+[smhd]?", t[0]):
                t.pop(0)
            continue
        break
    return t


# ======================= CONTENIDO HOSTIL: descargar y ejecutar, tuberías a un intérprete, reverse shells =======================
_SHELLS = {"bash", "sh", "zsh", "fish", "dash"}
_DESCARGAN = {"curl", "wget", "aria2c", "lftp"}
_CLONAN = {"git", "svn", "hg"}
_A_UN_SHELL = re.compile(r"\|\s*(?:sudo\s+(?:-\S+\s+)*|env\s+\S+\s+)?(?:ba|z|da|fi|k|c|tc)?sh\b")
_A_UN_INTERPRETE = re.compile(r"\|\s*(?:sudo\s+(?:-\S+\s+)*)?(?:python[\d.]*|perl|ruby|node|php|lua)\s*(?:-\s*)?(?:$|[;&|)\n])")
_SUSTITUCION_A_SHELL = re.compile(r"(?:^|[;&|\s])(?:(?:ba|z|da|fi|k)?sh\s+(?:-\w+\s+)*[\"']?\$\(|(?:ba|z|da|fi|k)?sh\s+<\(|eval\s+[\"']?\$\(|(?:source|\.)\s+<\()")
_CODIGO_CON_RED = re.compile(r"urlopen|requests\.(?:get|post)|urllib|http\.client|fetch\(|\bcurl\b|\bwget\b|https?://")
_CODIGO_QUE_EJECUTA = re.compile(r"\b(?:exec|eval|system|popen|execSync|spawnSync|spawn|subprocess)\b")
_CODIGO_DESTRUCTIVO = re.compile(r"\brm\s+-\w*[rf]|rmtree|os\.(?:remove|unlink|rmdir)|\bunlink\(|\brmdir\(|\bshred\b|\bmkfs|\bdd\s+if=|truncate\(")


def _codigo_en_linea(base, args):
    """El texto de «python -c '…'», «node -e '…'», «perl -e '…'», o None."""
    if not _es_interprete(base) or base in _SHELLS:
        return None
    for i, a in enumerate(args):
        if a in ("-c", "-e", "-E", "--eval", "--command") and i + 1 < len(args):
            return args[i + 1]
    return None


def _nombres_descargados(base, args, texto):
    """Nombres de archivo que escribe una descarga (curl -o x, wget -O x, curl URL > x, o el nombre de la URL con -O / wget a secas)."""
    nombres = set()
    urls = [a for a in args if re.match(r"[A-Za-z][\w+.-]*://", a)]
    for i, a in enumerate(args):
        if a in ("-o", "--output", "-O", "--output-document") and i + 1 < len(args) and not args[i + 1].startswith("-") and base == "wget" or \
                a in ("-o", "--output") and base == "curl" and i + 1 < len(args):
            nombres.add(os.path.basename(args[i + 1]))
        elif a.startswith(("--output=", "--output-document=")):
            nombres.add(os.path.basename(a.split("=", 1)[1]))
    if base == "curl" and any(a in ("-O", "--remote-name") or (a.startswith("-") and not a.startswith("--") and "O" in a[1:]) for a in args):
        nombres |= {os.path.basename(u.split("?")[0].rstrip("/")) for u in urls}
    if base == "wget" and not nombres:
        nombres |= {os.path.basename(u.split("?")[0].rstrip("/")) or "index.html" for u in urls}
    nombres |= {os.path.basename(m) for m in re.findall(r">\s*(\S+)", texto)}
    nombres.discard("")
    return nombres


def _que_ejecuta(resto):
    """Lo que ejecuta un segmento: el programa si lo lanza por ruta (./x, /tmp/x), o el primer argumento de un intérprete/shell/source."""
    if not resto:
        return []
    base = os.path.basename(resto[0])
    candidatos = []
    if "/" in resto[0] or resto[0] in {"source", "."}:
        candidatos.append(os.path.basename(resto[0]))
    if _es_interprete(base) or base in _SHELLS or resto[0] in {"source", "."}:
        primero = next((a for a in resto[1:] if not a.startswith("-")), None)
        if primero:
            candidatos.append(os.path.basename(primero))
    return candidatos


def _descarga_y_ejecuta(comando):
    """'descargaría y ejecutaría…' si en el mismo comando algo se descarga y luego se ejecuta lo descargado; si no, None."""
    descargados, clonados = set(), False
    for seg in _segmentos(comando):
        t = _tokens(seg)
        resto = _quitar_prefijos(t) if t else None
        if not resto:
            continue
        base = os.path.basename(resto[0])
        ejecuta = _que_ejecuta(resto)
        if descargados and any(e in descargados for e in ejecuta):
            return "ejecutaría un programa que acaba de descargar sin que nadie lo revise"
        if clonados and (any(c.startswith("./") or c.endswith((".sh", ".py", ".run", ".bin")) for c in ejecuta) or "/" in resto[0]
                         or base in {"make", "cmake", "cargo", "npm", "pnpm", "yarn", "pip", "pip3", "meson", "ninja", "go"}):
            return "ejecutaría lo que acaba de bajar de un repositorio sin que nadie lo revise"
        if base in _DESCARGAN:
            descargados |= _nombres_descargados(base, resto[1:], seg)
        elif base in _CLONAN and resto[1:2] in (["clone"], ["checkout"], ["co"]):
            clonados = True
    return None


def _bloqueado_hostil(comando):
    """Bloqueos duros contra contenido hostil: scripts de internet, tuberías a un intérprete, reverse shells."""
    bajo = comando.lower()
    if re.search(r"/dev/(?:tcp|udp)/", bajo):
        return "abriría una conexión de red desde la shell (típico de una puerta trasera)"
    if _A_UN_SHELL.search(bajo) or _A_UN_INTERPRETE.search(bajo):
        return "ejecutaría como código lo que le llega por una tubería, sin poder revisarlo"
    if _SUSTITUCION_A_SHELL.search(bajo):
        return "ejecutaría como código el resultado de otra orden, sin poder revisarlo"
    motivo = _descarga_y_ejecuta(comando)
    if motivo:
        return motivo
    for seg in _segmentos(comando):
        t = _tokens(seg)
        resto = _quitar_prefijos(t) if t else None
        if not resto:
            continue
        codigo = _codigo_en_linea(os.path.basename(resto[0]), resto[1:])
        if codigo and _CODIGO_CON_RED.search(codigo) and _CODIGO_QUE_EJECUTA.search(codigo):
            return "descargaría código y lo ejecutaría sin que nadie lo revise"
    return None


def _critico_extra(comando):
    """Cosas que pasan por el filtro anterior pero piden el atajo: código libre que puede borrar, contenedores con acceso total, software de fuera."""
    for seg in _segmentos(comando):
        t = _tokens(seg)
        resto = _quitar_prefijos(t) if t else None
        if not resto:
            continue
        base, args = os.path.basename(resto[0]), resto[1:]
        codigo = _codigo_en_linea(base, args)
        if codigo and _CODIGO_DESTRUCTIVO.search(codigo):
            return "ejecuta código libre que puede borrar archivos"
        if base in {"docker", "podman", "nerdctl"} and ("--privileged" in args or any(re.match(r"(?:-v|--volume)(?:=|\s*)/(?::|\s|$)", a) or a in ("/:/host",) or a.startswith("/:") for a in args)
                                                      or re.search(r"(?:-v|--volume)[= ]+/:", " ".join(args))):
            return "da a un contenedor acceso total al equipo (equivale a ser administrador)"
        if base in {"flatpak", "snap"} and "install" in args and (any(a.endswith((".flatpakref", ".flatpak", ".snap")) or "://" in a for a in args)
                                                              or {"--dangerous", "--devmode", "--classic"} & set(args)):
            return "instala software de fuera de las tiendas oficiales"
        if base == "setfacl" and any(a in ("-R", "--recursive") for a in args):
            return "cambia permisos de acceso en masa"
    return None



def _bloqueado(comando, _profundidad=0):
    """Si el comando está prohibido siempre, devuelve el motivo; si no, None."""
    bajo = comando.lower()
    if re.search(r":\(\)\s*\{", comando):
        return "es una bomba de procesos"
    if re.search(r">\s*/dev/(sd|nvme|mmcblk|vd|hd)", bajo):
        return "escribiría directamente sobre un disco"
    if re.search(r"\b(curl|wget)\b[^|;&\n]*\|\s*(sudo\s+(-\S+\s+)*)?(ba|z|da|fi)?sh\b", bajo) or \
            re.search(r"\b(ba|z|da|fi)?sh\s+<\(\s*(curl|wget)", bajo) or re.search(r"\beval\b.*\$\(\s*(curl|wget)", bajo):
        return "descargaría y ejecutaría un script de internet sin revisarlo"
    for patron in _SECRETOS:
        if re.search(patron, bajo):
            return "toca claves, contraseñas o credenciales"
    if re.search(_PROPIO, bajo):
        return "tocaría mi propio código o mi servicio"
    if re.search(_SUDOERS, bajo):
        return "tocaría los permisos de sudo"
    if re.search(_AYUDANTE_ROOT, bajo) and not analizar_instalacion(comando):
        return "tocaría el ayudante con el que instalo paquetes como administrador"
    if re.search(_ORDEN_PROPIA, bajo):
        return "cambiaría mis propios ajustes de permisos, gasto o claves (eso lo haces tú, o con el atajo)"
    motivo = _bloqueado_hostil(comando)
    if motivo:
        return motivo

    for seg in _segmentos(comando):
        t = _tokens(seg)
        if not t:
            continue
        t = _quitar_prefijos(t)
        if not t:
            continue
        base = os.path.basename(t[0])
        args = t[1:]
        solo_flags = [a for a in args if a.startswith("-")]
        objetivos = [a for a in args if not a.startswith("-")]
        recursivo = any((a.startswith("-") and not a.startswith("--") and ("r" in a.lower())) or a == "--recursive"
                        for a in solo_flags)

        if base in {"bash", "sh", "zsh", "fish", "dash"} and "-c" in args and _profundidad < 3:
            i = args.index("-c")
            if i + 1 < len(args):
                motivo = _bloqueado(args[i + 1], _profundidad + 1)
                if motivo:
                    return motivo
        if (base == "gio" and args[:1] == ["trash"]) or base in {"trash-put", "trash"}:
            if any(_es_objetivo_peligroso(o) for o in objetivos if o != "trash"):
                return "mandaría a la papelera el sistema o tu carpeta personal"
        if base == "rm":
            if "--no-preserve-root" in solo_flags:
                return "borraría el sistema entero"
            if recursivo and any(_es_objetivo_peligroso(o) for o in objetivos):
                return "borraría el sistema o tu carpeta personal"
        if base in {"chmod", "chown", "chgrp"} and recursivo and any(_es_objetivo_peligroso(o) for o in objetivos):
            return "cambiaría los permisos de todo el sistema"
        if base.startswith("mkfs") or base in _HERRAMIENTAS_DISCO:
            return "formatearía o repartiría un disco"
        if base in {"fdisk", "cfdisk", "parted"} and not (set(args) & {"-l", "--list", "print", "p"}):
            return "repartiría un disco"
        if base == "dd" and any(a.startswith("of=/dev/") for a in args):
            return "escribiría directamente sobre un disco"
        if base == "shred" and any(o.startswith("/dev/") for o in objetivos):
            return "destruiría un disco"
        if base == "mkswap" and any(o.startswith("/dev/") for o in objetivos):
            return "formatearía una partición"
        if base == "cryptsetup" and any(a in {"luksFormat", "luksErase", "erase", "luksKillSlot", "reencrypt"} for a in args):
            return "destruiría un disco cifrado"
        if base in {"passwd", "chpasswd", "userdel", "usermod", "useradd", "visudo"}:
            return "tocaría cuentas de usuario"
        if base == "find" and ("-delete" in args or "-exec" in args) and any(_es_objetivo_peligroso(o) for o in objetivos):
            filtros = {"-name", "-iname", "-path", "-ipath", "-regex", "-type", "-mtime", "-atime", "-ctime", "-size",
                       "-user", "-group", "-newer", "-empty"}
            if not (filtros & set(args)):  # sin ningún filtro, borra todo lo que cuelga de ahí
                return "borraría el sistema o tu carpeta personal"
        if base == "xargs" and _profundidad < 3:
            i = next((k for k, a in enumerate(args) if not a.startswith("-")), None)
            if i is not None:
                motivo = _bloqueado(shlex.join(args[i:]) + " /", _profundidad + 1)
                if motivo:
                    return motivo

    if PROTEGER_DATOS and RUTA_DATOS in comando:
        destructivo = (re.search(r"\b(rm|mv|shred|truncate|dd|tee)\b", bajo) or re.search(r"\bsed\s+-i", bajo)
                       or re.search(r"\b(chmod|chown)\s+-\w*r", bajo) or re.search(r"--delete|-delete", bajo)
                       or ">" in comando)
        if destructivo:
            return "ese disco de datos está protegido"
    return None


# ----- Destrucción total (formatear el ordenador, borrar el sistema...) -----
# Red de seguridad por palabras sobre lo que PIDE el usuario y sobre lo que la IA OFRECE. La IA además lleva una regla; esto cubre cuando falla.
# Nunca se ofrece ni se prepara, ni siquiera «con confirmación»: los comandos que lo harían ya están bloqueados en _bloqueado().
_DT_OBJ = (r"(?:(?:el|la|los|las|mi|mis|tu|tus|este|esta|todo|todos|todas|completo|completa|entero|entera|principal|de)\s+){0,4}"
           r"(?:ordenador|ordenadores|computador\w*|pc|equipo|sistema(?:\s+operativo)?|discos?(?:\s+(?:duro|principal|del sistema|de arranque|de datos|ssd))?|ssd|nvme|"
           r"particion(?:es)?|windows|linux|cachyos|arranque|unidad(?:es)?)\b")
_DESTRUCCION_TOTAL = re.compile(
    r"\bformat\w*\s+(?:\w+\s+){0,2}?" + _DT_OBJ + r"|"
    r"\b(?:borra|borrar|borrame|borres|elimina|eliminar|eliminame|destruye|destruir|vacia|vaciar|machaca|machacar|wipe\w*|limpia\s+por\s+completo)\s+(?:\w+\s+){0,2}?" + _DT_OBJ + r"|"
    r"\b(?:restablece|restablecer|restaura|restaurar|resetea|resetear|reinicia|reiniciar)\w*\s+(?:\w+\s+){0,4}?de\s+fabrica\b|"
    r"\bdeja\w*\s+(?:\w+\s+){0,4}?(?:de\s+fabrica|como\s+nuev[oa]|desde\s+cero)\b|"
    r"\b(?:reinstala|reinstalar|reinstalame|instala\s+de\s+nuevo|instala\s+otra\s+vez)\s+(?:\w+\s+){0,2}?(?:el\s+)?(?:sistema|windows|linux|cachyos)\b|"
    r"\b(?:resetea|resetear)\w*\s+(?:el\s+|mi\s+)?(?:ordenador|pc|equipo|sistema)\b|\bwipefs\b|\bmkfs\b")


_DT_OBJ_EN = (r"(?:(?:the|my|your|this|that|whole|entire|all|of|main|primary|complete|full)\s+){0,4}"
              r"(?:computer|computers|pc|machine|system(?:\s+drive|\s+disk)?|operating system|disks?|hard\s?drives?|hard\s?disks?|drives?|ssd|nvme|"
              r"partitions?|windows|linux|cachyos|bootloader|boot\s+(?:drive|disk|partition))\b(?!\s+(?:tray|cache|logs?|settings|volume|sounds?|monitor|info|updates?|notifications?|clock|time))")
_DESTRUCCION_TOTAL_EN = re.compile(
    r"\bformat\w*\s+(?:\w+\s+){0,2}?" + _DT_OBJ_EN + r"|"
    r"\b(?:delete|deleting|erase|erasing|destroy|destroying|wipe|wiping|nuke|nuking|obliterate)\s+(?:\w+\s+){0,3}?" + _DT_OBJ_EN + r"|"
    r"\b(?:factory\s+reset|reset\s+(?:\w+\s+){0,3}?to\s+(?:factory|default)\s+(?:settings|state)?|restore\s+(?:\w+\s+){0,3}?to\s+factory)\b|"
    r"\b(?:leave|leaves|return|restore)\s+(?:\w+\s+){0,4}?(?:like\s+new|as\s+new|from\s+scratch|to\s+factory)\b|"
    r"\b(?:reinstall|reinstalling)\s+(?:\w+\s+){0,2}?(?:the\s+)?(?:system|windows|linux|cachyos|operating system)\b|\bwipefs\b|\bmkfs\b")


def destruccion_total(texto):
    """¿Se pide (o se ofrece) formatear el ordenador o un disco, borrar el sistema o las particiones, dejarlo de fábrica...?
    Se miran las frases de TODOS los idiomas a la vez (es una red de seguridad: no depende del idioma activo)."""
    t = _sin_acentos(str(texto or "").lower())
    return bool(_DESTRUCCION_TOTAL.search(t) or _DESTRUCCION_TOTAL_EN.search(t))


AVISO_DESTRUCCION_TOTAL = N_("Eso no lo hago: formatear discos, borrar particiones o el sistema entero está bloqueado en mi código, ni siquiera con tu confirmación. "
                           "Si de verdad quieres reinstalar o vaciar un disco, hazlo tú desde un USB de instalación o con el gestor de particiones. "
                           "Si lo que buscas es liberar espacio o volver a un punto anterior, dímelo y lo vemos con una copia o limpiando cachés.")


# ----- Solo lectura -----
_LECTURA_SIMPLE = {"ls", "cat", "head", "tail", "wc", "uniq", "cut", "tr", "stat", "file", "du", "df", "free",
                   "uname", "uptime", "lsblk", "lscpu", "lspci", "lsusb", "lsmod", "fc-list", "id", "whoami", "pwd",
                   "which", "type", "locale", "ps", "pgrep", "pidof", "ss", "echo", "printf", "basename", "dirname",
                   "readlink", "realpath", "seq", "true", "false", "tty", "nproc", "arch", "groups", "getent",
                   "lsof", "fastfetch", "neofetch", "findmnt", "diff", "cmp", "md5sum", "sha256sum", "sha1sum", "xxd", "od",
                   "strings", "jq", "tree"}


# Con sudo por delante, solo estos comandos se consideran de lectura
_SUDO_LECTURA = {"dmidecode", "lshw", "lspci", "lsusb", "dmesg", "journalctl", "smartctl", "nvme", "hdparm", "ethtool",
                 "fdisk", "blkid", "lsof", "ss", "systemctl", "iw", "lsblk", "nvidia-smi", "ip", "sensors", "snapper",
                 "cat", "head", "tail", "ls", "stat", "file", "grep", "egrep", "fgrep", "wc", "du", "df",
                 "diff", "cmp", "readlink", "realpath"}


def _segmento_lectura(t):
    if not t:
        return False
    base = os.path.basename(t[0])
    a = t[1:]
    primero = next((x for x in a if not x.startswith("-")), "")
    if base in _LECTURA_SIMPLE:
        return True
    if base in {"grep", "egrep", "fgrep", "rg"}:
        return not any(x == "--pre" or x.startswith("--pre=") for x in a)
    if base == "sed":                           # sed solo imprime, salvo con -i o con órdenes de escribir (w) o ejecutar (e)
        return not any(x == "--in-place" or x.startswith("--in-place=") or (x.startswith("-") and not x.startswith("--")
                                                                              and "i" in x[1:]) for x in a) \
            and not any(re.search(r"(?:^|[;\n{}])\s*[\d,$]*\s*[wWe]\s", x) for x in a if not x.startswith("-"))
    if base == "sort":
        return not any(x.startswith("-o") or x.startswith("--output") for x in a)
    if base == "find":
        return not any(x in {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf",
                             "-fls"} for x in a)
    if base == "date":
        return not any(x in {"-s", "--set"} or x.startswith("--set=") for x in a)
    if base == "dmesg":
        return not any(x in {"-c", "-C", "--clear", "--read-clear"} for x in a)
    if base == "hostname":
        return all(x in {"-f", "-i", "-I", "-s", "-d", "-A", "-a", "--fqdn", "--ip-address"} for x in a)
    if base == "hostnamectl":
        return not a or a == ["status"]
    if base == "timedatectl":
        return not a or a[0] in {"status", "show", "list-timezones"}
    if base in {"kreadconfig5", "kreadconfig6"}:
        return True
    if base in {"kcmshell6", "kcmshell5"}:
        return a == ["--list"]
    if base == "busctl":                        # solo mirar: listar, ver el árbol o los métodos, leer propiedades
        return primero in {"list", "tree", "introspect", "status", "get-property", "help"}
    if base == "mount":
        return not a
    if base == "sensors":
        return "-s" not in a
    if base == "nvidia-smi":
        setters = {"-pm", "-pl", "-ac", "-rac", "-r", "--gpu-reset", "-lgc", "-rgc", "-lmc", "-rmc", "-e", "-c", "-mig"}
        return not any(x in setters or x.startswith(("--power-limit", "--persistence-mode", "--compute-mode",
                                                      "--ecc-config", "--applications-clocks")) for x in a)
    if base == "ip":
        return not any(x in {"add", "del", "delete", "set", "flush", "change", "replace", "append", "up", "down"} for x in a)
    if base == "iw":
        return not any(x in {"set", "connect", "disconnect", "del", "add", "ibss", "mesh", "interface"} for x in a)
    if base == "nmcli":
        return (any(x in {"show", "status", "list", "get"} for x in a)
                and not any(x in {"up", "down", "connect", "disconnect", "delete", "modify", "add", "edit", "reload",
                                  "import", "clone"} for x in a))
    if base == "journalctl":
        return not any(x.startswith(("--vacuum", "--rotate", "--flush", "--sync", "--relinquish-var",
                                     "--smart-relinquish-var", "--setup-keys", "--update-catalog")) for x in a)
    if base == "systemctl":
        return primero in {"status", "is-active", "is-enabled", "is-failed", "list-units", "list-unit-files",
                           "list-timers", "list-sockets", "show", "cat", "get-default"}
    if base in {"apt-cache", "dpkg-query"}:         # solo consultan la base de paquetes
        return True
    if base == "apt-file":
        return primero in {"search", "list", "show", "find"}
    if base in PL.GESTORES_PAQUETES:                # pacman, apt, dnf, zypper, dpkg, rpm…: solo mirar (buscar, listar, comprobar)
        return PL.es_consulta(base, a)
    if base == "flatpak":
        return primero in {"list", "search", "info", "remote-ls", "remotes"}
    if base == "wpctl":
        return primero in {"status", "get-volume", "inspect"}
    if base == "pactl":
        return primero in {"list", "info"} or primero.startswith("get-")
    if base == "playerctl":
        return primero in {"status", "metadata", "position"}
    if base == "kscreen-doctor":
        return a in (["-o"], ["--outputs"], ["-j"], ["--json"])
    if base == "kdotool":                       # ver ventanas sí; activar, cerrar, mover... no
        acciones = {"windowactivate", "windowclose", "windowmove", "windowsize", "windowminimize", "windowraise", "windowfocus",
                    "windowstate", "set_desktop", "set_desktop_for_window", "set_num_desktops", "keyup", "keydown", "key"}
        return not any(x in acciones for x in a)
    if base == "xdotool":                       # leer ventanas sí; activar, cerrar, escribir, pulsar teclas, mover el ratón... no
        acciones = {"windowactivate", "windowclose", "windowmove", "windowsize", "windowminimize", "windowraise", "windowfocus", "windowmap",
                    "windowunmap", "windowkill", "windowreparent", "windowstate", "set_window", "set_desktop", "set_desktop_for_window",
                    "set_num_desktops", "key", "keydown", "keyup", "type", "click", "mousemove", "mousemove_relative", "mousedown", "mouseup",
                    "behave", "behave_screen_edge", "exec", "getwindowfocus_set"}
        return bool(a) and not any(x in acciones for x in a)
    if base == "hyprctl":
        orden = next((x for x in a if not x.startswith("-")), "")
        return orden in {"activewindow", "clients", "monitors", "workspaces", "activeworkspace", "version", "devices", "layers", "binds", "getoption",
                         "cursorpos", "layouts", "systeminfo", "animations", "globalshortcuts"}
    if base == "swaymsg":
        return any(x.startswith("get_") for x in a) and ("-t" in a or "--type" in a or any(x.startswith("--type=") for x in a)) and "-m" not in a
    if base == "powerprofilesctl":
        return primero in {"get", "list", "version"}
    if base == "upower":
        return not any(x in {"--monitor", "--monitor-detail"} for x in a)
    if base == "bluetoothctl":
        return primero in {"show", "devices", "info", "paired-devices", "list"}
    if base == "brightnessctl":
        return "set" not in a and "s" not in a and "-s" not in a
    if base == "ddcutil":
        return primero in {"detect", "getvcp", "capabilities", "environment", "usbdetect"}
    if base == "resolvectl":
        return primero in {"status", "query", "statistics", "show-cache", "dns", "domain"} or not a
    if base == "loginctl":
        return primero in {"list-sessions", "list-users", "list-seats", "show-session", "session-status", "show-user", "user-status",
                           "seat-status", "show-seat"}
    if base == "systemd-analyze":
        return primero in {"blame", "critical-chain", "time", "plot", "verify", "security"} and not any(x.startswith("--") and "=" in x and "dump" in x for x in a)
    if base == "systemd-inhibit":
        return "--list" in a
    if base == "top":
        return "-b" in a
    if base == "ping":
        return "-c" in a or "-w" in a
    if base in {"qdbus", "qdbus6", "qdbus-qt5", "qdbus-qt6"}:     # solo listar servicios u objetos; con un método ya es una llamada
        return len([x for x in a if not x.startswith("-")]) <= 2
    if base == "ollama":
        return primero in {"list", "ps", "show"}
    if base == "git":
        return primero in {"status", "log", "diff", "branch", "remote", "show", "rev-parse"} and not any(
            x.startswith("--output") for x in a)
    if base == "xdg-mime":
        return primero == "query"
    # Diagnóstico de hardware: leen información del equipo (suelen pedir sudo, pero no cambian nada)
    if base == "dmidecode":
        return not any(x.startswith("--dump-file") for x in a)
    if base == "lshw":
        return True
    if base == "smartctl":
        seguros = {"-a", "-A", "-H", "-i", "-x", "-l", "-c", "-j", "--all", "--attributes", "--health", "--info",
                   "--xall", "--capabilities", "--scan"}
        palabras = {"error", "selftest", "xerror", "xselftest"}
        return bool(a) and all(x in seguros or x in palabras or x.startswith(("/dev/", "--json")) for x in a)
    if base == "nvme":
        return primero in {"list", "smart-log", "id-ctrl", "id-ns", "error-log", "list-ns"}
    if base == "hdparm":
        return bool(a) and all(x in {"-I", "-i"} or x.startswith("/dev/") for x in a)
    if base == "ethtool":
        return bool(a) and all(x in {"-i", "--driver", "-S", "--statistics", "-k", "--show-features"}
                               or not x.startswith("-") for x in a)
    if base == "fdisk":
        return any(x in {"-l", "--list"} for x in a)
    if base == "blkid":
        return "-g" not in a
    if base == "snapper":                       # ver snapshots sí; crear, borrar o revertir pide confirmación
        resto, i = [], 0
        while i < len(a):
            if a[i] in ("-c", "--config") and i + 1 < len(a):
                i += 2
            elif a[i].startswith("--config="):
                i += 1
            else:
                resto.append(a[i])
                i += 1
        return bool(resto) and resto[0] in {"list", "ls", "list-configs", "get-config", "status", "diff"}
    return False


def _es_lectura(comando):
    c = comando.replace("2>/dev/null", "").replace("2>&1", "")
    if re.search(r"[<>]|\$\(|`|(?<![&])&(?![&])", c):
        return False
    segmentos = _segmentos(c)
    if not segmentos:
        return False
    for seg in segmentos:
        t = _tokens(seg)
        if not t or t[0] == "doas" or re.match(r"^[A-Za-z_]\w*=", t[0]):
            return False
        if t[0] == "sudo":
            t = [x for x in t[1:] if x != "-n"]
            if not t or os.path.basename(t[0]) not in _SUDO_LECTURA:
                return False
        if not _segmento_lectura(t):
            return False
    return True


# ----- Inocuo y lanzar -----
_INOCUO_REGEX = [
    r"wpctl set-volume @DEFAULT_AUDIO_SINK@ [0-9]+(\.[0-9]+)?%?[+-]?( -l [0-9.]+)?",
    r"wpctl set-mute @DEFAULT_AUDIO_SINK@ (0|1|toggle)",
    r"playerctl (play|pause|play-pause|next|previous|stop)",
]
_METACARACTERES = re.compile(r"[;&|<>$`\n\\]")


# Tipos de archivo que se pueden abrir con xdg-open sin pedir permiso (documentos, imágenes, audio y vídeo).
# Quedan fuera los que pueden ejecutar cosas: .sh, .desktop, .AppImage, .jar...
_EXTENSIONES_ABRIBLES = {".odt", ".ods", ".odp", ".odg", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf", ".txt",
                         ".md", ".csv", ".rtf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".mp4", ".mkv",
                         ".webm", ".avi", ".mov", ".mp3", ".flac", ".ogg", ".wav", ".epub"}


def _ruta_abrible(ruta, xdg=False):
    """¿Es una ruta de tu carpeta personal o del disco de datos protegido (sin carpetas ocultas ni '..')?
    Con xdg=True, además, tiene que ser una carpeta o un archivo de un tipo seguro."""
    ruta = _normalizar_ruta(ruta)
    if ".." in ruta.split("/"):
        return False
    for raiz in (_HOME, RUTA_DATOS):
        if ruta == raiz or ruta.startswith(raiz + "/"):
            resto = ruta[len(raiz) + 1:]
            if any(parte.startswith(".") for parte in resto.split("/") if parte):
                return False
            if not xdg or not resto:
                return True
            p = Path(ruta)
            return p.is_dir() or p.suffix.lower() in _EXTENSIONES_ABRIBLES
    return False


def _limpiar_escapes(comando):
    """Quita comillas y espacios escapados (\\ ) para buscar de verdad caracteres peligrosos."""
    return comando.replace("\\ ", " ").replace("'", "").replace('"', "")


def _es_inocuo(comando):
    if any(re.fullmatch(p, comando.strip()) for p in _INOCUO_REGEX):
        return True
    t = _tokens(comando)
    if t and os.path.basename(t[0]) == "notify-send" and not _METACARACTERES.search(comando.replace("'", "").replace('"', "")):
        return True
    return False


# Lo que NUNCA se abre «al instante» aunque aparezca en un .desktop: intérpretes, lanzadores genéricos y utilidades que borran, mueven o envían cosas.
_NO_ES_UN_PROGRAMA_DE_VENTANA = {"env", "sh", "bash", "zsh", "fish", "dash", "python", "python3", "perl", "ruby", "node", "java", "sudo", "pkexec", "su", "doas",
                                 "snap", "nohup", "setsid", "time", "xdg-open", "rm", "mv", "cp", "dd", "chmod", "chown", "ln", "tee", "curl", "wget", "ssh", "scp",
                                 "rsync", "nc", "ncat", "socat", "tar", "unzip", "kill", "killall", "pkill", "shred", "mkfs", "mount", "umount", "systemctl"} | PL.GESTORES_PAQUETES


def _apps_instaladas():
    """(ejecutables, ids de flatpak) de los programas con ventana INSTALADOS EN EL SISTEMA (no los de tu carpeta de usuario, que cualquiera podría
    haber escrito): se pueden abrir al instante sin esperar a que terminen."""
    ejecutables, flatpaks = set(), set()
    try:
        apps = comandos.nombres_de_apps()
    except Exception:
        return ejecutables, flatpaks
    casa = str(Path.home())
    for a in apps:
        partes = a["comando"].split()
        if not partes:
            continue
        base = os.path.basename(partes[0])
        if str(a.get("origen", "")).startswith(casa) and not (base == "flatpak" and "/flatpak/exports/" in str(a.get("origen", "")) + "/"):
            continue                                     # (los de Flatpak del usuario sí: «flatpak run id» solo ejecuta programas flatpak instalados)
        if base == "flatpak":
            flatpaks |= {x for x in partes if re.fullmatch(r"[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+){2,}", x)}
        elif base not in _NO_ES_UN_PROGRAMA_DE_VENTANA and re.fullmatch(r"[\w.+-]+", base):
            ejecutables.add(base)
    return ejecutables, flatpaks


def _es_lanzamiento(comando):
    comando = re.sub(r"(?<!&)\s*&\s*$", "", comando.strip())          # un «&» al final no cambia nada: ya se abre sin esperar
    if _METACARACTERES.search(_limpiar_escapes(comando)):
        return False
    t = _tokens(comando)
    if not t:
        return False
    base = os.path.basename(t[0])
    if base in _PROGRAMAS_PANELES:                   # kcmshell6 kcm_xxx: abre el panel y sigue (que exista se comprueba antes)
        return len(t) == 2 and re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.+-]*", t[1]) is not None
    if base == "xdg-open":
        if len(t) != 2:
            return False
        return re.fullmatch(r"https?://[^\s'\"`$;&|<>]+", t[1]) is not None or _ruta_abrible(t[1], xdg=True)
    instaladas, flatpaks = _apps_instaladas()
    if base == "flatpak":                              # «flatpak run id.del.programa», si ese programa está instalado
        return len(t) == 3 and t[1] == "run" and t[2] in flatpaks
    if base not in APPS_PERMITIDAS and base not in instaladas:
        return False
    for a in t[1:]:
        if a in FLAGS_SEGUROS.get(base, set()):
            continue
        if re.fullmatch(r"https?://[^\s'\"`$;&|<>]+", a) or re.fullmatch(r"steam://(rungameid|run|nav|open)/[\w./?=&:+-]+", a):
            continue
        if (a.startswith("/") or a.startswith("~")) and _ruta_abrible(a):
            continue
        return False
    return True


# ----- Instalar paquetes oficiales -----

def analizar_instalacion(comando):
    """Si es una instalación sencilla con el gestor de ESTA distribución (sudo pacman -S, apt-get install, dnf install, zypper install…),
    devuelve la lista de paquetes; si no, None."""
    if _METACARACTERES.search(comando):
        return None
    t = _tokens(comando)
    if t and t[:2] == ["sudo", "-n"]:
        t = ["sudo"] + t[2:]
    if t and t[:3] == ["sudo", RAIZ_AYUDANTE, "instalar"]:       # la forma que usa Lina cuando tiene el ayudante de root
        nombres = t[3:]
        if nombres and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}", a) for a in nombres):
            return nombres
        return None
    if not t or t[0] != "sudo":
        return None
    return PL.paquetes_a_instalar(t[1:])
