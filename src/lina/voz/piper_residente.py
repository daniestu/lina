# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Piper residente (fase 12): en vez de arrancar Piper y cargar la voz en cada frase (de uno a dos segundos), un proceso aparte la mantiene cargada y va
sintetizando lo que se le pide. Si algo falla (Piper de otra versión, el proceso muere, tarda demasiado, el audio sale vacío) se avisa y Lina sigue con
el método de siempre, un Piper por frase: el residente solo puede ahorrar tiempo, nunca dejarla muda.

El proceso es independiente (si se cae, no arrastra a Lina), se cierra solo tras un rato sin usarse para liberar memoria, y se cierra también si Lina termina
(al cerrarse su entrada, sale). Habla con Lina por líneas JSON en su entrada y salida estándar."""
import atexit
import json
import queue
import subprocess
import sys
import threading
import wave
from pathlib import Path

INACTIVIDAD_SEG = 600          # sin frases durante tanto tiempo, el proceso se cierra y suelta la memoria de la voz
ESPERA_CARGA_SEG = 90          # lo que puede tardar en cargar la voz la primera vez
ESPERA_FRASE_SEG = 45          # lo que puede tardar en sintetizar una frase
FALLOS_PARA_RENDIRSE = 2       # fallos seguidos antes de dejarlo por esta sesión
MIN_SEGUNDOS_AUDIO = 0.1       # un audio más corto que esto se toma por vacío


# ======================= el proceso que mantiene la voz cargada =======================
def _ruta_modelo(modelo, carpeta):
    p = Path(str(modelo))
    return p if p.is_file() else Path(str(carpeta)) / f"{modelo}.onnx"


def sintetizar_con(piper, voces, pedido):
    """Sintetiza `pedido` a un archivo wav con el módulo piper dado. Vale para piper-tts 1.2 (synthesize) y 1.3 o posterior (synthesize_wav).
    `voces` guarda las voces ya cargadas (como mucho dos, para no acumular memoria)."""
    ruta = str(_ruta_modelo(pedido["modelo"], pedido.get("carpeta", "")))
    voz = voces.get(ruta)
    if voz is None:
        if len(voces) >= 2:
            voces.pop(next(iter(voces)))
        voz = voces[ruta] = piper.PiperVoice.load(ruta)
    locutor, escala, texto = pedido.get("locutor"), pedido.get("escala"), pedido.get("texto", "")
    if not pedido.get("texto"):                                   # «cargar»: solo se quería tenerla lista
        return
    with wave.open(str(pedido["salida"]), "wb") as wav:
        if hasattr(voz, "synthesize_wav"):                          # piper-tts 1.3 o posterior
            config = None
            if hasattr(piper, "SynthesisConfig"):
                config = piper.SynthesisConfig(speaker_id=locutor, length_scale=escala)
            voz.synthesize_wav(texto, wav, syn_config=config)
        else:                                                       # piper-tts 1.2
            voz.synthesize(texto, wav, speaker_id=locutor, length_scale=escala)


def trabajador(entrada=None, salida=None, piper=None):
    """Bucle del proceso residente: una línea JSON entra, una línea JSON sale ({"ok": true} o {"ok": false, "error": …})."""
    entrada = entrada or sys.stdin
    salida = salida or sys.stdout
    sys.stdout = sys.stderr                                          # lo que escriba Piper no se mezcla con el protocolo
    if piper is None:
        import piper as piper_real
        piper = piper_real
    voces = {}
    for linea in entrada:
        try:
            pedido = json.loads(linea)
            if pedido.get("op") == "salir":
                break
            sintetizar_con(piper, voces, pedido)
            respuesta = {"ok": True}
        except Exception as e:                                       # cualquier fallo se cuenta, no mata el proceso
            respuesta = {"ok": False, "error": repr(e)[:200]}
        salida.write(json.dumps(respuesta) + "\n")
        salida.flush()


# ======================= el lado de Lina =======================
def audio_valido(ruta):
    """¿Es un wav legible con algo de audio dentro?"""
    try:
        with wave.open(str(ruta), "rb") as w:
            return w.getframerate() > 0 and w.getnframes() / w.getframerate() >= MIN_SEGUNDOS_AUDIO
    except (OSError, EOFError, wave.Error):
        return False


class PiperResidente:
    def __init__(self, orden=None, inactividad=INACTIVIDAD_SEG, espera_carga=ESPERA_CARGA_SEG, espera_frase=ESPERA_FRASE_SEG, log=print):
        self.orden = orden or [sys.executable, "-m", "lina.voz.piper_residente", "--trabajador"]
        self.inactividad, self.espera_carga, self.espera_frase, self.log = inactividad, espera_carga, espera_frase, log
        self.proceso = None
        self.respuestas = queue.Queue()
        self.cerrojo = threading.RLock()
        self.temporizador = None
        self.fallos = 0
        self.rendido = False
        self.cargadas = set()
        atexit.register(self.cerrar)

    # ----- proceso
    def _arrancar(self):
        if self.proceso is not None and self.proceso.poll() is None:
            return True
        self.proceso = None
        self.cargadas = set()
        self.respuestas = queue.Queue()
        try:
            proceso = subprocess.Popen(self.orden, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        except OSError as e:
            self.log(f"Piper residente: no he podido arrancarlo ({e!r})")
            return False
        cola = self.respuestas

        def leer():
            for linea in proceso.stdout:
                cola.put(linea)
            cola.put(None)                                           # el proceso terminó
        threading.Thread(target=leer, daemon=True).start()
        self.proceso = proceso
        return True

    def _esperar(self, segundos):
        try:
            linea = self.respuestas.get(timeout=segundos)
        except queue.Empty:
            return None
        if linea is None:
            return None
        try:
            return json.loads(linea)
        except ValueError:
            return None

    def _pedir(self, pedido, segundos):
        try:
            self.proceso.stdin.write(json.dumps(pedido) + "\n")
            self.proceso.stdin.flush()
        except (OSError, ValueError):
            return None
        return self._esperar(segundos)

    def _fallar(self, motivo):
        self.fallos += 1
        self.log(f"Piper residente: {motivo}; esta frase sale con el método de siempre")
        self.cerrar()
        if self.fallos >= FALLOS_PARA_RENDIRSE:
            self.rendido = True
            self.log("Piper residente: falla seguido; lo dejo por esta sesión (se puede apagar del todo con:  lina config poner voz.residente no)")
        return False

    def _vigilar_inactividad(self):
        if self.temporizador:
            self.temporizador.cancel()
        self.temporizador = threading.Timer(self.inactividad, self._cerrar_por_inactividad)
        self.temporizador.daemon = True
        self.temporizador.start()

    def _cerrar_por_inactividad(self):
        with self.cerrojo:
            self.log("Piper residente: sin hablar un rato, libero la memoria de la voz")
            self.cerrar()

    def cerrar(self):
        with self.cerrojo:
            if self.temporizador:
                self.temporizador.cancel()
                self.temporizador = None
            proceso, self.proceso = self.proceso, None
            self.cargadas = set()
        if proceso is None:
            return
        try:
            proceso.stdin.write(json.dumps({"op": "salir"}) + "\n")
            proceso.stdin.flush()
            proceso.wait(timeout=2)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            proceso.kill()

    # ----- uso
    def precalentar(self, modelo, carpeta):
        """Arranca el proceso y carga la voz sin sintetizar nada, para que la primera frase ya suene sin esperas. Se puede llamar desde otro hilo."""
        if self.rendido:
            return False
        with self.cerrojo:
            if not self._arrancar():
                return False
            clave = str(modelo)
            if clave in self.cargadas:
                return True
            r = self._pedir({"modelo": modelo, "carpeta": str(carpeta), "texto": ""}, self.espera_carga)
            if not r or not r.get("ok"):
                return self._fallar(f"no he podido cargar la voz ({(r or {}).get('error', 'sin respuesta')})")
            self.cargadas.add(clave)
            self._vigilar_inactividad()
            return True

    def sintetizar(self, modelo, carpeta, locutor, escala, texto, salida):
        """Sintetiza `texto` en el archivo `salida`. True si hay un audio bueno; False si hay que usar el método de siempre."""
        if self.rendido or not texto:
            return False
        with self.cerrojo:
            if not self._arrancar():
                return self._fallar("no arranca")
            primera = str(modelo) not in self.cargadas
            r = self._pedir({"modelo": modelo, "carpeta": str(carpeta), "locutor": locutor, "escala": escala, "texto": texto, "salida": str(salida)},
                            self.espera_carga if primera else self.espera_frase)
            if not r or not r.get("ok"):
                return self._fallar(f"no ha podido ({(r or {}).get('error', 'sin respuesta a tiempo')})")
            if not audio_valido(salida):
                return self._fallar("ha dejado un audio vacío")
            self.cargadas.add(str(modelo))
            self.fallos = 0
            self._vigilar_inactividad()
            return True


if __name__ == "__main__":
    if "--trabajador" in sys.argv:
        trabajador()
