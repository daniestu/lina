import sys, tempfile, pathlib
from unittest.mock import MagicMock
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
from lina.nucleo import recetas as R; from lina.nucleo import asistente as A; from lina.nucleo import herramientas as H; from lina.nucleo import ejecucion as EJ
d=pathlib.Path(tempfile.mkdtemp()); R.ARCHIVO=d/"r.json"
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
# receta demostrada
R.aprender_kde("luz nocturna","night light","activa luz nocturna","kwinrc",["NightColor"],"Active","true","kcm_nightlight","Horas de cambio","Amanecer y anochecer")
ok(R.probada_kde("kwinrc",["NightColor"],"Active","kcm_nightlight") is not None,"probada")
ok(R.probada_kde("kwinrc",["NightColor"],"Mode","kcm_nightlight") is None,"otra clave no")
ok(R.probada_kde("kwinrc",["NightColor"],"Active","kcm_otro") is None,"otro panel no")

a=A.Asistente.__new__(A.Asistente)
lecturas={"antes":0,"despues":0}
a._leer_panel_antes=lambda panel,preg:(lecturas.__setitem__("antes",lecturas["antes"]+1) or ("Siempre desactivadas",None))
a._claves=lambda x:["k"]
a._recargar_interno=lambda c,m:"ok"
a.pregunta_pura="activa la luz nocturna"
vistos={"texto":"Amanecer y anochecer"}
def vp(claves,preg,n): lecturas["despues"]+=1; return vistos["texto"],None
A._ver_pantalla=vp
ej=MagicMock(); ej.contaminado=False; ej.duda=""; ej.efecto_sin_comprobar=False
ej.herramienta=lambda x:"código de salida: 0\n"
ej.deshacer=lambda i:"Deshecho: x"
a.ejecutor=ej; a.modo_privado=False
H._validar_panel_kde=lambda c:None
import shutil; _w=shutil.which; shutil.which=lambda n,*x,**k:"/usr/bin/"+n if n.startswith("k") else _w(n,*x,**k)
EJ._ejecutar_simple=lambda argv,**k:(0,"false")
args={"archivo":"kwinrc","grupos":["NightColor"],"clave":"Active","valor":"true","panel":"kcm_nightlight","control":"Horas de cambio","esperado":"Amanecer y anochecer","ajuste":"luz nocturna"}
r=a.probar_ajuste_kde(dict(args)); print(r[:260])
ok(lecturas=={"antes":0,"despues":1},"con receta: sin lectura previa %s"%lecturas)
ok("COMPROBADO EN PANTALLA" in r and "Receta ya probada" in r,"mensaje")
ok(R.probada_kde("kwinrc",["NightColor"],"Active","kcm_nightlight")["exitos"]>=2,"suma acierto")
# valor ya en el archivo
EJ._ejecutar_simple=lambda argv,**k:(0,"true")
lecturas.update(antes=0,despues=0); r=a.probar_ajuste_kde(dict(args)); ok("quizá ya estaba así" in r,"avisa que ya estaba: "+r[-200:])
# la receta falla: se comprueba después y no se da por bueno
vistos["texto"]="Siempre desactivadas"; EJ._ejecutar_simple=lambda argv,**k:(0,"false")
r=a.probar_ajuste_kde(dict(args)); ok("COMPROBADO EN PANTALLA" not in r and ("NO TUVO EFECTO" in r or "REVERTIDO" in r),"fallo detectado: "+r[:120])
ok(R.probada_kde("kwinrc",["NightColor"],"Active","kcm_nightlight") is None,"tras fallar ya no es 'probada'")
# sin receta: sigue leyendo antes
vistos["texto"]="Amanecer y anochecer"
args2=dict(args,clave="Otra"); lecturas.update(antes=0,despues=0); r=a.probar_ajuste_kde(args2); ok(lecturas["antes"]==1,"sin receta lee antes")
print("fallos",f)
