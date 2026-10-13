import sys, os, json, types, importlib, tempfile, pathlib
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa)
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)

# ---- falso Atspi ----
class Rol:  # value_nick
    def __init__(s,n): s.value_nick=n
class Estados:
    def __init__(s,l): s.l=l
    def contains(s,x): return x in s.l
class SType:
    ENABLED="ENABLED";SHOWING="SHOWING";FOCUSED="FOCUSED";CHECKED="CHECKED";SELECTED="SELECTED";EXPANDED="EXPANDED";EDITABLE="EDITABLE";ACTIVE="ACTIVE";PRESSED="PRESSED";SENSITIVE="SENSITIVE"
class Acc:
    def __init__(s,rol,nombre="",hijos=(),est=("SHOWING","ENABLED","SENSITIVE"),acc=(),caja=(10,20,80,30),texto=""):
        s.r,s.n,s.h,s.e,s.a,s.c,s.t=rol,nombre,list(hijos),est,acc,caja,texto
    def get_child_count(s): return len(s.h)
    def get_child_at_index(s,i): return s.h[i]
    def get_name(s): return s.n
    def get_description(s): return getattr(s,'d','')
    def get_role(s): return Rol(s.r)
    def get_state_set(s): return Estados(s.e)
    def get_action_iface(s):
        if not s.a: return None
        o=MagicMock(); o.get_n_actions.return_value=len(s.a); o.get_action_name.side_effect=lambda i:s.a[i]; return o
    def get_component_iface(s):
        o=MagicMock(); e=MagicMock(); e.x,e.y,e.width,e.height=s.c; o.get_extents.return_value=e; return o
    def get_text_iface(s):
        if not s.t: return None
        o=MagicMock(); o.get_character_count.return_value=len(s.t); o.get_text.side_effect=lambda a,b:s.t[a:b]; return o
dolphin=Acc("application","dolphin",[Acc("frame","Descargas — Dolphin",[
    Acc("tool-bar","",[Acc("push-button","Atrás",acc=["click"]),Acc("push-button","Adelante",est=("SHOWING",)),]),
    Acc("panel","",[Acc("text","Ruta",texto="/home/usuario/Descargas",est=("SHOWING","ENABLED","EDITABLE")),
                    Acc("password-text","Clave",texto="secreta"),
                    Acc("check-box","Mostrar ocultos",est=("SHOWING","ENABLED","CHECKED")),
                    Acc("push-button","Oculto",est=("ENABLED",)),
                    Acc("label",""),Acc("label","3 elementos")])],est=("SHOWING","ACTIVE"))])
firefox=Acc("application","firefox",[Acc("frame","GeoGuessr — Mozilla Firefox",[Acc("push-button","Jugar")],est=("SHOWING",))])
desktop=Acc("desktop","",[firefox,dolphin])
gi=types.ModuleType("gi"); gi.require_version=lambda *a:None
at=types.ModuleType("gi.repository"); A=types.SimpleNamespace(StateType=SType,CoordType=types.SimpleNamespace(SCREEN=0),get_desktop=lambda n:desktop)
at.Atspi=A; gi.repository=at
sys.modules["gi"]=gi; sys.modules["gi.repository"]=at
from lina.escritorio import interfaz_atspi as AT
apps=AT.listar_apps(); ok(len(apps)==2 and apps[1]["ventanas"][0]["activa"],"apps %s"%apps)
sel,msg=AT.elegir_ventana(""); ok(sel and sel[3].n.startswith("Descargas"),"sin texto: la activa")
sel,msg=AT.elegir_ventana("geoguessr"); ok(sel and sel[0]==0,"por título")
sel,msg=AT.elegir_ventana("vlc"); ok(sel is None and "Dolphin" in msg and "Electron" in msg,"no existe: dice cuáles hay")
els,rec=AT.recorrer(dolphin.h[0],"1.0","",100)
nombres=[e["nombre"] for e in els]
ok("Atrás" in nombres and "Adelante" in nombres and "Mostrar ocultos" in nombres,"controles %s"%nombres)
ok("Oculto" not in nombres,"lo no visible no sale")
ok(not any(e["nombre"]=="" for e in els),"labels sin texto no salen")
pw=[e for e in els if e["rol"]=="password-text"][0]; ok(pw["valor"]=="(oculto)","contraseña nunca se lee")
ruta=[e for e in els if e["nombre"]=="Ruta"][0]; ok(ruta["valor"]=="/home/usuario/Descargas" and ruta["id"]=="1.0.1.0","valor e id %s"%ruta["id"])
els,_=AT.recorrer(dolphin.h[0],"1.0","casilla",100); ok(len(els)==1 and els[0]["nombre"]=="Mostrar ocultos","filtro por tipo")
els,rec=AT.recorrer(dolphin.h[0],"1.0","",2); ok(len(els)==2 and rec,"recorta")

# ---- módulo interfaz: formato ----
from lina.escritorio import interfaz as INT
def ayu(*a):
    if a[0]=="apps": return {"apps":AT.listar_apps()}
    kv=dict(x[2:].split("=",1) for x in a if x.startswith("--") and "=" in x)
    ven=kv["ventana"]; fil=kv["filtro"]
    sel,msg=AT.elegir_ventana(ven)
    if not sel: return {"error":msg}
    els,rec=AT.recorrer(sel[3],f"{sel[0]}.{sel[1]}",fil,100)
    return {"app":sel[2].n,"ventana":sel[3].n,"elementos":els,"recortado":rec}
t=INT.herramienta({"accion":"elementos"},ayu); print(t)
ok("«Atrás»" in t and "acción: click" in t and "datos" in t.lower() and "[1.0.0.0]" in t,"texto elementos")
ok("desactivado" in t,"Adelante sin ENABLED aparece desactivado")
ok("(oculto)" in t and "secreta" not in t,"sin secretos")
t=INT.herramienta({"accion":"elementos","ventana":"vlc"},ayu); ok("No veo" in t,"error claro")
t=INT.herramienta({"accion":"programas"},ayu); ok("firefox" in t and "(activa)" in t,"programas")
t=INT.herramienta({"accion":"capacidades"},ayu); ok("diagnostico" in t,"sin diagnóstico → lo pide")
INT.CAPACIDADES=casa/"cap.txt"; INT.CAPACIDADES.write_text("a11y_python=si\na11y_activa=si\nentrada=si\ncaptura=si\nventanas=si\n")
t=INT.herramienta({"accion":"capacidades"}); ok("accesibilidad (leer controles por nombre): sí" in t and "entrada virtual (pulsar, escribir): sí" in t,t)
# ayudante roto / lento
import subprocess
def lento(*a,**k): raise subprocess.TimeoutExpired("x",1)
ok("tardado" in INT._ayudante("apps",ejecutar=lento)["error"],"timeout")
def basura(*a,**k): return types.SimpleNamespace(stdout="Traceback...",stderr="boom",returncode=1)
ok("no ha contestado" in INT._ayudante("apps",ejecutar=basura)["error"],"salida rota")
# ---- grupos / herramientas ----
from lina.nucleo import grupos as G; from lina.nucleo import herramientas as H
ok("interfaz" in [d["name"] for d in H.DECLARACIONES],"declarada")
g=G.elegir("pulsa el botón de aceptar")
print("grupos para 'pulsa el botón de aceptar':",g)
ok(g and "interfaz" in g,"el grupo salta con «pulsa el botón»")

t=INT.herramienta({"accion":"elementos","filtro":"zzz"},ayu); ok("Ningún control encaja con «zzz»" in t and "«Atrás»" in t,"filtro vacío → enseña todo")
els,_=AT.recorrer(dolphin.h[0],"1.0","",1000,True); ok(len(els)>=9 and any(e["rol"]=="panel" for e in els) and any(e["nombre"]=="Oculto" for e in els),"crudo: todos los nodos %d"%len(els))

b=Acc("button","",est=("SHOWING","ENABLED","VISIBLE"),acc=["Press"]); b.d="Recargar"
b2=Acc("button","",est=("SHOWING","ENABLED","VISIBLE")); b3=Acc("button","Cerrar",est=("ENABLED",))
fr=Acc("frame","X",[b,b2,b3,Acc("text","",texto="búsqueda",est=("SHOWING","ENABLED"))],est=("SHOWING","ACTIVE"))
els,_=AT.recorrer(fr,"0.0","",100)
ok([e["nombre"] for e in els if e["rol"]=="button"]==["Recargar"],"rol «button» de Qt, nombre por descripción, sin nombre ni descripción no, oculto no: %s"%[(e["rol"],e["nombre"]) for e in els])
ok(any(e["rol"]=="text" and e["valor"]=="búsqueda" for e in els),"campo sin nombre pero con valor sí")

# ================= FASE 2 =================
AT.time.sleep=lambda *_:None; INT.time.sleep=lambda *_:None
class Dyn(Acc):
    cb=None; ed=None
    def get_action_iface(s):
        o=MagicMock(); o.get_n_actions.return_value=len(s.a); o.get_action_name.side_effect=lambda i:s.a[i]
        o.do_action.side_effect=lambda i:(s.cb() if s.cb else None) or True; return o
    def get_editable_text_iface(s):
        if s.ed is None: return None
        o=MagicMock()
        def st(t): s.t=t; return True
        o.set_text_contents.side_effect=st
        o.insert_text.side_effect=lambda pos,t,n:st(s.t[:pos]+t+s.t[pos:])
        return o
marco=Dyn("frame","Ajustes — App",[],est=("SHOWING","ACTIVE"))
btn=Dyn("button","Aplicar",est=("SHOWING","ENABLED","SENSITIVE"),acc=["Press"])
casilla=Dyn("check-box","Modo oscuro",est=("SHOWING","ENABLED","SENSITIVE"),acc=["Toggle"])
campo=Dyn("text","Nombre",est=("SHOWING","ENABLED","EDITABLE"),texto="viejo"); campo.ed=True
clave=Dyn("password-text","Clave",est=("SHOWING","ENABLED","EDITABLE"),texto="x"); clave.ed=True
dis=Dyn("button","Gris",est=("SHOWING",),acc=["Press"])
marco.h=[btn,casilla,campo,clave,dis]
def abrir_dialogo():
    marco.h.append(Dyn("button","Aceptar",est=("SHOWING","ENABLED","SENSITIVE"),acc=["Press"]))
btn.cb=abrir_dialogo
casilla.cb=lambda: casilla.e.__class__ and setattr(casilla,"e",("SHOWING","ENABLED","SENSITIVE","CHECKED"))
app2=Dyn("application","ajustes",[marco]); desktop.h.append(app2)
iapp=len(desktop.h)-1
def cli(orden,**kw):
    a=types.SimpleNamespace(ventana=kw.get("ventana",""),id=kw.get("id",""),nombre=kw.get("nombre",""),rol=kw.get("rol",""),texto=kw.get("texto",""),modo=kw.get("modo","reemplazar"))
    return (AT.accion_pulsar if orden=="pulsar" else AT.accion_escribir)(a)
r=cli("pulsar",id=f"{iapp}.0.0",nombre="Aplicar")
ok(r.get("ok") and r["accion"].lower()=="press","pulsar ok %s"%r)
ok(any("Aceptar" in x for x in r["cambios"]["controles_nuevos"]),"cambios: diálogo nuevo %s"%r)
# la ruta se desplazó pero el nombre sigue: se re-resuelve
marco.h.insert(0,Dyn("button","Otro",est=("SHOWING","ENABLED","SENSITIVE"),acc=["Press"]))
r=cli("pulsar",id=f"{iapp}.0.0",nombre="Modo oscuro"); ok(r.get("ok") and "CHECKED" in casilla.e,"re-resuelve por nombre %s"%r)
r=cli("pulsar",id=f"{iapp}.0.0",nombre="No existe"); ok("error" in r and "ya no está" in r["error"],"control desaparecido")
r=cli("pulsar",id=f"{iapp}.0.5",nombre="Gris"); ok("desactivado" in r.get("error",""),"desactivado %s"%r)
r=cli("pulsar",id="99.0.0",nombre="X"); ok("error" in r,"ventana inexistente")
r=cli("escribir",id=f"{iapp}.0.3",nombre="Nombre",texto="nuevo"); ok(r.get("ok") and r["despues"]=="nuevo" and r["antes"]=="viejo","escribir %s"%r)
r=cli("escribir",id=f"{iapp}.0.3",nombre="Nombre",texto="!",modo="anadir"); ok(r["despues"]=="nuevo!","añadir %s"%r)
r=cli("escribir",id=f"{iapp}.0.4",nombre="Clave",texto="hola"); ok("error" in r and clave.t=="x","contraseña intocable %s"%r)
r=cli("escribir",id=f"{iapp}.0.1",nombre="Modo oscuro",texto="x"); ok("error" in r,"no editable")
# ventana de autenticación
polkit=Dyn("application","polkit-kde-authentication-agent",[Dyn("frame","Autenticación requerida",[Dyn("button","Aceptar",est=("SHOWING","ENABLED","SENSITIVE"),acc=["Press"])],est=("SHOWING","ACTIVE"))])
desktop.h.append(polkit); ip=len(desktop.h)-1
r=cli("pulsar",id=f"{ip}.0.0",nombre="Aceptar"); ok("contraseñas o autenticación" in r.get("error",""),"polkit denegado %s"%r)

# ---- INT: riesgo ----
R=INT.riesgo
ok(R({"accion":"pulsar","nombre":"Aplicar","elemento":"1.0.0"},"Ajustes")is None,"normal")
ok(R({"accion":"pulsar","nombre":"Eliminar archivos"},"x")[0]=="confirmar","borrar confirma")
ok(R({"accion":"pulsar","nombre":"Aceptar"},"Pagar con PayPal")[0]=="confirmar","banca confirma")
ok(R({"accion":"pulsar","nombre":"Instalar"},"Discover")[0]=="confirmar","instalar confirma")
ok(R({"accion":"tecla","combo":"ctrl+alt+supr"})[0]=="negar","ctrl+alt+supr nunca")
ok(R({"accion":"tecla","combo":"alt+f4"})[0]=="confirmar","alt+f4 confirma")
ok(R({"accion":"tecla","combo":"ctrl+s"}) is None,"ctrl+s libre")
ok(R({"accion":"tecla","combo":"blabla"})[0]=="negar","combo raro")
# tecla con kdotool/ydotool simulados
llamadas=[]
kdo=lambda a:"Ajustes — App" if a[0]=="getactivewindow" else ""
print("combo:",INT._combo_normalizado("Ctrl + S"))
ok(INT._combo_normalizado("Ctrl + S")=="ctrl+s","normaliza")
def yd(a): llamadas.append(a); return True,""
t=INT.tecla({"combo":"ctrl+s","ventana":"Ajustes"},kdo,yd)
print(t); ok(llamadas and llamadas[0]==["key","29:1","31:1","31:0","29:0"],"ydotool %s"%llamadas)
llamadas.clear(); t2=INT.tecla({"combo":"ctrl+s","ventana":"Otra cosa"},lambda a:"Ajustes — App" if a[0]=="getactivewindow" else "",yd); ok(not llamadas and "no mando la tecla" in t2,"foco incorrecto no manda %s"%t2)
t=INT.tecla({"combo":"ctrl+s"},lambda a:"",yd); ok("Indica en qué ventana" in t,"tecla sin ventana ni foco")
ok("Esperado" in INT.herramienta({"accion":"esperar","segundos":99}) ,"esperar")
ok("Para pulsar necesito" in INT.pulsar({"accion":"pulsar","nombre":"x"}),"pulsar sin id")

# ---- wrapper del asistente ----
from lina.nucleo import asistente as AS
a=AS.Asistente.__new__(AS.Asistente)
class Ej:
    pend=[]
    def preparar_accion(s,d,f,m="",razon=""): s.pend.append((d,f,razon)); return "PREPARADO: "+razon
a.ejecutor=Ej(); a.en_juego=lambda:False; a.pasos_interfaz=0
INT.activar_accesibilidad=lambda log=print:None
hechos=[]
INT.herramienta=lambda args,ayudante=None:(hechos.append(args) or "Pulsado «x»\ncambios")
AS.ventana_activa=lambda:"Ajustes"
r=a.herramienta_interfaz({"accion":"pulsar","elemento":"1.0.0","nombre":"Aplicar"}); ok(r.startswith("Pulsado") and a.pasos_interfaz==1,"wrapper pulsa %s"%r)
r=a.herramienta_interfaz({"accion":"pulsar","nombre":"Aplicar"}); ok("necesito" in r and a.pasos_interfaz==1,"sin id no cuenta")
n=len(hechos); r=a.herramienta_interfaz({"accion":"pulsar","elemento":"1.0.0","nombre":"Eliminar todo"})
ok(r.startswith("PREPARADO") and len(hechos)==n and a.pasos_interfaz==1,"crítico → pendiente, no ejecuta %s"%r)
a.ejecutor.pend[-1][1](); ok(len(hechos)==n+1 and a.pasos_interfaz==2,"al confirmar se ejecuta y cuenta")
# manos libres: un crítico queda pendiente igual y un «sí» de voz libre no lo ejecuta
a.origen_voz_libre=True; n=len(hechos)
r=a.herramienta_interfaz({"accion":"pulsar","elemento":"1.0.0","nombre":"Eliminar todo"}); ok(r.startswith("PREPARADO") and len(hechos)==n,"manos libres: crítico queda pendiente")
a.origen_voz_libre=False
r=a.herramienta_interfaz({"accion":"tecla","combo":"ctrl+alt+supr","ventana":"x"}); ok("no la mando" in r,"negada")
a.en_juego=lambda:True; r=a.herramienta_interfaz({"accion":"pulsar","elemento":"1.0.0","nombre":"A"}); ok("juego" in r,"en juego no actúa")
ok(a.herramienta_interfaz({"accion":"elementos"})is not None,"leer sí en juego")
a.en_juego=lambda:False; a.pasos_interfaz=15
r=a.herramienta_interfaz({"accion":"pulsar","elemento":"1.0.0","nombre":"A"}); ok("Ya he hecho 15" in r,"tope 15")
AS._abortar.set(); a.pasos_interfaz=0; r=a.herramienta_interfaz({"accion":"pulsar","elemento":"1.0.0","nombre":"A"}); ok("parada" in r,"abortar"); AS._abortar.clear()
g=G.elegir("pulsa el botón de aplicar"); ok("interfaz" in g,"grupo")
ok("pulsar" in str(H.DECLARACIONES[[d["name"] for d in H.DECLARACIONES].index("interfaz")]),"declaración")

# campo que solo se queda con la 1ª letra → reintento por teclado
raro=Dyn("text","Ruta2",est=("SHOWING","ENABLED","EDITABLE"),texto="a"); raro.ed=True
marco.h.append(raro); ir=len(marco.h)-1
orig=raro.get_editable_text_iface
def ed2():
    o=orig(); o.set_text_contents.side_effect=lambda t:(setattr(raro,"t",t[-1:]) or True); return o
raro.get_editable_text_iface=ed2
AT._teclear=lambda acc,t,an:(setattr(acc,"t",t) or True)
r=cli("escribir",id=f"{iapp}.0.{ir}",nombre="Ruta2",texto="/tmp"); ok(r["ok"] and r["despues"]=="/tmp" and r["metodo"]=="teclado","fallback teclado %s"%r)
AT._teclear=lambda *a:False
r=cli("escribir",id=f"{iapp}.0.{ir}",nombre="Ruta2",texto="/usr"); ok(not r["ok"],"no ok si no coincide")
ok("OJO" in INT.escribir({"elemento":"1","nombre":"x","texto":"y"},lambda *a,**k:r),"aviso honesto")

# ---- fase 4: destino por nombre y contexto
marco.h.append(Dyn("label","¿Eliminar 3 archivos permanentemente?",est=("SHOWING","ENABLED")))
A=lambda **k: types.SimpleNamespace(**{**dict(id="",nombre="",rol="",ventana="",texto="",modo="reemplazar"),**k})
c,app_,fr,err=AT.destino(A(nombre="Aplicar",ventana="Ajustes")); ok(c is btn and not err,"destino por ventana+nombre %s"%err)
c,_,_,err=AT.destino(A(nombre="Nada",ventana="Ajustes")); ok(c is None and "No veo ningún control" in err,"destino inexistente")
c,_,_,err=AT.destino(A(nombre="Aplicar",ventana="noexiste")); ok(c is None and err,"ventana inexistente")
c,_,_,err=AT.destino(A()); ok("Hace falta" in err,"sin nada")
r=AT.accion_contexto(A(nombre="Aplicar",ventana="Ajustes")); ok(r["app"]=="ajustes" and any("Eliminar" in t for t in r["textos"]),"contexto %s"%r)
r=cli("pulsar",nombre="Modo oscuro",ventana="Ajustes"); ok(r.get("ok"),"pulsar sin id por ventana %s"%r)
print("FALLOS:",f)
