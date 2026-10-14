import sys, time
from types import SimpleNamespace
from unittest.mock import MagicMock
for m in ("sounddevice", "faster_whisper"):
    sys.modules[m] = MagicMock()
from lina.nucleo import asistente as A
from lina.nucleo import herramientas as H
from lina.nucleo import recetas as REC

fallos = 0
def ok(c, m):
    global fallos
    if not c:
        fallos += 1; print("FALLO:", m)

# ---- las recetas solo se guardan si la petición se da por cumplida, y con la petición original
def falso_asistente(historial, actual):
    ej = H.Ejecutor(avisar=lambda *a, **k: None, confirmar=True)
    a = SimpleNamespace(ejecutor=ej, historial=historial, pregunta_pura=actual, turno_aceptado=False, receta_interfaz_pendiente=None)
    a._peticion_de_receta = lambda: A.peticion_de_receta(a.historial, a.pregunta_pura)
    return a

def receta_de_prueba():
    return {"ajuste": "posición de las pantallas", "palabras": "pantalla monitor", "cambiar": "kscreen-doctor output.DP-9.position.1970,0", "valor_usado": "1970,0",
            "leer": "kscreen-doctor -o", "comprobar": "estado leído después: DP-9 en 1970,0", "web": False}

hist = [{"rol": "user", "texto": "Haz que cada pantalla enseñe una cosa distinta"}, {"rol": "model", "texto": "Hecho"}]
a = falso_asistente(hist, "No lo has hecho")
a.ejecutor.recetas_diferidas.append(receta_de_prueba())
A.Asistente._cerrar_receta_interfaz(a, False)
ok(a.turno_aceptado is False and a.ejecutor.recetas_diferidas == [], "descartada: se vacía la lista")
ok(not REC._cargar(), "descartada: no se guarda ninguna receta")

a = falso_asistente(hist, "No lo has hecho")
a.ejecutor.recetas_diferidas.append(receta_de_prueba())
A.Asistente._cerrar_receta_interfaz(a, True)
guardadas = REC._cargar()
ok(len(guardadas) == 1 and a.turno_aceptado and a.ejecutor.receta_turno, "aceptada: se guarda una receta")
ok(guardadas and guardadas[0]["pedido"].startswith("Haz que cada pantalla"), "el pedido es la petición original, no la queja: " + str(guardadas and guardadas[0]["pedido"]))
ok(guardadas and "hecho" not in guardadas[0]["palabras"] and "has" not in guardadas[0]["palabras"], "las palabras no salen de la queja: " + str(guardadas and guardadas[0]["palabras"]))

# ---- la red de seguridad automática tampoco aprende si la petición no se dio por cumplida
b = A.Asistente.__new__(A.Asistente)
b.ejecutor = H.Ejecutor(avisar=lambda *a, **k: None, confirmar=True); b.pregunta_pura = "activa la luz nocturna"; b.historial = []
OK = "código de salida: 0\n"
b.acciones_turno = [("ejecutar_comando", {"comando": "kwriteconfig6 --file kwinrc --group NightColor --key Active true", "motivo": "activar la luz nocturna"}, OK),
                    ("ejecutar_comando", {"comando": "kreadconfig6 --file kwinrc --group NightColor --key Active"}, OK + "true")]
antes = len(REC._cargar())
b.turno_aceptado = False; b.ejecutor.receta_turno = False; b.ejecutor.duda = ""; b._aprender_automatico()
ok(len(REC._cargar()) == antes, "sin cumplirse lo pedido, el apunte automático no aprende")
b.turno_aceptado = True; b._aprender_automatico()
ok(len(REC._cargar()) == antes + 1, "cumplido: el apunte automático sí aprende")

# ---- abrir un programa: no se avisa de que «ha terminado» cuando el usuario lo cierra
H.TIMEOUT_ESPERA = 1
avisos = []
e = H.Ejecutor(avisar=lambda *a, **k: avisos.append(a), confirmar=True)
e._ctx_fondo = None
r = e.ejecutar("sleep 2", "abrir el programa de prueba")
ok("sigue en marcha" in r and "SEGUNDO PLANO" not in r, "abrir: se dice que está abierto, no que siga una tarea en segundo plano: " + r[:80])
time.sleep(3.5)
ok(not avisos, "abrir: al cerrarse el programa no se avisa por voz: " + str(avisos))

avisos.clear()
r = e.ejecutar("sleep 2", "copiar la carpeta de prueba")
ok("SEGUNDO PLANO" in r, "una tarea normal sigue en segundo plano")
time.sleep(3.5)
ok(any("Ya ha terminado" in str(x) for x in avisos), "una tarea normal sí avisa al terminar: " + str(avisos))
print("fallos", fallos)
