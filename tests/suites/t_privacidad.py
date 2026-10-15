import sys, os, tempfile, pathlib
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa)
for m in ("sounddevice", "faster_whisper"): sys.modules[m] = MagicMock()
from lina.nucleo import ajustes as AJ, asistente as A
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
print("fallos", f); sys.exit(1 if f else 0)
