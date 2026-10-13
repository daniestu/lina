import sys, math
from lina.escritorio import interfaz_vision as V
class Raton:
    """Aceleración que depende del tamaño del empujón y distinta por eje, con redondeo a enteros del puntero."""
    def __init__(s,x,y,perfil): s.x,s.y,s.f,s.n=float(x),float(y),perfil,0
    def pos(s):
        if getattr(s,"lag",False) and random.random()<0.4: return s.ult
        s.ult=(round(s.x),round(s.y)); return s.ult
    def yd(s,a):
        if a[0]!="mousemove": return True,""
        dx,dy=int(a[2]),int(a[4]); m=math.hypot(dx,dy); k=s.f(m)
        s.x+=dx*k[0]; s.y+=dy*k[1]; s.n+=1; return True,""
import random
random.seed(3)
perfiles={
 "ruido":lambda m:(random.uniform(0.7,1.5),random.uniform(0.7,1.5)),
 "suave":lambda m:(min(3.0,0.4+m/30),min(3.0,0.4+m/30)),
 "plano":lambda m:(1.0,1.0),
 "acel":lambda m:(0.45,0.45) if m<8 else (1.0,1.0) if m<25 else (2.2,2.2),
 "dura":lambda m:(0.3,0.3) if m<12 else (1.9,1.9) if m<60 else (3.0,3.0),
 "ejes":lambda m:(1.3*(0.5 if m<10 else 1.0),0.8*(0.5 if m<10 else 1.6)),
 "escala1.3":lambda m:(1.3,1.3),
}
mal=0
for nombre,p in perfiles.items():
    for (a,b) in (((2642,719),(984,332)),((984,332),(2954,775)),((100,100),(103,98)),((3000,1000),(10,10))):
        r=Raton(*a,p); r.ult=a; r.lag=(nombre in ("acel","suave","ruido")); ok,det=V.mover_puntero(*b,pos=r.pos,yd=r.yd,pausa=0,kdo=None)
        e=max(abs(r.pos()[0]-b[0]),abs(r.pos()[1]-b[1]))
        if e>2: mal+=1; print("FALLO",nombre,a,b,"error",e,"pasos",r.n)
print("FALLOS:",mal)
