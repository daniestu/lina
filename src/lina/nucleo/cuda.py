# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Las librerías de NVIDIA (cuBLAS y cuDNN) que faster-whisper necesita para usar la tarjeta gráfica.

Vienen como paquetes de pip (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) y se instalan en el propio entorno de Lina, sin tocar el sistema. Como el sistema
solo mira `LD_LIBRARY_PATH` al arrancar el proceso, se cargan a mano antes de crear el modelo."""
import ctypes
import glob
import importlib.util
import os
import shutil
import subprocess
import sys

PAQUETES = ["nvidia-cublas-cu12", "nvidia-cudnn-cu12"]
_LIBRERIAS = [("nvidia.cublas", "libcublasLt.so.*"), ("nvidia.cublas", "libcublas.so.*"), ("nvidia.cudnn", "libcudnn.so.*")]


def hay_nvidia():
    return bool(shutil.which("nvidia-smi"))


def _carpeta(paquete):
    try:
        spec = importlib.util.find_spec(paquete)
    except (ImportError, ValueError):
        return None
    ubicaciones = list(getattr(spec, "submodule_search_locations", None) or []) if spec else []
    return os.path.join(ubicaciones[0], "lib") if ubicaciones else None


def instaladas():
    return all(_carpeta(p) and glob.glob(os.path.join(_carpeta(p), patron)) for p, patron in _LIBRERIAS)


def cargar_librerias():
    """Carga las librerías de NVIDIA del entorno de Lina. True si había que cargarlas y se cargaron todas."""
    if not instaladas():
        return False
    try:
        for paquete, patron in _LIBRERIAS:
            ctypes.CDLL(sorted(glob.glob(os.path.join(_carpeta(paquete), patron)))[0], mode=ctypes.RTLD_GLOBAL)
    except OSError:
        return False
    return True


def instalar(salida=print, ejecutar=subprocess.run):
    """pip install de las librerías en el entorno de Lina (unos 700 MB). True si queda todo."""
    r = ejecutar([sys.executable, "-m", "pip", "install", "--quiet", *PAQUETES], capture_output=True, text=True)
    if r.returncode != 0:
        salida((r.stderr or r.stdout or "").strip().splitlines()[-1][:200] if (r.stderr or r.stdout) else "pip falló")
        return False
    return instaladas()
