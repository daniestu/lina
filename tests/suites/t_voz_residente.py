# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 12: al hablar, primero la caché, luego el Piper residente, y si no hay o falla, un Piper por frase como siempre."""
import sys, os, tempfile, subprocess
os.environ["HOME"] = tempfile.mkdtemp()
from unittest.mock import MagicMock
for m in ("sounddevice", "faster_whisper"):
    sys.modules[m] = MagicMock()
from lina.nucleo import asistente as A
from lina.nucleo import ajustes as AJ

fallos = 0
def ok(c, m):
    global fallos
    if not c:
        fallos += 1; print("FALLO:", m)

class Residente:
    def __init__(self, resultado): self.resultado, self.pedidos = resultado, []
    def sintetizar(self, modelo, carpeta, locutor, escala, texto, salida):
        self.pedidos.append((texto, escala)); return self.resultado

lanzados, reproducidos = [], []
def run(orden, **kw):
    lanzados.append(orden); return MagicMock()
class Reproductor:
    def __init__(self, orden): reproducidos.append(orden)
    def wait(self): pass
subprocess.run = run
A.subprocess.Popen = Reproductor

def hablar(texto, residente, activo=True, velocidad=1.0):
    lanzados.clear(); reproducidos.clear()
    A._residente[:] = [residente]
    antes = AJ.actuales
    AJ.actuales = lambda log=None: type("C", (), {"get": lambda self, s, c: {("voz", "residente"): activo, ("voz", "velocidad"): velocidad}.get((s, c), True)})()
    a = A.Asistente.__new__(A.Asistente)
    try:
        a._hablar(texto)
    finally:
        AJ.actuales = antes

r = Residente(True)
hablar("Esto es una frase de prueba bastante larga para no entrar en la caché de frases cortas", r)
ok(len(r.pedidos) == 1 and r.pedidos[0][1] is None and lanzados == [] and len(reproducidos) == 1, f"con residente no se lanza Piper: {r.pedidos} {lanzados}")
r = Residente(True)
hablar("Esto es una frase de prueba bastante larga para no entrar en la caché de frases cortas", r, velocidad=1.25)
ok(r.pedidos and abs(r.pedidos[0][1] - 0.8) < 1e-9, f"la velocidad pasa a escala de Piper (1/velocidad): {r.pedidos}")
r = Residente(False)
hablar("Esto es una frase de prueba bastante larga para no entrar en la caché de frases cortas", r)
ok(len(r.pedidos) == 1 and len(lanzados) == 1 and "piper" in lanzados[0] and len(reproducidos) == 1, f"si el residente falla, un Piper por frase: {lanzados}")
r = Residente(True)
hablar("Esto es una frase de prueba bastante larga para no entrar en la caché de frases cortas", r, activo=False)
ok(r.pedidos == [] and len(lanzados) == 1, f"voz.residente = false: como siempre: {r.pedidos} {lanzados}")

print("fallos", fallos)
sys.exit(1 if fallos else 0)
