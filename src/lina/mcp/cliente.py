"""E1: el asistente como CLIENTE de MCP (Model Context Protocol): usa herramientas de servidores MCP que tú configuras.

Sin dependencias (solo la librería estándar y requests). Soporta servidores locales (stdio: «command» + «args») y remotos (Streamable HTTP: «url»).

Archivo de servidores: ~/.config/lina/mcp.json, con el mismo formato que Claude Desktop:
    {"mcpServers": {"github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
                               "palabras": ["github", "issue"], "autonomas": ["list_issues"], "descripcion": "GitHub: issues y pull requests"}}}
Claves propias (opcionales): palabras (con qué palabras se activa), descripcion, autonomas (herramientas que no piden confirmación aunque no sean de solo lectura,
o ["*"]), desactivado (true).

Seguridad (la aplica el asistente, aquí solo están los datos):
- un servidor solo existe si está en ese archivo; añadirlo desde la voz pide confirmación;
- cada servidor arranca con un entorno MÍNIMO (sin tus claves de Gemini ni otras variables), más lo que declares en «env»;
- lo que devuelve un servidor (y las descripciones de sus herramientas) son datos de un tercero, nunca órdenes;
- si las herramientas de un servidor cambian desde que las aprobaste, hace falta aprobarlas de nuevo.
"""
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import requests
from lina.nucleo import claves as CL
from lina.nucleo import rutas as RUT

CONFIG = RUT.CONFIG / "mcp.json"
ESTADO = RUT.DATOS / "mcp_estado.json"
VERSION_PEDIDA = "2025-06-18"
VERSIONES = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
TIMEOUT_ARRANQUE = 90          # la primera vez npx/uvx pueden descargar el paquete
TIMEOUT_LLAMADA = 90
MAX_RESULTADO = 6000
MAX_DESCRIPCION = 300
INACTIVO_SEG = 600
ENTORNO_BASE = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "DISPLAY",
                "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "TMPDIR", "SHELL", "TERM")


class ErrorMcp(Exception):
    """Un problema que se le puede contar al usuario."""


def _log(m):
    print(f"[{time.strftime('%H:%M:%S')}] MCP: {m}", flush=True)


def limpio(texto, largo):
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(texto or ""))
    return re.sub(r"\s+", " ", t).strip()[:largo]


def nombre_servidor(n):
    s = re.sub(r"[^a-z0-9]+", "_", str(n or "").lower()).strip("_")[:24]
    return s


def nombre_herramienta(servidor, herramienta):
    """Nombre válido para Gemini (letras, números, _ . -; máximo 64) y estable."""
    base = f"mcp__{servidor}__{re.sub(r'[^A-Za-z0-9_.-]', '_', str(herramienta))}"
    if len(base) <= 64:
        return base
    return base[:57] + "_" + hashlib.sha1(base.encode()).hexdigest()[:6]


def archivo_claves():
    return RUT.CONFIG / "mcp_claves.env"


def claves():
    """Claves de servidores MCP guardadas en el archivo de respaldo (CLAVE=valor por línea). Las que están en el llavero del sistema se
    piden por nombre (ver valor_de())."""
    salida = {}
    try:
        for linea in archivo_claves().read_text(encoding="utf-8").splitlines():
            k, _, v = linea.partition("=")
            if k.strip() and not k.strip().startswith("#"):
                salida[k.strip()] = v.strip()
    except OSError:
        pass
    return salida


def valor_de(nombre):
    """Valor de una variable de servidor MCP: entorno, llavero del sistema o archivo de respaldo."""
    return CL.valor_mcp(nombre)


def variables_de(valor):
    return re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", str(valor))


def faltan_claves(conf):
    """Variables ${X} que usa la configuración y que no existen ni en el entorno ni en el archivo de claves."""
    textos = [conf.get("url", ""), conf.get("command", ""), *(conf.get("args") or []), *(conf.get("env") or {}).values(), *(conf.get("headers") or {}).values()]
    return sorted({v for t in textos for v in variables_de(t) if not valor_de(v)})


def expandir(valor):
    """${VARIABLE} → su valor (entorno o archivo de claves): así las claves no tienen que estar escritas en mcp.json."""
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", lambda m: valor_de(m.group(1)), str(valor))


# ======================= esquemas: de JSON Schema a lo que admite Gemini =======================
_TIPOS = {"string", "number", "integer", "boolean", "array", "object"}


def limpiar_esquema(e, profundidad=0):
    """Gemini solo entiende un subconjunto de OpenAPI: se quitan $schema, additionalProperties, anyOf... y se simplifica lo que se pueda."""
    if not isinstance(e, dict) or profundidad > 6:
        return {"type": "string"}
    for clave in ("anyOf", "oneOf"):
        if isinstance(e.get(clave), list):
            alternativas = [x for x in e[clave] if isinstance(x, dict) and x.get("type") != "null"]
            if alternativas:
                fusion = dict(alternativas[0])
                fusion.setdefault("description", e.get("description", ""))
                return limpiar_esquema(fusion, profundidad + 1)
    if "allOf" in e and isinstance(e["allOf"], list) and e["allOf"]:
        return limpiar_esquema(e["allOf"][0], profundidad + 1)
    tipo = e.get("type")
    if isinstance(tipo, list):
        tipo = next((t for t in tipo if t != "null"), "string")
    if tipo not in _TIPOS:
        tipo = "object" if "properties" in e else ("array" if "items" in e else "string")
    salida = {"type": tipo}
    if e.get("description"):
        salida["description"] = limpio(e["description"], 300)
    if tipo == "object":
        props = e.get("properties") if isinstance(e.get("properties"), dict) else {}
        salida["properties"] = {str(k)[:60]: limpiar_esquema(v, profundidad + 1) for k, v in list(props.items())[:40]}
        req = [r for r in (e.get("required") or []) if r in salida["properties"]]
        if req:
            salida["required"] = req
    elif tipo == "array":
        salida["items"] = limpiar_esquema(e.get("items") or {"type": "string"}, profundidad + 1)
    elif tipo == "string":
        if isinstance(e.get("enum"), list) and e["enum"] and all(isinstance(x, str) for x in e["enum"]):
            salida["enum"] = [x[:80] for x in e["enum"][:50]]
    return salida


def declaracion(servidor, herramienta):
    """La declaración de función para Gemini de una herramienta de un servidor."""
    esquema = limpiar_esquema(herramienta.get("inputSchema") or {"type": "object"})
    d = {"name": nombre_herramienta(servidor, herramienta.get("name", "")),
         "description": f"[MCP {servidor}] " + limpio(herramienta.get("description") or herramienta.get("title") or herramienta.get("name"), MAX_DESCRIPCION)}
    if esquema.get("properties"):
        d["parameters"] = esquema
    return d


def solo_lectura(herramienta):
    return bool(((herramienta or {}).get("annotations") or {}).get("readOnlyHint"))


def resultado_a_texto(res):
    """El resultado de tools/call → texto (tope de tamaño)."""
    partes = []
    for c in (res or {}).get("content") or []:
        t = c.get("type")
        if t == "text":
            partes.append(str(c.get("text", "")))
        elif t == "resource" and isinstance(c.get("resource"), dict):
            partes.append(str(c["resource"].get("text") or f"[recurso {c['resource'].get('uri', '')}]"))
        elif t == "resource_link":
            partes.append(f"[enlace a recurso: {c.get('uri', '')}]")
        elif t in ("image", "audio"):
            partes.append(f"[{t} omitido: no puedo verlo por aquí]")
    if not partes and res and res.get("structuredContent") is not None:
        partes.append(json.dumps(res["structuredContent"], ensure_ascii=False))
    texto = "\n".join(p for p in partes if p).strip() or "(sin contenido)"
    return texto[:MAX_RESULTADO] + ("\n[…recortado]" if len(texto) > MAX_RESULTADO else "")


# ======================= transportes =======================
class _Stdio:
    def __init__(self, conf, nombre):
        orden = [expandir(conf.get("command", ""))] + [expandir(a) for a in (conf.get("args") or [])]
        exe = shutil.which(orden[0], path=os.environ.get("PATH", "") + ":" + str(Path.home() / ".local/bin"))
        if not exe:
            ayuda = {"npx": " (instala nodejs y npm)", "uvx": " (instala uv)", "node": " (instala nodejs)", "docker": " (instala docker)"}.get(orden[0], "")
            raise ErrorMcp(f"No encuentro el programa «{orden[0]}» que necesita el servidor {nombre}{ayuda}.")
        orden[0] = exe
        env = {k: os.environ[k] for k in ENTORNO_BASE if k in os.environ}
        for k, v in (conf.get("env") or {}).items():
            env[str(k)] = expandir(v)
        cwd = expandir(conf["cwd"]) if conf.get("cwd") else None
        try:
            self.p = subprocess.Popen(orden, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd, start_new_session=True)
        except OSError as e:
            raise ErrorMcp(f"No he podido arrancar el servidor {nombre}: {e.strerror or e}")
        self.nombre = nombre
        self.pendientes = {}
        self.cola_mensajes = queue.Queue()
        self.stderr = []
        self.lock = threading.Lock()
        self.alta = threading.Lock()
        self.muerto = False
        self.al_recibir = None
        threading.Thread(target=self._leer, daemon=True).start()
        threading.Thread(target=self._leer_err, daemon=True).start()

    def _leer(self):
        try:
            for linea in self.p.stdout:
                try:
                    msg = json.loads(linea.decode("utf-8", "replace"))
                except ValueError:
                    continue                                    # una línea que no es JSON (algún aviso suelto): se ignora
                self._repartir(msg)
        finally:
            self.muerto = True
            for q in list(self.pendientes.values()):
                q.put({"error": {"code": -32000, "message": "el servidor se ha cerrado"}})

    def _leer_err(self):
        for linea in self.p.stderr:
            self.stderr.append(linea.decode("utf-8", "replace").rstrip())
            del self.stderr[:-20]

    def _repartir(self, msg):
        if isinstance(msg, dict) and "id" in msg and ("result" in msg or "error" in msg):
            q = self.pendientes.get(msg["id"])
            if q:
                q.put(msg)
        elif self.al_recibir:
            self.al_recibir(msg)

    def enviar(self, msg):
        datos = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self.alta:
            try:
                self.p.stdin.write(datos)
                self.p.stdin.flush()
            except (OSError, ValueError):
                self.muerto = True
                raise ErrorMcp(f"El servidor {self.nombre} se ha cerrado." + self._pista())

    def peticion(self, msg, timeout):
        q = queue.Queue()
        self.pendientes[msg["id"]] = q
        try:
            self.enviar(msg)
            try:
                r = q.get(timeout=timeout)
            except queue.Empty:
                raise ErrorMcp(f"El servidor {self.nombre} no ha respondido en {timeout} s.")
            return r
        finally:
            self.pendientes.pop(msg["id"], None)

    def notificar(self, msg):
        self.enviar(msg)

    def _pista(self):
        return (" Dijo: " + " | ".join(self.stderr[-3:])[:300]) if self.stderr else ""

    def cerrar(self):
        self.muerto = True
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            for senal in (15, 9):
                try:
                    os.killpg(self.p.pid, senal)
                except OSError:
                    break
                try:
                    self.p.wait(timeout=2)
                    break
                except subprocess.TimeoutExpired:
                    continue


class _Http:
    def __init__(self, conf, nombre):
        self.url = expandir(conf.get("url", ""))
        if not re.match(r"^https?://", self.url):
            raise ErrorMcp(f"La dirección del servidor {nombre} no es http(s).")
        self.nombre = nombre
        self.cabeceras = {str(k): expandir(v) for k, v in (conf.get("headers") or {}).items()}
        self.sesion_id = None
        self.version = None
        self.s = requests.Session()
        self.muerto = False
        self.al_recibir = None
        self.stderr = []

    def _post(self, msg, timeout):
        h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", **self.cabeceras}
        if self.sesion_id:
            h["Mcp-Session-Id"] = self.sesion_id
        if self.version:
            h["MCP-Protocol-Version"] = self.version
        try:
            return self.s.post(self.url, data=json.dumps(msg, ensure_ascii=False).encode("utf-8"), headers=h, timeout=timeout, stream=True)
        except requests.RequestException as e:
            raise ErrorMcp(f"No puedo conectar con el servidor {self.nombre}: {type(e).__name__}")

    def _mensajes(self, r):
        tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if tipo == "text/event-stream":
            datos = []
            for linea in r.iter_lines(decode_unicode=True):
                if linea is None:
                    continue
                if linea == "":
                    if datos:
                        try:
                            yield json.loads("\n".join(datos))
                        except ValueError:
                            pass
                        datos = []
                elif linea.startswith("data:"):
                    datos.append(linea[5:].lstrip())
            if datos:
                try:
                    yield json.loads("\n".join(datos))
                except ValueError:
                    pass
        else:
            try:
                cuerpo = json.loads(r.content.decode("utf-8", "replace"))
            except ValueError:
                return
            for m in (cuerpo if isinstance(cuerpo, list) else [cuerpo]):
                yield m

    def peticion(self, msg, timeout):
        r = self._post(msg, timeout)
        try:
            if r.status_code in (401, 403):
                raise ErrorMcp(f"El servidor {self.nombre} no me deja entrar (error {r.status_code}): falta o está mal la clave en «headers».")
            if r.status_code == 404 and self.sesion_id:
                raise ErrorMcp(f"La sesión con {self.nombre} ha caducado; se volverá a abrir.")
            if not r.ok:
                raise ErrorMcp(f"El servidor {self.nombre} respondió con error {r.status_code}.")
            if msg.get("method") == "initialize" and r.headers.get("Mcp-Session-Id"):
                self.sesion_id = r.headers["Mcp-Session-Id"]
            for m in self._mensajes(r):
                if isinstance(m, dict) and m.get("id") == msg["id"] and ("result" in m or "error" in m):
                    return m
                if self.al_recibir:
                    self.al_recibir(m)
            raise ErrorMcp(f"El servidor {self.nombre} no ha contestado a la petición.")
        finally:
            r.close()

    def notificar(self, msg):
        r = self._post(msg, 20)
        r.close()

    def cerrar(self):
        self.muerto = True
        if self.sesion_id:
            try:
                self.s.delete(self.url, headers={"Mcp-Session-Id": self.sesion_id, **self.cabeceras}, timeout=5)
            except requests.RequestException:
                pass


# ======================= un servidor =======================
class Servidor:
    def __init__(self, nombre, conf):
        self.nombre, self.conf = nombre, conf
        self.t = None
        self.herramientas = []                  # tal como las manda el servidor
        self.cambio_lista = False
        self.ultimo_uso = 0.0
        self._id = 0
        self._lock = threading.RLock()
        self.info = {}

    def _siguiente(self):
        self._id += 1
        return self._id

    @property
    def vivo(self):
        return self.t is not None and not self.t.muerto

    def _responde_a_servidor(self, msg):
        """Cosas que el servidor nos pide a nosotros: ping sí; muestreo, raíces, etc. no (el asistente no los ofrece)."""
        if not isinstance(msg, dict):
            return
        m = msg.get("method")
        if m == "notifications/tools/list_changed":
            self.cambio_lista = True
        elif "id" in msg and m:
            resp = {"jsonrpc": "2.0", "id": msg["id"]}
            if m == "ping":
                resp["result"] = {}
            else:
                resp["error"] = {"code": -32601, "message": "método no soportado por este cliente"}
            if isinstance(self.t, _Stdio):
                try:
                    self.t.enviar(resp)
                except ErrorMcp:
                    pass

    def iniciar(self):
        with self._lock:
            if self.vivo:
                return
            if self.t:
                self.t.cerrar()
            self.t = _Http(self.conf, self.nombre) if self.conf.get("url") else _Stdio(self.conf, self.nombre)
            self.t.al_recibir = self._responde_a_servidor
            try:
                r = self.t.peticion({"jsonrpc": "2.0", "id": self._siguiente(), "method": "initialize",
                                     "params": {"protocolVersion": VERSION_PEDIDA, "capabilities": {},
                                                "clientInfo": {"name": "lina", "version": "1.0"}}}, TIMEOUT_ARRANQUE)
                if "error" in r:
                    raise ErrorMcp(f"El servidor {self.nombre} rechazó el arranque: {limpio(r['error'].get('message'), 150)}")
                res = r.get("result") or {}
                version = res.get("protocolVersion")
                if version not in VERSIONES:
                    raise ErrorMcp(f"El servidor {self.nombre} habla una versión de MCP que no conozco ({limpio(version, 20)}).")
                self.info = res.get("serverInfo") or {}
                if isinstance(self.t, _Http):
                    self.t.version = version
                self.t.notificar({"jsonrpc": "2.0", "method": "notifications/initialized"})
                self.refrescar()
            except Exception:
                self.cerrar()
                raise
            self.ultimo_uso = time.time()
            _log(f"{self.nombre} listo ({len(self.herramientas)} herramientas)")

    def refrescar(self):
        herramientas, cursor = [], None
        for _ in range(10):
            params = {"cursor": cursor} if cursor else {}
            r = self.t.peticion({"jsonrpc": "2.0", "id": self._siguiente(), "method": "tools/list", "params": params}, 30)
            if "error" in r:
                raise ErrorMcp(f"No he podido pedir las herramientas de {self.nombre}: {limpio(r['error'].get('message'), 150)}")
            res = r.get("result") or {}
            herramientas += [h for h in res.get("tools", []) if isinstance(h, dict) and h.get("name")]
            cursor = res.get("nextCursor")
            if not cursor:
                break
        self.herramientas = sorted(herramientas, key=lambda h: h["name"])[:60]
        self.cambio_lista = False

    def llamar(self, herramienta, argumentos, timeout=TIMEOUT_LLAMADA):
        """(texto, es_error)."""
        with self._lock:
            if not self.vivo:
                self.iniciar()
            elif self.cambio_lista:
                self.refrescar()
        self.ultimo_uso = time.time()
        r = self.t.peticion({"jsonrpc": "2.0", "id": self._siguiente(), "method": "tools/call",
                             "params": {"name": herramienta, "arguments": argumentos if isinstance(argumentos, dict) else {}}}, timeout)
        self.ultimo_uso = time.time()
        if "error" in r:
            return f"El servidor devolvió un error: {limpio(r['error'].get('message'), 300)}", True
        res = r.get("result") or {}
        return resultado_a_texto(res), bool(res.get("isError"))

    def cerrar(self):
        if self.t:
            try:
                self.t.cerrar()
            except Exception:
                pass
        self.t = None


# ======================= todos los servidores =======================
def huella_herramienta(h):
    return hashlib.sha256(json.dumps([h.get("name"), h.get("description"), h.get("inputSchema")], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def huella(herramientas):
    """Resumen estable de lo que ofrece un servidor (nombres, descripciones y parámetros): si cambia, hay que volver a aprobarlo."""
    base = json.dumps([[h.get("name"), h.get("description"), h.get("inputSchema")] for h in herramientas], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(base.encode()).hexdigest()[:16]


class Gestor:
    def __init__(self, config=CONFIG, estado=ESTADO):
        self.ruta_config, self.ruta_estado = Path(config), Path(estado)
        self.servidores = {}                    # nombre → Servidor (solo los activos en la configuración)
        self.conf = {}
        self.lock = threading.RLock()
        self.estado = {}
        self.recargar()

    # ----- configuración -----
    def recargar(self):
        with self.lock:
            nuevo = {}
            try:
                datos = json.loads(self.ruta_config.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                datos = {}
            bruto = datos.get("mcpServers") or datos.get("servidores") or {}
            for n, c in (bruto.items() if isinstance(bruto, dict) else []):
                nombre = nombre_servidor(n)
                if nombre and isinstance(c, dict) and not c.get("desactivado") and (c.get("command") or c.get("url")):
                    nuevo[nombre] = c
            for n in list(self.servidores):
                if n not in nuevo or nuevo[n] != self.conf.get(n):
                    self.servidores.pop(n).cerrar()
            for n, c in nuevo.items():
                self.servidores.setdefault(n, Servidor(n, c))
            self.conf = nuevo
            try:
                self.estado = json.loads(self.ruta_estado.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.estado = {}

    def _guardar_estado(self):
        try:
            self.ruta_estado.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.ruta_estado.with_name(self.ruta_estado.name + f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(self.estado, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.ruta_estado)
        except OSError:
            pass

    def _escribir_config(self, datos):
        self.ruta_config.parent.mkdir(parents=True, exist_ok=True)
        if self.ruta_config.exists():
            shutil.copy2(self.ruta_config, self.ruta_config.with_name(self.ruta_config.name + ".copia"))
        tmp = self.ruta_config.with_name(self.ruta_config.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.ruta_config)

    def _config_cruda(self):
        try:
            datos = json.loads(self.ruta_config.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            datos = {}
        if not isinstance(datos.get("mcpServers"), dict):
            datos["mcpServers"] = {}
        return datos

    def anadir(self, nombre, conf):
        nombre = nombre_servidor(nombre)
        if not nombre:
            raise ErrorMcp("Falta un nombre para el servidor.")
        if not (conf.get("command") or conf.get("url")):
            raise ErrorMcp("Falta el comando (servidor local) o la dirección (servidor remoto).")
        datos = self._config_cruda()
        datos["mcpServers"][nombre] = conf
        self._escribir_config(datos)
        self.recargar()
        return nombre

    def quitar(self, nombre):
        nombre = nombre_servidor(nombre)
        datos = self._config_cruda()
        if nombre not in datos["mcpServers"]:
            raise ErrorMcp(f"No hay ningún servidor llamado «{nombre}».")
        del datos["mcpServers"][nombre]
        self._escribir_config(datos)
        self.estado.pop(nombre, None)
        self._guardar_estado()
        self.recargar()

    # ----- herramientas -----
    def descubrir(self, nombre, aprobar=False):
        """Arranca el servidor (si hace falta), lee sus herramientas y las compara con lo aprobado. Devuelve la lista."""
        s = self.servidores.get(nombre)
        if not s:
            raise ErrorMcp(f"No hay ningún servidor llamado «{nombre}».")
        s.iniciar()
        h = huella(s.herramientas)
        e = self.estado.setdefault(nombre, {})
        e["herramientas"] = [dict(name=t["name"], description=limpio(t.get("description"), 200)) for t in s.herramientas]
        e["actual"] = h
        e["por_herramienta"] = {t["name"]: huella_herramienta(t) for t in s.herramientas}
        if aprobar or "aprobada" not in e:              # la primera vez se da por buena (la has puesto tú); si luego cambia, hay que aprobar de nuevo
            e["aprobada"] = h
            e["tools_aprobadas"] = dict(e["por_herramienta"])
        self._guardar_estado()
        return s.herramientas

    def diferencias(self, nombre):
        """(nuevas, quitadas, modificadas): qué ha cambiado un servidor respecto a lo que aprobaste."""
        e = self.estado.get(nombre) or {}
        antes, ahora = e.get("tools_aprobadas") or {}, e.get("por_herramienta") or {}
        return (sorted(set(ahora) - set(antes)), sorted(set(antes) - set(ahora)), sorted(n for n in set(ahora) & set(antes) if ahora[n] != antes[n]))

    def aprobada(self, nombre):
        e = self.estado.get(nombre) or {}
        return bool(e.get("aprobada")) and e.get("aprobada") == e.get("actual")

    def aprobar(self, nombre):
        e = self.estado.setdefault(nombre, {})
        e["aprobada"] = e.get("actual")
        e["tools_aprobadas"] = dict(e.get("por_herramienta") or {})
        self._guardar_estado()

    def declaraciones(self, nombre):
        """Declaraciones para Gemini de un servidor (de lo que se sabe: vivo, o la última lista guardada no tiene esquemas, así que solo vivo)."""
        s = self.servidores.get(nombre)
        return [declaracion(nombre, h) for h in (s.herramientas if s else [])]

    def buscar(self, nombre_completo):
        """(servidor, herramienta_de_servidor_dict) para un nombre mcp__srv__tool, o (None, None)."""
        for n, s in self.servidores.items():
            for h in s.herramientas:
                if nombre_herramienta(n, h["name"]) == nombre_completo:
                    return s, h
        return None, None

    def confianza(self, servidor, herramienta):
        """¿Se puede llamar sin pedir confirmación? Solo lectura, o listada en «autonomas»; y siempre con las herramientas aprobadas."""
        if not self.aprobada(servidor.nombre):
            return False
        aut = self.conf.get(servidor.nombre, {}).get("autonomas") or []
        return solo_lectura(herramienta) or "*" in aut or herramienta["name"] in aut

    def grupos(self):
        """{grupo: (descripcion, palabras_regex)} para registrar en grupos.py, uno por servidor configurado."""
        salida = {}
        for n, c in self.conf.items():
            palabras = [re.escape(unicode_plano(p)) for p in ([n] + list(c.get("palabras") or [])) if str(p).strip()]
            regex = r"\b(" + "|".join(palabras) + r")" if palabras else ""
            salida[f"mcp_{n}"] = (limpio(c.get("descripcion") or f"herramientas del servidor MCP {n}", 120), regex)
        return salida

    def limpiar_inactivos(self, segundos=INACTIVO_SEG):
        for n, s in list(self.servidores.items()):
            if s.vivo and time.time() - s.ultimo_uso > segundos:
                _log(f"{n} sin uso: se cierra")
                s.cerrar()

    def cerrar(self):
        for s in self.servidores.values():
            s.cerrar()

    def resumen(self):
        if not self.conf:
            return "No hay ningún servidor MCP configurado (archivo: " + str(self.ruta_config) + ")."
        filas = []
        for n, s in self.servidores.items():
            e = self.estado.get(n) or {}
            n_h = len(s.herramientas) if s.herramientas else len(e.get("herramientas") or [])
            estado = ("encendido" if s.vivo else "apagado (arranca al usarlo)") + ("" if self.aprobada(n) or not e else " · herramientas CAMBIADAS: hay que aprobarlas")
            filas.append(f"{n}: {estado}, {n_h} herramientas" + (f" ({', '.join(t['name'] for t in (e.get('herramientas') or [])[:8])})" if e.get("herramientas") else ""))
        return " | ".join(filas)


def unicode_plano(t):
    import unicodedata
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# ======================= darle a OTRAS IAs las herramientas de este asistente =======================
CANDIDATOS_CLAUDE_DESKTOP = [Path.home() / ".config/Claude/claude_desktop_config.json", Path.home() / ".config/claude-desktop/claude_desktop_config.json",
                             Path.home() / ".var/app/com.anthropic.Claude/config/Claude/claude_desktop_config.json"]


def config_servidor_propio():
    """(dict para Claude Desktop, texto TOML para Codex, comando de Claude Code) con las rutas reales de esta instalación."""
    import shlex
    import sys
    entrada = {"command": sys.executable, "args": ["-m", "lina.mcp.servidor"]}
    toml = f'[mcp_servers.lina]\ncommand = "{entrada["command"]}"\nargs = ["-m", "lina.mcp.servidor"]\n'
    return entrada, toml, "claude mcp add lina -- " + shlex.join([entrada["command"]] + entrada["args"])


def ruta_claude_desktop():
    return next((p for p in CANDIDATOS_CLAUDE_DESKTOP if p.exists()), None)


def publicar_en_claude_desktop(ruta=None):
    """Añade «asistente» a mcpServers de Claude Desktop (con copia del archivo). Devuelve un texto para el usuario."""
    ruta = Path(ruta) if ruta else ruta_claude_desktop()
    entrada, _, _ = config_servidor_propio()
    if ruta is None:
        return ("No encuentro el archivo de configuración de Claude Desktop. Abre Claude Desktop → Ajustes → Desarrollador → Editar configuración, "
                "y añade dentro de mcpServers: " + json.dumps({"lina": entrada}, ensure_ascii=False))
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.stat().st_size else {}
    except (OSError, ValueError):
        return f"No he podido leer {ruta}: no lo toco."
    if not isinstance(datos.get("mcpServers"), dict):
        datos["mcpServers"] = {}
    if datos["mcpServers"].get("lina") == entrada:
        return "Claude Desktop ya tenía este asistente dado de alta."
    copia = ruta.with_name(ruta.name + ".copia-lina")
    shutil.copy2(ruta, copia)
    datos["mcpServers"]["lina"] = entrada
    tmp = ruta.with_name(ruta.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ruta)
    return f"Dado de alta en {ruta} (copia anterior: {copia.name}). Cierra Claude Desktop del todo y vuelve a abrirlo; verás «lina» entre sus herramientas."
