# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Datos concretos de juegos y programas: se buscan antes de afirmarlos (bloque D3).

Caso real: «Quiero jugar a No Man's Sky, lo tengo instalado en Steam, ¿hay que hacer algo de Proton?». El modelo rápido contestó de memoria que tenía
versión nativa para Linux (falso: en Steam solo tiene Windows y Mac) y, cuando se le corrigió, se contradijo sin comprobar nada.

  · `pide_dato_de_juego`: la frase pregunta un dato concreto (Linux, Proton, versión, requisitos, actualización, fecha de salida…) de un juego (el que
    tienes delante, uno de tu biblioteca o «juego»). Entonces el código busca ANTES de llamar a la IA y le da los resultados.
  · `compatibilidad_linux` (herramienta de la IA, A13): la ficha de la tienda de Steam (¿tiene versión para Linux?) y el resumen de ProtonDB. Contesta la
    IA con esos datos y el código comprueba que no los contradiga (`contradice`). Los dos ven el número del juego y tu dirección IP (aviso la primera vez,
    antes de la respuesta). Si ProtonDB no responde, basta Steam. La detección por frases solo adelanta los datos.
  · `discute_un_dato`: le dices que se equivoca («creo que estás equivocado», «eso no es así»): se comprueba buscando antes de responder.
Conservador a propósito: solo preguntas (nunca una orden) y solo con un juego de por medio.
"""
import re

import requests

from lina.nucleo import comandos as C
from lina.nucleo import ia as IA
from lina.nucleo.idioma import N_, T
from lina.nucleo.registro import log

TIMEOUT = 6
_DATO = re.compile(r"\b(?:linux|proton|nativ[oa]s?|steam ?deck|compatib\w*|wine|requisitos|requerimientos|version(?:es)?|actualizacion(?:es)?|parches?|"
                   r"fecha de (?:salida|lanzamiento)|cuando sale|se puede jugar|funciona (?:en|con|bien)|anti ?(?:cheat|trampas)|dlc|expansion(?:es)?|"
                   r"update|patch(?:es)?|requirements|native|release date|runs? on|work(?:s)? on)\b")
_COMPATIBILIDAD = re.compile(r"\b(?:linux|proton|nativ[oa]s?|wine|steam ?deck|compatib\w*|funciona en (?:linux|el pc|mi pc)|native|runs? on linux|works? on linux)\b")
_JUEGO = re.compile(r"\b(?:juegos?|videojuegos?|games?)\b")
_ORDEN = re.compile(r"^(?:abre|abreme|pon|ponme|cierra|instala|instalame|desinstala|actualiza|sube|baja|quita|activa|desactiva|cambia|configura|lanza|"
                    r"open|install|update|close|launch|enable|disable)\b")
_DISCUTE = re.compile(r"\b(?:estas equivocad[oa]|te equivocas|te has equivocado|creo que no(?: es asi)?|eso no es (?:asi|verdad|cierto)|no es (?:verdad|cierto)|"
                      r"me parece que no|no estoy de acuerdo|seguro que no|yo creo que si|en realidad si|you(?: are| ?re) wrong|that(?: is| ?s) not (?:right|true)|"
                      r"i don ?t think so|are you sure)\b")
NIVELES = {"platinum": N_("perfectamente"), "gold": N_("bien, con pocos problemas"), "silver": N_("con algún problema"), "bronze": N_("con bastantes problemas"), "borked": N_("mal")}


def _t(frase):
    return C.normalizar(frase).strip(" ¿?¡!.,")


def es_orden(frase):
    return bool(_ORDEN.search(_t(frase)))


def juego_de(frase, contexto, buscar=None):
    """{nombre, id, origen} del juego del que se habla: el que nombra la frase (si está en tu biblioteca, con el nombre casi exacto: nada de parecidos de
    sonido) o, si no nombra ninguno, el de la ventana activa. None si no hay juego."""
    if buscar is None:
        try:
            from lina.modulos import juegos as JUE
            buscar = JUE.buscar
        except Exception:
            buscar = lambda q: []          # noqa: E731
    for puntos, j in buscar(frase) or []:
        if puntos >= 84:
            return {"nombre": j["nombre"], "id": j.get("id") if j.get("origen") == "steam" else None, "origen": j.get("origen")}
    if (contexto or {}).get("tipo") == "juego":
        m = re.fullmatch(r"steam_app_(\d+)", str(contexto.get("clase") or ""))
        return {"nombre": contexto.get("nombre") or "", "id": m.group(1) if m else None, "origen": "steam" if m else contexto.get("origen")}
    return None


def pide_dato_de_juego(frase, contexto, buscar=None):
    """¿Pregunta un dato concreto de un juego (compatibilidad, versión, requisitos, fecha…)? Solo preguntas, nunca órdenes."""
    t = _t(frase)
    if not t or es_orden(frase) or not _DATO.search(t):
        return False
    return bool(_JUEGO.search(t) or juego_de(frase, contexto, buscar))


_SI_FUNCIONA = re.compile(r"\b(?:funciona|funcionara|va (?:en|bien)|corre en|se puede jugar|puedo jugar|hay que|hace falta|necesit\w*|requiere|pide|"
                          r"nativ[oa]s?|compatible|does it (?:work|run|need)|will it run|is it native|need(?:s)?)\b")


def pide_compatibilidad(frase):
    """¿Pregunta SI funciona en Linux o si necesita Proton? Lo decide el código. «¿Cuál es la mejor versión de Proton?» no: eso se busca."""
    t = _t(frase)
    return bool(_COMPATIBILIDAD.search(t) and _SI_FUNCIONA.search(t)) and not es_orden(frase) and not re.search(r"\b(?:cual|que) (?:es la )?(?:mejor )?version\b", t)


def discute_un_dato(frase):
    """¿Dice que la respuesta anterior está mal («creo que estás equivocado», «eso no es así»)?"""
    return bool(_DISCUTE.search(_t(frase)))


def consultar(appid, get=None):
    """{linux: bool|None, nivel: str|None} de la ficha de Steam y de ProtonDB, o None si ninguna de las dos responde."""
    get = get or requests.get
    linux = nivel = None
    try:
        r = get("https://store.steampowered.com/api/appdetails", params={"appids": appid, "filters": "platforms"},
                headers={"User-Agent": IA.AGENTE}, timeout=TIMEOUT)
        datos = (r.json() or {}).get(str(appid), {}) if r.ok else {}
        if datos.get("success"):
            linux = bool((datos.get("data") or {}).get("platforms", {}).get("linux"))
    except (requests.RequestException, ValueError, AttributeError) as e:
        log(f"Steam (ficha {appid}): {type(e).__name__}")
    try:
        r = get(f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json", headers={"User-Agent": IA.AGENTE}, timeout=TIMEOUT)
        nivel = str((r.json() or {}).get("tier") or "") or None if r.ok else None
    except (requests.RequestException, ValueError, AttributeError) as e:
        log(f"ProtonDB ({appid}): {type(e).__name__}")
    if linux is None and nivel is None:
        return None
    return {"linux": linux, "nivel": nivel}


def appid_por_nombre(nombre, get=None):
    """El número de Steam de un juego que no está en tu biblioteca, con el buscador de la tienda (solo envía el nombre). None si no lo encuentra."""
    try:
        r = (get or requests.get)("https://store.steampowered.com/api/storesearch/", params={"term": str(nombre)[:80], "l": "spanish", "cc": "ES"},
                                  headers={"User-Agent": IA.AGENTE}, timeout=TIMEOUT)
        items = (r.json() or {}).get("items") or [] if r.ok else []
    except (requests.RequestException, ValueError, AttributeError) as e:
        log(f"Steam (buscar «{nombre}»): {type(e).__name__}")
        return None
    return (str(items[0].get("id")), str(items[0].get("name") or nombre)) if items and items[0].get("id") else None


def como_texto(nombre, datos):
    """Lo que recibe la IA: los hechos comprobados, para que conteste ella (A13: la respuesta la escribe la IA; el código solo vigila que no los contradiga)."""
    linux = {True: "sí", False: "NO (se juega con Proton)", None: "no se sabe"}[datos.get("linux")]
    nivel = datos.get("nivel")
    protondb = f"{nivel} ({T(NIVELES[nivel])})" if nivel in NIVELES else "sin datos"
    return (f"DATOS COMPROBADOS en la tienda de Steam y en ProtonDB para {nombre}: versión para Linux: {linux}; ProtonDB: {protondb}. Contesta con estos datos, "
            "en una o dos frases cortas para la voz y sin cifras, y di que salen de la tienda de Steam y de ProtonDB. No digas nada que los contradiga.")


_DICE_NATIVO = re.compile(r"\b(?:es nativ[oa]|version nativa|tiene version (?:nativa )?para linux|funciona (?:de forma )?nativ\w*|no (?:necesita|hace falta|requiere) proton)\b")
_DICE_PROTON = re.compile(r"\b(?:no tiene version (?:nativa )?para linux|no es nativ[oa]|necesita proton|requiere proton|hace falta proton|se juega con proton)\b")


def contradice(texto, datos):
    """¿La respuesta dice lo contrario de lo comprobado? Con linux: false no puede decir que es nativo; con linux: true, que necesita Proton."""
    t = re.sub(r"\b(?:no tiene (?:una )?version (?:nativa )?para linux|no es nativ[oa]|no (?:tiene|hay) version nativa)\b", " sin linux ", C.normalizar(texto))
    if datos.get("linux") is False:
        return bool(_DICE_NATIVO.search(t))
    if datos.get("linux") is True:
        return bool(_DICE_PROTON.search(C.normalizar(texto)))
    return False


def correccion(nombre, datos):
    if datos.get("linux") is False:
        return T("Corrijo: según la tienda de Steam, {juego} no tiene versión para Linux; se juega con Proton.", juego=nombre)
    return T("Corrijo: según la tienda de Steam, {juego} tiene versión para Linux, así que no necesita Proton.", juego=nombre)

