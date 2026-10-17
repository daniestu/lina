"""El atajo de teclado global que ejecuta `lina pulsar`.

Lo registra en el escritorio que haya (KDE Plasma, GNOME, Cinnamon o XFCE) sin pisar uno que el usuario ya tenga; en los demás (sway, Hyprland, MATE…)
enseña la línea exacta que hay que añadir. Nunca edita a escondidas archivos de configuración del usuario.
Cada registro deja anotado qué ha creado, para que `lina uninstall` lo quite.
"""
import ast
from lina.nucleo.idioma import T
import os
import re
import shutil
import subprocess
from pathlib import Path

NOMBRE_KDE = "lina-pulsar.desktop"
RUTA_GNOME = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lina/"
RUTA_CINNAMON = "/org/cinnamon/desktop/keybindings/custom-keybindings/lina/"
RUTA_XFCE = "/commands/custom/"
TECLA_POR_DEFECTO = {"kde": "Meta+Space", "gnome": "<Control><Alt>space", "cinnamon": "<Control><Alt>space", "xfce": "<Primary><Alt>space"}
_TECLA_KDE = re.compile(r"[A-Za-z0-9_+]{1,40}")
_TECLA_GNOME = re.compile(r"(?:<[A-Za-z]{3,8}>){0,4}[A-Za-z0-9_]{1,20}")


def escritorio(entorno=None):
    """'kde' | 'gnome' | 'cinnamon' | 'xfce' | 'sway' | 'hyprland' | 'otro' según el entorno de la sesión."""
    from lina.escritorio import sesion as SES
    e = SES.detectar(entorno)["escritorio"]
    return e if e in ("kde", "gnome", "cinnamon", "xfce", "sway", "hyprland") else "otro"


def _datos(home):
    return Path(os.environ.get("XDG_DATA_HOME") or Path(home) / ".local/share")


def _config(home):
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path(home) / ".config")


def tecla_valida(tecla, escr):
    return bool((_TECLA_KDE if escr == "kde" else _TECLA_GNOME).fullmatch(tecla or ""))


def a_mano(escr, comando):
    """Qué hacer cuando no se puede registrar solo: la línea exacta para ese escritorio."""
    if escr == "sway":
        return T("Añade a ~/.config/sway/config:  bindsym $mod+space exec {comando} pulsar   (y recarga con $mod+Shift+c)", comando=comando)
    if escr == "hyprland":
        return T("Añade a ~/.config/hypr/hyprland.conf:  bind = SUPER, SPACE, exec, {comando} pulsar", comando=comando)
    return T("Crea tú un atajo de teclado global (en los ajustes de tu escritorio) que ejecute:  {comando} pulsar", comando=comando)


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
    if escr == "cinnamon" and which("gsettings"):
        r = ejecutar(["gsettings", "get", "org.cinnamon.desktop.keybindings", "custom-list"], capture_output=True, text=True)
        return r.returncode == 0 and "lina" in _lista_gnome(r.stdout)
    if escr == "xfce" and which("xfconf-query"):
        r = ejecutar(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-lv"], capture_output=True, text=True)
        return r.returncode == 0 and bool(re.search(r"lina(?:-pulsar)? pulsar|/lina pulsar", r.stdout))
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
        return False, T("La tecla «{tecla}» no es válida para {v1}.", tecla=tecla, v1=escr.upper()), None
    if escr == "kde":
        kwrite = which("kwriteconfig6") or which("kwriteconfig5")
        if not kwrite:
            return False, T("No encuentro kwriteconfig (herramientas de KDE)."), None
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
            return False, T("kwriteconfig no ha podido guardar el atajo: ") + (r.stderr or r.stdout or "sin detalle").strip()[:150], None
        return True, (T("Atajo {tecla} registrado en KDE. Si no responde al momento, cierra y abre sesión (o mira Preferencias del sistema → Atajos de teclado).", tecla=tecla)), {"escritorio": "kde", "archivo": str(desktop), "tecla": tecla}
    if escr == "gnome":
        if not which("gsettings"):
            return False, T("No encuentro gsettings."), None
        esquema = "org.gnome.settings-daemon.plugins.media-keys"
        if simular:
            return True, f"[simulación] pondría {tecla} → {comando} pulsar con gsettings", None
        actual = ejecutar(["gsettings", "get", esquema, "custom-keybindings"], capture_output=True, text=True)
        lista = _lista_gnome(actual.stdout) if actual.returncode == 0 else []
        if RUTA_GNOME not in lista:
            lista.append(RUTA_GNOME)
        clave = f"{esquema}.custom-keybinding:{RUTA_GNOME}"
        pasos = [["gsettings", "set", esquema, "custom-keybindings", repr(lista)],
                 ["gsettings", "set", clave, "name", T("Lina: hablar")], ["gsettings", "set", clave, "command", f"{comando} pulsar"],
                 ["gsettings", "set", clave, "binding", tecla]]
        for p in pasos:
            r = ejecutar(p, capture_output=True, text=True)
            if r.returncode != 0:
                return False, T("gsettings ha fallado: ") + (r.stderr or r.stdout or "sin detalle").strip()[:150], None
        return True, T("Atajo {tecla} registrado en GNOME.", tecla=tecla), {"escritorio": "gnome", "ruta": RUTA_GNOME, "tecla": tecla}
    if escr == "cinnamon":
        if not which("gsettings"):
            return False, T("No encuentro gsettings."), None
        if simular:
            return True, f"[simulación] pondría {tecla} → {comando} pulsar en Cinnamon", None
        esquema = "org.cinnamon.desktop.keybindings"
        actual = ejecutar(["gsettings", "get", esquema, "custom-list"], capture_output=True, text=True)
        lista = _lista_gnome(actual.stdout) if actual.returncode == 0 else []
        if "lina" not in lista:
            lista.append("lina")
        clave = f"{esquema}.custom-keybinding:{RUTA_CINNAMON}"
        pasos = [["gsettings", "set", clave, "name", T("Lina: hablar")], ["gsettings", "set", clave, "command", f"{comando} pulsar"],
                 ["gsettings", "set", clave, "binding", repr([tecla])], ["gsettings", "set", esquema, "custom-list", repr(lista)]]
        for p in pasos:
            r = ejecutar(p, capture_output=True, text=True)
            if r.returncode != 0:
                return False, T("gsettings ha fallado: ") + (r.stderr or r.stdout or "sin detalle").strip()[:150], None
        return True, T("Atajo {tecla} registrado en Cinnamon.", tecla=tecla), {"escritorio": "cinnamon", "ruta": RUTA_CINNAMON, "tecla": tecla}
    if escr == "xfce":
        if not which("xfconf-query"):
            return False, T("No encuentro xfconf-query."), None
        propiedad = f"{RUTA_XFCE}{tecla}"
        if simular:
            return True, f"[simulación] pondría {tecla} → {comando} pulsar en XFCE", None
        r = ejecutar(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", propiedad, "-n", "-t", "string", "-s", f"{comando} pulsar"], capture_output=True, text=True)
        if r.returncode != 0:
            return False, T("xfconf-query ha fallado: ") + (r.stderr or r.stdout or "sin detalle").strip()[:150], None
        return True, T("Atajo {tecla} registrado en XFCE.", tecla=tecla), {"escritorio": "xfce", "propiedad": propiedad, "tecla": tecla}
    return False, a_mano(escr, comando), None


def quitar(anotacion, home, simular=False, ejecutar=subprocess.run, which=shutil.which):
    """Deshace `registrar`. Devuelve un mensaje."""
    if not isinstance(anotacion, dict):
        return T("nada que quitar")
    escr = anotacion.get("escritorio")
    if escr == "kde":
        ruta = Path(anotacion.get("archivo", ""))
        if ruta.name != NOMBRE_KDE:
            return T("ruta del atajo no reconocida: lo dejo como está")
        if simular:
            return f"[simulación] quitaría {ruta}"
        ruta.unlink(missing_ok=True)
        kwrite = which("kwriteconfig6") or which("kwriteconfig5")
        if kwrite:
            ejecutar([kwrite, "--file", "kglobalshortcutsrc", "--group", "services", "--group", NOMBRE_KDE, "--key", "_launch", "--delete"],
                     capture_output=True, text=True)
        return T("atajo de KDE quitado")
    if escr == "gnome" and which("gsettings"):
        if simular:
            return "[simulación] quitaría el atajo de GNOME"
        esquema = "org.gnome.settings-daemon.plugins.media-keys"
        actual = ejecutar(["gsettings", "get", esquema, "custom-keybindings"], capture_output=True, text=True)
        lista = [x for x in _lista_gnome(actual.stdout) if x != RUTA_GNOME]
        ejecutar(["gsettings", "set", esquema, "custom-keybindings", repr(lista)], capture_output=True, text=True)
        ejecutar(["gsettings", "reset-recursively", f"{esquema}.custom-keybinding:{RUTA_GNOME}"], capture_output=True, text=True)
        return T("atajo de GNOME quitado")
    if escr == "cinnamon" and which("gsettings"):
        if simular:
            return "[simulación] quitaría el atajo de Cinnamon"
        esquema = "org.cinnamon.desktop.keybindings"
        actual = ejecutar(["gsettings", "get", esquema, "custom-list"], capture_output=True, text=True)
        lista = [x for x in _lista_gnome(actual.stdout) if x != "lina"]
        ejecutar(["gsettings", "set", esquema, "custom-list", repr(lista)], capture_output=True, text=True)
        ejecutar(["gsettings", "reset-recursively", f"{esquema}.custom-keybinding:{RUTA_CINNAMON}"], capture_output=True, text=True)
        return T("atajo de Cinnamon quitado")
    if escr == "xfce" and which("xfconf-query"):
        propiedad = str(anotacion.get("propiedad", ""))
        if not propiedad.startswith(RUTA_XFCE):
            return T("propiedad del atajo no reconocida: lo dejo como está")
        if simular:
            return "[simulación] quitaría el atajo de XFCE"
        ejecutar(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-r", "-p", propiedad], capture_output=True, text=True)
        return T("atajo de XFCE quitado")
    return T("nada que quitar")
