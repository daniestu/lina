"""Voces de Lina: cuál se usa por defecto, dónde se guardan y cómo se descargan la primera vez.

Las voces son modelos de Piper (https://github.com/rhasspy/piper). No viajan dentro del repositorio: Lina descarga la que necesita
a ~/.local/share/lina/voces/ y, si no hay internet, usa cualquier otra que ya tenga.

La voz que se usa se elige con el archivo ~/.config/lina/voz.txt (una línea con el nombre, por ejemplo es_ES-mls_10246-low).
"""
import os
import urllib.request
from pathlib import Path

from lina.nucleo import rutas as RUT

VOZ_POR_DEFECTO = "es_ES-mls_10246-low"

# Revisión fija del repositorio de voces, para que la descarga sea siempre el mismo archivo.
REVISION = "9df7583dc899c8f5ecaaebf1120a9fd1911e8009"
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/" + REVISION

# nombre -> carpeta dentro del repositorio de voces
CATALOGO = {
    "es_ES-mls_10246-low": "es/es_ES/mls_10246/low",
    "es_ES-mls_9972-low": "es/es_ES/mls_9972/low",
    "es_ES-davefx-medium": "es/es_ES/davefx/medium",
    "es_ES-carlfm-x_low": "es/es_ES/carlfm/x_low",
}
TIEMPO = 60
TROZO = 1 << 20


def voz_elegida(carpeta_config=None):
    """Nombre de la voz que el usuario ha puesto en voz.txt, o la de por defecto."""
    ruta = Path(carpeta_config or RUT.CONFIG) / "voz.txt"
    try:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.split("#", 1)[0].strip()
            if linea:
                return linea
    except OSError:
        pass
    return VOZ_POR_DEFECTO


def archivos(nombre, carpeta=None):
    base = Path(carpeta or RUT.VOCES)
    return base / f"{nombre}.onnx", base / f"{nombre}.onnx.json"


def instalada(nombre, carpeta=None):
    return all(p.is_file() and p.stat().st_size > 0 for p in archivos(nombre, carpeta))


def _descargar(url, destino, abrir):
    parcial = destino.with_name(destino.name + ".parcial")
    with abrir(url, TIEMPO) as r, open(parcial, "wb") as f:
        while True:
            trozo = r.read(TROZO)
            if not trozo:
                break
            f.write(trozo)
    if parcial.stat().st_size == 0:
        parcial.unlink(missing_ok=True)
        raise OSError("descarga vacía")
    os.replace(parcial, destino)


def _abrir(url, tiempo):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "lina"}), timeout=tiempo)


def asegurar(nombre, carpeta=None, log=print, abrir=_abrir):
    """Deja la voz lista. True si está disponible (ya estaba o se ha descargado), False si no ha podido."""
    if instalada(nombre, carpeta):
        return True
    sitio = CATALOGO.get(nombre)
    if sitio is None:
        log(f"Voz: «{nombre}» no está en el catálogo y no la tengo instalada.")
        return False
    base = Path(carpeta or RUT.VOCES)
    try:
        base.mkdir(parents=True, exist_ok=True)
        log(f"Voz: descargando {nombre} (la primera vez; unos 60 MB)…")
        for destino in reversed(archivos(nombre, base)):               # primero el pequeño (.json), luego el modelo
            _descargar(f"{BASE}/{sitio}/{destino.name}", destino, abrir)
    except (OSError, ValueError) as e:
        log(f"Voz: no he podido descargar {nombre} ({e}).")
        for p in base.glob(f"{nombre}.*.parcial"):
            p.unlink(missing_ok=True)
        return False
    log(f"Voz: {nombre} lista.")
    return True


def disponibles(carpeta=None):
    """Nombres de las voces que hay instaladas."""
    base = Path(carpeta or RUT.VOCES)
    return sorted(p.name[:-5] for p in base.glob("*.onnx") if (base / (p.name + ".json")).is_file()) if base.is_dir() else []


def preparar(log=print, carpeta=None, carpeta_config=None, abrir=_abrir):
    """La voz que hay que usar ahora: la elegida si se puede tener; si no, otra instalada; si no hay ninguna, None."""
    elegida = voz_elegida(carpeta_config)
    if asegurar(elegida, carpeta, log, abrir):
        return elegida
    otras = disponibles(carpeta)
    if otras:
        log(f"Voz: uso {otras[0]} mientras tanto.")
        return otras[0]
    return None
