# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Papelera de Lina: los borrados se convierten en un movimiento a la papelera (recuperable) en vez de borrar de verdad."""
import os
import re
import shutil
from pathlib import Path
from urllib.parse import unquote

from lina.nucleo import comandos
from lina.nucleo.clasificador import (RUTA_DATOS, _HOME, _es_objetivo_peligroso, _normalizar_ruta, _quitar_prefijos, _segmentos,
                                      _tokens)
from lina.nucleo.registro import anotar


# Borrar archivos tuyos = moverlos a la papelera (se pueden recuperar). Lo hace el código, no la IA:
#  - 'rm', 'rmdir' o 'unlink' sencillos sobre tu carpeta personal o el disco de datos protegido se convierten en 'gio trash'.
#  - Si el borrado es complicado (varios comandos juntos, find -delete, xargs...) y toca tus archivos, se rechaza
#    para que lo pida de forma sencilla, porque así no se puede garantizar que vaya a la papelera.
#  - Si lo pides «definitivamente», «para siempre» o «sin papelera» (ver comandos.txt), no se transforma.
_BORRADORES = {"rm", "rmdir", "unlink"}
_FLAGS_RM_CORTOS = set("rRfvdiIp")
_FLAGS_RM_LARGOS = {"--recursive", "--force", "--verbose", "--dir", "--preserve-root", "--one-file-system", "--parents",
                    "--interactive=never", "--interactive=once", "--interactive=always", "--ignore-fail-on-non-empty"}
_USO_SENCILLO = ("Borra con un comando 'rm' sencillo por cada cosa (opciones antes de las rutas; sin find -delete, "
                 "tuberías, xargs ni varios comandos juntos): así los archivos van a la papelera y se pueden recuperar.")


def _se_va_a_la_papelera(ruta):
    """¿Un archivo en esta ruta se manda a la papelera al borrarlo? (carpeta personal y disco de datos protegido; no las cachés)"""
    ruta = _normalizar_ruta(ruta)
    if not ruta.startswith("/"):
        ruta = _normalizar_ruta(_HOME + "/" + ruta)      # los comandos se ejecutan desde la carpeta personal
    if ".." in ruta.split("/") or _es_objetivo_peligroso(ruta):
        return False
    for raiz in (_HOME, RUTA_DATOS):
        if ruta.startswith(raiz + "/"):
            resto = ruta[len(raiz) + 1:]
            if raiz == _HOME and (resto == ".cache" or resto.startswith(".cache/") or resto.startswith(".local/share/Trash")):
                return False
            return not (resto.startswith(".Trash-") or "/.Trash-" in ruta)
    return False


def _borrados_en(comando, _prof=0):
    """Busca borrados en cualquier parte del comando: [(programa, argumentos, cómo)]."""
    encontrados = []
    for seg in _segmentos(comando):
        t = _tokens(seg)
        t = _quitar_prefijos(t) if t else None
        if not t:
            continue
        base, args = os.path.basename(t[0]), t[1:]
        if base in _BORRADORES:
            encontrados.append((base, args, "directo"))
        elif base in {"bash", "sh", "zsh", "fish", "dash"} and "-c" in args and _prof < 3 and args.index("-c") + 1 < len(args):
            for b, a, _ in _borrados_en(args[args.index("-c") + 1], _prof + 1):
                encontrados.append((b, a, "anidado"))
        elif base == "find" and ("-delete" in args or any(x in _BORRADORES for x in args)):
            encontrados.append(("find", args, "find"))
        elif base == "xargs":
            i = next((k for k, a in enumerate(args) if not a.startswith("-")), None)
            if i is not None and os.path.basename(args[i]) in _BORRADORES:
                encontrados.append((os.path.basename(args[i]), args[i + 1:], "xargs"))
    return encontrados


def _es_zona_tuya(ruta):
    """¿Esta ruta es tuya o contiene cosas tuyas? (tus carpetas, tu carpeta personal entera, el disco de datos protegido, o '/')"""
    r = _normalizar_ruta(ruta)
    if not r.startswith("/"):
        r = _normalizar_ruta(_HOME + "/" + r)
    return _se_va_a_la_papelera(r) or _es_objetivo_peligroso(r) or r in {_HOME, RUTA_DATOS}


def _toca_tus_archivos(base, args, via):
    if via == "xargs":
        return True                                      # no se sabe qué rutas llegarán
    if base == "find":
        rutas = []
        for a in args:
            if a.startswith("-") or a in {"(", "!"}:
                break
            rutas.append(a)
        return not rutas or any(_es_zona_tuya(r) for r in rutas)
    objetivos = [a for a in args if not a.startswith("-")]
    return not objetivos or any(_es_zona_tuya(o) for o in objetivos)


def tratar_borrado(comando):
    """Devuelve (comando, None) sin cambios, (comando_nuevo, None) si pasa a la papelera, o (comando, motivo) si se rechaza."""
    borrados = _borrados_en(comando)
    if not borrados:
        return comando, None
    sencillo = (len(_segmentos(comando)) == 1 and len(borrados) == 1 and borrados[0][2] == "directo"
                and not re.search(r"\$\(|`|[<>]|(?<![&])&(?![&])", comando))
    if not sencillo:
        if any(_toca_tus_archivos(*b) for b in borrados):
            return comando, _USO_SENCILLO
        return comando, None                             # solo toca cosas de fuera (/tmp, cachés...): sigue como estaba
    base, args, _ = borrados[0]
    objetivos, fin_opciones = [], False
    for a in args:
        if not fin_opciones and a == "--":
            fin_opciones = True
        elif not fin_opciones and a.startswith("-") and len(a) > 1:
            if objetivos:
                return comando, "Pon las opciones de rm antes de las rutas. " + _USO_SENCILLO
            ok = a in _FLAGS_RM_LARGOS if a.startswith("--") else set(a[1:]) <= _FLAGS_RM_CORTOS
            if not ok:
                return comando, f"No reconozco la opción «{a}». " + _USO_SENCILLO
        else:
            objetivos.append(a)
    if not objetivos:
        return comando, None
    van = [_se_va_a_la_papelera(o) for o in objetivos]
    if not any(van):
        return comando, None
    if not all(van):
        return comando, "Mezcla archivos tuyos con otros de fuera (/tmp, cachés...). Bórralos con comandos distintos."
    nuevo = re.sub(r"^(\s*)(?:sudo\s+(?:-n\s+)?)?(?:\S*/)?(?:rm|rmdir|unlink)\b(?:\s+-\S*)*\s*", r"\1gio trash -- ", comando, count=1)
    if nuevo == comando:
        return comando, "No he podido pasarlo a la papelera. " + _USO_SENCILLO
    return nuevo, None


def _dirs_papelera():
    """[(carpeta de la papelera, carpeta base para rutas relativas o None)]: la de tu carpeta personal y la del disco de datos protegido."""
    datos_home = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local/share"))
    top = Path(RUTA_DATOS)
    return [(datos_home / "Trash", None), (top / f".Trash-{os.getuid()}", top)]


def contenido_papelera():
    """Lo que hay en la papelera, lo más reciente primero."""
    elementos = []
    for carpeta, base in _dirs_papelera():
        info_dir, files_dir = carpeta / "info", carpeta / "files"
        if not info_dir.is_dir():
            continue
        for info in info_dir.glob("*.trashinfo"):
            origen, fecha = None, ""
            try:
                for linea in info.read_text(encoding="utf-8", errors="replace").splitlines():
                    if linea.startswith("Path="):
                        origen = Path(unquote(linea[5:].strip()))
                    elif linea.startswith("DeletionDate="):
                        fecha = linea[13:].strip()
            except OSError:
                continue
            if origen is None:
                continue
            if not origen.is_absolute() and base:
                origen = base / origen
            almacenado = files_dir / info.name[:-len(".trashinfo")]
            if almacenado.exists() or almacenado.is_symlink():
                elementos.append({"nombre": origen.name, "origen": origen, "fecha": fecha, "almacenado": almacenado, "info": info})
    return sorted(elementos, key=lambda e: e["fecha"], reverse=True)


def ver_papelera():
    elementos = contenido_papelera()
    anotar(f"[papelera] consulta: {len(elementos)} elementos")
    if not elementos:
        return "La papelera está vacía."
    lineas = [f"{i}. {e['nombre']}  (estaba en {e['origen'].parent}; borrado el {e['fecha'].replace('T', ' a las ')})"
              for i, e in enumerate(elementos[:25], 1)]
    resto = f"\n(y {len(elementos) - 25} más antiguos)" if len(elementos) > 25 else ""
    return f"La papelera tiene {len(elementos)} elementos, lo más reciente primero:\n" + "\n".join(lineas) + resto


def restaurar_de_papelera(nombre):
    """Devuelve un archivo de la papelera a su sitio de origen (si ya hay algo ahí, lo guarda con otro nombre)."""
    buscado = comandos.normalizar(nombre or "")
    if not buscado:
        return "Falta el nombre de lo que quieres recuperar."
    candidatos = [e for e in contenido_papelera() if buscado in comandos.normalizar(e["nombre"])]
    if not candidatos:
        return "No hay nada con ese nombre en la papelera. Usa ver_papelera para ver lo que hay."
    nombres = sorted({e["nombre"] for e in candidatos})
    if len(nombres) > 1:
        return "Hay varios elementos que encajan: " + "; ".join(nombres[:8]) + ". Pregunta al usuario cuál quiere."
    e = candidatos[0]                                    # si hay varias versiones del mismo nombre, la más reciente
    destino = e["origen"]
    if not _se_va_a_la_papelera(str(destino)):
        return "Ese elemento venía de una zona que no restauro por voz. Recupéralo desde Dolphin (Papelera → Restaurar)."
    destino.parent.mkdir(parents=True, exist_ok=True)
    n = 1
    while destino.exists() or destino.is_symlink():
        destino = e["origen"].with_name(f"{e['origen'].stem} (restaurado{'' if n == 1 else ' ' + str(n)}){e['origen'].suffix}")
        n += 1
    try:
        shutil.move(str(e["almacenado"]), str(destino))
        e["info"].unlink()
    except OSError as err:
        return f"No he podido restaurarlo: {err}"
    anotar(f"[papelera] restaurado {destino}")
    return f"Restaurado en {destino}."


def vaciar_papelera():
    """Borra PARA SIEMPRE todo lo que hay en la papelera (la de tu carpeta personal y la del disco de datos protegido)."""
    total = 0
    for carpeta, _ in _dirs_papelera():
        for sub in ("files", "info"):
            d = carpeta / sub
            if not d.is_dir():
                continue
            for elemento in d.iterdir():
                try:
                    if elemento.is_dir() and not elemento.is_symlink():
                        shutil.rmtree(elemento)
                    else:
                        elemento.unlink()
                    if sub == "files":
                        total += 1
                except OSError:
                    pass
        try:
            (carpeta / "directorysizes").unlink()
        except OSError:
            pass
    anotar(f"[papelera] vaciada: {total} elementos borrados para siempre")
    return f"Papelera vaciada: {total} elementos borrados para siempre."

