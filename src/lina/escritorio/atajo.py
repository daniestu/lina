"""El atajo de teclado global que ejecuta `lina pulsar`.

Lo registra en el escritorio que haya (KDE Plasma o GNOME) sin pisar uno que el usuario ya tenga; en los demás escritorios explica cómo ponerlo.
Cada registro deja anotado qué ha creado, para que `lina uninstall` lo quite.
"""
import ast
import os
import re
import shutil
import subprocess
from pathlib import Path

NOMBRE_KDE = "lina-pulsar.desktop"
RUTA_GNOME = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lina/"
TECLA_POR_DEFECTO = {"kde": "Meta+Space", "gnome": "<Control><Alt>space"}
_TECLA_KDE = re.compile(r"[A-Za-z0-9_+]{1,40}")
_TECLA_GNOME = re.compile(r"(?:<[A-Za-z]{3,8}>){0,4}[A-Za-z0-9_]{1,20}")


def escritorio(entorno=None):
    """'kde' | 'gnome' | 'otro' según XDG_CURRENT_DESKTOP."""
    env = os.environ if entorno is None else entorno
    palabras = re.split(r"[:;,\s]+", (env.get("XDG_CURRENT_DESKTOP") or env.get("DESKTOP_SESSION") or "").lower())
    if "kde" in palabras or "plasma" in palabras:
        return "kde"
    if any(p in ("gnome", "ubuntu", "unity", "budgie", "pantheon", "cinnamon") for p in palabras):
        return "gnome"
    return "otro"


def _datos(home):
    return Path(os.environ.get("XDG_DATA_HOME") or Path(home) / ".local/share")


def _config(home):
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path(home) / ".config")


def tecla_valida(tecla, escr):
    return bool((_TECLA_KDE if escr == "kde" else _TECLA_GNOME).fullmatch(tecla or ""))


def ya_hay_atajo(escr, home, ejecutar=subprocess.run, which=shutil.which):
    """True si el usuario ya tiene un atajo que ejecuta `lina pulsar` (así no se duplica ni se pisa)."""
    if escr == "kde":
        for nombre in ("kglobalshortcutsrc", "khotkeysrc"):
            try:
                texto = (_config(home) / nombre).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"lina[ -]pulsar|lina pulsar", texto):
                return True
        return (_datos(home) / "applications" / NOMBRE_KDE).exists()
    if escr == "gnome" and which("gsettings"):
        r = ejecutar(["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"], capture_output=True, text=True)
        return r.returncode == 0 and RUTA_GNOME in r.stdout
    return False


def _lista_gnome(texto):
    texto = texto.strip()
    if texto.startswith("@as"):
        texto = texto[3:].strip()
    try:
        v = ast.literal_eval(texto)
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []
    except (ValueError, SyntaxError):
        return []


def registrar(escr, tecla, comando, home, simular=False, ejecutar=subprocess.run, which=shutil.which):
    """Registra el atajo. Devuelve (hecho, mensaje, anotacion), donde anotacion es lo que hay que guardar para poder quitarlo."""
    if not tecla_valida(tecla, escr):
        return False, f"La tecla «{tecla}» no es válida para {escr.upper()}.", None
    if escr == "kde":
        kwrite = which("kwriteconfig6") or which("kwriteconfig5")
        if not kwrite:
            return False, "No encuentro kwriteconfig (herramientas de KDE).", None
        desktop = _datos(home) / "applications" / NOMBRE_KDE
        contenido = ("[Desktop Entry]\nType=Application\nName=Lina: hablar\nComment=Pulsa para hablar con Lina (y otra vez para terminar)\n"
                     f"Exec={comando} pulsar\nIcon=audio-input-microphone\nNoDisplay=true\nTerminal=false\nX-KDE-GlobalAccel-CommandShortcut=true\n")
        orden = [kwrite, "--file", "kglobalshortcutsrc", "--group", "services", "--group", NOMBRE_KDE, "--key", "_launch", tecla]
        if simular:
            return True, f"[simulación] crearía {desktop} y pondría {tecla} en kglobalshortcutsrc", None
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text(contenido, encoding="utf-8")
        r = ejecutar(orden, capture_output=True, text=True)
        if r.returncode != 0:
            desktop.unlink(missing_ok=True)
            return False, "kwriteconfig no ha podido guardar el atajo: " + (r.stderr or r.stdout or "sin detalle").strip()[:150], None
        return True, (f"Atajo {tecla} registrado en KDE. Si no responde al momento, cierra y abre sesión (o mira Preferencias del sistema → "
                      "Atajos de teclado)."), {"escritorio": "kde", "archivo": str(desktop), "tecla": tecla}
    if escr == "gnome":
        if not which("gsettings"):
            return False, "No encuentro gsettings.", None
        esquema = "org.gnome.settings-daemon.plugins.media-keys"
        if simular:
            return True, f"[simulación] pondría {tecla} → {comando} pulsar con gsettings", None
        actual = ejecutar(["gsettings", "get", esquema, "custom-keybindings"], capture_output=True, text=True)
        lista = _lista_gnome(actual.stdout) if actual.returncode == 0 else []
        if RUTA_GNOME not in lista:
            lista.append(RUTA_GNOME)
        clave = f"{esquema}.custom-keybinding:{RUTA_GNOME}"
        pasos = [["gsettings", "set", esquema, "custom-keybindings", repr(lista)],
                 ["gsettings", "set", clave, "name", "Lina: hablar"], ["gsettings", "set", clave, "command", f"{comando} pulsar"],
                 ["gsettings", "set", clave, "binding", tecla]]
        for p in pasos:
            r = ejecutar(p, capture_output=True, text=True)
            if r.returncode != 0:
                return False, "gsettings ha fallado: " + (r.stderr or r.stdout or "sin detalle").strip()[:150], None
        return True, f"Atajo {tecla} registrado en GNOME.", {"escritorio": "gnome", "ruta": RUTA_GNOME, "tecla": tecla}
    return False, (f"No sé poner atajos globales en este escritorio ({os.environ.get('XDG_CURRENT_DESKTOP') or 'desconocido'}). "
                   f"Crea tú un atajo de teclado que ejecute:  {comando} pulsar"), None


def quitar(anotacion, home, simular=False, ejecutar=subprocess.run, which=shutil.which):
    """Deshace `registrar`. Devuelve un mensaje."""
    if not isinstance(anotacion, dict):
        return "nada que quitar"
    if anotacion.get("escritorio") == "kde":
        ruta = Path(anotacion.get("archivo", ""))
        if ruta.name != NOMBRE_KDE:
            return "ruta del atajo no reconocida: lo dejo como está"
        if simular:
            return f"[simulación] quitaría {ruta}"
        ruta.unlink(missing_ok=True)
        kwrite = which("kwriteconfig6") or which("kwriteconfig5")
        if kwrite:
            ejecutar([kwrite, "--file", "kglobalshortcutsrc", "--group", "services", "--group", NOMBRE_KDE, "--key", "_launch", "--delete"],
                     capture_output=True, text=True)
        return "atajo de KDE quitado"
    if anotacion.get("escritorio") == "gnome" and which("gsettings"):
        if simular:
            return "[simulación] quitaría el atajo de GNOME"
        esquema = "org.gnome.settings-daemon.plugins.media-keys"
        actual = ejecutar(["gsettings", "get", esquema, "custom-keybindings"], capture_output=True, text=True)
        lista = [x for x in _lista_gnome(actual.stdout) if x != RUTA_GNOME]
        ejecutar(["gsettings", "set", esquema, "custom-keybindings", repr(lista)], capture_output=True, text=True)
        ejecutar(["gsettings", "reset-recursively", f"{esquema}.custom-keybinding:{RUTA_GNOME}"], capture_output=True, text=True)
        return "atajo de GNOME quitado"
    return "nada que quitar"
