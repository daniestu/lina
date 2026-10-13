"""C2: notas en Markdown en ~/Documentos/Notas, con búsqueda. Una nota = un archivo .md (también se encuentran los .md y .txt que pongas tú a mano).

Seguridad: el nombre del archivo sale solo del título (letras, números y guiones), nunca se sale de la carpeta de notas, nunca se sobrescribe una nota
por crear, y borrar la manda a la papelera. Lo que hay dentro de una nota es información guardada, no órdenes.
"""
import difflib
import os
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path
from lina.nucleo import rutas as RUT

CARPETA = RUT.carpeta_usuario("DOCUMENTS", "Documents") / "Notas"
MAX_NOTA = 60_000          # caracteres por nota
MAX_ARCHIVOS = 3000        # lo máximo que se mira al buscar
MAX_LEER = 4000            # lo que se devuelve a la IA al leer una nota entera
EXTENSIONES = {".md", ".txt"}
_PARAR = {"de", "la", "el", "los", "las", "un", "una", "unos", "unas", "que", "en", "y", "a", "mi", "mis", "me", "con", "por", "para", "del", "al",
          "nota", "notas", "sobre", "lo", "se", "es", "tengo", "tenia", "dime", "busca", "buscame", "donde", "apunte", "apuntes", "apuntado"}


def _plano(texto):
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _palabras(texto):
    return [p for p in re.findall(r"[a-z0-9ñ]{2,}", _plano(texto)) if p not in _PARAR]


def slug(titulo):
    s = re.sub(r"[^a-z0-9]+", "-", _plano(titulo)).strip("-")[:60].strip("-")
    return s or "nota"


def _dentro(ruta):
    """La ruta (ya resuelta) está de verdad dentro de la carpeta de notas."""
    try:
        return Path(ruta).resolve().is_relative_to(CARPETA.resolve())
    except (OSError, ValueError):
        return False


def _archivos():
    if not CARPETA.is_dir():
        return []
    salida = []
    base = CARPETA.resolve()
    for raiz, dirs, ficheros in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if Path(raiz).relative_to(base).parts[1:]:                 # como mucho una subcarpeta
            dirs[:] = []
        for nombre in ficheros:
            p = Path(raiz) / nombre
            if p.suffix.lower() in EXTENSIONES and not p.is_symlink() and _dentro(p):
                salida.append(p)
                if len(salida) >= MAX_ARCHIVOS:
                    return salida
    return salida


def _leer_texto(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:MAX_NOTA]
    except OSError:
        return ""


def titulo_de(p, texto=None):
    texto = texto if texto is not None else _leer_texto(p)
    for linea in texto.splitlines()[:5]:
        if linea.startswith("# "):
            return linea[2:].strip()[:100]
    return p.stem.replace("-", " ").replace("_", " ")


def _fecha(p):
    try:
        return datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        return datetime.fromtimestamp(0)


def _escribir(ruta, texto):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, ruta)


def crear(titulo, texto, etiquetas="", ahora=None):
    """(ruta, mensaje_de_error). No sobrescribe: si ya existe una nota con ese título, error."""
    titulo = " ".join(str(titulo or "").split())[:100]
    texto = str(texto or "").strip()
    if not titulo:
        if not texto:
            return None, "Falta el título o el texto de la nota."
        titulo = " ".join(texto.split()[:6])[:60]
    if len(texto) > MAX_NOTA:
        return None, "La nota es demasiado larga."
    CARPETA.mkdir(parents=True, exist_ok=True)
    ruta = CARPETA / f"{slug(titulo)}.md"
    if not _dentro(ruta) or ruta.is_symlink():
        return None, "Ese nombre no es válido."
    if ruta.exists():
        return None, f"Ya existe una nota llamada «{titulo_de(ruta)}». Añade lo nuevo con la acción añadir, o elige otro título."
    ahora = ahora or datetime.now()
    cabecera = f"# {titulo}\n\n_Creada el {ahora:%Y-%m-%d %H:%M}_" + (f" · Etiquetas: {etiquetas.strip()[:100]}" if str(etiquetas).strip() else "")
    _escribir(ruta, cabecera + ("\n\n" + texto if texto else "") + "\n")
    return ruta, ""


def _puntos_titulo(consulta, p, texto=None):
    q = _plano(consulta).strip()
    nombre = _plano(titulo_de(p, texto)) + " " + _plano(p.stem)
    pal = _palabras(consulta)
    if not pal:
        return 0.0
    cubiertas = sum(1 for w in pal if w[:5] in nombre)
    ratio = difflib.SequenceMatcher(None, q, _plano(titulo_de(p, texto))).ratio()
    return cubiertas / len(pal) * 0.7 + ratio * 0.3 + (0.3 if q and q in nombre else 0)


def encontrar(referencia):
    """(ruta, mensaje). Busca UNA nota por su título aproximado; si hay varias parecidas, las lista."""
    puntuadas = []
    for p in _archivos():
        pts = _puntos_titulo(referencia, p)
        if pts >= 0.45:
            puntuadas.append((pts, p))
    if not puntuadas:
        return None, f"No encuentro ninguna nota con el título «{str(referencia)[:60]}». Prueba a buscar por palabras del contenido."
    puntuadas.sort(key=lambda x: (-x[0], -_fecha(x[1]).timestamp()))
    if len(puntuadas) > 1 and puntuadas[0][0] - puntuadas[1][0] < 0.12 and puntuadas[1][0] >= 0.6:
        return None, "Hay varias notas parecidas: " + "; ".join(f"«{titulo_de(p)}»" for _, p in puntuadas[:4]) + ". Pregúntale cuál."
    return puntuadas[0][1], ""


def anadir(referencia, texto, ahora=None):
    """Añade una línea o párrafo al final de una nota que ya existe. (ruta, mensaje_de_error)."""
    texto = str(texto or "").strip()
    if not texto:
        return None, "Falta qué añadir."
    p, error = encontrar(referencia)
    if not p:
        return None, error
    actual = _leer_texto(p).rstrip("\n")
    if len(actual) + len(texto) > MAX_NOTA:
        return None, "La nota ya es demasiado larga para añadir más."
    ultima = next((l for l in reversed(actual.splitlines()) if l.strip()), "")
    es_lista = bool(re.match(r"\s*([-*]|\d+[.)])\s", ultima))
    lineas = [l for l in texto.splitlines() if l.strip()]
    if es_lista:
        lineas = [l if re.match(r"\s*([-*]|\d+[.)])\s", l) else f"- {l.strip()}" for l in lineas]
        nuevo = actual + "\n" + "\n".join(lineas) + "\n"
    else:
        nuevo = actual + "\n\n" + "\n".join(lineas) + "\n"
    _escribir(p, nuevo)
    return p, ""


def leer(referencia):
    """(titulo, texto, ruta, error)."""
    p, error = encontrar(referencia)
    if not p:
        return None, None, None, error
    texto = _leer_texto(p)
    return titulo_de(p, texto), texto, p, ""


def listar(cuantas=10):
    """[(titulo, fecha, ruta)] las más recientes primero."""
    notas = sorted(_archivos(), key=lambda p: -_fecha(p).timestamp())[:cuantas]
    return [(titulo_de(p), _fecha(p), p) for p in notas]


def _fragmento(texto, palabras, ancho=90):
    plano = _plano(texto)
    i = min((plano.find(w) for w in palabras if plano.find(w) >= 0), default=-1)
    if i < 0:
        return ""
    ini = max(0, i - ancho // 2)
    frag = texto[ini:ini + ancho + 40].replace("\n", " ")
    return ("…" if ini else "") + " ".join(frag.split()) + "…"


def buscar(consulta, maximo=5):
    """[(puntos, titulo, fecha, fragmento, ruta)] de las notas que contienen las palabras (todas primero; si no, la mayoría)."""
    pal = _palabras(consulta)
    if not pal:
        return []
    raices = [w[:6] if len(w) > 6 else w for w in pal]
    resultados = []
    for p in _archivos():
        texto = _leer_texto(p)
        plano = _plano(texto)
        titulo = _plano(titulo_de(p, texto)) + " " + _plano(p.stem)
        en_titulo = sum(1 for r in raices if r in titulo)
        en_texto = sum(1 for r in raices if r in plano)
        if not en_texto and not en_titulo:
            continue
        cubiertas = max(en_texto, en_titulo)
        if cubiertas < max(1, (len(raices) + 1) // 2):
            continue
        puntos = cubiertas * 10 + en_titulo * 5 + (10 if cubiertas == len(raices) else 0) + min(5, sum(plano.count(r) for r in raices) / 3)
        resultados.append((puntos, titulo_de(p, texto), _fecha(p), _fragmento(texto, raices), p))
    resultados.sort(key=lambda x: (-x[0], -x[2].timestamp()))
    return resultados[:maximo]


def borrar(referencia):
    """Manda una nota a la papelera. (titulo, error)."""
    p, error = encontrar(referencia)
    if not p:
        return None, error
    titulo = titulo_de(p)
    if not shutil.which("gio"):
        return None, "No puedo mandarla a la papelera (falta gio): no la borro."
    try:
        r = subprocess.run(["gio", "trash", str(p)], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None, "No he podido mandar la nota a la papelera."
    if r.returncode != 0 or p.exists():
        return None, "No he podido mandar la nota a la papelera."
    return titulo, ""
