"""B4. MangoHud, Proton y opciones de lanzamiento de Steam, por voz.

 · MangoHud: es un archivo de texto (~/.config/MangoHud/MangoHud.conf). Se edita al momento, pero SIEMPRE con copia previa
   (se puede volver atrás con accion=deshacer).
 · Steam (Proton de cada juego, Proton por defecto y opciones de lanzamiento): viven en dos archivos de Valve (config.vdf y
   localconfig.vdf) que Steam reescribe entera al cerrarse. Por eso solo se tocan con Steam CERRADO, con copia previa y con la
   confirmación del usuario: aquí se PLANIFICA (se lee, se valida y se describe lo que pasará) y la acción interna que devuelve
   `planificar_steam` es lo que ejecuta herramientas.Ejecutor.preparar_accion() cuando el usuario dice que sí.

Nada de esto lleva «recetas» escritas a mano para un juego concreto: solo el formato de los archivos y las protecciones."""
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from lina.nucleo import plataforma as PL
from lina.nucleo import rutas as RUT

try:
    from lina.modulos import sistema as SIS
except ImportError:                                  # sin sistema.py no hay ni búsqueda aproximada ni lectura de procesos
    SIS = None
try:
    from lina.modulos import juegos as JUE
except ImportError:
    JUE = None

_HOME = Path.home()
DIR_COPIAS = RUT.DATOS / "copias_juego"
RUTA_MANGOHUD = _HOME / ".config/MangoHud/MangoHud.conf"
RAICES = None                                        # en las pruebas: lista de carpetas de Steam
COPIAS_A_GUARDAR = 20


def _ej(argv, timeout=8):
    if SIS is not None:
        return SIS.ej(argv, timeout=timeout)
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, errors="replace")
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)


def _puntos(consulta, *textos):
    if SIS is not None:
        return SIS.puntos(consulta, *textos)
    q = re.sub(r"\W+", " ", str(consulta).lower()).strip()
    return max((100 if q == re.sub(r"\W+", " ", str(t).lower()).strip() else (86 if q and q in str(t).lower() else 0)) for t in textos) if textos else 0


def _norm(s):
    return SIS._norm(s) if SIS is not None else re.sub(r"\W+", " ", str(s).lower()).strip()


# ======================================================================================================================
#  COPIAS PREVIAS
# ======================================================================================================================
def hacer_copia(ruta):
    """Copia el archivo antes de tocarlo. Devuelve la ruta de la copia (o None si el archivo aún no existe)."""
    ruta = Path(ruta)
    if not ruta.is_file():
        return None
    DIR_COPIAS.mkdir(parents=True, exist_ok=True)
    while True:                                                     # el nombre ordena por hora (con microsegundos): la última copia es la mayor
        ahora = time.time()
        marca = time.strftime("%Y%m%d-%H%M%S", time.localtime(ahora)) + f"-{int((ahora % 1) * 1e6):06d}"
        copia = DIR_COPIAS / f"{marca}__{ruta.name}"
        if not copia.exists():
            break
        time.sleep(0.001)
    shutil.copy2(ruta, copia)
    (DIR_COPIAS / (copia.name + ".origen")).write_text(str(ruta), encoding="utf-8")
    antiguas = sorted(DIR_COPIAS.glob(f"*__{ruta.name}"))
    for vieja in antiguas[:-COPIAS_A_GUARDAR]:
        for x in (vieja, DIR_COPIAS / (vieja.name + ".origen")):
            try:
                x.unlink()
            except OSError:
                pass
    return copia


def ultima_copia(ruta):
    """La copia más reciente de ese archivo (hecha desde esa misma ruta), o None."""
    ruta = Path(ruta)
    if not DIR_COPIAS.is_dir():
        return None
    for c in sorted(DIR_COPIAS.glob(f"*__{ruta.name}"), reverse=True):
        try:
            if (DIR_COPIAS / (c.name + ".origen")).read_text(encoding="utf-8").strip() == str(ruta):
                return c
        except OSError:
            continue
    return None


def _escribir_atomico(ruta, texto):
    ruta = Path(ruta)
    tmp = ruta.with_name(ruta.name + ".lina.tmp")
    tmp.write_text(texto, encoding="utf-8")
    if ruta.exists():
        shutil.copymode(ruta, tmp)
    os.replace(tmp, ruta)


# ======================================================================================================================
#  MANGOHUD
# ======================================================================================================================
OPCIONES_CONOCIDAS = set("""
fps frametime frame_timing frame_count fps_only fps_color_change fps_color fps_value fps_limit fps_limit_method vsync gl_vsync
cpu_stats cpu_temp cpu_power cpu_mhz cpu_load_change cpu_load_value cpu_load_color cpu_color core_load core_load_change core_bars
gpu_stats gpu_temp gpu_junction_temp gpu_mem_temp gpu_core_clock gpu_mem_clock gpu_power gpu_power_limit gpu_fan gpu_voltage gpu_name
gpu_load_change gpu_load_value gpu_load_color gpu_color gpu_text gpu_list gpu_efficiency
vram ram swap procmem procmem_shared procmem_virt io_read io_write io_stats
engine_version engine_short_names vulkan_driver wine winesync resolution display_server arch time time_no_label time_format
gamemode vkbasalt hdr refresh_rate fsr hide_fsr_sharpness fcat show_fps_limit throttling_status throttling_status_graph
battery battery_icon battery_watt battery_time device_battery device_battery_icon media_player media_player_name media_player_format
position font_size font_size_text font_scale font_scale_media_player font_file font_file_text text_outline text_outline_color text_outline_thickness
round_corners background_alpha background_color alpha text_color width height table_columns offset_x offset_y horizontal horizontal_stretch
hud_no_margin hud_compact legacy_layout no_display no_small_font cellpadding_y dynamic_frametime
toggle_hud toggle_hud_position toggle_preset toggle_fps_limit toggle_logging reload_cfg upload_log
output_folder output_file log_duration autostart_log log_interval log_versioning permit_upload
preset full version custom_text custom_text_center blacklist af bicubic trilinear retro picmip mip_bias
wine_color engine_color media_player_color network network_color frametime_color battery_color ram_color vram_color io_color
text_color_alt histogram gamepad_battery gamepad_battery_icon exec_name
""".split())
OPCIONES_PROHIBIDAS = {"exec": "«exec» ejecuta un programa cada vez que se dibuja el HUD: no la pongo por voz (edítala tú a mano si de verdad la quieres)"}
_CLAVE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_VALOR = re.compile(r"^[A-Za-z0-9_+.,:@%/ #~-]{0,120}$")
PRESETS = {
    "limpio": ["no_display"],
    "fps": ["fps", "position=top-left", "font_size=24", "background_alpha=0.3", "round_corners=8"],
    "rendimiento": ["fps", "frametime", "frame_timing", "cpu_stats", "cpu_temp", "gpu_stats", "gpu_temp", "gpu_power", "vram", "ram",
                    "position=top-left", "font_size=22", "background_alpha=0.35", "round_corners=8"],
    "completo": ["fps", "frametime", "frame_timing", "cpu_stats", "cpu_temp", "cpu_mhz", "gpu_stats", "gpu_temp", "gpu_core_clock",
                 "gpu_mem_clock", "gpu_power", "gpu_fan", "vram", "ram", "swap", "procmem", "io_read", "io_write", "engine_version",
                 "vulkan_driver", "gpu_name", "wine", "resolution", "gamemode", "time",
                 "position=top-left", "font_size=20", "background_alpha=0.35", "round_corners=8"],
}
_ACTIVA = re.compile(r"^\s*([a-z][a-z0-9_]*)\s*(?:=\s*(.*?))?\s*$")
_COMENTADA = re.compile(r"^\s*#\s*([a-z][a-z0-9_]*)\s*(?:=\s*(.*?))?\s*$")


def _parsear_opciones(args):
    """['fps', 'font_size=30'] (o una sola cadena «fps, font_size=30») → [(clave, valor|None)], error."""
    if isinstance(args, str):
        args = [x for x in re.split(r"[,\n]", args)]
    res = []
    for bruto in args or []:
        bruto = str(bruto).strip()
        if not bruto:
            continue
        clave, _, valor = bruto.partition("=")
        clave, valor = clave.strip().lower(), valor.strip()
        if not _CLAVE.match(clave):
            return None, f"«{bruto}» no parece una opción de MangoHud (letras, números y _)."
        if clave in OPCIONES_PROHIBIDAS:
            return None, OPCIONES_PROHIBIDAS[clave]
        if not _VALOR.match(valor):
            return None, f"El valor de «{clave}» tiene caracteres que no admito."
        res.append((clave, valor if "=" in bruto else None))
    return res, None


def _poner_opcion(lineas, clave, valor):
    nueva = clave if valor is None else f"{clave}={valor}"
    activas = [i for i, l in enumerate(lineas) if (m := _ACTIVA.match(l)) and m.group(1) == clave and not l.lstrip().startswith("#")]
    if activas:
        lineas[activas[0]] = nueva
        for i in reversed(activas[1:]):
            del lineas[i]
        return
    for i, l in enumerate(lineas):
        m = _COMENTADA.match(l)
        if m and m.group(1) == clave and clave in OPCIONES_CONOCIDAS:
            lineas[i] = nueva
            return
    lineas.append(nueva)


def _quitar_opcion(lineas, clave):
    antes = len(lineas)
    lineas[:] = [l for l in lineas if not ((m := _ACTIVA.match(l)) and m.group(1) == clave and not l.lstrip().startswith("#"))]
    return antes - len(lineas)


def _leer_mangohud():
    try:
        return RUTA_MANGOHUD.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None


def _activas(lineas):
    return [l.strip() for l in (lineas or []) if l.strip() and not l.lstrip().startswith("#")]


def mangohud(args):
    """Todo lo de MangoHud. Devuelve un texto para la IA. Acciones: ver, activar, quitar, preset, borrar, deshacer."""
    accion = str(args.get("accion", "ver")).strip().lower()
    if accion not in {"ver", "activar", "quitar", "preset", "borrar", "deshacer"}:
        return "Acciones de MangoHud: ver, activar, quitar, preset, borrar, deshacer."
    instalado = shutil.which("mangohud") is not None
    aviso = "" if instalado else f"\nAVISO: no encuentro el programa mangohud instalado ({PL.manual(['mangohud'], PL.familia_actual())})."
    lineas = _leer_mangohud()
    nota_uso = ("\nSe aplica la próxima vez que se abra el juego, y solo en los juegos que lo usen: en Steam, con la opción de lanzamiento "
                "«mangohud %command%» (herramienta opciones_lanzamiento).")
    if accion == "ver":
        if lineas is None:
            return f"No hay archivo de MangoHud ({RUTA_MANGOHUD}): MangoHud usa sus valores por defecto.{aviso}"
        return f"{RUTA_MANGOHUD}:\n" + ("\n".join(_activas(lineas)) or "(vacío)") + aviso
    if accion == "deshacer":
        copia = ultima_copia(RUTA_MANGOHUD)
        if not copia:
            return "No hay ninguna copia anterior de la configuración de MangoHud."
        actual = hacer_copia(RUTA_MANGOHUD)                       # lo de ahora también se guarda, por si se quiere volver
        _escribir_atomico(RUTA_MANGOHUD, copia.read_text(encoding="utf-8"))
        return f"Restaurada la configuración de MangoHud desde la copia {copia.name}." + (f" (La de antes quedó en {actual.name}.)" if actual else "")
    RUTA_MANGOHUD.parent.mkdir(parents=True, exist_ok=True)
    antes = list(lineas) if lineas is not None else None
    trabajo = list(lineas) if lineas is not None else ["# Configuración de MangoHud (editada por el asistente)"]
    resumen, opciones = [], []
    if accion == "borrar":
        if lineas is None:
            return "No hay archivo de MangoHud que borrar."
        copia = hacer_copia(RUTA_MANGOHUD)
        RUTA_MANGOHUD.unlink()
        return f"Quitada la configuración de MangoHud (copia en {copia.name}); vuelve a sus valores por defecto."
    if accion == "preset":
        nombre = _norm(args.get("preset") or args.get("opciones") or "")
        if isinstance(args.get("opciones"), list):
            nombre = _norm(" ".join(map(str, args["opciones"])))
        elegido = next((k for k in PRESETS if k == nombre), None)
        if not elegido:
            return "Presets: " + ", ".join(PRESETS) + ". Para algo distinto usa activar con las opciones concretas."
        trabajo = ["# Configuración de MangoHud (preset «%s» puesto por el asistente)" % elegido] + PRESETS[elegido]
        resumen.append(f"preset «{elegido}»")
        avisos = []
    else:
        opciones, error = _parsear_opciones(args.get("opciones"))
        if error:
            return error
        if not opciones:
            return "Di qué opciones (por ejemplo fps, gpu_stats, font_size=30, position=top-right, fps_limit=144)."
        avisos = [c for c, _ in opciones if c not in OPCIONES_CONOCIDAS]
        for clave, valor in opciones:
            if accion == "activar":
                _poner_opcion(trabajo, clave, valor)
                resumen.append(clave if valor is None else f"{clave}={valor}")
            else:
                quitadas = _quitar_opcion(trabajo, clave)
                resumen.append(f"{clave} {'quitada' if quitadas else '(no estaba)'}")
    if trabajo == antes:
        return "Ya estaba así; no he cambiado nada." + aviso
    copia = hacer_copia(RUTA_MANGOHUD)
    try:
        _escribir_atomico(RUTA_MANGOHUD, "\n".join(trabajo) + "\n")
    except OSError as e:
        return f"No he podido escribir {RUTA_MANGOHUD}: {e}"
    despues = _leer_mangohud() or []
    activas_ahora = {(_ACTIVA.match(l).group(1)) for l in _activas(despues) if _ACTIVA.match(l)}
    comprobado = accion == "activar" and all(c in activas_ahora for c, _ in opciones)
    return (f"Hecho ({', '.join(resumen)}). " + (f"Copia anterior: {copia.name}. " if copia else "Archivo nuevo. ")
            + ("COMPROBADO: leído de nuevo, está en el archivo.\n" if comprobado else "")
            + "Ahora el archivo tiene:\n" + "\n".join(_activas(despues))
            + (f"\nAVISO: no conozco {', '.join(avisos)} como opción de MangoHud (si no existe, la ignorará)." if avisos else "")
            + nota_uso + aviso)


# ======================================================================================================================
#  ARCHIVOS VDF DE STEAM (formato clave/valor de Valve)
# ======================================================================================================================
def vdf_parse(texto):
    pos, n = 0, len(texto)

    def saltar():
        nonlocal pos
        while pos < n:
            c = texto[pos]
            if c in " \t\r\n\ufeff":
                pos += 1
            elif texto.startswith("//", pos):
                while pos < n and texto[pos] != "\n":
                    pos += 1
            else:
                break

    def token():
        nonlocal pos
        saltar()
        if pos >= n:
            return None
        c = texto[pos]
        if c in "{}":
            pos += 1
            return (c, None)
        if c == '"':
            pos += 1
            salida = []
            while pos < n:
                c = texto[pos]
                if c == "\\" and pos + 1 < n:
                    e = texto[pos + 1]
                    salida.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(e, "\\" + e))
                    pos += 2
                elif c == '"':
                    pos += 1
                    return ("s", "".join(salida))
                else:
                    salida.append(c)
                    pos += 1
            raise ValueError("comillas sin cerrar")
        ini = pos
        while pos < n and texto[pos] not in " \t\r\n{}\"":
            pos += 1
        return ("s", texto[ini:pos])

    def objeto(con_llave):
        d = {}
        while True:
            t = token()
            if t is None:
                if con_llave:
                    raise ValueError("falta una llave de cierre")
                return d
            if t[0] == "}":
                if not con_llave:
                    raise ValueError("llave de cierre de más")
                return d
            if t[0] == "{":
                raise ValueError("llave de apertura inesperada")
            v = token()
            if v is None or v[0] == "}":
                raise ValueError("falta un valor")
            valor = objeto(True) if v[0] == "{" else v[1]
            if t[1] in d:
                raise ValueError(f"clave repetida «{t[1]}»")
            d[t[1]] = valor

    return objeto(False)


def _esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def vdf_dump(d, nivel=0):
    t = "\t" * nivel
    partes = []
    for k, v in d.items():
        if isinstance(v, dict):
            partes.append(f'{t}"{_esc(k)}"\n{t}{{\n{vdf_dump(v, nivel + 1)}{t}}}\n')
        else:
            partes.append(f'{t}"{_esc(k)}"\t\t"{_esc(str(v))}"\n')
    return "".join(partes)


def _clave_real(d, clave):
    for k in d:
        if k.lower() == clave.lower():
            return k
    return None


def _bajar(d, ruta, crear=False):
    """d['Software']['Valve']... sin importar mayúsculas. Devuelve el diccionario o None."""
    for paso in ruta:
        k = _clave_real(d, paso)
        if k is None or not isinstance(d[k], dict):
            if not crear:
                return None
            k = paso
            d[k] = {}
        d = d[k]
    return d


# ======================================================================================================================
#  STEAM: dónde están las cosas y cómo está
# ======================================================================================================================
def raiz_steam():
    for r in (RAICES if RAICES is not None else (JUE._raices_steam() if JUE else [])):
        r = Path(r)
        if (r / "config" / "config.vdf").is_file():
            return r.resolve()
    return None


def ruta_config(raiz=None):
    raiz = raiz or raiz_steam()
    return raiz / "config" / "config.vdf" if raiz else None


def ruta_localconfig(raiz=None):
    raiz = raiz or raiz_steam()
    if not raiz:
        return None
    candidatos = [p for p in (raiz / "userdata").glob("*/config/localconfig.vdf") if p.parent.parent.name.isdigit() and p.parent.parent.name != "0"]
    return max(candidatos, key=lambda p: p.stat().st_mtime) if candidatos else None


def steam_abierto():
    for nombre in ("steam", "steamwebhelper"):
        rc, _ = _ej(["pgrep", "-x", nombre])
        if rc == 0:
            return True
    return False


def juego_en_marcha():
    rc, out = _ej(["pgrep", "-f", "SteamLaunch|steamapps/common|reaper SteamLaunch"])
    return rc == 0 and bool(out.strip())


def _es_flatpak(raiz):
    return ".var/app/com.valvesoftware.Steam" in str(raiz)


def cerrar_steam(raiz=None):
    """Pide a Steam que se cierre (nunca lo mata) y espera. (ok, texto)."""
    argv = ["flatpak", "run", "com.valvesoftware.Steam", "-shutdown"] if _es_flatpak(raiz) else ["steam", "-shutdown"]
    _ej(argv, timeout=15)
    for _ in range(40):
        if not steam_abierto():
            time.sleep(1.0)                                         # que termine de escribir sus archivos
            return True, "Steam cerrado."
        time.sleep(0.75)
    return False, "Steam no se ha cerrado (puede estar actualizando o con un aviso abierto)."


def abrir_steam(raiz=None):
    argv = ["flatpak", "run", "com.valvesoftware.Steam"] if _es_flatpak(raiz) else ["steam"]
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


def juego_de_steam(consulta):
    """(appid, nombre, error). Acepta el número, o un nombre aproximado entre los juegos de Steam instalados."""
    consulta = str(consulta or "").strip()
    if consulta.isdigit():
        nombre = ""
        if JUE:
            nombre = next((j["nombre"] for j in JUE.biblioteca() if j["origen"] == "steam" and j["id"] == consulta), "")
        return consulta, nombre or f"app {consulta}", None
    if not JUE:
        return None, None, "Falta juegos.py."
    steam = [j for j in JUE.biblioteca() if j["origen"] == "steam"]
    hallados = JUE.buscar(consulta, steam)
    if not hallados:
        return None, None, f"No encuentro ningún juego de Steam instalado que se parezca a «{consulta}»."
    return hallados[0][1]["id"], hallados[0][1]["nombre"], None


def _nombre_de_appid(appid):
    if JUE:
        for j in JUE.biblioteca():
            if j["origen"] == "steam" and j["id"] == str(appid):
                return j["nombre"]
    return f"app {appid}"


# ======================================================================================================================
#  OPCIONES DE LANZAMIENTO
# ======================================================================================================================
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PROHIBIDO_EN_OPCIONES = re.compile(r"[;&|<>`\n\r]|\$\(")


def _trocear(texto):
    try:
        return shlex.split(texto), None
    except ValueError as e:
        return None, f"Las comillas de las opciones no cuadran ({e})."


def _partir(tokens):
    """(antes de %command%, después, ¿lleva %command%?). Sin %command%, Steam pone todo como argumentos del juego."""
    if "%command%" in tokens:
        i = tokens.index("%command%")
        return tokens[:i], tokens[i + 1:], True
    return [], list(tokens), False


def _unir(pre, post, con_comando):
    if not pre and not con_comando:
        return " ".join(shlex.quote(x) for x in post)
    return " ".join(shlex.quote(x) for x in [*pre, "%command%", *post])


def validar_opciones(texto):
    """(error | None, avisos). Una opción de lanzamiento se ejecuta con shell cada vez que abres el juego: nada de encadenar órdenes."""
    if len(texto) > 500:
        return "Demasiado larga (más de 500 caracteres).", []
    if _PROHIBIDO_EN_OPCIONES.search(texto):
        return ("Esas opciones llevan caracteres que encadenan o redirigen órdenes (; & | < > ` $( ). "
                "No las pongo por voz: se ejecutarían cada vez que abras el juego."), []
    tokens, error = _trocear(texto)
    if error:
        return error, []
    pre, _, _ = _partir(tokens)
    avisos = []
    for t in pre:
        if _ENV.match(t):
            continue
        if t in {"--", "env"} or t.startswith("-"):
            continue
        base = os.path.basename(t)
        if shutil.which(t) or (os.path.isabs(t) and os.access(t, os.X_OK)):
            continue
        if pre.index(t) > 0 and not _ENV.match(pre[pre.index(t) - 1]) and pre[pre.index(t) - 1] not in {"--", "env"}:
            continue                                                 # un argumento del programa anterior (gamescope -W 2560 ...)
        return f"El programa «{base}» no está instalado ni en el PATH: el juego no arrancaría.", avisos
    return None, avisos


def componer_opciones(actual, accion, valor):
    """(nuevo | None, error). accion: poner (la línea completa), anadir, quitar, borrar."""
    actual = (actual or "").strip()
    valor = (valor or "").strip()
    if accion == "borrar":
        return "", None
    if accion == "poner":
        if not valor:
            return None, "Falta la línea de opciones."
        t, e = _trocear(valor)
        return (None, e) if e else (valor, None)
    tokens, error = _trocear(actual)
    if error:
        return None, error
    pre, post, con = _partir(tokens)
    nuevos, error = _trocear(valor)
    if error or not nuevos:
        return None, error or "Falta qué añadir/quitar."
    if accion == "anadir":
        for i, t in enumerate(nuevos):
            if t == "%command%":
                continue
            if _ENV.match(t):
                var = t.split("=", 1)[0]
                pre = [x for x in pre if not (_ENV.match(x) and x.split("=", 1)[0] == var)]
                lugar = 0
                while lugar < len(pre) and _ENV.match(pre[lugar]):
                    lugar += 1
                pre.insert(lugar, t)
            elif t.startswith(("-", "+")):
                if t not in post:
                    post.append(t)
            else:
                if i + 1 < len(nuevos) and nuevos[i + 1].startswith("-") and nuevos[i + 1] != "--":
                    return None, "Un programa con sus propias opciones (como gamescope -W 2560...) hay que ponerlo con accion=poner y la línea completa."
                if not any(os.path.basename(x) == os.path.basename(t) for x in pre if not _ENV.match(x)):
                    pre.append(t)
        return _unir(pre, post, True), None
    if accion == "quitar":
        for t in nuevos:
            if _ENV.match(t) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t) and any(_ENV.match(x) and x.split("=", 1)[0] == t for x in pre):
                var = t.split("=", 1)[0]
                pre = [x for x in pre if not (_ENV.match(x) and x.split("=", 1)[0] == var)]
            elif t.startswith(("-", "+")):
                post = [x for x in post if x != t]
            else:
                pre = [x for x in pre if os.path.basename(x) != os.path.basename(t) or _ENV.match(x)]
        if not pre and not post:
            return "", None
        return _unir(pre, post, con or bool(pre)), None
    return None, "Acción desconocida."


def leer_opciones(localcfg, appid):
    arbol = vdf_parse(Path(localcfg).read_text(encoding="utf-8", errors="replace"))
    apps = _bajar(arbol, ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps"])
    app = _bajar(apps, [str(appid)]) if apps else None
    if not app:
        return ""
    k = _clave_real(app, "LaunchOptions")
    return app[k] if k else ""


def _juegos_con_opciones(localcfg):
    arbol = vdf_parse(Path(localcfg).read_text(encoding="utf-8", errors="replace"))
    apps = _bajar(arbol, ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps"]) or {}
    res = []
    for appid, app in apps.items():
        if isinstance(app, dict):
            k = _clave_real(app, "LaunchOptions")
            if k and app[k].strip():
                res.append((appid, app[k]))
    return res


# ======================================================================================================================
#  PROTON
# ======================================================================================================================
def _id_oficial(nombre):
    n = nombre.lower()
    if "experimental" in n:
        return "proton_experimental"
    if "hotfix" in n:
        return "proton_hotfix"
    m = re.search(r"proton\s+(\d+)\.(\d+)", n)
    if m:
        return f"proton_{int(m.group(1))}" if int(m.group(1)) >= 7 else f"proton_{m.group(1)}{m.group(2)}"
    return None


def _natural(s):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s.lower())]


def proton_instalados(raiz=None):
    """[{id, nombre, origen}] — los que Steam puede usar. id es lo que se escribe en config.vdf."""
    raiz = raiz or raiz_steam()
    res, vistos = [], set()

    def anadir(i, nombre, origen):
        if i and i not in vistos:
            vistos.add(i)
            res.append({"id": i, "nombre": nombre, "origen": origen})
    if raiz:
        carpetas = [raiz / "compatibilitytools.d", Path("/usr/share/steam/compatibilitytools.d"), Path("/usr/local/share/steam/compatibilitytools.d"),
                    _HOME / ".steam/root/compatibilitytools.d"]
        for c in carpetas:
            if not c.is_dir():
                continue
            for sub in sorted(c.iterdir()):
                vdf = sub / "compatibilitytool.vdf"
                if not vdf.is_file():
                    continue
                try:
                    datos = vdf_parse(vdf.read_text(encoding="utf-8", errors="replace"))
                except ValueError:
                    continue
                herr = _bajar(datos, ["compatibilitytools", "compat_tools"]) or {}
                for ident, info in herr.items():
                    if isinstance(info, dict):
                        anadir(ident, info.get("display_name", ident), "instalado por ti" if str(c).startswith(str(_HOME)) else "del sistema")
        for lib in (JUE._carpetas_steamapps() if JUE else []):
            comun = Path(lib) / "common"
            if comun.is_dir():
                for d in sorted(comun.glob("Proton*")):
                    anadir(_id_oficial(d.name), d.name, "oficial de Valve")
    return res


def mapa_proton(config_vdf):
    """{appid: nombre_interno} de CompatToolMapping ('0' es el predeterminado)."""
    arbol = vdf_parse(Path(config_vdf).read_text(encoding="utf-8", errors="replace"))
    mapa = _bajar(arbol, ["InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping"]) or {}
    return {k: (v.get("name", "") if isinstance(v, dict) else "") for k, v in mapa.items()}


def elegir_proton(consulta, instalados):
    """(herramienta, otras_candidatas, error)"""
    q = str(consulta or "").strip()
    if not q:
        return None, [], "Di qué Proton."
    for h in instalados:
        if q == h["id"]:
            return h, [], None
    puntuados = sorted(((max(_puntos(q, h["nombre"]), _puntos(q, h["id"])), h) for h in instalados), key=lambda x: -x[0])
    puntuados = [(p, h) for p, h in puntuados if p >= 70]
    if not puntuados:
        return None, [], f"No tengo instalado ningún Proton que se parezca a «{q}». Instalados: " + ", ".join(h["nombre"] for h in instalados) + "."
    tope = puntuados[0][0]
    empatados = sorted((h for p, h in puntuados if p >= tope - 4), key=lambda h: _natural(h["nombre"]), reverse=True)
    return empatados[0], empatados[1:], None


# ======================================================================================================================
#  STEAM: PLANES (se leen y validan ahora; se aplican cuando el usuario dice que sí)
# ======================================================================================================================
def _aplicar_vdf(ruta, transformar, comprobar, etiqueta, raiz):
    """Lo que se ejecuta tras la confirmación. transformar(arbol) cambia el árbol; comprobar(arbol) devuelve un texto con lo leído."""
    cerramos = False
    if steam_abierto():
        if juego_en_marcha():
            return "No he hecho nada: hay un juego en marcha y cerrar Steam lo cerraría. Ciérralo tú y vuelve a pedírmelo."
        ok, texto = cerrar_steam(raiz)
        if not ok:
            return f"No he hecho nada: {texto}"
        cerramos = True
    try:
        original = Path(ruta).read_text(encoding="utf-8", errors="replace")
        arbol = vdf_parse(original)
        if vdf_parse(vdf_dump(arbol)) != arbol:
            return f"No he hecho nada: no consigo reescribir {Path(ruta).name} con total fidelidad."
    except (OSError, ValueError) as e:
        return f"No he hecho nada: no puedo leer {Path(ruta).name} ({e})."
    copia = hacer_copia(ruta)
    try:
        transformar(arbol)
        nuevo = vdf_dump(arbol)
        if vdf_parse(nuevo) != arbol:
            raise ValueError("el resultado no se vuelve a leer igual")
        _escribir_atomico(ruta, nuevo)
        leido = comprobar(vdf_parse(Path(ruta).read_text(encoding="utf-8", errors="replace")))
    except (OSError, ValueError) as e:
        if copia:
            shutil.copy2(copia, ruta)
        return f"Algo falló ({e}); he dejado {Path(ruta).name} como estaba (copia {copia.name if copia else '-'})."
    reabierto = ""
    if cerramos:
        reabierto = " Steam vuelto a abrir." if abrir_steam(raiz) else " (No he podido volver a abrir Steam: ábrelo tú.)"
    return (f"Hecho: {etiqueta}. COMPROBADO leyendo el archivo de nuevo: {leido}. Copia anterior: {copia.name if copia else '(no había)'}."
            f"{' Steam estaba abierto: lo cerré para escribir.' if cerramos else ''}{reabierto}")


def _preparar(descripcion_base, ruta, transformar, comprobar, etiqueta, raiz):
    abierto = steam_abierto()
    if abierto and juego_en_marcha():
        return {"error": "Hay un juego de Steam en marcha: para tocar estos archivos hay que cerrar Steam y eso lo cerraría. Dile al usuario que lo cierre y vuelva a pedirlo."}
    cierre = " Steam está abierto: lo cerraré antes de escribir y lo volveré a abrir (si no, Steam machaca el cambio al salir)." if abierto else ""
    return {"descripcion": f"{descripcion_base}. Haré copia de {Path(ruta).name} antes.{cierre}",
            "aplicar": lambda: _aplicar_vdf(ruta, transformar, comprobar, etiqueta, raiz),
            "motivo": etiqueta}


def _planificar_deshacer(ruta, raiz, que):
    copia = ultima_copia(ruta)
    if not copia:
        return {"error": f"No hay ninguna copia anterior de {Path(ruta).name} hecha por mí."}
    texto_copia = copia.read_text(encoding="utf-8", errors="replace")
    try:
        copia_arbol = vdf_parse(texto_copia)
    except ValueError:
        return {"error": "La copia no se puede leer; no la restauro."}

    def transformar(arbol):
        arbol.clear()
        arbol.update(copia_arbol)
    return _preparar(f"Volver {que} a como estaba en la copia {copia.name}", ruta, transformar, lambda a: "restaurada", f"restaurar {Path(ruta).name}", raiz)


def planificar_opciones_lanzamiento(args):
    accion = str(args.get("accion", "ver")).strip().lower()
    if accion not in {"ver", "poner", "anadir", "añadir", "quitar", "borrar", "deshacer"}:
        return {"error": "Acciones: ver, poner, anadir, quitar, borrar, deshacer."}
    accion = "anadir" if accion == "añadir" else accion
    raiz = raiz_steam()
    ruta = ruta_localconfig(raiz) if raiz else None
    if not ruta:
        return {"error": "No encuentro los archivos de usuario de Steam (localconfig.vdf). ¿Steam instalado y abierto alguna vez?"}
    estado = "abierto" if steam_abierto() else "cerrado"
    if accion == "deshacer":
        return _planificar_deshacer(ruta, raiz, "las opciones de lanzamiento")
    juego = str(args.get("juego", "")).strip()
    if accion == "ver" and not juego:
        try:
            con = _juegos_con_opciones(ruta)
        except (OSError, ValueError) as e:
            return {"error": f"No puedo leer localconfig.vdf: {e}"}
        return {"texto": f"Steam está {estado}. Juegos con opciones de lanzamiento:\n"
                + ("\n".join(f"- {_nombre_de_appid(a)} ({a}): {o}" for a, o in con) or "(ninguno)")}
    appid, nombre, error = juego_de_steam(juego)
    if error:
        return {"error": error}
    try:
        actual = leer_opciones(ruta, appid)
    except (OSError, ValueError) as e:
        return {"error": f"No puedo leer localconfig.vdf: {e}"}
    if accion == "ver":
        return {"texto": f"{nombre}: opciones de lanzamiento «{actual}»" if actual else f"{nombre}: sin opciones de lanzamiento."}
    nuevo, error = componer_opciones(actual, accion, args.get("valor", ""))
    if error:
        return {"error": error}
    if nuevo:
        error, _ = validar_opciones(nuevo)
        if error:
            return {"error": error}
    if nuevo == actual.strip():
        return {"texto": f"{nombre} ya tiene esas opciones: «{actual}». No hay nada que cambiar."}

    def transformar(arbol):
        app = _bajar(arbol, ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps", str(appid)], crear=True)
        k = _clave_real(app, "LaunchOptions") or "LaunchOptions"
        if nuevo:
            app[k] = nuevo
        else:
            app.pop(k, None)

    def comprobar(arbol):
        app = _bajar(arbol, ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps", str(appid)]) or {}
        k = _clave_real(app, "LaunchOptions")
        leido = app[k] if k else ""
        if leido != nuevo:
            raise ValueError(f"se esperaba «{nuevo}» y se lee «{leido}»")
        return f"«{leido}»" if leido else "sin opciones"
    return _preparar(f"Cambiar las opciones de lanzamiento de «{nombre}»: de «{actual}» a «{nuevo}»", ruta, transformar, comprobar,
                     f"opciones de lanzamiento de {nombre}: {nuevo or '(vacías)'}", raiz)


def planificar_proton(args):
    accion = str(args.get("accion", "listar")).strip().lower()
    if accion not in {"listar", "ver", "poner", "quitar", "deshacer"}:
        return {"error": "Acciones: listar, ver, poner, quitar, deshacer."}
    raiz = raiz_steam()
    ruta = ruta_config(raiz) if raiz else None
    if not ruta:
        return {"error": "No encuentro la configuración de Steam (config.vdf)."}
    estado = "abierto" if steam_abierto() else "cerrado"
    try:
        mapa = mapa_proton(ruta)
    except (OSError, ValueError) as e:
        return {"error": f"No puedo leer config.vdf: {e}"}
    instalados = proton_instalados(raiz)
    nombre_de = {h["id"]: h["nombre"] for h in instalados}
    legible = lambda i: nombre_de.get(i, i) if i else "(ninguno)"
    if accion == "deshacer":
        return _planificar_deshacer(ruta, raiz, "la elección de Proton")
    if accion == "listar":
        otros = [(a, i) for a, i in mapa.items() if a != "0"]
        return {"texto": f"Steam está {estado}. Proton instalados:\n" + ("\n".join(f"- {h['nombre']} ({h['origen']}; id {h['id']})" for h in instalados) or "(ninguno)")
                + f"\nPredeterminado de Steam: {legible(mapa.get('0', ''))}\nElegido para juegos concretos:\n"
                + ("\n".join(f"- {_nombre_de_appid(a)}: {legible(i)}" for a, i in otros[:40]) or "(ninguno)")}
    juego = str(args.get("juego", "")).strip()
    global_ = _norm(juego) in {"todos", "global", "predeterminado", "por defecto", "defecto", "todo", "general", "0"}
    if accion == "ver" and not juego:
        global_ = True
    if global_:
        appid, nombre = "0", "todos los juegos (predeterminado de Steam)"
    else:
        if not juego:
            return {"error": "Di para qué juego, o «todos» para el predeterminado."}
        appid, nombre, error = juego_de_steam(juego)
        if error:
            return {"error": error}
    actual = mapa.get(appid, "")
    if accion == "ver":
        return {"texto": f"{nombre}: " + (f"Proton «{legible(actual)}»." if actual else
                                             f"sin elección propia; usa el predeterminado de Steam ({legible(mapa.get('0', ''))}) o se ejecuta nativo si es de Linux.")}
    if accion == "quitar":
        if not actual:
            return {"texto": f"{nombre} no tenía Proton elegido; no hay nada que quitar."}

        def transformar_q(arbol):
            m = _bajar(arbol, ["InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping"]) or {}
            k = _clave_real(m, appid)
            if k:
                del m[k]

        def comprobar_q(arbol):
            m = _bajar(arbol, ["InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping"]) or {}
            if _clave_real(m, appid):
                raise ValueError("sigue en el archivo")
            return "ya no hay elección propia"
        return _preparar(f"Quitar la elección de Proton de «{nombre}» (era «{legible(actual)}»)", ruta, transformar_q, comprobar_q,
                         f"quitar el Proton de {nombre}", raiz)
    herramienta, otras, error = elegir_proton(args.get("valor", ""), instalados)
    if error:
        return {"error": error}
    if actual == herramienta["id"]:
        return {"texto": f"{nombre} ya usa «{herramienta['nombre']}»."}

    def transformar(arbol):
        m = _bajar(arbol, ["InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping"], crear=True)
        k = _clave_real(m, appid) or appid
        if not isinstance(m.get(k), dict):
            m[k] = {"name": herramienta["id"], "config": "", "priority": "75" if appid == "0" else "250"}
        else:
            m[k]["name"] = herramienta["id"]

    def comprobar(arbol):
        m = _bajar(arbol, ["InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping"]) or {}
        k = _clave_real(m, appid)
        leido = m[k].get("name") if k and isinstance(m[k], dict) else None
        if leido != herramienta["id"]:
            raise ValueError(f"se esperaba {herramienta['id']} y se lee {leido}")
        return f"{nombre} usa «{herramienta['nombre']}»"
    extra = f" (También encajaban: {', '.join(h['nombre'] for h in otras[:4])}; he elegido la más reciente.)" if otras else ""
    return _preparar(f"Poner Proton «{herramienta['nombre']}» en «{nombre}» (antes: {legible(actual) if actual else 'predeterminado'}){extra}", ruta, transformar, comprobar,
                     f"Proton de {nombre}: {herramienta['nombre']}", raiz)


def planificar_steam(nombre, args):
    try:
        if nombre == "opciones_lanzamiento":
            return planificar_opciones_lanzamiento(args or {})
        if nombre == "proton":
            return planificar_proton(args or {})
    except Exception as e:                                          # un fallo aquí no debe tumbar el asistente
        return {"error": f"Fallo interno en {nombre}: {e!r}. No he tocado nada."}
    return {"error": f"Herramienta desconocida: {nombre}."}


# ======================================================================================================================
#  Protección general: estos archivos no se tocan con comandos sueltos
# ======================================================================================================================
_ARCHIVOS_STEAM = re.compile(r"(localconfig|sharedconfig|config|libraryfolders|loginusers)\.vdf|/Steam/userdata/|compatibilitytools\.d", re.I)


def motivo_critico_texto(comando):
    """Para clasificar(): cualquier comando que NO sea de lectura y nombre estos archivos pide confirmación."""
    if _ARCHIVOS_STEAM.search(comando):
        return ("toca archivos de configuración de Steam (Proton, opciones de lanzamiento...): solo se cambian con Steam cerrado y con copia; "
                "usa las herramientas proton / opciones_lanzamiento")
    return None
