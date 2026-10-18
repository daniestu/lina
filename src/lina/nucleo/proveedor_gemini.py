# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Proveedor Gemini (Google): la API generateContent."""
import re

import requests

from lina.nucleo import proveedores as P

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


def espera_de_cuota(r):
    """Segundos que Google pide esperar, SOLO si el límite agotado es el de por minuto (el diario no se arregla esperando)."""
    try:
        detalles = r.json()["error"].get("details", [])
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    por_minuto, espera = False, None
    for d in detalles:
        tipo = d.get("@type", "")
        if tipo.endswith("QuotaFailure"):
            por_minuto = por_minuto or any("perminute" in str(v.get("quotaId", "")).lower() for v in d.get("violations", []))
        elif tipo.endswith("RetryInfo"):
            m = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(d.get("retryDelay", "")).strip())
            espera = float(m.group(1)) if m else None
    return espera if por_minuto else None


def resumen_error(r):
    """Resume el error de Gemini en una línea, incluyendo qué cuota se ha agotado y cuándo reintentar."""
    try:
        e = r.json()["error"]
    except (ValueError, KeyError, TypeError):
        return f"error {r.status_code}: {r.text[:200]}"
    partes = [f"error {e.get('code', r.status_code)} {e.get('status', '')}".strip()]
    for d in e.get("details", []):
        tipo = d.get("@type", "")
        if tipo.endswith("QuotaFailure"):
            for v in d.get("violations", []):
                partes.append(f"cuota={v.get('quotaId') or v.get('quotaMetric', '?')} "
                              f"límite={v.get('quotaValue', '?')}")
        elif tipo.endswith("RetryInfo"):
            partes.append(f"reintentar en {d.get('retryDelay', '?')}")
    if len(partes) == 1:
        partes.append(str(e.get("message", ""))[:200])
    return " | ".join(partes)


def _contenidos(mensajes):
    salida = []
    for m in mensajes:
        rol = m.get("rol")
        if rol == "herramienta":
            partes = [{"functionResponse": {"name": r["nombre"], "response": {"resultado": r["texto"]}}} for r in m["resultados"]]
            salida.append({"role": "user", "parts": partes})
        elif "turno" in m:
            salida.append(m["turno"])                       # el turno del modelo con su firma interna, que Gemini 3 exige recibir de vuelta
        else:
            partes = [{"text": m.get("texto", "")}]
            if m.get("imagen"):
                partes.insert(0, {"inline_data": {"mime_type": "image/jpeg", "data": m["imagen"]}})
            salida.append({"role": rol, "parts": partes})
    return salida


class Gemini(P.Proveedor):
    nombre = "gemini"
    busqueda_nativa = True

    def modelos(self, clave, get=None, timeout=15):
        try:
            r = (get or requests.get)("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": clave}, timeout=timeout)
            if not r.ok:
                return None, resumen_error(r)
            datos = r.json().get("models", [])
        except (requests.RequestException, ValueError, AttributeError) as e:
            return None, f"no he podido consultarlo ({e})"
        return sorted(m["name"].split("/", 1)[-1] for m in datos if "generateContent" in m.get("supportedGenerationMethods", [])), ""

    def turno(self, clave, modelo, sistema, mensajes, *, herramientas=None, nivel=None, busqueda_nativa=False, json_esquema=None,
              temperatura=None, max_salida=None, timeout=20, post=None):
        cuerpo = {"system_instruction": {"parts": [{"text": sistema}]}, "contents": _contenidos(mensajes)}
        config = {}
        if temperatura is not None:
            config["temperature"] = temperatura
        if max_salida:
            config["maxOutputTokens"] = max_salida
        if json_esquema:
            config["responseMimeType"] = "application/json"
            if isinstance(json_esquema, dict):
                config["responseSchema"] = json_esquema
        if nivel:
            config["thinkingConfig"] = {"thinkingLevel": nivel}
        if config:
            cuerpo["generationConfig"] = config
        if busqueda_nativa:
            cuerpo["tools"] = [{"google_search": {}}]                 # la búsqueda de Google dentro de Gemini (cuenta de pago)
        elif herramientas:
            cuerpo["tools"] = [{"functionDeclarations": herramientas}]    # Gemini decide qué herramienta pedirnos
        try:
            r = (post or requests.post)(URL.format(modelo=modelo), headers={"x-goog-api-key": clave}, json=cuerpo, timeout=timeout)
        except requests.RequestException as e:
            return P.ErrorIA("red", None, str(e))
        if not r.ok:
            return P.ErrorIA(P.tipo_de_estado(r.status_code), r.status_code, resumen_error(r), espera_de_cuota(r) if r.status_code == 429 else None)
        try:
            datos = r.json()
            contenido = dict(datos["candidates"][0]["content"])
            partes = contenido.get("parts", [])
        except (KeyError, IndexError, ValueError, TypeError, AttributeError):
            return P.ErrorIA("vacia", r.status_code, "respuesta vacía o bloqueada")
        contenido.setdefault("role", "model")
        llamadas = [P.Llamada(p["functionCall"].get("name", ""), p["functionCall"].get("args") or {}) for p in partes if "functionCall" in p]
        texto = " ".join(p.get("text", "") for p in partes if not p.get("thought")).strip()
        return P.Respuesta(texto, llamadas, datos.get("usageMetadata") or {}, datos.get("modelVersion"), contenido)


GEMINI = P.registrar(Gemini())
