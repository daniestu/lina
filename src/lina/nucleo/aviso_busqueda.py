# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Los avisos de la búsqueda en internet: que falta (una sola vez) y que Tavily ha llegado a su límite (como mucho una vez al mes por motivo).

Lo hablado es corto y sin nombres técnicos; el comando va en la notificación. El «ya avisé» vive en un archivo de estado para que sobreviva a
los reinicios y lo vean los demás procesos: se olvida al cambiar `ia.busqueda` (se guarda el modo con el que se avisó) y al guardar o borrar
la clave de Tavily (`claves.guardar`/`claves.borrar` llaman a `olvidar`). Un fallo al escribirlo nunca rompe nada: como mucho, se avisa otra vez.
"""
import json
import time

from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T

ARCHIVO = "aviso_busqueda.json"
SIN_BUSQUEDA, LIMITE_PLAN, LIMITE_GASTO = "sin_busqueda", "limite_432", "limite_433"
# Lo que le llega a la IA cuando Tavily dice que no por cupo (432: el plan; 433: el tope de gasto que pusiste). El 429 es de ritmo y no cuenta.
POR_CODIGO = {432: LIMITE_PLAN, 433: LIMITE_GASTO}
PARA_LA_IA_LIMITE = "La búsqueda en internet ha llegado a su límite de uso: responde con lo que sabes y di en pocas palabras que puede no estar al día."
PARA_LA_IA_SIN_BUSQUEDA = "No hay búsqueda en internet. Responde con lo que sabes y di en pocas palabras que puede no estar al día."

HABLADO = {SIN_BUSQUEDA: N_("Para tener datos de hoy necesito poder buscar en internet; te dejo cómo activarlo en una notificación."),
           LIMITE_PLAN: N_("Se han acabado las búsquedas en internet por ahora; respondo con lo que sé."),
           LIMITE_GASTO: N_("Se han acabado las búsquedas en internet por ahora; respondo con lo que sé.")}
NOTIFICACION = {SIN_BUSQUEDA: (N_("Lina: sin búsqueda en internet"),
                               N_("Sin búsqueda no tengo datos de hoy (resultados, horarios, noticias). Es gratis:  lina clave tavily  (o  lina bienvenida). "
                                  "Si no la quieres: pon ia.busqueda en «ninguna» con  lina config")),
                LIMITE_PLAN: (N_("Lina: Tavily ha llegado a su límite"),
                              N_("Tu plan de Tavily ha llegado a su límite de uso; se renueva cada ciclo o puedes ampliarlo en app.tavily.com")),
                LIMITE_GASTO: (N_("Lina: Tavily ha llegado a su límite"),
                               N_("Has llegado al límite de gasto que pusiste en Tavily; puedes subirlo en el panel (app.tavily.com)"))}

_pendientes: set = set()        # lo apuntado en la petición en curso


def _ruta():
    return RUT.ESTADO / ARCHIVO


def _leer():
    try:
        d = json.loads(_ruta().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir(d):
    try:
        _ruta().parent.mkdir(parents=True, exist_ok=True)
        _ruta().write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def _mes(ahora=None):
    return time.strftime("%Y-%m", time.localtime(ahora if ahora is not None else time.time()))


def apuntar(motivo):
    """Que hay que avisar de esto al terminar la petición (si no se avisó ya)."""
    _pendientes.add(motivo)


def descartar():
    """Lo apuntado en una petición que no llegó a responderse no se arrastra a la siguiente."""
    _pendientes.clear()


def olvidar():
    """Borra el «ya avisé»: la clave de Tavily se ha guardado o borrado."""
    try:
        _ruta().unlink()
    except OSError:
        pass


def pendientes(modo, ahora=None):
    """[(hablado, título, texto)] de lo que toca avisar ahora, y lo marca como avisado. Con `ninguna` no se avisa de que falta la búsqueda."""
    hechos, d, mes = [], _leer(), _mes(ahora)
    for motivo in sorted(_pendientes):
        if motivo == SIN_BUSQUEDA:
            if modo == "ninguna" or d.get(SIN_BUSQUEDA) == modo:     # ya avisé con este mismo modo
                continue
            d[SIN_BUSQUEDA] = modo
        elif d.get(motivo) == mes:                                   # el límite: como mucho una vez al mes por motivo
            continue
        else:
            d[motivo] = mes
        titulo, texto = NOTIFICACION[motivo]
        hechos.append((T(HABLADO[motivo]), T(titulo), T(texto)))
    _pendientes.clear()
    if hechos:
        _escribir(d)
    return hechos
