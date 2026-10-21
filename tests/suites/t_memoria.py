# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""La memoria de preferencias dentro del asistente: «recuerda que…» lo resuelve el código sin llamar a la IA, y la IA solo recibe lo pertinente."""
import sys, os, tempfile
from pathlib import Path
os.environ["HOME"] = tempfile.mkdtemp()
from unittest.mock import MagicMock
for m in ("sounddevice", "faster_whisper"):
    sys.modules[m] = MagicMock()
from lina.nucleo import asistente as A
from lina.nucleo import memoria as M

fallos = 0
def ok(c, m):
    global fallos
    if not c:
        fallos += 1; print("FALLO:", m)

M.ARCHIVO = Path(tempfile.mkdtemp()) / "memoria.json"
src = open(A.__file__, encoding="utf-8").read()
i = src.index("recuerdo = MEM.entender(pregunta)")
ok(i < src.index("accion = C.entender_alias(pregunta)") and i > src.index("orden_ml = ML.entender_orden"), "la memoria se resuelve en el código, antes de la IA")
ok("MEM.nota_para_la_ia(self.pregunta_pura)" in src and "AJ.actuales(log=lambda m: None).get(\"memoria\", \"usar\")" in src, "la IA recibe lo pertinente si el ajuste está activo")
ok(src.index("MEM.nota_para_la_ia") > src.index("pregunta_sin_receta = pregunta"), "los recuerdos no entran en el historial")
a = A.Asistente.__new__(A.Asistente)
dichas = []
a.decir = dichas.append
for frase in ("Recuerda que mi opción preferida para jugar es Proton-CachyOS", "qué recuerdas de mí", "olvida lo de Proton"):
    accion = M.entender(frase)
    a.decir(M.gestionar(accion))
ok("recordaré" in dichas[0] and "Proton" in dichas[1] and "olvidado" in dichas[2], f"flujo completo: {dichas}")
print("fallos", fallos)
sys.exit(1 if fallos else 0)
