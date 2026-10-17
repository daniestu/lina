"""Qué IA está en uso: el proveedor, sus modelos y su clave, según la sección [ia] de los ajustes (fase 7).

Si no se toca nada, es Gemini con los modelos de siempre. Los demás proveedores se activan con `lina ia usar …` o editando config.toml.
"""
from dataclasses import dataclass, field
from urllib.parse import urlparse

from lina.nucleo import ajustes as AJ
from lina.nucleo import claves as CL
from lina.nucleo import proveedor_anthropic as PAN
from lina.nucleo import proveedor_gemini as PG
from lina.nucleo import proveedor_openai as POA
from lina.nucleo import proveedores as P
from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import T
from lina.nucleo.constantes import MODELOS_CONFIRMACION, MODELOS_GEMINI, MODELOS_PROFUNDO

# Modelos recomendados por proveedor. Con «openai» no hay recomendación: depende del servicio (se piden con `lina ia modelos`).
RECOMENDADOS = {
    "gemini": {"rapido": MODELOS_GEMINI, "profundo": MODELOS_PROFUNDO, "mini": MODELOS_CONFIRMACION},
    "anthropic": {"rapido": ["claude-haiku-5-5"], "profundo": ["claude-sonnet-5-5"]},
    "openai": {},
}


@dataclass
class Activa:
    nombre: str
    proveedor: P.Proveedor
    url_base: str = ""
    rapido: list = field(default_factory=list)
    profundo: list = field(default_factory=list)
    mini: list = field(default_factory=list)

    @property
    def local(self):
        """Un servidor propio (Ollama, LM Studio, uno de empresa): no es OpenAI, así que puede no pedir clave."""
        return self.nombre == "openai" and bool(self.url_base) and urlparse(self.url_base).hostname != "api.openai.com"

    def servidor(self):
        """(host, puerto) al que se conecta Lina con este proveedor."""
        direccion = {"gemini": "https://generativelanguage.googleapis.com", "anthropic": "https://api.anthropic.com"}.get(self.nombre) or self.url_base or POA.URL_OPENAI
        u = urlparse(direccion)
        return u.hostname or "", u.port or (80 if u.scheme == "http" else 443)

    def clave(self):
        """La clave de este proveedor ('' si no hay). Los servidores locales sin clave devuelven el marcador SIN_CLAVE."""
        if self.nombre == "gemini":
            return CL.obtener("gemini") or ""
        return CL.obtener(self.nombre) or (P.SIN_CLAVE if self.local else "")

    def firma(self):
        """Lo que identifica a qué IA se habla: si cambia, la clave en uso ya no vale."""
        return (self.nombre, self.url_base)

    def listo(self):
        """(True, '') o (False, qué falta)."""
        if not self.rapido:
            return False, T("falta indicar el modelo: `lina ia usar {nombre} --modelo NOMBRE` (los que ofrece el servicio: `lina ia modelos`)", nombre=self.nombre)
        if not self.clave():
            return False, T("falta la clave: `lina clave {nombre}`", nombre=self.nombre)
        return True, ""


def claves_de(ia):
    """(gratuita, de pago) de esta IA. Solo Gemini tiene dos y control de euros; los demás, una sola clave y se cuentan tokens."""
    if ia.nombre == "gemini":
        return CL.obtener("gemini"), CL.obtener("gemini_pago")
    return ia.clave(), ""


_cache: dict = {"marca": None, "aj": None}


def _lector():
    """Los ajustes, releídos solo si config.toml ha cambiado (esto se consulta en cada pregunta)."""
    ruta = RUT.CONFIG / AJ.NOMBRE_ARCHIVO
    try:
        marca = (str(ruta), ruta.stat().st_mtime_ns)
    except OSError:
        marca = (str(ruta), None)
    if _cache["marca"] != marca:
        _cache["marca"], _cache["aj"] = marca, AJ.solo_lectura()
    return _cache["aj"]


LECTOR = _lector


def actual(leer=None):
    """La IA activa según los ajustes (`leer` devuelve los ajustes; en las pruebas se pasa uno falso)."""
    aj = (leer or LECTOR)()
    nombre = str(aj.get("ia", "proveedor") or "gemini")
    if nombre not in P.nombres():
        nombre = "gemini"
    url = str(aj.get("ia", "url_base") or "").strip()
    rapido, profundo = str(aj.get("ia", "modelo_rapido") or "").strip(), str(aj.get("ia", "modelo_profundo") or "").strip()
    rec = RECOMENDADOS.get(nombre, {})
    lista_rapido = [rapido] if rapido else list(rec.get("rapido", []))
    lista_profundo = [profundo] if profundo else list(rec.get("profundo") or lista_rapido)
    lista_mini = [rapido] if rapido else list(rec.get("mini") or lista_rapido)
    if nombre == "openai":
        proveedor = POA.OpenAI(url or POA.URL_OPENAI, bool(aj.get("ia", "razonamiento")))
    else:
        proveedor = P.obtener(nombre)
    return Activa(nombre, proveedor, url, lista_rapido, lista_profundo, lista_mini)


def modelos(modo, leer=None):
    """Los modelos a probar, por orden: «rapido», «profundo» o «mini» (confirmaciones y resúmenes)."""
    a = actual(leer)
    return list(getattr(a, modo))


__all__ = ["Activa", "actual", "modelos", "RECOMENDADOS", "PG", "PAN"]
