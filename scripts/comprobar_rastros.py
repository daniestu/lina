#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Comprueba que el repositorio no lleva secretos ni rastros personales.

Busca: claves de API, claves privadas, correos reales, rutas de carpetas personales (/home/<nombre>/…).
Además lee tus propias palabras prohibidas (nombre, apellidos, ciudad, nombre del equipo…) de:
  - el archivo `.rastros-local` de la raíz del repo (está en .gitignore: no se sube), una por línea, o
  - la variable de entorno LINA_RASTROS (separadas por comas).

Uso:  python scripts/comprobar_rastros.py            sale con código 1 si encuentra algo
"""
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
IGNORAR_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "build", "dist", ".casa-pruebas"}
IGNORAR_NOMBRES = {".rastros-local"}
EXT_BINARIAS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".pptx", ".xlsx", ".zip", ".gz", ".onnx", ".wav", ".mp3", ".pyc"}

PATRONES = [
    ("clave de API de Google", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("clave de API de Google (formato AQ.)", re.compile(r"\bAQ\.[0-9A-Za-z_\-]{30,}")),
    ("token de GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("clave tipo sk-", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("clave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
CORREO = re.compile(r"[\w.+\-]+@([\w\-]+\.)+[A-Za-z]{2,}")
CORREOS_OK = re.compile(r"(@example\.(com|org|net)$|@users\.noreply\.github\.com$|^git@github\.com$)", re.I)
HOME = re.compile(r"/home/([A-Za-z0-9_.\-]+)/")
HOME_OK = {"usuario", "user", "tu_usuario", "tuusuario", "nombre", "x", "ejemplo", "yo"}


def palabras_personales():
    pals = []
    f = RAIZ / ".rastros-local"
    if f.is_file():
        pals += [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    pals += [p.strip() for p in os.environ.get("LINA_RASTROS", "").split(",") if p.strip()]
    return [(p, re.compile(re.escape(p), re.I)) for p in pals]


def archivos():
    for dirpath, dirs, nombres in os.walk(RAIZ):
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIRS and not d.endswith(".egg-info")]
        for n in nombres:
            p = Path(dirpath) / n
            if p == Path(__file__).resolve() or n in IGNORAR_NOMBRES or p.suffix.lower() in EXT_BINARIAS:
                continue
            yield p


def revisar(raiz_archivos=None, personales=None):
    """[(archivo, nº de línea, motivo)]"""
    personales = palabras_personales() if personales is None else personales
    hallazgos = []
    for p in (raiz_archivos if raiz_archivos is not None else archivos()):
        try:
            texto = Path(p).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, linea in enumerate(texto.splitlines(), 1):
            for motivo, rx in PATRONES:
                if rx.search(linea):
                    hallazgos.append((p, n, motivo))
            for m in CORREO.finditer(linea):
                if not CORREOS_OK.search(m.group(0)):
                    hallazgos.append((p, n, f"correo real: {m.group(0)}"))
            for m in HOME.finditer(linea):
                if m.group(1) not in HOME_OK:
                    hallazgos.append((p, n, f"ruta personal: {m.group(0)}"))
            for palabra, rx in personales:
                if rx.search(linea):
                    hallazgos.append((p, n, f"palabra personal: {palabra}"))
    return hallazgos


def main():
    hallazgos = revisar()
    for p, n, motivo in hallazgos:
        print(f"{Path(p).relative_to(RAIZ)}:{n}: {motivo}")
    if hallazgos:
        print(f"\n{len(hallazgos)} hallazgo(s). Quítalos antes de subir nada.", file=sys.stderr)
        return 1
    print("Sin secretos ni rastros personales.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
