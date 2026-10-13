import sys, os, json, types, tempfile, pathlib, time
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa); os.environ["XDG_DATA_HOME"]=str(casa/"share")
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
from lina.escritorio import interfaz as INT
estado={"checked":False}
lista="""org.kde.dolphin-2714      2714 dolphin usuario :1.85 session-3.scope session-3 -
org.freedesktop.FileManager1 2714 dolphin usuario :1.85 session-3.scope session-3 -
org.kde.kded6             900 kded6 usuario :1.5 x y -
:1.85                     2714 dolphin usuario :1.85 session-3.scope session-3 -"""
arbol="\n".join(["/","/dolphin","/dolphin/Dolphin_1","/dolphin/Dolphin_1/actions","/dolphin/Dolphin_1/actions/show_hidden_files","/dolphin/Dolphin_1/actions/file_quit","/dolphin/Dolphin_1/actions/view_mode"])
def getall(ruta):
    if ruta.endswith("show_hidden_files"): return f'a{{sv}} 5 "autoRepeat" b true "checkable" b true "checked" b {"true" if estado["checked"] else "false"} "enabled" b true "text" s "Mostrar archivos &ocultos"'
    if ruta.endswith("file_quit"): return 'a{sv} 4 "checkable" b false "checked" b false "enabled" b true "text" s "&Salir"'
    return 'a{sv} 4 "checkable" b false "checked" b false "enabled" b false "text" s "Modo de vista \\"x\\""'
disparos=[]
def bus(args,ejecutar=None,timeout=5):
    if args[0]=="list": return 0,lista
    if args[0]=="tree": return (0,arbol) if args[-1]=="org.kde.dolphin-2714" else (0,"/\n/org/freedesktop/FileManager1")
    if args[0]=="call" and args[3]=="org.freedesktop.DBus.Properties": return 0,getall(args[2])
    if args[0]=="call" and args[-1]=="trigger":
        disparos.append(args[2]); 
        if args[2].endswith("show_hidden_files") and not os.environ.get("NO_CAMBIA"): estado["checked"]=not estado["checked"]
        return 0,""
    return 1,""
arbol_dibujado="""└─/dolphin
  └─/dolphin/Dolphin_1
    ├─/dolphin/Dolphin_1/actions
    │ ├─/dolphin/Dolphin_1/actions/show_hidden_files
    │ ├─/dolphin/Dolphin_1/actions/file_quit
    │ └─/dolphin/Dolphin_1/actions/view_mode"""
kdo=lambda a:"2714" if a[-1]=="getwindowpid" else ("" if a[0]=="search" else "x")
INT.time.sleep=lambda *_:None
sv,raiz,err=INT.servicio_de("",kdo,bus); ok(sv=="org.kde.dolphin-2714" and raiz=="/dolphin/Dolphin_1","servicio %s %s"%(sv,err))
t=INT.acciones({"filtro":"ocultos"},kdo,bus); ok("show_hidden_files" in t and "desmarcada" in t and "Mostrar archivos ocultos" in t,t)
t=INT.acciones({"filtro":"hidden"},kdo,bus); ok("show_hidden_files" in t,"filtro por id en inglés")
t=INT.acciones({"filtro":"zzz"},kdo,bus); ok("Ninguna acción" in t,"sin resultados")
INT._CACHE_ACC.clear()
# ya está como se pide → no toca
t=INT.accionar({"nombre":"show_hidden_files","estado":"desmarcar"},kdo,bus); ok("ya estaba" in t and not disparos,"idempotente: "+t)
t=INT.accionar({"nombre":"show_hidden_files","estado":"marcar"},kdo,bus); ok(t.startswith("Accionado") and "Verificado" in t and estado["checked"] and len(disparos)==1,"marca: "+t)
INT._CACHE_ACC.clear()
t=INT.accionar({"nombre":"ocultos","estado":"marcar"},kdo,bus); ok("ya estaba marcada" in t and len(disparos)==1,"por texto, ya marcada: "+t)
INT._CACHE_ACC.clear()
t=INT.accionar({"nombre":"show_hidden_files","estado":"desmarcar"},kdo,bus); ok("ahora desmarcada" in t and not estado["checked"],"desmarca: "+t)
# no cambia → OJO
INT._CACHE_ACC.clear(); os.environ["NO_CAMBIA"]="1"
t=INT.accionar({"nombre":"show_hidden_files","estado":"marcar"},kdo,bus); ok(t.startswith("OJO"),"detecta que no cambió: "+t); del os.environ["NO_CAMBIA"]
INT._CACHE_ACC.clear()
t=INT.accionar({"nombre":"view_mode"},kdo,bus); ok("desactivada" in t,"desactivada: "+t)
t=INT.accionar({"nombre":"file_quit","estado":"marcar"},kdo,bus); ok("no es un interruptor" in t,"no interruptor")
t=INT.accionar({"nombre":"nada"},kdo,bus); ok("No hay ninguna acción" in t,"inexistente")
# riesgo
ok(INT.riesgo({"accion":"accionar","nombre":"file_quit Salir"},"Dolphin",{"app":"org.kde.dolphin-2714"})[0]=="confirmar","salir confirma")
ok(INT.riesgo({"accion":"accionar","nombre":"show_hidden_files Mostrar archivos ocultos"},"Dolphin",{"app":"org.kde.dolphin-2714"}) is None,"ocultos libre")
ok(INT.riesgo({"accion":"accionar","nombre":"x"},"Konsole",{"app":"org.kde.konsole-1"})[0]=="negar","konsole negada")
ok(INT.riesgo({"accion":"accionar","nombre":"edit_delete Eliminar"},"Dolphin",{})[0]=="confirmar","eliminar confirma")
def bus_viejo(args,**k):
    if args[0]=="tree" and "--list" in args: return 1,""
    if args[0]=="tree": return 0,arbol_dibujado
    return bus(args)
INT._CACHE_ACC.clear(); sv,raiz,err=INT.servicio_de("",kdo,bus_viejo); ok(sv and raiz=="/dolphin/Dolphin_1","árbol dibujado %s %s"%(sv,err))
# sin acciones
bus2=lambda args,**k:(0,lista) if args[0]=="list" else (0,"/")
sv,_,err=INT.servicio_de("",kdo,bus2); ok(sv is None and "no publica" in err,"programa sin acciones")

# wrapper
from lina.nucleo import asistente as AS; from lina.nucleo import herramientas as H; from lina.nucleo import recetas as REC
a=AS.Asistente.__new__(AS.Asistente)
class Ej:
    pend=[]; duda=""; efecto_sin_comprobar=False; receta_turno=False
    def preparar_accion(s,d,fn,m="",razon=""): s.pend.append((d,fn,razon)); return "PREPARADO: "+razon
    def duda_corta(s): return ""
a.ejecutor=Ej(); a.en_juego=lambda:False; a.pasos_interfaz=0; a.pasos_receta=[]; a.obstaculo=""; a.pregunta_pura="muestra los archivos ocultos"
AS.ventana_activa=lambda:"Carpeta — Dolphin"; INT.activar_accesibilidad=lambda log=print:None
INT.resolver_accion=lambda args:("org.kde.dolphin-2714",args["nombre"],{"texto":"Mostrar archivos ocultos" if "hidden" in args["nombre"] else "Salir","ruta":"/x"},"")
rr={"r":"Accionado «Mostrar archivos ocultos»: antes desmarcada, ahora marcada. Verificado por el estado del propio programa."}
def herr(args,ayudante=None):
    INT.ULTIMO.clear(); INT.ULTIMO.update(accion=args["accion"],ventana="dolphin",nombre=args.get("nombre",""),estado=args.get("estado",""),app="org.kde.dolphin-2714")
    return rr["r"]
INT.herramienta=herr
r=a.herramienta_interfaz({"accion":"accionar","nombre":"show_hidden_files","estado":"marcar","ventana":"dolphin"})
ok(r.startswith("Accionado") and a.pasos_receta and a.pasos_receta[0]["accion"]=="accionar" and a.pasos_receta[0]["estado"]=="marcar" and a.ejecutor.efecto_sin_comprobar is False,"wrapper accionar verificado %s %s"%(r,a.pasos_receta))
a.pasos_receta=[a.pasos_receta[0]]
g=a._guardar_receta_interfaz({"ajuste":"mostrar archivos ocultos en Dolphin","comprobar":"estado marcado"}); a._cerrar_receta_interfaz(True)
nota,ids=REC.ofrecer("muestra los archivos ocultos"); ok(ids and "interfaz(accionar" in nota and "estado=marcar" in nota,"receta de accionar: %s"%nota)
r=a.herramienta_interfaz({"accion":"accionar","nombre":"file_quit","ventana":"dolphin"}); ok(r.startswith("PREPARADO"),"salir → confirmar")
rr["r"]="«Mostrar archivos ocultos» ya estaba marcada: no he tocado nada."
a.obstaculo=""; r=a.herramienta_interfaz({"accion":"accionar","nombre":"show_hidden_files","estado":"marcar","ventana":"dolphin"}); ok(a.obstaculo=="","no tocar nada no es fallo")
ok("Para accionar necesito" in a.herramienta_interfaz({"accion":"accionar"}),"sin nombre")
# tecla repetida
rr["r"]="Mandado ctrl+h a «Dolphin»."
a.herramienta_interfaz({"accion":"tecla","combo":"ctrl+h","ventana":"dolphin"}); 
r=a.herramienta_interfaz({"accion":"tecla","combo":"ctrl+h","ventana":"dolphin"}); ok("Ya mandaste esa misma tecla" in r,"repetida bloqueada: %s"%r)
rr["r"]="Controles..."; a.herramienta_interfaz({"accion":"elementos"})
rr["r"]="Mandado ctrl+h a «Dolphin»."; r=a.herramienta_interfaz({"accion":"tecla","combo":"ctrl+h","ventana":"dolphin"}); ok(r.startswith("Mandado"),"tras mirar se permite")
d=[x for x in H.DECLARACIONES if x["name"]=="interfaz"][0]; ok("accionar" in str(d) and "estado" in str(d),"declaración")
print("FALLOS:",f)
