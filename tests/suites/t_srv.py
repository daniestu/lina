# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys,os,tempfile
os.environ["HOME"]=tempfile.mkdtemp(); 
from lina.escritorio import interfaz as I
lista="NAME PID PROCESS\n:1.5 100 dolphin\norg.freedesktop.FileManager1 100 dolphin\norg.kde.dolphin-100 100 dolphin\norg.kde.kate-200 200 kate\n"
def bus(a):
    if a[0]=="list": return 0,lista
    if a[0]=="tree": return 0,"/dolphin/Dolphin_1/actions/x\n" if a[-1] in ("org.kde.dolphin-100","org.freedesktop.FileManager1") else "/\n"
    return 1,""
kdo=lambda a: "100" if a[-1]=="getwindowpid" else "1"
f=0
for v in ("","dolphin","org.kde.dolphin-100","Dolphin"):
    r=I.servicio_de(v,kdo,bus)
    if r[0]!="org.kde.dolphin-100": f+=1; print("FALLO",v,r)
if I.servicio_de("kate",kdo,bus)[0] is not None: f+=1; print("FALLO kate sin acciones")
if I._nombre_amigable("org.kde.dolphin-100")!="dolphin": f+=1; print("FALLO amigable")
print("FALLOS:",f)
