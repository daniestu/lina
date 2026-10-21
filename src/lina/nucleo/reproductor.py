# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Controlar la música que ya suena: pausar, seguir, siguiente, anterior y detener.

Hay dos caminos. Si algún reproductor habla MPRIS (Spotify, el navegador, VLC, mpv con su plugin…), se usa `playerctl`. Y la música que pone la propia Lina con mpv
se lanza con un socket de control (`--input-ipc-server`), porque mpv a pelo no habla MPRIS y `playerctl` no lo ve: sin esto, «pausa» no tendría a quién hablarle.
Aquí está el segundo camino, que también sirve desde la terminal:  lina musica pausar|reanudar|siguiente|anterior|detener"""
import json
import socket

from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import T

ACCIONES = ("pausar", "reanudar", "siguiente", "anterior", "detener")
_ORDENES_MPV = {"pausar": [["set_property", "pause", True]], "reanudar": [["set_property", "pause", False]], "siguiente": [["playlist-next"]],
                "anterior": [["playlist-prev"]], "detener": [["quit"]]}
ESPERA_SEG = 1.5


def ruta_mpv():
    """Dónde escucha el mpv que lanza Lina."""
    return RUT.EJECUCION / "mpv.sock"


def enviar_mpv(accion, ruta=None, espera=ESPERA_SEG):
    """Manda la orden al mpv de Lina. True solo si mpv contesta que la ha hecho; False si no hay ninguno sonando (o no es suyo)."""
    ordenes = _ORDENES_MPV.get(accion)
    if not ordenes:
        return False
    ruta = ruta or ruta_mpv()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(espera)
            s.connect(str(ruta))
            lector = s.makefile("r", encoding="utf-8")
            for orden in ordenes:
                s.sendall((json.dumps({"command": orden, "request_id": 7}) + "\n").encode("utf-8"))
                while True:                                           # mpv también manda eventos sueltos: se espera a LA respuesta
                    linea = lector.readline()
                    if not linea:
                        return accion == "detener"                    # al salir, cierra la conexión sin contestar
                    try:
                        r = json.loads(linea)
                    except ValueError:
                        continue
                    if r.get("request_id") == 7:
                        if r.get("error") != "success":
                            return False
                        break
        return True
    except (OSError, ValueError):
        return False


def principal(argv, salida=print):
    if len(argv) != 1 or argv[0] not in ACCIONES:
        salida(T("Uso:  lina musica pausar|reanudar|siguiente|anterior|detener   (la música que pone Lina con mpv)"))
        return 2
    if enviar_mpv(argv[0]):
        salida(T("Hecho."))
        return 0
    salida(T("No hay música de Lina sonando (con mpv); los demás reproductores se controlan con playerctl."))
    return 1
