# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys, os, json, types, tempfile, pathlib, math
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa)
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
from PIL import Image
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
from lina.escritorio import interfaz_vision as V; from lina.escritorio import interfaz as INT
from lina.nucleo import ajustes as AJ
AJ.actuales(log=lambda m: None).establecer("privacidad", "capturas", "si")          # con permiso para enviar capturas

# --- geometría
kscreen=json.dumps({"outputs":[{"enabled":True,"pos":{"x":0,"y":0},"size":{"width":3840,"height":2160},"scale":1.5},{"enabled":False,"pos":{"x":9,"y":9},"size":{"width":10,"height":10},"scale":1}]})
ej=lambda cmd,**k: types.SimpleNamespace(returncode=0,stdout=kscreen,stderr="")
ok(V.pantallas(ej)==(0,0,2560.0,1440.0),"pantallas %s"%(V.pantallas(ej),))
kd_geo=lambda a: "Window {abc}\n  Position: 100,200\n  Geometry: 800x600" if a[-1]=="getwindowgeometry" else ("Mi App" if a[-1]=="getwindowname" else "")
ok(V.geometria_ventana(kd_geo)==(100,200,800,600),"geometria")
# recorte: captura 3840x2160 (escala 1.5) -> ventana lógica 100,200 800x600 => px 150,300 1200x900
img=Image.new("RGB",(3840,2160),(10,10,10))
rec,caja=V.recortar(img,(100,200,800,600),(0,0,2560.0,1440.0))
ok(rec.size==(1200,900) and caja==(100,200,800.0,600.0),"recorte %s %s"%(rec.size,caja))
# --- localizar con visor falso (dos pasadas: general + ampliación + cruz)
llamadas=[]
def caja(fx,fy,t=40): return [int(fy*1000-t),int(fx*1000-t),int(fy*1000+t),int(fx*1000+t)]
def visor_ok(b64,texto,sistema):
    llamadas.append(sistema[:20])
    if "CRUZ" in sistema: return json.dumps({"correcto":True,"que_hay":"botón"}),None
    if "AMPLIACI" in sistema: return json.dumps({"encontrado":True,"box_2d":caja(0.5,0.5),"etiqueta":"Reproducir","confianza":0.9}),None
    return json.dumps({"encontrado":True,"x":500,"y":250,"etiqueta":"Reproducir","confianza":0.9,"vista":""}),None
loc=V.localizar({"descripcion":"botón Reproducir"},visor_ok,kd_geo,lambda:img,lambda:(0,0,2560.0,1440.0))
ok(loc.get("x")==500 and loc.get("y")==350 and loc["ventana"]=="Mi App" and len(llamadas)==3,"localizar %s %s"%(loc,llamadas))
# la ampliación corrige a un vecino: centro de la caja en fx=.25 de la zona (420 px de ancho en el recorte) => x lógico 430
def visor_corrige(b64,texto,sistema):
    if "CRUZ" in sistema: return json.dumps({"correcto":True}),None
    if "AMPLIACI" in sistema: return json.dumps({"encontrado":True,"box_2d":caja(0.25,0.5),"etiqueta":"Atrás","confianza":0.9}),None
    return json.dumps({"encontrado":True,"x":500,"y":250,"etiqueta":"Adelante","confianza":0.9}),None
loc=V.localizar({"descripcion":"atrás"},visor_corrige,kd_geo,lambda:img,lambda:(0,0,2560.0,1440.0))
ok(loc.get("x")==430 and loc.get("y")==350 and loc["etiqueta"]=="Atrás","afinado por ampliación %s"%loc)
def visor_no(b64,texto,sistema):
    if "CRUZ" in sistema: return json.dumps({"correcto":False,"que_hay":"un icono distinto"}),None
    if "AMPLIACI" in sistema: return json.dumps({"encontrado":True,"box_2d":caja(0.5,0.5),"confianza":0.9}),None
    return json.dumps({"encontrado":True,"x":500,"y":250,"etiqueta":"x","confianza":0.9}),None
r=V.localizar({"descripcion":"algo"},visor_no,kd_geo,lambda:img,lambda:(0,0,2560.0,1440.0)); ok("No estoy seguro" in r.get("error","") and "icono distinto" in r["error"],"cruz mal → no clic %s"%r)
visor_baja=lambda b,t,s:(json.dumps({"encontrado":True,"x":500,"y":500,"confianza":0.3}),None)
r=V.localizar({"descripcion":"algo"},visor_baja,kd_geo,lambda:img,lambda:None); ok("segura" in r.get("error",""),"baja confianza")
def visor_baja2(b,t,s):
    if "AMPLIACI" in s: return json.dumps({"encontrado":True,"box_2d":caja(.5,.5),"confianza":0.2}),None
    return json.dumps({"encontrado":True,"x":500,"y":500,"confianza":0.9}),None
r=V.localizar({"descripcion":"algo"},visor_baja2,kd_geo,lambda:img,lambda:None); ok("Al ampliar" in r.get("error",""),"baja confianza al ampliar %s"%r)
def visor_nf2(b,t,s):
    if "AMPLIACI" in s: return json.dumps({"encontrado":False,"vista":"otra cosa"}),None
    return json.dumps({"encontrado":True,"x":500,"y":500,"confianza":0.9}),None
r=V.localizar({"descripcion":"algo"},visor_nf2,kd_geo,lambda:img,lambda:None); ok("No localizo" in r.get("error",""),"no está al ampliar")
visor_nf=lambda b,t,s:(json.dumps({"encontrado":False,"vista":"un menú"}),None)
r=V.localizar({"descripcion":"algo"},visor_nf,kd_geo,lambda:img,lambda:None); ok("No localizo" in r["error"] and "un menú" in r["error"],"no encontrado")
visor_err=lambda b,t,s:(None,"sin clave")
ok(V.localizar({"descripcion":"a"},visor_err,kd_geo,lambda:img,lambda:None)["error"]=="sin clave","error visor")
visor_fuera=lambda b,t,s:(json.dumps({"encontrado":True,"x":1500,"y":5,"confianza":0.9}),None)
ok("fuera" in V.localizar({"descripcion":"a"},visor_fuera,kd_geo,lambda:img,lambda:None)["error"],"fuera de rango")
ok("Falta describir" in V.localizar({},visor_ok)["error"],"sin descripcion")
ok("capturar" in V.localizar({"descripcion":"a"},visor_ok,kd_geo,lambda:None,lambda:None)["error"],"sin captura")
def visor_grande(b64,texto,sistema): return json.dumps({"encontrado":True,"box_2d":[0,0,900,900],"confianza":0.9}),None
ok("demasiado grande" in V.localizar({"descripcion":"menú"},visor_grande,kd_geo,lambda:img,lambda:None)["error"],"caja enorme rechazada")
# zona ampliada: tamaño y límites
z,(rx,ry,rw,rh)=V._zona_ampliada(Image.new("RGB",(1200,900)),0.0,1.0)
ok(rx==0 and ry+rh==900 and z.width>=1000,"zona en el borde %s"%((rx,ry,rw,rh),))

# --- mover en bucle cerrado con aceleración simulada
class Raton:
    def __init__(s,x,y,acel): s.x,s.y,s.a,s.n=x,y,acel,0
    def pos(s): return (round(s.x),round(s.y))
    def yd(s,a):
        if a[0]=="mousemove":
            dx,dy=int(a[2]),int(a[4]); k=s.a if math.hypot(dx,dy)>20 else 1.0   # aceleración solo en saltos grandes
            s.x+=dx*k; s.y+=dy*k; s.n+=1; return True,""
        if a[0]=="click": s.clics=getattr(s,"clics",[])+[a[1]]; return True,""
        return False,"?"
for acel in (1.0,1.7,0.6):
    m=Raton(50,60,acel); ok_,det=V.mover_puntero(1800,900,pos=m.pos,yd=m.yd,pausa=0,kdo=None)
    ok(ok_ and abs(m.pos()[0]-1800)<=2 and abs(m.pos()[1]-900)<=2,"converge con aceleración %s: %s %s"%(acel,m.pos(),det))
m=Raton(5,5,1); m.yd=lambda a:(True,"")      # no se mueve
ok(not V.mover_puntero(500,500,pos=m.pos,yd=m.yd,pausa=0,kdo=None)[0],"puntero inmóvil → falla")
ok(not V.mover_puntero(5,5,pos=lambda:None,yd=lambda a:(True,""),pausa=0,kdo=None)[0],"sin lectura del puntero → no mueve")
# --- clic
m=Raton(0,0,1.3)
r=V.hacer_clic({"x":300,"y":200,"etiqueta":"Reproducir","ventana":"Mi App"},kdo=lambda a:"Mi App" if a[-1]=="getwindowname" else "",yd=m.yd,pos=m.pos)
ok("Clic sobre «Reproducir»" in r and m.clics==["0xC0"] and abs(m.pos()[0]-300)<=2 and abs(m.pos()[1]-200)<=2,"clic %s %s"%(r,m.pos()))
m=Raton(0,0,1); r=V.hacer_clic({"x":10,"y":10,"etiqueta":"X","ventana":"Mi App"},"derecho",2,kdo=lambda a:"Mi App",yd=m.yd,pos=m.pos); ok(m.clics==["0xC1","0xC1"] and "doble" in r,"doble derecho")
m=Raton(0,0,1); r=V.hacer_clic({"x":10,"y":10,"etiqueta":"X","ventana":"Mi App"},kdo=lambda a:"Otra",yd=m.yd,pos=m.pos); ok("ha cambiado" in r and not hasattr(m,"clics"),"ventana cambió → no clic")
m=Raton(0,0,1); r=V.hacer_clic({"x":10,"y":10,"etiqueta":"X","ventana":"Mi App"},solo_mover=True,kdo=lambda a:"Mi App",yd=m.yd,pos=m.pos); ok("No he hecho clic" in r and not hasattr(m,"clics"),"señalar")

# --- riesgo con clic
ok(INT.riesgo({"accion":"clic","nombre":"botón Reproducir Reproducir"},"Spotify") is None,"clic normal")
ok(INT.riesgo({"accion":"clic","nombre":"botón Comprar ahora"},"Tienda")[0]=="confirmar","clic comprar confirma")
ok(INT.riesgo({"accion":"clic","nombre":"Aceptar"},"Autenticación requerida")[0]=="negar","clic en auth negado")

# --- wrapper del asistente
from lina.nucleo import asistente as AS; from lina.nucleo import herramientas as H; from lina.nucleo import grupos as G
a=AS.Asistente.__new__(AS.Asistente)
class Ej:
    pend=[]
    def preparar_accion(s,d,fn,m="",razon=""): s.pend.append((d,fn,razon)); return "PREPARADO: "+razon
a.ejecutor=Ej(); a.en_juego=lambda:False; a.pasos_interfaz=0; a.modo_privado=False; a.titulo="Mi App"; a.contexto={"clase":"app"}
a._claves=lambda m:["k"]
AS.ventana_activa=lambda:"Mi App"; AS.clase_activa=lambda:"app"; INT.activar_accesibilidad=lambda log=print:None
AS.visor_gemini=lambda *a,**k:("{}",None)
resultado={"loc":{"x":5,"y":6,"etiqueta":"Reproducir","ventana":"Mi App","confianza":0.8}}
AS.VIS.localizar=lambda args,visor:dict(resultado["loc"])
hechos=[]
AS.VIS.hacer_clic=lambda loc,boton="izquierdo",veces=1,solo_mover=False,**k:(hechos.append((loc["etiqueta"],boton,veces,solo_mover)) or "Clic sobre «%s»"%loc["etiqueta"])
r=a.herramienta_interfaz({"accion":"clic","descripcion":"botón Reproducir"}); ok(r.startswith("Clic") and a.pasos_interfaz==1 and hechos[-1][0]=="Reproducir","wrapper clic %s"%r)
r=a.herramienta_interfaz({"accion":"senalar","descripcion":"botón Reproducir"}); ok(hechos[-1][3] is True and a.pasos_interfaz==1,"señalar no cuenta paso")
resultado["loc"]["etiqueta"]="Comprar ahora"; n=len(hechos)
r=a.herramienta_interfaz({"accion":"clic","descripcion":"el botón verde"}); ok(r.startswith("PREPARADO") and len(hechos)==n,"etiqueta crítica → confirmar, sin clic")
a.ejecutor.pend[-1][1](); ok(len(hechos)==n+1 and a.pasos_interfaz==2,"confirmado: clic y cuenta")
resultado["loc"]={"error":"No localizo"}; ok(a.herramienta_interfaz({"accion":"clic","descripcion":"x"})=="No localizo","error de visión pasa")
resultado["loc"]={"x":1,"y":1,"etiqueta":"A","ventana":"Mi App","confianza":0.9}
a.modo_privado=True; ok("modo privado" in a.herramienta_interfaz({"accion":"clic","descripcion":"x"}),"privado: no mira"); a.modo_privado=False
a.en_juego=lambda:True; ok("juego" in a.herramienta_interfaz({"accion":"clic","descripcion":"x"}),"juego: no"); a.en_juego=lambda:False
ok("Describe" in a.herramienta_interfaz({"accion":"clic"}),"sin descripción")
a.pasos_interfaz=15; ok("Ya he hecho 15" in a.herramienta_interfaz({"accion":"clic","descripcion":"x"}),"tope")
a.pasos_interfaz=0; AS.ventana_activa=lambda:"Autenticación requerida — polkit"; ok("contraseñas" in a.herramienta_interfaz({"accion":"clic","descripcion":"Aceptar"}),"auth negado"); AS.ventana_activa=lambda:"Mi App"
# modelos por mirada: general y cruz con el barato, la ampliación con el fuerte
usados=[]
AS.visor_gemini=lambda claves,img,txt,sis,json_salida=False,modelos=None:(usados.append((sis[:15],modelos)) or ("{}",None))
def loc_falso(args,visor):
    for p in (AS.VIS.PROMPT_LOCALIZAR,AS.VIS.PROMPT_REFINAR,AS.VIS.PROMPT_COMPROBAR): visor("x","y",p)
    return dict(resultado["loc"])
AS.VIS.localizar=loc_falso; a.pasos_interfaz=0
a.herramienta_interfaz({"accion":"senalar","descripcion":"botón"})
ok(len(usados)==3 and usados[0][1] == AS.MODELOS_GEMINI and usados[1][1] == AS.MODELOS_PROFUNDO and usados[2][1] == AS.MODELOS_GEMINI,"modelos por mirada %s"%usados)
AS.VIS.localizar=lambda args,visor:dict(resultado["loc"])
d=[x for x in H.DECLARACIONES if x["name"]=="interfaz"][0]; ok("clic" in str(d) and "descripcion" in str(d),"declaración")
ok("interfaz(clic" in G.REGLAS["interfaz"],"reglas")
print("FALLOS:",f)
