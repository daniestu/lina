# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys, os, json, tempfile, pathlib
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa)
# Aislado del equipo real: sin las carpetas XDG ni el bus de sesión de quien lo lance, y con las claves en archivo,
# para que la prueba no escriba nada en su llavero del sistema.
for _k in [k for k in os.environ if k.startswith("XDG_") or k == "DBUS_SESSION_BUS_ADDRESS"]:
    del os.environ[_k]
(casa/".config/lina").mkdir(parents=True); (casa/".config/lina/config.toml").write_text('[privacidad]\nalmacen_claves = "archivo"\n', encoding="utf-8")
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
from lina.nucleo import asistente as A; from lina.nucleo import herramientas as H; from lina.nucleo import grupos as G; from lina.mcp import cliente as MC
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
fake=str(pathlib.Path("fake_mcp.py").resolve())
cfg=casa/"mcp.json"
cfg.write_text(json.dumps({"mcpServers":{"fake":{"command":sys.executable,"args":[fake],"palabras":["calculadora"],"autonomas":["entorno"]},
                                         "roto":{"command":"/nonexistent/xx"}}}))
a=A.Asistente.__new__(A.Asistente)
pend=[]
ej=MagicMock(); ej.contaminado=False
ej.preparar_accion=lambda d,fn,m,razon="":(pend.append((d,fn,razon)) or "PENDIENTE")
a.ejecutor=ej; a.grupos_previos=set()
MC.CONFIG=cfg
gestor=MC.Gestor(cfg,casa/"estado.json")
a.mcp=gestor; a._registrar_grupos_mcp(gestor)
ok("mcp_fake" in G.GRUPOS and "mcp_roto" in G.GRUPOS,"grupos registrados %s"%list(G.GRUPOS))
ok("mcp_fake" in a.elegir_grupos("usa la calculadora") if hasattr(a,"elegir_grupos") else True,"regex grupo")
# activar
n0=len(H.DECLARACIONES)
ok(a._activar_mcp("mcp_fake")=="","activar fake")
nombres=[d["name"] for d in H.DECLARACIONES if d["name"].startswith("mcp__")]
print(nombres); ok(len(nombres)==6,"6 herramientas declaradas")
r=a._activar_mcp("mcp_roto"); ok(r!="","roto da error: %r"%r)
ok(set(a._preparar_grupos_mcp({"mcp_fake","mcp_roto","nucleo"}))=={"mcp_fake","nucleo"},"preparar descarta roto")
# llamadas
suma=[n for n in nombres if n.endswith("suma")][0]
r=a.herramienta_mcp(suma,{"a":1,"b":2}); print(r[:200]); ok("RESULTADO" in r and not pend,"solo lectura directo")
ok(ej.contaminar.called,"contamina")
ent=[n for n in nombres if n.endswith("entorno")][0]
r=a.herramienta_mcp(ent,{"nombre":"HOME"}); ok("RESULTADO" in r,"autónoma directa")
err=[n for n in nombres if n.endswith("error")][0]
r=a.herramienta_mcp(err,{}); ok(r=="PENDIENTE" and len(pend)==1,"no lectura pide confirmación")
print(pend[0][2]); print(pend[0][1]()[:150])
r=a.herramienta_mcp("mcp__fake__nada",{}); ok("ya no existe" in r,"inexistente")
# gestor
r=a.herramienta_mcp_servidores({"accion":"listar"}); print(r[:300]); ok("fake" in r,"listar")
r=a.herramienta_mcp_servidores({"accion":"anadir","nombre":"otro","comando":"/nonexistent/zz"})
ok(r=="PENDIENTE","añadir pide confirmación"); r=pend[-1][1](); print(r); ok("No ha funcionado" in r and "otro" not in gestor.conf,"añadir fallido se deshace")
r=a.herramienta_mcp_servidores({"accion":"anadir","nombre":"otro2","comando":sys.executable,"argumentos":[fake]})
r=pend[-1][1](); print(r[:200]); ok("añadido" in r and "mcp_otro2" in G.GRUPOS and any(d["name"].startswith("mcp__otro2") for d in H.DECLARACIONES),"añadir ok")
r=a.herramienta_mcp_servidores({"accion":"anadir","nombre":"x","url":"ftp://a"}); ok("http" in r,"url mala")
r=a.herramienta_mcp_servidores({"accion":"reiniciar","nombre":"fake"}); ok("reiniciado" in r,r)
r=a.herramienta_mcp_servidores({"accion":"quitar","nombre":"otro2"}); ok("quitado" in r and "mcp_otro2" not in G.GRUPOS and not any(d["name"].startswith("mcp__otro2") for d in H.DECLARACIONES),"quitar "+r)
r=a.herramienta_mcp_servidores({"accion":"quitar","nombre":"zzz"}); ok("No hay" in r,"quitar inexistente")
r=a.herramienta_mcp_servidores({"accion":"publicar","destino":"codex"}); ok("config.toml" in r,"publicar codex")
r=a.herramienta_mcp_servidores({"accion":"publicar","destino":"claude_code"}); ok("claude" in r.lower(),"publicar claude code")
a.herramienta_mcp_servidores({"accion":"publicar"}); ok(len(pend)>=3,"publicar desktop pide confirmación")
# orden estable
d1=[d["name"] for d in H.DECLARACIONES]; a._sincronizar_declaraciones_mcp(); ok(d1==[d["name"] for d in H.DECLARACIONES],"orden estable")

# claves
n=len(pend)
r=a.herramienta_mcp_servidores({"accion":"anadir","nombre":"gh","url":"http://127.0.0.1:9/mcp","cabeceras":["Authorization=Bearer ${TOKEN_X}"]})
ok("lina clave TOKEN_X" in r and len(pend)==n,"falta clave: no pide confirmar, da el comando: "+r[:120])
r=a.herramienta_mcp_servidores({"accion":"anadir","nombre":"gh","url":"http://127.0.0.1:9/mcp","cabeceras":["Authorization=Bearer ghp_abcdefghijklmnopqrstu"]})
ok("No escribas claves" in r,"clave real rechazada")
import subprocess
subprocess.run([sys.executable,"-m","lina","clave","TOKEN_X"],input="secreto123\n",text=True,capture_output=True,start_new_session=True)  # sin terminal de control: getpass lee de la entrada y no del teclado real
cl=casa/".config/lina/mcp_claves.env"
ok(cl.exists() and oct(cl.stat().st_mode)[-3:]=="600","archivo 600") 
ok(MC.expandir("Bearer ${TOKEN_X}")=="Bearer secreto123","expandir usa el archivo")
r=a.herramienta_mcp_servidores({"accion":"anadir","nombre":"gh","url":"http://127.0.0.1:9/mcp","cabeceras":["Authorization=Bearer ${TOKEN_X}"]})
ok(r=="PENDIENTE" and "secreto123" not in json.dumps(pend[-1][0]),"con la clave pide confirmación sin enseñarla")
gestor.cerrar()
print("fallos",f)
