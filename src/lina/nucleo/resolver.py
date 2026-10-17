"""Lo que hace falta para resolver peticiones de configuración: ajustes de KDE (kwriteconfig, esquemas, paneles), paquetes del AUR
en los que se confía, fechas relativas y programas que faltan."""
import difflib
import os
import re
import subprocess
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from lina.nucleo import comandos
from lina.nucleo import ejecucion as EJ
from lina.nucleo import idioma as IDI
from lina.nucleo import plataforma as PL
from lina.nucleo import rutas as RUT
from lina.nucleo.clasificador import _HOME, _PROGRAMAS_PANELES, _quitar_prefijos, _segmentos, _sin_acentos, _tokens
from lina.nucleo.ejecucion import _abs

# Si falta un programa, la herramienta dice qué paquete lo trae. Los paneles de ajustes se comprueban contra la lista real
# de KDE. Los ajustes de KDE guardan su valor anterior y avisan si la clave no existía (suele ser una clave inventada).
# Los paquetes del AUR en los que confías (los que ya confirmaste una vez) se instalan sin preguntar.
_estado_fdb = {"sincronizada": False}                 # la base de archivos de pacman (pacman -F) se sincroniza una vez por sesión
_cache_paneles = {"t": 0.0, "datos": {}}
_AUR_HELPERS = {"paru", "yay", "pikaur", "aurman"}
ARCHIVO_CONFIABLES = RUT.editable("paquetes_confiables.txt")
_cache_conf: dict = {"marca": None, "datos": set()}
_PROGRAMAS_KWRITE = {"kwriteconfig6": "kreadconfig6", "kwriteconfig5": "kreadconfig5"}
_SIN_VALOR = "__SIN_VALOR_ASISTENTE__"


def _programas_que_faltan(salida):
    """Programas que el shell dice no encontrar («nombre: command not found»)."""
    nombres = (re.findall(r"(?m)(?<![\w.+-])([A-Za-z0-9_][A-Za-z0-9_.+-]{0,39}): command not found[ \t]*$", salida)
               + re.findall(r"command not found: ([A-Za-z0-9_][A-Za-z0-9_.+-]{0,39})", salida))
    return list(dict.fromkeys(nombres))[:2]


def _ejecutables_parecidos(programa):
    """Programas YA instalados cuyo nombre empieza igual (lo habitual cuando un programa cambia de nombre entre versiones)."""
    base = re.sub(r"[-_.]?\d+$", "", programa)
    if len(base) < 3:
        return []
    vistos = set()
    for carpeta in os.environ.get("PATH", "").split(os.pathsep):
        try:
            nombres = os.listdir(carpeta)
        except OSError:
            continue
        for n in nombres:
            if n != programa and n.startswith(base) and re.fullmatch(r"[\w.+-]+", n) and os.access(os.path.join(carpeta, n), os.X_OK):
                vistos.add(n)
    return sorted(vistos, key=lambda n: (len(n), n))[:5]


def _paquetes_que_traen(regex_nombre, avisar=None):
    """[(paquete, programa)] de los repositorios oficiales (pacman -F, apt-file…). Baja la lista de archivos si falta. [] si esta distribución no sabe."""
    consulta = PL.consulta_quien_trae(regex_nombre)
    if not consulta:
        return []
    codigo, salida = EJ._ejecutar_simple(consulta, timeout=60)
    sincronizar = PL.sincronizar_archivos()
    if (codigo is None or codigo > 1 or re.search(r"database file for .* does not exist|use '-Fy'|cache is empty|apt-file update", salida)) \
            and sincronizar and not _estado_fdb["sincronizada"]:
        _estado_fdb["sincronizada"] = True            # la lista de archivos hay que bajarla una vez
        if avisar:
            avisar("Voy a actualizar la lista de archivos de paquetes para saber cuál trae ese programa. Tardará un momento.")
        EJ._como_root(sincronizar, timeout=240)
        codigo, salida = EJ._ejecutar_simple(consulta, timeout=60)
    return PL.pares_que_traen(salida)


def _sugerir_paquete(programa, avisar=None):
    """Qué hacer cuando falta un programa. Todo se DESCUBRE en este equipo: programas parecidos ya instalados, o el paquete oficial."""
    parecidos = _ejecutables_parecidos(programa)
    if parecidos:
        return (f"«{programa}» no existe en este sistema, pero hay programas con nombre parecido ya instalados: {', '.join(parecidos)}. "
                "Si es el mismo programa con otro nombre (pasa entre versiones), mira su `--help` y repite el comando con ese nombre.")
    exactos = _paquetes_que_traen(re.escape(programa), avisar)
    if exactos:
        paquetes = list(dict.fromkeys(p for p, _ in exactos))[:3]
        otros = f" (también lo trae: {', '.join(paquetes[1:])})" if len(paquetes) > 1 else ""
        return (f"«{programa}» no está instalado. Lo trae el paquete «{paquetes[0]}» de los repositorios oficiales{otros}: "
                f"instálalo con `{PL.orden_canonica_instalar([paquetes[0]])}` (va directo, sin preguntar) y repite el comando.")
    base = re.sub(r"[-_.]?\d+$", "", programa)
    similares = _paquetes_que_traen(re.escape(base) + r"[\w.+-]*", avisar) if len(base) >= 3 else []
    if similares:
        paquetes = list(dict.fromkeys(p for p, _ in similares))[:3]
        trae = "; ".join(f"«{p}» (trae {', '.join(e for q, e in similares if q == p)[:60]})" for p in paquetes)
        return (f"«{programa}» no está instalado. Hay paquetes oficiales con programas de nombre parecido: {trae}. Si es el mismo programa con "
                f"otro nombre, instálalo con `{PL.orden_canonica_instalar([paquetes[0]])}` (va directo) y usa ese nombre; compruébalo con su `--help`.")
    return (f"«{programa}» no está instalado y no lo encuentro en los repositorios oficiales (o esta distribución no me deja buscar por archivo: "
            f"prueba `{PL.FAMILIAS.get(PL.familia_actual(), PL._GENERICO)['texto_buscar']} {programa}`). Mira si existe en Flathub "
            f"(`flatpak search {programa}`); si solo está en {PL.FAMILIAS.get(PL.familia_actual(), PL._GENERICO)['texto_externo']} hay que preguntar al usuario. Si no hay forma de conseguirlo, "
            "díselo con claridad en vez de dar el trabajo por hecho.")


_NO_VISIBLE = re.compile(r"\bno (se )?(ve|ven|veo|vemos|muestra|aparece|aparecen|encuentra|distingue)\b|\bno (puedo|se puede) (ver|leer)\b"
                         r"|\bno es (visible|legible)\b|\bno (hay|existe) (ningun )?(control|panel|ventana)\b|\bnot (visible|shown|found)\b")


def control_no_visible(texto):
    """True si lo que dijo la visión es «ese control no se ve» (no un valor distinto): la comprobación no es concluyente."""
    return bool(_NO_VISIBLE.search(_sin_acentos(str(texto or "").lower())))


_RELLENO_PENDIENTE = PL.GESTORES_PAQUETES | {"deshacer", "cambio", "anotado", "ultimo", "aplicado", "sistema", "sudo", "noconfirm", "needed", "purge", "remove",
                                              "assumeyes", "recommends", "interactive",
                      "systemctl", "hacer", "instalar", "desinstalar", "reinstalar", "quitar", "restaurar", "devolver", "recuperar", "paquete",
                      "paquetes", "archivo", "archivos", "servicio", "ajuste", "carpeta", "fichero", "programa", "aplicacion", "tarea",
                      "voy", "como", "estaba", "para", "este", "esta", "esto", "con", "los", "las", "del"}


def que_pendiente(p):
    """Lo que está esperando el «sí», con palabras: la descripción si es una acción interna (deshacer…), o el motivo."""
    if p.get("funcion"):
        return str(p["comando"])[:160]
    return str(p.get("motivo") or p["comando"])[:90]


def pendiente_dicho(texto, pendientes):
    """True si la frase menciona algo CONCRETO de cada cosa pendiente (un nombre, no solo «deshacer el último cambio»)."""
    dicho = _sin_acentos(str(texto).lower())
    for p in pendientes:
        base = _sin_acentos((str(p["comando"]) if p.get("funcion") else f"{p.get('motivo') or ''} {p['comando']}").lower())
        claves = {w for w in re.findall(r"[a-z0-9][a-z0-9._+-]{2,}", base) if w not in _RELLENO_PENDIENTE and not re.fullmatch(r"[\d._+-]+", w)}
        if claves and not any(w[:6] in dicho for w in claves):                    # por la raíz: «reiniciar» ≈ «reinicio»
            return False
    return True


_RECARGA_FALLIDA = re.compile(r"command not found|No such file or directory|Failed to |not found|does not exist|could not be found|Access denied", re.I)


def aviso_recarga(comando, resultado):
    """'' si la recarga fue bien. Si no (código distinto de 0, o un error en la salida aunque el código sea 0 por un «|| true»),
    el aviso que debe ver la IA, con las pistas que el ejecutor ya añadió (programa parecido instalado, paquete...)."""
    if resultado.startswith("código de salida: 0") and not _RECARGA_FALLIDA.search(resultado):
        return ""
    cuerpo = resultado.split("\n", 1)[1] if resultado.startswith("código de salida") and "\n" in resultado else resultado
    detalle = " | ".join(l.strip() for l in cuerpo.splitlines() if l.strip())[:500] or "(sin salida)"
    if "NO EJECUTADO" in resultado:
        return (f" OJO: el comando de recarga `{comando[:80]}` NO se ha ejecutado (queda pendiente de la confirmación del usuario): {detalle} "
                "El programa en marcha puede no haber recargado.")
    return (f" OJO: el comando de recarga `{comando[:80]}` NO funcionó: {detalle} La comprobación del panel puede valer (los paneles suelen "
            "leer del disco al abrirse), pero el programa que está en marcha puede no haber recargado: descubre cómo recargarlo (busctl, "
            "systemctl --user) o dile al usuario que lo reinicie.")


def _resolver_fecha(texto, hoy=None):
    """«hoy», «ayer», «anteayer», AAAA-MM-DD o DD/MM[/AAAA] → ('AAAA-MM-DD', None); si no se entiende → (None, mensaje)."""
    import datetime
    hoy = hoy or datetime.date.today()
    t = _sin_acentos(str(texto).strip().lower())
    atras = {"hoy": 0, "ayer": 1, "anteayer": 2, "antes de ayer": 2, "antier": 2}
    error = (None, f"No entiendo la fecha «{texto}». Usa «hoy», «ayer», «anteayer» o una fecha como 2026-10-05 (o 05/10).")
    if t in atras:
        return (hoy - datetime.timedelta(days=atras[t])).isoformat(), None
    sin_anio = False
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        a, mes, d = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?", t)
        if not m:
            return error
        sin_anio = m.group(3) is None
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3) or hoy.year)
    try:
        dia = datetime.date(a, mes, d)
    except ValueError:
        return error
    if sin_anio and dia > hoy:
        dia = datetime.date(a - 1, mes, d)                                  # «30/12» dicho en enero es del año pasado
    return dia.isoformat(), None


_PARECE_LECTURA = re.compile(r"(?:^|\s)(?:--?(?:list|ls|help|version|status|show|get|print|dump|query|info|search)(?:-[\w-]+|s)?(?=\s|=|$)"
                             r"|list|ls|status|show|get|info|query|search|print|dump|which|whereis)(?:\s|=|$)")


_CURL_ESCRIBE = re.compile(r"(?:^|\s)(?:-[a-zA-Z]*[oOTdFX][a-zA-Z]*|--(?:output|remote-name|upload-file|data\S*|form|request))(?:\s|=|$)|[>|]")


def _parece_lectura(comando):
    """Un comando que el código no sabe interpretar pero que por cómo está escrito solo mira, no cambia nada: --list, --help, status…,
    o un curl sin banderas ni redirecciones que escriban (su respuesta va a la pantalla)."""
    comando = str(comando)
    if _PARECE_LECTURA.search(comando):
        return True
    return bool(re.match(r"\s*(?:sudo\s+)?curl\b", comando)) and not _CURL_ESCRIBE.search(comando)


def _clave_rechazo(texto):
    """Para comparar «lo mismo» aunque cambien los espacios o las mayúsculas."""
    return " ".join(str(texto).split()).lower()


def _paneles_kde():
    """{id: nombre} de los paneles de ajustes de KDE que existen de verdad (kcmshell6 --list); caché de 10 minutos."""
    if _cache_paneles["datos"] and time.time() - _cache_paneles["t"] < 600:
        return _cache_paneles["datos"]
    codigo, salida = EJ._ejecutar_simple(["kcmshell6", "--list"], timeout=20)
    datos = {}
    if codigo == 0:
        for linea in salida.splitlines():
            m = re.match(r"^\s*([A-Za-z0-9_.+-]+)\s+-\s+(.+?)\s*$", linea)
            if m:
                datos[m.group(1)] = m.group(2)
    _cache_paneles.update(t=time.time(), datos=datos)
    return datos


def _validar_panel_kde(comando):
    """Si el comando abre un panel de ajustes de KDE que NO existe: el mensaje de error con los parecidos. Si no, None."""
    segmentos = _segmentos(comando)
    if len(segmentos) != 1:
        return None
    t = _tokens(segmentos[0])
    resto = _quitar_prefijos(t) if t else None
    if not resto or os.path.basename(resto[0]) not in _PROGRAMAS_PANELES:
        return None
    ids = [a for a in resto[1:] if not a.startswith("-")]
    paneles = _paneles_kde() if ids else {}
    for pid in ids:
        if not paneles or pid in paneles:
            continue
        nucleo = re.sub(r"^kcm_?", "", pid).lower()
        parecidos = difflib.get_close_matches(pid, list(paneles), n=5, cutoff=0.5)
        parecidos += [i for i in paneles if nucleo and nucleo in i.lower() and i not in parecidos]
        parecidos += [i for i, n in paneles.items() if nucleo and nucleo in n.lower() and i not in parecidos]
        sugerencias = ", ".join(f"{i} ({paneles[i]})" for i in parecidos[:5]) or "ninguno parecido"
        return (f"NO EXISTE el panel de ajustes «{pid}»: no se ha abierto nada. Paneles parecidos: {sugerencias}. Usa el identificador "
                "exacto (la lista completa sale con `kcmshell6 --list`) y repite. No le digas al usuario que lo has abierto.")
    return None


# ---- Paquetes del AUR en los que confías ----
def paquetes_confiables():
    """Los paquetes del AUR de paquetes_confiables.txt (se relee solo al cambiar el archivo)."""
    try:
        marca = ARCHIVO_CONFIABLES.stat().st_mtime_ns
    except OSError:
        return set()
    if marca == _cache_conf["marca"]:
        return _cache_conf["datos"]
    datos = set()
    try:
        for linea in ARCHIVO_CONFIABLES.read_text(encoding="utf-8").splitlines():
            linea = linea.split("#", 1)[0].strip()
            if re.fullmatch(r"[\w.@+-]+", linea):
                datos.add(linea)
    except OSError:
        pass
    _cache_conf.update(marca=marca, datos=datos)
    return datos


def recordar_confiables(nombres):
    """Añade estos paquetes del AUR a la lista de confianza (porque acabas de confirmar su instalación)."""
    nuevos = [n for n in nombres if n not in paquetes_confiables()]
    if not nuevos:
        return []
    cabecera = ("# Paquetes del AUR en los que confías: el asistente los instala SIN preguntar.\n"
                "# Se rellena solo cuando confirmas la instalación de uno. Borra una línea para que vuelva a preguntar.\n"
                "# El asistente no puede modificar este archivo por voz.\n")
    try:
        existe = ARCHIVO_CONFIABLES.exists()
        with ARCHIVO_CONFIABLES.open("a", encoding="utf-8") as f:
            if not existe:
                f.write(cabecera)
            for n in nuevos:
                f.write(f"{n}  # confirmado el {time.strftime('%Y-%m-%d')}\n")
    except OSError:
        return []
    return nuevos


def _aur_instalar(base, args):
    """Nombres que instala un «paru -S nombre...» puntual (None si no lo es: actualizaciones, otras operaciones)."""
    if base not in _AUR_HELPERS:
        return None
    letras = "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))
    if "S" not in letras or "u" in letras or "--sysupgrade" in args:
        return None
    nombres = [a for a in args if not a.startswith("-")]
    return nombres or None


def _aur_todo_confiable(base, args):
    nombres = _aur_instalar(base, args)
    return bool(nombres) and all(n in paquetes_confiables() for n in nombres)


# ---- Ajustes de KDE (kwriteconfig6) ----
def _parse_kwriteconfig(args):
    """kwriteconfig6 --file F --group G [--group G2] --key K [--type T] [--delete] [VALOR] → dict, o None si no se entiende."""
    d = {"archivo": None, "grupos": [], "clave": None, "valor": "", "borrar": False}
    pos, i = [], 0
    while i < len(args):
        a = args[i]
        if a in ("--file", "--group", "--key", "--type") and i + 1 < len(args):
            if a == "--file":
                d["archivo"] = args[i + 1]
            elif a == "--group":
                d["grupos"].append(args[i + 1])
            elif a == "--key":
                d["clave"] = args[i + 1]
            i += 2
            continue
        if a == "--delete":
            d["borrar"] = True
        elif a == "--notify":
            pass
        elif a.startswith("--"):
            return None
        else:
            pos.append(a)
        i += 1
    if not d["archivo"] or not d["clave"] or len(pos) > 1:
        return None
    d["valor"] = pos[0] if pos else ""
    return d


def _leer_ajuste(programa_lectura, archivo, grupos, clave):
    """(se pudo leer, valor actual o None si la clave no existe)."""
    argv = [programa_lectura, "--file", archivo]
    for g in grupos:
        argv += ["--group", g]
    argv += ["--key", clave, "--default", _SIN_VALOR]
    codigo, salida = EJ._ejecutar_simple(argv)
    if codigo != 0:
        return False, None
    return True, (None if salida.strip() == _SIN_VALOR else salida)


def _es_configuracion(ruta):
    """¿Es un archivo de configuración de un programa (donde editar NO prueba que el programa lo use)?"""
    ruta = _abs(ruta)
    return ruta.startswith((_HOME + "/.config/", _HOME + "/.local/share/", "/etc/"))


def coincide_visto(visto, esperado):
    """¿Lo que se ve en pantalla es lo esperado? Sin tildes ni mayúsculas, con límites de número («5 minutos» NO está en «15 minutos»)."""
    v, e = comandos.normalizar(visto or ""), comandos.normalizar(esperado or "")
    if not e:
        return False
    inicio = r"(?<![a-z0-9])" if e[0].isalnum() else ""             # «activado» NO está dentro de «desactivado»
    for m in re.finditer(inicio + re.escape(e) + r"(?!\d)", v):
        negado = re.search(r"(?:^|\s)(?:no|sin|nunca)\s*$", v[:m.start()]) and not re.match(r"(?:no|sin|nunca)\b", e)      # «no activado» tampoco
        if not negado:
            return True
    nums_e, nums_v = re.findall(r"\d+", e), re.findall(r"\d+", v)
    palabras = [w for w in re.findall(r"[a-z]{3,}", e) if w not in {"tras", "cada", "con", "los", "las", "por", "una", "uno"}]
    fichas = v.split()
    return bool(nums_e) and all(n in nums_v for n in nums_e) and all(w in v or any(f.startswith(w[:3]) for f in fichas) for w in palabras)


_CONTEXTO_NEGATIVO = re.compile(
    r"no esta(?:n)? (?:instalad|disponible)|no disponible|no existe|no se (?:encuentra|ha encontrado|pudo|puede)|no (?:fue|ha sido) (?:encontrad|posible)|no encontrad"
    r"|not (?:installed|found|available)|does not exist|doesn t exist|invalid|invalido|\berror\b|\baviso\b|advertencia|warning|por omision|en su lugar")


def mismo_valor_visto(a, b):
    """¿Dos lecturas del mismo control dicen lo mismo (aunque la visión las redacte distinto)? Solo orienta el consejo; nunca da nada por bueno."""
    ta, tb = set(re.findall(r"[a-z0-9]{2,}", comandos.normalizar(a or ""))), set(re.findall(r"[a-z0-9]{2,}", comandos.normalizar(b or "")))
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def visto_con_problema(visto, esperado):
    """Lo esperado SALE en lo que se ve, pero rodeado de un aviso que dice lo contrario («el esquema X no está instalado»). Si TODAS las
    veces que sale es en ese contexto, no cuenta como comprobado. Las palabras del propio valor esperado no cuentan como aviso."""
    v, e = comandos.normalizar(visto or ""), comandos.normalizar(esperado or "")
    if not e:
        return False
    apariciones = list(re.finditer(r"(?<!\d)" + re.escape(e) + r"(?!\d)", v))
    if not apariciones:
        return False
    for m in apariciones:
        ventana = v[max(0, m.start() - 90):m.start()] + " " + v[m.end():m.end() + 90]       # lo de alrededor, SIN el valor mismo
        if not _CONTEXTO_NEGATIVO.search(ventana):
            return False                                                                    # esta vez sale limpio
    return True


# ---- Dónde se compilan los nombres de las claves ----
DIRS_BINARIOS = [Path("/usr/lib"), Path("/usr/lib64"), Path("/usr/libexec")]


def _identificadores(datos, palabras):
    """Nombres con aspecto de clave (CamelCase) que hay dentro de un binario, en ASCII y en UTF-16 (QStringLiteral), con TODAS las palabras."""
    candidatos = {m.group().decode("ascii") for m in re.finditer(rb"[A-Za-z][A-Za-z0-9_]{5,60}", datos)}
    for m in re.finditer(rb"(?:[A-Za-z0-9_]\x00){6,60}", datos):
        try:
            candidatos.add(m.group().decode("utf-16-le"))
        except UnicodeDecodeError:
            pass
    return {c for c in candidatos if re.search(r"[a-z][A-Z]", c) and all(p in c.lower() for p in palabras)}


def buscar_clave_en_binarios(app, palabras):
    """Nombres de claves de configuración que un programa lleva compilados. Sirve cuando no hay esquema (.kcfg) instalado."""
    app_n = re.sub(r"[^a-z0-9]", "", str(app or "").lower())
    claves = [p for p in re.split(r"\W+", comandos.normalizar(palabras or "")) if len(p) >= 3][:5]
    if len(app_n) < 3 or not claves:
        return "Falta el programa (tal como aparece en el nombre de sus archivos) y las palabras en inglés que debe contener la clave."
    ficheros = []
    for base in DIRS_BINARIOS:
        for raiz, dirs, nombres in os.walk(base):
            if raiz.count(os.sep) - str(base).count(os.sep) > 5:
                dirs[:] = []
            for n in nombres:
                ruta = os.path.join(raiz, n)
                if ".so" in n.lower() and app_n in re.sub(r"[^a-z0-9]", "", ruta.lower()):
                    ficheros.append(ruta)
    if not ficheros:
        return f"No encuentro binarios de «{app}» en /usr/lib. Prueba con otro nombre del programa o busca en internet (buscar_web, en inglés)."
    encontrados, leidos, inicio = {}, 0, time.time()
    for ruta in sorted(ficheros)[:60]:
        try:
            if os.path.getsize(ruta) > 40 * 1024 * 1024 or leidos > 150 * 1024 * 1024 or time.time() - inicio > 20:
                continue
            datos = Path(ruta).read_bytes()
        except OSError:
            continue
        leidos += len(datos)
        for ident in _identificadores(datos, claves):
            encontrados.setdefault(ident, os.path.basename(ruta))
    if not encontrados:
        return (f"En los {len(ficheros)} binarios de «{app}» no hay nombres con «{' '.join(claves)}». Prueba con otras palabras en inglés "
                "(por ejemplo timeout, display, shutdown) o busca en internet.")
    lineas = [f"- {n}  ({f})" for n, f in sorted(encontrados.items(), key=lambda x: (len(x[0]), x[0]))[:30]]
    pie = []
    for nombre in sorted(os.listdir(os.path.join(_HOME, ".config"))) if os.path.isdir(os.path.join(_HOME, ".config")) else []:
        if nombre.endswith("rc") and app_n in re.sub(r"[^a-z0-9]", "", nombre.lower()):
            grupos = list(dict.fromkeys(g for g, _ in _parsear_ini(Path(_HOME, ".config", nombre).read_text(encoding="utf-8", errors="replace"))
                                        if g))[:10]
            pie.append(f"Grupos que ya existen en ~/.config/{nombre}: " + (", ".join(grupos) if grupos else "(ninguno todavía)"))
    return (f"Nombres que lleva compilados «{app}» y contienen «{' '.join(claves)}» (las claves de configuración suelen salir así; los "
            "grupos también):\n" + "\n".join(lineas) + ("\n" + "\n".join(pie) + "\nLos grupos van anidados: mira cómo se anidan los que ya existen. "
                                                         if pie else "\n") + "No dicen en qué grupo va cada clave ni en qué unidad: pruébalas con "
            "probar_ajuste_kde, que mira el panel y revierte si no tienen efecto.")


# ---- Aprender mirando: qué clave se mueve cuando el usuario lo cambia en el panel ----
_foto_config: dict = {"datos": {}}


def _parsear_ini(texto):
    grupo, filas = "", {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith(("#", ";")):
            continue
        if linea.startswith("[") and linea.endswith("]"):
            grupo = linea
        elif "=" in linea:
            k, v = linea.split("=", 1)
            filas[(grupo, re.sub(r"\[\$\w+\]$", "", k.strip()))] = v.strip()
    return filas


def _fotografiar_config(carpeta):
    """Los archivos de configuración de KDE de primer nivel (los acabados en «rc» y kdeglobals): solo esos, nunca archivos con secretos."""
    datos = {}
    try:
        nombres = os.listdir(carpeta)
    except OSError:
        return datos
    for n in nombres:
        if not (re.fullmatch(r"[\w.-]*rc", n) or n == "kdeglobals"):
            continue
        ruta = os.path.join(carpeta, n)
        try:
            if os.path.isfile(ruta) and os.path.getsize(ruta) <= 200_000:
                datos[n] = Path(ruta).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return datos


MAX_CAMBIOS_CONFIG = 40                # de un comando desconocido se anotan como mucho tantas claves cambiadas


def _valor_corto(v):
    """El valor de una clave para anotarlo: una línea, sin caracteres de control y sin pasarse de largo."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(v))[:80]


def _diferencias_config(antes, ahora):
    """Lo que ha cambiado entre dos fotos de la configuración de KDE, clave a clave: [{archivo, grupo, clave, antes, despues}].
    «antes» es None si la clave no existía; «despues» es None si la han quitado."""
    cambios = []
    for n in sorted(set(antes) | set(ahora)):
        a, b = _parsear_ini(antes.get(n, "")), _parsear_ini(ahora.get(n, ""))
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                cambios.append({"archivo": n, "grupo": k[0], "clave": k[1],
                                "antes": None if k not in a else _valor_corto(a[k]), "despues": None if k not in b else _valor_corto(b[k])})
    return cambios


def _hay_anterior(e):
    return bool(e.get("cambios") or e.get("valor_anterior"))


def _resumen_anterior(e, maximo=6):
    """Lo que se sabe de cómo estaba algo antes de un cambio: el valor leído con una receta y/o las claves de KDE que se movieron."""
    partes = []
    va = e.get("valor_anterior")
    if va:
        partes.append(f"«{va.get('ajuste', '?')}» valía {va.get('valor', '?')} (leído antes del cambio con `{va.get('leer', '?')}`)")
    if e.get("cambios"):
        partes.append(_resumen_cambios(e["cambios"], maximo))
    return "; ".join(partes)


def _leer_valor(comando):
    """Ejecuta un comando de LECTURA de una receta y devuelve lo que muestra (o None). Nunca lanza."""
    try:
        r = subprocess.run(["bash", "-c", comando], capture_output=True, text=True, timeout=10)
        return re.sub(r"\s+", " ", r.stdout).strip()[:200] or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _texto_cambio(c):
    ant = "(no existía)" if c.get("antes") is None else c["antes"]
    des = "(eliminada)" if c.get("despues") is None else c["despues"]
    return f"{c.get('archivo', '?')} {c.get('grupo', '')} {c.get('clave', '?')}: {ant} → {des}"


def _resumen_cambios(cambios, maximo=6):
    """Las claves cambiadas en una frase; si hay más de «maximo», se dice cuántas faltan."""
    cambios = list(cambios or [])
    texto = "; ".join(_texto_cambio(c) for c in cambios[:maximo])
    return texto + (f"; …y {len(cambios) - maximo} más" if len(cambios) > maximo else "")


def observar_config(fase, carpeta=None):
    carpeta = carpeta or os.path.join(_HOME, ".config")
    if fase == "antes":
        _foto_config["datos"] = _fotografiar_config(carpeta)
        return (f"Guardada una foto de cómo está ahora la configuración de KDE ({len(_foto_config['datos'])} archivos). Dile al usuario "
                "que cambie ÉL el ajuste en el panel (y pulse Aplicar) y que te avise cuando termine; entonces llama a "
                "observar_config con fase «despues» y verás qué clave se ha movido.")
    if fase != "despues":
        return "La fase es «antes» (antes de que el usuario cambie el ajuste) o «despues» (cuando ya lo ha cambiado)."
    if not _foto_config["datos"]:
        return "Primero llama a observar_config con fase «antes»."
    ahora, antes = _fotografiar_config(carpeta), _foto_config["datos"]
    cambios = []
    for n in sorted(set(ahora) | set(antes)):
        a, b = _parsear_ini(antes.get(n, "")), _parsear_ini(ahora.get(n, ""))
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                cambios.append(f"- {n} {k[0]} {k[1]}: {a.get(k, '(no existía)')} → {b.get(k, '(eliminada)')}")
    if not cambios:
        return ("No ha cambiado ningún archivo de configuración de KDE. Puede que el usuario no haya pulsado Aplicar, o que ese ajuste "
                "se guarde en otro sitio. Pídele que lo repita y vuelve a mirar.")
    return ("Esto es lo que ha cambiado en la configuración de KDE (esa es la clave real y el grupo exacto, con la unidad que usa):\n"
            + "\n".join(cambios[:20]) + "\nAplícala tú con probar_ajuste_kde para el valor que el usuario quiere.")


# ---- Los esquemas de KDE: dónde están declaradas las claves de verdad ----
# Cada aplicación de KDE declara sus ajustes en un archivo .kcfg (grupo, clave, tipo, valor por defecto). Los valores por
# defecto NO se escriben en tu archivo de configuración: que una clave no esté ahí no significa que sea inválida.
DIRS_KCFG = [Path("/usr/share/config.kcfg"), Path("/usr/local/share/config.kcfg")]
_cache_esquemas = {"t": 0.0, "datos": []}


def _esquemas_kcfg():
    """Las claves que declaran las aplicaciones de KDE: [{archivo, grupo, clave, tipo, defecto, etiqueta}] (caché de 10 min)."""
    if _cache_esquemas["datos"] and time.time() - _cache_esquemas["t"] < 600:
        return _cache_esquemas["datos"]
    datos = []
    for carpeta in DIRS_KCFG:
        try:
            ficheros = sorted(carpeta.glob("*.kcfg"))
        except OSError:
            continue
        for f in ficheros:
            try:
                raiz = ET.parse(f).getroot()
            except (ET.ParseError, OSError):
                continue                                   # un esquema roto no tumba el resto
            nombre = lambda e: e.tag.rsplit("}", 1)[-1]
            archivos = [h.get("name") for h in raiz if nombre(h) == "kcfgfile" and h.get("name")]
            archivo = os.path.basename(archivos[0]) if archivos else ""
            for g in raiz:
                if nombre(g) != "group":
                    continue
                for en in g:
                    clave = en.get("key") or en.get("name")
                    if nombre(en) != "entry" or not clave:
                        continue
                    textos, calculado = {}, False
                    for h in en:
                        if nombre(h) == "default" and "default" not in textos:
                            calculado = h.get("code") == "true"           # <default code="true">: lo calcula el programa
                        textos.setdefault(nombre(h), (h.text or "").strip())
                    datos.append({"archivo": archivo, "grupo": g.get("name") or "", "clave": clave, "tipo": en.get("type") or "",
                                  "defecto": "" if calculado else textos.get("default", ""), "calculado": calculado,
                                  "etiqueta": textos.get("label") or textos.get("tooltip") or textos.get("whatsthis") or ""})
    _cache_esquemas.update(t=time.time(), datos=datos)
    return datos


def _clave_en_esquema(archivo, grupos, clave):
    """¿Existe esta clave en el esquema de KDE de ese archivo? ('si' | 'otro_grupo' | 'no' | 'sin_esquema', detalle)."""
    entradas = [e for e in _esquemas_kcfg() if e["archivo"] == os.path.basename(archivo)]
    if not entradas:
        return "sin_esquema", ""
    ultimo = grupos[-1] if grupos else ""
    mismas = [e for e in entradas if e["clave"] == clave]
    if not mismas:
        return "no", ""
    for e in mismas:
        g = e["grupo"]
        if g == ultimo or "$(" in g or g.split("][")[-1] == ultimo:      # un grupo con parámetros ($(perfil)) vale para cualquiera
            return "si", ""
    return "otro_grupo", ", ".join(sorted({e["grupo"] for e in mismas}))[:120]


def _leer_ini(ruta):
    """[(grupo, clave, valor)] de un archivo de configuración de KDE (grupos anidados tal cual: «[AC][Display]»)."""
    try:
        lineas = Path(ruta).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    grupo, filas = "", []
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith(("#", ";")):
            continue
        if linea.startswith("[") and linea.endswith("]"):
            grupo = linea
        elif "=" in linea:
            k, v = linea.split("=", 1)
            filas.append((grupo, re.sub(r"\[\$\w+\]$", "", k.strip()), v.strip()))
    return filas


def _num(n):
    return str(int(n)) if float(n).is_integer() else str(round(float(n), 4))


def _candidatos_valor(texto):
    """«5 minutos» → {'5', '300', '300000'}: el mismo valor en los formatos habituales de KDE (minutos, segundos, milisegundos)."""
    limpio = "".join(c for c in unicodedata.normalize("NFD", str(texto or "").lower()) if unicodedata.category(c) != "Mn")   # sin tildes, con la coma decimal
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(horas?|h|minutos?|min|segundos?|seg|s|milisegundos?|ms)?\b", limpio)
    if not m:
        return set()
    n, u = float(m.group(1).replace(",", ".")), m.group(2) or ""
    if u == "h" or u.startswith("hora"):
        seg = n * 3600
    elif u.startswith("min"):
        seg = n * 60
    elif u in ("s", "seg") or u.startswith("segundo"):
        seg = n
    elif u == "ms" or u.startswith("mili"):
        seg = n / 1000
    else:
        return {_num(n)}
    return {_num(n), _num(seg), _num(seg * 1000), _num(seg / 60)}


def _mismo_numero(a, candidatos):
    try:
        return any(abs(float(a) - float(c)) < 1e-9 for c in candidatos)
    except (TypeError, ValueError):
        return str(a).strip() in candidatos


def buscar_ajuste_kde(consulta, valor=None):
    """Qué claves de configuración existen de verdad para un ajuste de KDE, cuánto valen ahora y cuáles valen lo que dice el usuario."""
    palabras = [p for p in re.split(r"\W+", comandos.normalizar(consulta or "")) if len(p) >= 2][:6]
    if not palabras:
        return "Falta qué ajuste buscas. Usa palabras en INGLÉS que describan el ajuste (los esquemas de KDE están en inglés)."
    esquemas = _esquemas_kcfg()
    if not esquemas:
        return ("No encuentro esquemas de configuración de KDE en este equipo (carpeta /usr/share/config.kcfg). Busca en internet "
                "(buscar_web, con palabras en inglés) cómo se configura ese ajuste, o usa buscar_clave_en_binarios.")
    encontrados = []
    for e in esquemas:
        clave_n = comandos.normalizar(e["clave"])
        resto_n = comandos.normalizar(f"{e['archivo']} {e['grupo']} {e['etiqueta']}")
        if all(p in clave_n or p in resto_n for p in palabras):
            encontrados.append((-sum(2 if p in clave_n else 1 for p in palabras), e["archivo"], e["clave"], e))
    if not encontrados:
        return (f"Ningún ajuste de los esquemas de KDE encaja con «{consulta}». Prueba con otras palabras en INGLÉS (sinónimos, o menos palabras). Si el programa no instala su esquema, busca los nombres de sus claves dentro de sus "
                "binarios con buscar_clave_en_binarios (programa y palabras), y si tampoco, con buscar_web.")
    candidatos = _candidatos_valor(valor) if valor else set()
    ini, filas, archivos = {}, [], []
    for puntos, _, _, e in sorted(encontrados, key=lambda x: x[:3])[:40]:
        if e["archivo"] and e["archivo"] not in ini:
            ini[e["archivo"]] = _leer_ini(os.path.join(_HOME, ".config", e["archivo"]))
            archivos.append(e["archivo"])
        tuyos = [(g, v) for g, k, v in ini.get(e["archivo"], []) if k == e["clave"]]
        if tuyos:
            efectivo, ahora = tuyos[0][1], "ahora vale " + tuyos[0][1] + " (tu archivo: " + "; ".join(f"{g}={v}" for g, v in tuyos[:3]) + ")"
        elif e["defecto"]:
            efectivo, ahora = e["defecto"], f"ahora vale {e['defecto']} (valor por defecto: no está en tu archivo)"
        elif e.get("calculado"):
            efectivo, ahora = None, "valor por defecto calculado por el programa: no se puede saber leyendo el esquema (míralo en su panel con mirar_pantalla)"
        else:
            efectivo, ahora = None, "sin valor por defecto conocido"
        coincide = bool(candidatos) and efectivo is not None and _mismo_numero(efectivo, candidatos)
        filas.append((0 if coincide else 1, puntos, coincide, e, ahora))
    filas.sort(key=lambda f: (f[0], f[1], f[3]["archivo"], f[3]["clave"]))
    lineas = []
    for _, _, coincide, e, ahora in filas[:12]:
        marca = f"  ← COINCIDE con el valor que dice el usuario ({valor})" if coincide else ""
        lineas.append(f"- {e['archivo'] or '(archivo propio de la app)'} · grupo «{e['grupo']}» · clave {e['clave']} "
                      f"({e['tipo'] or '?'}): {e['etiqueta'][:70]} — {ahora}{marca}")
    cabecera = ""
    if candidatos:
        coinc = [f[3]["clave"] for f in filas if f[2]]
        cabecera = (f"Valen ahora «{valor}»: {', '.join(coinc)}. Si el que ve el usuario no es el que él nombra, díselo y pregúntale cuál quiere cambiar.\n"
                    if coinc else f"Ninguno de estos ajustes vale ahora «{valor}»: el que ve el usuario con ese valor puede tener otro nombre o estar en otra "
                                   "aplicación. Ábrele el panel (kcmshell6) y míralo con mirar_pantalla.\n")
    pie = []
    for a in archivos[:3]:
        grupos = list(dict.fromkeys(g for g, _, _ in ini[a] if g))[:10]
        pie.append(f"Grupos que ya tienes en ~/.config/{a}: " + (", ".join(grupos) if grupos else "(el archivo está vacío o no existe)"))
    texto = ("Ajustes de KDE que encajan (sacados de los esquemas instalados, no inventados):\n" + cabecera + "\n".join(lineas) + "\n"
             + "\n".join(pie) + "\nPara escribirla: `kwriteconfig6 --file ARCHIVO --group GRUPO --key CLAVE VALOR`; si el archivo usa grupos padre "
             "(perfiles como AC o Battery), repite cada nivel con --group, de fuera hacia dentro. Después comprueba el valor y que el programa "
             "lo aplica (mirar_pantalla sobre su panel).")
    return texto[:3600]



_LANZAMIENTO = re.compile(r"^\s*(?:abrir|abre|abriendo|lanzar|lanza|iniciar|inicia|arrancar|arranca)\b", re.I)
_LANZAMIENTO_EN = re.compile(r"^\s*(?:open|opening|launch|launching|start|starting|run|running)\b", re.I)
_LANZAMIENTO_POR_IDIOMA = {"es": _LANZAMIENTO, "en": _LANZAMIENTO_EN}          # cómo empieza el «motivo» de una orden de abrir un programa, por idioma


def _motivo_es_abrir(motivo):
    """¿El «motivo» del comando es abrir un programa? Esos siguen en marcha hasta que el usuario los cierra, y eso no es «terminar una tarea»."""
    return bool(IDI.segun(_LANZAMIENTO_POR_IDIOMA).match(_sin_acentos(str(motivo or "")).strip()))
