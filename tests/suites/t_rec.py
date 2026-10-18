# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys, tempfile, pathlib
from datetime import datetime
from lina.modulos import recordatorios as R
d=pathlib.Path(tempfile.mkdtemp()); R.RUTA=d/"r.json"
REF=datetime(2026,10,9,13,20)   # viernes
f=0
def esp(txt,exp,ref=REF):
    global f
    try: got=R.parse_cuando(txt,ref)
    except ValueError as e: got=f"ERROR {e}"
    exp=datetime.fromisoformat(exp) if isinstance(exp,str) and not exp.startswith("ERR") else exp
    ok = (got==exp) if not isinstance(exp,str) else str(got).startswith(exp)
    if not ok: f+=1; print("FALLO",repr(txt),"->",got,"esperaba",exp)
esp("dentro de 20 minutos","2026-10-09T13:40")
esp("en 20 minutos","2026-10-09T13:40")
esp("en una hora","2026-10-09T14:20")
esp("en media hora","2026-10-09T13:50")
esp("dentro de un cuarto de hora","2026-10-09T13:35")
esp("en 2 horas y media","2026-10-09T15:50")
esp("en una hora y media","2026-10-09T14:50")
esp("dentro de tres días","2026-10-12T13:20")
esp("en 2 semanas","2026-10-23T13:20")
esp("en 90 segundos","2026-10-09T13:21:30")
esp("mañana a las 9","2026-10-10T09:00")
esp("mañana","2026-10-10T09:00")
esp("mañana por la mañana","2026-10-10T09:00")
esp("mañana por la tarde","2026-10-10T17:00")
esp("mañana a las 8 de la tarde","2026-10-10T20:00")
esp("pasado mañana a las 10 y media","2026-10-11T10:30")
esp("hoy a las 18:30","2026-10-09T18:30")
esp("esta noche a las 10","2026-10-09T22:00")
esp("esta tarde","2026-10-09T17:00")
esp("a las 6","2026-10-09T18:00")
esp("a las 14","2026-10-09T14:00")
esp("a las 9","2026-10-09T21:00")
esp("el viernes a las 18:30","2026-10-09T18:30")
esp("el lunes a las 9","2026-10-12T09:00")
esp("el próximo viernes a las 9","2026-10-16T09:00")
esp("el sábado a las 5 de la tarde","2026-10-10T17:00")
esp("el 15 de octubre a las 5 de la tarde","2026-10-15T17:00")
esp("el 15 de octubre","2026-10-15T09:00")
esp("el 3 de enero a las 12","2027-01-03T12:00")
esp("15/10 a las 8","2026-10-15T08:00")
esp("el 20 a las 10","2026-10-20T10:00")
esp("a las ocho y media","2026-10-09T20:30")
esp("a las cinco menos cuarto","2026-10-09T16:45")
esp("a las 7 y cuarto de la mañana","2026-10-10T07:15")
esp("mañana a mediodía","2026-10-10T12:00")
esp("mañana a medianoche","2026-10-11T00:00")
esp("2026-11-01 08:15","2026-11-01T08:15")
esp("ayer a las 9","ERROR")
esp("el 1 de octubre a las 9","2027-10-01T09:00")
esp("blablabla","ERROR No entiendo")
esp("","ERROR")
# domingo/lunes con hoy: el viernes a las 10 (ya pasó hoy) -> siguiente viernes
esp("el viernes a las 10","2026-10-16T10:00")
# repetir
for t,e in [("todos los días","diario"),("cada día","diario"),("de lunes a viernes","laborables"),("entre semana","laborables"),("cada lunes","semanal"),
            ("todas las semanas","semanal"),("cada mes","mensual"),("cada 30 minutos","cada:30:min"),("cada 2 horas","cada:2:h"),("","" ),("no","")]:
    got=R.parse_repetir(t)
    if got!=e: f+=1; print("FALLO repetir",t,got,e)
try: R.parse_repetir("cada 1 minuto"); f+=1; print("FALLO cada minuto")
except ValueError: pass
try: R.parse_repetir("cuando llueva"); f+=1; print("FALLO repetir raro")
except ValueError: pass
# siguiente
from datetime import datetime as D
if R.siguiente(D(2026,10,9,9,0),"laborables",D(2026,10,9,10,0))!=D(2026,10,12,9,0): f+=1; print("FALLO laborables")
if R.siguiente(D(2026,1,31,9,0),"mensual",D(2026,2,1,0,0))!=D(2026,2,28,9,0): f+=1; print("FALLO mensual")
if R.siguiente(D(2026,10,9,9,0),"cada:30:min",D(2026,10,9,10,0))!=D(2026,10,9,10,30): f+=1; print("FALLO cada30")
# humano
for dt,e in [(D(2026,10,9,13,40),"dentro de 20 minutos"),(D(2026,10,9,18,30),"hoy a las 18 y media"),(D(2026,10,10,9,0),"mañana a las 9"),
             (D(2026,10,13,18,15),"el martes a las 18 y cuarto"),(D(2026,10,25,9,5),"el 25 de octubre a las 9 y 5"),(D(2027,1,3,12,0),"el 3 de enero de 2027 a las 12")]:
    g=R.humano(dt,REF)
    if g!=e: f+=1; print("FALLO humano",g,"!=",e)
# guardar / listar / cancelar / posponer / vencidos
a=R.crear("llamar a mi madre","en 10 minutos","",REF)
b=R.crear("sacar la basura","hoy a las 21","diario",REF)
c=R.crear("llamar a mi madre","en 10 minutos","",REF)
if c["id"]!=a["id"]: f+=1; print("FALLO duplicado")
if len(R.listar(REF))!=2: f+=1; print("FALLO listar")
if R.vencidos(D(2026,10,9,13,29)): f+=1; print("FALLO no vencido")
v=R.vencidos(D(2026,10,9,13,31)); 
if [x["id"] for x in v]!=[a["id"]]: f+=1; print("FALLO vencido",v)
R.marcar_sonado(a["id"],D(2026,10,9,13,31))
if any(x["id"]==a["id"] for x in R.listar(REF)): f+=1; print("FALLO sonado sigue pendiente")
R.marcar_sonado(b["id"],D(2026,10,9,21,1))
nb=[x for x in R.listar(REF) if x["id"]==b["id"]][0]
if nb["cuando"]!="2026-10-10T21:00:00": f+=1; print("FALLO repetido",nb)
# persistencia: recargar el módulo
import importlib; ruta=R.RUTA; importlib.reload(R); R.RUTA=ruta
if len(R.listar(REF))!=1: f+=1; print("FALLO persistencia")
r,m=R.posponer("basura","mañana a las 7",REF); 
if not r or r["cuando"]!="2026-10-10T07:00:00": f+=1; print("FALLO posponer",r,m)
canc,m=R.cancelar("basura")
if len(canc)!=1 or R.listar(REF): f+=1; print("FALLO cancelar",canc,m)
R.crear("tomar pastilla","en 1 hora","",REF); R.crear("tomar té","en 2 horas","",REF)
c,m=R.cancelar("tomar"); 
if c or "varios" not in m: f+=1; print("FALLO ambiguo",m)
c,m=R.cancelar("todos"); 
if len(c)!=2: f+=1; print("FALLO todos")
# archivo corrupto
R.RUTA.write_text("{rota"); 
if R.listar(REF)!=[]: f+=1; print("FALLO corrupto")
print("TODO OK" if not f else f"{f} FALLOS")
