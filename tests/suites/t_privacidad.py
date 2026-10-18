# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys, os, tempfile, pathlib
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa)
for m in ("sounddevice", "faster_whisper"): sys.modules[m] = MagicMock()
from lina.nucleo import ajustes as AJ, asistente as A, herramientas as H
f = 0
def ok(c, m):
    global f
    if not c: f += 1; print("FALLO:", m)
    else: print("OK ", m)

aj = AJ.actuales(log=lambda m: None)
a = A.Asistente.__new__(A.Asistente); a.modo_privado = False; a.titulo = "Konsole"; a.contexto = {"clase": "org.kde.konsole"}
ok("lina privacidad" in a._motivo_sin_pantalla(), "sin decidir: no se envía ninguna captura")
aj.establecer("privacidad", "capturas", "no")
ok(a._motivo_sin_pantalla() != "", "capturas = no: nunca")
aj.establecer("privacidad", "capturas", "si")
ok(a._motivo_sin_pantalla() == "", "capturas = si: se pueden enviar")
a.modo_privado = True
ok("privado" in a._motivo_sin_pantalla(), "…pero nunca en modo privado")
a.modo_privado = False
ok("sensible" in a._motivo_sin_pantalla("Banco Santander - Posición global", "firefox"), "…ni con ventanas sensibles")
ok("sensible" in a._motivo_sin_pantalla("Mis contraseñas — KeePassXC", "org.keepassxc.KeePassXC"), "…ni con el gestor de contraseñas")
a.paso_guion = 0; a.guion_herramientas = []; a.ejecutor = MagicMock(); a.pantalla_adjunta = False; a.captura_guardada = "x"
aj.establecer("privacidad", "capturas", "preguntar")
ok("permiso" in str(a._ejecutar_herramienta("ver_pantalla", {})), "ver_pantalla sin permiso lo explica")

# --- la IA necesita ver la pantalla y falta permiso: lo pide, y solo el atajo lo concede ---
aj.establecer("privacidad", "capturas", "preguntar")
a.ejecutor = H.Ejecutor(avisar=lambda *x, **k: None, confirmar=True); a.pregunta_pura = "¿qué ves en la pantalla?"
a.origen_voz_libre = False; a.pedir_pantalla = False; a.imagen_del_turno = "IMG"; a.captura_guardada = None
r = str(a._ejecutar_herramienta("ver_pantalla", {}))
ok(len(a.ejecutor.pendientes) == 1 and "NO describas" in r, "sin permiso: queda pendiente pedirlo y no describe nada")
ok(aj.get("privacidad", "capturas") == "preguntar", "…y todavía NO se ha concedido")
ok("capturas" in H.describir_pendientes(a.ejecutor.pendientes) and "Google" in H.describir_pendientes(a.ejecutor.pendientes), "…la descripción la escribe el código y dice adónde va")
res = a.ejecutor.confirmar_pendientes()
ok(aj.get("privacidad", "capturas") == "si" and a.pedir_pantalla and a.captura_guardada == "IMG", "al confirmar: permiso dado y captura lista para retomar lo pedido")
ok(a._motivo_sin_pantalla() == "", "…y el permiso rige")
# decirle «activa las capturas» explícitamente sigue el mismo camino (la IA no lo cambia sola)
aj.establecer("privacidad", "capturas", "preguntar"); a.ejecutor = H.Ejecutor(avisar=lambda *x, **k: None, confirmar=True); a.pedir_pantalla = False
r = str(a._ejecutar_herramienta("mis_ajustes", {"accion": "cambiar", "ajuste": "privacidad.capturas", "valor": "si"}))
ok(len(a.ejecutor.pendientes) == 1 and aj.get("privacidad", "capturas") == "preguntar", "mis_ajustes privacidad.capturas=si: solo lo deja pendiente")
# dijo NO: se respeta
aj.establecer("privacidad", "capturas", "no"); a.ejecutor = H.Ejecutor(avisar=lambda *x, **k: None, confirmar=True)
r = str(a._ejecutar_herramienta("ver_pantalla", {}))
ok(not a.ejecutor.pendientes and "NUNCA" in r, "con «no» no insiste ni lo propone")
# contenido de fuera en la tarea: no lo propone
aj.establecer("privacidad", "capturas", "preguntar"); a.ejecutor = H.Ejecutor(avisar=lambda *x, **k: None, confirmar=True); a.ejecutor.contaminado = "web"
r = str(a._ejecutar_herramienta("ver_pantalla", {}))
ok(not a.ejecutor.pendientes, "con contenido de fuera en la tarea no lo propone")
print("fallos", f); sys.exit(1 if f else 0)
