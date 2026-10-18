# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El idioma de Lina (fase 8): cuál está activo y cómo se traducen los textos que el usuario lee u oye.

El código y sus textos están en español. Un texto que el usuario ve u oye se escribe igual que siempre pero envuelto en `T("…")`:

    avisar(T("Ya no tengo conexión con {servicio}", servicio="Gemini"))

La clave de la traducción es el propio texto en español. Si el idioma activo es el español, o a ese texto le falta traducción, sale tal cual:
nunca hay huecos ni claves a medias. Las traducciones viven en `datos/idiomas/<código>.toml`, una línea por texto:

    "Lista para usar" = "Ready to use"

Los huecos `{nombre}` tienen que ser los mismos en el texto y en su traducción (`comprobar` lo vigila). Una llave literal se escribe `{{` y `}}`.
Si una traducción está mal escrita (le falta un hueco, por ejemplo), no rompe nada: sale el texto en español.
"""
import string
import tomllib

from lina.nucleo import ajustes as AJ
from lina.nucleo import rutas as RUT

IDIOMAS = AJ.IDIOMAS          # los que se pueden elegir
POR_DEFECTO = "es"
CARPETA = RUT.DEFECTOS / "idiomas"

_cache_ajustes: dict = {"marca": None, "aj": None}
_catalogos: dict = {}


def _lector():
    """Los ajustes, releídos solo si config.toml ha cambiado (el idioma se consulta en cada texto)."""
    ruta = RUT.CONFIG / AJ.NOMBRE_ARCHIVO
    try:
        marca = (str(ruta), ruta.stat().st_mtime_ns)
    except OSError:
        marca = (str(ruta), None)
    if _cache_ajustes["marca"] != marca:
        _cache_ajustes["marca"], _cache_ajustes["aj"] = marca, AJ.solo_lectura()
    return _cache_ajustes["aj"]


LECTOR = _lector


def actual(leer=None):
    """El código del idioma activo según los ajustes (`leer` devuelve los ajustes; en las pruebas se pasa uno falso)."""
    try:
        codigo = str((leer or LECTOR)().get("asistente", "idioma") or POR_DEFECTO).strip().lower()
    except Exception:                                  # un config.toml roto no puede dejar a Lina muda
        return POR_DEFECTO
    return codigo if codigo in IDIOMAS else POR_DEFECTO


def segun(tabla):
    """El valor de una tabla {idioma: valor} para el idioma activo. Si no tiene el suyo, el del español (siempre debe tenerlo)."""
    codigo = actual()
    return tabla[codigo] if codigo in tabla else tabla[POR_DEFECTO]


class PorIdioma:
    """Un patrón (o un conjunto) que cambia con el idioma: se usa igual que el objeto de `re` o la colección que sustituye (`.search`, `.match`, `in`)."""

    def __init__(self, tabla):
        self.tabla = tabla

    def _actual(self):
        return segun(self.tabla)

    def search(self, *a, **k):
        return self._actual().search(*a, **k)

    def match(self, *a, **k):
        return self._actual().match(*a, **k)

    def __contains__(self, x):
        return x in self._actual()


def catalogo(codigo):
    """Las traducciones de un idioma ({texto en español: traducción}). El español no necesita catálogo."""
    if codigo == POR_DEFECTO:
        return {}
    if codigo not in _catalogos:
        try:
            with open(CARPETA / f"{codigo}.toml", "rb") as f:
                datos = tomllib.load(f)
            _catalogos[codigo] = {str(k): str(v) for k, v in datos.items() if str(v).strip()}
        except (OSError, tomllib.TOMLDecodeError):
            _catalogos[codigo] = {}
    return _catalogos[codigo]


def N_(texto):
    """Marca un texto para traducir sin traducirlo todavía (constantes que se definen al importar): se usa luego con `T(CONSTANTE)`."""
    return texto


def _rellenar(plantilla, datos):
    return plantilla.format(**datos) if datos else plantilla


def T(texto, /, **datos):
    """El texto en el idioma activo, con sus huecos rellenos. Sin traducción (o con una mal escrita), el texto en español."""
    traducido = catalogo(actual()).get(texto, texto)
    try:
        return _rellenar(traducido, datos)
    except (KeyError, IndexError, ValueError):
        return _rellenar(texto, datos)


def _huecos(plantilla):
    return {nombre for _, nombre, _, _ in string.Formatter().parse(plantilla) if nombre is not None}


def comprobar(codigo):
    """Lo que está mal en el catálogo de un idioma (lista vacía = bien): huecos que no coinciden o llaves sin cerrar."""
    problemas = []
    for original, traduccion in catalogo(codigo).items():
        try:
            if _huecos(original) != _huecos(traduccion):
                problemas.append(f"«{original}»: los huecos no coinciden ({sorted(_huecos(original))} frente a {sorted(_huecos(traduccion))})")
        except ValueError as e:
            problemas.append(f"«{original}»: {e}")
    return problemas
