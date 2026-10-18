# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys, tempfile, pathlib
from unittest.mock import MagicMock
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
from lina.nucleo import recetas as R; from lina.nucleo import asistente as A; from lina.nucleo import herramientas as H; from lina.modulos import sistema as S
d=pathlib.Path(tempfile.mkdtemp()); R.ARCHIVO=d/"r.json"
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
# ---- A: herramientas de sistema ----
exec(open("t_sis.py").read().split("# ventanas")[0].split("fallos = 0")[1].join(["fallos = 0",""]) if False else "")
src=open("t_sis.py").read()
pre=src.split("from lina.nucleo import comandos")[0].replace("fallos = 0","fallos = 0",1)
exec(pre)
e=H.Ejecutor(avisar=lambda *a,**k:None, confirmar=True); e.pregunta_pura="sube el volumen"
ejec=[]
e.ejecutar=lambda c,m="tarea":(ejec.append(c) or "código de salida: 0\n(sin salida)")
H.SNAPSHOT_AUTOMATICA=False
estado["vol"]="Volume: 0.50"
def ej2(argv,timeout=8):
    if argv[:2]==["wpctl","get-volume"]: return 0,estado["vol"]
    return ej(argv,timeout)
S.EJ=ej2
r=e.sistema("audio",{"accion":"volumen","valor":"50"}); print(r)
ok("guardará como receta" in r,"volumen absoluto verificado: queda por confirmar")
ok(R._cargar()==[],"aún no se guarda: falta que la petición se dé por cumplida")
e.guardar_diferidas(e.pregunta_pura)
rs=R._cargar(); ok(any(x["ajuste"]=="volumen" and "{valor}" in x["cambiar"] for x in rs),"receta volumen %s"%[x.get("cambiar") for x in rs])
estado["vol"]="Volume: 0.50"
r=e.sistema("audio",{"accion":"volumen","valor":"30"}); ok("guardará como receta" not in r,"no coincide con lo pedido: no se apunta")
estado["vol"]="Volume: 0.60"
r=e.sistema("audio",{"accion":"subir"}); ok("guardará como receta" in r,"subir verificado: "+r)
estado["vol"]="Volume: 0.40 [MUTED]"
r=e.sistema("audio",{"accion":"silenciar"}); ok("guardará como receta" in r,"silenciar")
e.guardar_diferidas(e.pregunta_pura)
n=len(R._cargar()); ok(n==3,"3 recetas distintas, no fusionadas: %s"%[x["ajuste"] for x in R._cargar()])
r=e.sistema("energia",{"accion":"perfil","valor":"rendimiento"}); ok("guardará como receta" not in r,"perfil: powerprofilesctl simulado dice balanced → no")
# pantalla
KS["outputs"][0]["currentModeId"]="3"
r=e.sistema("pantalla",{"accion":"modo","salida":"DP-1","valor":"1920x1080@144"}); ok("guardará como receta" in r,"pantalla modo verificado: "+r[-120:])
KS["outputs"][0]["currentModeId"]="2"
r=e.sistema("pantalla",{"accion":"escala","salida":"DP-1","valor":"1.5"}); ok("guardará como receta" not in r,"escala no aplicada → no")
# no se apunta si el comando falla
e.ejecutar=lambda c,m="tarea":"código de salida: 1\nerror"
estado["vol"]="Volume: 0.20"
r=e.sistema("audio",{"accion":"volumen","valor":"20"}); ok("guardará como receta" not in r,"comando fallido no se apunta")

# ---- B: red de seguridad con comandos sueltos ----
a=A.Asistente.__new__(A.Asistente)
a.ejecutor=H.Ejecutor(avisar=lambda *a,**k:None, confirmar=True); a.pregunta_pura="activa la luz nocturna"
a.historial=[]
def turno(*acc): a.acciones_turno=list(acc); a.turno_aceptado=True; a.ejecutor.receta_turno=False; a.ejecutor.duda=""; a._aprender_automatico()
OK="código de salida: 0\n"
R.ARCHIVO=d/"r2.json"
turno(("ejecutar_comando",{"comando":"kwriteconfig6 --file kwinrc --group NightColor --key Active true","motivo":"activar la luz nocturna"},OK),
      ("ejecutar_comando",{"comando":"kreadconfig6 --file kwinrc --group NightColor --key Active"},OK+"true"))
rs=R._cargar(); ok(len(rs)==1 and rs[0]["ajuste"]=="luz nocturna" and "{valor}" in rs[0]["cambiar"] and rs[0]["leer"].startswith("kreadconfig6"),"auto kde-cmd %s"%rs)
turno(("ejecutar_comando",{"comando":"kwriteconfig6 --file kwinrc --group NightColor --key Active false","motivo":"desactivar la luz nocturna"},OK),
      ("ejecutar_comando",{"comando":"kreadconfig6 --file kwinrc --group NightColor --key Active"},OK+"false"))
rs=R._cargar(); ok(len(rs)==1,"desactivar se fusiona con activar (misma receta con {valor}): %s"%[x["ajuste"] for x in rs])
turno(("ejecutar_comando",{"comando":"gsettings set org.gnome.x tema oscuro","motivo":"poner tema"},OK))   # sin lectura posterior
ok(len(R._cargar())==1,"sin comprobación no se apunta")
turno(("ejecutar_comando",{"comando":"touch /tmp/a","motivo":"crear archivo a"},OK),("ejecutar_comando",{"comando":"ls /tmp/a"},OK+"/tmp/a"))
ok(len(R._cargar())==1,"touch/ls no es ajuste")
turno(("ejecutar_comando",{"comando":"kwriteconfig6 --file k --group g --key a 1","motivo":"cambiar a"},OK),("ejecutar_comando",{"comando":"kwriteconfig6 --file k --group g --key b 1","motivo":"cambiar b"},OK),
      ("ejecutar_comando",{"comando":"kreadconfig6 --file k --group g --key a"},OK+"1"))
ok(len(R._cargar())==1,"varios cambios: lo deja a la IA")
turno(("ejecutar_comando",{"comando":"systemctl --user restart pipewire","motivo":"reiniciar pipewire"},OK),("ejecutar_comando",{"comando":"systemctl --user is-active pipewire"},OK+"active"))
ok(len(R._cargar())==1,"servicios no son ajustes")
a.acciones_turno=[("guardar_receta",{},"Receta guardada")]; a.ejecutor.receta_turno=False; a._aprender_automatico()
print("fallos",f)
