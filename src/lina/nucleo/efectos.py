# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A16: qué HACE una orden, sin mirar para qué es. Sirve para dos decisiones del ejecutor:

  · Sin «sí» lo reversible e inocuo: una orden que solo es crítica por escribir en una ruta de las que arrancan solas (persistencia) de tu carpeta
    va sin confirmar si solo escribe archivos de claves y valores sin ninguna clave que lance un programa (las que empiezan por Exec o TryExec). Lo
    que no sea de claves y valores, o no se pueda leer antes de ejecutarlo, se confirma como siempre.
  · Un «sí» solo cubre lo que se describió: el efecto de cada orden (borrar, escribir, instalar, servicios, ejecutar) para comparar con lo confirmado.

Ninguna acción concreta tiene aquí su caso: solo formatos (claves y valores, heredoc, redirecciones) y programas por lo que hacen. Caso real que lo
motivó (2026-11-21): quitar un programa del inicio automático pidió un «sí» para borrar archivos que no existían y luego escribió otra cosa con él."""
import glob
import os
import re
import shlex

_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_REDIRECCION = re.compile(r"(?<![<0-9&])(>>?)\s*([^\s;|&<>]+)")
# Las claves que lanzan un programa o preparan cómo se lanza: Exec, ExecStart, ExecStartPre…, TryExec y las de entorno (Environment, EnvironmentFile).
_CLAVE_QUE_EJECUTA = re.compile(r"^\s*(?:(?:Try)?Exec\w*|Environment\w*)\s*=", re.I)
_SUDO = {"sudo", "doas", "pkexec", "run0", "su"}
BORRAN = {"rm", "unlink", "shred", "rmdir", "trash-put", "trash-rm", "srm", "wipe"}
ESCRIBEN = {"tee", "cp", "mv", "install", "ln", "mkdir", "touch", "truncate", "rsync", "dd"}


def _expandir(ruta, casa):
    return os.path.normpath(os.path.join(casa, re.sub(r"^(?:~|\$HOME\b|\$\{HOME\})(?=/|$)", lambda _: casa, ruta)))


def es_de_claves(contenido):
    """¿Es un archivo de claves y valores con grupos (formato INI: [grupo], clave=valor y comentarios, como los de escritorio y los de systemd)? Sin
    ningún [grupo] no cuenta: «NOMBRE=valor» suelto es lo que leen una shell o environment.d (PATH=…, LD_PRELOAD=…), y eso puede ejecutar código."""
    lineas = [x.strip() for x in str(contenido).splitlines() if x.strip() and not x.strip().startswith(("#", ";"))]
    if not lineas or not re.fullmatch(r"\[[^\]]+\]", lineas[0]):
        return False
    return all(re.fullmatch(r"\[[^\]]+\]", x) or re.fullmatch(r"[A-Za-z0-9_.\-]+(?:\[[^\]]*\])?\s*=.*", x) for x in lineas)


def hace_ejecutar(contenido):
    """¿Lo escrito puede hacer que se ejecute algo? Si no es de claves y valores, sí (un script, un perfil de la shell…); si lo es, solo si lleva una
    clave Exec… o TryExec… (Exec, ExecStart, ExecStartPre, ExecStop…)."""
    if not es_de_claves(contenido):
        return True
    return any(_CLAVE_QUE_EJECUTA.match(x) for x in str(contenido).splitlines())


def _trozos_con_heredoc(comando):
    """[(texto de la orden, cuerpo del heredoc o None)]: cada línea de la orden, con el cuerpo de su heredoc pegado (sin trocearlo como órdenes)."""
    lineas, salida, i = str(comando).split("\n"), [], 0
    while i < len(lineas):
        linea = lineas[i]
        m = _HEREDOC.search(linea)
        if not m:
            salida.append((linea, None))
            i += 1
            continue
        cuerpo, i = [], i + 1
        while i < len(lineas) and lineas[i].strip() != m.group(2):
            cuerpo.append(lineas[i])
            i += 1
        if i >= len(lineas):
            return None                                     # un heredoc sin cierre: no se sabe qué hace
        salida.append((linea, "\n".join(cuerpo) + "\n"))
        i += 1
    return salida


def _palabras(tramo):
    try:
        return shlex.split(tramo)
    except ValueError:
        return None


def _sin_prefijos(palabras):
    from lina.nucleo.clasificador import _quitar_prefijos
    return _quitar_prefijos(palabras or [])


def escrituras(comando, casa=None):
    """(escrituras, resto) de la orden: escrituras = [(ruta absoluta, contenido, «>» o «>>»)] de lo que escribe con contenido que se sabe antes de ejecutarla
    (heredoc, echo o printf literales, kwriteconfig); resto = los tramos que no escriben nada. None si escribe algo cuyo contenido no se puede saber,
    o si no se puede leer la orden."""
    casa = casa or os.path.expanduser("~")
    trozos = _trozos_con_heredoc(comando)
    if trozos is None:
        return None
    from lina.nucleo.clasificador import _segmentos
    hechas, resto = [], []
    for linea, cuerpo in trozos:
        tramos = [linea] if cuerpo is not None else _segmentos(linea)
        for tramo in tramos:
            tramo = tramo.strip()
            if not tramo:
                continue
            palabras = _sin_prefijos(_palabras(_HEREDOC.sub(" ", tramo)))
            if palabras is None:
                return None
            prog = os.path.basename(palabras[0]) if palabras else ""
            destinos = [(op, d) for op, d in _REDIRECCION.findall(_HEREDOC.sub(" ", tramo)) if d not in ("/dev/null", "&1", "&2")]
            if prog.startswith("kwriteconfig") and "--file" in palabras and "--key" in palabras:
                i, j = palabras.index("--file"), palabras.index("--key")
                if i + 1 >= len(palabras) or j + 2 >= len(palabras) or palabras[j + 2].startswith("-"):
                    return None
                hechas.append((_expandir(palabras[i + 1], casa), f"[x]\n{palabras[j + 1]}={palabras[j + 2]}\n", ">"))
                continue
            if prog == "tee" and cuerpo is not None:
                rutas = [p for p in palabras[1:] if not p.startswith("-")]
                hechas += [(_expandir(r, casa), cuerpo, ">>" if any(p in ("-a", "--append") for p in palabras) else ">") for r in rutas]
                continue
            if destinos:
                if len(destinos) != 1:
                    return None
                op, ruta = destinos[0][0], _expandir(destinos[0][1], casa)
                if cuerpo is not None and prog == "cat":
                    hechas.append((ruta, cuerpo, op))
                    continue
                literal = _literal(_REDIRECCION.sub(" ", tramo))
                if literal is None:
                    return None
                hechas.append((ruta, literal, op))
                continue
            if prog in ESCRIBEN - {"mkdir"} or (prog == "sed" and any(p.startswith("-i") for p in palabras[1:])):
                return None                                 # copia, mueve, enlaza o edita: el contenido no se sabe antes
            resto.append(tramo)
    return hechas, resto


def _literal(tramo):
    """Lo que imprime un echo o printf sin nada de la shell ($, `), o None."""
    if re.search(r"[$`]", tramo):
        return None
    palabras = _sin_prefijos(_palabras(tramo))
    if not palabras:
        return None
    prog, args = os.path.basename(palabras[0]), palabras[1:]
    if prog == "echo":
        escapes = False
        while args and re.fullmatch(r"-[neE]+", args[0]):
            escapes = escapes or "e" in args[0]
            args = args[1:]
        texto = " ".join(args)
        return (_escapes(texto) if escapes else texto) + "\n"
    if prog == "printf" and args and "%" not in args[0] and len(args) == 1:
        return _escapes(args[0])
    return None


def _escapes(texto):
    return texto.replace("\\n", "\n").replace("\\t", "\t")


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            return f.read(200_000)
    except OSError:
        return ""


def _lo_que_queda(contenido, op, antes):
    """Lo que hay que juzgar: lo escrito o, si se añade a un archivo de claves que ya existe, sus líneas como si fueran de su último grupo."""
    if op == ">>" and antes and es_de_claves(antes):
        return "[añadido]\n" + contenido
    return contenido


def reversible_e_inocuo(comando, casa=None, existe=os.path.exists, se_puede_deshacer=lambda ruta: False, leer=_leer):
    """(True, «») si la orden solo escribe, dentro de tu carpeta y sin sudo, archivos de claves y valores sin ninguna clave Exec/TryExec, cada uno nuevo
    o que el diario puede deshacer, y lo demás que hace no cambia nada (lectura, o crear la carpeta donde escribe). Si no, (False, por qué)."""
    casa = os.path.normpath(casa or os.path.expanduser("~"))
    trozos = _trozos_con_heredoc(comando) or []
    if any(re.search(r"(?:^|[;&|(]\s*)(?:sudo|doas|pkexec|run0|su)\b", linea.strip()) for linea, _ in trozos):     # solo en las órdenes, no en lo escrito
        return False, "lleva permisos de administrador"
    partes = escrituras(comando, casa)
    if partes is None:
        return False, "escribe algo cuyo contenido no se puede saber antes"
    hechas, resto = partes
    if not hechas:
        return False, "no escribe nada"
    from lina.nucleo import contexto as CTX
    from lina.nucleo.clasificador import _es_lectura
    quedara = {}                                           # lo que va teniendo cada archivo a lo largo de la orden (> y luego >>)
    for ruta, contenido, op in hechas:
        if not (ruta == casa or ruta.startswith(casa + os.sep)) or CTX.protegida(ruta, casa):
            return False, f"escribe fuera de tu carpeta o en una ruta protegida ({ruta})"
        antes = quedara[ruta] if ruta in quedara else (leer(ruta) if existe(ruta) else "")
        if hace_ejecutar(_lo_que_queda(contenido, op, antes)):
            return False, f"lo que escribe en {os.path.basename(ruta)} puede hacer que se ejecute algo"
        if existe(ruta) and not se_puede_deshacer(ruta):
            return False, f"sobrescribe {os.path.basename(ruta)} sin copia para deshacerlo"
        quedara[ruta] = antes + contenido if op == ">>" else contenido
    for tramo in resto:
        palabras = _sin_prefijos(_palabras(tramo)) or []
        prog = os.path.basename(palabras[0]) if palabras else ""
        if prog == "mkdir" and all(a.startswith("-") or _expandir(a, casa).startswith(casa + os.sep) for a in palabras[1:]):
            continue
        if _es_lectura(tramo):
            continue
        if prog == "systemctl" and "--user" in palabras and any(v in palabras for v in ("daemon-reload", "list-unit-files", "status", "is-enabled")):
            continue                                       # recargar o mirar los servicios de tu usuario no cambia lo que arranca
        return False, f"hace algo más que escribir ({tramo[:60]})"
    return True, ""


def efectos(comando):
    """El efecto de cada tramo de la orden: «borrar», «escribir», «instalar», «servicio», «ejecutar» (sin las lecturas). Para que un «sí» solo cubra lo
    que se describió (A16): borrar no cubre escribir, ni instalar cubre activar un servicio."""
    from lina.nucleo import plataforma as PL
    from lina.nucleo.clasificador import _es_lectura, _segmentos
    trozos = _trozos_con_heredoc(comando) or [(comando, None)]
    hechos = set()
    for linea, cuerpo in trozos:
        for tramo in ([linea] if cuerpo is not None else _segmentos(linea)):
            if not tramo.strip() or (cuerpo is None and _es_lectura(tramo)):
                continue
            palabras = _sin_prefijos(_palabras(_HEREDOC.sub(" ", tramo))) or []
            prog = os.path.basename(palabras[0]) if palabras else ""
            args = palabras[1:]
            if prog in BORRAN or (prog == "gio" and args[:1] == ["trash"]) or (prog == "find" and "-delete" in args):
                hechos.add("borrar")
            elif prog in PL.GESTORES_PAQUETES or prog in PL.AYUDANTES_AUR or prog in ("pip", "pip3", "pipx", "npm", "cargo", "flatpak", "snap"):
                hechos.add("instalar")
            elif prog in ("systemctl", "loginctl", "service"):
                hechos.add("servicio")
            elif prog in ESCRIBEN or prog.startswith("kwriteconfig") or _REDIRECCION.search(_HEREDOC.sub(" ", tramo)) or (prog == "sed" and "-i" in " ".join(args)):
                hechos.add("escribir")
            elif prog:
                hechos.add("ejecutar")
    return hechos


def comodines_sin_nada(comando, casa=None):
    """Si la orden borra o mueve y TODO lo que nombra son rutas (con comodines o sin ellos) que no existen, la lista; si no, []. Así no se pide un «sí»
    para borrar nada (caso real: tres comodines inventados que no coincidían con ningún archivo)."""
    casa = casa or os.path.expanduser("~")
    from lina.nucleo.clasificador import _segmentos
    nombres = []
    for tramo in _segmentos(str(comando)):
        palabras = _sin_prefijos(_palabras(tramo)) or []
        prog, args = (os.path.basename(palabras[0]), palabras[1:]) if palabras else ("", [])
        if prog == "gio" and args[:1] == ["trash"]:
            args = args[1:]
        elif prog not in BORRAN | {"mv"}:
            return []
        rutas = [a for a in args if not a.startswith("-")]
        if prog == "mv":
            rutas = rutas[:-1]
        if not rutas:
            return []
        for r in rutas:
            if glob.glob(_expandir(r, casa)):
                return []
        nombres += rutas
    return nombres
