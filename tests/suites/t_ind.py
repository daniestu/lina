import sys, os, io, types, tempfile, pathlib, subprocess
os.environ["HOME"]=tempfile.mkdtemp()
from unittest.mock import MagicMock
sys.modules["sounddevice"]=MagicMock(); sys.modules["faster_whisper"]=MagicMock()
from lina.voz import indicador as I; from lina.voz import manos_libres as M
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
# funciones puras
ok(I.color_de("rojo")=="#ef4444" and I.color_de("#00FF00")=="#00ff00" and I.color_de("00ff00")=="#00ff00" and I.color_de("zzz")=="#3b82f6","colores")
ok(I.grosor_de("90")==90 and I.grosor_de("5")==12 and I.grosor_de("9999")==300 and I.grosor_de("x")==40,"grosor")
ok(I.interpretar("modo habla")==("modo","habla") and I.interpretar("modo raro") is None and I.interpretar("")is None and I.interpretar("salir")==("salir","") and I.interpretar("color rojo")==("color","#ef4444") and I.interpretar("grosor 100")==("grosor",100),"interpretar")
ok(I.estilo_de("pensando","#3b82f6")[0]=="#f59e0b" and I.estilo_de("seguimiento","#123456")[2]==0.0 and I.estilo_de("off","#111111")[1]==0.0,"estilos")
# sin GTK aquí: el proceso de dibujo avisa y sale
sal=io.StringIO(); rc=I.servir(io.StringIO(""),sal); ok(rc in (2,3) and ("SIN GTK3" in sal.getvalue() or "SIN PANTALLA" in sal.getvalue()),"sin GTK: avisa %s %s"%(rc,sal.getvalue()))
# decisión de modo
ruta=pathlib.Path(tempfile.mkdtemp())/"a.txt"; cfg=M.Config(ruta)
t=[100.0]
class Prop: 
    def __init__(s): s.escrito=[]; s.stdin=types.SimpleNamespace(write=lambda x:s.escrito.append(x),flush=lambda:None); s.stdout=io.StringIO(""); s.returncode=None
    def poll(s): return s.returncode
    def wait(s,timeout=None): s.returncode=0
    def kill(s): s.returncode=-9
a=types.SimpleNamespace(estado="esperando",manos_libres=types.SimpleNamespace(modo=None,seguimiento_hasta=0.0),en_juego=lambda:False)
procs=[]
def lanzar(): p=Prop(); procs.append(p); return p
ind=I.Indicador(a,cfg=cfg,log=lambda *x:None,lanzar=lanzar,reloj=lambda:t[0]); ind.listo=True
ok(ind.modo_deseado()=="off","reposo")
a.estado="grabando"; ok(ind.modo_deseado()=="escucha","atajo grabando → escucha")
a.estado="esperando"; a.manos_libres.modo="orden"; ok(ind.modo_deseado()=="escucha","espera la orden → escucha"); a.manos_libres.modo=None
a.estado="pensando"; ok(ind.modo_deseado()=="pensando","pensando")
a.estado="hablando"; ok(ind.modo_deseado()=="habla","hablando")
a.estado="esperando"; a.manos_libres.seguimiento_hasta=t[0]+5; ok(ind.modo_deseado()=="seguimiento","ventana de seguimiento")
t[0]+=10; ok(ind.modo_deseado()=="off","seguimiento caducado")
# juegos
a.en_juego=lambda:True; a.estado="grabando"; t[0]+=5; ok(ind.modo_deseado()=="off","con juego no dibuja")
cfg.valores["indicador_juegos"]="si"; ok(ind.modo_deseado()=="escucha","indicador_juegos=si dibuja")
cfg.valores["indicador_juegos"]="no"; a.en_juego=lambda:False; t[0]+=5
# desactivado
cfg.valores["indicador"]="no"; ok(ind.modo_deseado()=="off","indicador=no"); cfg.valores["indicador"]="si"
# envío: no arranca el proceso en reposo; solo manda cambios
a.estado="esperando"; ind.paso(); ok(not procs,"en reposo no lanza el proceso")
a.estado="grabando"; ind.paso(); ok(len(procs)==1 and "modo escucha\n" in procs[0].escrito and "color #3b82f6\n" in procs[0].escrito and "grosor 40\n" in procs[0].escrito,"manda color, grosor y modo %s"%procs[0].escrito)
n=len(procs[0].escrito); ind.paso(); ok(len(procs[0].escrito)==n,"sin cambios no repite")
a.estado="pensando"; ind.paso(); ok(procs[0].escrito[-1]=="modo pensando\n","cambia de modo")
cfg.valores["indicador_color"]="rojo"; ind.paso(); ok("color #ef4444\n" in procs[0].escrito,"cambio de color en caliente")
a.estado="esperando"; ind.paso(); ok(procs[0].escrito[-1]=="modo off\n","vuelve a off")
# el proceso muere → se relanza, y tras 3 fallos se rinde
a.estado="grabando"; procs[0].returncode=1; ind.paso(); ok(len(procs)==2,"relanza si muere")
procs[1].returncode=1; ind.paso(); procs[2].returncode=1; ind.paso(); ok(ind.rendido and len(procs)==3,"se rinde tras 3 fallos %s %s"%(ind.rendido,len(procs)))
# lanzar que falla
ind2=I.Indicador(a,cfg=cfg,log=lambda *x:None,lanzar=lambda:(_ for _ in ()).throw(OSError("no")),reloj=lambda:t[0]); ind2.listo=True
a.estado="grabando"
for _ in range(4): ind2.paso()
ok(ind2.rendido,"si no puede lanzar, se rinde")
# cerrar
ind3=I.Indicador(a,cfg=cfg,log=lambda *x:None,lanzar=lanzar,reloj=lambda:t[0]); ind3.listo=True; ind3.paso(); p=procs[-1]; ind3.cerrar(); ok("salir\n" in p.escrito,"cerrar manda salir")
# config de manos libres reconoce las claves
ok(M.Config(ruta).valores["indicador"]=="si" and "indicador_grosor" in M.PREDETERMINADOS,"claves en PREDETERMINADOS")

# --- dependencias: se comprueban y se instalan solas
logs=[]; lg=lambda x:logs.append(x)
completo={"gtk":True,"cairo":True,"capa":True}
i1=I.Indicador(a,cfg=cfg,log=lg,lanzar=lanzar,reloj=lambda:t[0]); i1.sonda=lambda p:dict(completo)
llam=[]; i1.instalar=lambda log:llam.append(1) or True
ok(i1.preparar() and i1.listo and not llam,"todo presente: no instala")
i2=I.Indicador(a,cfg=cfg,log=lg,lanzar=lanzar,reloj=lambda:t[0]); estados=[{"gtk":True,"cairo":True,"capa":False},{"gtk":True,"cairo":True,"capa":True}]
i2.sonda=lambda p:estados.pop(0) if len(estados)>1 else estados[0]; i2.instalar=lambda log:llam.append(2) or True
ok(i2.preparar() and llam==[2] and i2.listo,"falta la capa: instala y queda listo")
i3=I.Indicador(a,cfg=cfg,log=lg,lanzar=lanzar,reloj=lambda:t[0]); i3.sonda=lambda p:{"gtk":False,"cairo":False,"capa":False}; i3.instalar=lambda log:False
ok(not i3.preparar() and i3.rendido and any("no hay con qué dibujar" in x for x in logs),"sin GTK y sin poder instalar: apagado con aviso")
a.estado="grabando"; i3.paso(); ok(not i3.proc,"apagado no lanza nada")
cfg.valores["indicador_instalar"]="no"; llam.clear()
i4=I.Indicador(a,cfg=cfg,log=lg,lanzar=lanzar,reloj=lambda:t[0]); i4.sonda=lambda p:{"gtk":True,"cairo":True,"capa":False}; i4.instalar=lambda log:llam.append(4) or True
i4.preparar(); ok(not llam and i4.listo,"indicador_instalar=no: no instala, dibuja con ventana normal"); cfg.valores["indicador_instalar"]="si"
i5=I.Indicador(a,cfg=cfg,log=lg,lanzar=lanzar,reloj=lambda:t[0]); a.estado="grabando"; n=len(procs); i5.paso(); ok(len(procs)==n,"sin preparar no lanza el dibujo")
ARCH={"familia":"arch","gestor":"pacman","tiene_gestor":True,"distro":"Arch"}; SIN={"familia":"arch","gestor":"pacman","tiene_gestor":False,"distro":"Arch"}
# instalar_dependencias con falsos
class R: 
    def __init__(s,rc=0,out="",err=""): s.returncode=rc; s.stdout=out; s.stderr=err
marca=pathlib.Path(tempfile.mkdtemp())/"m"; cmds=[]
def ej(cmd,**k): cmds.append(cmd); return R(0)
ok(I.instalar_dependencias(lg,ej,ARCH,marca,lambda:1000.0) and cmds[-1][:5]==["sudo","-n","pacman","-S","--noconfirm"] and "gtk-layer-shell" in cmds[-1],"instala con pacman oficial %s"%cmds[-1])
n=len(cmds); ok(not I.instalar_dependencias(lg,ej,ARCH,marca,lambda:1000.0+3600) and len(cmds)==n,"no insiste antes de 24 h")
ok(I.instalar_dependencias(lg,ej,ARCH,marca,lambda:1000.0+90000),"pasadas 24 h vuelve a probar")
def ej_sin_sudo(cmd,**k): return R(1) if cmd[:3]==["sudo","-n","true"] else R(0)
marca2=pathlib.Path(tempfile.mkdtemp())/"m"; ok(not I.instalar_dependencias(lg,ej_sin_sudo,ARCH,marca2,lambda:1.0) and any("sudo pide contraseña" in x for x in logs),"sin sudo sin contraseña: avisa y no instala")
marca3=pathlib.Path(tempfile.mkdtemp())/"m"; ok(not I.instalar_dependencias(lg,ej,SIN,marca3,lambda:1.0),"sin pacman: no hace nada")
def ej_falla(cmd,**k): return R(1,"","error: target not found: gtk-layer-shell") if "pacman" in cmd else R(0)
marca4=pathlib.Path(tempfile.mkdtemp())/"m"; ok(not I.instalar_dependencias(lg,ej_falla,ARCH,marca4,lambda:1.0) and any("target not found" in x for x in logs),"pacman falla: lo cuenta")
# sondear
ok(I.sondear("x",lambda *a,**k:R(0,'{"gtk": true, "cairo": true, "capa": false}\n'))=={"gtk":True,"cairo":True,"capa":False},"sondear")
ok(I.sondear("x",lambda *a,**k:(_ for _ in ()).throw(OSError()))=={"gtk":False,"cairo":False,"capa":False},"sondear falla")
ok(I.sondear(sys.executable)["gtk"] in (True,False),"sonda real no revienta")
ok(I.interpretar("intensidad 0.5")==("intensidad",0.5) and I.intensidad_de("9")==2.0 and I.intensidad_de("x")==1.0 and I.intensidad_de("0")==0.1,"intensidad")
ok("intensidad 1.0\n" in procs[0].escrito,"manda la intensidad")
print("FALLOS:",f)
