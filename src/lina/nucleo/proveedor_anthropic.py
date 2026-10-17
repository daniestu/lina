"""Proveedor «anthropic»: la API de mensajes de Anthropic (/v1/messages)."""
import json

import requests

from lina.nucleo import proveedores as P
from lina.nucleo.proveedor_openai import esquema_json

URL = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"
SALIDA_POR_DEFECTO = 4096                      # la API exige un máximo de tokens de salida


def _bloques(m):
    bloques = []
    if m.get("imagen"):
        bloques.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": m["imagen"]}})
    if m.get("texto"):                           # la API rechaza los bloques de texto vacíos
        bloques.append({"type": "text", "text": m["texto"]})
    return bloques


def _mensajes(mensajes):
    salida = []
    for m in mensajes:
        rol = m.get("rol")
        if rol == "herramienta":
            salida.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": r.get("id") or r["nombre"], "content": r["texto"]}
                                                       for r in m["resultados"]]})
        elif "turno" in m:
            salida.append(m["turno"])
        else:
            bloques = _bloques(m)
            if bloques:
                salida.append({"role": "assistant" if rol == "model" else "user", "content": bloques})
    return salida


def _uso(u):
    if not isinstance(u, dict):
        return {}
    leidos = u.get("cache_read_input_tokens") or 0
    return {"promptTokenCount": (u.get("input_tokens") or 0) + leidos + (u.get("cache_creation_input_tokens") or 0),
            "candidatesTokenCount": u.get("output_tokens") or 0, "thoughtsTokenCount": 0, "cachedContentTokenCount": leidos}


def _resumen(r):
    try:
        e = r.json()["error"]
        return f"error {r.status_code} {e.get('type', '')}: {str(e.get('message', ''))[:200]}"
    except (ValueError, KeyError, TypeError, AttributeError):
        return f"error {r.status_code}: {str(r.text)[:200]}"


def _espera(r):
    try:
        return float(r.headers.get("retry-after"))
    except (TypeError, ValueError, AttributeError):
        return None


class Anthropic(P.Proveedor):
    nombre = "anthropic"

    def modelos(self, clave, get=None, timeout=15):
        try:
            r = (get or requests.get)("https://api.anthropic.com/v1/models?limit=100", headers={"x-api-key": clave, "anthropic-version": VERSION}, timeout=timeout)
            if not r.ok:
                return None, _resumen(r)
            return sorted(str(m["id"]) for m in r.json()["data"]), ""
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as e:
            return None, f"no he podido consultarlo ({e})"

    def turno(self, clave, modelo, sistema, mensajes, *, herramientas=None, nivel=None, busqueda_nativa=False, json_esquema=None,
              temperatura=None, max_salida=None, timeout=20, post=None):
        if json_esquema:                           # no hay modo JSON en la petición: se pide en las instrucciones (quien llama ya limpia ```json … ```)
            sistema += ("\n\nResponde SOLO con un objeto JSON válido, sin texto antes ni después"
                        + (f", que cumpla este esquema: {json.dumps(esquema_json(json_esquema), ensure_ascii=False)}" if isinstance(json_esquema, dict) else "") + ".")
        cuerpo = {"model": modelo, "max_tokens": max_salida or SALIDA_POR_DEFECTO, "system": sistema, "messages": _mensajes(mensajes)}
        if herramientas:
            cuerpo["tools"] = [{"name": h["name"], "description": h.get("description", ""),
                                "input_schema": esquema_json(h.get("parameters") or {"type": "object", "properties": {}})} for h in herramientas]
        if temperatura is not None:
            cuerpo["temperature"] = temperatura
        cabeceras = {"x-api-key": clave, "anthropic-version": VERSION, "content-type": "application/json"}
        try:
            r = (post or requests.post)(URL, headers=cabeceras, json=cuerpo, timeout=timeout)
        except requests.RequestException as e:
            return P.ErrorIA("red", None, str(e))
        if not r.ok:
            return P.ErrorIA(P.tipo_de_estado(r.status_code), r.status_code, _resumen(r), _espera(r) if r.status_code == 429 else None)
        try:
            datos = r.json()
            contenido = list(datos["content"])
        except (KeyError, ValueError, TypeError, AttributeError):
            return P.ErrorIA("vacia", r.status_code, "respuesta vacía o bloqueada")
        llamadas = [P.Llamada(b.get("name", ""), b.get("input") if isinstance(b.get("input"), dict) else {}, b.get("id"))
                    for b in contenido if isinstance(b, dict) and b.get("type") == "tool_use"]
        texto = " ".join(b.get("text", "") for b in contenido if isinstance(b, dict) and b.get("type") == "text").strip()
        if not texto and not llamadas:
            return P.ErrorIA("vacia", r.status_code, "respuesta vacía o bloqueada")
        return P.Respuesta(texto, llamadas, _uso(datos.get("usage")), datos.get("model"), {"role": "assistant", "content": contenido})


ANTHROPIC = P.registrar(Anthropic())
