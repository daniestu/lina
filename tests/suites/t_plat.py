import sys, os, tempfile, pathlib, types
from lina.nucleo import plataforma as P
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
for osr,fam in (({"ID":"cachyos","ID_LIKE":"arch"},"arch"),({"ID":"ubuntu","ID_LIKE":"debian"},"debian"),({"ID":"linuxmint","ID_LIKE":"ubuntu debian"},"debian"),
                ({"ID":"fedora"},"fedora"),({"ID":"nobara","ID_LIKE":"fedora"},"fedora"),({"ID":"opensuse-tumbleweed","ID_LIKE":"opensuse suse"},"suse"),
                ({"ID":"pop","ID_LIKE":"ubuntu debian"},"debian"),({"ID":"void"},None),({},None)):
    ok(P.familia_de(osr)==fam,"familia %s → %s"%(osr,P.familia_de(osr)))
# os-release de verdad
d=pathlib.Path(tempfile.mkdtemp())/"os"; d.write_text('# c\nNAME="CachyOS Linux"\nPRETTY_NAME="CachyOS"\nID=cachyos\nID_LIKE="arch"\n')
ok(P.leer_os_release(d)["ID_LIKE"]=="arch" and P.leer_os_release("/no/existe")=={},"os-release")
det=P.detectar(P.leer_os_release(d),{"XDG_CURRENT_DESKTOP":"KDE","XDG_SESSION_TYPE":"wayland"},lambda x:"/usr/bin/"+x)
ok(det["familia"]=="arch" and det["gestor"]=="pacman" and det["tiene_gestor"] and det["escritorio"]=="kde" and det["sesion"]=="wayland" and det["distro"]=="CachyOS","detectar %s"%det)
ok(not P.detectar({"ID":"void"},{},lambda x:None)["tiene_gestor"],"distro desconocida")
# traducción de paquetes
ok(P.nombres_reales(["pygobject","gtk-layer-shell"],"debian")==(["python3-gi","gir1.2-gtklayershell-0.1"],[]),"debian")
ok(P.nombres_reales(["pycairo"],"arch")==(["python-cairo"],[]) and P.nombres_reales(["algo-raro"],"arch")==(["algo-raro"],[]),"arch y nombre libre")
ok(P.nombres_reales(["gtk3","gtk3"],"fedora")==(["gtk3"],[]),"sin duplicados")
ok(P.orden_instalar(["ydotool"],"arch")==["sudo","-n","pacman","-S","--noconfirm","--needed","--noprogressbar","ydotool"],"orden arch")
ok(P.orden_instalar(["ydotool"],"debian")[:5]==["sudo","-n","apt-get","install","-y"],"orden debian")
ok(P.orden_instalar(["ydotool"],"fedora")[2:5]==["dnf","install","-y"] and P.orden_instalar(["ydotool"],"suse")[2]=="zypper" and P.orden_instalar(["x"],None) is None,"fedora/suse/None")
ok(P.manual(["ydotool"],"fedora")=="sudo dnf install -y ydotool" and "gestor" in P.manual(["x"],None),"manual")
# todas las familias tienen todos los paquetes
for n,t in P.PAQUETES.items():
    ok(all(t.get(fm) for fm in P.FAMILIAS),"paquete %s completo"%n)
# instalar
class R:
    def __init__(s,rc=0,out="",err=""): s.returncode=rc; s.stdout=out; s.stderr=err
cmds=[]; logs=[]
def ej(c,**k): cmds.append(c); return R(0)
deb={"familia":"debian","gestor":"apt-get","tiene_gestor":True,"distro":"Ubuntu"}
ok(P.instalar(["pygobject"],logs.append,ej,deb) and cmds[-1]==["sudo","-n","apt-get","install","-y","--no-install-recommends","--no-remove","python3-gi"],"instala en debian %s"%cmds[-1])
ok(not P.instalar(["x"],logs.append,ej,{"familia":None,"tiene_gestor":False,"distro":"Void"}) and any("no reconozco" in l for l in logs),"distro desconocida: avisa")
ok(not P.instalar(["x"],logs.append,ej,{"familia":"arch","gestor":"pacman","tiene_gestor":False,"distro":"A"}),"sin gestor instalado")
m=pathlib.Path(tempfile.mkdtemp())/"m"; n=len(cmds)
ok(P.instalar(["x"],logs.append,ej,deb,m,lambda:10.0) and not P.instalar(["x"],logs.append,ej,deb,m,lambda:20.0),"marca: no repite")
print("FALLOS:",f)
