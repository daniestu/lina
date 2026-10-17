"""Hablar con una IA sin saber cuál es: el formato común y el registro de proveedores (fase 7).

Un proveedor traduce UNA petición de Lina a la API de su servicio y la respuesta de vuelta. Lo demás (el bucle de herramientas, los
reintentos, la espera de cuota, la cancelación, el plazo) está escrito una sola vez en `ia.py` y vale para todos.

Formato común de la conversación (lista de diccionarios):
  {"rol": "user" | "model", "texto": "...", "imagen": "<jpeg en base64>" (opcional)}      lo que dice cada uno
  {"rol": "model", "turno": <lo que devolvió el proveedor>}                                  el turno del modelo con llamadas, tal cual
  {"rol": "herramienta", "resultados": [{"nombre": "...", "texto": "...", "id": ...}]}        lo que devolvieron las herramientas pedidas
"""
from dataclasses import dataclass, field


@dataclass
class Llamada:
    nombre: str
    args: dict = field(default_factory=dict)
    id: str | None = None             # los proveedores que identifican cada llamada (OpenAI, Anthropic) la rellenan


@dataclass
class Respuesta:
    texto: str = ""
    llamadas: list = field(default_factory=list)
    uso: dict = field(default_factory=dict)       # con los nombres de Gemini (promptTokenCount…), que es lo que entiende presupuesto.py
    modelo_real: str | None = None
    turno: object = None                           # el turno del modelo tal como lo mandó el proveedor, para devolvérselo en la siguiente vuelta


@dataclass
class ErrorIA:
    tipo: str                                      # cuota | servidor | peticion | auth | red | vacia | otro
    estado: int | None = None                      # código HTTP, si lo hubo
    resumen: str = ""
    espera: float | None = None                    # segundos que el servicio pide esperar (solo si esperar sirve de algo)


SIN_CLAVE = "sin-clave"        # marcador para los servidores locales o de empresa que no piden clave (nunca se envía)


def tipo_de_estado(estado):
    if estado == 429:
        return "cuota"
    if estado in (500, 502, 503, 504, 529):            # 529: «sobrecargado» (Anthropic)
        return "servidor"
    if estado in (401, 403):
        return "auth"
    if estado in (400, 404, 413, 422):
        return "peticion"
    return "otro"


def contexto_desbordado(texto):
    """¿El error dice que lo enviado no cabe en la ventana de contexto del modelo? Cada servicio lo escribe a su manera
    («exceeds the available context size», «maximum context length», «prompt is too long»…)."""
    t = (texto or "").lower()
    if "prompt is too long" in t or "context window" in t:
        return True
    return "context" in t and any(p in t for p in ("exceed", "too long", "too large", "maximum", "overflow"))


class Proveedor:
    """Lo que tiene que hacer cada proveedor. `turno` devuelve una Respuesta o un ErrorIA; no lanza por fallos de red ni de la API."""
    nombre = ""
    busqueda_nativa = False            # ¿tiene una búsqueda web propia que se pueda activar en la petición?

    def turno(self, clave, modelo, sistema, mensajes, *, herramientas=None, nivel=None, busqueda_nativa=False, json_esquema=None,
              temperatura=None, max_salida=None, timeout=20, post=None):
        """json_esquema: None = texto libre; True = JSON; un dict = JSON con ese esquema. `nivel`: esfuerzo de razonamiento, si el modelo lo admite."""
        raise NotImplementedError

    def modelos(self, clave, get=None, timeout=15):
        """Los modelos que ofrece el servicio: (lista de nombres, '') o (None, motivo)."""
        return None, "este proveedor no sabe listar modelos"


_REGISTRO: dict = {}


def registrar(proveedor):
    _REGISTRO[proveedor.nombre] = proveedor
    return proveedor


def obtener(nombre):
    """El proveedor con ese nombre (Gemini si no existe o no se indica)."""
    return _REGISTRO.get(str(nombre or "").strip().lower()) or _REGISTRO["gemini"]


def nombres():
    return sorted(_REGISTRO)
