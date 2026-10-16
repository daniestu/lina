"""A5 · Presupuesto de Gemini: la clave gratuita y la de pago, lo gastado en el mes, el tope y los avisos.

Aquí no se habla con Gemini: solo se lleva la cuenta y se decide QUÉ clave toca. Lo ajustable (tope, tipo de cambio, precios)
está en config.toml ([gasto]; los precios, en presupuesto.txt). Lo gastado se guarda en ~/.local/share/lina/gasto.json (solo legible por ti, y la IA no puede tocarlo).

Reglas:
  - Lo rápido va con la clave gratuita; lo «a fondo» va con la de pago; si una falla, se prueba con la otra.
  - Al llegar al tope del mes, la clave de pago deja de usarse sola (queda la gratuita).
  - Solo TÚ puedes subir el tope: por voz («sigue con el de pago hasta 15 euros»), nunca la IA.
  - La contabilidad es una ESTIMACIÓN con la tabla de precios. El tope DURO de verdad es el prepago de Google (sin recarga automática).
"""
import json
import math
import os
import re
import subprocess
import threading
import time

from lina.nucleo import ajustes as AJ
from lina.nucleo import comandos
from lina.nucleo import rutas as RUT

ARCHIVO = RUT.editable("presupuesto.txt")
ARCHIVO_GASTO = RUT.DATOS / "gasto.json"
TOPE_MAXIMO_POR_VOZ = 100            # por voz no se sube el tope de más de esto (euros): una cifra mal oída no puede costar mucho

TOPE_EUR = 10.0
EUR_POR_USD = 0.92                    # conservador (si el dólar vale menos, la cuenta sale algo más alta que la real)
AVISOS_PORCENTAJE = (50, 80, 100)
_FLASH_38 = [(None, 0.75, 3.75, 0.075), ("2027-01-01", 1.50, 7.50, 0.15)]        # Google lo sube el 1 de enero de 2027
PRECIOS_DEFECTO = {                  # dólares por millón de tokens: (desde, entrada, salida —con el razonamiento—, entrada en caché)
    "gemini-3.8-flash": _FLASH_38, "gemini-3.7-flash": _FLASH_38, "gemini-3.6-flash": _FLASH_38,
    "gemini-3.5-flash": [(None, 1.50, 9.00, 0.15)], "gemini-3.5-flash-lite": [(None, 0.30, 2.50, 0.03)],
    "gemini-3.1-flash-lite": [(None, 0.25, 1.50, 0.025)], "gemini-3-flash-preview": [(None, 0.50, 3.00, 0.05)],
    "gemini-3.1-pro-preview": [(None, 2.00, 12.00, 0.20)],
    "gemini-2.5-flash": [(None, 0.30, 2.50, 0.03)], "gemini-2.5-pro": [(None, 1.25, 10.00, 0.125)],
    "gemini-flash-latest": _FLASH_38, "gemini-flash-lite-latest": [(None, 0.30, 2.50, 0.03)],
}

_lock = threading.RLock()
_claves = {"gratis": "", "pago": ""}
_avisos_pendientes: list = []
_cache_conf = {"marca": "x", "datos": None}
_precio_desconocido_avisado: set = set()


def log(mensaje):
    print(f"[{time.strftime('%H:%M:%S')}] {mensaje}", flush=True)


# ======================= las dos claves =======================
def configurar_claves(gratis, pago):
    """Las dos claves (cadenas). Si son la misma o la de pago está vacía, solo hay una."""
    gratis, pago = (gratis or "").strip(), (pago or "").strip()
    _claves["gratis"], _claves["pago"] = gratis, ("" if pago == gratis else pago)


def hay_clave_de_pago():
    return bool(_claves["pago"])


def una_sola_clave():
    return not _claves["pago"]


def nombre_de(clave):
    """«pago» o «gratis», para saber a quién apuntar el gasto."""
    return "pago" if clave and clave == _claves["pago"] else "gratis"


def pago_disponible():
    """¿Se puede usar la clave de pago ahora? Hay clave y no se ha llegado al tope de este mes."""
    if not _claves["pago"]:
        return False
    with _lock:
        d = _cargar()
        return _gasto_eur(d) < _tope_eur(d)


def claves_para(modo):
    """Las claves en el orden en que se prueban. «profundo»: primero la de pago; lo demás («rapido», «mini»): primero la gratuita.
    La de pago solo entra si hay saldo de tope este mes."""
    pago = _claves["pago"] if pago_disponible() else ""
    orden = [pago, _claves["gratis"]] if modo == "profundo" else [_claves["gratis"], pago]
    return [c for c in dict.fromkeys(orden) if c]


# ======================= lo ajustable: presupuesto.txt =======================
def _parsear_precio(valor):
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", valor)]
    return tuple(nums) if len(nums) in (2, 3) else None


def configuracion():
    """{'tope_eur', 'eur_por_usd', 'avisos', 'precios': {modelo: [(desde, entrada, salida, cache)]}} de presupuesto.txt (con valores de
    fábrica si falta o está mal). Se vuelve a leer solo si el archivo cambia."""
    try:
        marca = ARCHIVO.stat().st_mtime_ns
    except OSError:
        marca = None
    aj = AJ.actuales(log=log)
    marca = (marca, aj.marca)
    if _cache_conf["datos"] is not None and _cache_conf["marca"] == marca:
        return _cache_conf["datos"]
    marca_txt = marca[0]
    datos = {"tope_eur": TOPE_EUR, "eur_por_usd": EUR_POR_USD, "avisos": AVISOS_PORCENTAJE,
             "precios": {m: list(v) for m, v in PRECIOS_DEFECTO.items()}}
    propios = {}
    if marca_txt is not None:
        seccion = ""
        try:
            lineas = ARCHIVO.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            lineas = []
            log(f"No he podido leer {ARCHIVO.name} ({e}): uso los valores de fábrica")
        for linea in lineas:
            linea = linea.split("#", 1)[0].strip()
            if not linea:
                continue
            if linea.startswith("[") and linea.endswith("]"):
                seccion = linea[1:-1].strip().lower()
                continue
            if "=" not in linea:
                continue
            k, v = (x.strip() for x in linea.split("=", 1))
            if seccion == "precios":
                precio = _parsear_precio(v)
                m, _, desde = k.partition("@")
                if precio and m.strip():
                    entrada, salida = precio[0], precio[1]
                    cache = precio[2] if len(precio) == 3 else entrada / 10
                    propios.setdefault(m.strip(), []).append((desde.strip() or None, entrada, salida, cache))
                continue
            try:
                if k == "tope_mensual_eur":
                    datos["tope_eur"] = max(0.0, float(v.replace(",", ".")))
                elif k == "eur_por_usd":
                    datos["eur_por_usd"] = max(0.01, float(v.replace(",", ".")))
                elif k == "avisos_porcentaje":
                    datos["avisos"] = tuple(sorted({int(x) for x in re.findall(r"\d+", v) if 0 < int(x) <= 100})) or AVISOS_PORCENTAJE
            except ValueError:
                log(f"{ARCHIVO.name}: no entiendo «{k} = {v}»: uso el valor de fábrica")
        datos["precios"].update(propios)
    # El tope, el cambio euro/dólar y los avisos viven en config.toml, sección [gasto] (presupuesto.txt solo guarda los precios)
    datos["tope_eur"] = float(aj.get("gasto", "tope_mensual_eur"))
    datos["eur_por_usd"] = float(aj.get("gasto", "eur_por_usd"))
    datos["avisos"] = tuple(aj.get("gasto", "avisos_porcentaje"))
    _cache_conf["marca"], _cache_conf["datos"] = marca, datos
    return datos


def _precio_de(entradas, hoy=None):
    """De las tarifas de un modelo, la que vale HOY (la más reciente cuya fecha «desde» ya ha llegado)."""
    hoy = hoy or time.strftime("%Y-%m-%d")
    validas = [e for e in entradas if e[0] is None or e[0] <= hoy]
    base = [e for e in validas if e[0] is None]
    elegida = max((e for e in validas if e[0] is not None), key=lambda e: e[0], default=(base[0] if base else entradas[0]))
    return elegida[1], elegida[2], elegida[3]


def precio(modelo_real, modelo_pedido=None):
    """(entrada, salida, caché, es_estimado) en dólares por millón de tokens. Primero el modelo REAL que contestó (Google lo dice aunque
    pidas un alias como «-latest»), luego el alias, y si no se conoce, el precio más alto de la tabla (para no quedarse corto)."""
    tabla = configuracion()["precios"]
    for nombre in (modelo_real, modelo_pedido):
        if not nombre:
            continue
        if nombre in tabla:
            return (*_precio_de(tabla[nombre]), False)
        candidatos = [k for k in tabla if nombre.startswith(k)]
        if candidatos:
            return (*_precio_de(tabla[max(candidatos, key=len)]), False)
    todos = [_precio_de(v) for v in tabla.values()]
    clave = str(modelo_real or modelo_pedido)
    if clave not in _precio_desconocido_avisado:
        _precio_desconocido_avisado.add(clave)
        log(f"No conozco el precio de «{clave}» (añádelo en {ARCHIVO.name}): cuento el más caro de la tabla")
    return (max(t[0] for t in todos), max(t[1] for t in todos), max(t[2] for t in todos), True)


def coste_usd(modelo_real, modelo_pedido, prompt, candidatos, razonamiento, cacheados=0):
    entrada, salida, cache, _ = precio(modelo_real, modelo_pedido)
    cacheados = max(0, min(int(cacheados or 0), int(prompt or 0)))
    return (((int(prompt or 0) - cacheados) * entrada) + (cacheados * cache) + ((int(candidatos or 0) + int(razonamiento or 0)) * salida)) / 1_000_000


# ======================= lo gastado =======================
def _nuevo(mes):
    return {"mes": mes, "usd": 0.0, "llamadas_pago": 0, "llamadas_gratis": 0, "tokens_pago": 0, "tokens_gratis": 0, "avisos": [], "por_modelo": {}}


def _cargar():
    mes = time.strftime("%Y-%m")
    try:
        datos = json.loads(ARCHIVO_GASTO.read_text(encoding="utf-8"))
        if not isinstance(datos, dict) or datos.get("mes") != mes:
            return _nuevo(mes)                           # mes nuevo: se empieza de cero (y el tope vuelve al del archivo)
        for k, v in _nuevo(mes).items():
            datos.setdefault(k, v)
        return datos
    except (OSError, ValueError):
        return _nuevo(mes)


def _guardar(datos):
    try:
        ARCHIVO_GASTO.parent.mkdir(parents=True, exist_ok=True)
        tmp = ARCHIVO_GASTO.with_name(ARCHIVO_GASTO.name + ".tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(ARCHIVO_GASTO)
    except OSError as e:
        log(f"No he podido guardar el gasto: {e}")


def _tope_eur(d):
    return float(d.get("tope_eur") or configuracion()["tope_eur"])


def _gasto_eur(d):
    return float(d.get("usd", 0.0)) * configuracion()["eur_por_usd"]


def _euros(x):
    t = f"{x:.2f}".replace(".", ",")
    return (t[:-3] if t.endswith(",00") else t) + " €"


def _entero(valor):
    """Un contador de tokens: lo que no sea un número (o sea negativo) cuenta como 0, para que un dato raro de Google no rompa nada."""
    return int(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor > 0 else 0


def registrar(clave, modelo, uso, modelo_real=None):
    """Apunta una llamada a Gemini. NUNCA falla: la contabilidad no puede estropear una respuesta."""
    try:
        _registrar(clave, modelo, uso, modelo_real)
    except Exception as e:
        log(f"No he podido apuntar el gasto de esta llamada: {e!r}")


def _registrar(clave, modelo, uso, modelo_real=None):
    """Con la clave gratuita solo cuentan llamadas y tokens; con la de pago, también el dinero, y si se cruza un umbral de aviso
    (50, 80, 100 %), queda un mensaje pendiente de decir."""
    if not isinstance(uso, dict):
        return
    prompt, cand, pens, cache = (_entero(uso.get(k)) for k in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "cachedContentTokenCount"))
    with _lock:
        d = _cargar()
        tipo = nombre_de(clave)
        d[f"llamadas_{tipo}"] = d.get(f"llamadas_{tipo}", 0) + 1
        d[f"tokens_{tipo}"] = d.get(f"tokens_{tipo}", 0) + prompt + cand + pens
        if tipo == "pago":
            usd = coste_usd(modelo_real, modelo, prompt, cand, pens, cache)
            d["usd"] = float(d.get("usd", 0.0)) + usd
            real = str(modelo_real or modelo)
            d["por_modelo"][real] = round(float(d["por_modelo"].get(real, 0.0)) + usd, 6)
            tope, gasto = _tope_eur(d), _gasto_eur(d)
            porcentaje = gasto / tope * 100 if tope > 0 else 100.0
            cruzados = [u for u in configuracion()["avisos"] if u not in d["avisos"] and porcentaje >= u]
            if cruzados:
                d["avisos"] = sorted(set(d["avisos"]) | set(cruzados))
                u = max(cruzados)
                if u >= 100:
                    _avisos_pendientes.append(f"He llegado al tope de gasto de este mes ({_euros(tope)}). A partir de ahora uso solo la clave "
                                              f"gratuita. Si quieres seguir con la de pago, dime «sigue con el de pago hasta {math.ceil(tope) + 5} euros».")
                elif u >= 80:
                    _avisos_pendientes.append(f"Aviso: llevas el {u} % del tope de gasto de este mes ({_euros(gasto)} de {_euros(tope)}).")
                else:
                    _avisos_pendientes.append(f"Ojo: llevas el {u} % del tope de gasto de este mes ({_euros(gasto)} de {_euros(tope)}).")
        _guardar(d)


def avisos_pendientes():
    """Los avisos de gasto que toca decir (y se vacían)."""
    with _lock:
        pendientes, _avisos_pendientes[:] = list(_avisos_pendientes), []
    return pendientes


def notificar(texto):
    """Una notificación de escritorio (si hay notify-send)."""
    try:
        subprocess.Popen(["notify-send", "-a", "Asistente", "Gasto de Gemini", str(texto)[:300]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def estado():
    with _lock:
        d = _cargar()
    tope, gasto = _tope_eur(d), _gasto_eur(d)
    return {"mes": d["mes"], "gasto_eur": gasto, "tope_eur": tope, "porcentaje": (gasto / tope * 100) if tope > 0 else 100.0,
            "llamadas_pago": d["llamadas_pago"], "llamadas_gratis": d["llamadas_gratis"], "hay_pago": hay_clave_de_pago(),
            "pago_disponible": pago_disponible(), "por_modelo": dict(d["por_modelo"])}


def resumen():
    """Lo que se le cuenta al usuario cuando pregunta cuánto lleva gastado."""
    e = estado()
    if not e["hay_pago"]:
        return (f"No hay clave de pago configurada (añádela con:  lina clave pago), así que no se está gastando nada. "
                f"Este mes llevo {e['llamadas_gratis']} llamadas con la clave gratuita.")
    texto = (f"Este mes ({e['mes']}) llevas gastados {_euros(e['gasto_eur'])} de {_euros(e['tope_eur'])} ({e['porcentaje']:.0f} %) con la clave de pago, "
             f"en {e['llamadas_pago']} llamadas; con la gratuita, {e['llamadas_gratis']}. ")
    texto += ("Estado: uso la clave de pago para lo de a fondo." if e["pago_disponible"]
              else "Estado: he llegado al tope, así que solo uso la clave gratuita hasta que subas el tope o empiece el mes que viene.")
    return texto + " Es una estimación mía con la tabla de precios; lo oficial está en AI Studio, en Dashboard > Usage."


def subir_tope(euros, voz_libre=False):
    """Cambia el tope de ESTE mes (solo lo llama el código ante una frase tuya, nunca la IA). Devuelve lo que se te dice.
    Con voz_libre=True (la orden llegó por «Oye Lina») solo se deja bajarlo: subirlo exige el atajo."""
    if not hay_clave_de_pago():
        return "No hay clave de pago configurada (añádela con:  lina clave pago): no hay ningún gasto que topar."
    if voz_libre and euros > estado()["tope_eur"]:
        return ("Subir el tope de gasto solo lo hago si pulsas el atajo y me lo dices tú. "
                "Con «Oye Lina» no, por si lo dijera otra voz.")
    if not (1 <= euros <= TOPE_MAXIMO_POR_VOZ):
        return (f"Por seguridad solo cambio el tope por voz entre 1 y {TOPE_MAXIMO_POR_VOZ} euros. Si quieres otra cifra, edita {ARCHIVO.name}.")
    with _lock:
        d = _cargar()
        d["tope_eur"] = round(float(euros), 2)
        gasto, tope = _gasto_eur(d), d["tope_eur"]
        d["avisos"] = [u for u in d["avisos"] if u <= (gasto / tope * 100 if tope else 100)]      # los avisos que ya no tocan, vuelven a armarse
        _guardar(d)
    base = configuracion()["tope_eur"]
    if gasto >= tope:
        return f"Vale, pero ya llevas {_euros(gasto)}: con un tope de {_euros(tope)} sigo usando solo la clave gratuita."
    return (f"Vale: sigo con la clave de pago hasta {_euros(tope)} este mes (llevas {_euros(gasto)}). "
            f"El mes que viene vuelve a ser de {_euros(base)}.")


# ======================= entender «sigue con el de pago hasta 15 euros» =======================
_VERBOS_TOPE = {"sube", "subir", "aumenta", "aumentar", "amplia", "ampliar", "eleva", "elevar", "pon", "poner", "cambia", "cambiar", "sigue", "seguir",
                "continua", "continuar", "deja", "permite", "baja", "bajar", "reduce", "reducir", "limita", "limitar", "fija", "fijar"}
_UNIDADES = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
             "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
             "veintiuno": 21, "veintiun": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
             "veintisiete": 27, "veintiocho": 28, "veintinueve": 29}
_DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100}


def _palabras_a_numero(frase):
    p = frase.split()
    if len(p) == 1:
        return _UNIDADES.get(p[0], _DECENAS.get(p[0]))
    if len(p) == 3 and p[1] == "y" and p[0] in _DECENAS and _UNIDADES.get(p[2], 99) < 10:
        return _DECENAS[p[0]] + _UNIDADES[p[2]]
    return None


def entender_tope(texto):
    """Si has dicho que cambies el tope de gasto de la clave de pago, la cantidad en euros; si no, None. Exige un verbo de cambiar,
    hablar del gasto o del pago (no vale «pon un límite de 30 euros a mi compra») y una cantidad dicha por ti."""
    solo = comandos.normalizar(texto)
    palabras = set(solo.split())
    if not (palabras & _VERBOS_TOPE):
        return None
    if not ("de pago" in solo or palabras & {"tope", "gasto", "gastar", "gastado"}):
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:€|euros?|eur\b)", str(texto).lower())
    valor = float(m.group(1).replace(",", ".")) if m else None
    if valor is None:
        m2 = re.search(r"\b([a-z]+(?: y [a-z]+)?) euros?\b", solo)
        valor = _palabras_a_numero(m2.group(1)) if m2 else None
    return float(valor) if valor and valor > 0 else None
