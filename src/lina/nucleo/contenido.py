# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""«Ponme el partido del Barça contra el Sevilla»: el código busca la página para verlo y la elige, sin IA.

Dejar que la IA elija el enlace salía distinto cada vez (la portada, la programación del canal, una noticia, la ficha de la temporada pasada o la de otra
competición). Aquí se busca dentro de las plataformas oficiales (primero la que el usuario dijo que usa, si lo dijo), se descarta con las mismas reglas
que vigilan a la IA (turnos.pagina_que_no_es: portada, guía, noticia, otra temporada, otro país, que no lo nombre) y se elige la mejor. Si no hay una
clara, None: entonces lo intenta la IA, como siempre. Lo que se abre pasa por el ejecutor de siempre (xdg-open), con sus reglas.
"""
import re
from urllib.parse import urlparse

from lina.nucleo import comandos as C
from lina.nucleo import turnos as TU

# Plataformas oficiales donde buscar la página de un partido, por orden (si no dices cuál usas). Solo se abren direcciones de estas webs.
PLATAFORMAS_DEPORTE = ("movistarplus.es", "dazn.com")
NOMBRES = {"movistarplus.es": ("movistar",), "dazn.com": ("dazn",)}
NOMBRE_VISIBLE = {"movistarplus.es": "Movistar Plus", "dazn.com": "DAZN"}
_ES_DEPORTE = re.compile(r"\b(?:partido|partidazo|clasico|derbi|liga|laliga|jornada|champions|copa|contra|vs|versus|match|game)\b")
_FEMENINO = re.compile(r"(?:^|[/_-])(?:liga-f|femenin[ao]s?|women|wsl|nwsl)(?:[/_-]|$)")
_PIDE_FEMENINO = re.compile(r"\b(?:femenino|femenina|liga f|women|womens)\b")


def es_deporte(peticion):
    """¿Pide poner un partido (y no una serie o un vídeo)?"""
    return bool(_ES_DEPORTE.search(C.normalizar(peticion)))


def consulta(peticion):
    """Las palabras que identifican el partido, en su orden («barcelona sevilla»)."""
    distintivas = TU.palabras_distintivas(peticion)
    vistas, palabras = set(), []
    for p in C.normalizar(peticion).split():
        p = TU._SINONIMOS.get(p, p)
        if p in distintivas and p not in vistas:
            vistas.add(p)
            palabras.append(p)
    return " ".join(palabras)


# Varias búsquedas a la vez dentro de cada plataforma: el buscador devuelve cosas distintas según las palabras (medido: con «partido ficha» o «jornada ficha
# ver» la ficha del partido sale siempre; con «ficha» a secas o con la temporada, no).
CONSULTAS = ("{} partido ficha", "{} jornada ficha ver", "{} ficha ver")
MAXIMO = 15


def plataformas(preferencias=()):
    """Dónde buscar, por orden: primero la que dijiste que usas («el fútbol lo veo en Movistar Plus»), luego las demás."""
    texto = C.normalizar(" ".join(preferencias or ()))
    primero = [d for d in PLATAFORMAS_DEPORTE if any(n in texto for n in NOMBRES.get(d, ()))]
    return primero + [d for d in PLATAFORMAS_DEPORTE if d not in primero]


def _encaja(res, peticion, dominio):
    """Puntos de un resultado (más = mejor) o None si no vale: tiene que ser de esa web y pasar las reglas de turnos.pagina_que_no_es."""
    url, titulo = str(res.get("url") or ""), str(res.get("title") or "")
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not (p.netloc == dominio or p.netloc.endswith("." + dominio)):
        return None
    pide_femenino = bool(_PIDE_FEMENINO.search(C.normalizar(peticion)))
    if bool(_FEMENINO.search(p.path.lower())) != pide_femenino:
        return None                                           # sin decir «femenino», el partido es el de la competición masculina (y al revés)
    acciones = [("buscar_web", {}, f"[1] {titulo} ({dominio}) {url}"), ("ejecutar_comando", {"comando": f"xdg-open {url}"}, "")]
    if TU.pagina_que_no_es(acciones, peticion, lambda c: False):
        return None
    ruta = C.normalizar(p.path.replace("-", " ").replace("/", " ")).split()
    titulo_palabras = {TU._SINONIMOS.get(t, t) for t in C.normalizar(titulo).split()}
    distintivas = TU.palabras_distintivas(peticion)
    if not all(d in ruta or d in titulo_palabras for d in distintivas):
        return None                                           # tienen que estar TODAS (los dos equipos): «Racing - Sevilla» no es «Barça - Sevilla»
    return sum(1 for d in distintivas if d in ruta) * 2 + (1 if TU._PAGINA_DE_CONTENIDO.search(p.path.lower()) else 0)


def buscar(peticion, preferencias=(), resultados_de=None):
    """(dirección, plataforma, título) de la página para ver lo pedido, o None si no hay una clara (entonces decide la IA)."""
    if resultados_de is None:
        from lina.nucleo import ia as IA
        resultados_de = IA.resultados_tavily
    q = consulta(peticion)
    if not q:
        return None
    from concurrent.futures import ThreadPoolExecutor
    for dominio in plataformas(preferencias):
        with ThreadPoolExecutor(max_workers=len(CONSULTAS)) as hilos:
            tandas = list(hilos.map(lambda plantilla, d=dominio: resultados_de(plantilla.format(q), d, maximo=MAXIMO), CONSULTAS))
        if all(isinstance(t, str) for t in tandas):
            return None                                       # sin búsqueda (sin clave o sin red): que lo intente la IA
        resultados, vistas = [], set()
        for tanda in tandas:
            for res in tanda if not isinstance(tanda, str) else []:
                if res.get("url") not in vistas:
                    vistas.add(res.get("url"))
                    resultados.append(res)
        buenos = []
        for res in resultados:
            puntos = _encaja(res, peticion, dominio)
            if puntos is not None:
                buenos.append((puntos, res))
        if not buenos:
            continue
        competiciones = TU.competiciones_de_ahora([r.get("url", "") for _, r in buenos])
        if len(competiciones) > 1:
            return None                                       # dos competiciones distintas que encajan: no adivina
        buenos.sort(key=lambda x: -x[0])
        mejor = buenos[0][1]
        return str(mejor["url"]), dominio, str(mejor.get("title") or "")
    return None
