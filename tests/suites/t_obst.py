import sys, os, tempfile, pathlib
from unittest.mock import MagicMock
os.environ["HOME"]=tempfile.mkdtemp()
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
from lina.nucleo import asistente as A; from lina.modulos import web as W
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
a=A.Asistente.__new__(A.Asistente)
ej=MagicMock(); ej.contaminado=False; ej.duda=""; ej.pendientes=[]; ej.profundo=False; ej.efecto_sin_comprobar=False
a.ejecutor=ej; a.obstaculo=""; a.pedir_profundo=""; a.insistiendo=False; a.clave="k"; a.acciones_turno=[("leer_web",{"url":"u"},"No he podido leer")]
a.historial=[]; a.t_tarea=0; a._avisar_voz=lambda *x:None; a.pregunta_pura="lee la pagina"
def malo(url): raise W.ErrorWeb("La web no me deja leerla (error 403); puede que pida iniciar sesión o bloquee a los programas.")
W.leer=malo
r=a.leer_web({"url":"https://x.com/p"})
ok("reintentarlo" in r,"aviso: "+r[:300])
ok(a.obstaculo.startswith("leer la página https://x.com/p"),"obstáculo marcado "+a.obstaculo)
visto={}
def fake(grupo,m,pregunta,*args,**kw):
    visto.update(grupo=grupo,m=m,pregunta=pregunta,max_pasos=kw.get("max_pasos")); return "Hecho: las pociones son X."
a._gemini=fake
r,m=a._insistir_si_hace_falta("Según UESP...", "flash-lite", "rapido", "lee la pagina", None, [], "sis")
ok(r.startswith("Hecho"),"usa la respuesta de la reintentada: %r"%r)
ok(visto.get("grupo")=="profundo" and "mcp_servidores" in visto.get("pregunta","") and "NO te rindas" in visto["pregunta"],"nota con el plan")
ok(a.obstaculo=="","obstáculo limpiado")
visto.clear(); a.insistiendo=False; r,m=a._insistir_si_hace_falta("ok","l","rapido","p",None,[],"s"); ok(not visto and r=="ok","sin obstáculo, nada")
# genérico: sin obstáculo previo, por cómo suena la respuesta
for txt,acc,debe in [("No he podido hacerlo porque falta docker.",True,True),("No puedo ayudarte con eso.",False,True),("Listo, he abierto Firefox.",True,False),
                     ("Ha fallado la conexión, comprueba que Chrome esté abierto.",True,True),("Ha fallado en tu código la línea 3.",False,False),("Son las diez y media.",False,False)]:
    ok(A.fracaso_en_respuesta(txt,acc)==debe,"detector: "+txt)
visto.clear(); a.insistiendo=False; a.obstaculo=""; a.acciones_turno=[("ejecutar_comando",{},"x")]
r,m=a._insistir_si_hace_falta("No he podido arrancar el contenedor de docker.","l","rapido","levanta el docker de prueba",None,[],"s")
ok(r.startswith("Hecho") and "docker" in visto.get("pregunta",""),"fracaso genérico reintenta: %r"%visto.get("pregunta","")[:80])
visto.clear(); a.insistiendo=False; r,m=a._insistir_si_hace_falta("No he podido.","l","profundo","p",None,[],"s"); ok(not visto,"en modo profundo no repite")
# revisor
from lina.nucleo import asistente as A2
llamadas=[]
def mini(clave,prompt,esq,cont,val,et):
    llamadas.append(cont); return {"decision":"no_cumplido" if "Según la página" in cont else "cumplido","modelo":"x"}
A._mini_consulta_ia=mini
visto.clear(); a.insistiendo=False; a.obstaculo=""; a.pregunta_pura="lee la página copiada"
a.acciones_turno=[("ejecutar_comando",{"comando":"wl-paste"},"https://x"),("buscar_web",{"consulta":"potions"},"5 resultados")]
r,m=a._insistir_si_hace_falta("Según la página que tienes copiada, hay pociones.","l","rapido","lee la página copiada",None,[],"s")
ok(r.startswith("Hecho") and "no se apoya" in visto.get("pregunta",""),"revisor dispara reintento")
ok("wl-paste" in llamadas[0] and "buscar_web" in llamadas[0],"el revisor ve las acciones")
visto.clear(); a.insistiendo=False; r,m=a._insistir_si_hace_falta("Listo, hecho.","l","rapido","p",None,[],"s"); ok(not visto and r=="Listo, hecho.","cumplido: nada")
a.acciones_turno=[]; llamadas.clear(); a.insistiendo=False; a._insistir_si_hace_falta("Según la página","l","rapido","p",None,[],"s"); ok(not llamadas,"sin acciones no gasta llamada")
print("fallos",f)
