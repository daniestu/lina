"""Manos libres (E2): decir «Oye Lina, …» y que te atienda sin pulsar nada.

Cómo funciona (todo en tu ordenador):
  1. El micrófono se escucha SIEMPRE, pero el sonido NO se guarda ni se envía a ningún sitio. Un detector de voz muy simple (volumen) corta el
     audio en frases.
  2. Cada frase la pasa Whisper (local) a texto. Si empieza por la palabra de activación («oye lina», «escucha lina», «hey lina»…), lo que
     sigue es tu orden. Si no, se tira: no se guarda, no se envía.
  3. Solo la orden (ya en texto) llega al asistente, igual que si la hubieras dicho pulsando el atajo.

Seguridad: lo que pide confirmación (borrar, instalar, gastar…) NO se puede confirmar con la voz en manos libres: ahí hay que pulsar el atajo
(así una voz de la tele o de otra persona no puede autorizar nada). Cancelar sí se puede por voz.

Configuración: config.toml, secciones [asistente] y [activacion] (nombre, variantes, tiempos, sensibilidad); ver ajustes.py. Se relee sola al cambiarla; el nombre también se cambia por voz
(«a partir de ahora te llamas Jarvis»).

Pruebas sin micrófono:
    lina manos-libres probar "oye lina abre firefox"     → dice si se activaría y qué orden entendería
    lina manos-libres eco                                 → instala la cancelación de eco (no oye lo que suena por los altavoces)
    lina manos-libres nivel                               → mide el ruido de tu habitación y tu voz y recomienda la sensibilidad
"""
import collections
import difflib
import queue
import re
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

import numpy as np
from lina.nucleo import ajustes as AJ
from lina.nucleo import plataforma as PL
from lina.nucleo import rutas as RUT

FRECUENCIA = 16000
BLOQUE = 480                      # 30 ms por bloque de audio

PREDETERMINADOS = {
    "activo": "si",               # si / no
    "nombre": "lina",
    "alias": "",                  # otros nombres que también valen, separados por comas
    "prefijos": "oye, escucha, hey, ey, eh, hola, oiga, atiende, despierta, ok, vale, oie",
    "sin_prefijo": "si",          # si: vale decir solo «Lina, …» al principio de la frase
    "seguimiento": "8",           # segundos tras responderte (solo si lo pediste por manos libres, nunca con el atajo) en los que puedes seguir hablando sin decir el nombre (0 = nunca)
    "espera_orden": "6",          # segundos que espera tu orden tras decir solo «Oye Lina»
    "en_juegos": "no",            # si: también escucha mientras juegas
    "sensibilidad": "0.012",      # volumen mínimo para considerar que hablas (más alto = menos sensible)
    "eco": "auto",                # auto: si has instalado la cancelación de eco (lina manos-libres eco), usa ese micrófono; no: nunca
    "registro_ruido": "no",       # si: apunta en el registro lo que oye y descarta (por defecto NO se apunta nada de lo que no va para mí)
    "indicador": "si",            # si: resplandor en los bordes de la pantalla mientras te escucha, piensa o habla (indicador.py)
    "indicador_color": "azul",    # color al escucharte: azul, rojo, verde, morado, naranja, amarillo, rosa, cian, blanco o #rrggbb
    "indicador_grosor": "40",     # píxeles que entra el resplandor desde el borde
    "indicador_intensidad": "1.0", # lo fuerte que brilla: 0.1 casi invisible … 1 normal … 2 muy fuerte
    "indicador_instalar": "si",   # si: si faltan paquetes para dibujarlo (gtk3, gtk-layer-shell…), los instala solo con el gestor de paquetes (repositorios oficiales)
    "indicador_juegos": "no",     # si: también se dibuja con un juego en primer plano (por defecto no, para no molestar jugando)
    "parecido": "0.78",           # lo parecido que tiene que sonar el nombre (0-1). Más bajo = acepta más variantes (y más falsos avisos)
}

# palabras que Whisper se inventa con ruido o silencio
_RUIDOS = ("amara.org", "subtitulos", "suscribete", "gracias por ver")
_SUELTAS = {"gracias", "muchas gracias", "vale", "ok", "eh", "mm", "hm", "ah", "si", "no", "adios"}
_RELLENO = {"pues", "bueno", "venga", "a", "ver", "entonces", "y", "oye"}
_FUNCION = {"a", "de", "la", "el", "en", "y", "que", "los", "las", "un", "una", "con", "por", "para", "se", "lo", "me", "te", "mi", "tu", "su"}


# ----------------------------------------------------------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------------------------------------------------------
class Config:
    """Los ajustes del manos libres y del indicador, con los nombres de siempre (nombre, activo, indicador_color…).
    Sin ruta: se leen y se guardan en config.toml (ver ajustes.py). Con ruta: un archivo suelto «clave = valor» (para pruebas y uso antiguo)."""

    def __init__(self, ruta=None, ajustes=None):
        self.ruta = Path(ruta) if ruta else None
        self.ajustes = None if ruta else (ajustes or AJ.actuales(log=lambda m: None))
        self.valores = dict(PREDETERMINADOS)
        self.mtime = None
        self.cargar()

    def cargar(self):
        if self.ajustes is not None:
            self.ajustes.cargar()
            self.valores = dict(PREDETERMINADOS)
            self.valores.update({k: v for k, v in self.ajustes.planas().items() if k in PREDETERMINADOS})
            self.mtime = self.ajustes.marca
            return
        self.valores = dict(PREDETERMINADOS)
        try:
            self.mtime = self.ruta.stat().st_mtime_ns
            texto = self.ruta.read_text(encoding="utf-8")
        except OSError:
            self.mtime = None
            return
        for linea in texto.splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            valor = re.split(r"\s+#", valor, maxsplit=1)[0].strip()
            clave = clave.strip().lower()
            if clave in PREDETERMINADOS:
                self.valores[clave] = valor

    def recargar_si_cambio(self):
        try:
            m = self.ajustes._marca() if self.ajustes is not None else self.ruta.stat().st_mtime_ns
        except OSError:
            m = None
        if m != self.mtime:
            self.cargar()
            return True
        return False

    def guardar(self, clave, valor):
        """Cambia un ajuste conservando los comentarios del archivo (y lo crea si no existe)."""
        if self.ajustes is not None:
            seccion, k = AJ.PLANAS[clave]
            try:
                self.ajustes.establecer(seccion, k, valor)
            except ValueError:
                return
            self.valores[clave] = AJ.a_texto_plano(self.ajustes.get(seccion, k))
            self.mtime = self.ajustes.marca
            return
        self.valores[clave] = str(valor)
        try:
            lineas = self.ruta.read_text(encoding="utf-8").splitlines()
        except OSError:
            lineas = [f"{k} = {v}" for k, v in PREDETERMINADOS.items()]
        hecho = False
        for i, l in enumerate(lineas):
            if re.match(rf"\s*{re.escape(clave)}\s*=", l):
                comentario = re.search(r"\s+#.*$", l)
                lineas[i] = f"{clave} = {valor}" + (comentario.group(0) if comentario else "")
                hecho = True
                break
        if not hecho:
            lineas.append(f"{clave} = {valor}")
        self.ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        try:
            self.mtime = self.ruta.stat().st_mtime_ns
        except OSError:
            pass

    def si(self, clave):
        return self.valores.get(clave, "").strip().lower() in ("si", "sí", "yes", "true", "1", "on")

    def numero(self, clave):
        try:
            return float(str(self.valores.get(clave, PREDETERMINADOS[clave])).replace(",", "."))
        except ValueError:
            return float(PREDETERMINADOS[clave])

    def lista(self, clave):
        return [x.strip() for x in str(self.valores.get(clave, "")).split(",") if x.strip()]

    @property
    def nombres(self):
        return [self.valores["nombre"].strip()] + self.lista("alias")

    @property
    def nombre(self):
        return self.valores["nombre"].strip()


# ----------------------------------------------------------------------------------------------------------------------
# Entender la palabra de activación
# ----------------------------------------------------------------------------------------------------------------------
def normalizar(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn" or c == "̃")   # sin tildes (la ñ se conserva hasta la fonética)
    return unicodedata.normalize("NFC", s)


def fonetica(s):
    """Como suena: sin tildes ni mayúsculas, y juntando letras que en español suenan igual (b/v, c/z/s, ll/y, h muda…)."""
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn" or c == "̃")
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[^a-zñ0-9]", "", s)
    s = s.replace("ñ", "ni").replace("qu", "k").replace("ll", "y").replace("ch", "x")
    s = re.sub(r"c(?=[ei])", "s", s)
    s = s.replace("c", "k").replace("z", "s").replace("v", "b").replace("w", "u").replace("h", "")
    s = re.sub(r"g(?=[ei])", "j", s)
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


def _parecido(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _tokens(texto):
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[0-9a-záéíóúüñÁÉÍÓÚÜÑ]+", texto, re.I)]


def _umbral_nombre(fon_nombre, umbral):
    return max(umbral, 0.88) if len(fon_nombre) <= 4 else umbral


def _coincide_nombre(toks, i, nombre, umbral):
    """¿A partir del token i suena el nombre? Devuelve cuántos tokens ocupa (0 si no). Admite el nombre partido: «at las»."""
    fn = fonetica(nombre)
    if not fn:
        return 0
    palabras = len(nombre.split())
    limite = _umbral_nombre(fn, umbral)
    for n in sorted({palabras, palabras + 1, max(1, palabras - 1)}, key=lambda k: (k != palabras, k)):
        grupo = toks[i:i + n]
        if len(grupo) < n:
            continue
        if n > 1 and palabras == 1 and normalizar(grupo[0][0]) in _FUNCION:
            continue                                   # «a las» no es «lina»
        junto = fonetica("".join(t[0] for t in grupo))
        if _parecido(junto, fn) >= limite:
            return n
    return 0


def _es_prefijo(token, prefijos):
    f = fonetica(token)
    if not f:
        return False
    return any(_parecido(f, fonetica(p)) >= 0.74 for p in prefijos)


def buscar_activacion(texto, cfg):
    """(¿te han llamado?, lo que viene después). Solo vale al PRINCIPIO de la frase: «oye lina, …», «escucha lina …», «lina, …».
    Si en medio de una frase aparece «lina» (hablando de otra cosa) no se activa."""
    toks = _tokens(texto)
    if not toks:
        return False, ""
    umbral = cfg.numero("parecido")
    prefijos = cfg.lista("prefijos")
    for i in range(min(len(toks), 4)):
        previos = toks[:i]
        if previos and not all(_es_prefijo(t[0], prefijos) or normalizar(t[0]) in _RELLENO for t in previos):
            break                                       # delante hay otras palabras: no te hablaba a ti
        for nombre in cfg.nombres:
            n = _coincide_nombre(toks, i, nombre, umbral)
            pegado = False
            if not n:                                   # «oylina» pegado en una sola palabra
                f, fnom = fonetica(toks[i][0]), fonetica(nombre)
                for p in prefijos:
                    fp = fonetica(p)
                    if len(f) > len(fp) + 2 and f.startswith(fp) and _parecido(f[len(fp):], fnom) >= max(umbral, 0.85):
                        n, pegado = 1, True
                        break
            if not n:
                continue
            tiene_prefijo = pegado or any(_es_prefijo(t[0], prefijos) for t in previos)
            if tiene_prefijo or cfg.si("sin_prefijo"):
                return True, limpiar_orden(texto[toks[i + n - 1][2]:])
    return False, ""


def limpiar_orden(resto):
    resto = resto.strip(" \t\n,.;:¡!¿?-–—…\"'«»")
    if normalizar(resto) in _SUELTAS or any(r in normalizar(resto) for r in _RUIDOS):
        return ""
    return resto


def es_ruido(texto):
    n = normalizar(texto)
    if re.sub(r"[^a-z ]", "", n).strip() in ("musica", "aplausos", "risas"):
        return True                                       # lo que Whisper escribe cuando oye solo ruido: «[Música]»
    return any(r in n for r in _RUIDOS)


# ----------------------------------------------------------------------------------------------------------------------
# Órdenes por voz sobre el propio manos libres (las entiende el código, sin gastar una llamada a la IA)
# ----------------------------------------------------------------------------------------------------------------------
_TEMA = re.compile(r"\b(manos libres|escucha continua|activacion por voz|palabra de activacion|modo escucha)\b")
_NO_NOMBRE = {"ahora", "de", "la", "el", "un", "una", "que", "asi", "otra", "otro", "nuevo", "mismo", "tu", "tus", "mi", "mis", "por",
              "siempre", "como", "cuando", "cual", "quien", "te", "me", "se", "lo", "a"}


def entender_orden(texto):
    """Devuelve None o una tupla: ('activar',) ('desactivar',) ('juegos', True/False) ('nombre', X) ('pregunta_nombre',) ('estado',)."""
    n = normalizar(texto)
    n = re.sub(r"[^a-z0-9ñ ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if re.search(r"\b(como te llamas|como te tengo que llamar|como te llamo|cual es tu nombre|cual es tu palabra de activacion|"
                 r"como te activo|como te despierto)\b", n):
        return ("pregunta_nombre",)
    m = re.search(r"\b(?:te llamas|te llames|llamate|a partir de ahora te llamas|cambia(?:r)? (?:tu|el) nombre (?:a|por)|"
                  r"tu nombre (?:es|sera|va a ser)|quiero que te llames|(?:tu )?palabra de activacion (?:es|sera))\s+(?:ahora\s+)?(?:se\s+)?(?:es\s+)?([a-z0-9ñ]+(?: [a-z0-9ñ]+)?)", n)
    if m:
        palabras = [p for p in m.group(1).split() if p]
        while palabras and palabras[0] in _NO_NOMBRE:
            palabras.pop(0)
        if palabras:
            nombre = palabras[0]
            if len(nombre) >= 3:
                return ("nombre", nombre)
        return ("nombre", "")
    if re.search(r"\b(eco|cancelacion de eco|cancelador de eco)\b", n):
        if re.search(r"\b(desactiva|desactivar|apaga|apagar|quita|quitar|deshabilita|sin)\b", n):
            return ("eco", False)
        if re.search(r"\b(activa|activar|enciende|encender|pon|poner|habilita|instala|instalar)\b", n):
            return ("eco", True)
    if _TEMA.search(n):
        if re.search(r"\b(juego|juegos|jugando|jugar)\b", n):
            if re.search(r"\b(desactiva|apaga|quita|deshabilita|no )", n):
                return ("juegos", False)
            if re.search(r"\b(activa|enciende|pon|habilita|deja|quiero)", n):
                return ("juegos", True)
        if re.search(r"\b(desactiva|desactivar|apaga|apagar|quita|quitar|deshabilita|para|parar|cancela|no quiero|sin)\b", n):
            return ("desactivar",)
        if re.search(r"\b(activa|activar|enciende|encender|pon|poner|habilita|vuelve|quiero)\b", n):
            return ("activar",)
        if re.search(r"\b(esta|estas|funciona|activado|activo|estado)\b", n):
            return ("estado",)
    return None


# ----------------------------------------------------------------------------------------------------------------------
# Que no se escuche a sí mismo: cancelación de eco de PipeWire (resta lo que suena por los altavoces al micrófono)
# ----------------------------------------------------------------------------------------------------------------------
FUENTE_ECO = "lina_eco_source"
FICHERO_ECO = Path.home() / ".config/pipewire/pipewire.conf.d/60-lina-eco.conf"
CONF_ECO = """# Creado por el asistente (lina manos-libres eco). Para quitarlo: lina manos-libres eco quitar
context.modules = [
  { name = libpipewire-module-echo-cancel
    args = {
      library.name = aec/libspa-aec-webrtc
      monitor.mode = true
      capture.props = { node.name = "lina_eco_capture" }
      source.props = { node.name = "%s" node.description = "Microfono sin eco (asistente)" }
      playback.props = { node.name = "lina_eco_playback" }
    }
  }
]
""" % FUENTE_ECO


def pactl(*args, tiempo=4):
    try:
        r = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=tiempo)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def fuente_eco_existe(ejecutar=pactl):
    return FUENTE_ECO in ejecutar("list", "short", "sources")


def eco_en_uso(ejecutar=pactl):
    return ejecutar("get-default-source").strip() == FUENTE_ECO


def pc_suena(ejecutar=pactl):
    """¿Hay algo sonando ahora mismo en el ordenador (música, vídeo, partido…)? Mira las apps con sonido activo y sin pausar."""
    texto = ejecutar("list", "sink-inputs")
    for bloque in re.split(r"\n(?=Sink Input #)", texto):
        if "Sink Input #" in bloque and re.search(r"Corked:\s*no", bloque) and not re.search(r"Mute:\s*yes", bloque) \
                and FUENTE_ECO not in bloque and "lina_eco" not in bloque:
            return True
    return False


def usar_fuente_eco(log=print, ejecutar=pactl):
    """Si existe el micrófono sin eco y no es ya el predeterminado, lo pone (lo usan el manos libres y el atajo)."""
    if fuente_eco_existe(ejecutar) and not eco_en_uso(ejecutar):
        ejecutar("set-default-source", FUENTE_ECO)
        log("Manos libres: uso el micrófono con cancelación de eco (no oigo lo que suena por los altavoces)")
    return eco_en_uso(ejecutar)


def _reiniciar_audio():
    subprocess.run(["systemctl", "--user", "restart", "pipewire", "pipewire-pulse", "wireplumber"], timeout=30)


MARCA_FALLO = RUT.DATOS / "eco_fallo"      # si instalar el eco falló una vez, no se reintenta solo cada arranque


def configurar_eco(accion="instalar", log=print):
    """Instala o quita la cancelación de eco. Devuelve True si todo quedó como se pedía."""
    if accion == "quitar":
        FICHERO_ECO.unlink(missing_ok=True)
        _reiniciar_audio()
        log("Cancelación de eco quitada: el audio vuelve a ser el de siempre.")
        return True
    if accion == "estado":
        log(f"Micrófono sin eco: {'creado' if fuente_eco_existe() else 'NO existe'} · en uso: {'sí' if eco_en_uso() else 'no'} · sonando ahora en el PC: {'sí' if pc_suena() else 'no'}")
        return True
    FICHERO_ECO.parent.mkdir(parents=True, exist_ok=True)
    FICHERO_ECO.write_text(CONF_ECO)
    log("Cancelación de eco: la preparo (el audio se corta 2-3 segundos)…")
    _reiniciar_audio()
    for _ in range(20):
        time.sleep(1)
        if fuente_eco_existe():
            break
    else:
        FICHERO_ECO.unlink(missing_ok=True)
        _reiniciar_audio()
        log("Cancelación de eco: no se ha podido crear (seguramente falta el módulo webrtc de PipeWire). Dejo el audio como estaba. "
            f"Diagnóstico:  {PL.FAMILIAS.get(PL.familia_actual(), PL._GENERICO)['texto_consultar']} | grep -i webrtc ; find /usr/lib* -path '*spa-0.2/aec*'")
        return False
    MARCA_FALLO.unlink(missing_ok=True)
    usar_fuente_eco(log)
    log("Cancelación de eco: activada. El micrófono resta lo que suena por los altavoces.")
    return True


# ----------------------------------------------------------------------------------------------------------------------
# Cortar el audio en frases
# ----------------------------------------------------------------------------------------------------------------------
class Segmentador:
    """Detector de voz por volumen: junta los bloques de una frase y la entrega cuando hay un silencio."""

    def __init__(self, umbral_min=0.012, silencio_fin=0.8, max_seg=15.0, preroll=0.3, min_voz=0.25):
        self.umbral_min = umbral_min
        self.bloques_silencio = max(1, int(silencio_fin * FRECUENCIA / BLOQUE))
        self.max_bloques = int(max_seg * FRECUENCIA / BLOQUE)
        self.pre = collections.deque(maxlen=max(1, int(preroll * FRECUENCIA / BLOQUE)))
        self.min_voz = max(1, int(min_voz * FRECUENCIA / BLOQUE))
        self.suelo = 0.003
        self.reiniciar()

    def reiniciar(self):
        self.pre.clear()
        self.seg = []
        self.en_voz = False
        self.fuertes = 0
        self.silencio = 0
        self.voz = 0

    @property
    def umbral(self):
        return max(self.umbral_min, self.suelo * 3.0)

    def alimentar(self, bloque):
        """Entrega un bloque. Devuelve la frase completa (array float32) cuando termina, o None."""
        b = np.asarray(bloque, dtype=np.float32).reshape(-1)
        rms = float(np.sqrt(np.mean(b * b))) if len(b) else 0.0
        fuerte = rms >= self.umbral
        if not self.en_voz:
            if not fuerte:
                self.suelo = 0.98 * self.suelo + 0.02 * rms
                self.fuertes = 0
                self.pre.append(b)
                return None
            self.fuertes += 1
            self.pre.append(b)
            if self.fuertes >= 3:
                self.en_voz = True
                self.seg = list(self.pre)
                self.pre.clear()
                self.voz = self.fuertes
                self.silencio = 0
            return None
        self.seg.append(b)
        if rms >= self.umbral * 0.7:
            self.silencio = 0
            self.voz += 1
        else:
            self.silencio += 1
        if self.silencio >= self.bloques_silencio or len(self.seg) >= self.max_bloques:
            audio = np.concatenate(self.seg)
            voz = self.voz
            self.reiniciar()
            return audio if voz >= self.min_voz else None
        return None


# ----------------------------------------------------------------------------------------------------------------------
# El oyente
# ----------------------------------------------------------------------------------------------------------------------
class ManosLibres:
    """Hilo que escucha el micrófono y llama a asistente.atender_manos_libres(texto) cuando te dirijas a él.

    El asistente debe tener: estado, interrumpiendo, modo_privado, atender_manos_libres(texto), en_juego().
    transcribir(audio) → texto. Todo lo demás (pitido, log, reloj) es inyectable para poder probarlo sin micrófono."""

    def __init__(self, asistente, transcribir, log=print, pitido=lambda f: None, reloj=time.time, cfg=None, abrir_micro=None, pactl=pactl):
        self.a = asistente
        self.transcribir = transcribir
        self.log = log
        self.pitido = pitido
        self.reloj = reloj
        self.cfg = cfg or Config()
        self.abrir_micro = abrir_micro
        self.pactl = pactl
        self.eco_activo = False
        self.seg = Segmentador(self.cfg.numero("sensibilidad"))
        self.cola = queue.Queue(maxsize=600)
        self.modo = None                  # None | "orden" (ha dicho el nombre y falta la orden)
        self.limite_orden = 0.0
        self.seguimiento_hasta = 0.0
        self.silencio_hasta = 0.0
        self.estado_previo = "esperando"
        self.juego = False
        self.t_juego = 0.0
        self.t_config = 0.0
        self.parado = threading.Event()
        self.reabrir = threading.Event()        # hay que reabrir el micrófono (cambió el audio del sistema)
        self.ultimo_motivo_pausa = None

    # --- hilo ---
    def iniciar(self):
        threading.Thread(target=self._vivir, daemon=True, name="manos-libres").start()

    def _vivir(self):
        while not self.parado.is_set():
            try:
                self._escuchar()
            except Exception as e:
                self.log(f"Manos libres: el micrófono ha fallado ({e!r}); reintento en 30 s")
            if self.reabrir.is_set():
                self.reabrir.clear()
                time.sleep(2)
                continue
            self.parado.wait(30)

    def _escuchar(self):
        import sounddevice as sd
        self._preparar_eco()
        self.log(f"Manos libres: listo. Di «Oye {self.cfg.nombre.capitalize()}» para hablarme sin pulsar nada"
                 + ("" if self.cfg.si("activo") else " (ahora está DESACTIVADO: lina config poner activacion.activo si)"))
        flujo = sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32", blocksize=BLOQUE,
                               callback=lambda datos, *_: self._meter(datos))
        with flujo:
            while not self.parado.is_set() and not self.reabrir.is_set():
                try:
                    bloque = self.cola.get(timeout=0.5)
                except queue.Empty:
                    self.tic()
                    continue
                self.procesar_bloque(bloque)

    def _preparar_eco(self):
        """Por defecto el eco se cancela solo: la primera vez lo instala (con permiso de eco = auto), después solo lo usa."""
        self.eco_activo = False
        if self.cfg.valores.get("eco", "auto").lower() == "no":
            return
        if not fuente_eco_existe(self.pactl):
            if FICHERO_ECO.exists():                       # ya instalado: PipeWire puede estar aún arrancando
                for _ in range(15):
                    if fuente_eco_existe(self.pactl):
                        break
                    time.sleep(1)
            elif not MARCA_FALLO.exists():
                if not configurar_eco("instalar", self.log):
                    try:
                        MARCA_FALLO.parent.mkdir(parents=True, exist_ok=True)
                        MARCA_FALLO.touch()
                    except OSError:
                        pass
        self.eco_activo = usar_fuente_eco(self.log, self.pactl)
        if not self.eco_activo:
            self.log("Manos libres: sin cancelación de eco. Con sonido en el PC oirá también lo que suene")

    def cambiar_eco(self, activar):
        """Orden por voz «activa/desactiva el eco»: lo hace en segundo plano cuando termine de hablar y reabre el micrófono."""
        self.cfg.guardar("eco", "auto" if activar else "no")

        def trabajo():
            for _ in range(60):                            # espera a que acabe de decir la confirmación (cortaría su voz)
                if self.a.estado == "esperando":
                    break
                time.sleep(0.5)
            if activar:
                MARCA_FALLO.unlink(missing_ok=True)
                configurar_eco("instalar", self.log)
            else:
                configurar_eco("quitar", self.log)
            self.reabrir.set()
        threading.Thread(target=trabajo, daemon=True).start()

    def _meter(self, datos):
        try:
            self.cola.put_nowait(datos[:, 0].copy())
        except queue.Full:
            pass                                            # si Whisper va retrasado se descarta lo más viejo en vez de acumular

    def parar(self):
        self.parado.set()

    # --- estado ---
    def pausa(self):
        """Por qué NO hay que escuchar ahora (o None)."""
        a = self.a
        if not self.cfg.si("activo"):
            return "desactivado"
        if getattr(a, "modo_privado", False):
            return "modo privado"
        if a.estado in ("grabando", "hablando") or getattr(a, "interrumpiendo", False):
            return "ocupado"
        if self.reloj() < self.silencio_hasta:
            return "eco"
        if not self.cfg.si("en_juegos") and self.juego:
            return "juego"
        return None

    def tic(self):
        """Cosas periódicas: releer la configuración, mirar si hay un juego en primer plano, caducar esperas."""
        ahora = self.reloj()
        if ahora - self.t_config > 3:
            self.t_config = ahora
            if self.cfg.recargar_si_cambio():
                self.seg.umbral_min = self.cfg.numero("sensibilidad")
                self.log(f"Manos libres: configuración recargada (nombre «{self.cfg.nombre}», "
                         f"{'activo' if self.cfg.si('activo') else 'desactivado'})")
        if ahora - self.t_juego > 4 and not self.cfg.si("en_juegos") and self.cfg.si("activo"):
            self.t_juego = ahora
            try:
                nuevo = bool(self.a.en_juego())
            except Exception:
                nuevo = False
            if nuevo != self.juego:
                self.log("Manos libres: " + ("hay un juego en primer plano: dejo de escuchar (usa el atajo)" if nuevo else "ya no hay juego: vuelvo a escuchar"))
            self.juego = nuevo
        if self.modo == "orden" and ahora > self.limite_orden and not self.seg.en_voz:
            self.modo = None
            self.log("Manos libres: no he oído la orden; vuelvo a esperar")
            self.pitido(400)
            self.silencio_hasta = self.reloj() + 0.35

    def _nueva_peticion(self):
        self.log("")
        self.log("=" * 22 + " NUEVA PETICIÓN " + "=" * 22)

    def _seguir_estado(self):
        """Abre la ventana de seguimiento cuando acaba de contestarte."""
        est = self.a.estado
        ahora = self.reloj()
        if self.estado_previo in ("hablando", "pensando") and est == "esperando":
            self.silencio_hasta = ahora + 0.6                # la cola del eco del altavoz
            s = self.cfg.numero("seguimiento")
            # solo si la petición que acaba de contestarse vino del propio manos libres: con el atajo no hay ventana de seguimiento
            if s > 0 and getattr(self.a, "origen_voz_libre", True):
                self.seguimiento_hasta = ahora + 0.6 + s
        if est != "esperando" and not getattr(self.a, "origen_voz_libre", True):
            self.seguimiento_hasta = 0.0                     # se está atendiendo algo pedido con el atajo: cualquier ventana anterior se cierra
        self.estado_previo = est

    def procesar_bloque(self, bloque):
        """Un bloque de audio (30 ms). Si completa una frase, la trata. Devuelve el texto tratado (solo para pruebas)."""
        self.tic()
        self._seguir_estado()
        motivo = self.pausa()
        if motivo:
            self.seg.reiniciar()
            if motivo != self.ultimo_motivo_pausa and motivo in ("juego", "modo privado"):
                self.log(f"Manos libres en pausa ({motivo})")
            self.ultimo_motivo_pausa = motivo
            return None
        self.ultimo_motivo_pausa = None
        frase = self.seg.alimentar(bloque)
        if frase is None:
            return None
        return self.tratar_frase(frase)

    # --- lo que se hace con cada frase ---
    def tratar_frase(self, audio):
        ahora = self.reloj()
        try:
            texto = (self.transcribir(audio) or "").strip()
        except Exception as e:
            self.log(f"Manos libres: error al transcribir ({e!r})")
            return None
        if not texto or es_ruido(texto):
            return None
        ahora = self.reloj()
        activada, orden = buscar_activacion(texto, self.cfg)
        if activada:
            self.modo = None
            self.seguimiento_hasta = 0.0
            self._nueva_peticion()
            if orden:
                self.log(f"Manos libres: me has llamado y has dicho «{orden}» (oído: «{texto}»)")
                self.pitido(1000)
                self.silencio_hasta = self.reloj() + 0.35
                self.a.atender_manos_libres(orden)
            else:
                self.log(f"Manos libres: me has llamado (oído: «{texto}»); espero tu orden")
                self.pitido(1000)
                self.modo = "orden"
                self.limite_orden = self.reloj() + 0.35 + self.cfg.numero("espera_orden")
                self.silencio_hasta = self.reloj() + 0.35
            return texto
        if self.modo == "orden":
            self.modo = None
            orden = limpiar_orden(texto)
            if orden:
                self.log(f"Manos libres: orden «{orden}»")
                self.a.atender_manos_libres(orden)
            return texto
        if ahora <= self.seguimiento_hasta and self.a.estado == "esperando" and (self.eco_activo or not pc_suena(self.pactl)):
            self.seguimiento_hasta = 0.0                      # una sola frase de seguimiento por respuesta
            orden = limpiar_orden(texto)
            if len(orden.split()) >= 2:
                self._nueva_peticion()
                self.log(f"Manos libres: seguimiento sin nombre «{orden}»")
                self.a.atender_manos_libres(orden)
            return texto
        if self.cfg.si("registro_ruido"):
            self.log(f"Manos libres: oído pero no va para mí (se tira): «{texto[:40]}{'…' if len(texto) > 40 else ''}»")
        return None


# ----------------------------------------------------------------------------------------------------------------------
# Utilidades de línea de comandos
# ----------------------------------------------------------------------------------------------------------------------
def _probar(frases):
    cfg = Config()
    print(f"Nombre: «{cfg.nombre}» · variantes: {cfg.lista('alias') or '—'} · prefijos: {', '.join(cfg.lista('prefijos'))}")
    for f in frases:
        ok, resto = buscar_activacion(f, cfg)
        print(("✔ ACTIVA " if ok else "✘ no activa") + f"  «{f}»" + (f"  → orden: «{resto}»" if ok and resto else ("  → esperaría tu orden" if ok else "")))


def _nivel():
    import sounddevice as sd
    print("Quédate en silencio 3 segundos…")
    ruido = sd.rec(int(3 * FRECUENCIA), samplerate=FRECUENCIA, channels=1, dtype="float32")
    sd.wait()
    print("Ahora di en voz normal: «Oye Lina, ¿qué tiempo hace hoy?» (4 segundos)")
    voz = sd.rec(int(4 * FRECUENCIA), samplerate=FRECUENCIA, channels=1, dtype="float32")
    sd.wait()

    def niveles(x):
        x = x[:, 0]
        n = len(x) // BLOQUE
        return np.array([float(np.sqrt(np.mean(x[i * BLOQUE:(i + 1) * BLOQUE] ** 2))) for i in range(n)])
    r, v = niveles(ruido), niveles(voz)
    suelo, habla = float(np.percentile(r, 95)), float(np.percentile(v, 90))
    print(f"Ruido de fondo (casi el máximo): {suelo:.4f} · tu voz: {habla:.4f}")
    if habla < suelo * 2.5:
        print("Tu voz apenas se distingue del ruido: acércate al micrófono o súbele la ganancia en los ajustes de sonido.")
        return
    recomendado = max(0.006, round(min(habla * 0.25, max(suelo * 3, 0.008)), 4))
    print(f"Sensibilidad recomendada: {recomendado}")
    print(f"Ponlo con:  lina config poner activacion.sensibilidad {recomendado}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "probar":
        _probar(sys.argv[2:])
    elif len(sys.argv) >= 2 and sys.argv[1] == "eco":
        sys.exit(configurar_eco(sys.argv[2] if len(sys.argv) > 2 else "instalar"))
    elif len(sys.argv) >= 2 and sys.argv[1] == "nivel":
        _nivel()
    else:
        print(__doc__)
