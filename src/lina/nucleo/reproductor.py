# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Controlar la música que ya suena: pausar, seguir, siguiente, anterior y detener.

Hay dos caminos. Si algún reproductor habla MPRIS (Spotify, el navegador, VLC, mpv con su plugin…), se usa `playerctl`. Y la música que pone la propia Lina con mpv
se lanza con un socket de control (`--input-ipc-server`), porque mpv a pelo no habla MPRIS y `playerctl` no lo ve: sin esto, «pausa» no tendría a quién hablarle.
Aquí está el segundo camino, que también sirve desde la terminal:  lina musica pausar|reanudar|siguiente|anterior|detener"""
import json
import os
import shutil
import socket
import subprocess
import time

from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import T

ACCIONES = ("pausar", "reanudar", "siguiente", "anterior", "detener")
_ORDENES_MPV = {"pausar": [["set_property", "pause", True]], "reanudar": [["set_property", "pause", False]], "siguiente": [["playlist-next"]],
                "anterior": [["playlist-prev"]], "detener": [["quit"]], "vivo": [["get_property", "pause"]]}
ESPERA_SEG = 1.5
ESPERA_BUSCAR_SEG = 40          # lo que puede tardar yt-dlp en encontrar la canción
ESPERA_ARRANQUE_SEG = 15        # lo que puede tardar mpv en estar listo y respondiendo


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


def _cola(texto, n=3):
    lineas = [l.strip() for l in str(texto or "").splitlines() if l.strip()]
    return " | ".join(lineas[-n:])[:300]


def poner(consulta, ruta=None, salida=print, buscar_seg=ESPERA_BUSCAR_SEG, arranque_seg=ESPERA_ARRANQUE_SEG):
    """Pone música con mpv (con su socket de control) y SOLO dice que suena si mpv está vivo y contesta; si algo falla, cuenta qué (sin mpv, sin yt-dlp, no se
    encuentra, mpv se cierra…). Una búsqueda («Queen») o un enlace. Devuelve 0 si suena."""
    consulta = " ".join(str(consulta).split())
    if not consulta:
        salida(T("Dime qué quieres escuchar:  lina musica poner \"Queen\""))
        return 2
    mpv = shutil.which("mpv")
    if not mpv:
        salida(T("No está instalado mpv, el reproductor que usa Lina para la música. Instálalo (por ejemplo el paquete «mpv») y vuelve a probar."))
        return 1
    ruta = ruta or ruta_mpv()
    enviar_mpv("detener", ruta)                                     # lo que sonara antes de Lina se cierra: no se montan dos músicas
    objetivo = consulta
    if not consulta.lower().startswith(("http://", "https://")):
        ytdlp = shutil.which("yt-dlp")
        if not ytdlp:
            salida(T("No está instalado yt-dlp, que busca las canciones en internet. Instálalo (el paquete «yt-dlp») y vuelve a probar."))
            return 1
        try:
            r = subprocess.run([ytdlp, "-g", "-f", "bestaudio/best", "--no-playlist", "--no-warnings", f"ytsearch1:{consulta}"],
                               capture_output=True, text=True, timeout=buscar_seg, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            salida(T("yt-dlp no ha encontrado «{consulta}» a tiempo (¿sin internet?). No suena nada.", consulta=consulta))
            return 1
        enlaces = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("http")]
        if r.returncode != 0 or not enlaces:
            salida(T("yt-dlp no ha podido encontrar «{consulta}»: {motivo}. No suena nada.", consulta=consulta, motivo=_cola(r.stderr) or T("sin resultados")))
            return 1
        objetivo = enlaces[0]
    try:
        os.makedirs(os.path.dirname(str(ruta)), mode=0o700, exist_ok=True)
        registro = open(os.path.join(os.path.dirname(str(ruta)), "mpv.log"), "w+", encoding="utf-8")
        proceso = subprocess.Popen([mpv, "--no-video", "--really-quiet", f"--input-ipc-server={ruta}", objetivo],
                                   stdin=subprocess.DEVNULL, stdout=registro, stderr=registro, start_new_session=True)
    except OSError as e:
        salida(T("No he podido arrancar mpv ({error}). No suena nada.", error=e))
        return 1
    limite = time.time() + arranque_seg
    while time.time() < limite:
        if proceso.poll() is not None:
            registro.seek(0)
            salida(T("mpv se ha cerrado nada más empezar: {motivo}. No suena nada.", motivo=_cola(registro.read()) or T("sin mensaje")))
            return 1
        if enviar_mpv("vivo", ruta, espera=1):
            time.sleep(1.5)                                          # si el enlace no vale, mpv se cierra enseguida
            if proceso.poll() is None:
                salida(T("Sonando: {consulta}.", consulta=consulta))
                return 0
        else:
            time.sleep(0.3)
    if proceso.poll() is None:
        proceso.terminate()
    salida(T("mpv no ha llegado a empezar a tiempo. No suena nada."))
    return 1


def principal(argv, salida=print):
    if argv and argv[0] == "poner":
        return poner(" ".join(argv[1:]), salida=salida)
    if len(argv) != 1 or argv[0] not in ACCIONES:
        salida(T("Uso:  lina musica pausar|reanudar|siguiente|anterior|detener   (la música que pone Lina con mpv)"))
        return 2
    if enviar_mpv(argv[0]):
        salida(T("Hecho."))
        return 0
    salida(T("No hay música de Lina sonando (con mpv); los demás reproductores se controlan con playerctl."))
    return 1
