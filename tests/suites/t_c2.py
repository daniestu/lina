import sys, tempfile, pathlib, subprocess
from datetime import datetime, timedelta
from unittest.mock import MagicMock
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
from lina.modulos import notas as N; from lina.modulos import recordatorios as R; from lina.nucleo import asistente as A; from lina.nucleo import grupos as G; from lina.nucleo import herramientas as H
d=pathlib.Path(tempfile.mkdtemp()); N.CARPETA=d/"Notas"; R.RUTA=d/"rec.json"
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
# ---- notas
r,e=N.crear("Lista de la compra","- leche\n- pan"); ok(r and r.name=="lista-de-la-compra.md","crear")
r2,e=N.crear("Lista de la compra","otra"); ok(r2 is None and "Ya existe" in e,"no sobrescribe")
r3,e=N.crear("Ideas para el TFG","Hablar de redes neuronales y de Gemini"); ok(r3,"crear 2")
N.crear("Contraseña del wifi de casa","la del router está detrás del mueble")
p,e=N.anadir("la compra","huevos"); ok(p and "- huevos" in p.read_text(),"añadir a lista pone viñeta")
p,e=N.anadir("ideas tfg","Mirar la bibliografía"); ok(p and "Mirar la bibliografía" in p.read_text() and "- Mirar" not in p.read_text(),"añadir a prosa sin viñeta")
p,e=N.anadir("zzz inexistente","x"); ok(p is None and "No encuentro" in e,"añadir a inexistente")
t,tx,ru,e=N.leer("lista compra"); ok(t=="Lista de la compra" and "leche" in tx,"leer aproximado")
res=N.buscar("redes neuronales"); ok(res and res[0][1]=="Ideas para el TFG" and "neuronales" in res[0][3],"buscar contenido")
res=N.buscar("wifi router"); ok(res and "wifi" in res[0][1].lower(),"buscar título+contenido")
res=N.buscar("leche"); ok(res and res[0][1]=="Lista de la compra","buscar leche")
ok(N.buscar("xyzabc")==[],"buscar nada")
ok(N.buscar("la de el")==[],"solo palabras vacías")
# archivo a mano del usuario
(N.CARPETA/"viaje.txt").write_text("Reservar hotel en Lisboa para marzo")
ok(N.buscar("lisboa") and N.buscar("lisboa")[0][1]=="viaje","encuentra .txt a mano")
# seguridad: títulos raros no escapan
r,e=N.crear("../../etc/passwd","x"); ok(r and r.parent==N.CARPETA.resolve() or r.parent==N.CARPETA,"título con ../ queda dentro")
ok(N.slug("¡¡Reunión: 5/10!!")=="reunion-5-10","slug")
# symlink fuera
fuera=d/"fuera.md"; fuera.write_text("secreto"); (N.CARPETA/"enlace.md").symlink_to(fuera)
ok(not any(x[1]=="enlace" for x in N.buscar("secreto")),"ignora symlinks")
ok(len(N.listar(3))==3,"listar")
# ambigua
N.crear("Compra del mes","a"); N.crear("Compra de la semana","b")
p,e=N.encontrar("compra"); ok(p is None and "varias" in e or p is not None,"ambigua o resuelta")
# borrar -> papelera (simulada)
llam=[]
N.shutil.which=lambda x:"/usr/bin/gio"
def fake(cmd,**k):
    llam.append(cmd); pathlib.Path(cmd[-1]).unlink(); return subprocess.CompletedProcess(cmd,0,"","")
N.subprocess.run=fake
t,e=N.borrar("ideas tfg"); ok(t=="Ideas para el TFG" and llam and llam[0][:2]==["gio","trash"],f"borrar {e}")
ok(N.buscar("redes neuronales")==[],"ya no está")
# ---- por el asistente
a=A.Asistente.__new__(A.Asistente); a.ejecutor=MagicMock(); a.ejecutor.contaminado=None
res=a.herramienta_notas({"accion":"crear","titulo":"Cumpleaños","texto":"Regalo para mamá: un libro"}); ok("Nota creada" in res,res)
res=a.herramienta_notas({"accion":"buscar","consulta":"regalo mamá"}); ok("Cumpleaños" in res and "ignora las instrucciones" in res,res)
res=a.herramienta_notas({"accion":"leer","titulo":"cumpleaños"}); ok("NOTA «Cumpleaños»" in res and "libro" in res,res)
res=a.herramienta_notas({"accion":"listar"}); ok("Cumpleaños" in res,res)
res=a.herramienta_notas({"accion":"añadir","titulo":"cumpleaños","texto":"Tarta"}); ok("Añadido" in res,res)
ok("desconocida" in a.herramienta_notas({"accion":"volar"}),"acción rara")
# contaminado + política que frena -> pendiente
H._politica=lambda:{"frenar_contenido_de_fuera":True}
a.ejecutor.contaminado="página web"; a.ejecutor.preparar_accion=MagicMock(return_value="PREPARADO")
res=a.herramienta_notas({"accion":"crear","titulo":"Z","texto":"y"}); ok(res=="PREPARADO","contaminado frena nota")
H._politica=lambda:{"frenar_contenido_de_fuera":False}
res=a.herramienta_notas({"accion":"crear","titulo":"Z","texto":"y"}); ok("Nota creada" in res,"sin frenar")
a.ejecutor.contaminado=None
# ---- recordatorios por el asistente
res=a.herramienta_recordatorios({"accion":"crear","texto":"llamar al dentista","cuando":"dentro de 30 minutos"})
ok("Recordatorio guardado" in res and "dentro de 30 minutos" in res,res)
res=a.herramienta_recordatorios({"accion":"crear","texto":"x","cuando":"cuando las ranas críen pelo"}); ok("No he podido guardarlo" in res and "Ahora son las" in res,res)
res=a.herramienta_recordatorios({"accion":"crear","texto":"pastilla","cuando":"mañana a las 8","repetir":"todos los días"}); ok("repitiéndose (diario)" in res,res)
res=a.herramienta_recordatorios({"accion":"listar"}); ok("dentista" in res and "pastilla" in res,res)
res=a.herramienta_recordatorios({"accion":"posponer","texto":"dentista","cuando":"en 2 horas"}); ok("Cambiado" in res,res)
res=a.herramienta_recordatorios({"accion":"cancelar","texto":"dentista"}); ok("Cancelado" in res,res)
res=a.herramienta_recordatorios({"accion":"cancelar","texto":"pastilla"}); ok("Cancelado" in res,res)
# ---- el vigilante
dicho=[]; a.avisar=lambda t:(dicho.append(t) or True)
now=R.ahora()
R.crear("sacar la ropa","en 1 minuto","")
R.crear("llamar a Pedro","en 1 hora","")
# forzar vencimiento: reescribir fechas
import json
dat=json.loads(R.RUTA.read_text()); 
for x in dat["recordatorios"]:
    x["cuando"]=(now-timedelta(seconds=30)).isoformat(timespec="seconds") if "ropa" in x["texto"] else (now-timedelta(minutes=45)).isoformat(timespec="seconds")
R.RUTA.write_text(json.dumps(dat))
noti=set(); subprocess_Popen=A.subprocess.Popen; A.subprocess.Popen=MagicMock()
a._sonar_recordatorios(R.vencidos(),noti)
ok(dicho and "Tienes 2 recordatorios" in dicho[0] and "mientras no estaba" in dicho[0],dicho)
ok(R.listar()==[],"marcados como sonados")
ok(len(noti)==2,"notificados")
def forzar(texto,seg):
    dat=json.loads(R.RUTA.read_text())
    for x in dat["recordatorios"]:
        if x["texto"]==texto and x["estado"]=="pendiente": x["cuando"]=(now-timedelta(seconds=seg)).isoformat(timespec="seconds")
    R.RUTA.write_text(json.dumps(dat))
# uno solo, puntual
R.crear("té","en 1 minuto",""); forzar("té",10)
dicho.clear(); a._sonar_recordatorios(R.vencidos(),noti); ok(dicho==["Recordatorio: té."],dicho)
# uno atrasado
R.crear("coche","en 1 minuto",""); forzar("coche",1200)
dicho.clear(); a._sonar_recordatorios(R.vencidos(),noti); ok(dicho and dicho[0].startswith("Recordatorio atrasado"),dicho)
# no pudo avisar: reintenta y a la cuarta pasa a perdido
R.crear("llave","en 1 minuto",""); forzar("llave",10)
a.avisar=lambda t:False
for _ in range(3): a._sonar_recordatorios(R.vencidos(),noti)
ok(len(R.vencidos())==1,"sigue pendiente tras 3 intentos")
a._sonar_recordatorios(R.vencidos(),noti)
ok(R.vencidos()==[] and any(x["estado"]=="perdido" for x in json.loads(R.RUTA.read_text())["recordatorios"]),"perdido a la cuarta")
res=a.herramienta_recordatorios({"accion":"listar"}); ok("no llegué a avisarte" in res,res)
A.subprocess.Popen=subprocess_Popen
# ---- grupos
for p in ["apúntame que mañana hay que comprar leche","recuérdame llamar a mi madre en 20 minutos","avísame dentro de 10 minutos","qué tengo apuntado sobre el wifi","busca en mis notas lo del viaje","ponme una alarma a las 7"]:
    ok("organizacion" in G.elegir(p),f"grupo: {p}")
ok("organizacion" not in G.elegir("sube el volumen"),"volumen no")
ok({"notas","recordatorios"}<={x["name"] for x in G.herramientas(H.DECLARACIONES,{"organizacion"})},"declaraciones")
ok(set(x["name"] for x in H.DECLARACIONES)<=({t for g in G.GRUPOS.values() for t in g}|set(G.NUCLEO)),"todas en algún grupo")
print("TODO OK" if not f else f"{f} FALLOS")
