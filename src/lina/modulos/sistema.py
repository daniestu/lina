"""B3. Control del sistema: ventanas, procesos, servicios, red y Bluetooth, energía, pantalla, audio y D-Bus de KDE.

Este módulo NO ejecuta los cambios: los PLANIFICA. Cada función `planificar_*` devuelve un diccionario:
    {"texto": "..."}                            -> solo información (lecturas): se le da a la IA tal cual
    {"comando": "...", "motivo": "...",         -> un cambio: lo ejecuta herramientas.Ejecutor.herramienta(), o sea con la misma
     "comprobar": callable, "espera": seg}         clasificación, confirmaciones, diario y topes que cualquier otro comando
    {"error": "..."}                             -> no se puede (con el motivo, para que la IA lo cuente o pruebe otra cosa)
Después del cambio se vuelve a LEER el estado (`comprobar`) y se le da a la IA lo que hay de verdad, no lo que se esperaba.

Las lecturas usan EJ (inyectable en las pruebas). Aquí no hay ninguna lista de «casos»: solo las piezas con las que se habla con
kdotool, systemctl, nmcli, wpctl, kscreen-doctor, busctl... y las protecciones (`motivo_critico`)."""
import difflib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
import unicodedata
from lina.escritorio import sesion as SES
from lina.nucleo import rutas as RUT

EJ = None                                   # en las pruebas: función (argv, timeout) -> (código, salida)
_HOME = os.path.expanduser("~")
ARCHIVO_PANTALLA_PREVIA = str(RUT.DATOS / "pantalla_previa.json")


def _ej_real(argv, timeout=8, entrada=None):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=entrada, errors="replace",
                           env=dict(os.environ, LC_ALL="C.UTF-8", TERM="dumb"))
    except FileNotFoundError:
        return None, f"{argv[0]}: no está instalado"
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"{argv[0]}: {e}"
    return r.returncode, (r.stdout if r.returncode == 0 else r.stdout + r.stderr).strip()


def ej(argv, timeout=8, entrada=None):
    if EJ:
        return EJ(argv, timeout=timeout)
    return _ej_real(argv, timeout=timeout, entrada=entrada)


def _q(x):
    return shlex.quote(str(x))


# ----------------------------------------------------------------------------------------------------------------------
#  Búsqueda por nombre (sin acentos, con parecidos de oído)
# ----------------------------------------------------------------------------------------------------------------------
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def puntos(consulta, *textos):
    """0-100: cuánto se parece lo que se ha dicho a alguno de esos textos."""
    q = _norm(consulta)
    if not q:
        return 0
    mejor = 0
    tq = q.split()
    for texto in textos:
        t = _norm(texto)
        if not t:
            continue
        tt = t.split()
        if q == t:
            p = 100
        elif q.replace(" ", "") == t.replace(" ", ""):      # «dp1» frente a «DP-1»
            p = 96
        elif all(x in tt for x in tq):
            p = 92
        elif q in t:
            p = 86
        elif t in q:
            p = 80
        else:
            p = int(difflib.SequenceMatcher(None, q, t).ratio() * 70)
            if len(tq) == 1 and len(q) >= 4:                    # una palabra mal oída frente a las palabras del texto
                p = max(p, max((int(difflib.SequenceMatcher(None, q, w).ratio() * 85) if len(w) >= 3 else 0) for w in tt))
        mejor = max(mejor, p)
    return mejor


def _mejores(consulta, elementos, textos_de, minimo=62, margen=0):
    puntuados = sorted(((puntos(consulta, *textos_de(e)), i, e) for i, e in enumerate(elementos)), key=lambda x: (-x[0], x[1]))
    puntuados = [x for x in puntuados if x[0] >= minimo]
    if not puntuados:
        return []
    tope = puntuados[0][0]
    return [e for p, _, e in puntuados if p >= tope - margen]


# ----------------------------------------------------------------------------------------------------------------------
#  VENTANAS (kdotool + atajos de KWin)
# ----------------------------------------------------------------------------------------------------------------------
_ID_VENTANA = re.compile(r"^(\{?[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}?|\d{3,12})$")      # KWin: UUID · X11: número
SOLO_KDE = {"mostrar_escritorio", "cambiar_escritorio", "mover_a_escritorio", "mover_a_monitor", "mosaico",
            "maximizar", "pantalla_completa", "siempre_encima", "sin_bordes"}               # usan atajos de KWin
_ATAJOS_VENTANA = {                             # nombre del atajo de KWin que se pulsa sobre la ventana activa
    "maximizar": "Window Maximize", "pantalla_completa": "Window Fullscreen", "siempre_encima": "Window Above Other Windows",
    "siempre_debajo": "Window Below Other Windows", "sin_bordes": "Window No Border",
    "monitor_siguiente": "Window to Next Screen", "monitor_anterior": "Window to Previous Screen",
    "escritorio_siguiente": "Window to Next Desktop", "escritorio_anterior": "Window to Previous Desktop",
}
_MOSAICOS = {"izquierda": "Left", "derecha": "Right", "arriba": "Top", "abajo": "Bottom",
             "arriba_izquierda": "Top Left", "arriba_derecha": "Top Right",
             "abajo_izquierda": "Bottom Left", "abajo_derecha": "Bottom Right"}
ACCIONES_VENTANA = ["listar", "enfocar", "cerrar", "minimizar", "maximizar", "pantalla_completa", "siempre_encima", "sin_bordes",
                    "mosaico", "mover_a_monitor", "mover_a_escritorio", "mover", "tamano", "cambiar_escritorio", "mostrar_escritorio"]


def _prog():
    """El programa que maneja las ventanas aquí: kdotool (KDE) o xdotool (X11 y XWayland; habla igual). Sin ninguno, kdotool para que el error lo diga."""
    return SES.actual().programa_ventanas() or "kdotool"


def _kde():
    return SES.actual().escritorio == "kde"


def _kd(*args):
    return ej([_prog(), *args], timeout=10)


def _atributo(opc, ids, orden):
    rc, out = _kd("search", *opc, orden, "%@")
    lineas = out.split("\n") if rc == 0 else []
    if len(lineas) == len(ids):
        return [x.strip() for x in lineas]
    res = []
    for i in ids[:30]:                                          # lento pero seguro
        rc, out = _kd(orden, i)
        res.append(out.strip() if rc == 0 else "")
    return res + [""] * (len(ids) - len(res))


def listar_ventanas():
    """(lista, error). Cada ventana: {id, titulo, clase, pid}."""
    ids, usada = [], None
    for opc in (["--name", "."], ["--classname", "."], ["--class", "."]):
        rc, out = _kd("search", *opc)
        if rc is None:
            return [], (f"{_prog()} no está instalado o no responde, así que no puedo ver las ventanas" if _kde() or SES.actual().programa_ventanas()
                        else f"En {SES.actual().nombre()} no tengo cómo manejar ventanas (haría falta xdotool en X11; en sway y Hyprland aún no está)")
        encontrados = [x.strip() for x in out.splitlines() if _ID_VENTANA.match(x.strip())]
        if encontrados:
            ids, usada = encontrados, opc
            break
    if not ids:
        return [], None
    nombres = _atributo(usada, ids, "getwindowname")
    clases = _atributo(usada, ids, "getwindowclassname")
    pids = _atributo(usada, ids, "getwindowpid")
    return [{"id": i, "titulo": n, "clase": c, "pid": int(p) if p.isdigit() else 0}
            for i, n, c, p in zip(ids, nombres, clases, pids)], None


def ventana_activa_id():
    rc, out = _kd("getactivewindow")
    out = out.strip()
    return out if rc == 0 and _ID_VENTANA.match(out) else None


def _texto_ventanas(lista, activa=None):
    if not lista:
        return "No veo ninguna ventana abierta."
    filas = []
    for w in lista[:30]:
        marca = " ← activa" if activa and w["id"] == activa else ""
        filas.append(f"- {w['id']} · {w['clase'] or '?'} · «{(w['titulo'] or '(sin título)')[:70]}» · pid {w['pid']}{marca}")
    return f"{len(lista)} ventanas:\n" + "\n".join(filas)


_ACTIVA = {"", "activa", "actual", "esta", "ésta", "la activa", "la actual", "esta ventana", "ventana activa", "focused", "active"}


def _por_programa(q, lista):
    try:
        from lina.nucleo import comandos
        hallados = comandos.buscar_app(q)[:3]
    except Exception:
        return []
    res = []
    for p, a in hallados:
        if p < 70:
            continue
        cmd = (a.get("comando") or "").split()
        claves = {_norm(a.get("nombre", "")), _norm(a.get("id", "")), _norm(cmd[0].rsplit("/", 1)[-1] if cmd else "")}
        claves |= {_norm(x) for x in str(a.get("id", "")).split(".") if len(x) >= 4}
        claves.discard("")
        for w in lista:
            c = _norm(w["clase"])
            if c and w not in res and (c in claves or any(len(k) >= 4 and (k in c or c in k) for k in claves)):
                res.append(w)
    return res


def elegir_ventana(consulta, lista, activa):
    """(ventana, error). Entiende el id, el pid, el título, la clase o «la activa»."""
    q = str(consulta or "").strip()
    if _norm(q) in {_norm(x) for x in _ACTIVA}:
        if not activa:
            return None, "No sé cuál es la ventana activa ahora mismo."
        for w in lista:
            if w["id"] == activa:
                return w, None
        return None, "La ventana activa no aparece en la lista."
    for w in lista:
        if q.strip("{}").lower() == w["id"].strip("{}").lower():
            return w, None
    if q.isdigit():
        por_pid = [w for w in lista if w["pid"] == int(q)]
        if por_pid:
            return por_pid[0], None
    candidatas = _mejores(q, lista, lambda w: (w["titulo"], w["clase"], w["clase"].replace(".", " ")), margen=4)
    if not candidatas or max(puntos(q, w["titulo"], w["clase"]) for w in candidatas) < 80:
        por_programa = _por_programa(q, lista)           # «la consola» → Konsole, usando los lanzadores instalados
        if por_programa:
            candidatas = por_programa
    if not candidatas:
        return None, f"No hay ninguna ventana que se parezca a «{q}».\n" + _texto_ventanas(lista, activa)
    if len(candidatas) > 1:
        return None, (f"Hay {len(candidatas)} ventanas que encajan con «{q}»; repite indicando el id de la que sea:\n"
                      + _texto_ventanas(candidatas, activa))
    return candidatas[0], None


def planificar_ventanas(args):
    accion = str(args.get("accion", "listar")).strip().lower()
    if accion not in ACCIONES_VENTANA:
        return {"error": f"Acción de ventanas desconocida «{accion}». Las hay: {', '.join(ACCIONES_VENTANA)}."}
    valor = str(args.get("valor", "") or "").strip()
    if accion in SOLO_KDE and not _kde():
        return {"error": f"«{accion}» solo sé hacerlo en KDE Plasma (usa atajos de KWin) y esto es {SES.actual().nombre()}. "
                         "Aquí puedo: listar, enfocar, cerrar, minimizar, mover y tamano."}
    lista, error = listar_ventanas()
    if error:
        return {"error": error}
    activa = ventana_activa_id()
    if accion == "listar":
        return {"texto": _texto_ventanas(lista, activa)}
    if accion == "mostrar_escritorio":
        return {"comando": 'qdbus6 org.kde.kglobalaccel /component/kwin invokeShortcut "Show Desktop"', "motivo": "mostrar el escritorio",
                "comprobar": lambda: "Alterna entre mostrar el escritorio y volver a las ventanas."}
    if accion == "cambiar_escritorio":
        if not valor.isdigit() or not 1 <= int(valor) <= 20:
            return {"error": "Di el número de escritorio (1, 2, 3...) en «valor»."}
        return {"comando": f'qdbus6 org.kde.kglobalaccel /component/kwin invokeShortcut "Switch to Desktop {int(valor)}"',
                "motivo": f"cambiar al escritorio {int(valor)}", "comprobar": lambda: _ej_escritorio()}
    w, error = elegir_ventana(args.get("ventana", ""), lista, activa)
    if error:
        return {"error": error}
    nombre = f"«{(w['titulo'] or w['clase'])[:40]}»"
    i = w["id"]

    def comprobar():
        nueva, _ = listar_ventanas()
        mia = next((x for x in nueva if x["id"] == i), None)
        if accion == "cerrar":
            if mia:
                return (f"La ventana {nombre} SIGUE abierta (puede estar pidiendo guardar algo o no responder). "
                        f"Si no responde, usa la herramienta de procesos.")
            return f"La ventana {nombre} ya no está."
        if not mia:
            return "La ventana ya no aparece en la lista."
        rc, geo = _kd("getwindowgeometry", i)
        act = ventana_activa_id()
        return (f"Ahora: ventana {nombre}" + (", es la activa" if act == i else ", NO es la activa")
                + (f", geometría: {' '.join(geo.split())}" if rc == 0 and geo else "") + ".")

    base = {"comprobar": comprobar, "espera": 0.6}
    if accion == "enfocar":
        return {**base, "comando": f"{_prog()} windowactivate {_q(i)}", "motivo": f"enfocar la ventana {nombre}"}
    if accion == "cerrar":
        return {**base, "comando": f"{_prog()} windowclose {_q(i)}", "motivo": f"cerrar la ventana {nombre}", "espera": 1.2}
    if accion == "minimizar":
        return {**base, "comando": f"{_prog()} windowminimize {_q(i)}", "motivo": f"minimizar la ventana {nombre}"}
    if accion == "mover":
        m = re.fullmatch(r"\s*(-?\d{1,5})\s*[ ,x]\s*(-?\d{1,5})\s*", valor)
        if not m:
            return {"error": "Para mover, «valor» es «x,y» en píxeles (por ejemplo 100,50)."}
        return {**base, "comando": f"{_prog()} windowmove {_q(i)} {int(m.group(1))} {int(m.group(2))}", "motivo": f"mover la ventana {nombre}"}
    if accion == "tamano":
        m = re.fullmatch(r"\s*(\d{2,5})\s*[ ,x]\s*(\d{2,5})\s*", valor)
        if not m:
            return {"error": "Para cambiar el tamaño, «valor» es «ancho,alto» en píxeles (por ejemplo 1280,720)."}
        return {**base, "comando": f"{_prog()} windowsize {_q(i)} {int(m.group(1))} {int(m.group(2))}", "motivo": f"cambiar el tamaño de {nombre}"}
    if accion == "mover_a_escritorio":
        if not valor.isdigit() or not 1 <= int(valor) <= 20:
            return {"error": "Di el número de escritorio (1, 2, 3...) en «valor»."}
        return {**base, "comando": f'{_prog()} windowactivate {_q(i)} && qdbus6 org.kde.kglobalaccel /component/kwin invokeShortcut "Window to Desktop {int(valor)}"',
                "motivo": f"mover {nombre} al escritorio {int(valor)}"}
    if accion == "mover_a_monitor":
        atajo = _ATAJOS_VENTANA["monitor_anterior" if _norm(valor) in {"anterior", "previo", "izquierda"} else "monitor_siguiente"]
        return {**base, "comando": f'{_prog()} windowactivate {_q(i)} && qdbus6 org.kde.kglobalaccel /component/kwin invokeShortcut "{atajo}"',
                "motivo": f"mover {nombre} a otro monitor"}
    if accion == "mosaico":
        lado = _MOSAICOS.get(_norm(valor).replace(" ", "_"))
        if not lado:
            return {"error": f"Para el mosaico, «valor» es uno de: {', '.join(_MOSAICOS)}."}
        return {**base, "comando": f'{_prog()} windowactivate {_q(i)} && qdbus6 org.kde.kglobalaccel /component/kwin invokeShortcut "Window Quick Tile {lado}"',
                "motivo": f"colocar {nombre} a la {valor}"}
    atajo = _ATAJOS_VENTANA[accion]                              # maximizar, pantalla_completa, siempre_encima, sin_bordes
    return {**base, "comando": f'{_prog()} windowactivate {_q(i)} && qdbus6 org.kde.kglobalaccel /component/kwin invokeShortcut "{atajo}"',
            "motivo": f"{accion.replace('_', ' ')} en {nombre} (alterna: si ya estaba así, lo quita)"}


def _ej_escritorio():
    rc, out = _kd("get_desktop")
    return f"Escritorio actual: {out.strip()}." if rc == 0 and out.strip() else "No he podido leer en qué escritorio estás."


# ----------------------------------------------------------------------------------------------------------------------
#  PROCESOS
# ----------------------------------------------------------------------------------------------------------------------
# Matarlos rompe la sesión o el sistema: no se hace sin tu confirmación (lo vigila motivo_critico).
PROCESOS_PROTEGIDOS = {"systemd", "init", "kwin_wayland", "kwin_x11", "plasmashell", "startplasma-way", "startplasma-x11", "xwayland",
                       "sddm", "sddm-helper", "sddm-greeter", "dbus-daemon", "dbus-broker", "dbus-broker-lau", "networkmanager",
                       "polkitd", "systemd-logind", "systemd-journal", "systemd-udevd", "kded6", "kglobalacceld", "ksmserver",
                       "plasma_session", "plasma-kwin_wayland"}


USUARIO = None


def _usuario():
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except (ImportError, KeyError):
        return os.environ.get("USER") or os.path.basename(_HOME)


def listar_procesos():
    rc, out = ej(["ps", "-eo", "pid=,user=,pcpu=,pmem=,rss=,etimes=,comm=,args=", "--sort=-pcpu"], timeout=8)
    if rc != 0:
        return []
    res = []
    for linea in out.splitlines():
        p = linea.split(None, 7)
        if len(p) < 7 or not p[0].isdigit():
            continue
        try:
            res.append({"pid": int(p[0]), "usuario": p[1], "cpu": float(p[2]), "mem": float(p[3]), "mb": int(p[4]) // 1024,
                        "seg": int(p[5]), "nombre": p[6], "args": p[7] if len(p) > 7 else p[6]})
        except ValueError:
            continue
    return [x for x in res if x["nombre"] not in {"ps"}]


def _duracion(seg):
    if seg < 90:
        return f"{seg}s"
    if seg < 5400:
        return f"{seg // 60}min"
    if seg < 172800:
        return f"{seg // 3600}h"
    return f"{seg // 86400}d"


def _fila_proceso(x):
    return f"- pid {x['pid']} · {x['nombre']} · {x['usuario']} · CPU {x['cpu']:.0f}% · RAM {x['mb']} MB · {_duracion(x['seg'])} · {x['args'][:70]}"


def procesos_que_encajan(consulta, lista=None):
    lista = lista if lista is not None else listar_procesos()
    q = str(consulta or "").strip()
    if q.isdigit():
        return [x for x in lista if x["pid"] == int(q)]
    exactos = [x for x in lista if _norm(x["nombre"]) == _norm(q)]
    if exactos:
        return exactos
    nq = _norm(q)
    dentro = [x for x in lista if nq and (nq in _norm(x["nombre"]) or nq in _norm(x["args"].split(" ")[0].rsplit("/", 1)[-1]))]
    if dentro:
        return dentro
    return [x for x in lista if nq and nq in _norm(x["args"])] or _mejores(q, lista, lambda x: (x["nombre"],), minimo=80)


ACCIONES_PROCESO = ["listar", "buscar", "detalle", "terminar", "forzar", "prioridad", "pausar", "reanudar"]


def planificar_procesos(args):
    accion = str(args.get("accion", "listar")).strip().lower()
    if accion not in ACCIONES_PROCESO:
        return {"error": f"Acción de procesos desconocida «{accion}». Las hay: {', '.join(ACCIONES_PROCESO)}."}
    objetivo = str(args.get("proceso", "") or "").strip()
    valor = str(args.get("valor", "") or "").strip()
    lista = listar_procesos()
    if not lista:
        return {"error": "No he podido leer la lista de procesos."}
    yo = USUARIO or _usuario()
    if accion == "listar" or (accion == "buscar" and not objetivo):
        orden = _norm(valor)
        clave = (lambda x: -x["mb"]) if orden in {"ram", "memoria", "mem"} else (lambda x: -x["cpu"])
        top = sorted(lista, key=clave)[:12]
        return {"texto": ("Procesos que más " + ("memoria" if orden in {"ram", "memoria", "mem"} else "CPU") + " usan:\n")
                + "\n".join(_fila_proceso(x) for x in top)}
    encajan = procesos_que_encajan(objetivo, lista)
    if not encajan:
        return {"texto": f"No hay ningún proceso que encaje con «{objetivo}» (puede que ya no esté en marcha)."}
    if accion in {"buscar", "detalle"}:
        filas = "\n".join(_fila_proceso(x) for x in encajan[:15])
        extra = ""
        if accion == "detalle" and len(encajan) == 1:
            pid = encajan[0]["pid"]
            rc, out = ej(["ps", "-o", "pid,ppid,stat,nlwp,ni,etime,cmd", "-p", str(pid)])
            extra = "\n" + out if rc == 0 else ""
        return {"texto": f"{len(encajan)} proceso(s):\n{filas}{extra}"}
    ajenos = [x for x in encajan if x["usuario"] != yo]
    if ajenos and accion != "prioridad":
        return {"error": (f"{len(ajenos)} de esos procesos son de otro usuario ({ajenos[0]['usuario']}), no tuyos. "
                          "Si hace falta de verdad, díselo al usuario: hace falta su confirmación para tocar procesos de administrador.")}
    if len(encajan) > 6 and not args.get("todos"):
        return {"error": (f"«{objetivo}» encaja con {len(encajan)} procesos. Mira cuáles son y repite con el pid concreto "
                          "(o con todos=true si de verdad hay que parar todos):\n" + "\n".join(_fila_proceso(x) for x in encajan[:10]))}
    pids = " ".join(str(x["pid"]) for x in encajan)
    nombres = ", ".join(sorted({x["nombre"] for x in encajan}))[:60]

    def vivos():
        ahora = {x["pid"]: x for x in listar_procesos()}
        return [ahora[x["pid"]] for x in encajan if x["pid"] in ahora and ahora[x["pid"]]["nombre"] == x["nombre"]]

    def comprobar():
        quedan = vivos()
        if accion in {"terminar", "forzar"}:
            if quedan:
                return (f"{len(quedan)} proceso(s) de {nombres} SIGUEN vivos"
                        + (" (le he pedido que termine y no ha hecho caso: si el usuario quiere, se fuerza)" if accion == "terminar" else "") + ".")
            return f"Comprobado: {nombres} ya no está en marcha."
        if accion in {"pausar", "reanudar"}:
            rc, out = ej(["ps", "-o", "pid=,stat=", "-p", ",".join(str(x["pid"]) for x in encajan)])
            return "Estado ahora (T = pausado): " + " | ".join(" ".join(l.split()) for l in out.splitlines())
        rc, out = ej(["ps", "-o", "pid=,ni=", "-p", ",".join(str(x["pid"]) for x in encajan)])
        return "Prioridad (nice) ahora: " + " | ".join(" ".join(l.split()) for l in out.splitlines())

    if accion == "terminar":
        return {"comando": f"kill -TERM {pids}", "motivo": f"cerrar {nombres}", "comprobar": comprobar, "espera": 2.0}
    if accion == "forzar":
        return {"comando": f"kill -KILL {pids}", "motivo": f"forzar el cierre de {nombres}", "comprobar": comprobar, "espera": 1.0}
    if accion == "pausar":
        return {"comando": f"kill -STOP {pids}", "motivo": f"pausar {nombres}", "comprobar": comprobar, "espera": 0.5}
    if accion == "reanudar":
        return {"comando": f"kill -CONT {pids}", "motivo": f"reanudar {nombres}", "comprobar": comprobar, "espera": 0.5}
    if not re.fullmatch(r"-?\d{1,2}", valor) or not -20 <= int(valor) <= 19:
        return {"error": "Para la prioridad, «valor» es el nice de -20 (máxima) a 19 (mínima)."}
    if ajenos:
        return {"error": "Solo puedo cambiar la prioridad de procesos tuyos."}
    pre = "sudo -n " if int(valor) < 0 else ""
    return {"comando": f"{pre}renice -n {int(valor)} -p {pids}", "motivo": f"cambiar la prioridad de {nombres}", "comprobar": comprobar, "espera": 0.3}


# ----------------------------------------------------------------------------------------------------------------------
#  SERVICIOS (systemd, del sistema o del usuario)
# ----------------------------------------------------------------------------------------------------------------------
ACCIONES_SERVICIO = ["estado", "listar_fallidos", "listar_en_marcha", "buscar", "registro", "iniciar", "parar", "reiniciar", "recargar",
                     "habilitar", "deshabilitar"]
_UNIDAD = re.compile(r"^[A-Za-z0-9:_.@\\-]{1,100}$")


def _unidades(ambito):
    rc, out = ej(["systemctl", *(["--user"] if ambito == "usuario" else []), "list-unit-files", "--type=service", "--no-legend", "--no-pager"],
                 timeout=10)
    return [l.split()[0] for l in out.splitlines() if l.split()] if rc == 0 else []


def resolver_unidad(nombre):
    """(unidad, ambito, error). Busca en las del usuario y en las del sistema, aunque no se diga exacto."""
    n = str(nombre or "").strip()
    if not n:
        return None, None, "Falta el nombre del servicio."
    if _UNIDAD.match(n) and "." in n and not n.endswith(".service"):
        base = n
    else:
        base = re.sub(r"\.service$", "", n)
    todas = {"usuario": _unidades("usuario"), "sistema": _unidades("sistema")}
    for ambito in ("usuario", "sistema"):
        for u in todas[ambito]:
            if u.lower() in {base.lower(), base.lower() + ".service"}:
                return u, ambito, None
    candidatas = []
    for ambito in ("usuario", "sistema"):
        for u in todas[ambito]:
            candidatas.append((u, ambito))
    cerca = _mejores(base, candidatas, lambda x: (x[0].replace(".service", ""),), minimo=70, margen=3)
    if len(cerca) == 1:
        return cerca[0][0], cerca[0][1], None
    if cerca:
        return None, None, ("Hay varios servicios que encajan con «%s»: %s." % (n, ", ".join(f"{u} ({a})" for u, a in cerca[:8])))
    return None, None, f"No hay ningún servicio que se llame o se parezca a «{n}»."


def _estado_unidad(unidad, ambito):
    pre = ["--user"] if ambito == "usuario" else []
    _, act = ej(["systemctl", *pre, "is-active", unidad])
    _, hab = ej(["systemctl", *pre, "is-enabled", unidad])
    return f"{unidad} ({ambito}): {act.splitlines()[-1] if act else '?'}, al arrancar: {hab.splitlines()[-1] if hab else '?'}"


def planificar_servicios(args):
    accion = str(args.get("accion", "listar_fallidos")).strip().lower()
    if accion not in ACCIONES_SERVICIO:
        return {"error": f"Acción de servicios desconocida «{accion}». Las hay: {', '.join(ACCIONES_SERVICIO)}."}
    if accion == "listar_fallidos":
        _, a = ej(["systemctl", "--failed", "--no-legend", "--no-pager"])
        _, b = ej(["systemctl", "--user", "--failed", "--no-legend", "--no-pager"])
        return {"texto": "Servicios fallidos del sistema:\n" + (a or "(ninguno)") + "\nServicios fallidos de tu usuario:\n" + (b or "(ninguno)")}
    if accion == "listar_en_marcha":
        _, a = ej(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--no-pager"], timeout=10)
        _, b = ej(["systemctl", "--user", "list-units", "--type=service", "--state=running", "--no-legend", "--no-pager"], timeout=10)
        corta = lambda t: "\n".join(" ".join(l.split()[:1] + l.split()[4:]) [:90] for l in t.splitlines()[:40])
        return {"texto": "En marcha (sistema):\n" + corta(a) + "\nEn marcha (usuario):\n" + corta(b)}
    if accion == "buscar":
        q = str(args.get("servicio", "")).strip()
        todas = [(u, "usuario") for u in _unidades("usuario")] + [(u, "sistema") for u in _unidades("sistema")]
        cerca = _mejores(q, todas, lambda x: (x[0].replace(".service", ""),), minimo=65, margen=12)[:15]
        return {"texto": ("Servicios que encajan: " + ", ".join(f"{u} ({a})" for u, a in cerca)) if cerca else f"Ninguno encaja con «{q}»."}
    unidad, ambito, error = resolver_unidad(args.get("servicio", ""))
    if error:
        return {"error": error}
    pre = ["--user"] if ambito == "usuario" else []
    if accion == "estado":
        rc, out = ej(["systemctl", *pre, "status", unidad, "--no-pager", "-n", "12"], timeout=10)
        return {"texto": out[:1800] if out else _estado_unidad(unidad, ambito)}
    if accion == "registro":
        rc, out = ej(["journalctl", *pre, "-u", unidad, "-n", "40", "--no-pager", "-o", "short"], timeout=10)
        return {"texto": out[-2500:] if out else "Sin registros."}
    verbo = {"iniciar": "start", "parar": "stop", "reiniciar": "restart", "recargar": "reload-or-restart",
             "habilitar": "enable", "deshabilitar": "disable"}[accion]
    ahora = " --now" if accion in {"habilitar", "deshabilitar"} and args.get("ahora") else ""
    sudo = "" if ambito == "usuario" else "sudo -n "
    return {"comando": f"{sudo}systemctl {'--user ' if ambito == 'usuario' else ''}{verbo}{ahora} {_q(unidad)}",
            "motivo": f"{accion} el servicio {unidad.replace('.service', '')}", "espera": 1.5,
            "comprobar": lambda: _estado_unidad(unidad, ambito)}


# ----------------------------------------------------------------------------------------------------------------------
#  RED y BLUETOOTH
# ----------------------------------------------------------------------------------------------------------------------
ACCIONES_RED = ["estado", "wifi_redes", "wifi_encender", "wifi_apagar", "conectar", "desconectar", "probar", "dns",
                "bluetooth_estado", "bluetooth_encender", "bluetooth_apagar", "bluetooth_conectar", "bluetooth_desconectar"]
_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$|^[0-9a-fA-F:]{2,39}$")


def _conexiones_guardadas():
    rc, out = ej(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    res = []
    for l in out.splitlines() if rc == 0 else []:
        n, _, t = l.rpartition(":")
        if n:
            res.append((n.replace("\\:", ":"), t))
    return res


def _bt_dispositivos():
    rc, out = ej(["bluetoothctl", "devices"], timeout=6)
    rc2, conectados = ej(["bluetoothctl", "devices", "Connected"], timeout=6)
    conn = {l.split()[1] for l in conectados.splitlines() if l.startswith("Device") and len(l.split()) > 2} if rc2 == 0 else set()
    res = []
    for l in out.splitlines() if rc == 0 else []:
        p = l.split(None, 2)
        if len(p) == 3 and p[0] == "Device":
            res.append({"mac": p[1], "nombre": p[2], "conectado": p[1] in conn})
    return res


def estado_red():
    _, d = ej(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    _, ip = ej(["ip", "-br", "-4", "addr"])
    _, ruta = ej(["ip", "route", "show", "default"])
    _, con = ej(["nmcli", "-t", "networking", "connectivity"])
    _, wifi = ej(["nmcli", "-t", "radio", "wifi"])
    return (f"Conectividad: {con or '?'} · Wi-Fi (radio): {wifi or '?'}\nDispositivos:\n"
            + "\n".join("- " + l.replace(":", " · ") for l in d.splitlines() if not l.startswith("lo:"))
            + f"\nDirecciones IPv4:\n{ip}\nPuerta de enlace: {ruta.splitlines()[0] if ruta else '(ninguna)'}")


def planificar_red(args):
    accion = str(args.get("accion", "estado")).strip().lower()
    if accion not in ACCIONES_RED:
        return {"error": f"Acción de red desconocida «{accion}». Las hay: {', '.join(ACCIONES_RED)}."}
    objetivo = str(args.get("objetivo", "") or "").strip()
    if accion == "estado":
        return {"texto": estado_red()}
    if accion == "wifi_redes":
        rc, out = ej(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list"], timeout=12)
        filas = [l.replace("*:", "★ ", 1).replace(":", " · ") for l in out.splitlines() if l.split(":")[1:2] != [""]] if rc == 0 else []
        return {"texto": "Redes Wi-Fi a la vista:\n" + "\n".join(filas[:20]) if filas else f"No veo redes Wi-Fi ({out[:120]})."}
    if accion in {"probar", "dns"}:
        host = objetivo or "1.1.1.1"
        if not _HOST.match(host):
            return {"error": "Ese destino no parece una dirección ni un nombre válido."}
        if accion == "dns":
            rc, out = ej(["getent", "hosts", host], timeout=8)
            return {"texto": out if rc == 0 and out else f"No se resuelve «{host}» (¿DNS caído?)."}
        rc, out = ej(["ping", "-c", "3", "-W", "2", host], timeout=12)
        resumen = [l for l in out.splitlines() if "packet loss" in l or "rtt" in l or "min/avg" in l]
        return {"texto": f"Ping a {host}: " + (" | ".join(resumen) if resumen else f"sin respuesta ({out[-120:]})")}
    if accion in {"wifi_encender", "wifi_apagar"}:
        quiere = "on" if accion == "wifi_encender" else "off"
        return {"comando": f"nmcli radio wifi {quiere}", "motivo": f"{'encender' if quiere == 'on' else 'apagar'} el Wi-Fi", "espera": 2.0,
                "comprobar": lambda: "Wi-Fi (radio) ahora: " + ej(["nmcli", "-t", "radio", "wifi"])[1]}
    if accion in {"conectar", "desconectar"}:
        guardadas = _conexiones_guardadas()
        if accion == "desconectar" and not objetivo:
            rc, out = ej(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
            activas = [l.rpartition(":")[0] for l in out.splitlines() if l and not l.endswith(("loopback", ":bridge"))] if rc == 0 else []
            if len(activas) != 1:
                return {"error": "Hay varias conexiones activas; di cuál: " + ", ".join(activas)}
            objetivo = activas[0]
        cerca = _mejores(objetivo, guardadas, lambda x: (x[0],), minimo=70, margen=3)
        if not cerca:
            return {"error": (f"No hay ninguna conexión guardada que se parezca a «{objetivo}». Guardadas: "
                              + ", ".join(n for n, _ in guardadas[:20]) + ". Conectarse a una red NUEVA pide contraseña: eso lo hace el usuario.")}
        if len(cerca) > 1:
            return {"error": "Encajan varias conexiones: " + ", ".join(n for n, _ in cerca)}
        nombre = cerca[0][0]
        verbo = "up" if accion == "conectar" else "down"
        return {"comando": f"nmcli connection {verbo} id {_q(nombre)}", "motivo": f"{accion} la conexión {nombre}", "espera": 3.0,
                "comprobar": lambda: estado_red()}
    # ---- Bluetooth ----
    if accion == "bluetooth_estado":
        _, show = ej(["bluetoothctl", "show"], timeout=6)
        datos = [l.strip() for l in show.splitlines() if l.strip().startswith(("Powered", "Discoverable", "Pairable", "Name"))]
        disp = _bt_dispositivos()
        return {"texto": "Bluetooth:\n" + "\n".join(datos) + "\nDispositivos:\n"
                + ("\n".join(f"- {d['nombre']} ({d['mac']}) {'CONECTADO' if d['conectado'] else 'no conectado'}" for d in disp) or "(ninguno emparejado)")}
    if accion in {"bluetooth_encender", "bluetooth_apagar"}:
        quiere = "on" if accion.endswith("encender") else "off"
        return {"comando": f"bluetoothctl power {quiere}", "motivo": f"{'encender' if quiere == 'on' else 'apagar'} el Bluetooth", "espera": 1.5,
                "comprobar": lambda: "Bluetooth ahora: " + " ".join(l.strip() for l in ej(["bluetoothctl", "show"])[1].splitlines() if "Powered" in l)}
    disp = _bt_dispositivos()
    cerca = _mejores(objetivo, disp, lambda d: (d["nombre"],), minimo=65, margen=3) if objetivo else (
        [d for d in disp if d["conectado"]] if accion == "bluetooth_desconectar" else [])
    if not cerca:
        return {"error": "No encuentro ese dispositivo entre los emparejados: " + (", ".join(d["nombre"] for d in disp) or "(ninguno)")}
    if len(cerca) > 1:
        return {"error": "Encajan varios dispositivos: " + ", ".join(d["nombre"] for d in cerca)}
    d = cerca[0]
    verbo = "connect" if accion == "bluetooth_conectar" else "disconnect"
    return {"comando": f"bluetoothctl {verbo} {d['mac']}", "motivo": f"{verbo.replace('connect', 'conectar') if verbo=='connect' else 'desconectar'} {d['nombre']}", "espera": 3.0,
            "comprobar": lambda: "Ahora: " + "; ".join(f"{x['nombre']} {'conectado' if x['conectado'] else 'no conectado'}"
                                                      for x in _bt_dispositivos() if x['mac'] == d['mac'])}


# ----------------------------------------------------------------------------------------------------------------------
#  ENERGÍA
# ----------------------------------------------------------------------------------------------------------------------
ACCIONES_ENERGIA = ["estado", "perfil", "bloquear", "apagar_pantalla", "suspender", "hibernar", "reiniciar", "apagar", "cerrar_sesion"]
_PERFILES = {"ahorro": "power-saver", "ahorrar": "power-saver", "power saver": "power-saver", "power-saver": "power-saver",
             "equilibrado": "balanced", "balanced": "balanced", "normal": "balanced",
             "rendimiento": "performance", "performance": "performance", "maximo": "performance", "máximo": "performance"}


def planificar_energia(args):
    accion = str(args.get("accion", "estado")).strip().lower()
    if accion not in ACCIONES_ENERGIA:
        return {"error": f"Acción de energía desconocida «{accion}». Las hay: {', '.join(ACCIONES_ENERGIA)}."}
    valor = str(args.get("valor", "") or "").strip()
    if accion == "estado":
        partes = []
        rc, perfil = ej(["powerprofilesctl", "get"])
        partes.append("Perfil de energía: " + (perfil if rc == 0 else "no disponible (power-profiles-daemon no responde)"))
        rc, gov = ej(["cat", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"])
        if rc == 0:
            partes.append("Gobernador de CPU: " + gov)
        rc, gpu = ej(["nvidia-smi", "--query-gpu=name,power.draw,power.limit,temperature.gpu,utilization.gpu,clocks.gr",
                      "--format=csv,noheader"], timeout=8)
        if rc == 0 and gpu:
            partes.append("GPU (nombre, consumo, límite, °C, uso, MHz): " + gpu)
        rc, enum = ej(["upower", "-e"])
        bat = [l for l in enum.splitlines() if "battery" in l] if rc == 0 else []
        for b in bat[:1]:
            _, info = ej(["upower", "-i", b])
            partes.append("Batería: " + " ".join(l.strip() for l in info.splitlines() if l.strip().startswith(("state", "percentage", "time to"))))
        if not bat:
            partes.append("No hay batería (equipo de sobremesa).")
        rc, up = ej(["uptime", "-p"])
        partes.append("Encendido: " + (up if rc == 0 else "?"))
        rc, inh = ej(["systemd-inhibit", "--list", "--no-pager", "--no-legend"])
        if rc == 0 and inh:
            partes.append("Programas que impiden suspender/apagar:\n" + "\n".join(inh.splitlines()[:6]))
        return {"texto": "\n".join(partes)}
    if accion == "perfil":
        if not valor:
            rc, p = ej(["powerprofilesctl", "get"])
            return {"texto": f"Perfil actual: {p}" if rc == 0 else "No puedo leer el perfil de energía (¿falta power-profiles-daemon?)."}
        p = _PERFILES.get(_norm(valor).replace(" ", " ")) or _PERFILES.get(valor.lower())
        if not p:
            return {"error": "Perfiles: ahorro (power-saver), equilibrado (balanced) o rendimiento (performance)."}
        return {"comando": f"powerprofilesctl set {p}", "motivo": f"poner el perfil de energía en {p}", "espera": 0.5, "esperado": p,
                "comprobar": lambda: "Perfil ahora: " + ej(["powerprofilesctl", "get"])[1]}
    if accion == "bloquear":
        return {"comando": "loginctl lock-session", "motivo": "bloquear la pantalla", "espera": 0.5, "comprobar": lambda: "Pantalla bloqueada."}
    if accion == "apagar_pantalla":
        return {"comando": "kscreen-doctor --dpms off", "motivo": "apagar las pantallas (se encienden al mover el ratón)", "espera": 0.3,
                "comprobar": lambda: "Pantallas apagadas; se encienden al mover el ratón o pulsar una tecla."}
    if accion == "cerrar_sesion":
        return {"comando": "qdbus6 org.kde.LogoutPrompt /LogoutPrompt promptLogout", "motivo": "cerrar la sesión", "comprobar": lambda: ""}
    verbo = {"suspender": "suspend", "hibernar": "hibernate", "reiniciar": "reboot", "apagar": "poweroff"}[accion]
    return {"comando": f"systemctl {verbo}", "motivo": f"{accion} el equipo", "comprobar": lambda: ""}


# ----------------------------------------------------------------------------------------------------------------------
#  PANTALLA (kscreen-doctor, brillo)
# ----------------------------------------------------------------------------------------------------------------------
ACCIONES_PANTALLA = ["listar", "modo", "escala", "posicion", "girar", "activar", "desactivar", "principal", "vrr", "hdr",
                     "brillo", "revertir"]
_GIROS = {"normal": "normal", "ninguno": "normal", "izquierda": "left", "left": "left", "derecha": "right", "right": "right",
          "invertido": "inverted", "inverted": "inverted", "boca abajo": "inverted"}
_GIRO_NUM = {1: "normal", 2: "left", 4: "inverted", 8: "right"}


def leer_pantallas():
    rc, out = ej(["kscreen-doctor", "-j"], timeout=10)
    if rc != 0:
        return None, f"No puedo leer las pantallas ({out[:120]})."
    try:
        datos = json.loads(out)
    except ValueError:
        return None, "kscreen-doctor no ha dado un JSON legible."
    salidas = []
    for o in datos.get("outputs", []):
        if not o.get("connected", True):
            continue
        modos = []
        for m in o.get("modes", []):
            tam = m.get("size", {})
            modos.append({"id": str(m.get("id")), "w": int(tam.get("width", 0)), "h": int(tam.get("height", 0)),
                          "hz": float(m.get("refreshRate", 0))})
        actual = next((m for m in modos if m["id"] == str(o.get("currentModeId"))), None)
        pos = o.get("pos", {})
        salidas.append({"nombre": o.get("name", "?"), "activa": bool(o.get("enabled")), "prioridad": int(o.get("priority", 0) or 0),
                        "modos": modos, "actual": actual, "escala": float(o.get("scale", 1) or 1),
                        "x": int(pos.get("x", 0)), "y": int(pos.get("y", 0)), "giro": _GIRO_NUM.get(int(o.get("rotation", 1) or 1), "normal"),
                        "vrr": o.get("vrrPolicy"), "hdr": o.get("hdr")})
    return salidas, None


def _texto_pantallas(salidas):
    filas = []
    for o in salidas:
        a = o["actual"]
        modo = f"{a['w']}x{a['h']}@{a['hz']:.0f}" if a else "?"
        tam = sorted({(m["w"], m["h"]) for m in o["modos"]}, reverse=True)[:6]
        filas.append(f"- {o['nombre']}: {'ACTIVA' if o['activa'] else 'apagada'}"
                     + (", principal" if o["prioridad"] == 1 else "") + f", {modo}, escala {o['escala']:g}, posición {o['x']},{o['y']}, giro {o['giro']}"
                     + (f", VRR {o['vrr']}" if o["vrr"] is not None else "") + (f", HDR {o['hdr']}" if o["hdr"] is not None else "")
                     + "\n    resoluciones: " + ", ".join(f"{w}x{h}" for w, h in tam)
                     + "\n    frecuencias: " + ", ".join(f"{hz:g}" for hz in sorted({m['hz'] for m in o['modos']}, reverse=True)[:8]))
    return "Pantallas:\n" + "\n".join(filas)


def _guardar_previo(salidas):
    try:
        os.makedirs(os.path.dirname(ARCHIVO_PANTALLA_PREVIA), exist_ok=True)
        with open(ARCHIVO_PANTALLA_PREVIA, "w", encoding="utf-8") as f:
            json.dump({"cuando": time.time(), "salidas": [
                {"nombre": o["nombre"], "activa": o["activa"], "prioridad": o["prioridad"], "modo": o["actual"]["id"] if o["actual"] else None,
                 "escala": o["escala"], "x": o["x"], "y": o["y"], "giro": o["giro"]} for o in salidas]}, f)
    except OSError:
        pass


def _orden_para_restaurar(previo):
    partes = []
    for o in previo:
        n = o["nombre"]
        partes.append(f"output.{n}.{'enable' if o['activa'] else 'disable'}")
        if o["activa"]:
            if o.get("modo"):
                partes.append(f"output.{n}.mode.{o['modo']}")
            partes += [f"output.{n}.scale.{o['escala']:g}", f"output.{n}.position.{o['x']},{o['y']}", f"output.{n}.rotation.{o['giro']}"]
            if o.get("prioridad"):
                partes.append(f"output.{n}.priority.{o['prioridad']}")
    return "kscreen-doctor " + " ".join(_q(p) for p in partes)


def _logico(o):
    a = o["actual"]
    if not a:
        return (0, 0)
    w, h = a["w"] / o["escala"], a["h"] / o["escala"]
    return (h, w) if o["giro"] in {"left", "right"} else (w, h)


def _se_solapan(a, b):
    (wa, ha), (wb, hb) = _logico(a), _logico(b)
    return a["x"] < b["x"] + wb and b["x"] < a["x"] + wa and a["y"] < b["y"] + hb and b["y"] < a["y"] + ha


def _brillo_kde():
    """[(ruta, actual, maximo)] con el servicio de brillo de Plasma 6 (también monitores por DDC)."""
    rc, out = ej(["busctl", "--user", "tree", "org.kde.ScreenBrightness", "--no-pager"], timeout=6)
    if rc != 0:
        return []
    res = []
    for l in out.splitlines():
        m = re.search(r"(/org/kde/ScreenBrightness/\S+)", l)
        if not m:
            continue
        ruta = m.group(1)
        r1, a = ej(["busctl", "--user", "get-property", "org.kde.ScreenBrightness", ruta, "org.kde.ScreenBrightness.Display", "Brightness"])
        r2, mx = ej(["busctl", "--user", "get-property", "org.kde.ScreenBrightness", ruta, "org.kde.ScreenBrightness.Display", "MaxBrightness"])
        if r1 == 0 and r2 == 0:
            try:
                res.append((ruta, int(a.split()[-1]), int(mx.split()[-1])))
            except ValueError:
                pass
    return res


def planificar_pantalla(args):
    accion = str(args.get("accion", "listar")).strip().lower()
    if accion not in ACCIONES_PANTALLA:
        return {"error": f"Acción de pantalla desconocida «{accion}». Las hay: {', '.join(ACCIONES_PANTALLA)}."}
    valor = str(args.get("valor", "") or "").strip()
    salida_pedida = str(args.get("salida", "") or "").strip()
    if accion == "brillo":
        return _planificar_brillo(valor)
    salidas, error = leer_pantallas()
    if error:
        return {"error": error}
    if accion == "listar":
        return {"texto": _texto_pantallas(salidas)}
    if accion == "revertir":
        try:
            with open(ARCHIVO_PANTALLA_PREVIA, encoding="utf-8") as f:
                previo = json.load(f)["salidas"]
        except (OSError, ValueError, KeyError):
            return {"error": "No tengo guardada la configuración anterior de pantallas."}
        return {"comando": _orden_para_restaurar(previo), "motivo": "volver a la configuración de pantallas de antes", "espera": 2.5,
                "comprobar": lambda: _texto_pantallas(leer_pantallas()[0] or [])}
    if salida_pedida:
        cerca = _mejores(salida_pedida, salidas, lambda o: (o["nombre"],), minimo=70, margen=2)
        if len(cerca) != 1:
            return {"error": f"No sé a qué pantalla te refieres con «{salida_pedida}».\n" + _texto_pantallas(salidas)}
        o = cerca[0]
    else:
        activas = [x for x in salidas if x["activa"]]
        if len(salidas) == 1:
            o = salidas[0]
        elif accion in {"modo", "escala", "girar", "vrr", "hdr"} and len(activas) == 1:
            o = activas[0]
        else:
            return {"error": "Hay varias pantallas: dime en «salida» cuál.\n" + _texto_pantallas(salidas)}
    n = o["nombre"]

    def hecho(texto):
        return {"comando": "kscreen-doctor " + _q(texto["orden"]), "motivo": texto["motivo"], "espera": 2.5, "previo": salidas,
                "esperado": dict(texto.get("esperado") or {}, salida=n),
                "comprobar": lambda: _texto_pantallas(leer_pantallas()[0] or [])
                + "\nSi algo se ve mal: pantalla(accion=revertir) vuelve a como estaba."}

    if accion == "modo":
        m = re.fullmatch(r"\s*(?:(\d{3,5})\s*[x×]\s*(\d{3,5}))?\s*(?:@|a|,)?\s*(\d{2,3}(?:\.\d+)?)?\s*(?:hz)?\s*", valor.lower())
        if not m or not (m.group(1) or m.group(3)):
            return {"error": "Para el modo, «valor» es «2560x1440@144», «1920x1080» o solo la frecuencia («144»)."}
        w = int(m.group(1)) if m.group(1) else (o["actual"]["w"] if o["actual"] else 0)
        h = int(m.group(2)) if m.group(2) else (o["actual"]["h"] if o["actual"] else 0)
        hz = float(m.group(3)) if m.group(3) else None
        candidatos = [x for x in o["modos"] if x["w"] == w and x["h"] == h]
        if hz is not None:
            candidatos = [x for x in candidatos if abs(x["hz"] - hz) < 1.0]
        if not candidatos:
            return {"error": f"{n} no tiene ese modo.\n" + _texto_pantallas([o])}
        mejor = max(candidatos, key=lambda x: x["hz"])
        return hecho({"orden": f"output.{n}.mode.{mejor['id']}", "motivo": f"poner {n} a {mejor['w']}x{mejor['h']}@{mejor['hz']:.0f}",
                      "esperado": {"modo": mejor["id"]}})
    if accion == "escala":
        try:
            e = float(valor.replace(",", ".").replace("%", ""))
        except ValueError:
            return {"error": "«valor» es la escala: 1, 1.25, 1.5, 2... (o un porcentaje como 125)."}
        if e > 10:
            e /= 100
        if not 0.5 <= e <= 3:
            return {"error": "La escala tiene que estar entre 0.5 y 3."}
        return hecho({"orden": f"output.{n}.scale.{e:g}", "motivo": f"poner la escala de {n} en {e:g}", "esperado": {"escala": e}})
    if accion == "girar":
        g = _GIROS.get(_norm(valor)) or _GIROS.get(valor.lower())
        if not g:
            return {"error": "«valor»: normal, izquierda, derecha o invertido."}
        return hecho({"orden": f"output.{n}.rotation.{g}", "motivo": f"girar {n} ({g})", "esperado": {"giro": g}})
    if accion == "posicion":
        m = re.fullmatch(r"\s*(-?\d{1,6})\s*[ ,x]\s*(-?\d{1,6})\s*", valor)
        if not m:
            return {"error": "«valor» es «x,y» en píxeles lógicos (por ejemplo 2560,0 para ponerla a la derecha de una de 2560)."}
        nuevo = dict(o, x=int(m.group(1)), y=int(m.group(2)))
        choca = [x["nombre"] for x in salidas if x["nombre"] != n and x["activa"] and nuevo["activa"] and _se_solapan(nuevo, x)]
        if choca:
            return {"error": (f"Con esa posición {n} se SOLAPARÍA con {', '.join(choca)} (se vería una encima de otra, no en espejo). "
                              "Mira las posiciones y tamaños con pantalla(listar) y elige unas que no se pisen.")}
        return hecho({"orden": f"output.{n}.position.{nuevo['x']},{nuevo['y']}", "motivo": f"mover {n} a {nuevo['x']},{nuevo['y']}",
                      "esperado": {"pos": [nuevo["x"], nuevo["y"]]}})
    if accion == "activar":
        return hecho({"orden": f"output.{n}.enable", "motivo": f"encender la pantalla {n}"})
    if accion == "desactivar":
        if sum(1 for x in salidas if x["activa"] and x["nombre"] != n) == 0:
            return {"error": f"{n} es la única pantalla encendida: apagarla dejaría el equipo sin imagen. No lo hago."}
        return hecho({"orden": f"output.{n}.disable", "motivo": f"apagar la pantalla {n}"})
    if accion == "principal":
        return hecho({"orden": f"output.{n}.primary", "motivo": f"poner {n} como pantalla principal", "esperado": {"principal": True}})
    if accion == "vrr":
        p = {"nunca": "never", "never": "never", "no": "never", "automatico": "automatic", "automático": "automatic", "automatic": "automatic",
             "siempre": "always", "always": "always"}.get(_norm(valor)) or {"nunca": "never"}.get(valor.lower())
        if not p:
            return {"error": "«valor» para VRR: nunca, automatico o siempre."}
        return hecho({"orden": f"output.{n}.vrrpolicy.{p}", "motivo": f"VRR de {n}: {p}"})
    quiere = {"si": "enable", "activar": "enable", "on": "enable", "enable": "enable", "no": "disable", "desactivar": "disable",
              "off": "disable", "disable": "disable"}.get(_norm(valor))
    if not quiere:
        return {"error": "«valor» para HDR: si o no."}
    return hecho({"orden": f"output.{n}.hdr.{quiere}", "motivo": f"HDR de {n}: {quiere}"})


def _planificar_brillo(valor):
    pantallas = _brillo_kde()
    if not valor:
        if pantallas:
            return {"texto": "Brillo: " + "; ".join(f"{r.rsplit('/', 1)[-1]} {a * 100 // max(m, 1)}%" for r, a, m in pantallas)}
        rc, out = ej(["brightnessctl", "-m"])
        return {"texto": f"Brillo: {out}" if rc == 0 and out else "No encuentro un control de brillo (ni en Plasma ni brightnessctl). Si el monitor es externo, hace falta DDC/CI."}
    m = re.fullmatch(r"\s*([+-])?\s*(\d{1,3})\s*%?\s*", valor)
    if not m:
        return {"error": "«valor» es un porcentaje (40), o con signo para subir/bajar (+10, -10)."}
    n = int(m.group(2))
    rel = m.group(1)
    if not rel and not 0 <= n <= 100:
        return {"error": "El brillo va de 0 a 100."}
    if pantallas:
        cmds = []
        for ruta, actual, mx in pantallas:
            obj = actual + (n if rel == "+" else -n if rel == "-" else 0) * mx // 100 if rel else n * mx // 100
            obj = max(1 if mx > 1 else 0, min(mx, obj))
            cmds.append(f"busctl --user call org.kde.ScreenBrightness {_q(ruta)} org.kde.ScreenBrightness.Display SetBrightness iu {obj} 0")
        return {"comando": " && ".join(cmds), "motivo": f"ajustar el brillo ({valor})", "espera": 1.0,
                "comprobar": lambda: "Brillo ahora: " + "; ".join(f"{r.rsplit('/', 1)[-1]} {a * 100 // max(mx, 1)}%" for r, a, mx in _brillo_kde())}
    if shutil.which("brightnessctl"):
        arg = f"{n}%{rel}" if rel in {"+", "-"} and False else (f"{n}%+" if rel == "+" else f"{n}%-" if rel == "-" else f"{n}%")
        return {"comando": f"brightnessctl set {arg}", "motivo": f"ajustar el brillo ({valor})", "espera": 0.5,
                "comprobar": lambda: "Brillo ahora: " + ej(["brightnessctl", "-m"])[1]}
    return {"error": "No encuentro un control de brillo para esta pantalla (ni Plasma ni brightnessctl). Los monitores externos necesitan DDC/CI."}


# ----------------------------------------------------------------------------------------------------------------------
#  AUDIO (PipeWire con wpctl y pactl)
# ----------------------------------------------------------------------------------------------------------------------
ACCIONES_AUDIO = ["estado", "volumen", "subir", "bajar", "silenciar", "activar_sonido", "salida_por_defecto", "entrada_por_defecto",
                  "mover_app"]
_SECCION = re.compile(r"(Sinks|Sources|Streams|Devices|Filters|Clients|Sink endpoints|Source endpoints):\s*$")
_ELEM = re.compile(r"^[\s│├└─]*(\*)?\s*(\d+)\.\s+(.*?)(?:\s+\[vol:\s*([\d.]+)(\s+MUTED)?\])?\s*$")
VOLUMEN_MAXIMO = 100


def leer_audio():
    rc, out = ej(["wpctl", "status"], timeout=8)
    if rc != 0:
        return None, f"No puedo leer el audio ({out[:120]}). ¿PipeWire/WirePlumber en marcha?"
    res = {"Sinks": [], "Sources": [], "Streams": []}
    seccion, ind_stream = None, None
    for linea in out.splitlines():
        m = _SECCION.search(linea)
        if m:
            seccion = m.group(1)
            ind_stream = None
            continue
        if seccion not in res:
            continue
        e = _ELEM.match(linea)
        if not e:
            continue
        pref = len(linea) - len(linea.lstrip(" │├└─"))
        nombre = e.group(3).strip()
        if seccion == "Streams":
            if ind_stream is None:
                ind_stream = pref
            if pref > ind_stream or re.search(r"\s[<>]\s|_(FL|FR|MONO)\b", nombre):
                continue                                         # son los puertos de la app, no la app
        res[seccion].append({"id": int(e.group(2)), "nombre": nombre, "defecto": bool(e.group(1)),
                             "vol": float(e.group(4)) if e.group(4) else None, "mudo": bool(e.group(5))})
    return res, None


def _texto_audio(a):
    def fila(x):
        v = f", volumen {round(x['vol'] * 100)}%" if x["vol"] is not None else ""
        return f"- [{x['id']}] {x['nombre']}{v}{' MUTE' if x['mudo'] else ''}{' ← por defecto' if x['defecto'] else ''}"
    return ("Salidas:\n" + ("\n".join(fila(x) for x in a["Sinks"]) or "(ninguna)") + "\nEntradas:\n"
            + ("\n".join(fila(x) for x in a["Sources"]) or "(ninguna)") + "\nApps con sonido:\n" + ("\n".join(fila(x) for x in a["Streams"]) or "(ninguna)"))


def _elegir_audio(a, objetivo, preferir=("Sinks", "Streams", "Sources")):
    """(tipo, elemento, error). Sin objetivo: la salida por defecto."""
    if not objetivo:
        d = next((x for x in a["Sinks"] if x["defecto"]), None)
        return ("Sinks", d, None) if d else (None, None, "No hay salida de audio por defecto.")
    if str(objetivo).isdigit():
        for t in ("Sinks", "Sources", "Streams"):
            for x in a[t]:
                if x["id"] == int(objetivo):
                    return t, x, None
    todos = [(t, x) for t in preferir for x in a[t]]
    cerca = _mejores(objetivo, todos, lambda p: (p[1]["nombre"],), minimo=65, margen=3)
    if not cerca:
        return None, None, f"No encuentro «{objetivo}» en el audio.\n" + _texto_audio(a)
    if len(cerca) > 1:
        return None, None, "Encajan varios; di el número entre corchetes:\n" + "\n".join(f"- [{x['id']}] {x['nombre']} ({t})" for t, x in cerca[:8])
    return cerca[0][0], cerca[0][1], None


def _volumen_ahora(ref):
    rc, out = ej(["wpctl", "get-volume", str(ref)])
    return out if rc == 0 else "?"


def planificar_audio(args):
    accion = str(args.get("accion", "estado")).strip().lower()
    if accion not in ACCIONES_AUDIO:
        return {"error": f"Acción de audio desconocida «{accion}». Las hay: {', '.join(ACCIONES_AUDIO)}."}
    a, error = leer_audio()
    if error:
        return {"error": error}
    objetivo = str(args.get("objetivo", "") or "").strip()
    valor = str(args.get("valor", "") or "").strip()
    if accion == "estado":
        return {"texto": _texto_audio(a)}
    mic = _norm(objetivo) in {"microfono", "mic", "entrada", "input"}
    if mic:
        d = next((x for x in a["Sources"] if x["defecto"]), None)
        tipo, x, error = ("Sources", d, None) if d else (None, None, "No hay micrófono por defecto.")
    else:
        tipo, x, error = _elegir_audio(a, objetivo, preferir=("Sinks", "Streams", "Sources") if accion != "entrada_por_defecto" else ("Sources",))
    if error:
        return {"error": error}
    ref = x["id"]
    if accion == "salida_por_defecto" or accion == "entrada_por_defecto":
        if tipo not in {"Sinks", "Sources"}:
            return {"error": "Eso no es un dispositivo de audio, es una app."}
        return {"comando": f"wpctl set-default {ref}", "motivo": f"usar {x['nombre']} como {'salida' if tipo == 'Sinks' else 'entrada'} de audio", "espera": 0.5,
                "comprobar": lambda: "Ahora por defecto: " + ", ".join(f"{y['nombre']}" for t in ('Sinks', 'Sources') for y in (leer_audio()[0] or {}).get(t, []) if y['defecto'])}
    if accion == "mover_app":
        if tipo != "Streams":
            return {"error": "En «objetivo» va la app (por ejemplo Firefox) y en «valor» la salida de destino."}
        destino = _mejores(valor, a["Sinks"], lambda s: (s["nombre"],), minimo=65, margen=3)
        if len(destino) != 1:
            return {"error": "No sé a qué salida moverla. Salidas: " + ", ".join(f"[{s['id']}] {s['nombre']}" for s in a["Sinks"])}
        rc, out = ej(["pactl", "list", "short", "sinks"])
        nombre_sink = None
        for l in out.splitlines() if rc == 0 else []:
            p = l.split("\t")
            if p and p[0].isdigit():
                rc2, props = ej(["wpctl", "inspect", str(destino[0]["id"])])
                m = re.search(r'node\.name = "([^"]+)"', props)
                if m and p[1] == m.group(1):
                    nombre_sink = p[1]
        rc3, ent = ej(["pactl", "list", "short", "sink-inputs"])
        rc4, props_app = ej(["wpctl", "inspect", str(ref)])
        m = re.search(r'object\.serial = (\d+)', props_app)
        if not nombre_sink or not m:
            return {"error": "No he podido averiguar los identificadores para mover esa app; usa pactl move-sink-input con ejecutar_comando."}
        serial = m.group(1)
        entrada = next((l.split("\t")[0] for l in ent.splitlines() if l.split("\t")[0] == serial), None) or serial
        return {"comando": f"pactl move-sink-input {entrada} {_q(nombre_sink)}", "motivo": f"mover {x['nombre']} a {destino[0]['nombre']}", "espera": 0.5,
                "comprobar": lambda: "Hecho; comprueba con audio(estado)."}
    destino = str(ref)
    if tipo == "Sinks" and not objetivo:
        destino = "@DEFAULT_AUDIO_SINK@"
    elif tipo == "Sources" and mic:
        destino = "@DEFAULT_AUDIO_SOURCE@"
    if accion in {"silenciar", "activar_sonido"}:
        mudo = "1" if accion == "silenciar" else "0"
        return {"comando": f"wpctl set-mute {destino} {mudo}", "motivo": f"{'silenciar' if mudo == '1' else 'activar el sonido de'} {x['nombre']}", "espera": 0.3,
                "comprobar": lambda: f"{x['nombre']}: " + _volumen_ahora(destino)}
    if accion == "volumen":
        m = re.fullmatch(r"\s*(\d{1,3})\s*%?\s*", valor)
        if not m:
            return {"error": "«valor» es el porcentaje de volumen (0-100)."}
        n = int(m.group(1))
        objetivo_n = min(n, VOLUMEN_MAXIMO)
        pasa = f" (limitado a {VOLUMEN_MAXIMO}%: por encima distorsiona y puede dañar)" if n > VOLUMEN_MAXIMO else ""
        return {"comando": f"wpctl set-volume {destino} {objetivo_n}%", "motivo": f"poner el volumen de {x['nombre']} al {objetivo_n}%{pasa}", "espera": 0.3,
                "comprobar": lambda: f"{x['nombre']}: " + _volumen_ahora(destino) + pasa}
    m = re.fullmatch(r"\s*(\d{1,2})\s*%?\s*", valor or "10")
    paso = int(m.group(1)) if m else 10
    signo = "+" if accion == "subir" else "-"
    return {"antes_vol": x.get("vol"), "comando": f"wpctl set-volume {destino} {paso}%{signo}" + (f" -l {VOLUMEN_MAXIMO / 100:g}" if signo == "+" else ""),
            "motivo": f"{'subir' if signo == '+' else 'bajar'} el volumen de {x['nombre']} {paso}%", "espera": 0.3,
            "comprobar": lambda: f"{x['nombre']}: " + _volumen_ahora(destino)}


# ----------------------------------------------------------------------------------------------------------------------
#  D-BUS de KDE (la «comunicación interna» del escritorio)
# ----------------------------------------------------------------------------------------------------------------------
ACCIONES_DBUS = ["servicios", "objetos", "metodos", "propiedad", "llamar"]
_SERV = re.compile(r"^(?:[A-Za-z_][\w-]*(?:\.[\w-]+)+|:\d+\.\d+)$")
_RUTA = re.compile(r"^/[\w/]*$")
_METODO = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*$")


def _qdbus():
    for n in ("qdbus6", "qdbus-qt6", "qdbus"):
        if shutil.which(n):
            return n
    return "qdbus6"


def planificar_dbus(args):
    accion = str(args.get("accion", "servicios")).strip().lower()
    if accion not in ACCIONES_DBUS:
        return {"error": f"Acción de D-Bus desconocida «{accion}». Las hay: {', '.join(ACCIONES_DBUS)}."}
    serv = str(args.get("servicio", "") or "").strip()
    ruta = str(args.get("ruta", "") or "").strip() or "/"
    iface = str(args.get("interfaz", "") or "").strip()
    metodo = str(args.get("metodo", "") or "").strip()
    if accion == "servicios":
        rc, out = ej(["busctl", "--user", "list", "--no-pager", "--no-legend"], timeout=8)
        nombres = sorted({l.split()[0] for l in out.splitlines() if l.split() and not l.split()[0].startswith(":")}) if rc == 0 else []
        if serv:
            nombres = [n for n in nombres if _norm(serv) in _norm(n)]
        return {"texto": ("Servicios D-Bus de tu sesión:\n" + "\n".join(nombres[:80])) if nombres else "No veo servicios (¿busctl instalado?)."}
    if not _SERV.match(serv):
        return {"error": "Falta «servicio» (por ejemplo org.kde.KWin). Con accion=servicios se ven los que hay."}
    if not _RUTA.match(ruta):
        return {"error": "La ruta tiene que ser tipo /KWin o /org/kde/ScreenBrightness."}
    if accion == "objetos":
        rc, out = ej(["busctl", "--user", "tree", serv, "--no-pager"], timeout=8)
        return {"texto": "\n".join(out.splitlines()[:80]) if out else "Sin objetos."}
    if accion == "metodos":
        rc, out = ej(["busctl", "--user", "introspect", serv, ruta, "--no-pager"], timeout=8)
        lineas = out.splitlines()
        if iface:
            vistas, dentro = [], False
            for l in lineas:
                if l.startswith("NAME") or not l.strip():
                    continue
                if not l.startswith((".", "+", " ")) and not l.startswith("-"):
                    dentro = False
                if l.split()[0] == iface:
                    dentro = True
                    continue
                if dentro:
                    vistas.append(l)
            lineas = vistas or lineas
        return {"texto": "\n".join(lineas[:120]) if lineas else "Nada ahí (revisa servicio y ruta con objetos)."}
    if accion == "propiedad":
        if not iface or not metodo:
            return {"error": "Para leer una propiedad hacen falta «interfaz» y «metodo» (el nombre de la propiedad)."}
        rc, out = ej(["busctl", "--user", "get-property", serv, ruta, iface, metodo], timeout=8)
        return {"texto": out or "(vacío)"}
    if not metodo or not _METODO.match(metodo):
        return {"error": "Falta «metodo» (por ejemplo reconfigure, o org.kde.KWin.showDesktop)."}
    argumentos = [str(x) for x in (args.get("argumentos") or [])][:10]
    if any(len(x) > 400 or "\x00" in x for x in argumentos):
        return {"error": "Argumento demasiado largo o no válido."}
    nombre_metodo = metodo if "." in metodo or not iface else f"{iface}.{metodo}"
    comando = " ".join([_qdbus(), _q(serv), _q(ruta), _q(nombre_metodo), *[_q(x) for x in argumentos]])
    return {"comando": comando, "motivo": f"hablar con {serv}: {nombre_metodo}", "espera": 0.3,
            "comprobar": lambda: "Si esto debía cambiar algo visible, compruébalo (ver_pantalla o leyendo el estado) antes de decir que está hecho."}


# ----------------------------------------------------------------------------------------------------------------------
#  Despacho
# ----------------------------------------------------------------------------------------------------------------------
PLANIFICADORES = {"ventanas": planificar_ventanas, "procesos": planificar_procesos, "servicios": planificar_servicios,
                  "red": planificar_red, "energia": planificar_energia, "pantalla": planificar_pantalla, "audio": planificar_audio,
                  "kde_dbus": planificar_dbus}


def planificar(nombre, args):
    f = PLANIFICADORES.get(nombre)
    if not f:
        return {"error": f"Herramienta de sistema desconocida: {nombre}."}
    try:
        plan = f(args or {})
        if plan.get("comando"):
            plan["receta"] = _receta(nombre, args or {}, plan)
        return plan
    except Exception as e:                                       # una herramienta rota no debe tumbar el asistente
        return {"error": f"Fallo interno en {nombre}: {e!r}. Prueba con ejecutar_comando."}


# ----------------------------------------------------------------------------------------------------------------------
#  Recetas automáticas: cuando un AJUSTE cambia y se comprueba, queda apuntado sin depender de que la IA se acuerde.
#  Solo se apunta si `verificar_plan` confirma que el estado real es el pedido.
# ----------------------------------------------------------------------------------------------------------------------
_AJUSTES_PANTALLA = {"modo": "resolución y frecuencia de pantalla", "escala": "escala de pantalla", "girar": "giro de pantalla",
                     "posicion": "posición de las pantallas", "principal": "pantalla principal", "brillo": "brillo de pantalla"}


def _llamada(nombre, args, claves=("accion", "objetivo", "salida", "valor")):
    partes = [f"{c}={str(args.get(c)).strip()}" for c in claves if str(args.get(c, "") or "").strip()]
    return f"{nombre}({', '.join(partes)})"


def _receta(nombre, args, plan):
    """{ajuste, palabras, valor_usado, leer, cambiar} si el cambio es de los que se apuntan como receta, o None."""
    accion = str(args.get("accion", "")).strip().lower()
    valor = str(args.get("valor", "") or "").strip()
    objetivo = str(args.get("objetivo", "") or "").strip()
    cmd = plan.get("comando", "")
    if nombre == "audio" and accion in {"volumen", "subir", "bajar", "silenciar", "activar_sonido"}:
        m = re.search(r"set-(?:volume|mute) (\S+)", cmd)
        destino = m.group(1) if m else "@DEFAULT_AUDIO_SINK@"
        nom = {"volumen": "volumen", "subir": "volumen relativo", "bajar": "volumen relativo", "silenciar": "silenciar sonido",
               "activar_sonido": "activar sonido"}[accion] + (f" de {objetivo}" if objetivo else "")
        a = dict(args)
        if accion in {"subir", "bajar"} and not valor:
            a.pop("valor", None)
        return {"ajuste": nom, "palabras": "sonido audio volumen" + (" subir bajar" if accion in {"subir", "bajar"} else ""), "leer": f"wpctl get-volume {destino}",
                "valor_usado": valor if accion in {"volumen", "subir", "bajar"} else "", "cambiar": _llamada("audio", a)}
    if nombre == "energia" and accion == "perfil" and valor:
        return {"ajuste": "perfil de energía", "palabras": "rendimiento ahorro equilibrado energía", "leer": "powerprofilesctl get",
                "valor_usado": valor, "cambiar": _llamada("energia", args)}
    if nombre == "red" and accion in {"wifi_encender", "wifi_apagar", "bluetooth_encender", "bluetooth_apagar"}:
        que = "wifi" if accion.startswith("wifi") else "bluetooth"
        return {"ajuste": ("encender " if accion.endswith("encender") else "apagar ") + que, "palabras": que,
                "leer": "nmcli -t radio wifi" if que == "wifi" else "bluetoothctl show", "valor_usado": "", "cambiar": _llamada("red", {"accion": accion})}
    if nombre == "pantalla" and accion in _AJUSTES_PANTALLA:
        return {"ajuste": _AJUSTES_PANTALLA[accion], "palabras": "pantalla monitor", "leer": "" if accion == "brillo" else "kscreen-doctor -o",
                "valor_usado": valor, "cambiar": _llamada("pantalla", args)}
    return None


def _numero(texto, patron):
    m = re.search(patron, texto or "")
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


def verificar_plan(nombre, args, plan, real):
    """¿El estado leído DESPUÉS coincide con lo pedido? Solo con True se apunta la receta."""
    accion = str(args.get("accion", "")).strip().lower()
    valor = str(args.get("valor", "") or "").strip()
    real = str(real or "")
    try:
        if nombre == "audio":
            vol = _numero(real, r"Volume:\s*([\d.]+)")
            if accion == "silenciar":
                return "MUTED" in real
            if accion == "activar_sonido":
                return vol is not None and "MUTED" not in real
            if vol is None:
                return False
            if accion == "volumen":
                return abs(vol * 100 - min(int(re.sub(r"\D", "", valor) or -999), VOLUMEN_MAXIMO)) <= 1.5
            antes = plan.get("antes_vol")
            if antes is None:
                return False
            return vol > antes + 1e-6 or vol >= 0.995 if accion == "subir" else vol < antes - 1e-6 or vol <= 0.005
        if nombre == "energia" and accion == "perfil":
            return plan.get("esperado") is not None and plan["esperado"] in real.split()
        if nombre == "red":
            if accion.startswith("wifi"):
                return ("enabled" if accion.endswith("encender") else "disabled") in real
            if accion.startswith("bluetooth"):
                return ("Powered: yes" if accion.endswith("encender") else "Powered: no") in real
        if nombre == "pantalla":
            esperado = plan.get("esperado") or {}
            if accion == "brillo":
                n = _numero(valor, r"^\s*(\d{1,3})\s*%?\s*$")
                got = _numero(real, r"(\d+)%")
                return n is not None and got is not None and abs(got - n) <= 3
            salidas, _ = leer_pantallas()
            o = next((x for x in (salidas or []) if x["nombre"] == esperado.get("salida")), None)
            if not o or not esperado:
                return False
            if "modo" in esperado:
                return bool(o["actual"]) and o["actual"]["id"] == esperado["modo"]
            if "escala" in esperado:
                return abs(o["escala"] - esperado["escala"]) < 0.01
            if "giro" in esperado:
                return o["giro"] == esperado["giro"]
            if "pos" in esperado:
                return (o["x"], o["y"]) == tuple(esperado["pos"])
            if esperado.get("principal"):
                return o["prioridad"] == 1
    except (ValueError, TypeError):
        return False
    return False


# ----------------------------------------------------------------------------------------------------------------------
#  Protecciones que se aplican a CUALQUIER comando (también a los de ejecutar_comando)
# ----------------------------------------------------------------------------------------------------------------------
_DBUS_PROGRAMAS = {"qdbus", "qdbus6", "qdbus-qt5", "qdbus-qt6", "gdbus", "dbus-send"}
_PALABRAS_SESION = re.compile(r"(?i)(logout|shutdown|reboot|halt|poweroff|power-?off|suspend|hibernate|terminate|quit|doLogout|"
                              r"requestShutdown|promptLogout|promptShutdown|promptReboot)")
_PALABRAS_SCRIPT = re.compile(r"(?i)(evaluateScript|loadScript|loadDeclarativeScript|unloadScript|replace)")
_SERVICIOS_DELICADOS = re.compile(r"(?i)(login1|systemd1|PackageKit|Accounts|PolicyKit|polkit|udisks|NetworkManager\.Settings|ksmserver|"
                                  r"org\.kde\.Shutdown|LogoutPrompt)")


def _nombre_de_pid(pid):
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def motivo_critico(t, con_sudo=False, pantallas=None):
    """t: lista de palabras ya sin prefijos (sudo, env...). Devuelve un motivo si el comando hay que pedirlo, o None."""
    if not t:
        return None
    base, a = os.path.basename(t[0]), t[1:]
    if base in {"kill", "pkill", "killall", "killall5", "skill", "pidwait"} or base == "xkill":
        if base == "killall5":
            return "mataría todos los procesos"
        objetivos = [x for x in a if not x.startswith("-")]
        if base == "kill":
            resto = list(a)
            if resto and resto[0] in {"-s", "-n", "--signal"}:
                resto = resto[2:]
            elif resto and resto[0].startswith("-") and resto[0] != "--":
                resto = resto[1:]                                   # la señal (-9, -KILL...)
            resto = [x for x in resto if x != "--"]
            for x in resto:
                if not re.fullmatch(r"-?\d+", x):
                    continue
                n = int(x)
                if n <= 1:
                    return "mataría el proceso 1 o a todos los procesos del usuario"
                if n in {os.getpid(), os.getppid()}:
                    return "mataría al propio asistente"
                nombre = _nombre_de_pid(n).lower()
                if nombre in PROCESOS_PROTEGIDOS:
                    return f"mataría «{nombre}», que mantiene viva la sesión o el sistema"
        else:
            if any(x in {"-u", "--user", "-U", "--uid"} or x.startswith(("--user=", "--uid=")) for x in a):
                return "mataría todos los procesos de un usuario"
            for x in objetivos:
                bajo = x.lower().strip("^$")
                if bajo in PROCESOS_PROTEGIDOS or bajo in {".", ".*", "*", ""}:
                    return f"mataría «{x}», que mantiene viva la sesión o el sistema"
        if con_sudo:
            return "mata procesos con permisos de administrador"
        return None
    if base in _DBUS_PROGRAMAS or (base == "busctl" and "call" in a):
        texto = " ".join(a)
        if "--system" in a or (base == "busctl" and "--user" not in a) or "--bus" in a and "system" in texto:
            return "habla con el bus del SISTEMA (puede cambiar servicios, usuarios o energía)"
        if _SERVICIOS_DELICADOS.search(texto):
            return "habla con un servicio que controla sesión, energía, cuentas o paquetes"
        if _PALABRAS_SESION.search(texto):
            return "apaga, reinicia o cierra la sesión (perderías lo que tengas abierto)"
        if _PALABRAS_SCRIPT.search(texto):
            return "ejecuta un script dentro del escritorio (KWin o Plasma), que puede hacer casi cualquier cosa"
        return None
    if base == "kscreen-doctor":
        quita = [re.match(r"output\.([^.]+)\.disable$", x) for x in a]
        quita = {m.group(1) for m in quita if m}
        if quita:
            pantallas = pantallas if pantallas is not None else (leer_pantallas()[0] or [])
            quedan = [o for o in pantallas if o["activa"] and o["nombre"] not in quita]
            encendidas = {m.group(1) for x in a for m in [re.match(r"output\.([^.]+)\.enable$", x)] if m}
            if pantallas and not quedan and not encendidas:
                return "dejaría el equipo sin ninguna pantalla encendida"
    return None
