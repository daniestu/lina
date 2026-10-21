# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Una petición que espera a una tarea en segundo plano (instalar y luego abrir) se retoma SOLA al terminar: no se queda en el paso previo."""
import sys, time, os, tempfile, threading
os.environ["HOME"] = tempfile.mkdtemp()
from types import SimpleNamespace
from unittest.mock import MagicMock
for m in ("sounddevice", "faster_whisper"):
    sys.modules[m] = MagicMock()
from lina.nucleo import asistente as A
from lina.nucleo import herramientas as H

fallos = 0
def ok(c, m):
    global fallos
    if not c:
        fallos += 1; print("FALLO:", m)

class Proc:
    def __init__(self, rc=0):
        self.returncode = rc
    def communicate(self, timeout=None):
        return ("hecho", None)

def ejecutor(continuar):
    avisos = []
    e = H.Ejecutor(avisar=lambda t: avisos.append(t), confirmar=True)
    e.continuar = continuar
    return e, avisos

# ---- al terminar bien: se retoma la petición original y NO se da el aviso de «ya ha terminado»
llamadas = []
e, avisos = ejecutor(lambda p, m, n, r: llamadas.append((p, m, n, r)) or True)
e._vigilar(Proc(0), "flatpak install -y flathub com.stremio.Stremio", "instalar Stremio", None, "Abre Stremio", 0)
ok(llamadas == [("Abre Stremio", "instalar Stremio", 0, False)] and not avisos, f"retoma y no avisa: {llamadas} {avisos}")

# ---- si nadie se hace cargo (ocupada mucho rato), el aviso de siempre
e, avisos = ejecutor(lambda p, m, n, r: False)
e._vigilar(Proc(0), "flatpak install -y flathub com.stremio.Stremio", "instalar Stremio", None, "Abre Stremio", 0)
ok(len(avisos) == 1 and "Ya ha terminado" in avisos[0], f"sin retomar, avisa: {avisos}")

# ---- si falla el retomar (excepción), también avisa
def roto(*a):
    raise RuntimeError("x")
e, avisos = ejecutor(roto)
e._vigilar(Proc(0), "flatpak install -y x", "instalar x", None, "Abre x", 0)
ok(len(avisos) == 1 and "Ya ha terminado" in avisos[0], f"excepción: avisa: {avisos}")

# ---- si la tarea falla, no se retoma nada: se avisa del fallo
llamadas = []
e, avisos = ejecutor(lambda *a: llamadas.append(a) or True)
e._vigilar(Proc(1), "flatpak install -y x", "instalar x", None, "Abre x", 0)
ok(not llamadas and len(avisos) == 1 and "fallado" in avisos[0], f"fallo: no retoma: {llamadas} {avisos}")

# ---- sin petición asociada (o sin retomar): como siempre
llamadas = []
e, avisos = ejecutor(lambda *a: llamadas.append(a) or True)
e._vigilar(Proc(0), "pacman -Syu", "actualizar", None, "", 0)
ok(not llamadas and "Ya ha terminado" in avisos[0], "sin petición: aviso normal")
e, avisos = ejecutor(None)
e._vigilar(Proc(0), "pacman -Syu", "actualizar", None, "actualiza el sistema", 0)
ok("Ya ha terminado" in avisos[0], "sin retomar: aviso normal")

# ---- una actualización completa pasa «reiniciar» para que lo diga la vuelta que retoma
llamadas = []
e, avisos = ejecutor(lambda p, m, n, r: llamadas.append(r) or True)
e._vigilar(Proc(0), "sudo -n pacman -Syu --noconfirm", "actualizar el sistema", None, "actualiza el sistema", 0)
ok(llamadas == [True], f"actualización completa: reiniciar=True {llamadas}")

# ---- el asistente: se hace cargo cuando está libre, con la petición original y una nota, y cuenta las vueltas
def falso_asistente(estado):
    a = A.Asistente.__new__(A.Asistente)
    a.cerrojo, a.estado, a.interrumpiendo, a.fin_tarea = threading.RLock(), estado, True, threading.Event()
    a.fin_tarea.set()
    lanzadas = []
    a._tarea = lambda *args: lanzadas.append(args)
    a._atender = lambda *args: None
    return a, lanzadas

a, lanzadas = falso_asistente("esperando")
hecho = a._continuar_peticion("Abre Stremio", "instalar Stremio", 0, False)
time.sleep(0.2)
ok(hecho is True and a.estado == "pensando" and not a.interrumpiendo and not a.fin_tarea.is_set(), "toma el estado")
ok(len(lanzadas) == 1, f"lanza una tarea: {lanzadas}")
if lanzadas:
    f, pregunta, _, crono, nota, profundidad = lanzadas[0]
    ok(pregunta == "Abre Stremio" and crono is None and profundidad == 1, "retoma la petición original, una vuelta más")
    ok("YA HA TERMINADO" in nota and "instalar Stremio" in nota and "reiniciar" not in nota, "la nota dice qué terminó")

a, lanzadas = falso_asistente("esperando")
a._continuar_peticion("actualiza", "actualizar", 0, True)
time.sleep(0.2)
ok(lanzadas and "reiniciar" in lanzadas[0][4], "actualización completa: la nota pide recomendar reiniciar")

# ---- tope de vueltas: no da vueltas sin fin
a, lanzadas = falso_asistente("esperando")
ok(a._continuar_peticion("x", "y", A.MAX_CONTINUACIONES, False) is False and not lanzadas, "tope de continuaciones")

# ---- _atender recibe la nota y la profundidad (firma) y las pasa al ejecutor
import inspect
firma = inspect.signature(A.Asistente._atender).parameters
ok("nota_sistema" in firma and "profundidad" in firma, "la firma de _atender")

# ---- la respuesta de «sigue en segundo plano» le dice a la IA que se retomará sola (y que no dé la petición por cumplida)
ej = H.Ejecutor(avisar=lambda t: None, confirmar=True)
ej.continuar = lambda *a: True
ej.pregunta_pura = "Abre Stremio"
H.TIMEOUT_ESPERA = 1
r = ej.ejecutar("sleep 3", "instalar algo")
ok("RETOMARÁ SOLO" in r and "NO ha terminado" in r, f"mensaje a la IA con retomar: {r[:200]}")
ej2 = H.Ejecutor(avisar=lambda t: None, confirmar=True)
ej2.pregunta_pura = "Abre Stremio"
r2 = ej2.ejecutar("sleep 3", "instalar algo")
ok("RETOMARÁ" not in r2, "sin retomar, no promete nada")

# ---- una música o un programa lanzado y dejado funcionando no es una tarea que «termine»
for c in ("setsid mpv --no-video x &", "nohup firefox &", "mpv --no-video https://x", "vlc /tmp/a.mp3", "/usr/bin/mpv a.mp3"):
    ok(H._es_lanzamiento_persistente(c), f"lanzamiento persistente: {c}")
for c in ("flatpak install -y flathub com.x.X", "sleep 3", "apt install mpv", "pip install yt-dlp"):
    ok(not H._es_lanzamiento_persistente(c), f"no es persistente: {c}")

# ---- si has pedido otra cosa desde entonces, la petición vieja no se retoma
a = A.Asistente.__new__(A.Asistente)
a.historial = [{"rol": "user", "texto": "Reproduce música de Queen"}, {"rol": "model", "texto": "Puesta."},
               {"rol": "user", "texto": "Para la música"}, {"rol": "model", "texto": "Parada."}]
ok(a._pidio_otra_cosa_despues("Reproduce música de Queen"), "pidió parar la música después: no se retoma")
a.historial = [{"rol": "user", "texto": "Pregunta: Abre Stremio\n[SISTEMA: x]"}, {"rol": "model", "texto": "Instalando."},
               {"rol": "user", "texto": "Gracias"}, {"rol": "model", "texto": "De nada."}]
ok(not a._pidio_otra_cosa_despues("Abre Stremio"), "un «gracias» no cuenta como otra petición")
a.historial = [{"rol": "user", "texto": "Abre Stremio"}, {"rol": "model", "texto": "Instalando."}]
ok(not a._pidio_otra_cosa_despues("Abre Stremio"), "sin nada después: se retoma")
ok(not a._pidio_otra_cosa_despues("otra que no está"), "petición desconocida: no bloquea")

# ---- y el comando que se queda funcionando no se vigila como tarea (rama del tiempo de espera)
e, avisos = ejecutor(lambda *a: True)
e.pregunta_pura = "Reproduce música de Queen"
H.TIMEOUT_ESPERA = 1
r = e.ejecutar("sleep 3 &", "poner música")
ok("RETOMARÁ SOLO" not in r, f"un lanzamiento persistente no promete retomar: {r[:200]}")

print("fallos", fallos)
