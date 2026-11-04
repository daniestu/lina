# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-busqueda`: la prueba de aceptación de la búsqueda (bloque C). Veinte preguntas típicas pasan por tu Lina como si fuera la de un usuario nuevo.

Usuario nuevo: config.toml de fábrica (ia.busqueda = auto) y un estado vacío, en carpetas temporales que se borran al terminar; sin fuentes, memoria ni
historial; y solo las claves del nivel. La IA, la búsqueda y la lectura de webs son de verdad; ningún comando se ejecuta y nada mira tu pantalla.
Las llamadas cuentan como medida (no salen en lina tiempos ia).

Cada pregunta está bien si hay respuesta, no dice que no puede buscar ni que no lo sabe, y nombra una web que salió de una búsqueda o lectura de esa
misma pregunta. Los errores del servicio (429, 500, 502, 503, 504, sin red) no son fallos de búsqueda: la pregunta se repite tras 20, 40 y 60 s y, si sigue
igual, sale aparte como «api» y no cuenta. Criterio, escrito antes de medir: con Tavily o con la clave de pago, al menos 18 de 20; si más de 2 acaban en
«api», la pasada no vale y hay que repetirla. Solo con la clave gratuita se informa de lo que haya, sin criterio.
"""
import re
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from unittest.mock import MagicMock
from urllib.parse import urlparse

from lina.nucleo import comandos as C
from lina.nucleo.idioma import N_, T

AYUDA = N_("""lina probar-busqueda [gratis|tavily|pago] [N]
    Pasa 20 preguntas típicas (la poción de Skyrim, los partidos de LoL, precios, noticias…) por tu Lina como si fuera la de un usuario nuevo: ajustes de
    fábrica, sin fuentes, memoria ni historial, y solo las claves del nivel. Busca y lee webs de verdad; no ejecuta comandos ni mira tu pantalla.
      gratis  solo tu clave gratuita de Gemini (de fábrica). Dice lo que hay, sin criterio.
      tavily  tu clave gratuita de Gemini y tu clave de Tavily. Criterio: al menos 18 de 20 con respuesta y fuente.
      pago    tus claves de Gemini, también la de pago (gasta de tu tope). Criterio: al menos 18 de 20 con respuesta y fuente.
    Los errores del servicio (429, 503…) se repiten con pausa y no cuentan; si quedan más de 2, la pasada no vale. N: solo las N primeras.""")
PREGUNTAS = [
    "cómo se hace la poción de invisibilidad en Skyrim", "qué partidos de LoL hay esta semana", "cuánto cuesta la Steam Deck OLED",
    "cuál es la noticia de tecnología más importante de hoy", "quién ganó el último Gran Premio de Fórmula 1", "cuáles son los requisitos mínimos de Cyberpunk 2077",
    "cuándo sale la próxima actualización de No Man's Sky", "qué tiempo hará mañana en Sevilla", "cuál es la versión actual del kernel de Linux",
    "cuánto mide la torre Eiffel", "qué es el protocolo MCP de los asistentes de IA", "cómo va la clasificación de LaLiga",
    "a cuánto está el euro frente al dólar", "qué estrenos de cine hay esta semana", "qué ingredientes lleva la poción de curación en Skyrim",
    "cuál es el precio de la RTX 5070", "qué es un creeper en Minecraft", "cuál es la receta de la tortilla de patatas",
    "quién ganó el último mundial de League of Legends", "cuándo es el próximo eclipse visible en España",
]
NIVELES = {"gratis": ("gemini",), "tavily": ("gemini", "tavily"), "pago": ("gemini", "gemini_pago")}
CRITERIO = {"gratis": None, "tavily": 18, "pago": 18}
MAX_API = 2
PERMITIDAS = {"buscar_web", "leer_web", "mas_herramientas", "necesito_datos_actuales", "pensar_a_fondo"}
NO_EJECUTA = "En esta prueba no se ejecuta nada en el equipo ni se mira la pantalla: responde con lo que hayas buscado o leído en internet."
TRANSITORIOS = {"429", "500", "502", "503", "504", "red"}
REINTENTOS = (20, 40, 60)
PAUSA_SEG = 8                                        # entre pregunta y pregunta: la clave gratuita admite 15 llamadas por minuto
TOPE_SEG = 90
_NO_RESPONDE = re.compile(r"\b(?:no tengo acceso|no puedo (?:buscar|acceder|navegar|consultar)|no he podido (?:buscar|encontrar|leer)|no lo se\b|"
                          r"no lo he encontrado|no he encontrado|no dispongo)")
_GENERICAS = {"www", "com", "es", "org", "net", "en", "w", "wiki", "co", "uk", "io", "gg", "info", "html"}


# ---------------------------------------------------------------- el juez
def dominios_de(acciones):
    """Las webs que salieron de una búsqueda o una lectura con éxito en esta pregunta."""
    dominios = []
    for nombre, args, resultado in acciones:
        texto = str(resultado)
        if nombre == "buscar_web" and texto.startswith("RESULTADOS DE BÚSQUEDA"):
            dominios += re.findall(r"^\[\d+\] .*? \(([a-z0-9.-]+\.[a-z]{2,})\) ", texto, re.M)
        if nombre == "leer_web" and texto.startswith("CONTENIDO DE LA PÁGINA"):
            dominios.append(urlparse(str((args or {}).get("url", ""))).netloc.lower().removeprefix("www."))
        if nombre == "buscar_web" and "CONTENIDO DE LA PÁGINA" in texto:                # la wiki: la escalera ya leyó la primera página
            dominios += re.findall(r"^\[1\] .*? \(([a-z0-9.-]+\.[a-z]{2,})\) ", texto, re.M)
    return list(dict.fromkeys(d for d in dominios if d))


def cita(dominio, texto):
    """¿La respuesta nombra esa web? Vale una parte con nombre propio del dominio («uesp», «wikipedia», «elderscrolls» aunque diga «Elder Scrolls»)."""
    t = C.normalizar(texto)
    junto = t.replace(" ", "")
    return any(len(p) >= 3 and p not in _GENERICAS and (re.search(rf"\b{re.escape(p)}\b", t) or p in junto) for p in re.split(r"[.-]", dominio.lower()))


def juzgar(dicho, acciones):
    """(nota, motivo): «bien» o «mal»."""
    texto = " ".join(str(d) for d in dicho).strip()
    if not texto or texto.startswith("(cortada") or texto.startswith("(error"):
        return "mal", T("sin respuesta")
    if _NO_RESPONDE.search(C.normalizar(texto)):
        return "mal", T("dice que no puede o que no lo sabe")
    dominios = dominios_de(acciones)
    if not dominios:
        return "mal", T("ninguna búsqueda ni lectura dio resultados")
    if not any(cita(d, texto) for d in dominios):
        return "mal", T("no nombra la web de donde sale ({webs})", webs=", ".join(dominios[:3]))
    return "bien", T("cita {web}", web=next(d for d in dominios if cita(d, texto)))


def veredicto(notas, nivel):
    """(¿pasa?, frase). Las «api» no cuentan como fallo, pero si son más de MAX_API la pasada no vale."""
    bien, api = notas.count("bien"), notas.count("api")
    criterio = CRITERIO[nivel]
    resumen = T("{bien} de {n} con respuesta y fuente ({api} fuera por errores del servicio)", bien=bien, n=len(notas), api=api)
    if criterio is None:
        return True, resumen + T(" · solo con la clave gratuita no hay criterio: es para saber lo que hay")
    if api > MAX_API:
        return False, resumen + T(" · la pasada no vale: más de {m} preguntas sin servicio. Repítela más tarde", m=MAX_API)
    return bien >= criterio, resumen + (T(" · PASA (hace falta {c})", c=criterio) if bien >= criterio else T(" · NO PASA (hace falta {c})", c=criterio))


# ---------------------------------------------------------------- un usuario nuevo
@contextmanager
def usuario_nuevo(nivel, obtener_real=None):
    """Lina con ajustes de fábrica y un estado vacío (carpetas temporales) y solo las claves del nivel. Lo deja todo como estaba al salir."""
    from lina.nucleo import claves as CL
    from lina.nucleo import fuentes as FUE
    from lina.nucleo import memoria as MEM
    from lina.nucleo import rutas as RUT
    obtener_real = obtener_real or CL.obtener
    claves = {n: obtener_real(n) for n in NIVELES[nivel]}
    carpeta = tempfile.mkdtemp(prefix="lina-probar-busqueda-")
    cambios = [(RUT, "CONFIG", RUT.CONFIG.__class__(carpeta) / "config"), (RUT, "ESTADO", RUT.ESTADO.__class__(carpeta) / "estado"),
               (CL, "obtener", lambda nombre, *a, **k: claves.get(nombre, "")), (FUE, "listar", lambda *a, **k: []),
               (MEM, "relevantes", lambda *a, **k: []), (MEM, "nota_para_la_ia", lambda *a, **k: "")]
    antes = [(o, n, getattr(o, n)) for o, n, _ in cambios]
    try:
        for o, n, v in cambios:
            setattr(o, n, v)
        yield claves
    finally:
        for o, n, v in antes:
            setattr(o, n, v)
        shutil.rmtree(carpeta, ignore_errors=True)


def _asistente():
    """La Lina de verdad sin Whisper; solo puede buscar y leer webs. Devuelve (A, a, resultados de las llamadas a la IA de la pregunta en curso)."""
    from lina.nucleo import asistente as A
    from lina.nucleo import ia as IA
    A.MODELOS.cargar_whisper = lambda *x, **k: MagicMock()
    a = A.Asistente()
    a.titulo, a.contexto = "", {"tipo": "general", "nombre": None, "clase": ""}
    a.hilo_captura, a.ruta_captura, a.ventana_al_pulsar = None, None, {}
    real = a._ejecutar_herramienta
    a._ejecutar_herramienta = lambda nombre, args: real(nombre, args) if nombre in PERMITIDAS else NO_EJECUTA
    llamadas: list = []
    medido = IA._turno_medido

    def apuntar(*x, **k):
        r = medido(*x, **k)
        llamadas.append("ok" if not isinstance(r, IA.PROV.ErrorIA) else ("red" if r.tipo == "red" else str(r.estado or r.tipo)))
        return r
    IA._turno_medido = apuntar
    return A, a, llamadas


def pasar(frase, A, a, llamadas, tope=TOPE_SEG):
    """(dicho, acciones, resultados de las llamadas a la IA, segundos) de una pregunta, cortándola si pasa de `tope`."""
    dicho = []
    a.decir = dicho.append
    a._hablar = lambda texto, *x, **k: None
    a.historial, a.hechos_recientes, a.busquedas_hechas = [], [], []
    llamadas.clear()
    corte = threading.Timer(tope, A._abortar.set)
    corte.start()
    t0 = time.time()
    try:
        a._atender(frase, time.time(), origen="atajo")
    except A.Cancelado:
        dicho.append("(cortada por tiempo)")
    except Exception as e:
        dicho.append(f"(error: {e!r})")
    finally:
        corte.cancel()
        A._abortar.clear()
    return dicho, list(getattr(a, "acciones_turno", []) or []), list(llamadas), time.time() - t0


def es_de_servicio(nota, llamadas):
    """¿Falló por el servicio de la IA y no por la búsqueda? Solo si no salió bien y alguna llamada dio un error pasajero."""
    return nota != "bien" and any(r in TRANSITORIOS for r in llamadas)


def principal(argv, salida=print, preparar=None, pasar_pregunta=None, dormir=time.sleep):
    if argv[:1] in (["-h"], ["--help"], ["ayuda"]):
        salida(T(AYUDA))
        return 0
    nivel = next((x for x in argv if x in NIVELES), "gratis")
    numeros = [x for x in argv if x.isdigit()]
    preguntas = PREGUNTAS[:int(numeros[0])] if numeros else PREGUNTAS
    from lina.nucleo import claves as CL
    from lina.nucleo import ia as IA
    CL.proteger_salida()
    with usuario_nuevo(nivel) as claves:
        faltan = [n for n, v in claves.items() if not v]
        if faltan:
            salida(T("Para el nivel «{nivel}» falta la clave: {faltan}. Guárdala con  lina clave {primera}", nivel=nivel, faltan=", ".join(faltan), primera=faltan[0]))
            return 2
        salida(T("Nivel «{nivel}»: paso {n} preguntas por una Lina de usuario nuevo (unos segundos cada una, con pausas)…", nivel=nivel, n=len(preguntas)))
        A, a, llamadas = (preparar or _asistente)()
        filas, notas = [], []
        with IA.solo_medida():
            for i, frase in enumerate(preguntas):
                if i:
                    dormir(PAUSA_SEG)
                for espera in (*REINTENTOS, None):
                    dicho, acciones, hechas, seg = (pasar_pregunta or pasar)(frase, A, a, llamadas)
                    nota, motivo = juzgar(dicho, acciones)
                    if not es_de_servicio(nota, hechas):
                        break
                    if espera is None:
                        nota, motivo = "api", T("el servicio de la IA siguió fallando ({codigos})", codigos=", ".join(sorted(set(hechas) & TRANSITORIOS)))
                        break
                    salida(T("   ({codigos}: error del servicio, repito en {s} s)", codigos=", ".join(sorted(set(hechas) & TRANSITORIOS)), s=espera))
                    dormir(espera)
                escalon = next((b.escalon or "-" for b in reversed(getattr(a, "busquedas_hechas", []) or [])), "-")
                notas.append(nota)
                filas.append((nota, seg, escalon, frase, motivo, " ".join(str(d) for d in dicho)))
                salida(f"{nota:5} {seg:5.1f} s  {escalon:10} {frase}\n      {motivo}\n      dice: {' '.join(filas[-1][5].split())[:240]}")
    pasa, frase_final = veredicto(notas, nivel)
    por_escalon: dict = {}
    for nota, _, escalon, *_ in filas:
        if nota == "bien":
            por_escalon[escalon] = por_escalon.get(escalon, 0) + 1
    salida("")
    salida(frase_final)
    if por_escalon:
        salida(T("Respondidas con fuente, por escalón: {d}", d=", ".join(f"{k} {v}" for k, v in sorted(por_escalon.items()))))
    return 0 if pasa else 1
