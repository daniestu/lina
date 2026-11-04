# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Los avisos de la búsqueda en internet: que falta (una sola vez), que Tavily ha llegado a su límite (como mucho una vez al mes por motivo) y, la primera
vez que se usan, adónde va tu consulta sin Tavily (DuckDuckGo, Wikipedia y las wikis de juegos). Estos últimos van en otro archivo y no se olvidan nunca.

Lo hablado es corto y sin nombres técnicos; el comando va en la notificación. El «ya avisé» vive en un archivo de estado para que sobreviva a
los reinicios y lo vean los demás procesos: se olvida al cambiar `ia.busqueda` (se guarda el modo con el que se avisó) y al guardar o borrar
la clave de Tavily (`claves.guardar`/`claves.borrar` llaman a `olvidar`). Un fallo al escribirlo nunca rompe nada: como mucho, se avisa otra vez.
"""
import json
import time

from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T

ARCHIVO = "aviso_busqueda.json"
ARCHIVO_PRIMERA = "aviso_busqueda_primera.json"
SIN_BUSQUEDA, LIMITE_PLAN, LIMITE_GASTO = "sin_busqueda", "limite_432", "limite_433"
PRIMERA_DUCKDUCKGO, PRIMERA_WIKI = "primera_duckduckgo", "primera_wiki"
UNA_VEZ = {PRIMERA_DUCKDUCKGO, PRIMERA_WIKI}
# Lo que le llega a la IA cuando Tavily dice que no por cupo (432: el plan; 433: el tope de gasto que pusiste). El 429 es de ritmo y no cuenta.
POR_CODIGO = {432: LIMITE_PLAN, 433: LIMITE_GASTO}
PARA_LA_IA_LIMITE = "La búsqueda en internet ha llegado a su límite de uso: responde con lo que sabes y di en pocas palabras que puede no estar al día."
PARA_LA_IA_SIN_BUSQUEDA = "No hay búsqueda en internet. Responde con lo que sabes y di en pocas palabras que puede no estar al día."

HABLADO = {SIN_BUSQUEDA: N_("Para tener datos de hoy necesito poder buscar en internet; te dejo cómo activarlo en una notificación."),
           LIMITE_PLAN: N_("Se han acabado las búsquedas en internet por ahora; respondo con lo que sé."),
           LIMITE_GASTO: N_("Se han acabado las búsquedas en internet por ahora; respondo con lo que sé."),
           PRIMERA_DUCKDUCKGO: N_("Esta vez he buscado en DuckDuckGo; te dejo los detalles en una notificación."),
           PRIMERA_WIKI: ""}                         # solo la notificación: es lo de fábrica sin Tavily y no merece interrumpir la respuesta
NOTIFICACION = {SIN_BUSQUEDA: (N_("Lina: sin búsqueda en internet"),
                               N_("Sin búsqueda no tengo datos de hoy (resultados, horarios, noticias). Es gratis:  lina clave tavily  (o  lina bienvenida). "
                                  "Si no la quieres: pon ia.busqueda en «ninguna» con  lina config")),
                LIMITE_PLAN: (N_("Lina: Tavily ha llegado a su límite"),
                              N_("Tu plan de Tavily ha llegado a su límite de uso; se renueva cada ciclo o puedes ampliarlo en app.tavily.com")),
                LIMITE_GASTO: (N_("Lina: Tavily ha llegado a su límite"),
                               N_("Has llegado al límite de gasto que pusiste en Tavily; puedes subirlo en el panel (app.tavily.com)")),
                PRIMERA_DUCKDUCKGO: (N_("Lina: he buscado en DuckDuckGo"),
                                     N_("Lo encendiste tú (ia.busqueda_reserva). Es poco fiable: suele tomar a los programas por robots y entonces no da nada. DuckDuckGo ve "
                                        "el texto de la búsqueda y tu dirección IP. Para apagarlo:  lina config poner ia.busqueda_reserva false")),
                PRIMERA_WIKI: (N_("Lina: he buscado en Wikipedia"),
                               N_("Sin clave de Tavily busco en Wikipedia y en algunas wikis de juegos: ven el texto de la búsqueda y tu dirección IP. Para noticias, "
                                  "precios, horarios o resultados, una clave gratuita de Tavily va mucho mejor:  lina bienvenida"))}

MIENTRAS_RESERVA = N_("Mientras tanto busco en DuckDuckGo.")

_pendientes: set = set()        # lo apuntado en la petición en curso


def _ruta(nombre=ARCHIVO):
    return RUT.ESTADO / nombre


def _leer(nombre=ARCHIVO):
    try:
        d = json.loads(_ruta(nombre).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir(d, nombre=ARCHIVO):
    try:
        _ruta(nombre).parent.mkdir(parents=True, exist_ok=True)
        _ruta(nombre).write_text(json.dumps(d), encoding="utf-8")
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


def pendientes(modo, ahora=None, reserva=False):
    """[(hablado, título, texto)] de lo que toca avisar ahora, y lo marca como avisado. Con `ninguna` no se avisa de que falta la búsqueda. Con la
    búsqueda de reserva activa, el límite de Tavily no se dice en voz alta (se sigue buscando): solo la notificación, que lo cuenta."""
    hechos, d, mes, primeras = [], _leer(), _mes(ahora), _leer(ARCHIVO_PRIMERA)
    for motivo in sorted(_pendientes):
        if motivo in UNA_VEZ:
            if primeras.get(motivo):
                continue
            primeras[motivo] = True
            _escribir(primeras, ARCHIVO_PRIMERA)
        elif motivo == SIN_BUSQUEDA:
            if modo == "ninguna" or d.get(SIN_BUSQUEDA) == modo:     # ya avisé con este mismo modo
                continue
            d[SIN_BUSQUEDA] = modo
        elif d.get(motivo) == mes:                                   # el límite: como mucho una vez al mes por motivo
            continue
        else:
            d[motivo] = mes
        titulo, texto = NOTIFICACION[motivo]
        if reserva and motivo in POR_CODIGO.values():
            hechos.append(("", T(titulo), T(texto) + " " + T(MIENTRAS_RESERVA)))
        else:
            hechos.append((T(HABLADO[motivo]) if HABLADO[motivo] else "", T(titulo), T(texto)))
    _pendientes.clear()
    if hechos:
        _escribir(d)
    return hechos
