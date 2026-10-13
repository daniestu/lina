#!/usr/bin/env python3
"""
Diario de cambios del asistente: qué cambió, cuándo, con qué comando y cómo deshacerlo.

Aquí solo se guarda y se lee (las entradas, las copias de los archivos tal como estaban antes y su restauración). La lógica
de qué anotar y cómo deshacerlo está en herramientas.py. No depende de audio ni de IA, para poder probarlo por separado.

Todo vive en ~/.local/share/lina/diario/ (solo legible por ti):
  diario.jsonl      una línea por cambio; para marcar algo como deshecho se añade una línea de actualización (nunca se reescribe)
  respaldos/<id>/   copias de los archivos que el asistente iba a modificar, tal como estaban
El asistente no puede tocar esta carpeta desde la terminal (herramientas.py la protege), para que nadie pueda reescribir el
diario y hacer que «deshacer» restaure otra cosa.
"""
import json
import os
import shutil
import stat
import subprocess
import time
import uuid
from pathlib import Path
from lina.nucleo import rutas as RUT

DIR = RUT.DATOS / "diario"
MAX_ENTRADAS = 300          # se conservan las últimas
DIAS_RESPALDOS = 30         # las copias de archivos más antiguas se borran
MAX_RESPALDOS_MB = 500      # tope total de copias


def _archivo():
    return DIR / "diario.jsonl"


def _carpeta_respaldos():
    return DIR / "respaldos"


def _privilegios():
    return [] if os.geteuid() == 0 else ["sudo", "-n"]


def nuevo_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def _preparar_dir():
    DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DIR, 0o700)
    except OSError:
        pass


def _escribir_linea(obj):
    _preparar_dir()
    nuevo = not _archivo().exists()
    with _archivo().open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    if nuevo:
        try:
            os.chmod(_archivo(), 0o600)
        except OSError:
            pass


def anotar(entrada):
    """Guarda una entrada nueva y la devuelve (con su id y su fecha)."""
    entrada = dict(entrada)
    entrada.setdefault("id", nuevo_id())
    entrada.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
    entrada.setdefault("t", time.time())
    _escribir_linea(entrada)
    return entrada


def marcar(id_entrada, **campos):
    """Cambia campos de una entrada (por ejemplo deshecho=True) añadiendo una línea de actualización."""
    _escribir_linea({"id": id_entrada, "_actualiza": True, **campos})


def listar(n=None):
    """Las entradas, la más reciente primero, con las actualizaciones ya aplicadas."""
    entradas, orden = {}, []
    try:
        lineas = _archivo().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for linea in lineas:
        try:
            obj = json.loads(linea)
        except ValueError:
            continue                                      # una línea rota no tumba el diario
        if not isinstance(obj, dict) or "id" not in obj:
            continue
        if obj.get("_actualiza"):
            if obj["id"] in entradas:
                entradas[obj["id"]].update({k: v for k, v in obj.items() if k not in ("_actualiza", "id")})
        else:
            if obj["id"] not in entradas:
                orden.append(obj["id"])
            entradas[obj["id"]] = obj
    resultado = [entradas[i] for i in reversed(orden)]
    return resultado[:n] if n else resultado


def obtener(referencia):
    """Una entrada por su id exacto o por un trozo único de él (los últimos caracteres sirven)."""
    referencia = str(referencia or "").strip()
    if not referencia:
        return None
    todas = listar()
    exactas = [e for e in todas if e["id"] == referencia]
    if exactas:
        return exactas[0]
    parecidas = [e for e in todas if referencia in e["id"]]
    return parecidas[0] if len(parecidas) == 1 else None


# ------------------------- copias de los archivos -------------------------
def respaldo_valido(ruta):
    """¿Esta ruta está de verdad dentro de la carpeta de copias? (el diario nunca restaura desde otro sitio)"""
    try:
        return Path(os.path.realpath(ruta)).is_relative_to(os.path.realpath(_carpeta_respaldos()))
    except (OSError, ValueError):
        return False


def guardar_respaldo(id_entrada, ruta, limite_mb=20):
    """Copia el archivo tal como está ahora. Devuelve (ruta de la copia, "") o (None, motivo si no se pudo)."""
    ruta = Path(ruta)
    try:
        st = ruta.lstat()
    except OSError:
        return None, "no existe"
    if stat.S_ISLNK(st.st_mode):
        return None, "es un enlace"
    if not stat.S_ISREG(st.st_mode):
        return None, "no es un archivo normal"
    if st.st_size > limite_mb * 1024 * 1024:
        return None, f"pesa más de {limite_mb} MB"
    carpeta = _carpeta_respaldos() / id_entrada
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        os.chmod(carpeta, 0o700)
    except OSError as e:
        return None, f"no puedo crear la carpeta de copias ({e})"
    destino = carpeta / f"{len(list(carpeta.iterdir()))}_{ruta.name}"
    try:
        shutil.copy2(ruta, destino)
    except PermissionError:                               # un archivo solo legible por root: se copia con sudo
        try:
            r = subprocess.run([*_privilegios(), "cp", "--preserve=timestamps", "--", str(ruta), str(destino)],
                               capture_output=True, timeout=30)
            if r.returncode != 0:
                return None, "no tengo permiso para leerlo"
            if os.geteuid() != 0:
                subprocess.run([*_privilegios(), "chown", f"{os.getuid()}:{os.getgid()}", "--", str(destino)],
                               capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None, "no tengo permiso para leerlo"
    except OSError as e:
        return None, str(e)
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass
    return str(destino), ""


def restaurar_respaldo(respaldo, destino, modo=None, uid=None, gid=None):
    """Devuelve la copia a su sitio (con sudo si hace falta). Devuelve (ok, mensaje)."""
    if not respaldo_valido(respaldo) or not Path(respaldo).is_file():
        return False, "la copia de seguridad ya no existe"
    destino = Path(destino)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_name(destino.name + ".lina-tmp")
        shutil.copyfile(respaldo, temporal)
        if modo is not None:
            os.chmod(temporal, modo & 0o777)
        os.replace(temporal, destino)
        if (uid is not None and uid != os.getuid()) or (gid is not None and gid != os.getgid()):
            os.chown(destino, uid if uid is not None else -1, gid if gid is not None else -1)
        return True, ""
    except PermissionError:
        pass                                              # el sitio es de root: se hace con sudo
    except OSError as e:
        return False, str(e)
    orden = [*_privilegios(), "install"]
    if modo is not None:
        orden += ["-m", format(modo & 0o777, "o")]
    if uid is not None and uid != os.getuid():
        orden += ["-o", str(uid)]
    if gid is not None and gid != os.getgid():
        orden += ["-g", str(gid)]
    try:
        r = subprocess.run([*orden, "--", str(respaldo), str(destino)], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if r.returncode != 0:
        return False, (r.stderr.strip().splitlines() or ["no he podido restaurarlo"])[0]
    return True, ""


# ------------------------- limpieza -------------------------
def _tamano(carpeta):
    total = 0
    for base, _, archivos in os.walk(carpeta):
        for a in archivos:
            try:
                total += os.lstat(os.path.join(base, a)).st_size
            except OSError:
                pass
    return total


def limpiar(max_entradas=None, dias=None, max_mb=None):
    """Conserva las últimas entradas y borra las copias antiguas o las que sobren del tope. Devuelve cuántas carpetas borró."""
    max_entradas = max_entradas or MAX_ENTRADAS
    dias = DIAS_RESPALDOS if dias is None else dias
    max_mb = max_mb or MAX_RESPALDOS_MB
    todas = listar()
    conservar = todas[:max_entradas]
    if len(todas) > max_entradas:                         # se reescribe el archivo solo con las últimas, ya fusionadas
        _preparar_dir()
        temporal = _archivo().with_name("diario.jsonl.tmp")
        with temporal.open("w", encoding="utf-8") as f:
            for e in reversed(conservar):
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.chmod(temporal, 0o600)
        os.replace(temporal, _archivo())
    vivas = {e["id"] for e in conservar}
    borradas = 0
    carpeta = _carpeta_respaldos()
    if not carpeta.is_dir():
        return 0
    limite_t = time.time() - dias * 86400
    candidatas = []
    for sub in carpeta.iterdir():
        if not sub.is_dir():
            continue
        try:
            t = sub.stat().st_mtime
        except OSError:
            continue
        if sub.name not in vivas or t < limite_t:
            shutil.rmtree(sub, ignore_errors=True)
            borradas += 1
        else:
            candidatas.append((t, sub))
    candidatas.sort()                                      # si aún pesan demasiado, caen las más antiguas
    while candidatas and _tamano(carpeta) > max_mb * 1024 * 1024:
        _, sub = candidatas.pop(0)
        shutil.rmtree(sub, ignore_errors=True)
        borradas += 1
    return borradas
