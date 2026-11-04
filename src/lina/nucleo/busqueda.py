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
  4. Wikipedia y algunas wikis de juegos (datos/wikis.toml), con su buscador MediaWiki, sin clave.
Si nada da resultados, el motivo concreto de cada paso, para decirlo tal cual: nunca «no tengo acceso a internet».
Lo que sí encuentra se guarda CACHE_SEG (partidos, precios y noticias cambian: poco rato). Con «google», solo los pasos 1 y 3.
"""
import hashlib
import json
import re
import time
import tomllib
from dataclasses import dataclass, field
from urllib.parse import quote

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


def resultados_wiki(consulta, idioma=None, get=None, maximo=5):
    """(resultados, motivo) de la primera wiki que encuentre algo."""
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
    """{url, titulo, texto} de la página de una wiki, pedida a su API (action=parse): Fandom devuelve 403 a los programas que piden la página, no a la
    API. None si no se puede."""
    api = resultado.get("api")
    if not api:
        return None
    try:
        r = (get or requests.get)(f"https://{api}/api.php", params={"action": "parse", "page": resultado.get("title", ""), "prop": "text", "redirects": 1,
                                                                 "disabletoc": 1, "disableeditsection": 1, "format": "json", "formatversion": 2},
                                  headers={"User-Agent": IA.AGENTE}, timeout=TIMEOUT_WIKI)
        html = str(r.json().get("parse", {}).get("text", "")) if r.ok else ""
    except (requests.RequestException, ValueError, AttributeError) as e:
        log(f"Wiki {api}: no he podido traer la página ({type(e).__name__})")
        return None
    texto = IA._texto_html(re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S | re.I))
    return {"url": resultado["url"], "titulo": resultado.get("title", ""), "texto": texto} if texto else None


# ---------------------------------------------------------------- la escalera
def _clave_cache(consulta, dominio, modo):
    return (" ".join(str(consulta).lower().split()), dominio or "", modo)


def buscar(consulta, dominio=None, modo=None, ahora=None):
    """Resultado de la escalera de `modo` (auto o google; por defecto el de ia.busqueda). Nunca lanza por la red."""
    modo = modo or IA.modo_busqueda()
    ahora_real = ahora or time.time()
    clave = _clave_cache(consulta, dominio, modo)
    guardado = _cache.get(clave)
    if guardado and ahora_real - guardado[0] < CACHE_SEG:
        log(f"Búsqueda «{consulta}»: la de hace {int(ahora_real - guardado[0])} s ({guardado[1].escalon})")
        return guardado[1]
    dom = IA.dominio_valido(dominio) if dominio else None
    res = Resultado()
    for escalon in ESCALONES.get(modo, ()):
        encontrados, motivo = _escalon(escalon, consulta, dom, res, ahora_real)
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


def _escalon(escalon, consulta, dominio, res, ahora):
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
        return resultados_wiki(consulta)
    return [], ""


def como_texto(res):
    """Lo que recibe la IA: los resultados de siempre o, si nada dio resultados, el motivo y cómo decirlo."""
    if res.resultados:
        return IA._resultados_como_texto(res.resultados)
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
