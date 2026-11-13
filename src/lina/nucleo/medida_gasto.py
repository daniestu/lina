# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El gasto de las medidas con la clave de pago (`lina probar-ia`, `lina probar-busqueda`): el máximo estimado antes de empezar y un tope que las para solas.

Caso real (2026-11-13): una tarde de medidas gastó 431 llamadas de pago (unos 0,91 €) y agotó el saldo prepago de la cuenta de Google sin que nadie lo
viera venir. Ahora cada tanda dice antes cuánto puede gastar como mucho (todas sus llamadas posibles a la clave de pago, al precio medio por llamada de pago de
los últimos 30 días) y, si al terminar una frase lo gastado con la de pago pasa de ese tope, se para y lo dice. `--estimar` solo dice el máximo, sin
gastar nada; `--tope-eur=N` cambia el tope. `solo_gratis()` mide sin la clave de pago.
"""
import json
import re
import statistics
from contextlib import contextmanager

from lina.nucleo.idioma import T

EUR_POR_LLAMADA_SIN_DATOS = 0.003      # si no hay llamadas de pago apuntadas: algo por encima de lo medido (0,0021 € el 2026-11-13)


def eur_por_llamada(archivo=None, dias=30):
    """Lo que cuesta de media una llamada a la IA con la clave de pago, según llamadas_ia.jsonl (sin texto: solo tokens). Si no hay datos, una cifra prudente."""
    from lina.nucleo import presupuesto as PRES
    from lina.nucleo import tiempos as TIE
    archivo = archivo or TIE.ARCHIVO_LLAMADAS
    costes = []
    try:
        lineas = archivo.read_text(encoding="utf-8").splitlines()[-5000:]
    except OSError:
        lineas = []
    for linea in lineas:
        try:
            x = json.loads(linea)
        except ValueError:
            continue
        if x.get("pago") and x.get("res") == "ok":
            costes.append(PRES.coste_usd(x.get("modelo"), x.get("modelo"), x.get("ent", 0), x.get("sal", 0), x.get("raz", 0), x.get("cache", 0))
                          * PRES.EUR_POR_USD)
    return statistics.mean(costes) if len(costes) >= 20 else EUR_POR_LLAMADA_SIN_DATOS


def maximo_estimado(frases, llamadas_por_frase, eur_llamada=None):
    """Lo más que puede gastar una tanda si todas sus llamadas fueran a la clave de pago."""
    return frases * llamadas_por_frase * (eur_por_llamada() if eur_llamada is None else eur_llamada)


def tope_de(argv, por_defecto):
    """El tope de --tope-eur=N (con coma o punto), o el máximo estimado."""
    for x in argv:
        m = re.fullmatch(r"--tope-eur=(\d+(?:[.,]\d+)?)", x)
        if m:
            return float(m.group(1).replace(",", "."))
    return por_defecto


def gastado_eur():
    """Lo gastado este mes con la clave de pago, según presupuesto (en euros)."""
    from lina.nucleo import presupuesto as PRES
    try:
        return float(PRES._cargar().get("usd") or 0.0) * PRES.EUR_POR_USD
    except Exception:
        return 0.0


class Tope:
    """Cuenta lo gastado con la clave de pago desde que empieza la tanda."""

    def __init__(self, eur, gastado=None):
        self.eur, self._gastado = eur, gastado or (lambda: gastado_eur())
        self.inicio = self._gastado()

    def llevado(self):
        return max(0.0, self._gastado() - self.inicio)

    def superado(self):
        return self.llevado() > self.eur


def frase_estimacion(maximo, tope):
    return T("Gasto máximo estimado con la clave de pago: {m} €. Tope de esta tanda: {t} € (se para sola si lo pasa; cámbialo con --tope-eur=N).",
             m=f"{maximo:.2f}".replace(".", ","), t=f"{tope:.2f}".replace(".", ","))


def frase_parada(tope):
    return T("Parada: llevo gastados {g} € con la clave de pago en esta tanda y el tope era {t} €. Lo hecho hasta aquí no vale como medida completa.",
             g=f"{tope.llevado():.2f}".replace(".", ","), t=f"{tope.eur:.2f}".replace(".", ","))


@contextmanager
def solo_gratis():
    """Mide sin la clave de pago: dentro, la clave «gemini_pago» no existe para Lina (ni para el presupuesto)."""
    from lina.nucleo import claves as CL
    from lina.nucleo import presupuesto as PRES
    real = CL.obtener
    antes = dict(PRES._claves)
    CL.obtener = lambda nombre, *a, **k: "" if nombre == "gemini_pago" else real(nombre, *a, **k)
    PRES.configurar_claves(antes.get("gratis", ""), "")
    try:
        yield
    finally:
        CL.obtener = real
        PRES._claves.update(antes)
