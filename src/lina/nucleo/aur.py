# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A15 (d) y (e): antes de pedir el «sí» para instalar algo del AUR, qué más trae de él, y cómo lanzar paru o yay sin que se queden en una pregunta.

Se mira con la API pública del AUR (la misma que usa paru), solo con los nombres de los paquetes, y con `pacman` para saber qué dependencias están en
los repositorios. Caso real (2026-11-20): caffeine-ng trae python-ewmh del AUR, y paru preguntaba entre varios proveedores y si editar."""
import re
import shlex
import subprocess

from lina.nucleo.idioma import T

RPC = "https://aur.archlinux.org/rpc/v5"
TIMEOUT = 8
MAX_PAQUETES = 30
AYUDANTES = ("paru", "yay")


def _http():
    import requests
    return requests


def _pide(ruta, params, http):
    r = (http or _http()).get(f"{RPC}/{ruta}", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("results") or []


def _en_repositorios(dep, ejecutar=subprocess.run):
    """¿La da algún paquete de los repositorios oficiales (también por «provides»)? `pacman -Sp` lo resuelve sin instalar nada."""
    try:
        r = ejecutar(["pacman", "-Sp", "--noconfirm", "--print-format", "%n", "--", dep], capture_output=True, text=True, timeout=15,
                     stdin=subprocess.DEVNULL, env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"})
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def _limpio(dep):
    """«python-click>=8» → «python-click»."""
    return re.split(r"[<>=:]", dep, maxsplit=1)[0].strip()


def objetivos(comando):
    """(ayudante, [paquetes]) si la orden instala con paru o yay; si no, None."""
    try:
        palabras = shlex.split(str(comando))
    except ValueError:
        return None
    while palabras and palabras[0] in ("sudo", "env"):
        palabras.pop(0)
    if not palabras or palabras[0].rsplit("/", 1)[-1] not in AYUDANTES:
        return None
    if not any(re.fullmatch(r"-S[a-z]*", p) and not set(p[2:]) & set("sicgl") for p in palabras[1:]):
        return None
    return palabras[0].rsplit("/", 1)[-1], [p for p in palabras[1:] if not p.startswith("-")]


def que_trae(paquetes, http=None, en_repos=_en_repositorios):
    """{"aur": [lo que viene también del AUR], "elegidos": {dependencia: (paquete, cuántos la dan)}, "error": texto o ""}. Sigue las dependencias
    (también las de compilar) de lo que viene del AUR, hasta MAX_PAQUETES."""
    vistos, pendientes, aur, elegidos = set(paquetes), list(paquetes), [], {}
    try:
        while pendientes and len(vistos) <= MAX_PAQUETES:
            lote, pendientes = pendientes[:20], pendientes[20:]
            for info in _pide("info", {"arg[]": lote}, http):
                for dep in [_limpio(d) for d in (info.get("Depends") or []) + (info.get("MakeDepends") or [])]:
                    if not dep or dep in vistos:
                        continue
                    vistos.add(dep)
                    if en_repos(dep):
                        continue
                    exacto = _pide("info", {"arg[]": [dep]}, http)
                    if exacto:
                        nombre = exacto[0]["Name"]
                    else:
                        dan = _pide(f"search/{dep}", {"by": "provides"}, http)
                        if not dan:
                            continue                                  # ni en los repositorios ni en el AUR: lo dirá paru al fallar
                        nombre = max(dan, key=lambda p: (p.get("NumVotes") or 0, p.get("Popularity") or 0))["Name"]
                        if len(dan) > 1:
                            elegidos[dep] = (nombre, len(dan))
                    if nombre not in aur and nombre not in paquetes:
                        aur.append(nombre)
                        pendientes.append(nombre)
    except Exception as e:                                            # sin red, el AUR caído o una respuesta rara: se dice, no se calla
        return {"aur": aur, "elegidos": elegidos, "error": f"{type(e).__name__}"}
    return {"aur": aur, "elegidos": elegidos, "error": ""}


def frase(trae):
    """Lo que la confirmación dice, escrito por el código."""
    partes = []
    if trae["aur"]:
        partes.append(T("Trae también del AUR: {lista}.", lista=", ".join(trae["aur"])))
    for dep, (nombre, n) in trae["elegidos"].items():
        partes.append(T("Para {dep} hay {n} paquetes que lo dan; usaré {nombre}, el más votado.", dep=dep, n=n, nombre=nombre))
    if trae["error"]:
        partes.append(T("No he podido mirar en el AUR qué más trae."))
    return " ".join(partes)


def sin_preguntas(comando, trae=None):
    """(e) La orden de paru o yay tal que en segundo plano no se quede en ninguna pregunta: sin revisión ni edición, y con el proveedor ya elegido
    por el código (se añade a los paquetes, para que el ayudante no elija otro)."""
    o = objetivos(comando)
    if not o:
        return comando
    ayudante, _ = o
    palabras = shlex.split(str(comando))
    sueltas = ["--needed", "--noconfirm"] + (["--skipreview"] if ayudante == "paru" else [])
    pares = [] if ayudante == "paru" else [("--answerdiff", "None"), ("--answerclean", "None"), ("--answeredit", "None")]
    nuevas = [x for x in sueltas if x not in palabras] + [y for a, b in pares if a not in palabras for y in (a, b)]
    i = next(k for k, p in enumerate(palabras) if re.fullmatch(r"-S[a-z]*", p))
    proveedores = [nombre for nombre, _ in (trae or {}).get("elegidos", {}).values() if nombre not in palabras]
    return shlex.join(palabras[:i + 1] + nuevas + palabras[i + 1:] + proveedores)
