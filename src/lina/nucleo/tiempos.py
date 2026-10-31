# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Dónde se va el tiempo de cada petición (fase 11). Un cronómetro por fases, una línea en el registro y un archivo `tiempos.jsonl` que guarda SOLO números
(nunca lo que dijiste ni lo que contesté). `lina tiempos` lo resume.

Aparte, `escuchas.jsonl` (V3c): cómo terminó cada escucha del atajo (por silencio, por tu pulsación, «No te he oído» o el tope) con el día, sin hora, y
tiempos. Tampoco lleva audio ni texto. `lina tiempos escucha [días]` lo resume.

Y `llamadas_ia.jsonl` (V4a): por cada llamada a la IA, los tokens (de entrada, servidos desde la caché, de salida y de razonamiento), cuánto tardó, el
tamaño del principio fijo (instrucciones y herramientas) y una huella de 8 caracteres de ese principio, para saber si se repite sin guardar su contenido.
Solo el día, sin hora. `lina tiempos ia [días]` dice si la caché de Gemini se aprovecha y cuánto pesa el tamaño, con el criterio de la fila V4."""
import datetime
import json
import statistics
import time
from contextlib import contextmanager

from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T

ARCHIVO = RUT.ESTADO / "tiempos.jsonl"
MAX_BYTES = 200_000          # al pasarse, se queda con las últimas MAX_LINEAS_TRAS_ROTAR líneas
MAX_LINEAS_TRAS_ROTAR = 500
FASES = ("whisper", "previas", "ia", "herramientas", "sintesis", "voz")
NOMBRES = {"whisper": N_("Whisper (voz a texto)"), "previas": N_("decisiones previas del código"), "ia": N_("IA (sin herramientas)"),
           "herramientas": N_("herramientas"), "sintesis": N_("síntesis de la voz"), "voz": N_("reproducción")}
HASTA_OIRTE = ("whisper", "previas", "ia", "herramientas", "sintesis")      # lo que pasa desde que terminas de hablar hasta que suena la primera palabra

ARCHIVO_ESCUCHAS = RUT.ESTADO / "escuchas.jsonl"
MAX_LINEAS_ESCUCHAS = 5000           # ~450 KB: meses de uso
FINES = ("silencio", "pulsacion", "nada", "tope", "pulsacion_ignorada")
CAMPOS_ESCUCHA = ("dia", "fin", "ajuste", "silencio", "dur", "espera", "tras_corte")   # lo ÚNICO que se guarda de una escucha
TRAS_CORTE_MAX = 10.0                # volver a pulsar antes de esto tras un corte por silencio cuenta como «posible corte a destiempo»
DIAS_ESCUCHA = 14

ARCHIVO_LLAMADAS = RUT.ESTADO / "llamadas_ia.jsonl"
MAX_LINEAS_LLAMADAS = 5000
CAMPOS_LLAMADA = ("dia", "modelo", "res", "seg", "ent", "cache", "sal", "raz", "pref", "conv", "huella", "repite", "pago", "motivo")
# Por qué se llamó a la IA, de esta lista y nada más: separa los reintentos de las llamadas normales al mirar la caché y el coste.
MOTIVOS = ("normal", "a_fondo", "hechos", "reintento", "pantalla", "comprobacion", "consulta", "resumen", "medida", "otro")
REPITE_SEG = 300                     # el mismo principio en menos de esto: la caché debería aprovecharlo
DIAS_IA = 30
MIN_LLAMADAS_CACHE = 50              # criterio de V4 (escrito antes de medir)
MIN_LLAMADAS_TAMANO = 100
UMBRAL_CACHE = 0.30
UMBRAL_PRINCIPIO_TOKENS = 6000
UMBRAL_DIFERENCIA_SEG = 0.5
UMBRAL_PARTE_ENTRADA = 0.70


class Cronometro:
    """Suma segundos por fase. El reloj se puede sustituir (pruebas)."""

    def __init__(self, reloj=time.monotonic):
        self.reloj = reloj
        self.fases = {}
        self.herramientas = 0
        self.llamadas = []                      # [(segundos, resultado)] de cada llamada a la IA de esta petición
        self.inicio = reloj()

    def sumar(self, fase, segundos):
        self.fases[fase] = self.fases.get(fase, 0.0) + max(0.0, float(segundos))

    @contextmanager
    def medir(self, fase):
        t0 = self.reloj()
        try:
            yield
        finally:
            self.sumar(fase, self.reloj() - t0)

    def total(self):
        return self.reloj() - self.inicio

    def hasta_oirte(self):
        return sum(self.fases.get(f, 0.0) for f in HASTA_OIRTE)

    def registro(self, ruta, modo=""):
        """La línea que se guarda: solo números y la ruta que se siguió. Sin texto del usuario."""
        reg = {"t": int(time.time()), "ruta": str(ruta)[:60], "modo": str(modo)[:12], "herramientas": self.herramientas,
               "fases": {k: round(v, 3) for k, v in self.fases.items()}, "hasta_oirte": round(self.hasta_oirte(), 3)}
        if self.llamadas:
            reg["llamadas"] = [[round(float(s), 3), str(r)[:12]] for s, r in self.llamadas[:30]]
        return reg


def _s(x):
    return f"{x:.1f}".replace(".", ",") + " s"


def linea_de_registro(reg):
    """La línea legible para el registro del sistema."""
    f = reg["fases"]
    partes = [f"{k} {_s(f[k])}" for k in FASES if k in f]
    if reg["herramientas"]:
        partes.append(f"{reg['herramientas']} herramientas")
    if reg.get("llamadas"):
        partes.append(f"{len(reg['llamadas'])} llamadas a la IA ({', '.join(f'{_s(s)} {r}' for s, r in reg['llamadas'][:8])})")
    return "Tiempos [" + reg["ruta"] + "]: " + " · ".join(partes) + f" · hasta oírte {_s(reg['hasta_oirte'])}"


def guardar(reg, archivo=None):
    """Añade una línea al archivo, y lo recorta si crece. Nunca falla: medir es un extra."""
    archivo = archivo or ARCHIVO
    try:
        RUT.asegurar(archivo.parent)
        with open(archivo, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        if archivo.stat().st_size > MAX_BYTES:
            lineas = archivo.read_text(encoding="utf-8").splitlines()[-MAX_LINEAS_TRAS_ROTAR:]
            archivo.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def leer(archivo=None, ultimas=50):
    archivo = archivo or ARCHIVO
    try:
        lineas = archivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for linea in lineas[-ultimas:]:
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("fases"), dict):
            out.append(d)
    return out


def resumir(registros):
    """Media y mediana de cada fase y de «hasta oírte», y cuál es la fase más lenta (por la media)."""
    out = {"n": len(registros), "fases": {}}
    for fase in FASES:
        valores = [r["fases"][fase] for r in registros if fase in r["fases"]]
        if valores:
            out["fases"][fase] = (statistics.mean(valores), statistics.median(valores), len(valores))
    totales = [r.get("hasta_oirte", 0.0) for r in registros]
    out["hasta_oirte"] = (statistics.mean(totales), statistics.median(totales)) if totales else None
    lentas = {f: v[0] for f, v in out["fases"].items() if f in HASTA_OIRTE}
    out["mas_lenta"] = max(lentas, key=lentas.get) if lentas else None
    return out


def resumir_llamadas(registros):
    """Las llamadas a la IA de esos registros: cuántas, tiempo medio y mediano, la más lenta y cuántas fallaron (y por qué). None si no hay ninguna."""
    todas = [(float(s), str(r)) for reg in registros for s, r in reg.get("llamadas", []) if isinstance(s, (int, float))]
    if not todas:
        return None
    duraciones = [s for s, _ in todas]
    fallidas = {}
    for _, r in todas:
        if r != "ok":
            fallidas[r] = fallidas.get(r, 0) + 1
    return {"n": len(todas), "peticiones": sum(1 for reg in registros if reg.get("llamadas")), "media": statistics.mean(duraciones),
            "mediana": statistics.median(duraciones), "maxima": max(duraciones), "fallidas": fallidas}


def _bloque(titulo, registros, salida):
    if not registros:
        return
    r = resumir(registros)
    salida(T("{titulo}: {n} peticiones", titulo=T(titulo), n=r["n"]))
    for fase, (media, mediana, _) in r["fases"].items():
        salida(f"  {T(NOMBRES[fase]):34} " + T("media {media} · mediana {mediana}", media=_s(media), mediana=_s(mediana)))
    salida(f"  {T('desde que acabas de hablar hasta que suena'):34} " + T("media {media} · mediana {mediana}", media=_s(r["hasta_oirte"][0]),
                                                                              mediana=_s(r["hasta_oirte"][1])))
    if r["mas_lenta"]:
        salida("  " + T("La fase más lenta: {fase}.", fase=T(NOMBRES[r["mas_lenta"]])))
    ll = resumir_llamadas(registros)
    if ll:
        salida("  " + T("Llamadas a la IA: {n} en {p} peticiones · media {media} · mediana {mediana} · la más lenta {maxima}", n=ll["n"], p=ll["peticiones"],
                        media=_s(ll["media"]), mediana=_s(ll["mediana"]), maxima=_s(ll["maxima"])))
        if ll["fallidas"]:
            salida("  " + T("   no llegaron bien: {detalle}", detalle=", ".join(f"{k} ×{v}" for k, v in sorted(ll["fallidas"].items()))))


# ======================= escuchas del atajo (V3c) =======================
def registro_escucha(fin, ajuste=None, silencio=None, dur=None, espera=None, tras_corte=None, hoy=None):
    """La línea de una escucha: el modo de terminar, el día (sin hora) y números. Nada más, por construcción."""
    if fin not in FINES:
        raise ValueError(fin)
    reg = {"dia": (hoy or datetime.date.today()).isoformat(), "fin": fin}
    if ajuste is not None:
        reg["ajuste"] = bool(ajuste)
    for clave, valor in (("silencio", silencio), ("dur", dur), ("espera", espera), ("tras_corte", tras_corte)):
        if valor is not None:
            reg[clave] = round(float(valor), 2)
    return reg


def _anadir(archivo, reg, campos, maximo):
    """Añade una línea con solo `campos` y deja el archivo en sus últimas `maximo` líneas. Nunca falla."""
    try:
        limpio = {k: reg[k] for k in campos if k in reg}
        RUT.asegurar(archivo.parent)
        with open(archivo, "a", encoding="utf-8") as f:
            f.write(json.dumps(limpio, ensure_ascii=False) + "\n")
        if archivo.stat().st_size > maximo * 40:                    # ninguna línea ocupa menos: por debajo no puede haber de más
            lineas = archivo.read_text(encoding="utf-8").splitlines()
            if len(lineas) > maximo:
                archivo.write_text("\n".join(lineas[-maximo:]) + "\n", encoding="utf-8")
        return True
    except (OSError, TypeError, ValueError):
        return False


def apuntar_escucha(reg, archivo=None):
    """Añade la línea (solo con los campos permitidos) y recorta el archivo a las últimas MAX_LINEAS_ESCUCHAS. Nunca falla."""
    return _anadir(archivo or ARCHIVO_ESCUCHAS, reg, CAMPOS_ESCUCHA, MAX_LINEAS_ESCUCHAS)


def leer_escuchas(archivo=None, dias=DIAS_ESCUCHA, hoy=None):
    """Las escuchas de los últimos `dias` días (hoy incluido)."""
    archivo = archivo or ARCHIVO_ESCUCHAS
    desde = ((hoy or datetime.date.today()) - datetime.timedelta(days=dias - 1)).isoformat()
    try:
        lineas = archivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for linea in lineas:
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("fin") in FINES and isinstance(d.get("dia"), str) and d["dia"] >= desde:
            out.append(d)
    return out


def _mediana(xs):
    return statistics.median(xs) if xs else None


def resumir_escuchas(registros):
    """Por cada valor de silencio con el ajuste activo: cuántas cortó solo, cuántas acabaste pulsando, «No te he oído», tope, posibles cortes a destiempo y
    pulsaciones ignoradas; y las de doble pulsación (ajuste apagado)."""
    con, sin = {}, []
    ignoradas = sum(1 for r in registros if r["fin"] == "pulsacion_ignorada")
    for r in registros:
        if r["fin"] == "pulsacion_ignorada":
            continue
        if r.get("ajuste"):
            con.setdefault(r.get("silencio"), []).append(r)
        else:
            sin.append(r)
    bloques = []
    for silencio, rs in sorted(con.items(), key=lambda x: (x[0] is None, x[0] or 0)):
        por = {f: [r for r in rs if r["fin"] == f] for f in ("silencio", "pulsacion", "nada", "tope")}
        esperas = [r["espera"] for r in por["silencio"] if "espera" in r]
        bloques.append({"silencio": silencio, "n": len(rs), "por": {f: len(v) for f, v in por.items()},
                        "espera_corte": (statistics.mean(esperas) if esperas else None, _mediana(esperas)),
                        "espera_pulsando": _mediana([r["espera"] for r in por["pulsacion"] if "espera" in r]),
                        "a_destiempo": sum(1 for r in rs if "tras_corte" in r)})
    return {"n": len(registros) - ignoradas, "ignoradas": ignoradas, "con": bloques,
            "sin": {"n": len(sin), "dur": statistics.mean([r["dur"] for r in sin if "dur" in r]) if any("dur" in r for r in sin) else None}}


def _pc(n, total):
    return f"{round(100 * n / total)} %" if total else "-"


def _seg(x):
    return "-" if x is None else _s(x)


def principal_escucha(argv, salida=print, archivo=None, hoy=None):
    dias = DIAS_ESCUCHA
    if argv:
        try:
            dias = int(argv[0])
            if not 1 <= dias <= 365:
                raise ValueError
        except ValueError:
            salida(T("Uso:  lina tiempos escucha [días]   (por defecto, los últimos {d})", d=DIAS_ESCUCHA))
            return 2
    archivo = archivo or ARCHIVO_ESCUCHAS
    r = resumir_escuchas(leer_escuchas(archivo, dias, hoy))
    if not r["n"] and not r["ignoradas"]:
        salida(T("Todavía no hay escuchas del atajo apuntadas en los últimos {d} días.", d=dias))
        return 0
    salida(T("Escuchas con el atajo, últimos {d} días: {n}", d=dias, n=r["n"]))
    for b in r["con"]:
        n = b["n"]
        salida("  " + T("Con fin por silencio ({s}): {n}", s=_seg(b["silencio"]), n=n))
        salida("    " + T("cortó solo al callarte          {n}  ({pc})   espera media {media} · mediana {mediana}", n=b["por"]["silencio"],
                             pc=_pc(b["por"]["silencio"], n), media=_seg(b["espera_corte"][0]), mediana=_seg(b["espera_corte"][1])))
        salida("    " + T("acabaste pulsando               {n}  ({pc})   pulsaste {s} después de tu voz (mediana)", n=b["por"]["pulsacion"],
                             pc=_pc(b["por"]["pulsacion"], n), s=_seg(b["espera_pulsando"])))
        salida("    " + T("«No te he oído»                 {n}  ({pc})", n=b["por"]["nada"], pc=_pc(b["por"]["nada"], n)))
        salida("    " + T("tope de 60 s                    {n}  ({pc})", n=b["por"]["tope"], pc=_pc(b["por"]["tope"], n)))
        salida("    " + T("posibles cortes a destiempo     {n}   (volviste a pulsar menos de {s} después de un corte)", n=b["a_destiempo"], s=_s(TRAS_CORTE_MAX)))
    if r["ignoradas"]:
        salida("  " + T("Pulsaciones justo después de un corte (ignoradas): {n}", n=r["ignoradas"]))
    if r["sin"]["n"]:
        salida("  " + T("Con doble pulsación: {n}   duración media {dur}", n=r["sin"]["n"], dur=_seg(r["sin"]["dur"])))
    salida(T("Se guardan solo el modo de terminar, el día y tiempos en {archivo}; lo borras con:  lina olvidar tiempos", archivo=archivo))
    return 0


# ======================= llamadas a la IA y caché (V4a) =======================
def registro_llamada(modelo, res, seg, uso=None, pref=0, conv=0, huella="", repite=None, pago=False, hoy=None, motivo="normal"):
    """La línea de una llamada: el modelo, cómo acabó y números. Nunca texto de la petición ni de las instrucciones (de ellas, solo el tamaño y la huella)."""
    uso = uso if isinstance(uso, dict) else {}

    def entero(k):
        v = uso.get(k)
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    reg = {"dia": (hoy or datetime.date.today()).isoformat(), "modelo": str(modelo)[:60], "res": str(res)[:12], "seg": round(float(seg), 3),
           "pref": int(pref), "conv": int(conv), "huella": str(huella)[:8], "pago": bool(pago), "motivo": motivo if motivo in MOTIVOS else "otro"}
    for campo, k in (("ent", "promptTokenCount"), ("cache", "cachedContentTokenCount"), ("sal", "candidatesTokenCount"), ("raz", "thoughtsTokenCount")):
        if entero(k) is not None:
            reg[campo] = entero(k)
    if repite is not None:
        reg["repite"] = round(float(repite), 1)
    return reg


def apuntar_llamada(reg, archivo=None):
    return _anadir(archivo or ARCHIVO_LLAMADAS, reg, CAMPOS_LLAMADA, MAX_LINEAS_LLAMADAS)


def leer_llamadas(archivo=None, dias=DIAS_IA, hoy=None):
    archivo = archivo or ARCHIVO_LLAMADAS
    desde = ((hoy or datetime.date.today()) - datetime.timedelta(days=dias - 1)).isoformat()
    try:
        lineas = archivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for linea in lineas:
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("dia"), str) and d["dia"] >= desde and isinstance(d.get("seg"), (int, float)):
            out.append(d)
    return out


def _cuartiles(regs, clave):
    """(el cuarto más bajo, el cuarto más alto) de regs ordenados por `clave`."""
    orden = sorted(regs, key=lambda r: r[clave])
    q = len(orden) // 4
    return (orden[:q], orden[-q:]) if q else ([], [])


def resumir_ia(registros, precio=None):
    """Por modelo: si la caché se aprovecha (en las llamadas cuyo principio se repite y en las nuevas), cuánto ahorra en tiempo, cuánto pesa el tamaño y qué
    toca según el criterio de la fila V4. `precio(modelo, ent, sal, raz, cache)` → dólares (presupuesto.coste_usd); None = sin coste."""
    por = {}
    for r in registros:
        if r.get("res") == "ok" and isinstance(r.get("ent"), int) and r["ent"] > 0:
            por.setdefault(r.get("modelo", "?"), []).append(r)
    out = []
    for modelo, rs in sorted(por.items(), key=lambda x: -len(x[1])):
        n = len(rs)
        rep = [r for r in rs if "repite" in r]
        nuevas = [r for r in rs if "repite" not in r]

        def parte_cache(xs):
            ent = sum(r["ent"] for r in xs)
            return (sum(r.get("cache", 0) for r in xs) / ent) if ent else None
        caracteres = [r["ent"] / (r["pref"] + r["conv"]) for r in rs if r.get("pref", 0) + r.get("conv", 0) > 0]
        tok_por_car = statistics.median(caracteres) if caracteres else 0.25
        principio = statistics.median([r["pref"] * tok_por_car for r in rs]) if rs else 0
        con = [r for r in rs if r.get("cache", 0) > 0]
        sin = [r for r in rs if not r.get("cache")]
        bajo, alto = _cuartiles(rs, "ent")
        dif = (statistics.median([r["seg"] for r in alto]) - statistics.median([r["seg"] for r in bajo])) if bajo and alto else None
        coste = coste_entrada = coste_ideal = None
        if precio:
            pagadas = [r for r in rs if r.get("pago")]
            if pagadas:
                coste = sum(precio(modelo, r["ent"], r.get("sal", 0), r.get("raz", 0), r.get("cache", 0)) for r in pagadas)
                coste_entrada = coste - sum(precio(modelo, 0, r.get("sal", 0), r.get("raz", 0), 0) for r in pagadas)
                coste_ideal = sum(precio(modelo, r["ent"], r.get("sal", 0), r.get("raz", 0), max(r.get("cache", 0), min(r["ent"], int(r["pref"] * tok_por_car))))
                                  for r in pagadas)
        cache_rep = parte_cache(rep)
        decide_cache = None if len(rs) < MIN_LLAMADAS_CACHE or not rep else ("arreglar" if cache_rep < UMBRAL_CACHE else "bien")
        parte_entrada = (coste_entrada / coste) if coste else None
        if len(rs) < MIN_LLAMADAS_TAMANO:
            decide_tamano = None
        else:
            lento = principio > UMBRAL_PRINCIPIO_TOKENS and dif is not None and dif >= UMBRAL_DIFERENCIA_SEG
            caro = parte_entrada is not None and parte_entrada > UMBRAL_PARTE_ENTRADA
            decide_tamano = "aligerar" if lento or caro else "no tocar"
        motivos = {}
        for r in rs:
            m = motivos.setdefault(r.get("motivo", "sin_motivo"), [0, 0])
            m[0] += 1
            m[1] += r["ent"]
        out.append({"modelo": modelo, "n": n, "motivos": motivos, "con_cache": len(con), "cache_total": parte_cache(rs), "repetidas": len(rep), "cache_repetidas": cache_rep,
                    "nuevas": len(nuevas), "cache_nuevas": parte_cache(nuevas), "ent_mediana": statistics.median([r["ent"] for r in rs]),
                    "principio": principio, "tok_por_car": tok_por_car,
                    "seg_con": statistics.median([r["seg"] for r in con]) if con else None, "seg_sin": statistics.median([r["seg"] for r in sin]) if sin else None,
                    "diferencia_tamano": dif, "coste": coste, "coste_ideal": coste_ideal, "parte_entrada": parte_entrada,
                    "decide_cache": decide_cache, "decide_tamano": decide_tamano})
    return out


def _pct(x):
    return "-" if x is None else f"{round(100 * x)} %"


DECISIONES = {"arreglar": N_("menos del 30 % desde la caché aunque el principio se repite: toca V4b (dejar estable el principio)"),
              "bien": N_("la caché ya sirve el 30 % o más cuando el principio se repite: no se toca"),
              "aligerar": N_("el tamaño pesa: toca V4c (pasar reglas de situaciones concretas a sus grupos)"),
              "no tocar": N_("el tamaño no pesa lo bastante: no se aligeran las instrucciones")}


def principal_ia(argv, salida=print, archivo=None, hoy=None, precio=None):
    dias = DIAS_IA
    if argv:
        try:
            dias = int(argv[0])
            if not 1 <= dias <= 365:
                raise ValueError
        except ValueError:
            salida(T("Uso:  lina tiempos ia [días]   (por defecto, los últimos {d})", d=DIAS_IA))
            return 2
    archivo = archivo or ARCHIVO_LLAMADAS
    if precio is None:
        try:
            from lina.nucleo import presupuesto as PRES
            precio = lambda m, ent, sal, raz, cache: PRES.coste_usd(m, m, ent, sal, raz, cache)     # noqa: E731
        except Exception:
            precio = None
    modelos = resumir_ia(leer_llamadas(archivo, dias, hoy), precio)
    if not modelos:
        salida(T("Todavía no hay llamadas a la IA apuntadas en los últimos {d} días.", d=dias))
        return 0
    salida(T("Llamadas a la IA, últimos {d} días (solo las que respondieron):", d=dias))
    for m in modelos:
        salida(f"  {m['modelo']}: " + T("{n} llamadas · entrada mediana {ent} tokens · principio fijo ~{p} tokens ({c} tokens por carácter)",
                                       n=m["n"], ent=round(m["ent_mediana"]), p=round(m["principio"]), c=f"{m['tok_por_car']:.2f}".replace(".", ",")))
        salida("    " + T("por motivo: {detalle}", detalle=" · ".join(f"{k} {v[0]} ({v[1]} tokens)" for k, v in sorted(m["motivos"].items(), key=lambda x: -x[1][1]))))
        salida("    " + T("caché: {con} llamadas la usaron · desde la caché {total} de los tokens de entrada", con=m["con_cache"], total=_pct(m["cache_total"])))
        salida("    " + T("    con el mismo principio en menos de 5 min: {n} llamadas, {pc} desde la caché", n=m["repetidas"], pc=_pct(m["cache_repetidas"])))
        salida("    " + T("    con un principio nuevo: {n} llamadas, {pc} desde la caché", n=m["nuevas"], pc=_pct(m["cache_nuevas"])))
        salida("    " + T("tiempo (mediana): con caché {con} · sin caché {sin} · el cuarto más grande tarda {dif} más que el más pequeño",
                          con=_seg(m["seg_con"]), sin=_seg(m["seg_sin"]), dif=_seg(m["diferencia_tamano"])))
        if m["coste"] is not None:
            salida("    " + T("con la clave de pago: {c:.4f} $ ({pe} por la entrada); con todo el principio desde la caché sería {i:.4f} $",
                              c=m["coste"], pe=_pct(m["parte_entrada"]), i=m["coste_ideal"]))
        if m["decide_cache"]:
            salida("    → " + T("Caché: ") + T(DECISIONES[m["decide_cache"]]))
        else:
            salida("    → " + T("Caché: hacen falta al menos {n} llamadas (y alguna con el principio repetido) para decidir.", n=MIN_LLAMADAS_CACHE))
        if m["decide_tamano"]:
            salida("    → " + T("Tamaño: ") + T(DECISIONES[m["decide_tamano"]]))
        else:
            salida("    → " + T("Tamaño: hacen falta al menos {n} llamadas para decidir.", n=MIN_LLAMADAS_TAMANO))
    salida(T("Se guardan solo números, el modelo y una huella del principio en {archivo}; lo borras con:  lina olvidar tiempos", archivo=archivo))
    return 0


def principal(argv, salida=print, archivo=None, archivo_escuchas=None):
    if argv[:1] == ["escucha"]:
        return principal_escucha(argv[1:], salida, archivo_escuchas)
    if argv[:1] == ["ia"]:
        return principal_ia(argv[1:], salida)
    ultimas = 50
    if argv:
        try:
            ultimas = int(argv[0])
            if not 1 <= ultimas <= 5000:
                raise ValueError
        except ValueError:
            salida(T("Uso:  lina tiempos [N]   (resume las últimas N peticiones; por defecto 50)   |   lina tiempos escucha [días]   |   lina tiempos ia [días]"))
            return 2
    registros = leer(archivo, ultimas)
    if not registros:
        salida(T("Todavía no hay tiempos medidos. Habla con Lina un rato y vuelve a probar. (Se guardan solo números, nunca lo que dices; "
                 "se desactiva con:  lina config poner privacidad.registrar_tiempos no)"))
        return 0
    directas = [r for r in registros if str(r.get("ruta", "")).startswith("directa")]
    resto = [r for r in registros if r not in directas]
    _bloque(N_("Órdenes directas (sin IA)"), directas, salida)
    _bloque(N_("Con la IA, sin herramientas"), [r for r in resto if not r.get("herramientas")], salida)
    _bloque(N_("Con la IA y herramientas"), [r for r in resto if r.get("herramientas")], salida)
    escuchas = leer_escuchas(archivo_escuchas)
    if escuchas:
        salida(T("Escuchas con el atajo en los últimos {d} días: {n}. El detalle (cuántas cortó solo al callarte):  lina tiempos escucha", d=DIAS_ESCUCHA,
                 n=sum(1 for e in escuchas if e["fin"] != "pulsacion_ignorada")))
    salida(T("Se guardan solo números en {archivo}; lo borras con:  lina olvidar tiempos", archivo=archivo or ARCHIVO))
    return 0
