# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""La captura de pantalla que «sigue» una ayuda no se alarga sola: cada pregunta no relacionada (la hora, una receta) no debe mandarla a la IA para siempre."""
import sys, time, os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from unittest.mock import MagicMock
for m in ("sounddevice", "faster_whisper"):
    sys.modules[m] = MagicMock()
from lina.nucleo import asistente as A

fallos = 0
def ok(c, m):
    global fallos
    if not c:
        fallos += 1; print("FALLO:", m)

a = A.Asistente.__new__(A.Asistente)
a.contexto = {"tipo": "general"}
a._motivo_sin_pantalla = lambda: None
IMG = object()

# se habla de lo que se ve: se envía y se abre la ventana de ayuda
ok(a._decidir_pantalla(IMG, "Maximiza esta ventana") is IMG, "se envía al hablar de lo que ves")
t0 = a.ultima_pantalla_t
ok(t0 > 0, "se apunta cuándo")

# preguntas seguidas dentro de la ventana: se sigue enviando, pero SIN renovar el plazo
ok(a._decidir_pantalla(IMG, "¿Qué hora es?") is IMG, "dentro de la ventana, se sigue enviando")
ok(a.ultima_pantalla_t == t0, "seguir la ayuda no la alarga")

# pasada la ventana: ya no se envía, por muchas preguntas que hayan ido seguidas
a.ultima_pantalla_t = time.time() - A.PANTALLA_SESION_SEG - 1
ok(a._decidir_pantalla(IMG, "Dime una receta de tortilla") is None, "pasada la ventana, no se envía")

# una pregunta que pide mirar la vuelve a abrir
ok(a._decidir_pantalla(IMG, "Mira mi pantalla y dime qué ventanas tengo") is IMG and a.ultima_pantalla_t > t0, "mirar la renueva")

# en un juego, siempre
a.contexto = {"tipo": "juego"}
a.ultima_pantalla_t = 0.0
ok(a._decidir_pantalla(IMG, "¿Qué hora es?") is IMG, "en un juego, siempre")

print("fallos", fallos)
