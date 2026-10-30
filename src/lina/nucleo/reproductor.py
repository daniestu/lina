# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Controlar la música que ya suena: pausar, seguir, siguiente, anterior y detener.

Hay dos caminos. Si algún reproductor habla MPRIS (Spotify, el navegador, VLC, mpv con su plugin…), se usa `playerctl`. Y la música que pone la propia Lina con mpv
se lanza con un socket de control (`--input-ipc-server`), porque mpv a pelo no habla MPRIS y `playerctl` no lo ve: sin esto, «pausa» no tendría a quién hablarle.
Aquí está el segundo camino, que también sirve desde la terminal:  lina musica pausar|reanudar|siguiente|anterior|detener"""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
from urllib.parse import quote_plus

from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import T

ACCIONES = ("pausar", "reanudar", "siguiente", "anterior", "detener")
_ORDENES_MPV = {"pausar": [["set_property", "pause", True]], "reanudar": [["set_property", "pause", False]], "siguiente": [["playlist-next"]],
                "anterior": [["playlist-prev"]], "detener": [["quit"]], "vivo": [["get_property", "pause"]]}
ESPERA_SEG = 1.5
ESPERA_ARRANQUE_SEG = 30        # lo que puede tardar yt-dlp en encontrar la canción y mpv en empezar a sonar
MIN_SONANDO_SEG = 0.5           # «Sonando» solo cuando ya se ha reproducido esto de verdad (mpv vivo no basta)
ESPERA_ALTERNATIVA_SEG = 20     # cada vía alternativa (otro cliente, SoundCloud) tiene menos margen
# Clientes de YouTube que se prueban, en orden, si el de siempre no deja (comprobado en octubre de 2026: tv y web_safari fallaban, estos no). Cambia con
# el tiempo: por eso se comprueba cuál encuentra el audio antes de usarlo.
CLIENTES_YOUTUBE = ("web_embedded", "mweb", "android_vr", "tv_simply")


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


def poner(consulta, ruta=None, salida=print, arranque_seg=ESPERA_ARRANQUE_SEG, reloj=time.monotonic, dormir=time.sleep, alternativas=True):
    """Pone música (una búsqueda, «Queen», o un enlace) y SOLO dice que suena si el audio avanza de verdad. Si algo falla, cuenta qué (sin mpv, sin yt-dlp,
    no se encuentra, YouTube no deja descargarlo…). Devuelve 0 si suena (o si se ha abierto en el navegador, y lo dice).

    yt-dlp descarga el audio y se lo pasa a mpv por una tubería: YouTube ya no deja que otro programa descargue el enlace que extrae yt-dlp (mpv recibe un
    403), ni con `yt-dlp -g` ni con mpv resolviendo la página. mpv sigue con su socket de control (pausar, reanudar, detener).

    Si no suena, prueba otras vías antes de rendirse, en este orden y sin tus cookies ni tu cuenta (M3): otro cliente de YouTube (el primero de
    CLIENTES_YOUTUBE que encuentre el audio), la misma búsqueda en SoundCloud y, por último, abrirla en tu navegador. Dice siempre por qué vía suena."""
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
    enlace = consulta.lower().startswith(("http://", "https://"))
    objetivo = consulta if enlace else f"ytsearch1:{consulta}"

    def sonar(obj, extra=(), espera=arranque_seg):
        return _sonar(mpv, ytdlp, obj, consulta, ruta, espera, reloj, dormir, extra)
    ok, motivo, tipo = sonar(objetivo)
    if ok:
        salida(T("Sonando: {consulta}.", consulta=consulta))
        return 0
    if tipo == "arranque":                                         # sin poder lanzar mpv, ninguna otra vía con mpv va a ir mejor
        salida(motivo)
        return 1
    if not alternativas:
        if tipo == "tiempo":
            salida(T("No ha empezado a sonar a tiempo: {motivo}. No suena nada.", motivo=motivo))
        else:
            salida(T("No ha llegado a sonar: {motivo}. No suena nada.", motivo=motivo))
        return 1
    if not enlace or _es_youtube(consulta):
        cliente = _cliente_que_sirve(ytdlp, objetivo)
        if cliente:
            ok, _, _ = sonar(objetivo, ("--extractor-args", f"youtube:player_client={cliente}"), ESPERA_ALTERNATIVA_SEG)
            if ok:
                salida(T("Sonando: {consulta} (por YouTube, con otro cliente).", consulta=consulta))
                return 0
    if not enlace:
        ok, _, _ = sonar(f"scsearch1:{consulta}", espera=ESPERA_ALTERNATIVA_SEG)
        if ok:
            salida(T("Sonando: {consulta} (en SoundCloud, porque YouTube no ha dejado).", consulta=consulta))
            return 0
    url = consulta if enlace else _enlace_youtube(ytdlp, consulta)
    if url and abrir_en_navegador(url):
        salida(T("El reproductor de Lina no ha podido ponerla ({motivo}). Te la he abierto en el navegador: {url} (no puedo comprobar desde aquí que suene).",
                 motivo=motivo, url=url))
        return 0
    busqueda = "https://www.youtube.com/results?search_query=" + quote_plus(consulta)
    if not enlace and abrir_en_navegador(busqueda):
        salida(T("No he podido ponerla ({motivo}). Te he abierto la búsqueda en YouTube en el navegador: elige tú la canción. No suena nada todavía.",
                 motivo=motivo))
        return 1
    salida(T("No ha llegado a sonar: {motivo}. He probado YouTube, otro cliente de YouTube, SoundCloud y el navegador. No suena nada; no lo intentes por "
             "otra vía.", motivo=motivo))
    return 1


def _sonar(mpv, ytdlp, objetivo, titulo, ruta, arranque_seg, reloj, dormir, extra=()):
    """Un intento: yt-dlp (con `extra`) le pasa el audio de `objetivo` a mpv. (True, None, None) si el audio avanza; si no, (False, motivo, tipo), con
    tipo «cerrado» (mpv terminó), «tiempo» (no empezó a tiempo) o «arranque» (no se pudo lanzar; el motivo ya es la frase completa)."""
    carpeta = os.path.dirname(str(ruta))
    try:
        os.makedirs(carpeta, mode=0o700, exist_ok=True)
        registro_yt = open(os.path.join(carpeta, "yt-dlp.log"), "w+", encoding="utf-8")
        registro_mpv = open(os.path.join(carpeta, "mpv.log"), "w+", encoding="utf-8")
        descarga = subprocess.Popen([ytdlp, "-q", "--no-warnings", "--no-playlist", *extra, "-f", "bestaudio/best", "-o", "-", objetivo],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=registro_yt, start_new_session=True)
        proceso = subprocess.Popen([mpv, "--no-video", "--msg-level=all=error", f"--input-ipc-server={ruta}", f"--force-media-title={titulo}", "-"],
                                   stdin=descarga.stdout, stdout=registro_mpv, stderr=registro_mpv, start_new_session=True)
    except OSError as e:
        return False, T("No he podido arrancar mpv ({error}). No suena nada.", error=e), "arranque"
    descarga.stdout.close()                                         # así, si mpv se cierra, yt-dlp se entera y termina
    _guardar_pid(ruta, descarga.pid)

    def motivo():
        registro_yt.seek(0)
        registro_mpv.seek(0)
        return _cola(registro_yt.read()) or _cola(registro_mpv.read()) or T("sin mensaje")
    limite = reloj() + arranque_seg
    while reloj() < limite:
        if proceso.poll() is not None:
            _cerrar(descarga)
            return False, motivo(), "cerrado"
        tiempo = propiedad_mpv("playback-time", ruta)
        if isinstance(tiempo, (int, float)) and tiempo >= MIN_SONANDO_SEG:
            return True, None, None
        dormir(0.3)
    _cerrar(proceso)
    _cerrar(descarga)
    return False, motivo(), "tiempo"


def _es_youtube(url):
    return bool(re.search(r"(?:^|\.|//)(?:youtube\.com|youtu\.be)/", url.lower()))


def _cliente_que_sirve(ytdlp, objetivo):
    """El primer cliente de YouTube de CLIENTES_YOUTUBE con el que yt-dlp encuentra el audio (solo lo comprueba, sin descargar), o None."""
    for cliente in CLIENTES_YOUTUBE:
        try:
            r = subprocess.run([ytdlp, "-q", "--no-warnings", "--no-playlist", "--extractor-args", f"youtube:player_client={cliente}", "-f", "bestaudio/best",
                                "--print", "format_id", objetivo], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0 and r.stdout.strip():
            return cliente
    return None


def _enlace_youtube(ytdlp, consulta):
    """La dirección del primer vídeo de la búsqueda en YouTube (solo lee la lista de resultados: no hace falta descargar nada), o None."""
    try:
        r = subprocess.run([ytdlp, "-q", "--no-warnings", "--flat-playlist", "--print", "url", f"ytsearch1:{consulta}"],
                           capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    enlaces = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("https://")]
    return enlaces[0] if r.returncode == 0 and enlaces else None


def abrir_en_navegador(url):
    """Abre `url` en tu navegador (xdg-open). True si se ha podido lanzar."""
    abrir = shutil.which("xdg-open")
    if not abrir:
        return False
    try:
        subprocess.Popen([abrir, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


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
