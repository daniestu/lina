# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina bienvenida`: la primera conversación con Lina, en la terminal y en español.

Deja lista la parte que solo puede hacer el usuario: la clave de Gemini (gratuita), comprobar que el micrófono funciona, cómo se llama el
asistente, cuánta libertad tiene y si puede enviar capturas de pantalla. Cada paso se puede saltar y se puede repetir cuando se quiera.
Nada se decide por el usuario: lo que da permisos (autonomía, capturas) se pregunta con su explicación.
"""
import json
import os
import re
import subprocess
import time

import requests

from lina.nucleo import ajustes as AJ
from lina.nucleo import claves as CL
from lina.nucleo import privacidad as PRIV
from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T

ENLACE_CLAVE = "https://aistudio.google.com/apikey"
MODELO_PRUEBA = "gemini-flash-lite-latest"
TEXTO_PEDIR_CLAVE = N_(
    "  Lina necesita una «clave de API» de Gemini. Es como una contraseña que le deja usar la inteligencia artificial de Google para entenderte\n"
    "  y responderte. Es gratuita (no pide tarjeta) y la creas tú ahora mismo:\n\n"
    "    1) Abre esta página:  {ENLACE_CLAVE}\n"
    "       (en la mayoría de terminales, Ctrl+clic sobre el enlace la abre)\n"
    "    2) Entra con tu cuenta de Google.\n"
    "    3) Pulsa el botón para crear la clave («Crear clave de API», en inglés «Create API key»).\n"
    "       Si te pide elegir un proyecto, vale cualquiera.\n"
    "    4) Te sale un texto largo de letras y números (suele empezar por «AIza» o «AQ.»). Cópialo y pégalo aquí abajo con Ctrl+Mayús+V.\n"
    "       Al pegarlo no se ve nada: es normal. Pulsa Intro.")
MARCA = "bienvenida.json"
AVISO_SIN_CLAVE = (N_("Todavía no tengo clave de Gemini, así que no puedo responderte. Es gratis: abre una terminal y escribe lina bienvenida, "
                   "o directamente lina clave gemini."))
PERFILES = {"1": ("autonomo", N_("Autónoma: hace sola casi todo y te pregunta solo por lo crítico (borrar de verdad, instalar de fuera, apagar…).")),
            "2": ("equilibrado", N_("Equilibrada: además te pregunta antes de cambiar nada tras haber leído contenido de internet.")),
            "3": ("prudente", N_("Prudente: te pide confirmación para casi todo lo que cambie algo en tu equipo."))}


# ---------------------------------------------------------------- comprobaciones (inyectables para probarlas sin red ni micrófono)
def motivo_de_google(respuesta):
    """El motivo que da Google en un error («API key not valid…»), en una línea y sin ninguna clave; "" si no lo trae."""
    try:
        mensaje = str(respuesta.json().get("error", {}).get("message", "")).strip().splitlines()[0]
    except Exception:                                       # sin cuerpo, o no es JSON
        return ""
    return CL.limpiar(mensaje)[:160]


def limpiar_pegado(texto):
    """Lo pegado en la terminal, sin restos: secuencias de escape del «pegado entre corchetes», comillas y espacios de alrededor."""
    t = re.sub(r"\x1b\[[0-9;?]*[~A-Za-z]", "", str(texto or ""))
    t = re.sub(r"[\x00-\x1f\x7f]", "", t)
    return t.strip().strip("\"'").strip()


def validar_clave(clave, enviar=requests.post):
    """(True|False|None, detalle). None: no se ha podido comprobar (sin red); la clave se guarda igualmente."""
    try:
        r = enviar(f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO_PRUEBA}:generateContent", headers={"x-goog-api-key": clave},
                   json={"contents": [{"role": "user", "parts": [{"text": "Responde solo: ok"}]}]}, timeout=15)
    except requests.RequestException:
        return None, T("no he podido conectar para comprobarla")
    if r.status_code == 200:
        return True, "funciona"
    if r.status_code in (400, 401, 403):
        motivo = motivo_de_google(r)
        if motivo:
            return False, T("Google dice que esa clave no es válida (código {codigo}: {motivo})", codigo=r.status_code, motivo=motivo)
        return False, T("Google dice que esa clave no es válida (código {codigo})", codigo=r.status_code)
    if r.status_code == 429:
        return True, T("es válida (ahora mismo has llegado al límite gratuito)")
    return None, T("Google ha contestado {v1}; la guardo y se comprobará al usarla", v1=r.status_code)


SATURADO = 0.98                      # el pico de la grabación llega al máximo: el micrófono «se satura» (suena alto, distorsionado y con ruido)
MIC_PREDETERMINADO = "@DEFAULT_SOURCE@"


def volumen_entrada(ejecutar):
    """El volumen (%) de la entrada de sonido predeterminada, o None si no se puede leer."""
    try:
        r = ejecutar(["pactl", "get-source-volume", MIC_PREDETERMINADO], capture_output=True, text=True, timeout=5)
        m = re.search(r"(\d+)%", r.stdout or "") if r.returncode == 0 else None
        return int(m.group(1)) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def poner_volumen_entrada(ejecutar, porcentaje):
    try:
        return ejecutar(["pactl", "set-source-volume", MIC_PREDETERMINADO, f"{int(porcentaje)}%"], capture_output=True, text=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


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
    def __init__(self, entrada=input, secreto=None, salida=lambda *a: print(*a, flush=True), terminal=True, ajustes=None, enviar=requests.post, grabar=None, ejecutar=None):
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
        r = self.pregunta(f"{texto} [{T('S/n') if defecto else T('s/N')}] ").lower()
        return defecto if not r else r in ("s", "si", "sí", "y", "yes")

    def titulo(self, n, texto):
        self.salida(f"\n{n}. {texto}")

    # 1
    def paso_clave(self):
        self.titulo(1, T("Clave de Gemini (la inteligencia de Lina)"))
        if CL.obtener("gemini"):
            self.salida(T("  ✔ Ya hay una clave de Gemini guardada."))
            if not self.si_no(T("  ¿La compruebo?"), False):
                self.resultado["clave"] = "ya estaba"
                return
            ok, detalle = validar_clave(CL.obtener("gemini"), self.enviar)
            self.salida(f"  {'✔' if ok else '!' if ok is None else '✘'} {detalle}")
            self.resultado["clave"] = "ya estaba"
            return
        self.salida(T(TEXTO_PEDIR_CLAVE, ENLACE_CLAVE=ENLACE_CLAVE))
        for intento in range(3):
            clave = self.secreto(T("  Clave de Gemini (el texto largo que has copiado; Intro para saltar este paso): "))
            clave = limpiar_pegado(clave)
            if not clave:
                self.salida(T("  Vale. Sin clave Lina no puede responder; cuando la tengas:  lina clave gemini"))
                self.resultado["clave"] = "saltado"
                return
            self.salida(T("  Recibida ({n} caracteres). Compruebo que funciona…", n=len(clave)))
            if len(clave) < 20 or re.search(r"\s", clave):
                self.salida(T("  ! Eso no parece una clave de Gemini (es un texto largo, sin espacios): ¿has copiado la clave entera? La compruebo igualmente."))
            ok, detalle = validar_clave(clave, self.enviar)
            if ok is False:
                self.salida(T("  ✘ {detalle}. Prueba otra vez (quedan {v1}).", detalle=detalle, v1=2 - intento))
                continue
            try:
                _, donde = CL.guardar("gemini", clave)
            except ValueError as e:
                self.salida(T("  ✘ No la he guardado: {e}.", e=e))
                continue
            self.salida(T("  ✔ Clave guardada en {donde} ({detalle}).", donde=donde, detalle=detalle))
            if self.ejecutar and CL.reiniciar_servicio(self.ejecutar):
                self.salida(T("  ✔ He reiniciado a Lina para que use la clave."))
            self.resultado["clave"] = "guardada"
            return
        self.salida(T("  No he conseguido guardar una clave que funcione. Cuando la tengas:  lina clave gemini"))
        self.resultado["clave"] = "fallida"

    # 2
    def paso_microfono(self):
        self.titulo(2, T("Micrófono"))
        if not self.si_no(T("  Voy a escucharte 2 segundos: di algo en voz normal. ¿Empezamos?")):
            self.resultado["microfono"] = "saltado"
            return
        nivel, error = medir_microfono(2.0, self.grabar)
        if error:
            self.salida(T("  ✘ No he podido usar el micrófono ({error}).\n    Mira que esté enchufado y no silenciado, y repite luego con:  lina bienvenida", error=error))
            self.resultado["microfono"] = "fallo"
        elif nivel < 0.01:
            self.salida(T("  ! No oigo nada ({v1}). Revisa que no esté silenciado ni sea otro dispositivo (ajustes de sonido).", v1=barra(nivel)))
            self.resultado["microfono"] = "silencio"
        elif nivel >= SATURADO:
            self._microfono_saturado(nivel)
        else:
            self.salida(T("  ✔ Te oigo: {barra}", barra=barra(nivel)))
            self.resultado["microfono"] = "bien"

    def _microfono_saturado(self, nivel):
        """El pico llega al máximo: la ganancia del micrófono es demasiado alta y se oye alto, distorsionado y con ruido (Whisper no entiende). Se baja sola."""
        self.salida(T("  ! Tu micrófono llega al máximo ({barra}): se satura, suena demasiado alto y con ruido, y así no te entiendo bien.", barra=barra(nivel)))
        inicial = volumen_entrada(self.ejecutar) if self.ejecutar else None
        if not inicial or inicial < 15:
            self.salida(T("  Bájale el volumen de entrada en los ajustes de sonido, o usa unos auriculares con micrófono; y repite luego con:  lina bienvenida"))
            self.resultado["microfono"] = "saturado"
            return
        for factor in (0.6, 0.4, 0.25):
            porcentaje = max(5, int(inicial * factor))
            if not poner_volumen_entrada(self.ejecutar, porcentaje):
                break
            self.salida(T("  Le bajo la ganancia al {porcentaje} %. Di otra frase en voz normal (2 segundos)…", porcentaje=porcentaje))
            nuevo, error = medir_microfono(2.0, self.grabar)
            if error or nuevo is None:
                break
            if SATURADO > nuevo >= 0.01:
                self.salida(T("  ✔ Ahora se oye bien: {barra}. He dejado la ganancia al {porcentaje} %.", barra=barra(nuevo), porcentaje=porcentaje))
                self.resultado["microfono"] = "ajustado"
                return
        poner_volumen_entrada(self.ejecutar, inicial)
        self.salida(T("  Sigue saturando aunque lo bajo: he dejado la ganancia como estaba. Prueba unos auriculares con micrófono o un micrófono USB, y repite con:  lina bienvenida"))
        self.resultado["microfono"] = "saturado"

    # 3
    def paso_nombre(self):
        self.titulo(3, T("Cómo se llama"))
        actual = self.aj.get("asistente", "nombre")
        nombre = self.pregunta(T("  Nombre del asistente, y palabra para activarlo («Oye {actual}») [Intro = {actual}]: ", actual=actual), actual)
        if nombre != actual:
            try:
                self.aj.establecer("asistente", "nombre", nombre)
            except ValueError as e:
                self.salida(f"  ✘ {e}")
                return
        self.salida(T("  ✔ Se llama {nombre}.", nombre=nombre))
        self.resultado["nombre"] = nombre

    # 4
    def paso_autonomia(self):
        self.titulo(4, T("Cuánta libertad tiene"))
        actual = self.aj.get("autonomia", "perfil")
        for k, (clave, texto) in PERFILES.items():
            self.salida(f"  {k}) " + T(texto) + (T("   ← ahora") if clave == actual else ""))
        self.salida(T("  Hagas lo que hagas, lo crítico (discos, arranque, cuentas, dinero) siempre lo confirmas tú con el atajo de teclado."))
        r = self.pregunta(T("  Elige 1, 2 o 3 [Intro = dejarlo como está]: "))
        if r in PERFILES:
            self.aj.establecer("autonomia", "perfil", PERFILES[r][0])
            self.salida(T("  ✔ Perfil {perfil}.", perfil=PERFILES[r][0]))
            self.resultado["perfil"] = PERFILES[r][0]
        else:
            self.resultado["perfil"] = actual

    # 5
    def paso_privacidad(self):
        self.titulo(5, T("Privacidad: capturas de pantalla"))
        PRIV.principal([], entrada=self.entrada, salida=self.salida, ajustes=self.aj, es_terminal=self.terminal)
        self.resultado["capturas"] = PRIV.estado(self.aj)

    def contar(self):
        s = self.resultado
        self.salida(T("\nListo. Resumen:"))
        self.salida(T("  Clave de Gemini: {v1} · Micrófono: {v2} · Perfil: {v3} · Capturas: {v4}", v1=s.get('clave', '-'), v2=s.get('microfono', '-'), v3=s.get('perfil', '-'), v4=s.get('capturas', '-')))
        if s.get("clave") in ("saltado", "fallida"):
            self.salida(T("  Falta la clave de Gemini: sin ella no puedo responder.  →  lina clave gemini"))
        atajo = atajo_pendiente()
        if atajo:
            self.salida(T("  Tu atajo {tecla} se activa cuando cierres sesión y vuelvas a entrar (KDE no lo carga antes). Hasta entonces, di «Oye {v1}».", tecla=atajo["tecla"], v1=s.get('nombre', 'Lina')))
            self.salida(T("  Si algo no va:  lina doctor"))
        else:
            self.salida(T("  Para hablarme: pulsa tu atajo o di «Oye {v1}».  Si algo no va:  lina doctor", v1=s.get('nombre', 'Lina')))


def atajo_pendiente():
    """El atajo recién creado en KDE, si todavía no se ha cerrado sesión desde entonces (KDE no lo carga antes); si no, None."""
    try:
        from lina.nucleo.instalador import Manifiesto
        a = Manifiesto().de("atajo")
    except Exception:
        return None
    sesion = os.environ.get("XDG_SESSION_ID", "")
    return a if a and a.get("escritorio") == "kde" and a.get("sesion") and a["sesion"] == sesion else None


def texto_atajo_pendiente(atajo, nombre="Lina"):
    return T("Tu atajo {tecla} todavía no funciona: KDE lo activa cuando cierres sesión y vuelvas a entrar. Hasta entonces, dime «Oye {nombre}».", tecla=atajo["tecla"], nombre=nombre)


def toca_avisar_atajo(atajo, ruta=None):
    """Por voz, una sola vez por sesión (la notificación sí sale siempre): True si toca hablar ahora."""
    ruta = ruta or RUT.ESTADO / "aviso_atajo"
    try:
        if ruta.read_text().strip() == atajo.get("sesion", ""):
            return False
    except OSError:
        pass
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(atajo.get("sesion", ""))
    except OSError:
        pass
    return True


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
        print(T("lina bienvenida   te acompaña para dejar Lina lista: clave de Gemini, micrófono, nombre, autonomía y privacidad. Se puede repetir."))
        return 0
    import sys
    c = charla or Charla(terminal=sys.stdin.isatty(), ejecutar=subprocess.run)
    if not c.terminal:
        c.salida(T("La bienvenida es una conversación: ábrela en una terminal con  lina bienvenida"))
        return 2
    c.salida(T("¡Hola! Soy Lina. Vamos a dejarme lista (cinco cosas, un par de minutos). Intro en cualquier pregunta = lo que está entre corchetes."))
    try:
        for paso in (c.paso_clave, c.paso_microfono, c.paso_nombre, c.paso_autonomia, c.paso_privacidad):
            paso()
    except KeyboardInterrupt:
        c.salida(T("\nLo dejamos aquí. Cuando quieras seguir:  lina bienvenida"))
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
