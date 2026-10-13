#!/usr/bin/env python3
"""
Diagnóstico de Gemini: prueba cada modelo con texto solo, con búsqueda de Google y con imagen,
y muestra el motivo exacto de cada error (qué cuota, qué límite y cuánto esperar).

Uso:  python scripts/probar_gemini.py

Gasta como mucho 3 peticiones por modelo. Si el texto solo ya falla, no sigue con ese modelo.
"""
import base64
import io
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw

CLAVE = (Path.home() / ".config/lina/gemini.key").read_text().strip()
MODELOS = ["gemini-flash-latest", "gemini-flash-lite-latest"]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def imagen_prueba():
    img = Image.new("RGB", (320, 120), "white")
    ImageDraw.Draw(img).text((20, 50), "PRUEBA 123", fill="red")
    buffer = io.BytesIO()
    img.save(buffer, "JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def resumen_error(r):
    try:
        e = r.json()["error"]
    except (ValueError, KeyError, TypeError):
        return f"HTTP {r.status_code}: {r.text[:200]}"
    partes = [f"HTTP {e.get('code', r.status_code)} {e.get('status', '')}".strip()]
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


def probar(modelo, nombre, texto, imagen=None, busqueda=False):
    partes = [{"text": texto}]
    if imagen:
        partes.insert(0, {"inline_data": {"mime_type": "image/jpeg", "data": imagen}})
    cuerpo = {"contents": [{"role": "user", "parts": partes}]}
    if busqueda:
        cuerpo["tools"] = [{"google_search": {}}]
    inicio = time.time()
    try:
        r = requests.post(URL.format(modelo), headers={"x-goog-api-key": CLAVE}, json=cuerpo, timeout=40)
    except requests.RequestException as e:
        print(f"  {nombre:<28} SIN CONEXIÓN ({e})")
        return False
    segundos = time.time() - inicio
    if r.ok:
        print(f"  {nombre:<28} OK ({segundos:.1f} s)")
        return True
    print(f"  {nombre:<28} FALLA ({segundos:.1f} s): {resumen_error(r)}")
    return False


def main():
    imagen = imagen_prueba()
    for modelo in MODELOS:
        print(f"\n{modelo}")
        if not probar(modelo, "1) texto solo", "Responde solo con la palabra: hola"):
            print("  -> Falla incluso con texto solo: el problema es del modelo (saturación o cuota), no de lo que enviamos.")
            continue
        time.sleep(2)
        probar(modelo, "2) texto + búsqueda Google", "Responde en una frase: ¿qué es Skyrim?", busqueda=True)
        time.sleep(2)
        probar(modelo, "3) imagen + búsqueda Google", "Lee el texto de la imagen.", imagen=imagen, busqueda=True)
    print("\nCopia todo este resultado y pégalo en el chat.")


if __name__ == "__main__":
    main()
