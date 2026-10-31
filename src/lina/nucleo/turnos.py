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
_CON_POR_PON = r"con(?=\s+(?:el|la|los|las|un|una)\b)|"          # «con el partido del Barça»: Whisper oyó «con» donde dijiste «pon»
_ACCION_ES = re.compile(r"^(?:(?:oye|vale|venga|por favor|puedes|me puedes|podrias)\s+)*(?:" + _CON_POR_PON + r"pon|ponme|ponlo|ponla|ponmelo|ponmela|abre|abreme|reproduce|reproduceme|"
                        r"enciende|apaga|cierra|lanza|inicia|arranca|instala|descarga|activa|desactiva|conecta|desconecta|quiero ver|dejame ver)\b")
_ACCION_EN = re.compile(r"^(?:(?:hey|ok|please|can you|could you)\s+)*(?:put on|put|play|open|turn on|turn off|start|launch|install|download|enable|disable|"
                        r"connect|disconnect|i want to watch|let me watch)\b")
# Herramientas que solo informan (buscan, leen, miran): no hacen nada en el equipo.
HERRAMIENTAS_DE_INFORMAR = HERRAMIENTAS_META | {"buscar_web", "leer_web", "buscar_youtube", "mirar_pantalla", "ver_pantalla", "buscar_ajuste_kde",
                                                "buscar_clave_en_binarios", "observar_config", "ver_diario", "ver_recetas", "ver_juegos", "ver_gasto",
                                                "mis_ajustes", "ver_papelera", "usar_receta", "necesito_datos_actuales"}


# Para la última red de honestidad vale cualquier orden de hacer algo, no solo las que tienen reintento: «sube», «borra», «cambia», «crea», «reinicia»…
_HACER_ES = re.compile(r"^(?:(?:oye|vale|venga|por favor|puedes|me puedes|podrias)\s+)*(?:sube|baja|borra|elimina|mueve|copia|crea|cambia|pausa|quita|silencia|reinicia|actualiza|"
                       r"desinstala|guarda|renombra|escribe|envia|manda|configura|ajusta|ejecuta|limpia|vacia|minimiza|maximiza|suspende)(?:me|lo|la|los|las|le|melo|mela)?\b")
_HACER_EN = re.compile(r"^(?:(?:hey|ok|please|can you|could you)\s+)*(?:raise|lower|delete|remove|move|copy|create|change|pause|mute|restart|update|uninstall|save|rename|write|send|"
                       r"configure|adjust|run|clean|empty|minimize|maximize|close|stop)\b")


def pide_hacer(texto):
    """¿La frase pide hacer CUALQUIER cosa en el equipo (no saber algo)? Más amplio que pide_accion, para no dar nada por hecho sin que conste."""
    from lina.nucleo import idioma as IDI
    if pide_accion(texto):
        return True
    if "?" in str(texto) or "¿" in str(texto):
        return False
    return bool((_HACER_EN if IDI.actual() == "en" else _HACER_ES).match(C.normalizar(texto)))


# Lo que devuelve una herramienta cuando NO ha hecho lo que se le pedía
_NO_HECHO = re.compile(r"^(?:BLOQUEADO|PREPARADO|TOPE ALCANZADO|No |Falta |Hay varios|Intenté |La herramienta ha fallado|Error|código de salida: [1-9])")


def sin_efecto(acciones, es_lectura):
    """(True, motivo) si en esta petición NINGUNA acción consta como hecha: no se hizo nada, solo se leyó, o todo lo intentado falló (motivo: lo que dijo
    la última que falló, o ""). (False, "") si alguna hizo algo: una herramienta que no dice que ha fallado cuenta como hecha."""
    motivo = ""
    for nombre, args, resultado in acciones or []:
        if nombre in HERRAMIENTAS_DE_INFORMAR or (nombre == "ejecutar_comando" and es_lectura(str((args or {}).get("comando", "")))):
            continue
        if not _NO_HECHO.match(str(resultado)):
            return False, ""
        motivo = str(resultado)
    return True, motivo


_FUENTE_PIDE_ES = re.compile(r"\bfuentes?\b|\b(?:usa|uses|usar|utiliza|utilices|utilizar|guarda|guardes|guardar|apunta|apuntes|apuntar|anade|anadas|anadir|quita|quites|quitar|borra|borres|borrar|elimina|elimines|eliminar)\b.*\b(?:pagina|web|enlace|sitio)\b")
_FUENTE_PIDE_EN = re.compile(r"\bsources?\b|\b(?:use|save|add|remove|delete)\b.*\b(?:page|website|site|link)\b")
_FUENTE_OBJETO_ES = re.compile(r"\b(?:fuentes?|pagina|web|enlace|sitio)\b")
_FUENTE_OBJETO_EN = re.compile(r"\b(?:sources?|page|website|site|link)\b")
_FUENTE_HECHO_ES = re.compile(r"\b(?:(?:guardad|apuntad|anadid)[ao]s?|(?:quitad|borrad|eliminad)[ao]s?)\b")
_FUENTE_HECHO_EN = re.compile(r"\b(?:saved|added|removed|deleted)\b")


def afirma_fuente(peticion, respuesta):
    """«guardar» o «quitar» si, ante una orden sobre una fuente, la respuesta dice haberlo hecho; None si no (también si lo niega o si solo se pregunta)."""
    from lina.nucleo import idioma as IDI
    if "?" in str(peticion) or "¿" in str(peticion):
        return None
    en = IDI.actual() == "en"
    p, r = C.normalizar(peticion), C.normalizar(respuesta)
    if not (_FUENTE_PIDE_EN if en else _FUENTE_PIDE_ES).search(p) or not (_FUENTE_OBJETO_EN if en else _FUENTE_OBJETO_ES).search(r):
        return None
    m = (_FUENTE_HECHO_EN if en else _FUENTE_HECHO_ES).search(r)
    if not m or re.search(r"\b(?:no|not|n t)\b(?:\s+\S+){0,3}\s*$", r[:m.start()]):
        return None
    return "quitar" if m.group(0)[:3] in ("qui", "bor", "eli", "rem", "del") else "guardar"


def motivo_corto(texto, maximo=160):
    """La primera frase de lo que dijo una herramienta, para decirla en voz alta."""
    t = " ".join(str(texto).split())
    t = re.sub(r"^código de salida: \d+ \([^)]*\)\s*", "", t)
    primera = re.split(r"(?<=[.:;])\s", t, maxsplit=1)[0].rstrip(".:; ")
    return primera[:maximo]


# Preguntas sobre lo que acaba de pasar, o afirmaciones que buscan tu acuerdo («…, ¿no?»): ahí no vale contestar de memoria ni dar la razón.
_LO_ANTERIOR_ES = re.compile(r"\b(?:por que (?:ha|has|habia|habias|no|fallo|te|se)\b|que (?:ha|habia) pasado|que paso\b|que ha fallado|como es que|o sea que|entonces es que\b|entonces (?:si|no) (?:que )?(?:funciono|ha|has|habia|fue|estaba)\b|"
                             r"lo has (?:hecho|abierto|puesto|cerrado|conseguido)|ha funcionado|funciono\b|seguro que)")
_LO_ANTERIOR_EN = re.compile(r"\b(?:why (?:did|didn t|has|hasn t|was|wasn t)\b|what happened|what went wrong|so (?:it|you)\b|did (?:it|you) (?:work|open|do|manage)|are you sure)")
_BUSCA_ACUERDO = re.compile(r"\b(?:no|verdad|cierto|right|correct)\s*\?\s*$", re.I)


def pregunta_por_lo_anterior(texto):
    """¿Pregunta qué pasó antes o por qué, o busca que le des la razón («…, ¿no?»)?"""
    from lina.nucleo import idioma as IDI
    return bool(_BUSCA_ACUERDO.search(str(texto)) or (_LO_ANTERIOR_EN if IDI.actual() == "en" else _LO_ANTERIOR_ES).search(C.normalizar(texto)))


def hechos_de_peticion(acciones, es_lectura, peticion="", maximo=6):
    """Lo que consta que pasó en una petición, escrito por el código: cada herramienta con su resultado (las iguales seguidas, juntas). Solo datos."""
    lineas = []
    for nombre, args, resultado in acciones or []:
        if nombre in HERRAMIENTAS_META:
            continue
        args = args or {}
        dato = str(args.get("comando") or args.get("nombre") or args.get("consulta") or args.get("url") or "")[:80]
        r = str(resultado)
        m = re.match(r"código de salida: (\d+)", r)
        linea = f"{nombre} {dato}".strip() + " → " + (f"código {m.group(1)}: " if m else "") + motivo_corto(r, 100)
        if lineas and lineas[-1][0] == linea:
            lineas[-1][1] += 1
        else:
            lineas.append([linea, 1])
    hechos = [t + (f" (×{n})" if n > 1 else "") for t, n in lineas[-maximo:]] or ["no se usó ninguna herramienta"]
    if pide_hacer(peticion) and sin_efecto(acciones, es_lectura)[0]:
        hechos.append("no consta que se hiciera lo pedido")
    return hechos


def nota_de_hechos(registros):
    """El aviso para la IA con lo que consta de las últimas peticiones ('' si no hay ninguna)."""
    if not registros:
        return ""
    lineas = [f"- {r['hora']} «{r['pedido']}»: {'; '.join(r['hechos'])}. Respondiste: «{r['dijo']}»." for r in registros]
    return ("HECHOS REGISTRADOS POR EL CÓDIGO en las últimas peticiones. Es lo único que consta; lo que respondiste entonces NO es prueba de nada:\n" + "\n".join(lineas) +
            "\nExplica solo lo que se deduzca de estos hechos o de lo que compruebes ahora. Si no consta la causa, di que no lo sabes: no la supongas. Si el usuario afirma algo que "
            "estos hechos contradicen o no respaldan, díselo con claridad y no le des la razón.")


def pide_accion(texto):
    """¿La frase pide hacer algo («ponme el partido», «abre Steam») y no solo saber algo («¿a qué hora es el partido?»)?"""
    from lina.nucleo import idioma as IDI
    if "?" in str(texto) or "¿" in str(texto):          # una pregunta («¿con el volumen así está bien?») no es una orden
        return False
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
_CONTENIDO_ES = re.compile(r"^(?:(?:oye|vale|venga|por favor|puedes|me puedes|podrias)\s+)*(?:" + _CON_POR_PON + r"pon|ponme|ponlo|ponla|ponmelo|ponmela|reproduce|reproduceme|"
                           r"quiero ver|dejame ver)\b")
_CONTENIDO_EN = re.compile(r"^(?:(?:hey|ok|please|can you|could you)\s+)*(?:put on|put|play|i want to watch|let me watch)\b")
_URL = re.compile(r"https?://[^\s'\"]+")


def pide_contenido(texto):
    """¿Pide que le PONGAS algo (un partido, una serie, un vídeo), y no solo abrir un programa o una web?"""
    from lina.nucleo import idioma as IDI
    if "?" in str(texto) or "¿" in str(texto):
        return False
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
    "serie", "pelicula", "capitulo", "episodio", "video", "temporada", "favor", "femenino", "femenina", "masculino", "masculina", "liga", "laliga",
    "put", "on", "play", "the", "match", "game", "in", "browser", "i", "want", "to", "watch", "let", "live", "now", "today", "please", "of", "vs", "versus",
}
_SINONIMOS = {"barca": "barcelona", "atleti": "atletico"}
# Cómo suele llamarse la dirección de la página de UN contenido (ficha, partido, título, vídeo…). Si lo que se pidió solo sale en el título del resultado y
# no en la dirección, la dirección tiene que parecerse a esto: una sección de la portada («/es-ES/home/…») no es la página del partido.
_PAGINA_DE_CONTENIDO = re.compile(r"(?:^|[/_-])(?:ficha|fixture|event|evento|eventos|match|partido|watch|ver|title|titulo|video|player|play|episode|episodio|"
                                  r"movie|pelicula|serie|series|show|programa|directo|live)(?:[/_.:?=-]|$)")
# Páginas que no son el contenido aunque lo nombren: guías de programación, calendarios, agendas.
_PAGINA_DE_GUIA = re.compile(r"(?:^|[/_-])(?:programacion(?:-tv)?|parrilla|guia(?:-tv)?|calendario|agenda|horarios?|schedule|tv-guide|fixtures|"
                             r"news|noticias?|blog|articulos?|articles?|comunicacion|prensa|tudum|collections?|colecciones|coleccion|browse|"
                             r"categor(?:y|ies|ia|ias))(?:[/_.-]|$)")


def enlace_sin_comprobar(acciones, plataformas, es_lectura, pregunta=""):
    """La última ficha de una plataforma de vídeo (Netflix, Movistar…) que se ha ABIERTO en esta petición sin que su identificador haya salido de ningún
    resultado (una búsqueda, una página leída, la salida de un comando) ni de lo que dijiste: un número que la IA ha sacado de su memoria (o inventado).
    Devuelve (dirección, dominio) o None."""
    from urllib.parse import urlparse
    abierta, quien = None, None
    for i, (nombre, args, _) in enumerate(acciones or []):
        if nombre in HERRAMIENTAS_DE_INFORMAR or nombre != "ejecutar_comando":
            continue
        comando = str((args or {}).get("comando", ""))
        if es_lectura(comando) or re.search(r"\b(?:curl|wget|python3?|grep)\b", comando):
            continue                                              # leer una página no es abrirla
        for u in _URL.findall(comando):
            u = u.strip("'\"")
            dominio = next((d for d in plataformas if urlparse(u).netloc == d or urlparse(u).netloc.endswith("." + d)), None)
            if dominio:
                abierta, quien = (u, dominio), i
    if not abierta:
        return None
    vistos = " ".join(str(r) for i, (_, _, r) in enumerate(acciones) if i != quien) + " " + str(pregunta)     # lo que devolvió abrirla no cuenta
    ruta = urlparse(abierta[0]).path
    ids = re.findall(r"\d{4,}", ruta) or [s for s in ruta.strip("/").split("/")[-1:] if len(s) >= 6]
    if not ids or all(i in vistos for i in ids):
        return None
    return abierta


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
        if _PAGINA_DE_GUIA.search(p.path.lower()) or de_otra_temporada(u) or de_otro_pais(u):
            continue
        texto_url = C.normalizar(f"{p.netloc} {p.path} {p.query}").replace(" ", "")
        titulo = C.normalizar(titulos.get(u.rstrip("/"), "")).split()
        lo_nombra_el_titulo = any(d in {_SINONIMOS.get(t, t) for t in titulo} for d in distintivas)
        if not distintivas or any(d in texto_url for d in distintivas) or (lo_nombra_el_titulo and _PAGINA_DE_CONTENIDO.search(p.path.lower())):
            return None                                       # esta sí es la página de lo pedido (o no hay con qué comparar)
    u = abiertas[-1]
    p = urlparse(u)
    if p.path in ("", "/") and not p.query and not p.fragment:
        return u, f"solo se ha abierto la portada de {p.netloc}"
    if _PAGINA_DE_GUIA.search(p.path.lower()):
        return u, f"lo que se abrió ({u}) es una guía de programación, un calendario o una noticia, no la página para verlo"
    if de_otro_pais(u):
        return u, f"lo que se abrió ({u}) es la versión de otro país ({de_otro_pais(u)}), no la tuya ({mi_pais_web()}): puede ser otro partido o no verse aquí"
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



_LOCALE_EN_RUTA = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


def mi_pais_web(entorno=None):
    """«es-ES» a partir de LANG/LC_ALL («es_ES.UTF-8»), como lo escriben las webs en sus direcciones; None si no se sabe."""
    import os
    entorno = os.environ if entorno is None else entorno
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        m = re.match(r"([a-z]{2})_([A-Z]{2})", entorno.get(var, "") or "")
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return None


# Webs que ponen el país como primer trozo de la dirección y el idioma como segundo («max.com/ar/es/…»): solo se reconocen estos países, para no confundir
# otras rutas de dos letras.
_PAISES = set(("ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bl bm bn bo bq br bs bt bv bw by bz ca cc cd cf cg ch ci ck cl "
                "cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg eh er es et fi fj fk fm fo fr ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk "
                "hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mf mg mh mk "
                "ml mm mn mo mp mq mr ms mt mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re ro rs ru rw sa "
                "sb sc sd se sg sh si sj sk sl sm sn so sr ss st sv sx sy sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug um us uy uz va vc ve vg vi vn vu "
                "wf ws ye yt za zm zw uk").split())


def de_otro_pais(url, entorno=None):
    """El país de la dirección («en-US», «ar») si es la versión de otro país distinto del tuyo; None si es el tuyo, no lo dice o no se sabe el tuyo."""
    from urllib.parse import urlparse
    mio = mi_pais_web(entorno)
    if not mio:
        return None
    trozos = [t for t in urlparse(str(url or "")).path.split("/") if t]
    for trozo in trozos:
        if _LOCALE_EN_RUTA.match(trozo) and trozo.lower() != mio.lower():
            return trozo
    pais = mio.split("-")[1].lower()
    if len(trozos) >= 2 and re.fullmatch(r"[a-z]{2}", trozos[0]) and re.fullmatch(r"[a-z]{2}", trozos[1]) and trozos[0] != pais:
        return trozos[0]                                      # «max.com/ad/es/…»: país e idioma (Andorra, aunque esté en español)
    if trozos and re.fullmatch(r"[a-z]{2}-[a-z]{2}", trozos[0]) and trozos[0][:2] != pais:
        return trozos[0]                                      # «netflix.com/tt-es/…»: país-idioma (Trinidad y Tobago, en español)
    if trozos and trozos[0] in _PAISES and trozos[0] != pais:
        return trozos[0]                                      # «netflix.com/us/…»
    return None
