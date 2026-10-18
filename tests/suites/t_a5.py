# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys, json, tempfile, pathlib
from unittest.mock import MagicMock
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
from lina.nucleo import recetas as R; from lina.nucleo import asistente as A; from lina.nucleo import herramientas as H; from lina.nucleo import grupos as G
d=pathlib.Path(tempfile.mkdtemp()); R.ARCHIVO=d/"r.json"
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
# 1) todas las herramientas están en algún sitio y existen
todas={x["name"] for x in H.DECLARACIONES}
en={t for g in G.GRUPOS.values() for t in g}|set(G.NUCLEO)
ok(todas<=en, f"sin grupo: {todas-en}")
ok(en<=todas, f"grupo con herramienta inexistente: {en-todas}")
# 2) selección
casos={
 "sube el volumen":{"sistema"}, "pon la luz nocturna":{"ajustes_kde"}, "cambia el tamaño de la letra":{"ajustes_kde"},
 "cierra la ventana de Discord":{"sistema"}, "qué juegos tengo en Steam":{"juegos"}, "ponme el mangohud con fps":{"juegos"},
 "escríbeme una carta para mi casero":{"archivos"}, "mueve esto a la papelera, borra el archivo":{"archivos"},
 "cuánto llevo gastado":{"memoria"}, "qué has cambiado hoy":{"memoria"}, "abre Skyrim":set(), "cómo se mata al dragón":set(),
 "cuánto mide la torre eiffel":set(), "desactiva el wifi":{"sistema"}, "reinicia el servicio de bluetooth":{"sistema"},
 "quiero que el reloj salga en 24 horas":set(), "pon el modo oscuro":{"ajustes_kde"},
}
for p,esp in casos.items():
    r=G.elegir(p)
    ok(esp<=r, f"{p!r}: esperaba {esp} y salió {r}")
ok(G.elegir("abre Skyrim")==set(),"abrir no carga nada")
ok(G.elegir("cuánto mide la torre eiffel")==set(),"conocimiento no carga nada")
# seguimiento corto
ok(G.elegir("ahora desactívala",previos={"ajustes_kde"})=={"ajustes_kde"},"seguimiento")
ok(G.elegir("sí",previos={"sistema"})=={"sistema"},"confirmación")
ok("sistema" not in G.elegir("cuéntame un chiste muy largo sobre gatos que viven en Pekín y juegan al fútbol",previos={"sistema"}),"pregunta larga no arrastra")
# recetas
ok(G.grupos_de_receta("kde","")=={"ajustes_kde"},"receta kde")
ok(G.grupos_de_receta("comando","wpctl set-volume")==set(),"receta comando")
ok(G.grupos_de_receta("comando","audio(accion=volumen, valor={valor})")=={"sistema"},"receta de herramienta")
ok(G.elegir("activa la luz nocturna",previos={"sistema"})=={"ajustes_kde"} or G.elegir("activa la luz nocturna",previos={"sistema"})>={"ajustes_kde"} and "sistema" not in G.elegir("activa la luz nocturna",previos={"sistema"}),"no arrastra grupo si ya encaja otro")
# 3) herramientas + meta
lista=G.herramientas(H.DECLARACIONES,set())
nom=[x["name"] for x in lista]
ok(nom[-1]==G.META and "probar_ajuste_kde" not in nom and "ejecutar_comando" in nom,"núcleo")
ok(nom==[x["name"] for x in G.herramientas(H.DECLARACIONES,set())],"orden estable")
cargados=set()
r=G.cargar("ajustes_kde",H.DECLARACIONES,lista,cargados)
ok("probar_ajuste_kde" in {x["name"] for x in lista} and "ajustes_kde" in cargados and "[AJUSTES DE KDE]" in r,"carga en sitio")
n=len(lista); r2=G.cargar("ajustes_kde",H.DECLARACIONES,lista,cargados)
ok(len(lista)==n and "ya estaba" in r2,"no duplica")
ok("No existe" in G.cargar("zzz",H.DECLARACIONES,lista,cargados),"grupo falso")
# 4) por el asistente: la lista que ve Gemini es la misma y mas_herramientas la amplía
a=A.Asistente.__new__(A.Asistente)
a.grupos_previos=set(); a.grupos_turno=set(); a.ids_recetas=[]; a.pregunta_pura="sube el volumen"
g=a.elegir_grupos("x"); ok(g=={"sistema"},f"asistente elegir {g}")
a.herramientas_turno=G.herramientas(H.DECLARACIONES,g); a.grupos_turno=set(g)
ref=a.herramientas_turno
a.busquedas_turno=0; a.ejecutor=MagicMock()
res=a._ejecutar_herramienta("mas_herramientas",{"grupo":"juegos"})
ok(ref is a.herramientas_turno and "mangohud" in {x["name"] for x in ref} and "[JUEGOS]" in res,"asistente carga en sitio")
# usar_receta con receta kde carga ajustes_kde
R.aprender_kde("luz nocturna","night light","activa luz nocturna","kwinrc",["NightColor"],"Active","true","kcm_nightlight","Horas","Amanecer")
rid=R.listar.__doc__ and None
import json as J
rid=J.loads(R.ARCHIVO.read_text())[0]["id"] if R.ARCHIVO.exists() else None
res=a._ejecutar_herramienta("usar_receta",{"id":rid})
ok("probar_ajuste_kde" in {x["name"] for x in ref},"usar_receta carga ajustes_kde")
# 5) tamaños
def tok(n): return n/3.6
def total(grupos):
    l=G.herramientas(H.DECLARACIONES,grupos)
    s=G.sistema(A.INSTRUCCIONES,H.hechos_sistema(),G.ordenar(grupos))
    return len(s),len(json.dumps(l,ensure_ascii=False))
for etiqueta,gs in [("solo núcleo",set()),("sistema",{"sistema"}),("ajustes_kde",{"ajustes_kde"}),("todo",set(G.GRUPOS))]:
    s,t=total(gs); print(f"{etiqueta:12s} sistema={s:6d} chars  herramientas={t:6d} chars  ≈{int(tok(s+t))} tokens")
print("TODO OK" if not f else f"{f} FALLOS")
