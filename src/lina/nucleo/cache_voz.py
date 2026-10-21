# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Caché de frases cortas ya sintetizadas («Abierto.», «Volumen al 40 %.»): la segunda vez suenan al instante, sin arrancar Piper.
Solo guarda frases cortas; las respuestas largas no se repiten y no merece la pena. Vive en la carpeta de caché y se puede borrar sin perder nada."""
import hashlib
import os
import shutil

from lina.nucleo import rutas as RUT

MAX_CARACTERES = 48
MAX_ARCHIVOS = 300
CARPETA = RUT.CACHE / "voz"


def _ruta(modelo, locutor, velocidad, texto, carpeta=None):
    clave = f"{modelo}|{locutor}|{velocidad:.3f}|{texto}"
    return (carpeta or CARPETA) / (hashlib.sha1(clave.encode("utf-8")).hexdigest()[:20] + ".wav")


def buscar(modelo, locutor, velocidad, texto, carpeta=None):
    """La ruta del audio ya sintetizado, o None."""
    if not texto or len(texto) > MAX_CARACTERES:
        return None
    ruta = _ruta(modelo, locutor, velocidad, texto, carpeta)
    try:
        if ruta.stat().st_size > 44:
            os.utime(ruta)                       # lo usado hace poco no se retira
            return ruta
    except OSError:
        pass
    return None


def guardar(origen, modelo, locutor, velocidad, texto, carpeta=None):
    """Guarda una copia del audio recién sintetizado (si la frase es corta). Nunca falla: es un extra."""
    if not texto or len(texto) > MAX_CARACTERES:
        return False
    carpeta = carpeta or CARPETA
    try:
        RUT.asegurar(carpeta)
        destino = _ruta(modelo, locutor, velocidad, texto, carpeta)
        parcial = destino.with_suffix(".tmp")
        shutil.copyfile(origen, parcial)
        os.replace(parcial, destino)
        podar(carpeta)
        return True
    except OSError:
        return False


def podar(carpeta=None, maximo=None):
    carpeta = carpeta or CARPETA
    maximo = maximo or MAX_ARCHIVOS
    try:
        archivos = sorted(carpeta.glob("*.wav"), key=lambda f: f.stat().st_mtime)
        for f in archivos[:max(0, len(archivos) - maximo)]:
            f.unlink(missing_ok=True)
    except OSError:
        pass
