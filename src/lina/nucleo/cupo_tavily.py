# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""E2: el cupo mensual de Tavily. Cuenta las búsquedas de cada mes (de uso real y de medidas, por separado), les pone tope y recuerda hasta cuándo
está agotado tras un 432 o 433.

Caso real (2026-11-20): el plan de Tavily se agotó hasta el 1 de diciembre; las medidas habían gastado 228 búsquedas en una semana. Sin clave de pago,
Tavily es la única vía de datos de hoy: su cupo es lo que Lina sabe de hoy, y se cuida como el gasto. Solo se guardan números (ni la consulta ni la
clave), en la carpeta de datos (la misma que el gasto: `lina probar-busqueda` cambia el estado por uno temporal, pero el tope de las medidas sigue)."""
import datetime
import json

from lina.nucleo import rutas as RUT

ARCHIVO = RUT.DATOS / "tavily.json"
TOPE_MEDIDAS = 100              # búsquedas al mes para las medidas (como los 3 € de las medidas de pago)
TAVILY_MES = 1000               # de fábrica, el plan gratuito de Tavily (según Tavily); ia.tavily_mes lo cambia, 0 = sin tope
AVISO_PARTE = 0.8               # al 80 % del tope de uso real, una notificación


def _hoy(hoy=None):
    return hoy or datetime.date.today()


def _leer(hoy=None):
    """El estado de este mes; si es de otro mes, uno nuevo (el agotado de antes solo se conserva si sigue vigente)."""
    try:
        d = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    mes = _hoy(hoy).strftime("%Y-%m")
    if d.get("mes") != mes:
        d = {"mes": mes, "real": 0, "medida": 0, "agotado_hasta": d.get("agotado_hasta") or ""}
    if str(d.get("agotado_hasta") or "") <= _hoy(hoy).isoformat():
        d["agotado_hasta"] = ""
    return d


def _escribir(d):
    try:
        RUT.asegurar(ARCHIVO.parent)
        ARCHIVO.write_text(json.dumps(d), encoding="utf-8")
        ARCHIVO.chmod(0o600)
    except OSError:
        pass                                               # un fallo al apuntar nunca rompe una búsqueda


def tope_real():
    """El tope de uso real de este mes (ia.tavily_mes), o 0 si no hay."""
    try:
        from lina.nucleo import ajustes as AJ
        return max(0, int(AJ.actuales(log=lambda m: None).get("ia", "tavily_mes")))
    except Exception:
        return TAVILY_MES


def primer_dia_del_mes_siguiente(hoy=None):
    h = _hoy(hoy)
    return datetime.date(h.year + (h.month == 12), h.month % 12 + 1, 1)


def agotado(hoy=None):
    """Tavily ha dicho que no por cupo (432) o por tu tope de gasto en Tavily (433): no se le vuelve a llamar hasta el día 1. Devuelve esa fecha."""
    d = _leer(hoy)
    hasta = primer_dia_del_mes_siguiente(hoy)
    d["agotado_hasta"] = hasta.isoformat()
    _escribir(d)
    return hasta


def quitar_pausa():
    """Al guardar o borrar la clave de Tavily (has ampliado el plan o cambiado de cuenta): se vuelve a probar."""
    d = _leer()
    if d.get("agotado_hasta"):
        d["agotado_hasta"] = ""
        _escribir(d)


def agotado_hasta(hoy=None):
    """La fecha hasta la que Tavily está agotado (date) o None."""
    a = _leer(hoy).get("agotado_hasta")
    return datetime.date.fromisoformat(a) if a else None


def motivo_para_no_llamar(medida, hoy=None):
    """Por qué no se llama ahora a Tavily: «agotado», «tope_medidas», «tope_real» o «» si se puede."""
    d = _leer(hoy)
    if d.get("agotado_hasta"):
        return "agotado"
    if medida and d.get("medida", 0) >= TOPE_MEDIDAS:
        return "tope_medidas"
    tope = tope_real()
    if not medida and tope and d.get("real", 0) >= tope:
        return "tope_real"
    return ""


def apuntar(medida, hoy=None):
    """Una búsqueda hecha (Tavily contestó bien: es lo que gasta crédito). True si con esta el uso real llega al 80 % de su tope (para avisar)."""
    d = _leer(hoy)
    clave = "medida" if medida else "real"
    d[clave] = int(d.get(clave, 0)) + 1
    _escribir(d)
    tope = tope_real()
    return not medida and bool(tope) and d["real"] == max(1, int(tope * AVISO_PARTE))


def restante_medidas(hoy=None):
    return max(0, TOPE_MEDIDAS - int(_leer(hoy).get("medida", 0)))


def resumen(hoy=None):
    """{real, medida, tope_real, tope_medidas, agotado_hasta (date o None)} de este mes, sin llamar a Tavily."""
    d = _leer(hoy)
    return {"real": int(d.get("real", 0)), "medida": int(d.get("medida", 0)), "tope_real": tope_real(), "tope_medidas": TOPE_MEDIDAS,
            "agotado_hasta": datetime.date.fromisoformat(d["agotado_hasta"]) if d.get("agotado_hasta") else None}
