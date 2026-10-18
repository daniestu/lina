#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Ayudante de accesibilidad (AT-SPI) del control de programas. Se ejecuta APARTE (con el python del sistema, que trae PyGObject) para que un
programa que no responda no pueda colgar al asistente: quien lo llama pone un tiempo máximo.

    python3 interfaz_atspi.py apps
    python3 interfaz_atspi.py elementos [--ventana TEXTO] [--filtro TEXTO] [--max N]

Escribe JSON en la salida. Solo LEE: no pulsa nada (eso llega en la fase 2). Los campos de contraseña nunca se leen.
"""
import argparse
import subprocess
import json
import os
import sys
import threading
import time
import unicodedata
import warnings

warnings.filterwarnings("ignore")                                           # los avisos de «deprecated» de PyGObject no importan

try:
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
except Exception as e:                                                      # sin PyGObject / at-spi2-core
    print(json.dumps({"error": f"No puedo usar la accesibilidad (AT-SPI): {e}"}))
    sys.exit(0)

# roles que merece la pena enseñar (nombre interno de AT-SPI → lo que se dice)
ROLES = {
    "push-button": "botón", "button": "botón", "switch": "interruptor", "toggle-button": "interruptor", "check-box": "casilla", "radio-button": "opción",
    "menu-item": "elemento de menú", "check-menu-item": "elemento de menú", "radio-menu-item": "elemento de menú", "menu": "menú",
    "combo-box": "desplegable", "text": "campo de texto", "entry": "campo de texto", "password-text": "campo de contraseña",
    "link": "enlace", "page-tab": "pestaña", "list-item": "elemento de lista", "slider": "deslizador", "spin-button": "numérico",
    "tree-item": "elemento de árbol", "table-cell": "celda", "tool-bar": None, "label": "texto", "radio-menu": None,
}
SOLO_CON_NOMBRE = {"label", "list-item", "table-cell", "tree-item", "button", "push-button", "check-box"}          # los muy abundantes: solo si tienen texto
VENTANAS = {"frame", "dialog", "window", "alert", "file-chooser", "applet"}
MAX_NODOS = 6000
MAX_PROFUNDIDAD = 40


def plano(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# ---- capa fina sobre Atspi (así se puede probar sin sesión gráfica) ----
def hijos(acc):
    try:
        return [acc.get_child_at_index(i) for i in range(acc.get_child_count())]
    except Exception:
        return []


def nombre(acc):
    try:
        return acc.get_name() or ""
    except Exception:
        return ""


def descripcion(acc):
    try:
        return acc.get_description() or ""
    except Exception:
        return ""


def rol(acc):
    try:
        return acc.get_role().value_nick
    except Exception:
        return ""


def estados(acc):
    try:
        s = acc.get_state_set()
    except Exception:
        return set()
    cuales = {"ENABLED": "activo", "SHOWING": "visible", "FOCUSED": "con foco", "CHECKED": "marcado", "SELECTED": "seleccionado",
              "EXPANDED": "desplegado", "EDITABLE": "editable", "ACTIVE": "activa", "PRESSED": "pulsado", "SENSITIVE": "sensible",
              "VISIBLE": "visible"}
    return {texto for clave, texto in cuales.items() if hasattr(Atspi.StateType, clave) and s.contains(getattr(Atspi.StateType, clave))}


def acciones(acc):
    try:
        ai = acc.get_action_iface()
        return [ai.get_action_name(i) for i in range(ai.get_n_actions())] if ai else []
    except Exception:
        return []


def caja(acc):
    try:
        c = acc.get_component_iface()
        e = c.get_extents(Atspi.CoordType.SCREEN) if c else None
        return (e.x, e.y, e.width, e.height) if e else None
    except Exception:
        return None


def valor_texto(acc):
    try:
        t = acc.get_text_iface()
        if t:
            n = t.get_character_count()
            return t.get_text(0, min(n, 80))
    except Exception:
        pass
    return ""


def escritorio():
    return Atspi.get_desktop(0)


# ---- lógica ----
def ventanas_de(app):
    return [(j, f) for j, f in enumerate(hijos(app)) if rol(f) in VENTANAS or nombre(f)]


def listar_apps():
    res = []
    d = escritorio()
    for i, app in enumerate(hijos(d)):
        fr = [{"indice": j, "nombre": nombre(f), "rol": rol(f), "activa": "activa" in estados(f)} for j, f in ventanas_de(app)]
        res.append({"indice": i, "app": nombre(app), "ventanas": fr})
    return res


def elegir_ventana(texto):
    """(i, j, app, frame) de la ventana que se parece a texto; sin texto, la que tiene el foco. O (None, mensaje)."""
    d = escritorio()
    quiero = plano(texto)
    candidatas = []
    for i, app in enumerate(hijos(d)):
        for j, f in ventanas_de(app):
            nf, na = plano(nombre(f)), plano(nombre(app))
            activa = "activa" in estados(f)
            if quiero:
                if quiero in nf or quiero in na:
                    candidatas.append((i, j, app, f, activa))
            elif activa:
                candidatas.append((i, j, app, f, activa))
    if not candidatas:
        libres = [f"{nombre(a)}: «{nombre(f)}»" for a in hijos(d) for _, f in ventanas_de(a) if nombre(f)][:15]
        quien = f"«{texto}»" if texto else "con el foco"
        return None, (f"No veo por accesibilidad ninguna ventana {quien}. Las que sí publican sus controles: " + ("; ".join(libres) or "ninguna")
                      + ". Los programas abiertos antes de activar la accesibilidad, y los de Electron/Chromium (Discord, VS Code, Steam…), pueden no aparecer: "
                        "para esos hay que usar la captura de pantalla.")
    candidatas.sort(key=lambda c: not c[4])
    return candidatas[0], ""


def n_crudo(acc):
    return nombre(acc).strip()[:60]


def recorrer(frame, prefijo, filtro, maximo, crudo=False):
    """crudo=True: TODOS los nodos (rol, nombre, estados) sin filtrar por rol ni visibilidad: para ver qué publica de verdad un programa."""
    elementos, nodos, recortado = [], 0, False
    quiero = plano(filtro)
    pila = [(frame, prefijo, 0)]
    while pila:
        acc, ruta, prof = pila.pop()
        nodos += 1
        if nodos > MAX_NODOS or prof > MAX_PROFUNDIDAD:
            recortado = True
            continue
        r = rol(acc)
        st = estados(acc)
        if crudo:
            elementos.append({"id": ruta, "rol": r, "tipo": r, "nombre": n_crudo(acc), "valor": "", "estado": sorted(st), "acciones": acciones(acc)[:3], "caja": caja(acc)})
            if len(elementos) >= maximo:
                recortado = True
                break
            for k, h in reversed(list(enumerate(hijos(acc)))):
                pila.append((h, f"{ruta}.{k}", prof + 1))
            continue
        if acc is not frame and "visible" not in st:
            continue                                              # lo que no se ve (pestañas ocultas, menús cerrados) no se enseña
        n = nombre(acc).strip() or descripcion(acc).strip()          # un botón de icono suele tener solo descripción («Atrás»)
        if acc is not frame and r in ROLES and ROLES[r]:
            if not (r in SOLO_CON_NOMBRE and not n):
                valor = ""
                if r in ("text", "entry"):
                    valor = valor_texto(acc)
                elif r == "password-text":
                    valor = "(oculto)"
                if not quiero or quiero in plano(n) or quiero in plano(valor) or quiero in plano(ROLES[r]):
                    elementos.append({"id": ruta, "rol": r, "tipo": ROLES[r], "nombre": n[:90], "valor": valor[:80], "estado": sorted(st),
                                      "acciones": acciones(acc)[:3], "caja": caja(acc)})
                    if len(elementos) >= maximo:
                        recortado = True
                        break
        for k, h in reversed(list(enumerate(hijos(acc)))):
            pila.append((h, f"{ruta}.{k}", prof + 1))
    return elementos, recortado



# ---- actuar (fase 2) ----
DENEGADAS = ("polkit", "kwallet", "kdewallet", "keepass", "bitwarden", "1password", "autentic", "contrasen", "password", "gnome-keyring", "ksshaskpass", "sudo")
PREFERIDAS = ["press", "click", "toggle", "activate", "select", "open", "check", "uncheck", "jump", "expand or contract", "setfocus"]


def denegada(app_nombre, ventana_nombre):
    """Ventanas de contraseñas, autenticación o carteras: nunca se tocan (las hace el usuario)."""
    t = plano(f"{app_nombre} {ventana_nombre}")
    return next((d for d in DENEGADAS if d in t), "")


def por_ruta(ruta):
    nodo = escritorio()
    try:
        for p in [int(x) for x in str(ruta).split(".")]:
            nodo = nodo.get_child_at_index(p)
            if nodo is None:
                return None
    except Exception:
        return None
    return nodo


def coincide(acc, nombre_esperado, rol_esperado=""):
    n = plano(nombre(acc).strip() or descripcion(acc).strip())
    if nombre_esperado and plano(nombre_esperado) != n:
        return False
    return not rol_esperado or rol_esperado in (rol(acc), ROLES.get(rol(acc)))


def buscar_en(frame, nombre_esperado, rol_esperado=""):
    res, pila = [], [frame]
    n = 0
    while pila and n < MAX_NODOS:
        acc = pila.pop()
        n += 1
        if acc is not frame and "visible" in estados(acc) and rol(acc) in ROLES and coincide(acc, nombre_esperado, rol_esperado):
            res.append(acc)
        pila.extend(hijos(acc))
    return res


def resolver(ruta, nombre_esperado, rol_esperado=""):
    """(acc, i, j, app, frame, error). Si la ruta ya no apunta a lo esperado (la ventana cambió), busca el control por nombre en esa ventana."""
    partes = str(ruta).split(".")
    acc = por_ruta(ruta)
    app = por_ruta(partes[0]) if partes else None
    frame = por_ruta(".".join(partes[:2])) if len(partes) >= 2 else None
    if acc is not None and coincide(acc, nombre_esperado, rol_esperado):
        return acc, app, frame, ""
    if frame is None:
        return None, app, frame, "Esa ventana ya no existe: vuelve a listar los controles."
    cand = buscar_en(frame, nombre_esperado, rol_esperado)
    if len(cand) == 1:
        return cand[0], app, frame, ""
    if not cand:
        return None, app, frame, f"El control «{nombre_esperado}» ya no está donde estaba: vuelve a listar los controles de la ventana."
    return None, app, frame, f"Hay {len(cand)} controles llamados «{nombre_esperado}»: usa el id exacto del listado."


def destino(a):
    """(acc, app, frame, error) del control al que se refiere la orden: por su id, o (sin id) buscándolo por nombre en la ventana indicada o con foco."""
    if a.id:
        return resolver(a.id, a.nombre, a.rol)
    if not a.nombre:
        return None, None, None, "Hace falta el id del control o su nombre (con la ventana)."
    sel, msg = elegir_ventana(a.ventana)
    if not sel:
        return None, None, None, msg
    _, _, app, frame, _ = sel
    cand = buscar_en(frame, a.nombre, a.rol)
    if len(cand) == 1:
        return cand[0], app, frame, ""
    if not cand:
        return None, app, frame, f"No veo ningún control «{a.nombre}» en la ventana «{nombre(frame)}»: lista los controles para ver cómo se llama."
    return None, app, frame, f"Hay {len(cand)} controles llamados «{a.nombre}» en «{nombre(frame)}»: usa el id exacto del listado."


TEXTOS = {"label", "static", "heading", "paragraph", "text"}


def accion_contexto(a):
    """Qué ventana es y qué dice (títulos y textos de la ventana), SIN tocar nada: sirve para valorar el riesgo antes de pulsar."""
    acc, app, frame, err = destino(a)
    if err:
        return {"error": err}
    textos, pila, n = [], [frame], 0
    while pila and n < 1500 and len(textos) < 30:
        x = pila.pop(0)
        n += 1
        if x is not frame and "visible" in estados(x) and rol(x) in TEXTOS and "editable" not in estados(x):
            t = nombre(x).strip() or valor_texto(x).strip()
            if t and t not in textos:
                textos.append(t[:100])
        pila.extend(hijos(x))
    return {"app": nombre(app), "ventana": nombre(frame), "rol": ROLES.get(rol(acc)) or rol(acc), "control": nombre(acc) or descripcion(acc), "textos": textos}


def instantanea():
    """Qué se ve ahora: ventanas abiertas y controles de la ventana con foco (para decir qué cambió tras actuar)."""
    ventanas, controles = set(), set()
    d = escritorio()
    for app in hijos(d):
        for _, f in ventanas_de(app):
            if nombre(f):
                ventanas.add(f"{nombre(app)}: {nombre(f)}")
                if "activa" in estados(f):
                    els, _ = recorrer(f, "x", "", 300)
                    controles |= {f"{e['tipo']} «{e['nombre']}»" + (" (marcado)" if "marcado" in e["estado"] else "") for e in els if e["nombre"]}
    return ventanas, controles


def diferencias(antes, despues):
    va, ca = antes
    vd, cd = despues
    return {"ventanas_nuevas": sorted(vd - va)[:6], "ventanas_cerradas": sorted(va - vd)[:6],
            "controles_nuevos": sorted(cd - ca)[:12], "controles_desaparecen": sorted(ca - cd)[:12]}


def hacer_accion(acc):
    ai = acc.get_action_iface() if hasattr(acc, "get_action_iface") else None
    nombres = []
    if ai:
        for i in range(ai.get_n_actions()):
            nombres.append(ai.get_action_name(i))
    for pref in PREFERIDAS:
        for i, n in enumerate(nombres):
            if plano(n).replace(" ", "") == pref.replace(" ", ""):
                if pref == "setfocus" and len(nombres) > 1:
                    continue
                return ai, i, n
    return ai, None, ""


def accion_pulsar(a):
    acc, app, frame, err = destino(a)
    if err:
        return {"error": err}
    if denegada(nombre(app), nombre(frame)):
        return {"error": "Es una ventana de contraseñas o autenticación: no la toco, tiene que hacerlo el usuario."}
    if rol(acc) == "password-text":
        return {"error": "Es un campo de contraseña: no lo toco."}
    if "activo" not in estados(acc) and "sensible" not in estados(acc):
        return {"error": f"«{nombre(acc)}» está desactivado: no se puede pulsar ahora."}
    ai, idx, nom = hacer_accion(acc)
    if idx is None:
        return {"error": f"«{nombre(acc)}» no tiene una acción de pulsar por accesibilidad (acciones: {acciones(acc) or 'ninguna'}). Prueba con la tecla o con la captura de pantalla."}
    antes = instantanea()
    hecho = {"ok": False}

    def lanzar():
        try:
            hecho["ok"] = bool(ai.do_action(idx))
        except Exception as e:
            hecho["error"] = repr(e)
    t = threading.Thread(target=lanzar, daemon=True)
    t.start()
    t.join(3)
    bloqueado = t.is_alive()                              # un diálogo modal puede dejar la llamada abierta: se sigue igualmente
    time.sleep(0.8)
    if hecho.get("error"):
        return {"error": f"No se pudo pulsar: {hecho['error']}"}
    return {"ok": True, "accion": nom, "elemento": nombre(acc) or descripcion(acc), "rol": ROLES.get(rol(acc)) or rol(acc), "ventana": nombre(frame), "app": nombre(app),
            "modal": bloqueado, "cambios": diferencias(antes, instantanea())}


def accion_escribir(a):
    acc, app, frame, err = destino(a)
    if err:
        return {"error": err}
    if denegada(nombre(app), nombre(frame)) or rol(acc) == "password-text":
        return {"error": "Es un campo de contraseña o una ventana de autenticación: no escribo ahí, tiene que hacerlo el usuario."}
    ed = acc.get_editable_text_iface() if hasattr(acc, "get_editable_text_iface") else None
    if not ed:
        return {"error": f"«{nombre(acc)}» no es un campo editable por accesibilidad."}
    antes = valor_texto(acc)
    try:
        if a.modo == "anadir":
            t = acc.get_text_iface()
            pos = t.get_character_count() if t else len(antes)
            ok = ed.insert_text(pos, a.texto, len(a.texto))
        else:
            ok = ed.set_text_contents(a.texto)
    except Exception as e:
        return {"error": f"No se pudo escribir: {e!r}"}
    time.sleep(0.5)
    despues = valor_texto(acc)
    metodo = "accesibilidad"
    esperado = a.texto if a.modo != "anadir" else antes + a.texto
    if a.texto and despues.strip() != esperado[:80].strip():
        # Algunos campos (barras de ruta, buscadores con autocompletado) reaccionan al primer cambio y se quedan con otra cosa: se reintenta tecleando de verdad
        if _teclear(acc, a.texto, a.modo == "anadir"):
            metodo = "teclado"
            time.sleep(0.6)
            despues = valor_texto(acc)
    return {"ok": bool(ok) and despues.strip() == esperado[:80].strip(), "elemento": nombre(acc) or descripcion(acc), "ventana": nombre(frame),
            "antes": antes[:80], "despues": despues[:80], "metodo": metodo, "rol": ROLES.get(rol(acc)) or rol(acc), "app": nombre(app)}


def _teclear(acc, texto, anadir):
    """Pone el foco en el campo y teclea con ydotool (solo texto ASCII: el teclado virtual depende de la distribución)."""
    if not texto.isascii() or len(texto) > 200:
        return False
    try:
        c = acc.get_component_iface()
        if c:
            c.grab_focus()
        time.sleep(0.2)
        env = dict(os.environ)
        for sock in (env.get("YDOTOOL_SOCKET", ""), f"{os.environ.get('XDG_RUNTIME_DIR', '')}/.ydotool_socket", "/tmp/.ydotool_socket"):
            if sock and os.path.exists(sock):
                env["YDOTOOL_SOCKET"] = sock
                break
        if not anadir:
            subprocess.run(["ydotool", "key", "29:1", "30:1", "30:0", "29:0"], env=env, timeout=5, capture_output=True)   # ctrl+a
            time.sleep(0.1)
        r = subprocess.run(["ydotool", "type", "--key-delay", "25", "--", texto], env=env, timeout=15, capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("orden", choices=["apps", "elementos", "pulsar", "escribir", "contexto"])
    p.add_argument("--ventana", default="")
    p.add_argument("--filtro", default="")
    p.add_argument("--max", type=int, default=120)
    p.add_argument("--id", default="")
    p.add_argument("--nombre", default="")
    p.add_argument("--rol", default="")
    p.add_argument("--texto", default="")
    p.add_argument("--modo", default="reemplazar")
    p.add_argument("--crudo", action="store_true", help="vuelca todos los nodos tal cual (para diagnóstico)")
    a = p.parse_args()
    try:
        if a.orden == "apps":
            print(json.dumps({"apps": listar_apps()}, ensure_ascii=False))
            return
        if a.orden == "contexto":
            print(json.dumps(accion_contexto(a), ensure_ascii=False))
            return
        if a.orden in ("pulsar", "escribir"):
            print(json.dumps(accion_pulsar(a) if a.orden == "pulsar" else accion_escribir(a), ensure_ascii=False))
            sys.stdout.flush()
            os._exit(0)                                   # por si una acción dejó un hilo bloqueado en un diálogo modal
        elegida, msg = elegir_ventana(a.ventana)
        if not elegida:
            print(json.dumps({"error": msg}, ensure_ascii=False))
            return
        i, j, app, frame, _ = elegida
        els, recortado = recorrer(frame, f"{i}.{j}", a.filtro, max(1, min(a.max, 400 if not a.crudo else 1500)), a.crudo)
        print(json.dumps({"app": nombre(app), "ventana": nombre(frame), "elementos": els, "recortado": recortado}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": f"Fallo al leer la accesibilidad: {e!r}"}))


if __name__ == "__main__":
    main()
