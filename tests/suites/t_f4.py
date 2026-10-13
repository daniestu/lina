import sys, os, json, types, tempfile, pathlib
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa); os.environ["XDG_DATA_HOME"]=str(casa/"share")
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
from lina.escritorio import interfaz as INT; from lina.nucleo import recetas as REC
R=INT.riesgo
# terminales y lanzadores
ok(R({"accion":"escribir","nombre":"x","ventana":"Konsole"},"~ : fish — Konsole")[0]=="negar","terminal negada")
ok(R({"accion":"tecla","combo":"enter","ventana":"Konsole"},"")[0]=="negar","tecla en terminal negada")
ok(R({"accion":"pulsar","nombre":"Copiar"},"Dolphin",{"app":"alacritty","ventana":"alacritty"})[0]=="negar","por contexto")
ok(R({"accion":"tecla","combo":"alt+f2","ventana":"x"},"x")[0]=="confirmar","alt+f2 confirma")
ok(R({"accion":"pulsar","nombre":"Atrás"},"Descargas — Dolphin",{"app":"dolphin","ventana":"Descargas","textos":["3 elementos"]}) is None,"normal libre")
# diálogo que habla de borrar
ctx={"app":"dolphin","ventana":"Confirmar","textos":["¿Quieres eliminar 3 archivos permanentemente?"]}
ok(R({"accion":"pulsar","nombre":"Aceptar"},"Confirmar",ctx)[0]=="confirmar","Aceptar en diálogo de borrar")
ok(R({"accion":"pulsar","nombre":"Cancelar"},"Confirmar",ctx) is None,"Cancelar libre")
ok(R({"accion":"pulsar","nombre":"Aceptar"},"Confirmar",{"textos":["Guardar cambios en la configuración"]}) is None,"Aceptar inocuo libre")
ok(R({"accion":"pulsar","nombre":"Sí"},"Aviso",{"textos":["Esta acción no se puede deshacer"]})[0]=="confirmar","no se puede deshacer")
# contexto/pulsar sin id vía ayudante falso
llam=[]
def ayu(*a):
    llam.append(a)
    if a[0]=="contexto": return {"app":"dolphin","ventana":"Descargas","textos":["x"]}
    if a[0]=="pulsar": return {"ok":True,"accion":"click","elemento":"Atrás","rol":"botón","ventana":"Descargas","app":"dolphin","modal":False,"cambios":{}}
    if a[0]=="escribir": return {"ok":True,"elemento":"Ruta","rol":"campo de texto","ventana":"Descargas","app":"dolphin","antes":"a","despues":"-5","metodo":"accesibilidad"}
ok(INT.contexto({"nombre":"Atrás","ventana":"dolphin"},ayu)["app"]=="dolphin","contexto")
r=INT.pulsar({"nombre":"Atrás","ventana":"dolphin"},ayu); ok(r.startswith("Pulsado") and INT.ULTIMO["sin_cambios"] and INT.ULTIMO["app"]=="dolphin","pulsar sin id %s"%r)
ok("--id=" in llam[-1] and "--ventana=dolphin" in llam[-1],"args con =: %s"%(llam[-1],))
r=INT.escribir({"nombre":"Ruta","ventana":"dolphin","texto":"-5"},ayu); ok(r.startswith("Escrito") and "--texto=-5" in llam[-1],"texto que empieza por - ")
ok("necesito" in INT.pulsar({"nombre":"x"},ayu),"sin id ni ventana")

# --- recetas de interfaz
pasos=[{"accion":"tecla","ventana":"dolphin","combo":"ctrl+l"},{"accion":"escribir","ventana":"dolphin","nombre":"Ruta","rol":"campo de texto","texto":"/tmp/fotos"},
       {"accion":"pulsar","ventana":"dolphin","nombre":"Aplicar","rol":"botón"}]
rc=REC.aprender_interfaz("ir a una carpeta en Dolphin","abrir carpeta ruta","ve a la carpeta fotos",pasos,"/tmp/fotos","la barra muestra la ruta")
ok(rc and rc["tipo"]=="interfaz" and rc["pasos"][1]["texto"]=="{valor}","aprende %s"%rc)
nota,ids=REC.ofrecer("ve a la carpeta de dolphin"); ok(ids and "interfaz(escribir" in nota and "{valor}" in nota,"se ofrece: %s"%nota)
ok(REC.aprender_interfaz("x","","",[{"accion":"borrar"}],"","c") is None,"acción rara fuera")
ok(REC.aprender_interfaz("abrir ajustes","","",[{"accion":"pulsar","ventana":"x","nombre":""}],"","c") is None,"pulsar sin nombre fuera")
ok("interfaz" in REC.listar(),"listar")
rc2=REC.aprender_interfaz("ir a una carpeta en Dolphin","","",pasos,"/tmp/fotos","otra vez"); ok(rc2["id"]==rc["id"] and rc2["exitos"]==2,"misma receta suma")
from lina.nucleo import grupos as G
ok(G.grupos_de_receta("interfaz","")=={"interfaz"},"grupo de la receta")
ok("guardar_receta_interfaz" in G.GRUPOS["interfaz"],"herramienta en el grupo")

# --- asistente
from lina.nucleo import asistente as AS; from lina.nucleo import herramientas as H
a=AS.Asistente.__new__(AS.Asistente)
class Ej:
    pend=[]; duda=""; efecto_sin_comprobar=False; receta_turno=False
    def preparar_accion(s,d,fn,m="",razon=""): s.pend.append((d,fn,razon)); return "PREPARADO: "+razon
    def duda_corta(s): return ""
a.ejecutor=Ej(); a.en_juego=lambda:False; a.pasos_interfaz=0; a.pasos_receta=[]; a.pregunta_pura="ve a la carpeta fotos"; a.obstaculo=""
AS.ventana_activa=lambda:"Descargas — Dolphin"; INT.activar_accesibilidad=lambda log=print:None
ctx_actual={}
INT.contexto=lambda args:dict(ctx_actual)
res={"r":"Pulsado «Atrás» (click) en «Descargas» de dolphin."}
def herr(args,ayudante=None):
    INT.ULTIMO.clear(); INT.ULTIMO.update(accion=args["accion"],app="dolphin",ventana="Descargas",nombre=args.get("nombre",""),rol="botón",texto=args.get("texto",""),combo=args.get("combo",""),sin_cambios=True)
    return res["r"]
INT.herramienta=herr
r=a.herramienta_interfaz({"accion":"pulsar","nombre":"Atrás","ventana":"dolphin"}); ok(r.startswith("Pulsado") and a.pasos_receta and a.pasos_receta[0]["ventana"]=="dolphin","pulsa y apunta paso %s"%r)
ok(a.ejecutor.efecto_sin_comprobar is True,"pulsar sin cambios → sin comprobar")
ok("nadie ha comprobado" in a._guardar_receta_interfaz({"ajuste":"ir atrás en Dolphin","comprobar":"x"}),"no guarda sin comprobar")
res["r"]="Controles de Dolphin..."; a.herramienta_interfaz({"accion":"elementos"})
ok(a.ejecutor.efecto_sin_comprobar is False,"elementos comprueba")
g=a._guardar_receta_interfaz({"ajuste":"ir atrás en Dolphin","comprobar":"la ruta cambió"}); ok(g.startswith("Receta anotada") and "ir atrás" not in REC.listar(),g)
a._cerrar_receta_interfaz(False); ok("ir atrás" not in REC.listar(),"no aceptada: descartada")
a._guardar_receta_interfaz({"ajuste":"ir atrás en Dolphin","comprobar":"la ruta cambió"}); a._cerrar_receta_interfaz(True); ok("ir atrás" in REC.listar(),"aceptada: guardada")
a.pasos_receta=[]; ok("ningún paso" in a._guardar_receta_interfaz({"ajuste":"x y","comprobar":"c"}),"sin pasos")
# terminal por contexto → negado, no se ejecuta
ctx_actual.update(app="konsole",ventana="~ : fish — Konsole",textos=[])
n=a.pasos_interfaz; r=a.herramienta_interfaz({"accion":"escribir","nombre":"x","ventana":"konsole","texto":"rm -rf ~"}); ok("terminal" in r.lower() and a.pasos_interfaz==n,"terminal negada en wrapper %s"%r)
# archivos del propio asistente
ctx_actual.update(app="kate",ventana="politica.txt — Kate",textos=[])
ok("propio asistente" in a.herramienta_interfaz({"accion":"escribir","nombre":"Editor","ventana":"kate","texto":"modo=todo"}),"politica.txt protegido")
ctx_actual.clear()
# diálogo de borrar → pendiente
ctx_actual.update(app="dolphin",ventana="Confirmar",textos=["¿Eliminar 3 archivos permanentemente?"])
r=a.herramienta_interfaz({"accion":"pulsar","nombre":"Aceptar","ventana":"dolphin"}); ok(r.startswith("PREPARADO"),"Aceptar en diálogo de borrar → confirmar %s"%r)
ctx_actual.clear()
# fallo → obstáculo; éxito posterior lo quita
res["r"]="No veo ningún control «Zzz» en la ventana"; a.herramienta_interfaz({"accion":"pulsar","nombre":"Zzz","ventana":"dolphin"}); ok(a.obstaculo.startswith("usar la interfaz"),"fallo → obstáculo %s"%a.obstaculo)
res["r"]="Pulsado «Atrás» (click) en «Descargas» de dolphin."; a.herramienta_interfaz({"accion":"pulsar","nombre":"Atrás","ventana":"dolphin"}); ok(a.obstaculo=="","éxito limpia obstáculo")
# dispatch de la herramienta
ok(any(d["name"]=="guardar_receta_interfaz" for d in H.DECLARACIONES),"declarada")
# nueva_tarea reinicia pasos
a.pasos_receta=[1]; 
# fallback por visión si el control no tiene acción
a.pasos_interfaz=0; llamado=[]
a.interfaz_por_vision=lambda args,accion:(llamado.append((args,accion)) or "Clic sobre «Abrir menú»")
res["r"]="«Abrir menú» no tiene una acción de pulsar por accesibilidad (acciones: ninguna). Prueba con la tecla o con la captura de pantalla."
r=a.herramienta_interfaz({"accion":"pulsar","nombre":"Abrir menú","rol":"botón","ventana":"dolphin"}); ok(r.startswith("Clic") and llamado and "Abrir menú" in llamado[0][0]["descripcion"],"fallback visión %s"%r)
# tecla sin ventana usa la activa
yd_l=[]
t=INT.tecla({"combo":"ctrl+h"},lambda a:"Descargas — Dolphin" if a[-1]=="getwindowname" else "",lambda a:(yd_l.append(a) or (True,""))); ok(t.startswith("Mandado") and yd_l,"tecla sin ventana: %s"%t)
print("FALLOS:",f)
