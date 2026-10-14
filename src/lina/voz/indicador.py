#!/usr/bin/env python3
"""Indicador visual: un resplandor en los bordes de la pantalla que dice qué está haciendo el asistente.

  azul (o el color que elijas)  → te escucha (grabando con el atajo, o esperando tu orden tras «Oye Lina»)
  azul tenue, sin pulso         → ventana de seguimiento: puedes seguir hablando sin decir el nombre
  ámbar, pulsando               → pensando
  verde, suave                  → hablando
  nada                          → en reposo

Funciona en dos mitades:
  · Indicador (dentro del asistente): mira cada poco el estado y se lo cuenta por una tubería al proceso de dibujo.
  · servir()  (proceso aparte, python3 del sistema con GTK3): dibuja. Si está «gtk-layer-shell» usa una capa por encima de todo (como un panel)
    que no coge el foco ni el ratón; si no, usa una ventana normal transparente (menos fiable en Wayland).

Ajustes en activacion.txt:   indicador = si | no      indicador_color = azul | rojo | verde | morado | naranja | #rrggbb
                             indicador_grosor = 40 (píxeles)     indicador_intensidad = 1.0 (0.1 muy suave … 2 fuerte)     indicador_juegos = no (si: también se dibuja con un juego en primer plano)
                             indicador_instalar = si (no: no instala paquetes por su cuenta)
Todo es automático: al arrancar comprueba que haya con qué dibujar y, si falta, instala los paquetes oficiales (indicador_instalar = no lo impide).
Prueba opcional:   lina indicador probar     (recorre los estados y dice qué método de dibujo usa tu equipo)
"""
import math
import os
import re
import subprocess
import sys
import threading
import time

from lina.nucleo import plataforma as PL
from lina.nucleo import rutas as RUT

COLORES = {"azul": "#3b82f6", "rojo": "#ef4444", "verde": "#22c55e", "morado": "#a855f7", "violeta": "#a855f7", "naranja": "#f97316",
           "amarillo": "#eab308", "rosa": "#ec4899", "cian": "#06b6d4", "blanco": "#f1f5f9"}
COLOR_PENSANDO = "#f59e0b"
COLOR_HABLA = "#22c55e"
MODOS = ("off", "escucha", "seguimiento", "pensando", "habla")
GROSOR_MIN, GROSOR_MAX = 12, 300


def color_de(texto, defecto="azul"):
    """«azul» / «#3b82f6» / «3b82f6» → '#rrggbb' (si no se entiende, el color por defecto)."""
    t = str(texto or "").strip().lower()
    if t in COLORES:
        return COLORES[t]
    m = re.fullmatch(r"#?([0-9a-f]{6})", t)
    return "#" + m.group(1) if m else COLORES[defecto]


def hex_a_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def intensidad_de(valor, defecto=1.0):
    try:
        x = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        x = defecto
    return max(0.1, min(2.0, x))


def grosor_de(valor, defecto=40):
    try:
        g = int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        g = defecto
    return max(GROSOR_MIN, min(GROSOR_MAX, g))


def interpretar(linea):
    """Una línea de la tubería → (orden, argumento) o None. Órdenes: modo, color, grosor, salir."""
    partes = str(linea or "").strip().split(None, 1)
    if not partes:
        return None
    orden, arg = partes[0].lower(), (partes[1].strip() if len(partes) > 1 else "")
    if orden == "modo":
        return ("modo", arg) if arg in MODOS else None
    if orden == "color":
        return ("color", color_de(arg))
    if orden == "grosor":
        return ("grosor", grosor_de(arg))
    if orden == "intensidad":
        return ("intensidad", intensidad_de(arg))
    if orden == "salir":
        return ("salir", "")
    return None


LADOS = ("arriba", "abajo", "izquierda", "derecha")


def medidas_de(lado, ancho, alto, grosor):
    """Tamaño (ancho, alto) de la franja de un lado en un monitor de ancho×alto. Las de los lados dejan libres las esquinas."""
    e = max(1, min(grosor, ancho // 2, alto // 2))
    if lado in ("arriba", "abajo"):
        return ancho, e
    return e, max(1, alto - 2 * e)


def anclas_de(lado):
    """Bordes a los que se pega la franja, en el orden (arriba, abajo, izquierda, derecha). Pegada a tres: se estira a lo largo de ese lado."""
    return {"arriba": (True, False, True, True), "abajo": (False, True, True, True),
            "izquierda": (True, True, True, False), "derecha": (True, True, False, True)}[lado]


def degradado_de(lado, ancho, alto):
    """(x0, y0, x1, y1) del degradado: opaco en el borde de la pantalla y transparente hacia dentro."""
    return {"arriba": (0, 0, 0, alto), "abajo": (0, alto, 0, 0),
            "izquierda": (0, 0, ancho, 0), "derecha": (ancho, 0, 0, 0)}[lado]


def estilo_de(modo, color_escucha):
    """(color_hex, alfa_máximo, velocidad_de_pulso) de cada modo. Velocidad 0 = fijo."""
    return {"escucha": (color_escucha, 0.36, 2.0), "seguimiento": (color_escucha, 0.16, 0.0),
            "pensando": (COLOR_PENSANDO, 0.30, 3.0), "habla": (COLOR_HABLA, 0.20, 0.0)}.get(modo, (color_escucha, 0.0, 0.0))


# ----------------------------------------------------------------------------------------------------------------------
# Lado del asistente: decide qué modo toca y se lo manda al proceso de dibujo
# ----------------------------------------------------------------------------------------------------------------------
PYTHON_GTK = "/usr/bin/python3"          # el del sistema: ahí está PyGObject/GTK (el entorno del asistente puede no tenerlo)


def _entorno_hijo():
    """El dibujo corre con el Python del sistema (que tiene GTK): hay que decirle dónde está el paquete de Lina."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(RUT.PAQUETE.parent), env.get("PYTHONPATH", "")) if p)
    return env


PAQUETES = ["gtk3", "gtk-layer-shell", "pygobject", "pycairo"]      # nombres lógicos: plataforma.py los traduce a cada distribución
_SONDA = (
    "import json\n"
    "r = {}\n"
    "try:\n"
    "    import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk; r['gtk'] = True\n"
    "except Exception: r['gtk'] = False\n"
    "try:\n"
    "    import cairo; r['cairo'] = True\n"
    "except Exception: r['cairo'] = False\n"
    "try:\n"
    "    import gi; gi.require_version('GtkLayerShell', '0.1'); from gi.repository import GtkLayerShell; r['capa'] = True\n"
    "except Exception: r['capa'] = False\n"
    "print(json.dumps(r))\n"
)
_MARCA = RUT.DATOS / "indicador_instalacion"
REINTENTO_HORAS = 24


def sondear(python, ejecutar=subprocess.run):
    """Qué piezas de dibujo hay en ese Python: {'gtk': bool, 'cairo': bool, 'capa': bool}."""
    import json
    try:
        r = ejecutar([python, "-c", _SONDA], capture_output=True, text=True, timeout=30)
        d = json.loads((r.stdout or "").strip().splitlines()[-1])
        return {k: bool(d.get(k)) for k in ("gtk", "cairo", "capa")}
    except Exception:
        return {"gtk": False, "cairo": False, "capa": False}


def instalar_dependencias(log=print, ejecutar=subprocess.run, plataforma=None, marca=None, ahora=time.time):
    """Instala (con el gestor de la distribución y sudo sin contraseña) lo que falta para dibujar. Devuelve True si lo ha conseguido."""
    return PL.instalar(PAQUETES, lambda t: log("Indicador: " + t), ejecutar=ejecutar, plataforma=plataforma, marca=marca or _MARCA, ahora=ahora)


class Indicador:
    def __init__(self, asistente, cfg=None, log=print, lanzar=None, reloj=time.time, python=None):
        self.a = asistente
        self.cfg = cfg
        self.log = log
        self.reloj = reloj
        self.lanzar = lanzar or self._lanzar
        self.python = python or (PYTHON_GTK if os.path.exists(PYTHON_GTK) else sys.executable)
        self.proc = None
        self.modo_enviado = None
        self.ajustes_enviados = None
        self.fallos = 0
        self.rendido = False                  # tras varios fallos seguidos, deja de intentarlo (y lo dice una vez)
        self.listo = False                    # ya se sabe que hay con qué dibujar (se comprueba, y se instala si falta, al arrancar)
        self.sonda = sondear
        self.instalar = instalar_dependencias
        self._juego = (0.0, False)
        self._parar = threading.Event()
        self._hilo = None

    # --- ajustes
    def _si(self, clave, defecto=False):
        try:
            return self.cfg.si(clave)
        except Exception:
            return defecto

    def _val(self, clave, defecto=""):
        try:
            return self.cfg.valores.get(clave, defecto)
        except Exception:
            return defecto

    def activo(self):
        return self._si("indicador", True)

    # --- qué modo toca ahora
    def hay_juego(self):
        t, v = self._juego
        if self.reloj() - t > 2.0:                           # detectarlo cuesta una consulta a kdotool: solo cada 2 s
            try:
                v = bool(self.a.en_juego())
            except Exception:
                v = False
            self._juego = (self.reloj(), v)
        return v

    def modo_deseado(self):
        if not self.activo():
            return "off"
        if not self._si("indicador_juegos") and self.hay_juego():
            return "off"
        estado = getattr(self.a, "estado", "esperando")
        ml = getattr(self.a, "manos_libres", None)
        if estado == "grabando":
            return "escucha"
        if ml is not None and getattr(ml, "modo", None) == "orden":
            return "escucha"                                  # dijiste «Oye Lina» y espera tu orden
        if estado == "pensando":
            return "pensando"
        if estado == "hablando":
            return "habla"
        if ml is not None and estado == "esperando" and self.reloj() <= getattr(ml, "seguimiento_hasta", 0.0):
            return "seguimiento"
        return "off"

    # --- proceso de dibujo
    def _lanzar(self):
        return subprocess.Popen([self.python, "-m", "lina.voz.indicador", "--servir"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1, env=_entorno_hijo())

    def _vigilar_salida(self, proc):
        """Lee lo que cuenta el proceso (qué método usa o por qué falla) y lo apunta en el registro."""
        try:
            for linea in proc.stdout:
                linea = linea.strip()
                if linea:
                    self.log("Indicador: " + linea[:200])
        except (OSError, ValueError):
            pass

    def _asegurar_proceso(self):
        if self.rendido:
            return False
        if self.proc is not None and self.proc.poll() is None:
            return True
        if self.proc is not None:
            self.fallos += 1
            self.log(f"Indicador: el proceso de dibujo se ha cerrado (código {self.proc.returncode})")
            self.proc = None
            self.modo_enviado = self.ajustes_enviados = None
            if self.fallos >= 3:
                self.rendido = True
                self.log("Indicador: se ha cerrado demasiadas veces; lo dejo apagado. Mira:  lina indicador probar")
                return False
        try:
            self.proc = self.lanzar()
        except OSError as e:
            self.fallos += 1
            self.log(f"Indicador: no he podido lanzar el dibujo ({e})")
            if self.fallos >= 3:
                self.rendido = True
            return False
        threading.Thread(target=self._vigilar_salida, args=(self.proc,), daemon=True).start()
        return True

    def _enviar(self, linea):
        try:
            self.proc.stdin.write(linea + "\n")
            self.proc.stdin.flush()
            return True
        except (OSError, ValueError, AttributeError):
            return False

    def _cerrar_proceso(self):
        p, self.proc = self.proc, None
        self.modo_enviado = self.ajustes_enviados = None
        if p is None:
            return
        try:
            p.stdin.write("salir\n")
            p.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            p.wait(timeout=1.5)
        except (subprocess.TimeoutExpired, OSError):
            try:
                p.kill()
            except OSError:
                pass

    def paso(self):
        """Una vuelta: recarga ajustes si cambiaron, calcula el modo y lo manda si es distinto."""
        try:
            self.cfg.recargar_si_cambio()
        except Exception:
            pass
        modo = self.modo_deseado()
        if modo == "off" and self.proc is None:
            return modo                                       # nada que apagar: ni siquiera se arranca el proceso
        if not self.listo:
            return modo
        if not self._asegurar_proceso():
            return modo
        ajustes = (color_de(self._val("indicador_color", "azul")), grosor_de(self._val("indicador_grosor", "40")),
                   intensidad_de(self._val("indicador_intensidad", "1.0")))
        if ajustes != self.ajustes_enviados:
            if self._enviar(f"color {ajustes[0]}") and self._enviar(f"grosor {ajustes[1]}") and self._enviar(f"intensidad {ajustes[2]}"):
                self.ajustes_enviados = ajustes
        if modo != self.modo_enviado:
            if self._enviar(f"modo {modo}"):
                self.modo_enviado = modo
        return modo

    def _bucle(self):
        while not self._parar.is_set():
            try:
                self.paso()
            except Exception as e:                            # el indicador nunca debe tumbar al asistente
                self.log(f"Indicador: error ({e!r})")
                self._parar.wait(2.0)
            self._parar.wait(0.15)
        self._cerrar_proceso()

    def preparar(self):
        """Comprueba que el Python del sistema tiene GTK3, cairo y gtk-layer-shell; si falta algo y se puede, lo instala solo."""
        d = self.sonda(self.python)
        if not all(d.values()):
            if self._si("indicador_instalar", True):
                if self.instalar(self.log):
                    d = self.sonda(self.python)
        if d.get("gtk") and d.get("cairo"):
            self.listo = True
            if not d.get("capa"):
                self.log("Indicador: sin gtk-layer-shell se dibuja con una ventana normal (en Wayland puede quedar detrás o no verse)")
        else:
            self.rendido = True
            self.log("Indicador: no hay con qué dibujar (falta " + ", ".join(k for k in ("gtk", "cairo") if not d.get(k)) + "); queda apagado")
        return self.listo

    def iniciar(self):
        def arrancar():
            self.preparar()
            self._bucle()
        self._hilo = threading.Thread(target=arrancar, daemon=True)
        self._hilo.start()

    def cerrar(self):
        self._parar.set()
        if self._hilo:
            self._hilo.join(timeout=3)
        else:
            self._cerrar_proceso()


# ----------------------------------------------------------------------------------------------------------------------
# Lado del dibujo (proceso aparte, python3 del sistema)
# ----------------------------------------------------------------------------------------------------------------------
def servir(entrada=None, salida=None):
    """Bucle del proceso de dibujo: lee órdenes de la entrada estándar y pinta los bordes con GTK3."""
    entrada = entrada or sys.stdin
    salida = salida or sys.stdout

    def decir(t):
        print(t, file=salida, flush=True)

    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gtk, Gdk, GLib
        import cairo
    except Exception as e:                                    # sin GTK3 o sin cairo
        decir(f"SIN GTK3/cairo ({e})")
        return 2
    if Gdk.Display.get_default() is None:
        decir("SIN PANTALLA (no hay sesión gráfica accesible para este proceso)")
        return 3
    capa = None
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell as capa
        if not capa.is_supported():
            capa = None
    except Exception:
        capa = None
    decir("método: capa layer-shell (por encima de todo)" if capa else
          "método: ventana normal transparente (poco fiable en Wayland: falta gtk-layer-shell)")

    estado = {"modo": "off", "color": COLORES["azul"], "grosor": 40, "intensidad": 1.0, "t0": time.time(), "ventanas": []}

    def pintar(ventana, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        modo = estado["modo"]
        if modo == "off":
            return False
        color, alfa, vel = estilo_de(modo, estado["color"])
        if vel > 0:
            alfa *= 0.62 + 0.38 * (0.5 + 0.5 * math.sin((time.time() - estado["t0"]) * vel))
        alfa = min(1.0, alfa * estado["intensidad"])
        r, g, b = hex_a_rgb(color)
        w, h = ventana.get_allocated_width(), ventana.get_allocated_height()
        x0, y0, x1, y1 = degradado_de(ventana.lado_lina, w, h)
        grad = cairo.LinearGradient(x0, y0, x1, y1)
        grad.add_color_stop_rgba(0.0, r, g, b, alfa)
        grad.add_color_stop_rgba(0.25, r, g, b, alfa * 0.30)
        grad.add_color_stop_rgba(1.0, r, g, b, 0.0)
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.rectangle(0, 0, w, h)
        cr.set_source(grad)
        cr.fill()
        return False

    def sin_ratón(widget, *_):
        """Deja vacía la zona de entrada de la ventana: el ratón y el teclado pasan a lo que hay debajo. Se hace por tres vías porque en Wayland
        la capa se vuelve a crear cada vez que se muestra, y con ella se pierde lo anterior."""
        region = cairo.Region()
        try:
            widget.input_shape_combine_region(region)
        except Exception:
            pass
        ventana = widget.get_window()
        if ventana is not None:
            try:
                ventana.input_shape_combine_region(region, 0, 0)
            except Exception:
                pass
            try:
                ventana.set_pass_through(True)
            except Exception:
                pass

    def crear(monitor, lado):
        """Una franja fina pegada a un borde del monitor. Si el compositor no dejara pasar el ratón, solo bloquearía la franja y no toda la pantalla."""
        v = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        v.lado_lina = lado
        v.set_title("lina-indicador")
        v.set_app_paintable(True)
        v.set_decorated(False)
        v.set_skip_taskbar_hint(True)
        v.set_skip_pager_hint(True)
        v.set_accept_focus(False)
        v.set_can_focus(False)
        v.set_focus_on_map(False)
        v.set_keep_above(True)
        visual = v.get_screen().get_rgba_visual()
        if visual is not None:
            v.set_visual(visual)
        geo = monitor.get_geometry()
        v.set_default_size(*medidas_de(lado, geo.width, geo.height, estado["grosor"]))
        if capa:
            capa.init_for_window(v)
            capa.set_layer(v, capa.Layer.OVERLAY)
            for borde, ancla in zip((capa.Edge.TOP, capa.Edge.BOTTOM, capa.Edge.LEFT, capa.Edge.RIGHT), anclas_de(lado)):
                capa.set_anchor(v, borde, ancla)
            capa.set_exclusive_zone(v, -1)
            capa.set_keyboard_mode(v, capa.KeyboardMode.NONE)
            capa.set_namespace(v, "lina-indicador")
            capa.set_monitor(v, monitor)
        v.connect("draw", pintar)

        v.connect("realize", sin_ratón)                      # que el ratón y los clics lo atraviesen: se repite al crearse y cada vez que se muestra
        v.connect("map", sin_ratón)
        v.connect("map-event", lambda w, e: sin_ratón(w) or False)
        return v

    def margenes(v, lado, e):
        """Las franjas de los lados no pisan las de arriba y abajo en las esquinas (si no, ahí el color se sumaría dos veces)."""
        if capa and lado in ("izquierda", "derecha"):
            capa.set_margin(v, capa.Edge.TOP, e)
            capa.set_margin(v, capa.Edge.BOTTOM, e)

    def montar():
        pantalla = Gdk.Display.get_default()
        vistos = set()
        for i in range(pantalla.get_n_monitors()):
            m = pantalla.get_monitor(i)
            g = m.get_geometry()
            clave = (g.x, g.y, g.width, g.height)
            if clave in vistos:                              # pantallas duplicadas (espejo): una sola capa; la segunda la cierra el compositor
                continue
            vistos.add(clave)
            for lado in LADOS:
                v = crear(m, lado)
                margenes(v, lado, estado["grosor"])
                estado["ventanas"].append(v)

    def ajustar_tamano():
        e = estado["grosor"]
        if estado.get("grosor_aplicado") == e:
            return
        estado["grosor_aplicado"] = e
        for v in estado["ventanas"]:
            ancho, alto = (-1, e) if v.lado_lina in ("arriba", "abajo") else (e, -1)
            v.set_size_request(ancho, alto)
            margenes(v, v.lado_lina, e)

    def refrescar():
        visible = estado["modo"] != "off"
        ajustar_tamano()
        for v in estado["ventanas"]:
            if visible:
                if not v.get_visible():
                    v.show_all()
                    GLib.idle_add(lambda ventana=v: sin_ratón(ventana) and False)      # y otra vez ya mostrada
                v.queue_draw()
            elif v.get_visible():
                v.hide()
        return True

    def orden(linea):
        o = interpretar(linea)
        if not o:
            return
        if o[0] == "modo":
            if o[1] != estado["modo"]:
                estado["t0"] = time.time()
            estado["modo"] = o[1]
        elif o[0] == "color":
            estado["color"] = o[1]
        elif o[0] == "grosor":
            estado["grosor"] = o[1]
        elif o[0] == "intensidad":
            estado["intensidad"] = o[1]
        elif o[0] == "salir":
            Gtk.main_quit()
        refrescar()

    pendiente = {"buf": b""}

    def leer(fd, condicion):
        try:
            datos = os.read(entrada.fileno(), 4096) if condicion & GLib.IO_IN else b""
        except OSError:
            datos = b""
        if not datos:                                         # el asistente se ha cerrado (o la tubería falló): yo también
            Gtk.main_quit()
            return False
        pendiente["buf"] += datos
        while b"\n" in pendiente["buf"]:
            linea, _, pendiente["buf"] = pendiente["buf"].partition(b"\n")
            orden(linea.decode("utf-8", "replace"))
        return True

    montar()
    GLib.io_add_watch(entrada.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, leer)
    GLib.timeout_add(33, refrescar)
    decir("listo")
    Gtk.main()
    return 0


def probar():
    """Enciende cada modo unos segundos para ver los colores y qué método de dibujo se usa."""
    p = subprocess.Popen([PYTHON_GTK if os.path.exists(PYTHON_GTK) else sys.executable, "-m", "lina.voz.indicador", "--servir"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=_entorno_hijo())

    def lee():
        for l in p.stdout:
            print("  " + l.rstrip())
    threading.Thread(target=lee, daemon=True).start()
    time.sleep(1.5)
    for modo, texto in (("escucha", "te escucho (azul, pulsando)"), ("seguimiento", "ventana de seguimiento (azul tenue)"),
                        ("pensando", "pensando (ámbar)"), ("habla", "hablando (verde)")):
        if p.poll() is not None:
            print(f"El dibujo se ha cerrado (código {p.returncode}); mira el mensaje de arriba.")
            return 1
        print(f"→ {texto}")
        p.stdin.write(f"modo {modo}\n")
        p.stdin.flush()
        time.sleep(3)
    p.stdin.write("modo off\nsalir\n")
    p.stdin.flush()
    time.sleep(0.5)
    print("Hecho. ¿Has visto el resplandor en los bordes? Si no: mira el «método» de arriba.")
    return 0


if __name__ == "__main__":
    if "--servir" in sys.argv:
        sys.exit(servir())
    if "probar" in sys.argv[1:2]:
        sys.exit(probar())
    print(__doc__)
