import sys
from unittest.mock import MagicMock
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
src=open("t_b4.py").read().split("# --- proton ---")[0]
exec(src)
from lina.nucleo import herramientas as H; from lina.nucleo import asistente
e=H.Ejecutor(avisar=lambda *a,**k:None, confirmar=True)
r=e.steam_config("proton",{"accion":"poner","juego":"skyrim","valor":"GE"}); print(r[:120])
ok(H.MENSAJE_PREPARADO in r and len(e.pendientes)==1,"queda pendiente")
ok(J.mapa_proton(raiz/"config/config.vdf")["489830"]=="proton_9","aún no escrito")
out=e.confirmar_pendientes(); print(out[:200])
ok(J.mapa_proton(raiz/"config/config.vdf")["489830"]=="GE-Proton10-1","escrito tras el sí")
r=e.steam_config("proton",{"accion":"listar"}); ok("GE-Proton10-1" in r,"listar sin pendiente"); ok(len(e.pendientes)==0,"sin pendientes")
print(e.mangohud({"accion":"activar","opciones":["fps"]})[:80])
print("fallos",f)
