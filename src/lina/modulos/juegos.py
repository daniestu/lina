#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""
Biblioteca única de juegos: los instalados en Steam, Heroic (Epic, GOG, Amazon, propios) y Lutris, para poder decir «abre Skyrim» sin que la IA tenga que
adivinar comandos, para que Whisper conozca sus nombres y para saber QUÉ juego tienes delante mirando el proceso (no la clase de la ventana, que en
Lutris, Heroic o Wine no dice nada).

Solo LEE los archivos de los lanzadores (nunca los modifica). Los comandos de lanzamiento los fabrica este módulo con plantillas fijas y con identificadores
validados: nada de lo que haya dentro de esos archivos llega a un shell tal cual.
"""
import json
import os
import re
import shutil
import sqlite3
import time
from pathlib import Path

from lina.nucleo import comandos

_HOME = Path.home()
_TTL = 60
_cache = {"t": 0.0, "datos": []}

_NO_SON_JUEGOS = re.compile(r"^(proton\b|steam linux runtime|steamworks common|steam controller configs|steamvr\b|steam 360 video)", re.I)
_ID_VALIDO = re.compile(r"[A-Za-z0-9_.-]{1,80}")


def _limpiar_nombre(nombre):
    return re.sub(r"\s+", " ", re.sub(r"[™®©]", "", str(nombre or ""))).strip()


# ======================= Steam =======================
def _raices_steam():
    return [_HOME / ".local/share/Steam", _HOME / ".steam/steam", _HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]


def _carpetas_steamapps():
    carpetas = []
    for raiz in _raices_steam():
        principal = raiz / "steamapps"
        if not principal.is_dir():
            continue
        carpetas.append(principal.resolve())
        try:
            texto = (principal / "libraryfolders.vdf").read_text(errors="ignore")
        except OSError:
            continue
        for ruta in re.findall(r'"path"\s+"([^"]+)"', texto):
            extra = Path(ruta) / "steamapps"
            if extra.is_dir():
                carpetas.append(extra.resolve())
    return list(dict.fromkeys(carpetas))


def _steam():
    juegos = []
    for carpeta in _carpetas_steamapps():
        try:
            manifiestos = sorted(carpeta.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for m in manifiestos:
            try:
                t = m.read_text(errors="ignore")
            except OSError:
                continue

            def campo(k, t=t):
                r = re.search(r'"' + k + r'"\s+"([^"]*)"', t)
                return r.group(1) if r else ""
            appid, nombre, instalado = campo("appid"), _limpiar_nombre(campo("name")), campo("installdir")
            try:
                completo = int(campo("StateFlags") or 0) & 4
            except ValueError:
                completo = 0
            if not (appid.isdigit() and nombre and completo) or _NO_SON_JUEGOS.match(nombre):
                continue
            try:
                ultimo = float(campo("LastPlayed") or 0)
            except ValueError:
                ultimo = 0.0
            juegos.append({"nombre": nombre, "origen": "steam", "id": appid, "carpeta": str(carpeta / "common" / instalado) if instalado else "",
                           "ultimo": ultimo})
    return juegos


# ======================= Heroic =======================
def _config_heroic():
    return [d for d in (_HOME / ".config/heroic", _HOME / ".var/app/com.heroicgameslauncher.hgl/config/heroic") if d.is_dir()]


_RUNNERS = {"legendary": "legendary", "gog": "gog", "nile": "nile", "sideload": "sideload"}


def _nodos(obj):
    """Todos los diccionarios que parecen un juego (tienen identificador) dentro de un JSON de Heroic, sea cual sea su forma."""
    if isinstance(obj, dict):
        ident = obj.get("app_name") or obj.get("appName")
        if ident and isinstance(ident, str):
            yield obj
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from _nodos(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _nodos(v)


def _heroic():
    juegos, vistos = [], set()
    for base in _config_heroic():
        archivos = [("legendary", base / "legendaryConfig/legendary/installed.json", True), ("gog", base / "gog_store/installed.json", True),
                    ("nile", base / "nile_config/nile/installed.json", True), ("sideload", base / "sideload_apps/library.json", True),
                    ("legendary", base / "store_cache/legendary_library.json", False), ("gog", base / "store_cache/gog_library.json", False),
                    ("nile", base / "store_cache/nile_library.json", False)]
        titulos = {}
        datos = []
        for runner, ruta, solo_instalados in archivos:
            try:
                obj = json.loads(ruta.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, ValueError):
                continue
            for n in _nodos(obj):
                ident = str(n.get("app_name") or n.get("appName"))
                titulo = _limpiar_nombre(n.get("title") or n.get("name") or "")
                if titulo:
                    titulos[(runner, ident)] = titulo
                instalado = solo_instalados or bool(n.get("is_installed")) or bool(n.get("install_path"))
                carpeta = str(n.get("install_path") or (n.get("install") or {}).get("install_path") or n.get("folder_name") or "")
                datos.append((runner, ident, instalado, carpeta))
        for runner, ident, instalado, carpeta in datos:
            titulo = titulos.get((runner, ident), "")
            if not (instalado and titulo and _ID_VALIDO.fullmatch(ident)) or (runner, ident) in vistos:
                continue
            vistos.add((runner, ident))
            juegos.append({"nombre": titulo, "origen": "heroic", "id": ident, "runner": runner, "carpeta": carpeta if carpeta.startswith("/") else "",
                           "ultimo": 0.0})
    return juegos


# ======================= Lutris =======================
def _lutris():
    juegos = []
    for db in (_HOME / ".local/share/lutris/pga.db", _HOME / ".var/app/net.lutris.Lutris/data/lutris/pga.db"):
        if not db.is_file():
            continue
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
            try:
                filas = con.execute("SELECT id, name, directory, lastplayed FROM games WHERE installed = 1").fetchall()
            finally:
                con.close()
        except sqlite3.Error:
            continue
        for ident, nombre, carpeta, ultimo in filas:
            nombre = _limpiar_nombre(nombre)
            if nombre and isinstance(ident, int):
                juegos.append({"nombre": nombre, "origen": "lutris", "id": str(ident), "carpeta": str(carpeta or ""), "ultimo": float(ultimo or 0)})
    return juegos


# ======================= la biblioteca =======================
def biblioteca(forzar=False):
    """Todos los juegos instalados: [{'nombre', 'origen' (steam|heroic|lutris), 'id', 'carpeta', 'ultimo'}]. Se relee como mucho cada minuto."""
    if not forzar and time.time() - _cache["t"] < _TTL:
        return _cache["datos"]
    juegos = []
    for fuente in (_steam, _heroic, _lutris):
        try:
            juegos += fuente()
        except Exception:                                   # un lanzador con archivos raros no tumba a los demás
            continue
    vistos, unicos = set(), []
    for j in sorted(juegos, key=lambda j: -j["ultimo"]):
        clave = (comandos.normalizar(j["nombre"]), j["origen"])
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(j)
    _cache["t"], _cache["datos"] = time.time(), unicos
    return unicos


def como_apps(juegos=None):
    """Los juegos con la forma de los programas de comandos.py, para reutilizar las pistas de voz por parecido de sonido."""
    return [{"nombre": j["nombre"], "comando": "abrir_app", "es": "", "origen": "juego"} for j in (biblioteca() if juegos is None else juegos)]


def nombres_para_whisper(maximo=20, juegos=None):
    """Nombres cortos y normales, los jugados más recientemente primero (una lista larga de nombres raros haría que Whisper los oyera donde no están)."""
    vistos, nombres = set(), []
    for j in sorted(biblioteca() if juegos is None else juegos, key=lambda j: (-j["ultimo"], j["nombre"].lower())):
        n = j["nombre"]
        if len(n) > 30 and ":" in n:                         # «The Elder Scrolls V: Skyrim Special Edition» → «Skyrim Special Edition»
            n = n.rsplit(":", 1)[1].strip()
        clave = comandos.normalizar(n)
        if len(n) > 30 or not re.fullmatch(r"[\w ':&.,!-]+", n) or clave in vistos:
            continue
        vistos.add(clave)
        nombres.append(n)
        if len(nombres) >= maximo:
            break
    return nombres


# ======================= buscar por nombre =======================
_ROMANOS = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
_EXTRA = {"juega", "jugar", "juego", "partida", "videojuego", "a", "al"}


def _tokens(texto):
    return [_ROMANOS.get(w, w) for w in comandos.normalizar(texto).split()]


def buscar(consulta, juegos=None):
    """Los juegos que encajan con lo dicho, de más a menos parecido: [(puntos, juego)]. 100 = nombre exacto; también vale decir solo una parte
    («skyrim»), el nombre con números romanos o un nombre que suena parecido (lo que oye Whisper)."""
    q = [w for w in _tokens(consulta) if w not in comandos._RELLENO and w not in comandos._VERBOS_DE_PROGRAMA and w not in _EXTRA]
    if not q:
        return []
    qj = " ".join(q)
    resultado = []
    for j in (biblioteca() if juegos is None else juegos):
        nombre = _tokens(j["nombre"])
        nj = " ".join(nombre)
        if qj == nj or qj.replace(" ", "") == nj.replace(" ", ""):
            puntos = 100
        elif all(w in nombre for w in q):
            puntos = 90                                               # un trozo del nombre; si hay varios iguales, gana el que más has jugado
        elif len(nombre) >= 1 and set(nombre) <= set(q) and len(nj) >= 4:
            puntos = 84
        else:
            sonido = comandos._parecido(qj, j["nombre"]) if len(qj) >= 3 else 0.0
            puntos = int(80 * sonido) if sonido >= comandos.UMBRAL_PARECIDO else 0
        if puntos >= 55:
            resultado.append((puntos, j))
    resultado.sort(key=lambda x: (-x[0], -x[1]["ultimo"], len(x[1]["nombre"])))
    return resultado


# ======================= cómo se lanza =======================
def comando_de_lanzamiento(j):
    """El comando para abrir ese juego (plantilla fija, identificador validado), o None si no se puede."""
    ident = str(j.get("id", ""))
    if not _ID_VALIDO.fullmatch(ident):
        return None
    if j["origen"] == "steam":
        if not ident.isdigit():
            return None
        if shutil.which("steam"):
            return f"steam steam://rungameid/{ident}"
        if (_HOME / ".var/app/com.valvesoftware.Steam").is_dir() and shutil.which("flatpak"):
            return f"flatpak run com.valvesoftware.Steam steam://rungameid/{ident}"
        return None
    if j["origen"] == "lutris":
        if not ident.isdigit():
            return None
        if shutil.which("lutris"):
            return f"lutris lutris:rungameid/{ident}"
        if (_HOME / ".var/app/net.lutris.Lutris").is_dir() and shutil.which("flatpak"):
            return f"flatpak run net.lutris.Lutris lutris:rungameid/{ident}"
        return None
    if j["origen"] == "heroic":
        runner = j.get("runner", "")
        if runner not in _RUNNERS.values():
            return None
        url = f"heroic://launch/{runner}/{ident}"
        for programa in ("heroic", "heroic-games-launcher"):
            if shutil.which(programa):
                return f"{programa} {url}"
        if (_HOME / ".var/app/com.heroicgameslauncher.hgl").is_dir() and shutil.which("flatpak"):
            return f"flatpak run com.heroicgameslauncher.hgl {url}"
    return None


# ======================= qué juego es el de esta ventana (por el proceso) =======================
def _leer(ruta, binario=False):
    try:
        with open(ruta, "rb") as f:
            datos = f.read(200000)
    except OSError:
        return b"" if binario else ""
    return datos if binario else datos.decode("utf-8", "ignore")


def _padre(proc, pid):
    stat = _leer(f"{proc}/{pid}/stat")
    try:
        return int(stat.rsplit(")", 1)[1].split()[1])
    except (IndexError, ValueError):
        return 0


def juego_de_proceso(pid, proc="/proc", juegos=None):
    """Mira el proceso de la ventana y sus padres: el juego puede estar detrás de Wine, Proton, umu o un envoltorio, y la clase de la ventana
    ('wine', 'steam_proton', 'lutris') no dice cuál es. Devuelve {'nombre', 'origen'} o None."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 1:
        return None
    juegos = biblioteca() if juegos is None else juegos
    cadena, p = [], pid
    for _ in range(14):
        if p <= 1:
            break
        cadena.append(p)
        p = _padre(proc, p)
    steam = {j["id"]: j for j in juegos if j["origen"] == "steam"}
    por_nombre = {comandos.normalizar(j["nombre"]): j for j in juegos}
    carpetas = [(j["carpeta"], j) for j in juegos if len(j.get("carpeta", "")) > 12]
    for p in cadena:
        cmd = _leer(f"{proc}/{p}/cmdline", binario=True).replace(b"\0", b" ").decode("utf-8", "ignore").strip()
        entorno = _leer(f"{proc}/{p}/environ", binario=True).decode("utf-8", "ignore").split("\0")
        for e in entorno:                                                  # Steam marca el entorno de sus juegos (también los de Proton)
            m = re.fullmatch(r"(?:SteamAppId|SteamGameId|STEAM_COMPAT_APP_ID)=(\d+)", e)
            if m and m.group(1) in steam:
                return {"nombre": steam[m.group(1)]["nombre"], "origen": "steam"}
        m = re.search(r"AppId=(\d+)", cmd)
        if m and m.group(1) in steam:
            return {"nombre": steam[m.group(1)]["nombre"], "origen": "steam"}
        m = re.match(r"lutris-wrapper:\s*(.+)$", cmd)                       # Lutris pone el nombre del juego como título de su proceso
        if m:
            nombre = m.group(1).strip()
            j = por_nombre.get(comandos.normalizar(nombre))
            return {"nombre": j["nombre"] if j else nombre, "origen": "lutris"}
        raiz = _leer_enlace(f"{proc}/{p}/cwd") + " " + _leer_enlace(f"{proc}/{p}/exe") + " " + cmd
        for carpeta, j in carpetas:
            if carpeta in raiz:
                return {"nombre": j["nombre"], "origen": j["origen"]}
    return None


def _leer_enlace(ruta):
    try:
        return os.readlink(ruta)
    except OSError:
        return ""
