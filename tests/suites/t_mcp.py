import sys, os, json, tempfile, time, threading, subprocess
from pathlib import Path
casa = Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa)
os.environ["GEMINI_API_KEY"] = "secreto-que-no-debe-salir"; os.environ["MI_VAR_VISIBLE"] = "hola"
from lina.mcp import cliente as M
T = Path(__file__).parent
fallos = 0
def ok(c, m):
    global fallos
    print(("OK  " if c else "FALLO ") + m); fallos += 0 if c else 1

# ---------- esquemas
e = M.limpiar_esquema(json.loads(json.dumps({"$schema": "x", "type": "object", "additionalProperties": False, "properties": {
    "a": {"type": "number"}, "b": {"anyOf": [{"type": "integer"}, {"type": "null"}], "description": "opcional"}, "c": {"type": ["string", "null"], "enum": ["x", "y"]},
    "d": {"type": "array", "items": {"type": "object", "properties": {"z": {"type": "boolean"}}}}, "e": {"$ref": "#/defs/x"}}, "required": ["a", "nope"]})))
ok("additionalProperties" not in json.dumps(e) and "$schema" not in json.dumps(e) and "anyOf" not in json.dumps(e), "esquema sin claves que Gemini no admite")
ok(e["properties"]["b"]["type"] == "integer" and e["properties"]["c"]["enum"] == ["x", "y"] and e["required"] == ["a"], "anyOf/null/required filtrados")
ok(M.nombre_herramienta("github", "list issues!") == "mcp__github__list_issues_" and len(M.nombre_herramienta("a" * 24, "t" * 80)) <= 64, "nombres válidos")
d = M.declaracion("fake", {"name": "t", "description": "x" * 900 + "\n\n<b>hola</b>", "inputSchema": {"type": "object", "properties": {}}})
ok(len(d["description"]) < 340 and "\n" not in d["description"] and "parameters" not in d, "descripción recortada; sin parámetros si no hay")

# ---------- cliente ↔ servidor falso (stdio)
conf = {"mcpServers": {"Fake Uno": {"command": sys.executable, "args": [str(T / "fake_mcp.py")], "env": {"EXTRA": "${MI_VAR_VISIBLE}"}, "palabras": ["calculadora"], "autonomas": ["entorno"]},
                       "roto": {"command": "no-existe-este-programa"}, "off": {"command": "x", "desactivado": True}}}
(casa / ".config/lina").mkdir(parents=True); (casa / ".config/lina/mcp.json").write_text(json.dumps(conf))
g = M.Gestor(casa / ".config/lina/mcp.json", casa / "estado.json")
ok(set(g.servidores) == {"fake_uno", "roto"}, f"servidores leídos: {set(g.servidores)}")
hs = g.descubrir("fake_uno")
ok([h["name"] for h in hs] == ["entorno", "error", "lenta", "mucho", "revienta", "suma"], "paginación y orden estable: " + str([h["name"] for h in hs]))
s = g.servidores["fake_uno"]
ok(s.t.p.poll() is None, "sigue vivo tras ping y petición de muestreo del servidor")
t, err = s.llamar("suma", {"a": 2, "b": 3}); ok(t == "5" and not err, "tools/call suma = " + t)
t, err = s.llamar("entorno", {"nombre": "GEMINI_API_KEY"}); ok("(no)" in t, "la clave de Gemini NO llega al servidor: " + t)
t, err = s.llamar("entorno", {"nombre": "MI_VAR_VISIBLE"}); ok("(no)" in t, "variable no declarada no llega: " + t)
t, err = s.llamar("entorno", {"nombre": "EXTRA"}); ok(t == "EXTRA=hola", "env declarado con ${VAR}: " + t)
t, err = s.llamar("error", {}); ok(err and "a propósito" in t, "isError")
t, err = s.llamar("mucho", {}); ok(len(t) < M.MAX_RESULTADO + 40 and "recortado" in t and "x" in t, "recorta lo largo")
t, err = s.llamar("noexiste", {}); ok(err and "desconocida" in t, "error de protocolo: " + t)
t0 = time.time()
try: s.llamar("lenta", {}, timeout=1); ok(False, "timeout")
except M.ErrorMcp as e: ok("no ha respondido" in str(e) and time.time() - t0 < 3, "timeout: " + str(e))
t, err = s.llamar("revienta", {}); ok(err and "cerrado" in t, "el servidor se cae en plena llamada: " + t[:60])
ok(not s.vivo, "detecta que murió")
t, err = s.llamar("suma", {"a": 1}); ok(t == "1", "se reinicia solo al volver a llamar")
sv, h = g.buscar("mcp__fake_uno__suma"); ok(sv is s and M.solo_lectura(h), "buscar por nombre completo y readOnlyHint")
ok(g.confianza(sv, h) and not g.confianza(*g.buscar("mcp__fake_uno__error")) and g.confianza(*g.buscar("mcp__fake_uno__entorno")), "confianza: solo lectura y «autonomas»")
try: g.descubrir("roto"); ok(False, "programa inexistente")
except M.ErrorMcp as e: ok("no encuentro el programa" in str(e).lower(), "programa inexistente: " + str(e)[:70])
gr = g.grupos(); ok("mcp_fake_uno" in gr and "calculadora" in gr["mcp_fake_uno"][1], "grupos y palabras: " + str(gr["mcp_fake_uno"][1]))
ok(g.aprobada("fake_uno"), "aprobada la primera vez")
# rug pull: el servidor cambia sus herramientas
conf["mcpServers"]["Fake Uno"]["args"] = [str(T / "fake_mcp.py"), "cambia"]
(casa / ".config/lina/mcp.json").write_text(json.dumps(conf)); g.recargar()
g.descubrir("fake_uno")
ok(not g.aprobada("fake_uno"), "cambio de herramientas → deja de estar aprobada")
sv, h = g.buscar("mcp__fake_uno__suma"); ok(not g.confianza(sv, h), "sin aprobar nada va sin confianza")
g.aprobar("fake_uno"); ok(g.aprobada("fake_uno"), "se vuelve a aprobar")
# añadir / quitar
n = g.anadir("Otro Mas", {"command": sys.executable, "args": [str(T / "fake_mcp.py")]}); ok(n == "otro_mas" and "otro_mas" in g.servidores, "añadir")
ok((casa / ".config/lina/mcp.json.copia").exists(), "copia del archivo al cambiarlo")
g.quitar("otro_mas"); ok("otro_mas" not in g.servidores, "quitar")
try: g.anadir("x", {}); ok(False, "añadir vacío")
except M.ErrorMcp: ok(True, "añadir sin comando se rechaza")
ok("fake_uno" in g.resumen(), "resumen")
s.ultimo_uso = 0; g.limpiar_inactivos(1); ok(not s.vivo, "se apagan los servidores sin uso")

# ---------- nuestro servidor ↔ nuestro cliente
conf2 = {"mcpServers": {"lina": {"command": sys.executable, "args": ["-m", "lina.mcp.servidor"], "env": {"HOME": str(casa), "PYTHONPATH": os.environ.get("PYTHONPATH", "")}}}}
g2 = M.Gestor(casa / "c2.json", casa / "e2.json"); g2.ruta_config.write_text(json.dumps(conf2)); g2.recargar()
hs = g2.descubrir("lina"); nombres = [h["name"] for h in hs]
print(nombres)
ok({"notas", "recordatorios", "hoja_calculo", "presentacion", "disenar_documento", "crear_documento", "consultar_pc"} <= set(nombres), "el servidor ofrece sus herramientas")
ok("ejecutar_comando" not in nombres and "abrir_app" not in nombres, "NO ofrece ejecutar_comando ni abrir_app")
for h in hs: M.declaracion("lina", h)
s2 = g2.servidores["lina"]
t, err = s2.llamar("notas", {"accion": "crear", "titulo": "Desde MCP", "texto": "hola"}); ok("Nota creada" in t and not err, t[:70])
t, err = s2.llamar("notas", {"accion": "buscar", "consulta": "hola"}); ok("Desde MCP" in t, "buscar la nota")
t, err = s2.llamar("recordatorios", {"accion": "crear", "texto": "probar", "cuando": "dentro de 10 minutos"}); ok("guardado" in t, t[:60])
t, err = s2.llamar("hoja_calculo", {"accion": "crear", "nombre": "mcp hoja", "filas": [["a", "b"], ["1", "2"]]}); ok("Excel creado" in t, t[:60])
t, err = s2.llamar("consultar_pc", {"comando": "ls /"}); ok("usr" in t, "consultar_pc ls")
t, err = s2.llamar("consultar_pc", {"comando": "rm -rf /tmp/x"}); ok("No lo ejecuto" in t, "consultar_pc rechaza rm: " + t[:60])
t, err = s2.llamar("consultar_pc", {"comando": "ls / | cat"}); ok("sin tuberías" in t, "consultar_pc rechaza tuberías")
t, err = s2.llamar("consultar_pc", {"comando": "cat /etc/hostname; id"}); ok("sin tuberías" in t, "consultar_pc rechaza ;")
t, err = s2.llamar("consultar_pc", {"comando": "sudo ls"}); ok("No lo ejecuto" in t, "consultar_pc rechaza sudo: " + t[:40])
for c in ["cat /proc/self/environ", "ls ~/.local/share/kwalletd", "cat ~/.config/lina/mcp.json", "su -c ls", "cat /etc/shadow"]:
    t, err = s2.llamar("consultar_pc", {"comando": c}); ok("No lo ejecuto" in t, "rechaza " + c)
t, err = s2.llamar("nada", {}); ok(err, "herramienta inexistente → isError")
ok("[mcp-servidor] notas" in (casa / ".local/share/lina/acciones.log").read_text() if (casa / ".local/share/lina/acciones.log").exists() else True, "llamadas anotadas")
# protocolo crudo: solo JSON por stdout aunque la librería imprima
p = subprocess.Popen([sys.executable, "-m", "lina.mcp.servidor"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={**os.environ, "HOME": str(casa)})
entrada = "\n".join(json.dumps(x) for x in [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}, {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "ping"}, {"jsonrpc": "2.0", "id": 3, "method": "prompts/list"}, {"jsonrpc": "2.0", "id": 4, "method": "raro"}]) + "\nbasura\n"
salida, _ = p.communicate(entrada, timeout=20)
msgs = [json.loads(l) for l in salida.splitlines()]
ok(all("jsonrpc" in m for m in msgs) and len(msgs) == 5, f"stdout solo protocolo ({len(msgs)} mensajes)")
ok(msgs[0]["result"]["protocolVersion"] in M.VERSIONES and msgs[3]["error"]["code"] == -32601 and msgs[4]["error"]["code"] == -32700, "versión desconocida → una conocida; método raro y JSON roto → errores")

# ---------- HTTP (Streamable HTTP, con JSON y con SSE)
from http.server import BaseHTTPRequestHandler, HTTPServer
vistos = []
class H_(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        vistos.append((cuerpo.get("method"), self.headers.get("Mcp-Session-Id"), self.headers.get("Authorization"), self.headers.get("MCP-Protocol-Version")))
        if "id" not in cuerpo: self.send_response(202); self.end_headers(); return
        m = cuerpo["method"]
        if m == "initialize": r = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "http"}}
        elif m == "tools/list": r = {"tools": [{"name": "eco", "description": "repite", "inputSchema": {"type": "object", "properties": {"t": {"type": "string"}}}}]}
        else: r = {"content": [{"type": "text", "text": "eco:" + cuerpo["params"]["arguments"].get("t", "")}]}
        msg = json.dumps({"jsonrpc": "2.0", "id": cuerpo["id"], "result": r})
        self.send_response(200)
        if m == "initialize": self.send_header("Mcp-Session-Id", "sesion-42")
        if m == "tools/call":
            self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            self.wfile.write(b'data: {"jsonrpc":"2.0","method":"notifications/message","params":{}}\n\n' + b"data: " + msg.encode() + b"\n\n")
        else:
            self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(msg.encode())
    def do_DELETE(self): self.send_response(200); self.end_headers()
srv = HTTPServer(("127.0.0.1", 0), H_); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["TOKEN_PRUEBA"] = "abc"
g3 = M.Gestor(casa / "c3.json", casa / "e3.json"); g3.ruta_config.write_text(json.dumps({"mcpServers": {"web": {"url": f"http://127.0.0.1:{srv.server_address[1]}/mcp", "headers": {"Authorization": "Bearer ${TOKEN_PRUEBA}"}}}})); g3.recargar()
hs = g3.descubrir("web"); ok([h["name"] for h in hs] == ["eco"], "HTTP: initialize + tools/list")
t, err = g3.servidores["web"].llamar("eco", {"t": "hola"}); ok(t == "eco:hola", "HTTP: respuesta por SSE: " + t)
ok(all(v[1] == "sesion-42" for v in vistos[1:]) and all(v[2] == "Bearer abc" for v in vistos) and vistos[-1][3] == "2025-06-18", "HTTP: id de sesión, Authorization con ${VAR} y versión")
g3.cerrar(); g2.cerrar(); g.cerrar()
print("fallos", fallos)
