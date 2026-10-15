"""`lina bienvenida`: la primera conversación con Lina, en la terminal y en español.

Deja lista la parte que solo puede hacer el usuario: la clave de Gemini (gratuita), comprobar que el micrófono funciona, cómo se llama el
asistente, cuánta libertad tiene y si puede enviar capturas de pantalla. Cada paso se puede saltar y se puede repetir cuando se quiera.
Nada se decide por el usuario: lo que da permisos (autonomía, capturas) se pregunta con su explicación.
"""
import json
import time

import requests

from lina.nucleo import ajustes as AJ
from lina.nucleo import claves as CL
from lina.nucleo import privacidad as PRIV
from lina.nucleo import rutas as RUT

ENLACE_CLAVE = "https://aistudio.google.com/apikey"
MODELO_PRUEBA = "gemini-flash-lite-latest"
MARCA = "bienvenida.json"
AVISO_SIN_CLAVE = ("Todavía no tengo clave de Gemini, así que no puedo responderte. Es gratis: abre una terminal y escribe lina bienvenida, "
                   "o directamente lina clave gemini.")
PERFILES = {"1": ("autonomo", "Autónoma: hace sola casi todo y te pregunta solo por lo crítico (borrar de verdad, instalar de fuera, apagar…)."),
            "2": ("equilibrado", "Equilibrada: además te pregunta antes de cambiar nada tras haber leído contenido de internet."),
            "3": ("prudente", "Prudente: te pide confirmación para casi todo lo que cambie algo en tu equipo.")}


# ---------------------------------------------------------------- comprobaciones (inyectables para probarlas sin red ni micrófono)
def validar_clave(clave, enviar=requests.post):
    """(True|False|None, detalle). None: no se ha podido comprobar (sin red); la clave se guarda igualmente."""
    try:
        r = enviar(f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO_PRUEBA}:generateContent", headers={"x-goog-api-key": clave},
                   json={"contents": [{"role": "user", "parts": [{"text": "Responde solo: ok"}]}]}, timeout=15)
    except requests.RequestException:
        return None, "no he podido conectar para comprobarla"
    if r.status_code == 200:
        return True, "funciona"
    if r.status_code in (400, 401, 403):
        return False, "Google dice que esa clave no es válida"
    if r.status_code == 429:
        return True, "es válida (ahora mismo has llegado al límite gratuito)"
    return None, f"Google ha contestado {r.status_code}; la guardo y se comprobará al usarla"


def medir_microfono(segundos=2.0, grabar=None):
    """(nivel 0-1 aproximado, mensaje de error). Mide el volumen máximo de unos segundos de micrófono."""
    try:
        if grabar is None:
            import numpy as np
            import sounddevice as sd
            def grabar(s):
                datos = sd.rec(int(s * 16000), samplerate=16000, channels=1, dtype="float32")
                sd.wait()
                return float(np.abs(datos).max())
        return float(grabar(segundos)), None
    except Exception as e:                  # sin micrófono, sin PortAudio, dispositivo ocupado…
        return None, f"{type(e).__name__}: {e}"[:160]


def barra(nivel, ancho=30):
    llenos = max(0, min(ancho, int(round(min(1.0, nivel * 4) * ancho))))
    return "█" * llenos + "·" * (ancho - llenos)


# ---------------------------------------------------------------- pasos
class Charla:
    def __init__(self, entrada=input, secreto=None, salida=print, terminal=True, ajustes=None, enviar=requests.post, grabar=None, ejecutar=None):
        import getpass
        self.entrada, self.secreto, self.salida = entrada, secreto or getpass.getpass, salida
        self.terminal, self.enviar, self.grabar = terminal, enviar, grabar
        self._aj, self.ejecutar = ajustes, ejecutar
        self.resultado = {}

    @property
    def aj(self):
        if self._aj is None:
            self._aj = AJ.actuales(log=lambda m: None)
        return self._aj

    def pregunta(self, texto, defecto=""):
        try:
            r = self.entrada(texto).strip()
        except (EOFError, KeyboardInterrupt):
            raise KeyboardInterrupt
        return r or defecto

    def si_no(self, texto, defecto=True):
        r = self.pregunta(f"{texto} [{'S/n' if defecto else 's/N'}] ").lower()
        return defecto if not r else r in ("s", "si", "sí", "y", "yes")

    def titulo(self, n, texto):
        self.salida(f"\n{n}. {texto}")

    # 1
    def paso_clave(self):
        self.titulo(1, "Clave de Gemini (la inteligencia de Lina)")
        if CL.obtener("gemini"):
            self.salida("  ✔ Ya hay una clave de Gemini guardada.")
            if not self.si_no("  ¿La compruebo?", False):
                self.resultado["clave"] = "ya estaba"
                return
            ok, detalle = validar_clave(CL.obtener("gemini"), self.enviar)
            self.salida(f"  {'✔' if ok else '!' if ok is None else '✘'} {detalle}")
            self.resultado["clave"] = "ya estaba"
            return
        self.salida(f"  Lina usa Gemini para entenderte. La clave es gratuita (no hace falta tarjeta):\n    1) abre  {ENLACE_CLAVE}\n"
                    "    2) entra con tu cuenta de Google y pulsa «Crear clave de API»\n    3) copia la clave y pégala aquí (no se ve al escribir).")
        for intento in range(3):
            clave = self.secreto("  Clave (Intro para saltar este paso): ").strip()
            if not clave:
                self.salida("  Vale. Sin clave Lina no puede responder; cuando la tengas:  lina clave gemini")
                self.resultado["clave"] = "saltado"
                return
            ok, detalle = validar_clave(clave, self.enviar)
            if ok is False:
                self.salida(f"  ✘ {detalle}. Prueba otra vez (quedan {2 - intento}).")
                continue
            try:
                _, donde = CL.guardar("gemini", clave)
            except ValueError as e:
                self.salida(f"  ✘ No la he guardado: {e}.")
                continue
            self.salida(f"  ✔ Clave guardada en {donde} ({detalle}).")
            self.resultado["clave"] = "guardada"
            return
        self.resultado["clave"] = "fallida"

    # 2
    def paso_microfono(self):
        self.titulo(2, "Micrófono")
        if not self.si_no("  Voy a escucharte 2 segundos: di algo en voz normal. ¿Empezamos?"):
            self.resultado["microfono"] = "saltado"
            return
        nivel, error = medir_microfono(2.0, self.grabar)
        if error:
            self.salida(f"  ✘ No he podido usar el micrófono ({error}).\n    Mira que esté enchufado y no silenciado, y repite luego con:  lina bienvenida")
            self.resultado["microfono"] = "fallo"
        elif nivel < 0.01:
            self.salida(f"  ! No oigo nada ({barra(nivel)}). Revisa que no esté silenciado ni sea otro dispositivo (ajustes de sonido).")
            self.resultado["microfono"] = "silencio"
        else:
            self.salida(f"  ✔ Te oigo: {barra(nivel)}")
            self.resultado["microfono"] = "bien"

    # 3
    def paso_nombre(self):
        self.titulo(3, "Cómo se llama")
        actual = self.aj.get("asistente", "nombre")
        nombre = self.pregunta(f"  Nombre del asistente, y palabra para activarlo («Oye {actual}») [Intro = {actual}]: ", actual)
        if nombre != actual:
            try:
                self.aj.establecer("asistente", "nombre", nombre)
            except ValueError as e:
                self.salida(f"  ✘ {e}")
                return
        self.salida(f"  ✔ Se llama {nombre}.")
        self.resultado["nombre"] = nombre

    # 4
    def paso_autonomia(self):
        self.titulo(4, "Cuánta libertad tiene")
        actual = self.aj.get("autonomia", "perfil")
        for k, (clave, texto) in PERFILES.items():
            self.salida(f"  {k}) {texto}" + ("   ← ahora" if clave == actual else ""))
        self.salida("  Hagas lo que hagas, lo crítico (discos, arranque, cuentas, dinero) siempre lo confirmas tú con el atajo de teclado.")
        r = self.pregunta("  Elige 1, 2 o 3 [Intro = dejarlo como está]: ")
        if r in PERFILES:
            self.aj.establecer("autonomia", "perfil", PERFILES[r][0])
            self.salida(f"  ✔ Perfil {PERFILES[r][0]}.")
            self.resultado["perfil"] = PERFILES[r][0]
        else:
            self.resultado["perfil"] = actual

    # 5
    def paso_privacidad(self):
        self.titulo(5, "Privacidad: capturas de pantalla")
        PRIV.principal([], entrada=self.entrada, salida=self.salida, ajustes=self.aj, es_terminal=self.terminal)
        self.resultado["capturas"] = PRIV.estado(self.aj)

    def contar(self):
        s = self.resultado
        self.salida("\nListo. Resumen:")
        self.salida(f"  Clave de Gemini: {s.get('clave', '-')} · Micrófono: {s.get('microfono', '-')} · Perfil: {s.get('perfil', '-')} · Capturas: {s.get('capturas', '-')}")
        if s.get("clave") in ("saltado", "fallida"):
            self.salida("  Falta la clave de Gemini: sin ella no puedo responder.  →  lina clave gemini")
        self.salida(f"  Para hablarme: pulsa tu atajo o di «Oye {s.get('nombre', 'Lina')}».  Si algo no va:  lina doctor")


def marcar_hecha(ruta=None):
    ruta = ruta or RUT.ESTADO / MARCA
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"hecha": time.time()}), encoding="utf-8")
    except OSError:
        pass


def ya_hecha(ruta=None):
    try:
        return "hecha" in json.loads((ruta or RUT.ESTADO / MARCA).read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return False


def principal(argv, charla=None, ruta_marca=None):
    if "-h" in argv or "--help" in argv:
        print("lina bienvenida   te acompaña para dejar Lina lista: clave de Gemini, micrófono, nombre, autonomía y privacidad. Se puede repetir.")
        return 0
    import sys
    c = charla or Charla(terminal=sys.stdin.isatty())
    if not c.terminal:
        c.salida("La bienvenida es una conversación: ábrela en una terminal con  lina bienvenida")
        return 2
    c.salida("¡Hola! Soy Lina. Vamos a dejarme lista (cinco cosas, un par de minutos). Intro en cualquier pregunta = lo que está entre corchetes.")
    try:
        for paso in (c.paso_clave, c.paso_microfono, c.paso_nombre, c.paso_autonomia, c.paso_privacidad):
            paso()
    except KeyboardInterrupt:
        c.salida("\nLo dejamos aquí. Cuando quieras seguir:  lina bienvenida")
        return 1
    marcar_hecha(ruta_marca)
    c.contar()
    return 0


# ---------------------------------------------------------------- aviso cuando falta la clave
def toca_avisar(ruta=None, ahora=None, cada=24 * 3600):
    """¿Toca avisar por voz de que falta la clave? Como mucho una vez al día, para no ser pesada."""
    ruta = ruta or RUT.ESTADO / "aviso_sin_clave"
    ahora = time.time() if ahora is None else ahora
    try:
        if ahora - float(ruta.read_text().strip()) < cada:
            return False
    except (OSError, ValueError):
        pass
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(str(ahora))
    except OSError:
        pass
    return True
