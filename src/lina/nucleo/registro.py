# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Registro de acciones (acciones.log) y avisos del escritorio. Todo lo que hace el asistente queda anotado aquí, con las claves tapadas."""
import os
import re
import shutil
import subprocess
import time

from lina.nucleo import rutas as RUT

ARCHIVO_ACCIONES = RUT.REGISTRO_ACCIONES

# S10: en modo privado, lo que va al registro (y el servicio vuelca al journal: journalctl --user -u lina) no lleva lo que dices ni lo que contesto, con
# independencia de privacidad.registrar_preguntas. Lo pone el asistente al arrancar y al cambiar el modo. Se tapa aquí, por donde pasa todo, y no línea a
# línea: de cada línea queda solo el principio, hasta los primeros dos puntos, «, una dirección web o un nombre de dominio, y además se tapan en cualquier
# parte las frases del turno (lo que dijiste, lo que oyó Whisper, la respuesta). Coste aceptado: un fallo en privado es más difícil de diagnosticar.
PRIVADO = False
_FRASES: list[str] = []
MAX_FRASES = 20
_CORTE = re.compile(r": |«|\bhttps?://|\b(?:[\w-]+\.)+[a-z]{2,}\b", re.I)


def tapar(*textos):
    """Frases de este turno que no pueden salir en el registro mientras dure el modo privado (se guardan solo en memoria, las últimas MAX_FRASES)."""
    for texto in textos:
        texto = str(texto or "").strip()
        if len(texto) >= 3 and texto not in _FRASES:
            _FRASES.append(texto)
    del _FRASES[:-MAX_FRASES]


def privado(activo):
    global PRIVADO
    PRIVADO = bool(activo)
    if not PRIVADO:
        _FRASES.clear()


def _en_privado(mensaje):
    for frase in sorted(_FRASES, key=len, reverse=True):
        mensaje = mensaje.replace(frase, "…")
    m = _CORTE.search(mensaje)
    return mensaje[:m.start()].rstrip() + (": …" if m.group(0) == ": " else " …") if m else mensaje


def log(mensaje):
    mensaje = str(mensaje)
    if PRIVADO:
        mensaje = _en_privado(mensaje)
    print(f"[{time.strftime('%H:%M:%S')}] {mensaje}", flush=True)


MAX_REGISTRO_ACCIONES = 1_000_000          # al pasar de ~1 MB el registro de acciones se rota: se guarda la mitad vieja como .1 (una sola copia)


def _rotar(ruta, maximo):
    try:
        if ruta.stat().st_size > maximo:
            ruta.replace(ruta.with_name(ruta.name + ".1"))
    except OSError:
        pass


def anotar(linea):
    """Cada acción queda escrita en acciones.log (con las claves tapadas y rotando el archivo para que no crezca sin fin)."""
    try:
        from lina.nucleo import claves as _claves
        linea = _claves.limpiar(str(linea))
    except Exception:
        pass
    if not str(linea).startswith("[salida-del-fallo]"):
        linea = str(linea).replace("\n", " ⏎ ")       # A16: una orden de varias líneas, entera en su línea del registro
    try:
        _rotar(ARCHIVO_ACCIONES, MAX_REGISTRO_ACCIONES)
        fd = os.open(ARCHIVO_ACCIONES, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {linea}\n")
    except OSError:
        pass


def notificar(titulo, cuerpo=""):
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", "-a", "Asistente", titulo, cuerpo[:400]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
