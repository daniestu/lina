# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Dónde se va el tiempo de cada petición (fase 11). Un cronómetro por fases, una línea en el registro y un archivo `tiempos.jsonl` que guarda SOLO números
(nunca lo que dijiste ni lo que contesté). `lina tiempos` lo resume."""
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


def principal(argv, salida=print, archivo=None):
    ultimas = 50
    if argv:
        try:
            ultimas = int(argv[0])
            if not 1 <= ultimas <= 5000:
                raise ValueError
        except ValueError:
            salida(T("Uso:  lina tiempos [N]   (resume las últimas N peticiones; por defecto 50)"))
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
    salida(T("Se guardan solo números en {archivo}; lo borras con:  lina olvidar tiempos", archivo=archivo or ARCHIVO))
    return 0
