import sys, os, tempfile, pathlib
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa)
for m in ("sounddevice", "faster_whisper"): sys.modules[m] = MagicMock()
from lina.nucleo import ajustes as AJ, herramientas as H, politica as PO
f = 0
def ok(c, m):
    global f
    if not c: f += 1; print("FALLO:", m)
    else: print("OK ", m)

aj = AJ.actuales(log=lambda m: None)
ok((casa/".config"/"lina"/"config.toml").is_file(), "config.toml creado al primer uso")
ok(PO.datos()["modo"] == "alta" and PO.datos()["perfil"] == "autonomo", "perfil autónomo = como siempre")
nivel = lambda c: H.evaluar_politica(c)[0]
ok(nivel("rm /home/x/algo.txt") == "critico", "borrar de verdad pide confirmación por defecto")
ok(nivel("pacman -U paquete.pkg.tar.zst") == "critico", "software de fuera pide confirmación por defecto")
ok(nivel("ls /home") == "autonomo", "mirar no pide nada")

aj.establecer("autonomia", "borrado", "libre")
ok(nivel("rm /home/x/algo.txt") == "autonomo", "borrado = libre: ya no pregunta")
ok(nivel("pacman -U paquete.pkg.tar.zst") == "critico", "…y lo demás sigue igual")
aj.establecer("autonomia", "borrado", "perfil")
ok(nivel("rm /home/x/algo.txt") == "critico", "volver a «perfil» lo vigila otra vez")

# lo que no se puede aflojar: discos, arranque, cuentas, dinero
ok(nivel("mkfs.ext4 /dev/sdb1") == "critico" and nivel("passwd") == "critico" and nivel("efibootmgr") == "critico", "discos, cuentas y arranque siempre piden")
ok("discos_y_particiones" in AJ.SIEMPRE_CONFIRMAN and "dinero" in AJ.SIEMPRE_CONFIRMAN, "lista de lo que nunca se afloja")

aj.establecer("autonomia", "perfil", "prudente")
ok(PO.datos()["modo"] == "prudente" and PO.datos()["frenar_contenido_de_fuera"], "perfil prudente: modo prudente y frena tras leer internet")
ok(nivel("touch /home/x/nuevo.txt") == "critico", "prudente: hasta crear un archivo pide")
aj.establecer("autonomia", "perfil", "equilibrado")
ok(PO.datos()["modo"] == "alta" and PO.datos()["frenar_contenido_de_fuera"], "equilibrado: actúa solo pero frena tras leer internet")
aj.establecer("autonomia", "perfil", "autonomo")
ok(not PO.datos()["frenar_contenido_de_fuera"] and nivel("touch /home/x/nuevo.txt") == "autonomo", "autónomo otra vez")

# una sección vaciada a mano en politica.txt vuelve con «confirmar»
(casa/".config"/"lina"/"politica.txt").write_text("[modo]\nautonomia alta\n[borrado]\nmotivo x\n", encoding="utf-8")
ok(nivel("rm /home/x/algo.txt") == "autonomo", "politica.txt sin reglas de borrado: no pregunta")
aj.establecer("autonomia", "borrado", "confirmar")
ok(nivel("rm /home/x/algo.txt") == "critico", "borrado = confirmar recupera las reglas de fábrica")
# la IA no puede cambiar sus propios permisos, gasto ni claves por el terminal
for c in ("lina config poner autonomia.perfil autonomo", "lina config perfil autonomo", "lina config poner gasto.tope_mensual_eur 5000",
          "python -m lina config poner autonomia.borrado libre", "cd ~ && lina config poner voz.velocidad 2", "lina clave GITHUB_TOKEN", "lina voz es_ES-davefx-medium"):
    ok(H.clasificar(c)[0] == "bloqueado", "bloqueado para la IA: " + c)
for c in ("lina config", "lina config ver voz.velocidad", "lina config comprobar", "lina voz", "lina pulsar"):
    ok(H.clasificar(c)[0] != "bloqueado", "permitido (solo mira): " + c)

# Lina se consulta y se configura sola con la herramienta mis_ajustes; el origen (atajo o «Oye Lina») y lo leído de fuera limitan lo sensible
from lina.nucleo import asistente as A, grupos as G
from lina.voz import voces as VOC
def asistente(libre, sucio=False):
    a = A.Asistente.__new__(A.Asistente); a.origen_voz_libre = libre; a.ejecutor = MagicMock(); a.ejecutor.contaminado = "web" if sucio else None; return a
ok(any(d["name"] == "mis_ajustes" for d in H.DECLARACIONES) and "mis_ajustes" in G.GRUPOS["yo"], "mis_ajustes existe y está en el grupo «yo»")
ok("yo" in G.elegir("¿qué voces femeninas tienes?") and "yo" in G.elegir("ponme un ejemplo de tu voz"), "preguntar por las voces carga el grupo")
t = asistente(True)._mis_ajustes({"accion": "ayuda"})
ok("lina voz" in t and "voz.velocidad" in t and "es_MX-claude-high" in t, "ayuda: comandos, ajustes con valor y voces")
aj.establecer("autonomia", "perfil", "equilibrado")
asistente(True)._mis_ajustes({"accion": "cambiar", "ajuste": "autonomia.perfil", "valor": "prudente"})
ok(aj.get("autonomia", "perfil") == "prudente", "por «Oye Lina» se puede apretar el perfil")
r = asistente(True)._mis_ajustes({"accion": "cambiar", "ajuste": "autonomia.perfil", "valor": "autonomo"})
ok(aj.get("autonomia", "perfil") == "prudente" and "atajo" in r, "por «Oye Lina» no se puede aflojar el perfil")
asistente(False, sucio=True)._mis_ajustes({"accion": "cambiar", "ajuste": "autonomia.perfil", "valor": "autonomo"})
ok(aj.get("autonomia", "perfil") == "prudente", "tras leer contenido de fuera tampoco")
asistente(False)._mis_ajustes({"accion": "cambiar", "ajuste": "autonomia.perfil", "valor": "autonomo"})
ok(aj.get("autonomia", "perfil") == "autonomo", "con el atajo y sin contenido de fuera, sí")
asistente(False)._mis_ajustes({"accion": "cambiar", "ajuste": "gasto.tope_mensual_eur", "valor": "999"})
ok(aj.get("gasto", "tope_mensual_eur") == 10, "el tope de gasto no lo toca la IA ni con el atajo")
a = asistente(False); dichas = []
a._hablar = lambda texto, voz=None: dichas.append((voz, texto))
VOC.asegurar = lambda nombre, *x, **k: True
a._mis_ajustes({"accion": "probar_voz", "voz": "es_ES-davefx-medium", "texto": "hola"})
ok(dichas == [("es_ES-davefx-medium", "hola")] and VOC.voz_elegida() != "es_ES-davefx-medium", "probar_voz habla con esa voz sin cambiarla")
a._mis_ajustes({"accion": "elegir_voz", "voz": "es_ES-davefx-medium"})
ok(VOC.voz_elegida() == "es_ES-davefx-medium", "elegir_voz la cambia al instante")
ok("No conozco" in a._mis_ajustes({"accion": "elegir_voz", "voz": "inventada"}), "voz que no existe: lo dice")
print("fallos", f); sys.exit(1 if f else 0)
