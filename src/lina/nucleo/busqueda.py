# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""La búsqueda de `buscar_web` con ia.busqueda = «auto» (lo de fábrica): una escalera con lo que haya, sin pedirle nada al usuario.

  1. La búsqueda de Google dentro de Gemini, en una consulta aparte (junto a nuestras funciones da 400) y con «Busca en internet:» delante (sin eso, el
     modelo contestó de memoria 6 de 30). Con la clave de pago si queda tope este mes y, si no, con la de Gemini, que en las pruebas con la gratuita no
     pudo buscar: da un 429 sin detalle. Ese 429 sin plazo de espera es permanente: esa clave no se vuelve a probar hasta que cambies la clave de
     Gemini (con la de pago, también al día siguiente, porque puede ser el tope de gasto de tu cuenta de Google y lo puedes subir).
  2. Tavily, si hay clave (gratis: 1000 búsquedas al mes).
  3. DuckDuckGo, solo si lo enciendes (ia.busqueda_reserva): en las medidas nos tomó por un robot 59 de 60 veces. Como mucho una consulta cada
     INTERVALO_DUCKDUCKGO_SEG; si no toca, se salta sin esperar. No nos hacemos pasar por un navegador para esquivarlo.
  4. Wikipedia y algunas wikis de juegos (datos/wikis.toml), con su buscador MediaWiki, sin clave. Solo para lo enciclopédico: nada de precios,
     noticias, el tiempo, resultados ni lo de «hoy» (es_de_actualidad), y solo resultados que nombren algo de la consulta. Se lee el extracto de la
     página por su API (EXTRACTO_MAX caracteres, sin resumir por trozos: en la pasada gratis una pregunta gastó 8 llamadas de 20 al día).
Si nada da resultados, el motivo concreto de cada paso, para decirlo tal cual: nunca «no tengo acceso a internet».
Lo que sí encuentra se guarda CACHE_SEG (partidos, precios y noticias cambian: poco rato). Con «google», solo los pasos 1 y 3.
"""
import hashlib
import json
import re
import time
import tomllib
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urlparse

import requests

from lina.nucleo import aviso_busqueda as AVB
from lina.nucleo import claves as CL
from lina.nucleo import comandos as C
from lina.nucleo import ia as IA
from lina.nucleo import idioma as IDI
from lina.nucleo import proveedor_gemini as PG
from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T
from lina.nucleo.opcionales import PRES
from lina.nucleo.registro import log

MODELO_GOOGLE = "gemini-flash-lite-latest"          # el medido: 24 de 30 con búsqueda, mediana 1,4 s; con «Busca en internet:», 6 de 6 de las que faltaban
CACHE_SEG = 12 * 60
INTERVALO_DUCKDUCKGO_SEG = 30
PAUSA_GOOGLE_SEG = 600                               # tras un error que no es de cuota: un rato sin probar
ARCHIVO_GOOGLE = "busqueda_google.json"
WIKIS = RUT.PAQUETE / "datos" / "wikis.toml"
TIMEOUT_GOOGLE, TIMEOUT_WIKI = 12, 8
EXTRACTO_MIN, EXTRACTO_MAX = 1000, 3000              # el extracto de una wiki: la introducción y, si es muy corta, lo que siga hasta EXTRACTO_MAX
ESCALONES = {"auto": ("google", "tavily", "duckduckgo", "wiki"), "google": ("google", "duckduckgo")}

M_GOOGLE_GRATIS = N_("en las pruebas tu clave de Gemini no ha podido usar la búsqueda de Google")
M_GOOGLE_PAGO = N_("la búsqueda de Google con tu clave de pago ha dado un error 429 sin detalle (puede ser el tope de gasto de tu cuenta de Google)")
M_GOOGLE_FALLO = N_("la búsqueda de Google no ha respondido")
M_SIN_PAGO = N_("no tienes clave de pago de Gemini con saldo este mes")
M_SIN_TAVILY = N_("no tienes clave de Tavily")
M_TAVILY_FALLO = N_("Tavily no ha respondido")
M_TAVILY_LIMITE = N_("Tavily ha llegado a su límite")
M_TAVILY_NADA = N_("Tavily no ha encontrado nada")
M_DUCKDUCKGO = N_("DuckDuckGo no ha respondido o me ha bloqueado")
M_DUCKDUCKGO_PRONTO = N_("a DuckDuckGo le pregunté hace muy poco y no insisto")
M_WIKI_NADA = N_("Wikipedia y las wikis de juegos no tienen nada sobre esto")
M_WIKI_RED = N_("no he podido conectar con Wikipedia")
M_WIKI_ACTUALIDAD = N_("Wikipedia y las wikis no sirven para datos del momento como precios, noticias, el tiempo o resultados")

_cache: dict = {}
_pausa_google: dict = {}                              # huella de la clave -> hasta cuándo no se prueba (cuota por minuto u otro error)
_ultima_duckduckgo = [0.0]


@dataclass
class Resultado:
    resultados: list = field(default_factory=list)   # [{title, url, content, dominio?}]
    escalon: str = ""                                 # de dónde salieron: google · tavily · duckduckgo · wiki ("" si de ninguno)
    motivos: list = field(default_factory=list)      # por qué no dio nada cada paso que se probó (ya traducido)
    sin_tavily: bool = False                          # para sugerir la clave gratuita de Tavily


# ---------------------------------------------------------------- la búsqueda de Google dentro de Gemini
def huella(clave):
    return hashlib.sha256(str(clave).encode()).hexdigest()[:16]


def _bloqueos():
    try:
        d = json.loads((RUT.ESTADO / ARCHIVO_GOOGLE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _bloquear(clave, tipo, ahora=None):
    ahora = ahora or time.time()
    d = {h: v for h, v in _bloqueos().items() if isinstance(v, dict)}
    d[huella(clave)] = {"tipo": tipo, "desde": ahora, "hasta": IA._manana() if tipo == "pago" else None}
    d = dict(list(d.items())[-4:])                    # las claves de antes no importan: se queda lo último
    try:
        RUT.ESTADO.mkdir(parents=True, exist_ok=True)
        (RUT.ESTADO / ARCHIVO_GOOGLE).write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def bloqueo(clave, ahora=None):
    """{tipo, desde, hasta} si esta clave no se vuelve a probar con la búsqueda de Google (un 429 sin detalle), o None. Cambiar la clave lo levanta."""
    b = _bloqueos().get(huella(clave)) if clave else None
    if not isinstance(b, dict):
        return None
    if b.get("hasta") is not None and (ahora or time.time()) >= float(b["hasta"]):
        return None
    return b


def es_429_permanente(r):
    """Un 429 de ritmo dice cuánto esperar (RetryInfo) o qué cuota se pasó (QuotaFailure). El de «esta clave no puede» no trae ninguno: así respondió la
    gratuita en las pruebas, mientras la misma llamada sin la búsqueda daba 200."""
    try:
        detalles = r.json()["error"].get("details", [])
    except (ValueError, KeyError, TypeError, AttributeError):
        return False
    return not any(str(d.get("@type", "")).endswith(("RetryInfo", "QuotaFailure")) for d in detalles if isinstance(d, dict))


def _dominio(texto):
    d = IA.dominio_valido(texto)
    return d if d and "." in d else None


def resultados_de_google(datos, dominio=None):
    """[{title, url, dominio, content}] de la respuesta de Gemini con la búsqueda: un resultado por fuente, con las frases que se apoyan en ella. Los
    enlaces son de paso (vertexaisearch…): el dominio de verdad va en su título."""
    try:
        candidato = datos["candidates"][0]
        meta = candidato.get("groundingMetadata") or {}
        texto = " ".join(p.get("text", "") for p in candidato.get("content", {}).get("parts", []) if not p.get("thought")).strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return []
    trozos = meta.get("groundingChunks") or []
    apoyos: dict = {}
    for s in meta.get("groundingSupports") or []:
        frase = str((s.get("segment") or {}).get("text", "")).strip()
        for i in s.get("groundingChunkIndices") or []:
            if frase and frase not in apoyos.setdefault(i, []):
                apoyos[i].append(frase)
    salida = []
    for i, t in enumerate(trozos):
        web = (t or {}).get("web") or {}
        if not web.get("uri"):
            continue
        dom = _dominio(web.get("title", "")) or _dominio(web.get("uri", ""))
        if dominio and not (dom and (dom == dominio or dom.endswith("." + dominio))):
            continue
        salida.append({"title": web.get("title", ""), "url": web["uri"], "dominio": dom or "", "content": " ".join(apoyos.get(i, [])) or (texto if not salida else "")})
    return salida


def _claves_google():
    """[(clave, «pago»|«gratis»)] en el orden en que se prueban. La gratuita, siempre la de Gemini guardada: con otro proveedor, la clave «gratuita» del
    presupuesto es la de ese proveedor y no vale para Google."""
    pago = PRES.clave_de_pago_con_saldo()
    gratis = CL.obtener("gemini")
    return [(c, t) for c, t in ((pago, "pago"), (gratis, "gratis")) if c and not (t == "gratis" and c == pago)]


def resultados_google(consulta, dominio=None, post=None, ahora=None):
    """(resultados, motivo): la búsqueda de Google en una llamada aparte a Gemini. Cuenta en el gasto (tokens y búsquedas)."""
    claves = _claves_google()
    if not claves:
        return [], ""
    motivo = ""
    for clave, tipo in claves:
        if bloqueo(clave, ahora):
            motivo = motivo or T(M_GOOGLE_PAGO if tipo == "pago" else M_GOOGLE_GRATIS)
            continue
        if (ahora or time.time()) < _pausa_google.get(huella(clave), 0):
            motivo = motivo or T(M_GOOGLE_FALLO)
            continue
        pedido = f"Busca en internet{' solo dentro de la web ' + dominio if dominio else ''}: {consulta}. Responde con los datos que encuentres, en pocas frases."
        cuerpo = {"contents": [{"role": "user", "parts": [{"text": pedido}]}], "tools": [{"google_search": {}}]}
        inicio = time.time()
        try:
            r = (post or IA._post_cancelable)(PG.URL.format(modelo=MODELO_GOOGLE), headers={"x-goog-api-key": clave}, json=cuerpo, timeout=TIMEOUT_GOOGLE)
        except requests.RequestException as e:
            log(f"Búsqueda de Google ({tipo}): sin conexión ({e})")
            return [], T(M_GOOGLE_FALLO)
        if r.status_code == 429 and es_429_permanente(r):
            _bloquear(clave, tipo, ahora)
            log(f"Búsqueda de Google ({tipo}): 429 sin detalle ({PG.resumen_error(r)}). "
                + ("Puede ser el tope de gasto de tu cuenta de Google: no la vuelvo a probar hasta mañana o hasta que cambies la clave"
                   if tipo == "pago" else "No la vuelvo a probar con esta clave hasta que la cambies"))
            motivo = motivo or T(M_GOOGLE_PAGO if tipo == "pago" else M_GOOGLE_GRATIS)
            continue
        if not r.ok:
            espera = PG.espera_de_cuota(r) if r.status_code == 429 else None
            _pausa_google[huella(clave)] = (ahora or time.time()) + (espera if espera is not None else PAUSA_GOOGLE_SEG)
            log(f"Búsqueda de Google ({tipo}): {PG.resumen_error(r)}")
            motivo = motivo or T(M_GOOGLE_FALLO)
            continue
        try:
            datos = r.json()
        except ValueError:
            return [], T(M_GOOGLE_FALLO)
        PRES.registrar(clave, MODELO_GOOGLE, datos.get("usageMetadata") or {}, datos.get("modelVersion"))
        consultas = ((datos.get("candidates") or [{}])[0].get("groundingMetadata") or {}).get("webSearchQueries") or []
        if consultas:
            PRES.registrar_busquedas_google(clave, len(consultas))
        resultados = resultados_de_google(datos, dominio)
        log(f"Búsqueda de Google ({tipo}) «{consulta}»{' en ' + dominio if dominio else ''}: {len(resultados)} fuentes ({time.time() - inicio:.1f} s)")
        return resultados, ("" if resultados else T(M_GOOGLE_FALLO))
    return [], motivo


# ---------------------------------------------------------------- Wikipedia y las wikis de juegos
def wikis():
    try:
        return [w for w in tomllib.loads(WIKIS.read_text(encoding="utf-8")).get("wiki", []) if isinstance(w, dict)]
    except (OSError, tomllib.TOMLDecodeError):
        return []


def wikis_para(consulta, idioma):
    """[{api, pagina}] en el orden en que se prueban: las wikis del juego que nombra la consulta (su idioma primero) y luego Wikipedia."""
    t = C.normalizar(consulta)
    otro = "en" if idioma != "en" else "es"
    salida = []
    for w in wikis():
        if any(re.search(rf"(?<!\w){re.escape(C.normalizar(n))}(?!\w)", t) for n in w.get("nombres", [])):
            salida += [{**w[i], "nombres": w["nombres"]} for i in (idioma, otro) if isinstance(w.get(i), dict)]
    salida += [{"api": f"{i}.wikipedia.org/w", "pagina": f"https://{i}.wikipedia.org/wiki/"} for i in dict.fromkeys((idioma, "en"))]
    return salida


_ACTUALIDAD = re.compile(
    r"\b(?:hoy|manana|ayer|ahora|ahora mismo|esta (?:semana|noche|tarde|manana)|este (?:fin de semana|mes|ano)|actual(?:es|mente)?|ultim[oa]s?|proxim[oa]s?|"
    r"precios?|cuesta|cuestan|vale|valen|cotiza\w*|cotizacion\w*|bolsa|euros?|dolar(?:es)?|bitcoin|noticias?|novedad(?:es)?|"
    r"tiempo (?:hace|hara|en)|que tiempo|clima|lluvia|temperatura|prevision|resultados?|clasificacion|marcador|partidos?|jornada|gano|ganador|"
    r"estrenos?|cartelera|horarios?|today|tomorrow|now|current|latest|next|price|cost|news|weather|forecast|score|results?|standings|"
    r"matches|won|release date)\b")


def es_de_actualidad(texto):
    """¿Pide un dato del momento (precio, noticia, el tiempo, un resultado, lo de hoy)? Eso no lo trae una enciclopedia: las wikis no se usan."""
    return bool(_ACTUALIDAD.search(C.normalizar(texto)))


def terminos(consulta, nombres=()):
    """Las palabras que importan de la consulta (sin palabras vacías ni el nombre del juego), para ver si un resultado de wiki habla de ello."""
    return [p for p in re.findall(r"\w+", C.normalizar(consulta_wiki(consulta, nombres))) if len(p) >= 3 and p not in _VACIAS]


def _nombra_termino(resultado, palabras):
    texto = C.normalizar(f"{resultado.get('title', '')} {IA._texto_html(str(resultado.get('snippet', '')))}")
    return any(re.search(rf"\b{re.escape(p)}", texto) for p in palabras)


def resultados_wiki(consulta, idioma=None, get=None, maximo=5, peticion=""):
    """(resultados, motivo) de la primera wiki que encuentre algo que nombre la consulta. Nada si se pide un dato del momento."""
    if es_de_actualidad(f"{consulta} {peticion}"):
        log(f"Wikis: «{consulta}» pide un dato del momento; no busco en ellas")
        return [], T(M_WIKI_ACTUALIDAD)
    hubo_red = False
    for w in wikis_para(consulta, idioma or IDI.actual()):
        try:
            r = (get or requests.get)(f"https://{w['api']}/api.php", params={"action": "query", "list": "search", "srsearch": consulta_wiki(consulta, w.get("nombres", ())),
                                                                           "srlimit": maximo,
                                                                           "srprop": "snippet", "format": "json"},
                                      headers={"User-Agent": IA.AGENTE}, timeout=TIMEOUT_WIKI)
            hubo_red = True
            encontrados = r.json().get("query", {}).get("search", []) if r.ok else []
        except (requests.RequestException, ValueError, AttributeError) as e:
            log(f"Wiki {w['api']}: {type(e).__name__}")
            continue
        palabras = terminos(consulta, w.get("nombres", ()))
        if palabras and encontrados:
            antes, encontrados = len(encontrados), [e for e in encontrados if _nombra_termino(e, palabras)]
            if len(encontrados) < antes:
                log(f"Wiki {w['api']}: {antes - len(encontrados)} de {antes} resultados no nombran nada de la consulta ({', '.join(palabras)})")
        if encontrados:
            dominio = w["api"].split("/")[0]
            log(f"Búsqueda en {dominio} «{consulta}»: {len(encontrados)} resultados")
            encontrados = sorted(encontrados[:maximo], key=lambda e: -_cubre(str(e.get("title", "")), consulta))
            return [{"title": e.get("title", ""), "url": w["pagina"] + quote(str(e.get("title", "")).replace(" ", "_"), safe=":/()_,'!"),
                     "dominio": dominio, "api": w["api"], "content": IA._texto_html(str(e.get("snippet", "")))} for e in encontrados], ""
    return [], T(M_WIKI_NADA if hubo_red else M_WIKI_RED)


_VACIAS = set("de del la las el los un una unos unas en y o a al que como se hace hacer hay cual cuales cuando donde quien por para con sin es son esta estan "
               "me te lo le mi tu su mas muy este esto ese esa sobre entre hasta desde cuanto cuanta cuantos cuantas dime sabes "
               "the a an of in on for to and or is are how what which who when where does do can with by".split())


def consulta_wiki(consulta, nombres=()):
    """Lo que se le pide al buscador de una wiki: sin palabras vacías y, dentro de la wiki de un juego, sin su nombre («creeper Minecraft» → «creeper» en
    la de Minecraft). Medido a mano: con la frase entera, MediaWiki ponía delante páginas que no eran."""
    quitar = {p for n in nombres for p in C.normalizar(n).split()} | _VACIAS
    palabras = [p for p in str(consulta).split() if C.normalizar(p).strip("¿?¡!.,;:") not in quitar]
    return " ".join(palabras)[:300] or str(consulta)[:300]


def _cubre(titulo, consulta):
    """Qué parte de las palabras del título está en la consulta: el buscador de MediaWiki ordena mal las frases («capital de Australia» daba primero
    «Biblioteca Nacional de Australia»); a igualdad, se respeta su orden."""
    palabras = [p for p in re.findall(r"\w+", C.normalizar(titulo)) if len(p) >= 3]
    dichas = set(re.findall(r"\w+", C.normalizar(consulta)))
    return sum(p in dichas for p in palabras) / len(palabras) if palabras else 0.0


def pagina_wiki(resultado, get=None):
    """{url, titulo, texto} con el extracto de la página de una wiki, pedido a su API: la introducción (prop=extracts) o, donde no lo hay (Fandom), la
    primera sección (action=parse, section=0); si es más corta que EXTRACTO_MIN, la página entera, y siempre como mucho EXTRACTO_MAX caracteres. Así cabe
    entero en lo que lee la IA y no se resume por trozos. Fandom devuelve 403 a los programas que piden la página, no a la API. None si no se puede."""
    api = resultado.get("api")
    if not api:
        return None
    titulo = resultado.get("title", "")
    texto = ""
    for intro in (True, False):
        texto = _extracto(api, titulo, intro, get)
        if texto is None or len(texto) >= EXTRACTO_MIN:
            break
    if not texto:
        return None
    return {"url": resultado["url"], "titulo": titulo, "texto": _recortar(texto)}


def _recortar(texto):
    texto = re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", texto)).strip()
    if len(texto) <= EXTRACTO_MAX:
        return texto
    corte = texto[:EXTRACTO_MAX]
    return corte[:max(corte.rfind(". "), EXTRACTO_MAX // 2) + 1].rstrip() + " (…)"


def _extracto(api, titulo, intro, get=None):
    """El texto de la página (solo la introducción si `intro`) o None si no hay red."""
    pedir = get or requests.get
    comun = {"redirects": 1, "format": "json", "formatversion": 2}
    try:
        r = pedir(f"https://{api}/api.php", params={"action": "query", "prop": "extracts", "explaintext": 1, "titles": titulo, **({"exintro": 1} if intro else {}),
                                                     **comun}, headers={"User-Agent": IA.AGENTE}, timeout=TIMEOUT_WIKI)
        paginas = r.json().get("query", {}).get("pages", []) if r.ok else []
        texto = str((paginas[0] if paginas else {}).get("extract") or "")
        if texto:
            return texto
        r = pedir(f"https://{api}/api.php", params={"action": "parse", "page": titulo, "prop": "text", "disabletoc": 1, "disableeditsection": 1,
                                                     **({"section": 0} if intro else {}), **comun}, headers={"User-Agent": IA.AGENTE}, timeout=TIMEOUT_WIKI)
        html = str(r.json().get("parse", {}).get("text", "")) if r.ok else ""
    except (requests.RequestException, ValueError, AttributeError, IndexError) as e:
        log(f"Wiki {api}: no he podido traer la página ({type(e).__name__})")
        return None
    html = re.sub(r"<(style|script)\b.*?</\1>|<table\b.*?</table>|<aside\b.*?</aside>", " ", html, flags=re.S | re.I)    # sin fichas ni tablas
    return IA._texto_html(html)


def wiki_de_url(url):
    """{api, url, title} si la dirección es de una página de las wikis conocidas (o de Wikipedia), para leerla por su API y no la página entera; o None."""
    partes = urlparse(str(url))
    host = partes.netloc.lower()
    if re.fullmatch(r"[a-z]{2,3}(?:\.m)?\.wikipedia\.org", host):
        host = host.replace(".m.", ".")                    # la versión para el móvil es la misma página
        candidatas = [(f"{host}/w", f"https://{host}/wiki/")]
    else:
        candidatas = [(d["api"], d["pagina"]) for w in wikis() for d in (w.get("es"), w.get("en")) if isinstance(d, dict)]
    for api, pagina in candidatas:
        if f"https://{host}{partes.path}".startswith(pagina) and partes.scheme in ("http", "https") and len(partes.path) > len(urlparse(pagina).path):
            titulo = unquote(partes.path[len(urlparse(pagina).path):]).replace("_", " ")
            return {"api": api, "url": str(url), "title": titulo} if titulo and "/" not in titulo else None
    return None


# ---------------------------------------------------------------- la escalera
def _clave_cache(consulta, dominio, modo):
    return (" ".join(str(consulta).lower().split()), dominio or "", modo)


def buscar(consulta, dominio=None, modo=None, ahora=None, peticion=""):
    """Resultado de la escalera de `modo` (auto o google; por defecto el de ia.busqueda). `peticion`: lo que dijo el usuario, para no mandar a las wikis
    lo que pide un dato del momento aunque la consulta no lo diga. Nunca lanza por la red."""
    modo = modo or IA.modo_busqueda()
    ahora_real = ahora or time.time()
    clave = (*_clave_cache(consulta, dominio, modo), es_de_actualidad(peticion))
    guardado = _cache.get(clave)
    if guardado and ahora_real - guardado[0] < CACHE_SEG:
        log(f"Búsqueda «{consulta}»: la de hace {int(ahora_real - guardado[0])} s ({guardado[1].escalon})")
        return guardado[1]
    dom = IA.dominio_valido(dominio) if dominio else None
    res = Resultado()
    for escalon in ESCALONES.get(modo, ()):
        encontrados, motivo = _escalon(escalon, consulta, dom, res, ahora_real, peticion)
        if encontrados:
            res.resultados, res.escalon = encontrados, escalon
            if escalon == "wiki":
                AVB.apuntar(AVB.PRIMERA_WIKI)
            break
        if motivo and motivo not in res.motivos:
            res.motivos.append(motivo)
    if modo == "google" and not res.resultados and not _claves_google():
        res.motivos.insert(0, T(M_SIN_PAGO))
    if res.resultados:
        _cache[clave] = (ahora_real, res)
        for k in [k for k, (t, _) in _cache.items() if ahora_real - t >= CACHE_SEG]:
            _cache.pop(k, None)
    return res


def _escalon(escalon, consulta, dominio, res, ahora, peticion=""):
    if escalon == "google":
        return resultados_google(consulta, dominio, ahora=ahora)
    if escalon == "tavily":
        if not CL.obtener("tavily"):
            res.sin_tavily = True
            return [], T(M_SIN_TAVILY)
        r = IA.resultados_tavily(consulta, dominio, reserva=False, comprobar_modo=False)
        if isinstance(r, list):
            return r, ("" if r else T(M_TAVILY_NADA))
        return [], T(M_TAVILY_LIMITE if r == AVB.PARA_LA_IA_LIMITE else M_TAVILY_FALLO)
    if escalon == "duckduckgo":
        if not IA.hay_reserva():
            return [], ""
        if ahora - _ultima_duckduckgo[0] < INTERVALO_DUCKDUCKGO_SEG:
            return [], T(M_DUCKDUCKGO_PRONTO)
        _ultima_duckduckgo[0] = ahora
        r = IA.resultados_reserva(consulta, dominio)
        return (r, "") if isinstance(r, list) and r else ([], T(M_DUCKDUCKGO))
    if escalon == "wiki":
        if dominio and not re.search(r"(?:^|\.)(?:wikipedia\.org|fandom\.com|minecraft\.wiki|wiki\.gg|bg3\.wiki|wikidex\.net)$", dominio):
            return [], ""                                # buscar dentro de otra web no es cosa de las wikis
        return resultados_wiki(consulta, peticion=peticion)
    return [], ""


def como_texto(res):
    """Lo que recibe la IA: los resultados de siempre o, si nada dio resultados, el motivo y cómo decirlo."""
    if res.resultados:
        webs = dominios_de_resultados(res.resultados)
        return IA._resultados_como_texto(res.resultados) + (
            f"\nWEBS DE ESTOS RESULTADOS: {', '.join(webs)}. Si dices de dónde sale el dato, nombra SOLO una de estas webs por su dominio (por ejemplo "
            f"«según {webs[0]}»); no atribuyas nada a otra web, wiki o medio que no esté en esta lista." if webs else "")
    motivos = "; ".join(res.motivos) or T(M_WIKI_NADA)
    return (f"NO SE HA PODIDO BUSCAR: {motivos}. Díselo al usuario en una frase con ese motivo; NUNCA digas que no tienes acceso a internet. Si añades algo "
            "de memoria, di que no lo has comprobado."
            + (" Sugiere en pocas palabras una clave gratuita de Tavily, que se configura con lina bienvenida." if res.sin_tavily else ""))


def frase_de_fallo(resultados):
    """Lo que dice el código si la respuesta habla de «no tener acceso a internet» y nada se pudo buscar: el motivo de verdad, corto."""
    motivos = [m for r in resultados for m in r.motivos]
    sin_tavily = any(r.sin_tavily for r in resultados)
    utiles = [m for m in dict.fromkeys(motivos) if m != T(M_GOOGLE_GRATIS)] or list(dict.fromkeys(motivos))
    frase = T("No he podido buscarlo: {motivos}.", motivos=T(" y ").join(utiles[-2:])) if utiles else T("No he podido buscarlo.")
    return frase + (" " + T("Con una clave gratuita de Tavily buscaría noticias, precios y horarios: lina bienvenida.") if sin_tavily else "")


# ---------------------------------------------------------------- de dónde dice la respuesta que sale el dato
# Nombres con los que se cita una web que no salen de su dominio. Lo demás vale por la etiqueta del dominio («gamespot» = gamespot.com) o, en las wikis
# de datos/wikis.toml, por el nombre del juego («la wiki de Skyrim» = elderscrolls.fandom.com).
ALIAS = {"steampowered.com": ("steam",), "store.steampowered.com": ("steam",), "ign.com": ("ign",), "ign.es": ("ign",), "x.com": ("twitter",),
         "elpais.com": ("el pais",), "elmundo.es": ("el mundo",), "rtve.es": ("rtve", "radiotelevision espanola"), "aemet.es": ("aemet", "agencia estatal de meteorologia"),
         "bbc.com": ("bbc",), "bbc.co.uk": ("bbc",), "nytimes.com": ("new york times",), "lolesports.com": ("lol esports",),
         "uesp.net": ("uesp", "unofficial elder scrolls pages"), "wikipedia.org": ("wikipedia",), "pccomponentes.com": ("pc componentes", "pccomponentes")}
_GENERICAS = {"www", "com", "es", "org", "net", "en", "w", "wiki", "co", "uk", "io", "gg", "info", "html", "fandom", "store", "news", "blog"}
_NO_SON_FUENTE = {"google", "internet", "la busqueda", "los resultados", "las fuentes", "la web", "mis datos", "wiki"}
_ATRIBUCION = re.compile(
    r"(?P<intro>\b(?:[Ss]eg[uú]n|[Dd]e acuerdo con|[Cc]omo (?:indica|dice|recoge|explica|publica)|[Ii]nforma|[Ff]uente:|[Aa]ccording to|[Ss]ource:|"
    r"[Ee]n(?=\s+(?:la|el)\s+(?:web|página|pagina|wiki|tienda|sitio|portal)\b))\s+)"
    r"(?P<fuente>(?:(?:la|el|los|las|the)\s+)?(?:(?:web|página|pagina|wiki|tienda|sitio|portal|revista|diario|blog|website|site)\s+(?:de\s+(?:la\s+|el\s+)?|del\s+|of\s+(?:the\s+)?)?)?"
    r"(?:[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b|[A-Z0-9ÁÉÍÓÚÑ][\w'’.-]*(?:\s+(?:de\s+)?[A-Z0-9ÁÉÍÓÚÑ][\w'’.-]*){0,3}))")


def _sin_relleno(nombre):
    t = C.normalizar(nombre).rstrip(".")
    t = re.sub(r"^(?:(?:la|el|los|las|the) )?(?:(?:web|pagina|wiki|tienda|sitio|portal|revista|diario|blog|website|site) (?:de (?:la |el )?|del |of (?:the )?)?)?", "", t)
    return t.strip()


def nombra(dominio, nombre):
    """¿Ese nombre («la wiki UESP», «Steam», «gamespot.com», «la wiki de Skyrim») es la web `dominio`?"""
    n = _sin_relleno(nombre)
    if not n:
        return False
    junto = n.replace(" ", "")
    dominio = dominio.lower().removeprefix("www.")
    partes = [p for p in re.split(r"[.-]", dominio) if len(p) >= 3 and p not in _GENERICAS]
    if any(re.search(rf"\b{re.escape(p)}\b", n) or p in junto for p in partes):
        return True
    if any(dominio == d or dominio.endswith("." + d) for d, alias in ALIAS.items() for a in alias if re.search(rf"\b{re.escape(a)}\b", n)):
        return True
    for w in wikis():
        hosts = {str(d.get("api", "")).split("/")[0] for d in (w.get("es"), w.get("en")) if isinstance(d, dict)}
        if dominio in hosts and any(re.search(rf"\b{re.escape(C.normalizar(x))}\b", n) for x in w.get("nombres", [])):
            return True
    return False


def fuentes_nombradas(texto):
    """[(inicio, fin, nombre)] de cada «según X», «de acuerdo con X»… de la respuesta (X, la fuente a la que atribuye el dato)."""
    salida = []
    for m in _ATRIBUCION.finditer(str(texto)):
        nombre = m.group("fuente").rstrip(".")
        if _sin_relleno(nombre) in _NO_SON_FUENTE or C.normalizar(nombre) in _NO_SON_FUENTE:
            continue
        salida.append((m.start("fuente"), m.start("fuente") + len(nombre), nombre))
    return salida


def atribuciones_inventadas(texto, dominios):
    """Los nombres de fuente de la respuesta que no son ninguna de las webs que de verdad salieron (`dominios`)."""
    return [n for _, _, n in fuentes_nombradas(texto) if not any(nombra(d, n) for d in dominios)]


def corregir_atribucion(texto, dominios):
    """La respuesta con cada fuente inventada cambiada por una web de verdad («Según la wiki UESP» → «Según gamespot.com»). Sin `dominios`, tal cual."""
    if not dominios:
        return texto
    salida = str(texto)
    for inicio, fin, nombre in reversed(fuentes_nombradas(salida)):
        if not any(nombra(d, nombre) for d in dominios):
            salida = salida[:inicio] + dominios[0] + salida[fin:]
    return salida


def dominios_de_resultados(resultados):
    return list(dict.fromkeys(d for d in ((r.get("dominio") or urlparse(str(r.get("url", ""))).netloc).lower().removeprefix("www.") for r in resultados) if d))


def dominios_de_acciones(acciones):
    """Las webs que salieron de una búsqueda o una lectura con éxito, según lo que vio la IA (también en modo tavily)."""
    dominios = []
    for nombre, args, resultado in acciones:
        texto = str(resultado)
        if nombre == "buscar_web" and texto.startswith("RESULTADOS DE BÚSQUEDA"):
            dominios += re.findall(r"^\[\d+\] .*? \(([a-z0-9.-]+\.[a-z]{2,})\) ", texto, re.M)
            if "CONTENIDO DE LA PÁGINA" in texto:                # la wiki: la escalera ya leyó la primera página
                dominios += re.findall(r"^CONTENIDO DE LA PÁGINA «.*?» \(([a-z0-9.-]+\.[a-z]{2,})\)", texto, re.M)
        if nombre in ("leer_web", "usar_fuente") and "CONTENIDO DE LA PÁGINA" in texto:
            dominios.append(urlparse(str((args or {}).get("url", ""))).netloc.lower().removeprefix("www."))
            dominios += re.findall(r"CONTENIDO DE LA PÁGINA «.*?» \(([a-z0-9.-]+\.[a-z]{2,})\)", texto)
    return list(dict.fromkeys(d for d in dominios if d))


# ---------------------------------------------------------------- «búscalo igualmente» con ia.busqueda = ninguna
_IGUALMENTE_ES = re.compile(r"\b(?:buscal[oa]s?|busca(?:me)?(?:lo|la|los|las)?|mira(?:lo|la)?)\b(?:\s+\w+){0,4}?\s+(?:igualmente|de todas formas|de todos modos|aun asi|"
                            r"aunque sea|aunque no (?:quiera|quieras|este))\b")
_IGUALMENTE_EN = re.compile(r"\b(?:search|look)(?:\s+\w+){0,4}?\s+anyway\b")


def pide_buscar_igualmente(frase):
    """¿Pide buscar aunque la búsqueda esté apagada? («búscalo igualmente», «búscalo en internet de todas formas»). Vale solo para esa petición."""
    t = C.normalizar(frase)
    return bool((_IGUALMENTE_EN if IDI.actual() == "en" else _IGUALMENTE_ES).search(t))


# ---------------------------------------------------------------- para lina doctor
def estado_google(ahora=None):
    """[(«pago»|«gratis», desde, hasta)] de las claves de Gemini guardadas que ahora no se prueban con la búsqueda de Google."""
    salida = []
    for nombre, tipo in (("gemini_pago", "pago"), ("gemini", "gratis")):
        b = bloqueo(CL.obtener(nombre), ahora)
        if b:
            salida.append((tipo, float(b.get("desde") or 0), b.get("hasta")))
    return salida
