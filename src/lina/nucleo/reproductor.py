# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Controlar la música que ya suena: pausar, seguir, siguiente, anterior y detener.

Hay dos caminos. Si algún reproductor habla MPRIS (Spotify, el navegador, VLC, mpv con su plugin…), se usa `playerctl`. Y la música que pone la propia Lina con mpv
se lanza con un socket de control (`--input-ipc-server`), porque mpv a pelo no habla MPRIS y `playerctl` no lo ve: sin esto, «pausa» no tendría a quién hablarle.
Aquí está el segundo camino, que también sirve desde la terminal:  lina musica pausar|reanudar|siguiente|anterior|detener"""
import json
import os
import shutil
import signal
import socket
import subprocess
import time

from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import T

ACCIONES = ("pausar", "reanudar", "siguiente", "anterior", "detener")
_ORDENES_MPV = {"pausar": [["set_property", "pause", True]], "reanudar": [["set_property", "pause", False]], "siguiente": [["playlist-next"]],
                "anterior": [["playlist-prev"]], "detener": [["quit"]], "vivo": [["get_property", "pause"]]}
ESPERA_SEG = 1.5
ESPERA_ARRANQUE_SEG = 30        # lo que puede tardar yt-dlp en encontrar la canción y mpv en empezar a sonar
MIN_SONANDO_SEG = 0.5           # «Sonando» solo cuando ya se ha reproducido esto de verdad (mpv vivo no basta)


def ruta_mpv():
    """Dónde escucha el mpv que lanza Lina."""
    return RUT.EJECUCION / "mpv.sock"


def enviar_mpv(accion, ruta=None, espera=ESPERA_SEG):
    """Manda la orden al mpv de Lina. True solo si mpv contesta que la ha hecho; False si no hay ninguno sonando (o no es suyo)."""
    ordenes = _ORDENES_MPV.get(accion)
    if not ordenes:
        return False
    ruta = ruta or ruta_mpv()
    if accion == "detener":
        cerrar_descarga(ruta)
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


def propiedad_mpv(nombre, ruta=None, espera=1.0):
    """El valor de una propiedad del mpv de Lina (por ejemplo «playback-time»), o None si no hay mpv o aún no la tiene."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(espera)
            s.connect(str(ruta or ruta_mpv()))
            lector = s.makefile("r", encoding="utf-8")
            s.sendall((json.dumps({"command": ["get_property", nombre], "request_id": 8}) + "\n").encode("utf-8"))
            for linea in lector:
                try:
                    r = json.loads(linea)
                except ValueError:
                    continue
                if r.get("request_id") == 8:
                    return r.get("data") if r.get("error") == "success" else None
    except (OSError, ValueError):
        return None
    return None


def _cola(texto, n=3):
    lineas = [l.strip() for l in str(texto or "").splitlines() if l.strip()]
    return " | ".join(lineas[-n:])[:300]


def poner(consulta, ruta=None, salida=print, arranque_seg=ESPERA_ARRANQUE_SEG, reloj=time.monotonic, dormir=time.sleep):
    """Pone música (una búsqueda, «Queen», o un enlace) y SOLO dice que suena si el audio avanza de verdad. Si algo falla, cuenta qué (sin mpv, sin yt-dlp,
    no se encuentra, YouTube no deja descargarlo…). Devuelve 0 si suena.

    yt-dlp descarga el audio y se lo pasa a mpv por una tubería: YouTube ya no deja que otro programa descargue el enlace que extrae yt-dlp (mpv recibe un
    403), ni con `yt-dlp -g` ni con mpv resolviendo la página. mpv sigue con su socket de control (pausar, reanudar, detener)."""
    consulta = " ".join(str(consulta).split())
    if not consulta:
        salida(T("Dime qué quieres escuchar:  lina musica poner \"Queen\""))
        return 2
    mpv, ytdlp = shutil.which("mpv"), shutil.which("yt-dlp")
    if not mpv:
        salida(T("No está instalado mpv, el reproductor que usa Lina para la música. Instálalo (por ejemplo el paquete «mpv») y vuelve a probar."))
        return 1
    if not ytdlp:
        salida(T("No está instalado yt-dlp, que busca las canciones en internet. Instálalo (el paquete «yt-dlp») y vuelve a probar."))
        return 1
    ruta = ruta or ruta_mpv()
    enviar_mpv("detener", ruta)                                     # lo que sonara antes de Lina se cierra (y su descarga): no se montan dos músicas
    objetivo = consulta if consulta.lower().startswith(("http://", "https://")) else f"ytsearch1:{consulta}"
    carpeta = os.path.dirname(str(ruta))
    try:
        os.makedirs(carpeta, mode=0o700, exist_ok=True)
        registro_yt = open(os.path.join(carpeta, "yt-dlp.log"), "w+", encoding="utf-8")
        registro_mpv = open(os.path.join(carpeta, "mpv.log"), "w+", encoding="utf-8")
        descarga = subprocess.Popen([ytdlp, "-q", "--no-warnings", "--no-playlist", "-f", "bestaudio/best", "-o", "-", objetivo],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=registro_yt, start_new_session=True)
        proceso = subprocess.Popen([mpv, "--no-video", "--msg-level=all=error", f"--input-ipc-server={ruta}", f"--force-media-title={consulta}", "-"],
                                   stdin=descarga.stdout, stdout=registro_mpv, stderr=registro_mpv, start_new_session=True)
    except OSError as e:
        salida(T("No he podido arrancar mpv ({error}). No suena nada.", error=e))
        return 1
    descarga.stdout.close()                                         # así, si mpv se cierra, yt-dlp se entera y termina
    _guardar_pid(ruta, descarga.pid)

    def motivo():
        registro_yt.seek(0)
        registro_mpv.seek(0)
        return _cola(registro_yt.read()) or _cola(registro_mpv.read()) or T("sin mensaje")
    limite = reloj() + arranque_seg
    while reloj() < limite:
        if proceso.poll() is not None:
            salida(T("No ha llegado a sonar: {motivo}. No suena nada.", motivo=motivo()))
            _cerrar(descarga)
            return 1
        tiempo = propiedad_mpv("playback-time", ruta)
        if isinstance(tiempo, (int, float)) and tiempo >= MIN_SONANDO_SEG:
            salida(T("Sonando: {consulta}.", consulta=consulta))
            return 0
        dormir(0.3)
    _cerrar(proceso)
    _cerrar(descarga)
    salida(T("No ha empezado a sonar a tiempo: {motivo}. No suena nada.", motivo=motivo()))
    return 1


def _ruta_pid(ruta):
    return os.path.join(os.path.dirname(str(ruta or ruta_mpv())), "yt-dlp.pid")


def _guardar_pid(ruta, pid):
    try:
        with open(_ruta_pid(ruta), "w", encoding="utf-8") as f:
            f.write(str(pid))
    except OSError:
        pass


def _cerrar(proceso):
    try:
        if proceso.poll() is None:
            proceso.terminate()
    except OSError:
        pass


def cerrar_descarga(ruta=None):
    """Cierra el yt-dlp que estuviera descargando para la música de Lina (solo si de verdad es un yt-dlp: el número de proceso pudo reutilizarse)."""
    archivo = _ruta_pid(ruta)
    try:
        with open(archivo, encoding="utf-8") as f:
            pid = int(f.read().strip())
        os.remove(archivo)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            linea = f.read()
        if b"yt-dlp" not in linea and b"yt_dlp" not in linea:
            return False
        os.killpg(pid, signal.SIGTERM)
        return True
    except (OSError, ValueError):
        return False


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
