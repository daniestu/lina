"""Qué escritorio y qué tipo de sesión hay, y cómo se hacen en cada uno las cosas que Lina necesita del escritorio:

  · saber qué ventana tienes delante (título, clase, proceso)
  · capturar la pantalla (o solo la ventana activa)
  · copiar y pegar en el portapapeles

KDE Plasma, GNOME, XFCE, Cinnamon, MATE, sway, Hyprland y cualquier otro con X11 o Wayland tienen herramientas distintas para esto. Cada
una está aquí como un «método» con su orden exacta; se prueban en el orden que corresponde a lo detectado y se usa el primero que funciona.
Si ninguno funciona, el resultado es vacío y SE DICE (nunca se inventa una ventana ni se finge una captura).

Todo recibe `ejecutar`, `which` y `entorno` para probarlo sin escritorio.
"""
import json
from lina.nucleo.idioma import N_, T
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# XDG_CURRENT_DESKTOP (o similar) → identificador. Va de lo más concreto a lo más general (Budgie y Unity son «:GNOME»).
_ESCRITORIOS = (("kde", "kde"), ("plasma", "kde"), ("cinnamon", "cinnamon"), ("xfce", "xfce"), ("mate", "mate"), ("lxqt", "lxqt"),
                ("cosmic", "cosmic"), ("budgie", "gnome"), ("pantheon", "pantheon"), ("deepin", "deepin"), ("hyprland", "hyprland"),
                ("sway", "sway"), ("gnome", "gnome"), ("ubuntu", "gnome"), ("unity", "gnome"))
NOMBRES = {"kde": "KDE Plasma", "gnome": "GNOME", "xfce": "XFCE", "cinnamon": "Cinnamon", "mate": "MATE", "lxqt": "LXQt", "cosmic": "COSMIC",
           "pantheon": "Pantheon", "deepin": "Deepin", "sway": "sway", "hyprland": "Hyprland", "otro": N_("un escritorio sin identificar")}
WLROOTS = {"sway", "hyprland"}


def detectar(entorno=None):
    """{'escritorio': id, 'sesion': 'wayland'|'x11'|'tty'|'desconocida', 'xwayland': bool}."""
    env = os.environ if entorno is None else entorno
    texto = " ".join([env.get("XDG_CURRENT_DESKTOP", ""), env.get("DESKTOP_SESSION", ""), env.get("XDG_SESSION_DESKTOP", "")]).lower()
    palabras = [p for p in re.split(r"[^a-z0-9]+", texto) if p]
    escritorio = "otro"
    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        escritorio = "hyprland"
    elif env.get("SWAYSOCK"):
        escritorio = "sway"
    else:
        for clave, ident in _ESCRITORIOS:
            if any(p == clave or p.startswith(clave) for p in palabras):
                escritorio = ident
                break
    sesion = (env.get("XDG_SESSION_TYPE") or "").lower()
    if sesion not in ("wayland", "x11", "tty"):
        sesion = "wayland" if env.get("WAYLAND_DISPLAY") else "x11" if env.get("DISPLAY") else "desconocida"
    return {"escritorio": escritorio, "sesion": sesion, "xwayland": sesion == "wayland" and bool(env.get("DISPLAY"))}


def _correr(ejecutar, orden, entrada=None, tiempo=4, ignorar_salida=False):
    """(código, salida). Código None si el programa no existe o no responde."""
    try:
        extra = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if ignorar_salida else {"capture_output": True}
        r = ejecutar(orden, text=True, timeout=tiempo, **({"input": entrada} if entrada is not None else {}), **extra)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return r.returncode, (getattr(r, "stdout", "") or "").strip() if not ignorar_salida else ""


class Sesion:
    def __init__(self, entorno=None, ejecutar=subprocess.run, which=shutil.which):
        self.entorno = os.environ if entorno is None else entorno
        self.ejecutar, self.which = ejecutar, which
        self._ultima = (0.0, None)                       # (cuándo, ventana): el contexto pregunta tres veces seguidas
        d = detectar(self.entorno)
        self.escritorio, self.tipo, self.xwayland = d["escritorio"], d["sesion"], d["xwayland"]

    def nombre(self):
        return f"{T(NOMBRES.get(self.escritorio, self.escritorio))} ({self.tipo})"

    def _tiene(self, *programas):
        return all(self.which(p) for p in programas)

    def _ej(self, orden, **k):
        return _correr(self.ejecutar, orden, **k)

    # ------------------------------------------------------------------ ventana activa
    def _ventana_kdotool(self):
        v = {}
        for campo, orden in (("titulo", "getwindowname"), ("clase", "getwindowclassname"), ("pid", "getwindowpid")):
            rc, out = self._ej(["kdotool", "getactivewindow", orden])
            if rc != 0:
                return None
            v[campo] = out
        return v

    def _ventana_xdotool(self):
        rc, ident = self._ej(["xdotool", "getactivewindow"])
        if rc != 0 or not ident:
            return None
        v = {"titulo": self._ej(["xdotool", "getwindowname", ident])[1], "pid": self._ej(["xdotool", "getwindowpid", ident])[1], "clase": ""}
        rc, clase = self._ej(["xdotool", "getwindowclassname", ident])
        if rc != 0 or not clase:
            rc, texto = self._ej(["xprop", "-id", ident, "WM_CLASS"]) if self.which("xprop") else (None, "")
            m = re.findall(r'"([^"]*)"', texto or "")
            clase = m[-1] if m else ""
        v["clase"] = clase
        return v

    def _ventana_sway(self):
        rc, out = self._ej(["swaymsg", "-t", "get_tree", "-r"])
        if rc != 0:
            return None
        try:
            arbol = json.loads(out)
        except ValueError:
            return None
        pila = [arbol]
        while pila:
            n = pila.pop()
            if n.get("focused") and (n.get("pid") or n.get("app_id") or n.get("window_properties")):
                clase = n.get("app_id") or (n.get("window_properties") or {}).get("class") or ""
                return {"titulo": n.get("name") or "", "clase": clase, "pid": str(n.get("pid") or "")}
            pila.extend(n.get("nodes", []) + n.get("floating_nodes", []))
        return None

    def _ventana_hyprland(self):
        rc, out = self._ej(["hyprctl", "activewindow", "-j"])
        if rc != 0:
            return None
        try:
            d = json.loads(out)
        except ValueError:
            return None
        if not isinstance(d, dict) or not d.get("class") and not d.get("title"):
            return None
        return {"titulo": d.get("title") or "", "clase": d.get("class") or "", "pid": str(d.get("pid") or "")}

    def metodos_ventana(self):
        """[(nombre, función)] en el orden que toca para este escritorio, solo los que tienen su programa instalado."""
        todos = {"kdotool": (("kdotool",), self._ventana_kdotool), "xdotool": (("xdotool",), self._ventana_xdotool),
                 "swaymsg": (("swaymsg",), self._ventana_sway), "hyprctl": (("hyprctl",), self._ventana_hyprland)}
        orden = {"kde": ["kdotool", "xdotool"], "sway": ["swaymsg", "xdotool"], "hyprland": ["hyprctl", "xdotool"]}.get(self.escritorio, ["xdotool", "kdotool"])
        return [(n, todos[n][1]) for n in orden if self._tiene(*todos[n][0])]

    def ventana_activa(self, vigencia=0.6):
        """{'titulo','clase','pid','metodo'} de la ventana con el foco; con todo vacío si no se puede saber. Repite la respuesta si es de hace menos de `vigencia` s."""
        t, previa = self._ultima
        if previa is not None and time.monotonic() - t < vigencia:
            return previa
        v = self._leer_ventana()
        self._ultima = (time.monotonic(), v)
        return v

    def _leer_ventana(self):
        for nombre, f in self.metodos_ventana():
            v = f()
            if v and (v.get("titulo") or v.get("clase")):
                try:
                    pid = int(v.get("pid") or 0)
                except ValueError:
                    pid = 0
                return {"titulo": v.get("titulo", ""), "clase": v.get("clase", ""), "pid": pid, "metodo": nombre}
        return {"titulo": "", "clase": "", "pid": 0, "metodo": None}

    def programa_ventanas(self):
        """'kdotool' o 'xdotool' (las dos hablan igual: search, windowactivate, getwindowname…) o None. Para quien las usa directamente."""
        for n, _ in self.metodos_ventana():
            if n in ("kdotool", "xdotool"):
                return n
        return None

    # ------------------------------------------------------------------ captura de pantalla
    def _geometria_activa(self):
        """'x,y WxH' de la ventana activa en sway/Hyprland (para recortar con grim), o ''."""
        if self.escritorio == "sway" and self._tiene("swaymsg"):
            rc, out = self._ej(["swaymsg", "-t", "get_tree", "-r"])
            try:
                pila = [json.loads(out)] if rc == 0 else []
            except ValueError:
                pila = []
            while pila:
                n = pila.pop()
                if n.get("focused") and n.get("rect") and (n.get("pid") or n.get("app_id")):
                    r = n["rect"]
                    return f"{r['x']},{r['y']} {r['width']}x{r['height']}"
                pila.extend(n.get("nodes", []) + n.get("floating_nodes", []))
        if self.escritorio == "hyprland" and self._tiene("hyprctl"):
            rc, out = self._ej(["hyprctl", "activewindow", "-j"])
            try:
                d = json.loads(out) if rc == 0 else {}
                return f"{d['at'][0]},{d['at'][1]} {d['size'][0]}x{d['size'][1]}" if d.get("at") and d.get("size") else ""
            except (ValueError, KeyError, IndexError, TypeError):
                return ""
        return ""

    def _orden_captura(self, programa, destino, activa):
        destino = str(destino)
        if programa == "spectacle":
            return ["spectacle", "-b", "-n", "-a" if activa else "-f", "-o", destino]
        if programa == "grim":
            geo = self._geometria_activa() if activa else ""
            return ["grim", "-g", geo, destino] if geo else ["grim", destino]
        if programa == "gnome-screenshot":
            return ["gnome-screenshot", *(["-w"] if activa else []), "-f", destino]
        if programa == "xfce4-screenshooter":
            return ["xfce4-screenshooter", "-w" if activa else "-f", "-s", destino]
        if programa == "scrot":
            return ["scrot", *(["-u"] if activa else []), destino]
        if programa == "maim":
            ident = self._ej(["xdotool", "getactivewindow"])[1] if activa and self._tiene("xdotool") else ""
            return ["maim", *(["-i", ident] if ident else []), destino]
        if programa == "import":
            ident = self._ej(["xdotool", "getactivewindow"])[1] if activa and self._tiene("xdotool") else ""
            return ["import", "-window", ident or "root", destino]
        return []

    def programas_captura(self):
        """Los programas de captura que valen aquí, en el orden en que se prueban (sin filtrar por instalados)."""
        if self.escritorio == "kde":
            base = ["spectacle", "grim", "scrot", "maim", "import"]
        elif self.escritorio == "gnome":
            base = ["gnome-screenshot", "grim", "scrot", "maim", "import", "spectacle"]
        elif self.escritorio == "xfce":
            base = ["xfce4-screenshooter", "scrot", "maim", "import", "gnome-screenshot", "grim"]
        elif self.escritorio in WLROOTS or self.tipo == "wayland":
            base = ["grim", "spectacle", "gnome-screenshot", "scrot", "maim", "import"]
        else:
            base = ["scrot", "maim", "import", "spectacle", "gnome-screenshot", "xfce4-screenshooter"]
        if self.tipo == "wayland":                                 # scrot, maim e import solo ven X11/XWayland: en Wayland darían una imagen negra o vacía y se
            base = [p for p in base if p not in ("scrot", "maim", "import")]     # la mandaríamos a la IA como si fuera tu pantalla. Mejor decir que no se puede.
        return base

    def capturar(self, destino, activa=False, tiempo=15):
        """Guarda una captura en `destino`. Devuelve True solo si el archivo existe y no está vacío."""
        destino = Path(destino)
        for programa in self.programas_captura():
            if not self._tiene(programa):
                continue
            try:
                destino.unlink(missing_ok=True)
            except OSError:
                pass
            orden = self._orden_captura(programa, destino, activa)
            if not orden:
                continue
            self._ej(orden, tiempo=tiempo)
            try:
                if destino.exists() and destino.stat().st_size > 0:
                    return True
            except OSError:
                pass
        return False

    # ------------------------------------------------------------------ portapapeles
    def _ordenes_portapapeles(self):
        wl = {"copiar": ["wl-copy"], "pegar": ["wl-paste", "-n"], "programa": "wl-copy", "pegar_programa": "wl-paste"}
        xc = {"copiar": ["xclip", "-selection", "clipboard"], "pegar": ["xclip", "-selection", "clipboard", "-o"], "programa": "xclip", "pegar_programa": "xclip"}
        xs = {"copiar": ["xsel", "-b", "-i"], "pegar": ["xsel", "-b", "-o"], "programa": "xsel", "pegar_programa": "xsel"}
        return [wl, xc, xs] if self.tipo == "wayland" else [xc, xs, wl]

    def copiar(self, texto):
        """True si se ha copiado con alguno de los métodos."""
        for m in self._ordenes_portapapeles():
            if self._tiene(m["programa"]):
                rc, _ = self._ej(m["copiar"], entrada=texto, tiempo=5, ignorar_salida=True)
                if rc == 0:
                    return True
        return False

    def pegar(self):
        """Contenido del portapapeles, o '' si no hay o no se puede leer."""
        for m in self._ordenes_portapapeles():
            if self._tiene(m["pegar_programa"]):
                rc, out = self._ej(m["pegar"], tiempo=3)
                if rc == 0:
                    return out
        return ""

    def programa_portapapeles(self):
        """Primer programa instalado que sirve para copiar, o None."""
        return next((m["programa"] for m in self._ordenes_portapapeles() if self._tiene(m["programa"])), None)

    # ------------------------------------------------------------------ qué falta y qué se puede
    def recomendado(self):
        """Paquetes (nombres lógicos de plataforma.PAQUETES) que arreglarían cada carencia, según el escritorio."""
        capt = {"kde": "spectacle", "gnome": "gnome-screenshot", "xfce": "xfce4-screenshooter"}.get(self.escritorio) or ("grim" if self.tipo == "wayland" else "scrot")
        vent = None
        if self.escritorio == "kde":
            vent = None                                         # kdotool no viene en todos los repositorios: se explica aparte
        elif self.escritorio not in WLROOTS:
            vent = "xdotool"
        return {"captura": capt, "portapapeles": "wl-clipboard" if self.tipo == "wayland" else "xclip", "ventanas": vent}

    def capacidades(self):
        """{'ventana': (método|None, nota), 'captura': …, 'portapapeles': …}: lo que funciona AHORA y, si no, por qué."""
        cap = {}
        met = [n for n, _ in self.metodos_ventana()]
        if met:
            nota = ""
            if self.escritorio == "gnome" and self.tipo == "wayland":
                nota = T("en GNOME con Wayland solo se ven las ventanas de programas X11/XWayland (juegos, Steam, Electron); GNOME no deja leer las demás, así que puede no coincidir con la que tienes delante")
            cap["ventana"] = (met[0], nota)
        else:
            falta = T("no encuentro swaymsg/hyprctl") if self.escritorio in WLROOTS else T("instala kdotool") if self.escritorio == "kde" else T("instala xdotool")
            cap["ventana"] = (None, T("no hay con qué leer la ventana activa: ") + falta)
        instal = [p for p in self.programas_captura() if self._tiene(p)]
        cap["captura"] = (instal[0], "") if instal else (None, T("no hay programa de captura: instala {v1}", v1=self.recomendado()['captura']))
        pp = self.programa_portapapeles()
        cap["portapapeles"] = (pp, "") if pp else (None, T("no hay programa de portapapeles: instala {v1}", v1=self.recomendado()['portapapeles']))
        if self.tipo == "wayland" and self.escritorio == "gnome":
            cap["indicador"] = ("ventana", T("GNOME no deja dibujar encima de las ventanas: el resplandor puede no verse; te avisan los pitidos"))
        elif self.tipo == "wayland":
            cap["indicador"] = ("capa", "")
        else:
            cap["indicador"] = ("ventana", T("necesita un compositor con transparencia") if self.tipo == "x11" else "")
        return cap

    def paquetes_que_faltan(self):
        """Nombres lógicos de los paquetes que darían lo que falta HOY (captura, portapapeles, ventanas). Vacío si todo está cubierto."""
        c, r = self.capacidades(), self.recomendado()
        return [r[k] for k in ("captura", "portapapeles", "ventanas") if r.get(k) and not c["ventana" if k == "ventanas" else k][0]]

    def describir(self):
        """Líneas para la IA: qué escritorio es y qué puede y qué no puede hacer Lina en él (sin suponer)."""
        c = self.capacidades()
        l = [f"Escritorio: {self.nombre()}."]
        quitar = {"ventana": "leer la ventana activa", "captura": "capturar la pantalla", "portapapeles": "usar el portapapeles"}
        no = [quitar[k] for k, (m, _) in c.items() if k in quitar and not m]
        if no:
            l.append("En este escritorio NO puedes ahora: " + ", ".join(no) + ". Si te lo piden, dilo tal cual y di qué falta; no lo finjas.")
        if c["ventana"][0] and c["ventana"][1]:
            l.append("Aviso sobre ventanas: " + c["ventana"][1] + ".")
        if self.escritorio != "kde":
            l.append(("Las herramientas pensadas para KDE (ajustes de Plasma por kwriteconfig, D-Bus de KWin, acciones de menú de programas KDE) no valen aquí; "
                     "para ventanas y programas usa solo lo que funcione en ") + NOMBRES.get(self.escritorio, "este escritorio") + ".")
        return l


_actual: dict = {}


def actual():
    """La sesión de este proceso (se crea una vez)."""
    if "s" not in _actual:
        _actual["s"] = Sesion()
    return _actual["s"]


def principal(argv, sesion=None, salida=print):
    s = sesion or Sesion()
    salida(T("Escritorio: {v1}", v1=s.nombre()))
    for k, (m, nota) in s.capacidades().items():
        salida(f"  {'✔' if m else '✘'} {k}: {m or nota}" + (f" ({nota})" if m and nota else ""))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(principal(sys.argv[1:]))
