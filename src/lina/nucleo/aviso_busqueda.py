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
TOPE_PROPIO, AVISO_80 = "tope_ia_tavily_mes", "tavily_80"          # E2: el tope que pones tú (ia.tavily_mes) y el aviso al 80 %, una vez al mes cada uno
PRIMERA_DUCKDUCKGO, PRIMERA_WIKI, PRIMERA_COMPATIBILIDAD = "primera_duckduckgo", "primera_wiki", "primera_compatibilidad"
UNA_VEZ = {PRIMERA_DUCKDUCKGO, PRIMERA_WIKI, PRIMERA_COMPATIBILIDAD}
# Lo que le llega a la IA cuando Tavily dice que no por cupo (432: el plan; 433: el tope de gasto que pusiste). El 429 es de ritmo y no cuenta.
POR_CODIGO = {432: LIMITE_PLAN, 433: LIMITE_GASTO}
PARA_LA_IA_LIMITE = "La búsqueda en internet ha llegado a su límite de uso: responde con lo que sabes y di en pocas palabras que puede no estar al día."
PARA_LA_IA_SIN_BUSQUEDA = "No hay búsqueda en internet. Responde con lo que sabes y di en pocas palabras que puede no estar al día."

HABLADO = {SIN_BUSQUEDA: N_("Para tener datos de hoy necesito poder buscar en internet; te dejo cómo activarlo en una notificación."),
           LIMITE_PLAN: N_("No me quedan búsquedas de datos de hoy hasta el día 1; mientras, respondo con lo que sé."),
           LIMITE_GASTO: N_("No me quedan búsquedas de datos de hoy hasta el día 1; mientras, respondo con lo que sé."),
           TOPE_PROPIO: N_("He llegado al tope de búsquedas que pusiste para este mes; hasta el día 1, respondo con lo que sé."),
           AVISO_80: "",                             # solo la notificación
           PRIMERA_DUCKDUCKGO: N_("Esta vez he buscado en DuckDuckGo; te dejo los detalles en una notificación."),
           PRIMERA_WIKI: "",                         # solo la notificación: es lo de fábrica sin Tavily y no merece interrumpir la respuesta
           PRIMERA_COMPATIBILIDAD: ""}
NOTIFICACION = {SIN_BUSQUEDA: (N_("Lina: sin búsqueda en internet"),
                               N_("Sin búsqueda no tengo datos de hoy (resultados, horarios, noticias). Es gratis:  lina clave tavily  (o  lina bienvenida). "
                                  "Si no la quieres: pon ia.busqueda en «ninguna» con  lina config")),
                LIMITE_PLAN: (N_("Lina: Tavily ha llegado a su límite"),
                              N_("Tu plan de Tavily ha llegado a su límite de uso; se renueva cada ciclo o puedes ampliarlo en app.tavily.com")),
                LIMITE_GASTO: (N_("Lina: Tavily ha llegado a su límite"),
                               N_("Has llegado al límite de gasto que pusiste en Tavily; puedes subirlo en el panel (app.tavily.com)")),
                TOPE_PROPIO: (N_("Lina: tope de búsquedas de Tavily"),
                              N_("Has llegado a las búsquedas de Tavily que pusiste para este mes (ia.tavily_mes). Hasta el día 1 no se llama a Tavily. Para cambiarlo:  "
                                 "lina config poner ia.tavily_mes N  (0 = sin tope)")),
                AVISO_80: (N_("Lina: el 80 % de las búsquedas de Tavily"),
                           N_("Este mes ya van {n} de {tope} búsquedas de Tavily (ia.tavily_mes). Sin clave de pago, es la única vía de datos de hoy.")),
                PRIMERA_DUCKDUCKGO: (N_("Lina: he buscado en DuckDuckGo"),
                                     N_("Lo encendiste tú (ia.busqueda_reserva). Es poco fiable: suele tomar a los programas por robots y entonces no da nada. DuckDuckGo ve "
                                        "el texto de la búsqueda y tu dirección IP. Para apagarlo:  lina config poner ia.busqueda_reserva false")),
                PRIMERA_WIKI: (N_("Lina: he buscado en Wikipedia"),
                               N_("Sin clave de Tavily busco en Wikipedia y en algunas wikis de juegos: ven el texto de la búsqueda y tu dirección IP. Para noticias, "
                                  "precios, horarios o resultados, una clave gratuita de Tavily va mucho mejor:  lina bienvenida")),
                PRIMERA_COMPATIBILIDAD: (N_("Lina: he mirado Steam y ProtonDB"),
                                         N_("Para saber si un juego funciona en Linux pregunto a la tienda de Steam y a ProtonDB: ven el número del juego en Steam y tu "
                                            "dirección IP, nada más."))}

MIENTRAS_RESERVA = N_("Mientras tanto busco en DuckDuckGo.")
# E2: con las wikis en la escalera («auto»), la búsqueda sigue: no se dice que se han acabado las búsquedas
CON_WIKIS = {LIMITE_PLAN: N_("No me quedan búsquedas de datos de hoy hasta el día 1; mientras, busco en Wikipedia y en las wikis."),
             LIMITE_GASTO: N_("No me quedan búsquedas de datos de hoy hasta el día 1; mientras, busco en Wikipedia y en las wikis."),
             TOPE_PROPIO: N_("He llegado al tope de búsquedas que pusiste para este mes; hasta el día 1 busco en Wikipedia y en las wikis.")}

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


def primera_vez(motivo):
    """(título, texto) del aviso de primer uso de `motivo` si no se ha dado nunca, y lo marca como dado; si ya se dio, None. Para avisar ANTES de la respuesta
    (ProtonDB: el aviso de privacidad llegaba diez segundos después de lo que dijo Lina)."""
    primeras = _leer(ARCHIVO_PRIMERA)
    if motivo not in UNA_VEZ or primeras.get(motivo):
        return None
    primeras[motivo] = True
    _escribir(primeras, ARCHIVO_PRIMERA)
    titulo, texto = NOTIFICACION[motivo]
    return T(titulo), T(texto)


def descartar():
    """Lo apuntado en una petición que no llegó a responderse no se arrastra a la siguiente."""
    _pendientes.clear()


def olvidar():
    """Borra el «ya avisé»: la clave de Tavily se ha guardado o borrado."""
    try:
        _ruta().unlink()
    except OSError:
        pass


def pendientes(modo, ahora=None, reserva=False, wikis=None):
    """[(hablado, título, texto)] de lo que toca avisar ahora, y lo marca como avisado. Con `ninguna` no se avisa de que falta la búsqueda. Con la
    búsqueda de reserva activa, el límite de Tavily no se dice en voz alta (se sigue buscando): solo la notificación, que lo cuenta. Con las wikis en la
    escalera (`wikis`, de fábrica con «auto»), lo hablado dice que se sigue buscando en ellas, no que se han acabado las búsquedas (E2)."""
    wikis = modo == "auto" if wikis is None else wikis
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
        if motivo == AVISO_80:
            from lina.nucleo import cupo_tavily as CUP
            r = CUP.resumen()
            hechos.append(("", T(titulo), T(texto, n=r["real"], tope=r["tope_real"])))
        elif reserva and motivo in POR_CODIGO.values():
            hechos.append(("", T(titulo), T(texto) + " " + T(MIENTRAS_RESERVA)))
        else:
            hablado = CON_WIKIS.get(motivo) if wikis else None
            hablado = hablado or HABLADO[motivo]
            hechos.append((T(hablado) if hablado else "", T(titulo), T(texto)))
    _pendientes.clear()
    if hechos:
        _escribir(d)
    return hechos
