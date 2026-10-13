import sys, os, tempfile, pathlib, threading, time
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa)
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
import numpy as np; from lina.voz import manos_libres as M; from lina.nucleo import asistente as A
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
FR=16000
def ruido(seg,n=0.002): return (np.random.randn(int(seg*FR))*n).astype(np.float32)
def habla(seg,a=0.05,marca=0.0): return (np.sin(np.linspace(0,seg*440*6.28,int(seg*FR)))*a).astype(np.float32)
def bloques(x): return [x[i:i+480] for i in range(0,len(x)-479,480)]

# 1) segmentador
s=M.Segmentador(0.012); out=[]
for b in bloques(np.concatenate([ruido(1),habla(1.2),ruido(1.2),habla(0.1),ruido(1.2),habla(2),ruido(1)])):
    r=s.alimentar(b)
    if r is not None: out.append(len(r)/FR)
ok(len(out)==2,"2 frases (el chasquido de 0,1 s se ignora): %s"%out)
ok(1.2<out[0]<2.4,"duración %s"%out)

# 2) oyente con asistente falso
class Fa:
    estado="esperando"; interrumpiendo=False; modo_privado=False; juego=False
    def __init__(s): s.ordenes=[]
    def atender_manos_libres(s,t): s.ordenes.append(t); return True
    def en_juego(s): return s.juego
cfgp=casa/"activacion.txt"; cfg=M.Config(cfgp)
t=[0.0]; textos=[]; pit=[]; logs=[]
fa=Fa()
ml=M.ManosLibres(fa,lambda a:textos.pop(0),log=logs.append,pitido=pit.append,reloj=lambda:t[0],cfg=cfg)
def alim(x):
    for b in bloques(x):
        t[0]+=0.03; ml.procesar_bloque(b)
def frase(texto,seg=1.5):
    textos.append(texto); alim(habla(seg)); alim(ruido(1.0))
alim(ruido(1))
frase("Oye Lina, abre Firefox"); ok(fa.ordenes==["abre Firefox"],"orden directa %s"%fa.ordenes)
frase("estamos hablando de otra cosa"); ok(fa.ordenes==["abre Firefox"],"sin nombre se tira")
frase("escucha lina"); ok(ml.modo=="orden","espera la orden")
frase("pon música"); ok(fa.ordenes[-1]=="pon música" and ml.modo is None,"orden tras el nombre %s"%fa.ordenes)
# espera caducada
frase("hey lina"); alim(ruido(8)); ok(ml.modo is None,"caduca la espera"); ok(400 in pit,"pitido grave de caducidad")
n=len(fa.ordenes); frase("pon música"); ok(len(fa.ordenes)==n,"tras caducar, sin nombre no vale")
# seguimiento: responde (hablando→esperando)
fa.estado="pensando"; alim(ruido(0.1)); fa.estado="hablando"; alim(ruido(0.1)); fa.estado="esperando"; alim(ruido(1.0))
frase("y ahora sube el volumen"); ok(fa.ordenes[-1]=="y ahora sube el volumen","seguimiento sin nombre %s"%fa.ordenes)
n=len(fa.ordenes); frase("y otra cosa más aquí"); ok(len(fa.ordenes)==n,"solo una frase de seguimiento")
# seguimiento caducado
fa.estado="hablando"; alim(ruido(0.1)); fa.estado="esperando"; alim(ruido(10)); n=len(fa.ordenes); frase("sube el brillo por favor"); ok(len(fa.ordenes)==n,"seguimiento caducado")
# con el atajo NO hay ventana de seguimiento
fa.origen_voz_libre=False
fa.estado="pensando"; alim(ruido(0.1)); fa.estado="hablando"; alim(ruido(0.1)); fa.estado="esperando"; alim(ruido(1.0))
n=len(fa.ordenes); frase("y ahora baja el volumen"); ok(len(fa.ordenes)==n,"tras el atajo, sin nombre no vale (sin seguimiento)")
# una ventana abierta por manos libres se cierra si llega una petición del atajo
fa.origen_voz_libre=True
fa.estado="pensando"; alim(ruido(0.1)); fa.estado="hablando"; alim(ruido(0.1)); fa.estado="esperando"; alim(ruido(1.0))
fa.origen_voz_libre=False; fa.estado="pensando"; alim(ruido(0.1)); fa.estado="esperando"; alim(ruido(0.5))
n=len(fa.ordenes); frase("y ahora baja el brillo"); ok(len(fa.ordenes)==n,"petición del atajo cierra la ventana anterior")
fa.origen_voz_libre=True
# ignora mientras habla/graba
fa.estado="hablando"; textos.clear(); textos.append("oye lina para"); n=len(fa.ordenes); alim(habla(1.5)); alim(ruido(1)); ok(len(fa.ordenes)==n and textos,"no escucha mientras habla (eco)")
fa.estado="esperando"; textos.clear(); alim(ruido(1))
# durante 'pensando' sí oye el nombre (interrupción)
fa.estado="pensando"; frase("oye lina para"); ok(fa.ordenes[-1]=="para","interrupción por nombre mientras piensa")
fa.estado="esperando"; alim(ruido(1))
# juegos
fa.juego=True; t[0]+=10; alim(ruido(0.1)); n=len(fa.ordenes); frase("oye lina abre firefox"); ok(len(fa.ordenes)==n,"en juego no escucha"); textos.clear()
cfg.guardar("en_juegos","si"); ml.t_config=0; alim(ruido(4)); frase("oye lina abre firefox"); ok(fa.ordenes[-1]=="abre firefox","en_juegos=si escucha jugando")
cfg.guardar("en_juegos","no"); fa.juego=False; t[0]+=10; alim(ruido(1))
# privado y desactivado
fa.modo_privado=True; n=len(fa.ordenes); frase("oye lina abre firefox"); ok(len(fa.ordenes)==n,"modo privado: no escucha"); textos.clear(); fa.modo_privado=False
cfg.guardar("activo","no"); n=len(fa.ordenes); frase("oye lina abre firefox"); ok(len(fa.ordenes)==n,"desactivado"); textos.clear(); cfg.guardar("activo","si")
# alucinaciones
n=len(fa.ordenes); frase("Subtítulos por la comunidad de Amara.org"); ok(len(fa.ordenes)==n,"alucinación")
# nombre nuevo + recarga de archivo
cfg.guardar("nombre","jarvis"); ok("nombre = jarvis" in cfgp.read_text(),"guardado en archivo")
frase("oye yarvis enciende la luz"); ok(fa.ordenes[-1]=="enciende la luz","variante fonética yarvis→jarvis %s"%fa.ordenes)
frase("oye lina hola"); ok(fa.ordenes[-1]!="hola","el nombre viejo ya no vale")
# alias
cfg.guardar("alias","lina, mi asistente"); frase("hola mi asistente dime la hora"); ok(fa.ordenes[-1]=="dime la hora","alias de varias palabras %s"%fa.ordenes)
ok(any("Manos libres" in l for l in logs),"hay logs")

# 3) integración con el asistente real
a=A.Asistente.__new__(A.Asistente)
a.cerrojo=threading.Lock(); a.estado="esperando"; a.interrumpiendo=False; a.fin_tarea=threading.Event(); a.fin_tarea.set()
a.manos_libres=M.ManosLibres(a,lambda x:"",cfg=M.Config(casa/"a2.txt"))
lanzadas=[]
a._preparar_contexto=lambda:lanzadas.append("ctx")
a._tarea=lambda fn,*args:lanzadas.append(args)
ok(a.atender_manos_libres("abre firefox"),"atiende"); time.sleep(0.2)
ok(a.estado=="pensando" and a.origen_voz_libre,"estado pensando y origen manos libres")
ok(("abre firefox" in [x[0] for x in lanzadas if isinstance(x,tuple)]),"lanza _atender %s"%lanzadas)
ints=[]; a._interrupcion_con_texto=lambda t,i,c=True:ints.append((t,c))
a.atender_manos_libres("para"); time.sleep(0.2); ok(ints==[("para",False)],"mientras piensa → interrupción sin captura hecha %s"%ints)
a.estado="grabando"; ok(a.atender_manos_libres("x") is False,"grabando: no")
# confirmaciones por voz libre
class Ej:
    pendientes=[{"comando":"rm x"}]; t_pendiente=0
    def caducado(s): return False
    def exige_cantidad(s): return False
    def confirmar_pendientes(s): raise AssertionError("no debe ejecutar")
a.ejecutor=Ej(); a.historial=[]
A.H.describir_pendientes=lambda p:"borrar x"
a.decidir_confirmacion=lambda t,d:("confirma","atajo",False)
a.origen_voz_libre=True
nota,hecho=a.resolver_pendientes("sí"); ok(not hecho and "atajo" in nota,"voz libre no confirma: %s"%nota[:80])
a.origen_voz_libre=False
Ej.confirmar_pendientes=lambda s:"hecho"; Ej.ultimas=[]
nota,hecho=a.resolver_pendientes("sí"); ok(hecho,"con el atajo sí confirma")
a.origen_voz_libre=True; a.decidir_confirmacion=lambda t,d:("cancela","atajo",False); Ej.cancelar=lambda s,rechazar=False:None
nota,hecho=a.resolver_pendientes("no"); ok("NO" in nota,"cancelar por voz libre vale")
# órdenes de voz
cfgl=a.manos_libres.cfg
ok("desactivado" in a._gestionar_manos_libres(M.entender_orden("desactiva el manos libres")) and not cfgl.si("activo"),"desactivar")
a._gestionar_manos_libres(M.entender_orden("activa el manos libres")); ok(cfgl.si("activo"),"activar")
r=a._gestionar_manos_libres(M.entender_orden("a partir de ahora te llamas Jarvis")); ok("Jarvis" in r and cfgl.nombre=="jarvis","cambiar nombre: "+r)
ok("Jarvis" in a._gestionar_manos_libres(("pregunta_nombre",)),"pregunta nombre")

# 4) eco / sonido del PC
SUENA="Sink Input #5\n\tCorked: no\n\tMute: no\n\tProperties:\n\t\tapplication.name = \"mpv\"\n"
PAUSA="Sink Input #6\n\tCorked: yes\n\tMute: no\n"
ok(M.pc_suena(lambda *a:SUENA),"detecta sonido"); ok(not M.pc_suena(lambda *a:PAUSA),"pausado no cuenta"); ok(not M.pc_suena(lambda *a:""),"nada")
estado={"fuentes":"1\talsa_input\n2\t"+M.FUENTE_ECO+"\n","def":"alsa_input\n","inputs":SUENA,"set":[]}
def pa(*a):
    if a[:2]==("list","short"): return estado["fuentes"]
    if a[0]=="get-default-source": return estado["def"]
    if a[0]=="set-default-source": estado["def"]=a[1]+"\n"; estado["set"].append(a[1]); return ""
    if a[:2]==("list","sink-inputs"): return estado["inputs"]
    return ""
ok(M.usar_fuente_eco(lambda m:None,pa) and estado["set"]==[M.FUENTE_ECO],"pone la fuente sin eco")
estado["fuentes"]="1\talsa_input\n"; estado["def"]="alsa_input\n"; ok(not M.usar_fuente_eco(lambda m:None,pa),"sin módulo: no")
def nuevo(eco):
    fa2=Fa(); t2=[0.0]; tx=[]; ml2=M.ManosLibres(fa2,lambda a:tx.pop(0),log=lambda m:None,reloj=lambda:t2[0],cfg=M.Config(casa/"zz.txt"),pactl=pa); ml2.eco_activo=eco
    def al(x):
        for b in bloques(x): t2[0]+=0.03; ml2.procesar_bloque(b)
    al(ruido(1)); fa2.estado="hablando"; al(ruido(0.1)); fa2.estado="esperando"; al(ruido(1))
    tx.append("y ahora sube el volumen"); al(habla(1.5)); al(ruido(1)); return fa2
ok(nuevo(False).ordenes==[],"sonando y sin eco: el seguimiento sin nombre no vale (podría ser la tele)")
ok(nuevo(True).ordenes==["y ahora sube el volumen"],"con eco cancelado, el seguimiento vale aunque suene música")
# no se apunta lo descartado
logs.clear(); frase("hablando de tenis y de otras cosas"); ok(not any("tenis" in l for l in logs),"no registra lo que no va para mí")

ok(M.entender_orden("desactiva el eco")==("eco",False) and M.entender_orden("activa la cancelación de eco")==("eco",True),"orden eco")
# instalación automática simulada
from lina.voz import manos_libres as MM
llam=[]
MM.configurar_eco=lambda acc,log=print:(llam.append(acc) or True)
MM.FICHERO_ECO=casa/"noexiste.conf"; MM.MARCA_FALLO=casa/"fallo"
est2={"f":"1\talsa\n"}
def pa2(*a):
    if a[:2]==("list","short"): return est2["f"]
    return ""
fa3=Fa(); ml3=M.ManosLibres(fa3,lambda x:"",log=lambda m:None,cfg=M.Config(casa/"q.txt"),pactl=pa2)
ml3._preparar_eco(); ok(llam==["instalar"],"primer arranque instala el eco solo %s"%llam)
MM.configurar_eco=lambda acc,log=print:(llam.append(acc) or False)
llam.clear(); ml3._preparar_eco(); ok(llam==["instalar"] and (casa/"fallo").exists(),"si falla deja marca")
llam.clear(); ml3._preparar_eco(); ok(llam==[],"con marca de fallo no reintenta")
ml3.cfg.guardar("eco","no"); (casa/"fallo").unlink(); llam.clear(); ml3._preparar_eco(); ok(llam==[],"eco=no: no instala")
fa3.estado="esperando"; ml3.cfg.guardar("eco","auto"); llam.clear(); MM.configurar_eco=lambda acc,log=print:(llam.append(acc) or True)
ml3.cambiar_eco(False); time.sleep(0.4); ok(llam==["quitar"] and ml3.reabrir.is_set() and ml3.cfg.valores["eco"]=="no","desactivar eco por voz %s"%llam)

logs.clear(); frase("Oye Lina, abre Firefox"); ok(any("NUEVA PETICIÓN" in l for l in logs) and logs.index(next(l for l in logs if "NUEVA" in l))<logs.index(next(l for l in logs if "me has llamado" in l)),"separador antes de la petición")
logs.clear(); frase("hablando de otras cosas aquí"); ok(not any("NUEVA" in l for l in logs),"sin separador si no es para mí")
import io, contextlib
b=io.StringIO()
with contextlib.redirect_stdout(b): A.log_nueva_peticion()
ok("NUEVA PETICIÓN" in b.getvalue() and "=====" in b.getvalue(),"separador del atajo")
# palabra de activación por defecto: «Lina»
_c = M.Config()
for _frase, _debe in [("oye lina abre firefox", True), ("Lina, qué hora es", True), ("hola lina", True), ("oye lima abre firefox", False), ("ey nina pon música", False),
                      ("oye Marta abre firefox", False), ("esa casa es linda", False), ("oye mina", False), ("hablando de la vida", False)]:
    ok(M.buscar_activacion(_frase, _c)[0] == _debe, "activación por defecto %r -> %s" % (_frase, _debe))
print("FALLOS:",f)
