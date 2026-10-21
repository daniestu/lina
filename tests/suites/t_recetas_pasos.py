# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 12b: lo que funcionó se aprende como pasos y se repite sin IA; si algo no sale igual, la IA toma el relevo; lo crítico sigue pidiendo confirmación."""
import sys, time, os, tempfile, threading
os.environ["HOME"] = tempfile.mkdtemp()
from unittest.mock import MagicMock
for m in ("sounddevice", "faster_whisper"):
    sys.modules[m] = MagicMock()
from lina.nucleo import asistente as A
from lina.nucleo import herramientas as H
from lina.nucleo import recetas as R
from lina.nucleo import tiempos as TIE

fallos = 0
def ok(c, m):
    global fallos
    if not c:
        fallos += 1; print("FALLO:", m)

CAMBIAR = "gsettings set org.gnome.desktop.privacy disable-camera true"
LEER = "gsettings get org.gnome.desktop.privacy disable-camera"
CRITICO = "sudo -n modprobe -r uvcvideo"

class Ejec:
    """Ejecutor falso: devuelve lo que diga `respuestas[comando]` (por defecto, éxito) y apunta las llamadas."""
    def __init__(self, respuestas=None):
        self.pendientes, self.recetas_diferidas, self.continuar = [], [], "x"
        self.llamadas, self.respuestas, self.cancelado = [], respuestas or {}, 0
        self.pregunta_pura, self.borrado_definitivo = "", True
        self.duda, self.contaminado, self.receta_turno = "", "", False
    def herramienta(self, args):
        c = args["comando"]
        self.llamadas.append(c)
        if c in self.respuestas:
            r = self.respuestas[c]
            if r is H.MENSAJE_PREPARADO:
                self.pendientes.append({"comando": c})
            return r
        return "código de salida: 0 (0 s)\n\n" + ("true" if c == LEER else "")
    def abrir_app(self, nombre):
        self.llamadas.append(("abrir_app", nombre)); return "Abierto «Firefox»."
    def sistema(self, nombre, args):
        self.llamadas.append((nombre, dict(args)))
        return "código de salida: 0 (0 s)\n\nCOMPROBADO AHORA: Altavoces: Volume: 0.40"
    def cancelar(self, rechazar=False):
        self.cancelado += 1; self.pendientes = []

def asistente(ej, activo=True):
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor, a.historial, a.interrumpiendo = ej, [], False
    a.hilo_captura = threading.Thread(target=lambda: None); a.hilo_captura.start()
    a.nueva_tarea = lambda: None
    a._continuar_peticion = lambda *x: True
    a.acciones_turno, a.turno_aceptado, a.pregunta_pura, a.acciones_confirmadas = [], True, "", []
    a.dichas = []
    a.decir = lambda t: a.dichas.append(t)
    a._recetas_de_pasos_activas = lambda: activo
    return a

def limpiar():
    R._guardar([])

def terminar(a, frase, acciones, **cambios):
    """La IA ha hecho `acciones` para `frase` y se ha dado por buena: lo que ocurre al final de _atender."""
    a.pregunta_pura, a.acciones_turno, a.turno_aceptado = frase, acciones, True
    for k, v in cambios.items():
        setattr(a.ejecutor, k, v)
    a._aprender_pasos()
    return [r for r in R._cargar() if r["tipo"] == "pasos"]

def cmd(c, salida="", ok_=True):
    return ("ejecutar_comando", {"comando": c, "motivo": "Desactivar la cámara"}, ("código de salida: 0 (0 s)\n\n" if ok_ else "código de salida: 1 (0 s)\n\n") + salida)

def repetir(a, frase):
    crono = TIE.Cronometro()
    r = a._intentar_receta_pasos(frase, crono)
    if r:
        a._cerrar_directa(frase, r[0], r[1], time.time(), crono)
    return r

# ---- se aprende: solo lo que cambió algo y funcionó; la lectura posterior comprueba; los intentos fallidos y las exploraciones se quedan fuera
limpiar(); a = asistente(Ejec())
rs = terminar(a, "desactiva la cámara", [("mas_herramientas", {"grupo": "x"}, "ok"), cmd("gsettings get org.gnome.desktop.privacy camera-x", "", False),
                                         ("buscar_ajuste_kde", {}, "..."), cmd(CAMBIAR), cmd(LEER, "true")])
ok(len(rs) == 1 and [p["args"]["comando"] for p in rs[0]["pasos"]] == [CAMBIAR], f"solo el cambio que funcionó: {rs}")
ok(rs and rs[0]["verificada"] and rs[0]["comprobar"] == LEER and rs[0]["esperado"] == "true", f"comprobada por el código: {rs and (rs[0]['verificada'], rs[0]['comprobar'], rs[0]['esperado'])}")
ok(a.ejecutor.receta_turno, "queda marcado que ya se apuntó receta")

# ---- no se aprende si: no se dio por buena, hay duda, contenido de fuera, algo pendiente, ya se apuntó otra, o el ajuste está apagado
for nombre, extra in (("duda", dict(duda="x")), ("contaminado", dict(contaminado="búsqueda web")), ("pendiente", dict(pendientes=[{"comando": "x"}])),
                      ("ya apuntada", dict(receta_turno=True))):
    limpiar(); a = asistente(Ejec())
    ok(terminar(a, "desactiva la cámara", [cmd(CAMBIAR), cmd(LEER, "true")], **extra) == [], f"no se aprende ({nombre})")
limpiar(); a = asistente(Ejec()); a.turno_aceptado = False
a.pregunta_pura, a.acciones_turno = "desactiva la cámara", [cmd(CAMBIAR), cmd(LEER, "true")]
a._aprender_pasos(); ok(R._cargar() == [], "no se aprende si la petición no se dio por buena")
limpiar(); a = asistente(Ejec(), activo=False)
ok(terminar(a, "desactiva la cámara", [cmd(CAMBIAR), cmd(LEER, "true")]) == [], "ajuste directas.recetas = false: no se aprende")

# ---- no se aprende lo que no se sabe repetir o es peligroso
for nombre, acciones in (("notas", [cmd(CAMBIAR), ("notas", {"accion": "añadir"}, "ok")]),
                         ("borrar", [cmd("rm -rf ~/x")]),
                         ("apagar", [cmd("systemctl poweroff")]),
                         ("fecha", [cmd("kwriteconfig6 --key Hora 12:30")]),
                         ("nada que cambie", [cmd(LEER, "true")]),
                         ("todo falló", [cmd(CAMBIAR, "", False)])):
    limpiar(); a = asistente(Ejec())
    ok(terminar(a, "desactiva la cámara", acciones) == [], f"no se aprende ({nombre})")

# ---- frases que dependen del contexto, seguimientos o preguntas no se aprenden
for frase in ("ciérralo", "desactiva esto", "abre el último", "¿está desactivada la cámara?", "ahora desactívala", "desactiva la cámara y sube el volumen"):
    limpiar(); a = asistente(Ejec())
    ok(terminar(a, frase, [cmd(CAMBIAR), cmd(LEER, "true")]) == [], f"no se aprende de «{frase}»")

# ---- un paso crítico solo se aprende si es el último, y la petición es la de antes del «sí»
limpiar(); a = asistente(Ejec())
a.historial = [{"rol": "user", "texto": "Pregunta: desactiva la cámara\n[SISTEMA: x]"}, {"rol": "model", "texto": "¿Lo hago?"}]
rs = terminar(a, "sí", [cmd(CRITICO), cmd("lsmod | grep uvcvideo", "uvcvideo 114688 0")])
ok(len(rs) == 1 and rs[0]["ajuste"] == "desactiva la cámara" and rs[0]["pasos"][0]["args"]["comando"] == CRITICO, f"crítico tras un sí: {rs}")
limpiar(); a = asistente(Ejec())
ok(terminar(a, "desactiva la cámara", [cmd(CRITICO), cmd(CAMBIAR)]) == [], "un crítico que no es el último no se aprende")
ok(terminar(a, "desactiva la cámara", [cmd(CRITICO), cmd(CRITICO + " otro")]) == [], "dos críticos no se aprenden")

# ---- repetir: sin IA, con las herramientas de siempre, comprobando después
limpiar(); a = asistente(Ejec())
terminar(a, "desactiva la cámara", [cmd(CAMBIAR), cmd(LEER, "true")])
ej = Ejec(); a = asistente(ej)
r = repetir(a, "Oye, desactiva la cámara, por favor")
ok(r == ("Hecho.", "receta") and ej.llamadas == [CAMBIAR, LEER], f"se repite y se comprueba: {r} {ej.llamadas}")
ok(a.dichas == ["Hecho."] and a.historial[-1]["texto"] == "Hecho.", "se dice y queda en el historial")
ok(R._cargar()[0]["exitos"] == 2, "cuenta el acierto")
ej = Ejec(); a = asistente(ej)
ok(repetir(a, "activa la cámara") is None and ej.llamadas == [], "activar no repite lo de desactivar")
ok(repetir(a, "¿está desactivada la cámara?") is None and ej.llamadas == [], "una pregunta no repite nada")
ej = Ejec(); a = asistente(ej, activo=False)
ok(repetir(a, "desactiva la cámara") is None and ej.llamadas == [], "con directas.recetas = false no se repite")
ej = Ejec(); ej.pendientes = [{"comando": "x"}]; a = asistente(ej)
ok(repetir(a, "desactiva la cámara") is None and ej.llamadas == [], "con algo pendiente de confirmar, manda el flujo normal")

# ---- si la comprobación no da lo de antes: la IA toma el relevo con una nota, y a la segunda seguida se olvida la receta
ej = Ejec({LEER: "código de salida: 0 (0 s)\n\nfalse"}); a = asistente(ej)
r = repetir(a, "desactiva la cámara")
ok(r is None and "comprobación no dio" in a._nota_pasos and ej.cancelado == 1 and not a.dichas, f"comprobación distinta: {r} {a._nota_pasos}")
ok(R._cargar()[0]["fallos"] == 1, "cuenta el fallo")
a = asistente(Ejec({LEER: "código de salida: 0 (0 s)\n\nfalse"}))
ok(repetir(a, "desactiva la cámara") is None, "con un fallo suelto ya no se repite sola")
R.resultado_pasos(R._cargar()[0]["id"], False)
ok([r for r in R._cargar() if r["tipo"] == "pasos"] == [], "dos fallos seguidos: olvidada")

# ---- si un paso falla: relevo con nota que dice qué pasos ya se hicieron
limpiar(); terminar(asistente(Ejec()), "desactiva la cámara", [cmd(CAMBIAR), cmd(LEER, "true")]); terminar(asistente(Ejec()), "desactiva la cámara", [cmd(CAMBIAR), cmd(LEER, "true")])
ej = Ejec({CAMBIAR: "código de salida: 1 (0 s)\n\nerror"}); a = asistente(ej)
r = repetir(a, "desactiva la cámara")
ok(r is None and "falló en el paso 1" in a._nota_pasos and ej.llamadas == [CAMBIAR], f"paso fallido: {r} {a._nota_pasos} {ej.llamadas}")

# ---- si el comando ya no está permitido (política cambiada), no se ejecuta
limpiar(); terminar(asistente(Ejec()), "desactiva la cámara", [cmd(CAMBIAR), cmd(LEER, "true")]); terminar(asistente(Ejec()), "desactiva la cámara", [cmd(CAMBIAR), cmd(LEER, "true")])
clasificar_antes = H.clasificar
H.clasificar = lambda c: ("bloqueado", "x")
ej = Ejec(); a = asistente(ej)
r = repetir(a, "desactiva la cámara")
H.clasificar = clasificar_antes
ok(r is None and ej.llamadas == [] and "ya no es válida" in a._nota_pasos, f"bloqueado ahora: {r} {ej.llamadas}")

# ---- un paso crítico sigue pidiendo confirmación: se pregunta y queda pendiente (no se cancela ni se ejecuta)
limpiar(); a = asistente(Ejec()); a.historial = [{"rol": "user", "texto": "desactiva la cámara"}, {"rol": "model", "texto": "¿Lo hago?"}]
terminar(a, "sí", [cmd(CRITICO), cmd("lsmod | grep uvcvideo", "uvcvideo 114688 0")])
terminar(a, "sí", [cmd(CRITICO), cmd("lsmod | grep uvcvideo", "uvcvideo 114688 0")])
ej = Ejec({CRITICO: H.MENSAJE_PREPARADO}); a = asistente(ej)
r = repetir(a, "desactiva la cámara")
ok(r and r[0].startswith("Esto necesita tu confirmación") and r[0].endswith("¿Lo hago?") and ej.pendientes and ej.cancelado == 0 and ej.llamadas == [CRITICO],
   f"crítico: {r} {ej.pendientes} {ej.llamadas}")
ok(a.historial[-1]["texto"].endswith("?"), "la pregunta queda en el historial para que el «sí» la encuentre")

# ---- con número: se repite con el valor nuevo y la herramienta de sistema que comprueba
limpiar()
a = asistente(Ejec())
acc = [("audio", {"accion": "volumen", "valor": "40"}, "código de salida: 0 (0 s)\n\nCOMPROBADO AHORA: Altavoces: Volume: 0.40")]
terminar(a, "pon el volumen al 40", acc)
ej = Ejec(); a = asistente(ej)
r = repetir(a, "pon el volumen al 70")
ok(r == ("Hecho.", "receta") and ej.llamadas == [("audio", {"accion": "volumen", "valor": "70"})], f"con valor: {r} {ej.llamadas}")
ej = Ejec(); a = asistente(ej)
ok(repetir(a, "pon el volumen") is None and ej.llamadas == [], "sin número no se repite")

# ---- una herramienta de sistema que ya no comprueba el resultado deja de valer
class SinComprobar(Ejec):
    def sistema(self, nombre, args):
        self.llamadas.append((nombre, dict(args))); return "código de salida: 0 (0 s)"
ej = SinComprobar(); a = asistente(ej)
ok(repetir(a, "pon el volumen al 70") is None and "falló en el paso 1" in a._nota_pasos, "sin COMPROBADO AHORA, relevo a la IA")

print("t_recetas_pasos:", "OK" if not fallos else f"{fallos} fallos")
sys.exit(1 if fallos else 0)
