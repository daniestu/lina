# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Decisiones sobre cómo cerrar una petición: qué cuenta como trabajo real, y con qué frase se describe lo que se aprende.

Son funciones puras (sin audio ni red) para poder probarlas solas.
"""
import re

from lina.nucleo import comandos as C

# Herramientas que solo preparan el trabajo (cargar más herramientas, pensar a fondo): por sí solas no hacen ni comprueban nada en el equipo.
HERRAMIENTAS_META = {"mas_herramientas", "pensar_a_fondo"}


def solo_herramientas_meta(acciones):
    """True si en la petición solo se llamó a herramientas «meta»: se cargó material pero no se hizo ni se leyó nada del equipo."""
    return bool(acciones) and all(a[0] in HERRAMIENTAS_META for a in acciones)


_SEGUIMIENTO = re.compile(r"^(?:no|nada|sigue|todavia|aun|eso|otra vez|ahora|gracias|vale|has|ya|si|pero|perfecto|bien|genial)\b")


def es_seguimiento(texto):
    """¿Es una frase corta que reacciona a lo anterior («No lo has hecho», «Ahora sí, gracias») y no una petición nueva?"""
    t = C.normalizar(texto)
    return len(t.split()) <= 8 and bool(_SEGUIMIENTO.match(t))


def peticion_de_receta(historial, actual):
    """La petición que describe de verdad lo que se apunta en una receta: si lo último que dijiste es un seguimiento o una queja, la anterior."""
    if not es_seguimiento(actual):
        return actual
    for h in reversed(historial or []):
        if h.get("rol") == "user" and not es_seguimiento(h.get("texto", "")):
            return h["texto"]
    return actual


# Órdenes que piden HACER algo en el equipo (no una respuesta): con ellas, informar no es cumplir.
_ACCION_ES = re.compile(r"^(?:(?:oye|vale|venga|por favor|puedes|me puedes|podrias)\s+)*(?:pon|ponme|ponlo|ponla|ponmelo|ponmela|abre|abreme|reproduce|reproduceme|"
                        r"enciende|apaga|cierra|lanza|inicia|arranca|instala|descarga|activa|desactiva|conecta|desconecta|quiero ver|dejame ver)\b")
_ACCION_EN = re.compile(r"^(?:(?:hey|ok|please|can you|could you)\s+)*(?:put on|put|play|open|turn on|turn off|start|launch|install|download|enable|disable|"
                        r"connect|disconnect|i want to watch|let me watch)\b")
# Herramientas que solo informan (buscan, leen, miran): no hacen nada en el equipo.
HERRAMIENTAS_DE_INFORMAR = HERRAMIENTAS_META | {"buscar_web", "leer_web", "buscar_youtube", "mirar_pantalla", "ver_pantalla", "buscar_ajuste_kde",
                                                "buscar_clave_en_binarios", "observar_config", "ver_diario", "ver_recetas", "ver_juegos", "ver_gasto",
                                                "mis_ajustes", "ver_papelera", "usar_receta"}


def pide_accion(texto):
    """¿La frase pide hacer algo («ponme el partido», «abre Steam») y no solo saber algo («¿a qué hora es el partido?»)?"""
    from lina.nucleo import idioma as IDI
    t = C.normalizar(texto)
    return bool((_ACCION_EN if IDI.actual() == "en" else _ACCION_ES).match(t))


def solo_se_informo(acciones, es_lectura):
    """True si en la petición solo se buscó, leyó o miró (ningún comando que cambie o abra algo). `es_lectura(comando)` dice si un comando solo lee."""
    if not acciones:
        return True
    for nombre, args, _ in acciones:
        if nombre in HERRAMIENTAS_DE_INFORMAR:
            continue
        if nombre == "ejecutar_comando" and es_lectura(str((args or {}).get("comando", ""))):
            continue
        return False
    return True


# Órdenes de PONER algo para verlo u oírlo: abrir solo la portada de la plataforma no es ponerlo.
_CONTENIDO_ES = re.compile(r"^(?:(?:oye|vale|venga|por favor|puedes|me puedes|podrias)\s+)*(?:pon|ponme|ponlo|ponla|ponmelo|ponmela|reproduce|reproduceme|"
                           r"quiero ver|dejame ver)\b")
_CONTENIDO_EN = re.compile(r"^(?:(?:hey|ok|please|can you|could you)\s+)*(?:put on|put|play|i want to watch|let me watch)\b")
_URL = re.compile(r"https?://[^\s'\"]+")


def pide_contenido(texto):
    """¿Pide que le PONGAS algo (un partido, una serie, un vídeo), y no solo abrir un programa o una web?"""
    from lina.nucleo import idioma as IDI
    return bool((_CONTENIDO_EN if IDI.actual() == "en" else _CONTENIDO_ES).match(C.normalizar(texto)))


def solo_portadas(acciones, es_lectura):
    """La portada que se abrió (p. ej. «www.movistarplus.es») si, aparte de buscar y leer, lo único que se hizo fue abrir portadas de webs (sin ruta ni
    parámetros); None si se abrió una página concreta, se hizo otra cosa o no se abrió nada."""
    from urllib.parse import urlparse
    portada = None
    for nombre, args, _ in acciones or []:
        if nombre in HERRAMIENTAS_DE_INFORMAR:
            continue
        comando = str((args or {}).get("comando", "")) if nombre == "ejecutar_comando" else ""
        if nombre == "ejecutar_comando" and es_lectura(comando):
            continue
        urls = _URL.findall(comando)
        if not urls or len(comando.split()) > 1 + len(urls):
            return None
        for u in urls:
            p = urlparse(u)
            if p.path not in ("", "/") or p.query or p.fragment:
                return None
            portada = p.netloc
    return portada


# Palabras de una petición que NO identifican el contenido (verbos, artículos, «partido», «navegador»…): lo que queda tiene que aparecer en lo que se abre.
_PALABRAS_DE_RELLENO = {
    "pon", "ponme", "ponlo", "ponla", "ponmelo", "ponmela", "reproduce", "reproduceme", "quiero", "ver", "dejame", "oye", "vale", "venga", "por", "favor",
    "puedes", "podrias", "el", "la", "los", "las", "un", "una", "del", "de", "en", "al", "a", "y", "o", "con", "contra", "que", "me", "mi", "hoy", "ahora",
    "partido", "partidazo", "encuentro", "navegador", "rayador", "brave", "firefox", "chrome", "directo", "vivo", "online", "television", "tele", "canal",
    "serie", "pelicula", "capitulo", "episodio", "video", "temporada", "favor",
    "put", "on", "play", "the", "match", "game", "in", "browser", "i", "want", "to", "watch", "let", "live", "now", "today", "please", "of", "vs", "versus",
}
_SINONIMOS = {"barca": "barcelona", "atleti": "atletico"}
# Páginas que no son el contenido aunque lo nombren: guías de programación, calendarios, agendas.
_PAGINA_DE_GUIA = re.compile(r"(?:^|[/_-])(?:programacion(?:-tv)?|parrilla|guia(?:-tv)?|calendario|agenda|horarios?|schedule|tv-guide|fixtures|"
                             r"news|noticias?|blog|articulos?|article|comunicacion|prensa)(?:[/_.-]|$)")


def palabras_distintivas(texto):
    """Las palabras que identifican lo que se pidió poner («barcelona», «sevilla», «stranger», «things»), sin verbos, artículos ni palabras genéricas."""
    return {_SINONIMOS.get(p, p) for p in C.normalizar(texto).split() if len(p) >= 3 and p not in _PALABRAS_DE_RELLENO and not p.isdigit()}


def pagina_que_no_es(acciones, pregunta, es_lectura):
    """Tras «pon…»: (dirección, motivo) si lo que se abrió NO es la página de lo pedido (una portada, una guía de programación o una página que no lo
    nombra); None si se abrió algo que sí lo es, si se hizo otra cosa o si no se abrió nada."""
    from urllib.parse import urlparse
    abiertas = []
    for nombre, args, _ in acciones or []:
        if nombre in HERRAMIENTAS_DE_INFORMAR:
            continue
        comando = str((args or {}).get("comando", "")) if nombre == "ejecutar_comando" else ""
        if nombre == "ejecutar_comando" and es_lectura(comando):
            continue
        urls = _URL.findall(comando)
        if not urls or len(comando.split()) > 1 + len(urls):
            return None
        abiertas += [u.strip("'\"") for u in urls]
    if not abiertas:
        return None
    distintivas = palabras_distintivas(pregunta)
    titulos = {}                                                  # dirección → título, de los resultados de buscar_web («[1] Título (web) https://…»)
    for nombre, _, resultado in acciones or []:
        if nombre == "buscar_web":
            for m in re.finditer(r"^\[\d+\] (.*) \([^)]*\) (https?://\S+)$", str(resultado), re.M):
                titulos[m.group(2).rstrip("/")] = m.group(1)
    for u in abiertas:
        p = urlparse(u)
        if p.path in ("", "/") and not p.query and not p.fragment:
            if distintivas and any(d in C.normalizar(p.netloc).replace(" ", "") for d in distintivas):
                return None                                   # «ponme Movistar Plus»: su portada es justo lo pedido
            continue
        if _PAGINA_DE_GUIA.search(p.path.lower()) or de_otra_temporada(u):
            continue
        texto_url = C.normalizar(f"{p.netloc} {p.path} {p.query}").replace(" ", "")
        titulo = C.normalizar(titulos.get(u.rstrip("/"), "")).split()
        if not distintivas or any(d in texto_url for d in distintivas) or any(d in {_SINONIMOS.get(t, t) for t in titulo} for d in distintivas):
            return None                                       # esta sí es la página de lo pedido (o no hay con qué comparar)
    u = abiertas[-1]
    p = urlparse(u)
    if p.path in ("", "/") and not p.query and not p.fragment:
        return u, f"solo se ha abierto la portada de {p.netloc}"
    if _PAGINA_DE_GUIA.search(p.path.lower()):
        return u, f"lo que se abrió ({u}) es una guía de programación, un calendario o una noticia, no la página para verlo"
    if de_otra_temporada(u):
        a, b = temporada_actual()
        return u, f"lo que se abrió ({u}) es de la temporada {de_otra_temporada(u)}, no de la actual ({a:02d}-{b:02d})"
    return u, f"lo que se abrió ({u}) no nombra lo que pidió ({', '.join(sorted(distintivas))})"


# Temporadas deportivas en direcciones y títulos: «25-26», «2025-26», «2025/2026». La actual va de julio a junio.
_TEMPORADA = re.compile(r"(?<!\d)(?:20)?(\d{2})[-/_](?:20)?(\d{2})(?!\d)")


def temporada_actual(hoy=None):
    """(26, 27) en octubre de 2026; (25, 26) en mayo de 2026 (la temporada empieza en julio)."""
    import datetime
    hoy = hoy or datetime.date.today()
    inicio = hoy.year if hoy.month >= 7 else hoy.year - 1
    return inicio % 100, (inicio + 1) % 100


def temporadas_en(texto):
    """Las temporadas que aparecen en un texto, como (25, 26). Solo pares seguidos (25-26), para no confundirlas con fechas (2026-10-25)."""
    return {(int(a), int(b)) for a, b in _TEMPORADA.findall(str(texto or "")) if (int(a) + 1) % 100 == int(b)}


def de_otra_temporada(texto, hoy=None):
    """La temporada («25-26») si el texto es de una temporada que NO es la actual; None si es la actual o no dice ninguna."""
    vistas = temporadas_en(texto)
    actual = temporada_actual(hoy)
    if not vistas or actual in vistas:
        return None
    a, b = sorted(vistas)[-1]
    return f"{a:02d}-{b:02d}"



def competicion_de(url):
    """«laliga-ea-sports» de «…/laliga-ea-sports-26-27/…»: el trozo de la dirección que lleva la temporada, sin ella (o None si no lleva temporada)."""
    from urllib.parse import urlparse
    for trozo in urlparse(str(url or "")).path.split("/"):
        if temporadas_en(trozo):
            return _TEMPORADA.sub("", trozo).strip("-_") or None
    return None


def competiciones_de_ahora(urls, hoy=None):
    """Las competiciones distintas entre las direcciones de la temporada actual (para avisar si hay varias que encajan: LaLiga y Liga F…)."""
    vistas = []
    for u in urls:
        c = competicion_de(u)
        if c and not de_otra_temporada(u, hoy) and c not in vistas:
            vistas.append(c)
    return vistas
