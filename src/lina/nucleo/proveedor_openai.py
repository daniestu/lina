"""Proveedor «openai»: cualquier servicio con la API de chat de OpenAI (/chat/completions).

Sirve para OpenAI, OpenRouter, Groq, Mistral, DeepSeek… y para los servidores locales o de empresa que copian esa API (Ollama, LM Studio, llama.cpp,
vLLM): solo cambia la dirección base. En local la clave puede ir vacía.
"""
import json

import requests

from lina.nucleo import proveedores as P

URL_OPENAI = "https://api.openai.com/v1"


def esquema_json(valor):
    """El esquema de Lina (que escribe los tipos como los pide Gemini, «OBJECT», «STRING»…) en JSON Schema normal."""
    if isinstance(valor, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else esquema_json(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [esquema_json(v) for v in valor]
    return valor


def _mensajes(sistema, mensajes):
    salida = [{"role": "system", "content": sistema}]
    for m in mensajes:
        rol = m.get("rol")
        if rol == "herramienta":
            salida += [{"role": "tool", "tool_call_id": r.get("id") or r["nombre"], "content": r["texto"]} for r in m["resultados"]]
        elif "turno" in m:
            salida.append(m["turno"])
        else:
            texto = m.get("texto", "")
            if m.get("imagen"):
                contenido = [{"type": "text", "text": texto}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{m['imagen']}"}}]
            else:
                contenido = texto
            salida.append({"role": "assistant" if rol == "model" else "user", "content": contenido})
    return salida


def _argumentos(texto):
    try:
        datos = json.loads(texto) if texto else {}
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def _uso(u):
    if not isinstance(u, dict):
        return {}
    pensados = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    return {"promptTokenCount": u.get("prompt_tokens", 0), "candidatesTokenCount": max(0, (u.get("completion_tokens") or 0) - pensados),
            "thoughtsTokenCount": pensados, "cachedContentTokenCount": (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0}


def _espera(r):
    """Segundos que pide esperar el servicio (cabecera Retry-After), salvo si es que se acabó el saldo (esperar no lo arregla)."""
    try:
        if "insufficient_quota" in str(r.json().get("error", {}).get("code", "")):
            return None
    except (ValueError, AttributeError, TypeError):
        pass
    try:
        return float(r.headers.get("retry-after"))
    except (TypeError, ValueError, AttributeError):
        return None


def _resumen(r):
    try:
        e = r.json()["error"]
        return f"error {r.status_code} {e.get('type') or e.get('code') or ''}: {str(e.get('message', ''))[:200]}".replace(" :", ":")
    except (ValueError, KeyError, TypeError, AttributeError):
        return f"error {r.status_code}: {str(r.text)[:200]}"


class OpenAI(P.Proveedor):
    nombre = "openai"

    def __init__(self, url_base=URL_OPENAI, razonamiento=False):
        self.url_base = (url_base or URL_OPENAI).rstrip("/")
        self.razonamiento = razonamiento                # ¿enviar reasoning_effort? Solo lo admiten los modelos de razonamiento

    def turno(self, clave, modelo, sistema, mensajes, *, herramientas=None, nivel=None, busqueda_nativa=False, json_esquema=None,
              temperatura=None, max_salida=None, timeout=20, post=None):
        cuerpo = {"model": modelo, "messages": _mensajes(sistema, mensajes)}
        if herramientas:
            cuerpo["tools"] = [{"type": "function", "function": {"name": h["name"], "description": h.get("description", ""),
                                                                 "parameters": esquema_json(h.get("parameters") or {"type": "object", "properties": {}})}}
                               for h in herramientas]
        if temperatura is not None:
            cuerpo["temperature"] = temperatura
        if max_salida:
            cuerpo["max_tokens"] = max_salida
        if json_esquema:
            cuerpo["response_format"] = ({"type": "json_schema", "json_schema": {"name": "respuesta", "schema": esquema_json(json_esquema)}}
                                         if isinstance(json_esquema, dict) else {"type": "json_object"})
        if nivel and self.razonamiento:
            cuerpo["reasoning_effort"] = nivel
        cabeceras = {"Authorization": f"Bearer {clave}"} if clave else {}
        for _ in range(2):
            try:
                r = (post or requests.post)(f"{self.url_base}/chat/completions", headers=cabeceras, json=cuerpo, timeout=timeout)
            except requests.RequestException as e:
                return P.ErrorIA("red", None, str(e))
            if r.status_code == 400 and "max_tokens" in cuerpo and "max_completion_tokens" in str(r.text):
                cuerpo["max_completion_tokens"] = cuerpo.pop("max_tokens")           # los modelos nuevos de OpenAI usan este nombre
                continue
            break
        if not r.ok:
            return P.ErrorIA(P.tipo_de_estado(r.status_code), r.status_code, _resumen(r), _espera(r) if r.status_code == 429 else None)
        try:
            datos = r.json()
            mensaje = datos["choices"][0]["message"]
        except (KeyError, IndexError, ValueError, TypeError, AttributeError):
            return P.ErrorIA("vacia", r.status_code, "respuesta vacía o bloqueada")
        llamadas = [P.Llamada(c["function"].get("name", ""), _argumentos(c["function"].get("arguments")), c.get("id"))
                    for c in (mensaje.get("tool_calls") or []) if isinstance(c, dict) and isinstance(c.get("function"), dict)]
        texto = str(mensaje.get("content") or "").strip()
        if not texto and not llamadas:
            return P.ErrorIA("vacia", r.status_code, "respuesta vacía o bloqueada")
        turno = {"role": "assistant", "content": mensaje.get("content")}
        if llamadas:
            turno["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.nombre, "arguments": json.dumps(c.args, ensure_ascii=False)}}
                                   for c in llamadas]
        return P.Respuesta(texto, llamadas, _uso(datos.get("usage")), datos.get("model"), turno)


OPENAI = P.registrar(OpenAI())
