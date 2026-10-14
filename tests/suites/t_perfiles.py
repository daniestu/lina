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

# órdenes por voz: el origen (atajo o «Oye Lina») decide si se puede subir permisos o gasto; todo sin llamar a la IA
from lina.nucleo import asistente as A, presupuesto as PRES
def asistente(libre, dichas):
    a = A.Asistente.__new__(A.Asistente); a.origen_voz_libre = libre; a.decir = dichas.append; return a
dichas = []
aj.establecer("autonomia", "perfil", "equilibrado")
asistente(True, dichas)._atender("pasa al perfil prudente", 0)
ok(aj.get("autonomia", "perfil") == "prudente", "por «Oye Lina» se puede apretar el perfil")
asistente(True, dichas)._atender("pasa al perfil autónomo", 0)
ok(aj.get("autonomia", "perfil") == "prudente" and "atajo" in dichas[-1], "por «Oye Lina» no se puede aflojar el perfil")
asistente(False, dichas)._atender("pasa al perfil autónomo", 0)
ok(aj.get("autonomia", "perfil") == "autonomo", "con el atajo sí")
asistente(True, dichas)._atender("habla más rápido", 0)
ok(aj.get("voz", "velocidad") > 1.0, "la velocidad se cambia también por «Oye Lina»")
PRES.hay_clave_de_pago = lambda: True
PRES.estado = lambda: {"tope_eur": 10.0}
asistente(True, dichas)._atender("sube el tope de gasto a 50 euros", 0)
ok("atajo" in dichas[-1], "por «Oye Lina» no se sube el tope de gasto")
print("fallos", f); sys.exit(1 if f else 0)
