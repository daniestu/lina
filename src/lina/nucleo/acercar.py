# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Acercar lo que oyó Whisper a lo que Lina ya conoce: sus órdenes («pausas» → «pausa») y los nombres de tus programas y juegos («cait» → «Kate»).

Es parecido de sonido, sin IA y sin memoria de vídeo. Corrige en dos niveles:
  1. La frase entera, si es corta y casi idéntica a una orden conocida.
  2. Palabra a palabra, solo contra el vocabulario propio (programas, juegos, términos tuyos), nunca contra el diccionario.
Devuelve siempre lo cambiado, para poder registrarlo y para que se pueda medir cuántas veces acierta y cuántas estropea algo."""
import difflib
import re

from lina.nucleo import comandos as C

ORDENES = {
    "es": ["pausa", "reanuda la música", "sigue con la música", "siguiente canción", "canción anterior", "para la música", "sube el volumen", "baja el volumen",
           "silencia el sonido", "quita el silencio", "maximiza esta ventana", "minimiza esta ventana", "pantalla completa", "muestra el escritorio",
           "qué hora es", "qué día es hoy", "conecta mis auriculares", "desconecta el mando", "enciende el bluetooth", "cierra esta ventana", "pon música"],
    "en": ["pause", "resume the music", "next song", "previous song", "stop the music", "turn the volume up", "turn the volume down", "mute the sound",
           "unmute", "maximize this window", "minimize this window", "full screen", "show the desktop", "what time is it", "what day is it today",
           "connect my headphones", "disconnect the controller", "turn on bluetooth", "close this window", "play music"],
}
MAX_PALABRAS_FRASE = 6
UMBRAL_FRASE = 0.82
UMBRAL_PALABRA = 0.86
MIN_LETRAS_PALABRA = 4


def _fonetica(palabra):
    """Una clave de sonido para el español: las letras que suenan igual se igualan (v/b, c/k/qu, ll/y, h muda, z/s…)."""
    p = C.normalizar(palabra).replace(" ", "")
    for a, b in (("qu", "k"), ("ll", "y"), ("ch", "x"), ("gue", "ge"), ("gui", "gi"), ("ce", "se"), ("ci", "si"), ("ca", "ka"), ("co", "ko"), ("cu", "ku"), ("c", "k")):
        p = p.replace(a, b)
    p = re.sub(r"^h", "", p).replace("h", "")
    for a, b in (("v", "b"), ("z", "s"), ("w", "u"), ("j", "g"), ("ñ", "n")):
        p = p.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", p)


def _ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def acercar(texto, ordenes=(), vocabulario=(), umbral_frase=UMBRAL_FRASE, umbral_palabra=UMBRAL_PALABRA):
    """→ (texto_corregido, [cambios]). Cada cambio es (oído, puesto). Si no hay nada claro, devuelve el texto tal cual."""
    original = str(texto or "").strip()
    n = C.normalizar(original)
    if not n:
        return original, []
    if len(n.split()) <= MAX_PALABRAS_FRASE:                             # 1. ¿es una orden conocida mal oída?
        mejor, puntos = None, 0.0
        for o in ordenes:
            on = C.normalizar(o)
            if on == n:
                return original, []                                      # ya es exactamente una orden
            r = max(_ratio(n, on), _ratio(_fonetica(n), _fonetica(on)))
            if r > puntos:
                mejor, puntos = o, r
        if mejor is not None and puntos >= umbral_frase:
            return mejor, [(original, mejor)]
    conocidas = {C.normalizar(v): v for v in vocabulario if v}           # 2. palabras raras contra tu vocabulario
    claves = {_fonetica(k): v for k, v in conocidas.items() if " " not in k}
    cambios = []

    def cambiar(m):
        palabra = m.group(0)
        pn = C.normalizar(palabra)
        if len(pn) < MIN_LETRAS_PALABRA or pn in conocidas:
            return palabra
        mejor, puntos = None, 0.0
        for clave, valor in claves.items():
            r = _ratio(_fonetica(pn), clave)
            if r > puntos:
                mejor, puntos = valor, r
        if mejor is not None and puntos >= umbral_palabra:
            cambios.append((palabra, mejor))
            return mejor
        return palabra
    return re.sub(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+", cambiar, original), cambios


def ordenes_para(idioma, vocabulario=()):
    """Las órdenes conocidas del idioma, más «abre X» por cada programa o juego del vocabulario."""
    base = list(ORDENES.get(idioma) or ORDENES["es"])
    verbo = "open" if idioma == "en" else "abre"
    return base + [f"{verbo} {v}" for v in vocabulario if v]
