"""Voces de Lina: cuáles hay, cuál se usa, dónde se guardan y cómo se descargan la primera vez.

Las voces son modelos de Piper (https://github.com/rhasspy/piper). No viajan dentro del repositorio: Lina descarga la que necesita
a ~/.local/share/lina/voces/ y, si no hay internet, usa cualquier otra que ya tenga.

La voz que se usa se elige con `lina voz NOMBRE` (se guarda en config.toml, sección [voz]).
El catálogo está organizado por idioma para poder añadir otros más adelante.
"""
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

from lina.nucleo import ajustes as AJ
from lina.nucleo import rutas as RUT

IDIOMA = "es"

# Revisión fija del repositorio de voces, para que la descarga sea siempre el mismo archivo.
REVISION = "9df7583dc899c8f5ecaaebf1120a9fd1911e8009"
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/" + REVISION

# idioma -> nombre de la voz -> {modelo de Piper, carpeta en el repositorio de voces, hablante (si el modelo tiene varios), descripción}
CATALOGO = {
    "es": {
        "es_MX-claude-high": {"modelo": "es_MX-claude-high", "carpeta": "es/es_MX/claude/high", "locutor": None,
                              "descripcion": "Claude · México · calidad alta · femenina (por defecto)"},
        "es_ES-davefx-medium": {"modelo": "es_ES-davefx-medium", "carpeta": "es/es_ES/davefx/medium", "locutor": None,
                                "descripcion": "Dave · España · calidad media · masculina"},
        "es_ES-sharvard-medium-1": {"modelo": "es_ES-sharvard-medium", "carpeta": "es/es_ES/sharvard/medium", "locutor": 0,
                                    "descripcion": "Sharvard, hablante 1 · España · calidad media"},
        "es_ES-sharvard-medium-2": {"modelo": "es_ES-sharvard-medium", "carpeta": "es/es_ES/sharvard/medium", "locutor": 1,
                                    "descripcion": "Sharvard, hablante 2 · España · calidad media"},
    },
}
VOZ_POR_DEFECTO = "es_MX-claude-high"
TIEMPO = 60
TROZO = 1 << 20


def entrada(nombre):
    """La ficha del catálogo de esa voz, o None si no es una voz del catálogo."""
    for voces in CATALOGO.values():
        if nombre in voces:
            return voces[nombre]
    return None


def modelo(nombre):
    """Nombre del modelo de Piper (los archivos .onnx). Una voz que no esté en el catálogo se toma como nombre de modelo ya instalado."""
    ficha = entrada(nombre)
    return ficha["modelo"] if ficha else nombre


def locutor(nombre):
    """Número de hablante para los modelos con varios, o None."""
    ficha = entrada(nombre)
    return ficha["locutor"] if ficha else None


def voz_elegida(carpeta_config=None):
    """Nombre de la voz elegida en config.toml ([voz]) o, si se da una carpeta suelta (pruebas), en su voz.txt; si no hay, la de por defecto."""
    if carpeta_config is None:
        return AJ.actuales(log=lambda m: None).get("voz", "voz")
    ruta = Path(carpeta_config or RUT.CONFIG) / "voz.txt"
    try:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.split("#", 1)[0].strip()
            if linea:
                return linea
    except OSError:
        pass
    return VOZ_POR_DEFECTO


def fijar(nombre, carpeta_config=None):
    """Guarda la voz elegida (en config.toml, o en un voz.txt suelto si se da una carpeta)."""
    if carpeta_config is None:
        AJ.actuales(log=lambda m: None).establecer("voz", "voz", nombre)
        return
    base = Path(carpeta_config or RUT.CONFIG)
    base.mkdir(parents=True, exist_ok=True)
    (base / "voz.txt").write_text(nombre + "\n", encoding="utf-8")


def archivos(nombre, carpeta=None):
    base = Path(carpeta or RUT.VOCES)
    return base / f"{modelo(nombre)}.onnx", base / f"{modelo(nombre)}.onnx.json"


def instalada(nombre, carpeta=None):
    return all(p.is_file() and p.stat().st_size > 0 for p in archivos(nombre, carpeta))


def _descargar(url, destino, abrir, sha256=None):
    """Baja un archivo a `destino` comprobando que llega entero: tamaño igual al que anuncia el servidor, JSON válido si es un .json y, si el
    catálogo trae la huella (sha256), que coincida. Devuelve la huella del archivo."""
    parcial = destino.with_name(destino.name + ".parcial")
    suma, total = hashlib.sha256(), 0
    with abrir(url, TIEMPO) as r, open(parcial, "wb") as f:
        anunciado = getattr(getattr(r, "headers", None), "get", lambda *_: None)("Content-Length")
        while True:
            trozo = r.read(TROZO)
            if not trozo:
                break
            f.write(trozo)
            suma.update(trozo)
            total += len(trozo)
    try:
        if total == 0:
            raise OSError("descarga vacía")
        if anunciado and str(anunciado).isdigit() and int(anunciado) != total:
            raise OSError(f"descarga incompleta ({total} de {anunciado} bytes)")
        if destino.suffix == ".json":
            json.loads(parcial.read_text(encoding="utf-8"))
        if sha256 and suma.hexdigest() != sha256.lower():
            raise OSError("la huella no coincide con la del catálogo")
    except (OSError, ValueError) as e:
        parcial.unlink(missing_ok=True)
        raise OSError(str(e)) from e
    os.replace(parcial, destino)
    return suma.hexdigest()


def _abrir(url, tiempo):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "lina"}), timeout=tiempo)


def asegurar(nombre, carpeta=None, log=print, abrir=_abrir):
    """Deja la voz lista. True si está disponible (ya estaba o se ha descargado), False si no ha podido."""
    if instalada(nombre, carpeta):
        return True
    ficha = entrada(nombre)
    if ficha is None:
        log(f"Voz: «{nombre}» no está en el catálogo y no la tengo instalada. Mira las disponibles con:  lina voz")
        return False
    base = Path(carpeta or RUT.VOCES)
    try:
        base.mkdir(parents=True, exist_ok=True)
        log(f"Voz: descargando {nombre} (la primera vez; unos 60 MB)…")
        huellas = _leer_huellas(base)
        for destino in reversed(archivos(nombre, base)):               # primero el pequeño (.json), luego el modelo
            huellas[destino.name] = _descargar(f"{BASE}/{ficha['carpeta']}/{destino.name}", destino, abrir, (ficha.get("sha256") or {}).get(destino.suffix))
        _guardar_huellas(base, huellas)
    except (OSError, ValueError) as e:
        log(f"Voz: no he podido descargar {nombre} ({e}).")
        for p in base.glob(f"{ficha['modelo']}.*.parcial"):
            p.unlink(missing_ok=True)
        return False
    log(f"Voz: {nombre} lista.")
    return True


def _leer_huellas(base):
    try:
        d = json.loads((Path(base) / "huellas.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_huellas(base, huellas):
    try:
        (Path(base) / "huellas.json").write_text(json.dumps(huellas, indent=1, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def verificar(nombre, carpeta=None):
    """(estado, detalle) de una voz instalada: True si sus archivos son los que se descargaron, False si cambiaron o faltan, None si no hay huella guardada."""
    base = Path(carpeta or RUT.VOCES)
    if not instalada(nombre, carpeta):
        return False, "no está instalada"
    huellas = _leer_huellas(base)
    sin_huella = True
    for destino in archivos(nombre, base):
        esperada = huellas.get(destino.name)
        if not esperada:
            continue
        sin_huella = False
        suma = hashlib.sha256()
        with open(destino, "rb") as f:
            for trozo in iter(lambda: f.read(TROZO), b""):
                suma.update(trozo)
        if suma.hexdigest() != esperada:
            return False, f"{destino.name} no es el que se descargó (¿corrupto?): bórralo y vuelve a elegir la voz"
    return (None, "sin huella guardada (se instaló antes de que se guardaran)") if sin_huella else (True, "íntegra")


def disponibles(carpeta=None):
    """Nombres de los modelos que hay instalados."""
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


def principal(argv, carpeta=None, carpeta_config=None, abrir=_abrir, salida=print):
    """lina voz            lista las voces y marca la que se usa
    lina voz NOMBRE     elige esa voz (la descarga ahora si hace falta)"""
    actual = voz_elegida(carpeta_config)
    if not argv:
        salida("Voces disponibles (la marcada con * es la que se usa; «instalada» = ya descargada):")
        for nombre, ficha in CATALOGO[IDIOMA].items():
            marca = "*" if nombre == actual else " "
            estado = "instalada" if instalada(nombre, carpeta) else "se descarga al elegirla"
            salida(f" {marca} {nombre:26} {ficha['descripcion']}  [{estado}]")
        salida("\nElige una con:  lina voz NOMBRE   (después reinicia a Lina: systemctl --user restart lina)")
        return 0
    nombre = argv[0]
    if nombre not in CATALOGO[IDIOMA]:
        salida(f"No conozco la voz «{nombre}». Mira las que hay con:  lina voz")
        return 2
    if not asegurar(nombre, carpeta, salida, abrir):
        return 1
    fijar(nombre, carpeta_config)
    salida(f"Voz elegida: {nombre}. Reinicia a Lina para oírla:  systemctl --user restart lina")
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
