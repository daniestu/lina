# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 12: las órdenes directas se hacen sin llamar a la IA, con las mismas herramientas; si no queda claro o falla, se las deja a la IA."""
import sys, time, os, tempfile, threading
os.environ["HOME"] = tempfile.mkdtemp()
from unittest.mock import MagicMock
for m in ("sounddevice", "faster_whisper"):
    sys.modules[m] = MagicMock()
from lina.nucleo import asistente as A
from lina.nucleo import herramientas as H
from lina.nucleo import tiempos as TIE

fallos = 0
def ok(c, m):
    global fallos
    if not c:
        fallos += 1; print("FALLO:", m)

class Ejec:
    """Un ejecutor falso: apunta lo que se le pide y devuelve lo que se le diga."""
    def __init__(self, abrir="Abierto «Firefox Web Browser». Ya está.", audio="código de salida: 0 (0 s)\n\nCOMPROBADO AHORA: Altavoces: Volume: 0.85"):
        self.pendientes, self.recetas_diferidas, self.continuar = [], [], "x"
        self.llamadas, self.abrir, self.audio, self.cancelado = [], abrir, audio, 0
        self.pregunta_pura, self.borrado_definitivo = "", True
    def abrir_app(self, nombre):
        self.llamadas.append(("abrir_app", nombre)); return self.abrir
    def sistema(self, nombre, args):
        self.llamadas.append((nombre, args)); return self.audio
    def herramienta(self, args):
        self.llamadas.append(("cmd", args["comando"])); return getattr(self, "cmd", "código de salida: 0 (0 s)\n\n")
    def cancelar(self, rechazar=False):
        self.cancelado += 1

def asistente(ej, activo=True):
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor, a.historial, a.interrumpiendo = ej, [], False
    a.hilo_captura = threading.Thread(target=lambda: None); a.hilo_captura.start()
    a.nueva_tarea = lambda: None
    a._continuar_peticion = lambda *x: True
    dichas = []
    a.decir = lambda t: dichas.append(t)
    a.dichas = dichas
    A.AJ.actuales = lambda log=None: _Aj(activo)
    return a

class _Aj:
    def __init__(self, activo): self.activo = activo
    def get(self, s, c):
        return {("directas", "activo"): self.activo, ("privacidad", "registrar_preguntas"): True, ("privacidad", "registrar_tiempos"): False}[(s, c)]

def pedir(a, frase):
    crono = TIE.Cronometro()
    r = a._intentar_directa(frase, crono)
    if r:
        a._cerrar_directa(frase, r[0], r[1], time.time(), crono)
    return r, crono

# ---- abrir un programa: lo hace con abrir_app y dice «Abierto.» (lo oído está dentro del nombre real)
ej = Ejec(); a = asistente(ej)
r, crono = pedir(a, "Abre Firefox.")
ok(r == ("Abierto.", "abrir_app") and ej.llamadas == [("abrir_app", "firefox")], f"abrir: {r} {ej.llamadas}")
ok(a.dichas == ["Abierto."] and a.historial[-1] == {"rol": "model", "texto": "Abierto."}, f"se dice y queda en el historial: {a.dichas} {a.historial}")
ok(ej.continuar == a._continuar_peticion or callable(ej.continuar), "se restablece el retomar tras la directa")
ok("herramientas" in crono.fases and "sintesis" in crono.fases, "se miden las fases")

# ---- si el programa abierto se llama distinto de lo oído, lo dice
ej = Ejec(abrir="Abierto «Navegador Brave»."); a = asistente(ej)
r, _ = pedir(a, "abre el explorador")
ok(r == ("Abierto Navegador Brave.", "abrir_app"), f"nombre distinto: {r}")

# ---- no instalado / varios que encajan / error: no es una directa, se la deja a la IA (y no se dice nada)
for texto in ("No hay ningún programa INSTALADO que encaje con «stremio»", "Hay varios programas que encajan con «x»: ...", "Intenté abrir «Y» con `y` y: fallo"):
    ej = Ejec(abrir=texto); a = asistente(ej)
    r, _ = pedir(a, "abre stremio")
    ok(r is None and not a.dichas and ej.cancelado == 1, f"se deja a la IA: {texto[:30]} -> {r} {a.dichas}")

# ---- volumen: la frase sale de lo que se lee DESPUÉS de tocarlo
ej = Ejec(); a = asistente(ej)
r, _ = pedir(a, "Sube el volumen.")
ok(r == ("Volumen al 85 %.", "volumen") and ej.llamadas == [("audio", {"accion": "subir"})], f"subir: {r} {ej.llamadas}")
ej = Ejec(); a = asistente(ej)
r, _ = pedir(a, "pon el volumen al 40")
ok(ej.llamadas == [("audio", {"accion": "volumen", "valor": "40"})], f"poner: {ej.llamadas}")
ej = Ejec(); a = asistente(ej)
r, _ = pedir(a, "silencia al sonido")
ok(r == ("Silenciado.", "silencio"), f"silenciar: {r}")
ej = Ejec(); a = asistente(ej)
r, _ = pedir(a, "quita el silencio")
ok(r == ("Sonido activado.", "silencio"), f"activar: {r}")

# ---- ventanas: sobre la ventana activa, con la herramienta de siempre; dice «Hecho.»
for frase, accion in (("Maximiza esta ventana.", "maximizar"), ("Pon esta ventana en pantalla completa.", "pantalla_completa"), ("minimiza esta ventana", "minimizar")):
    ej = Ejec(audio="código de salida: 0 (0 s)\n\nCOMPROBADO AHORA: Ahora: ventana «Konsole», es la activa"); a = asistente(ej)
    r, _ = pedir(a, frase)
    ok(r == ("Hecho.", "ventanas") and ej.llamadas == [("ventanas", {"accion": accion, "ventana": "activa"})], f"ventanas {accion}: {r} {ej.llamadas}")
ej = Ejec(audio="No sé cuál es la ventana activa ahora mismo."); a = asistente(ej)
r, _ = pedir(a, "maximiza esta ventana")
ok(r is None and ej.cancelado == 1 and not a.dichas, "ventanas: si no se puede, a la IA")

# ---- la hora y la fecha las dice el código: ni IA ni herramientas
ej = Ejec(); a = asistente(ej)
r, crono = pedir(a, "¿Qué hora es?")
ok(r and r[1] == "hora" and (r[0].startswith("Son las ") or r[0].startswith("Es la ")) and ej.llamadas == [], f"hora: {r} {ej.llamadas}")
r, _ = pedir(a, "¿Qué día es hoy?")
ok(r and r[0].startswith("Hoy es ") and ej.llamadas == [], f"fecha: {r}")

# ---- si el sistema pide confirmación, falla o no hay audio: a la IA, y lo preparado se descarta
for texto in (H.MENSAJE_PREPARADO, "código de salida: 1", "No hay audio"):
    ej = Ejec(audio="código de salida: 0 " + texto if texto == H.MENSAJE_PREPARADO else texto); a = asistente(ej)
    r, _ = pedir(a, "sube el volumen")
    ok(r is None and not a.dichas and ej.cancelado == 1, f"volumen no confirmado: {texto[:30]} -> {r}")

# ---- lo que NO es directa no toca nada
ej = Ejec(); a = asistente(ej)
for frase in ("abre Firefox y busca recetas", "no abras Firefox", "¿cómo subo el volumen?", "borra todo", "apaga el ordenador"):
    r, _ = pedir(a, frase)
    ok(r is None, f"no es directa: {frase}")
ok(ej.llamadas == [] and not a.dichas, f"no se ha llamado a nada: {ej.llamadas}")

# ---- desactivadas por el ajuste, o con algo pendiente de tu «sí»: nada
ej = Ejec(); a = asistente(ej, activo=False)
ok(pedir(a, "abre Firefox")[0] is None and ej.llamadas == [], "ajuste directas.activo = false")
ej = Ejec(); ej.pendientes = [{"comando": "x"}]; a = asistente(ej)
ok(pedir(a, "abre Firefox")[0] is None and ej.llamadas == [], "con algo pendiente de confirmar, lo decide el flujo normal")

# ---- un fallo inesperado nunca se queda sin respuesta: a la IA
class Roto(Ejec):
    def abrir_app(self, nombre):
        raise RuntimeError("boom")
ej = Roto(); a = asistente(ej)
ok(pedir(a, "abre Firefox")[0] is None, "excepción: se deja a la IA")

# ---- el revisor sobra cuando el código ya comprobó lo hecho
a = asistente(Ejec())
a.acciones_turno = [("abrir_app", {"nombre": "firefox"}, "Abierto «Firefox». Ya está")]
ok(a._acciones_comprobadas() is True, "abrir comprobado: sin revisor")
a.acciones_turno = [("audio", {"accion": "subir"}, "código de salida: 0 (0 s)\n\nCOMPROBADO AHORA: x: Volume: 0.5")]
ok(a._acciones_comprobadas() is True, "volumen leído: sin revisor")
a.acciones_turno = [("abrir_app", {}, "Abierto «F»."), ("ejecutar_comando", {"comando": "rm x"}, "código de salida: 0")]
ok(a._acciones_comprobadas() is False, "si hubo otra acción, sí hay revisor")
a.acciones_turno = [("procesos", {}, "...")]
ok(a._acciones_comprobadas() is False, "una lectura que la IA resume (RAM, CPU): sí hay revisor")
a.acciones_turno = []
ok(a._acciones_comprobadas() is False, "sin acciones: sí hay revisor")

# ---- con dos claves no se espera 20 s a la primera: se prueba con la otra a los 8 s (la última sí espera lo normal)
vistos = []
def falso_preguntar(proveedor, clave, modelo, *args, **kw):
    vistos.append((clave, kw.get("timeout")))
    return None if clave == "libre" else "respuesta"
A.preguntar_ia = falso_preguntar
b = A.Asistente.__new__(A.Asistente)
b._claves = lambda modo: ["libre", "pago"]
b.paso_guion = 0
ok(b._gemini("rapido", "m", "pregunta", None) == "respuesta" and vistos == [("libre", A.TIMEOUT_PRIMERA_CLAVE), ("pago", None)], f"timeouts por clave: {vistos}")
vistos.clear()
b._gemini("profundo", "m", "pregunta", None)
ok(vistos[0] == ("libre", None), f"a fondo: sin recortar: {vistos}")
vistos.clear()
b._claves = lambda modo: ["unica"]
b._gemini("rapido", "m", "pregunta", None)
ok(vistos == [("unica", None)], f"con una sola clave, sin recortar: {vistos}")

# ---- música: primero el reproductor que hable MPRIS (playerctl), comprobando el estado; si no hay, el mpv de Lina; si no, a la IA
class Musica(Ejec):
    def __init__(self, jugadores="spotify", estado="Paused"):
        super().__init__(); self.jugadores, self.estado = jugadores, estado
    def herramienta(self, args):
        c = args["comando"]; self.llamadas.append(("cmd", c))
        if c == "playerctl -l":
            return "código de salida: 0 (0 s)\n\n" + (self.jugadores or "(sin salida)")
        if c == "playerctl status":
            return "código de salida: 0 (0 s)\n\n" + self.estado
        return getattr(self, "cmd", "código de salida: 0 (0 s)\n\n")

for frase, sub, dicho, estado in (("pausa la música", "pause", "Pausado.", "Paused"), ("reanuda", "play", "Reanudado.", "Playing"),
                                  ("siguiente canción", "next", "Siguiente.", "Playing"), ("la anterior", "previous", "Anterior.", "Playing"),
                                  ("para la música", "stop", "Parada.", "Stopped")):
    ej = Musica(estado=estado); a = asistente(ej)
    r, _ = pedir(a, frase)
    ok(r == (dicho, "reproduccion") and ("cmd", f"playerctl {sub}") in ej.llamadas, f"reproducción {frase}: {r} {ej.llamadas}")
# la música de Lina (mpv con socket) va antes que cualquier otro reproductor compatible, como el navegador
enviados = []
A.REPRO.enviar_mpv = lambda accion: enviados.append(accion) or True
ej = Musica(jugadores="brave.instance1"); a = asistente(ej)
r, _ = pedir(a, "para la música")
ok(r == ("Parada.", "reproduccion") and enviados == ["detener"] and ej.llamadas == [], f"primero el mpv de Lina: {r} {enviados} {ej.llamadas}")
A.REPRO.enviar_mpv = lambda accion: False
# parar con playerctl y que siga sonando: no se da por hecho
ej = Musica(jugadores="brave.instance1", estado="Playing"); a = asistente(ej)
r, _ = pedir(a, "para la música")
ok(r is None and not a.dichas, f"playerctl stop pero sigue sonando: {r}")
# si el estado no queda como se pidió (el «hecho» de playerctl no vale), no se da por hecho
ej = Musica(estado="Playing"); a = asistente(ej)
r, _ = pedir(a, "pausa")
ok(r is None and not a.dichas, f"playerctl dijo hecho pero sigue sonando: {r}")
# sin ningún reproductor MPRIS ni mpv de Lina: a la IA (y no se dice que se ha parado)
import lina.nucleo.reproductor as RP
RP.ruta_mpv = lambda: "/no/existe.sock"
ej = Musica(jugadores=""); a = asistente(ej)
r, _ = pedir(a, "pausa la música")
ok(r is None and ej.cancelado == 1 and not a.dichas and not any(c[1] == "playerctl pause" for c in ej.llamadas), f"sin reproductor: {r} {ej.llamadas}")
# con el mpv de Lina (socket de control) se pausa sin playerctl
enviados = []
A.REPRO.enviar_mpv = lambda accion: enviados.append(accion) or True
ej = Musica(jugadores=""); a = asistente(ej)
r, _ = pedir(a, "pausa la música")
ok(r == ("Pausado.", "reproduccion") and enviados == ["pausar"], f"mpv de Lina: {r} {enviados}")
A.REPRO.enviar_mpv = lambda accion: False
for malo in ("código de salida: 1 (0 s)\n\nfallo", H.MENSAJE_PREPARADO):
    ej = Musica(); ej.cmd = malo; a = asistente(ej)
    r, _ = pedir(a, "siguiente")
    ok(r is None and not a.dichas, f"playerctl falla: {malo[:20]} -> {r}")
ej = Musica(); a = asistente(ej)
a.historial = [{"rol": "user", "texto": "pon música"}, {"rol": "model", "texto": "¿Quieres la lista de siempre o la nueva?"}]
r, _ = pedir(a, "la anterior")
ok(r is None and ej.llamadas == [], f"si Lina acaba de preguntar, «la anterior» es una respuesta: {r}")

print("fallos", fallos)
