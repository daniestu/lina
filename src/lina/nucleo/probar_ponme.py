# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-ponme`: mide cómo de bien «pone» Lina cosas (partidos, carreras, capítulos, películas, vídeos), con la IA y la búsqueda de verdad.

Pasa una tanda fija de peticiones por la Lina real (tus ajustes, tus claves, Gemini y la búsqueda web), pero NO abre nada: cada `xdg-open` se apunta en
vez de ejecutarse. De cada una dice qué habría abierto, cuánto tardó y cuántas páginas abrió, y lo puntúa: «bien», «a medias» (por ejemplo la ficha de la
serie en vez del capítulo), «mal», o «revisar» cuando la dirección no basta para saberlo (un identificador sin nombre): entonces la enseña para que la
mires tú. No cambia ajustes, no escribe en tu memoria y gasta unas pocas llamadas a la IA y a la búsqueda por petición.
"""
import re
import sys
import threading
import time
from unittest.mock import MagicMock

from lina.nucleo import comandos as C
from lina.nucleo.idioma import N_, T

AYUDA = N_("""lina probar-ponme [N]
    Pasa una tanda de peticiones «ponme…» por tu Lina (IA y búsqueda de verdad) SIN abrir nada, y dice qué habría abierto, cuánto tardó y si acertó.
    N: solo las N primeras. Gasta unas pocas llamadas a la IA y a la búsqueda por petición.""")
TOPE_SEG = 120                        # una petición que tarde más se corta (cuenta como mal)


def _n(texto):
    return C.normalizar(texto).replace(" ", "")


def _en(url, *palabras):
    u = _n(url)
    return all(_n(p) in u for p in palabras)


_GUIA = re.compile(r"programacion|parrilla|calendario|agenda|/news/|/noticias?/|/blog/|comunicacion|/tudum")


def _oficial(url):
    from urllib.parse import urlparse
    from lina.nucleo import contenido as CONT
    web = urlparse(url).netloc.lower()
    dominios = {d for lista in CONT.PLATAFORMAS.values() for d in lista} | {"youtube.com", "youtu.be"}
    return any(web == d or web.endswith("." + d) for d in dominios)


def _no_vale(url):
    """Lo que nunca es la página para verlo: una web que no es una plataforma oficial, una portada, una guía, una noticia."""
    from urllib.parse import urlparse
    p = urlparse(url)
    return not _oficial(url) or p.path in ("", "/") or bool(_GUIA.search(p.path.lower()))


def _dijo_que_no_hay(dicho):
    t = C.normalizar(" ".join(dicho))
    return bool(re.search(r"\bno (?:hay|juega|se juega|encuentro|he encontrado|he dado)\b|\bhoy no\b|\bel proximo\b|\bproxima\b", t))


def juez_evento(*participantes):
    """Un partido o una carrera «de hoy»: bien si abre una página que nombra a los participantes (y no una guía o una noticia), o si dice que hoy no
    hay; revisar si la página no los nombra (un identificador) y no se sabe si es la de hoy."""
    def juzgar(abiertas, dicho):
        if not abiertas:
            return ("bien", "dice que hoy no hay") if _dijo_que_no_hay(dicho) else ("mal", "no abrió nada")
        u = abiertas[-1]
        if _no_vale(u):
            return "mal", "no es una plataforma oficial, o es una portada, una guía o una noticia"
        if participantes and not _en(u, *participantes):
            return "revisar", "la dirección no nombra a los participantes"
        return "revisar", "nombra a los participantes: mira que sea el de hoy"
    return juzgar


def juez_capitulo(serie, *pistas_de_episodio):
    """Un capítulo concreto: bien si abre la página de ver un episodio (o una dirección con sus pistas); a medias si abre la serie."""
    def juzgar(abiertas, dicho):
        if not abiertas:
            return "mal", "no abrió nada"
        u = abiertas[-1]
        if _no_vale(u):
            return "mal", "no es una plataforma oficial, o es una portada, una guía o una noticia"
        if re.search(r"/watch/|/video/watch|/episod|/capitulo|/s\d+e\d+|/play/", u.lower()) or (pistas_de_episodio and _en(u, *pistas_de_episodio)):
            return "revisar", "abre un episodio: mira que sea ese"
        if _en(u, serie) or re.search(r"/title/|/shows?/|/series?/", u.lower()):
            return "a medias", "abre la serie, no el capítulo"
        return "mal", "no es ni la serie"
    return juzgar


def juez_titulo(*palabras):
    """Una serie, una película o un programa: bien si abre su página en una plataforma (nombrándolo o con su ficha)."""
    def juzgar(abiertas, dicho):
        if not abiertas:
            return "mal", "no abrió nada"
        u = abiertas[-1]
        if _no_vale(u):
            return "mal", "no es una plataforma oficial, o es una portada, una guía o una noticia"
        if _en(u, *palabras):
            return "bien", "su página"
        if re.search(r"/title/|/watch|/shows?/|/movies?/|/peliculas?/|/series?/|/ficha", u.lower()):
            return "revisar", "una ficha que no lo nombra en la dirección"
        return "mal", "no es su página"
    return juzgar


def juez_video(canal):
    def juzgar(abiertas, dicho):
        if not abiertas:
            return "mal", "no abrió nada"
        u = abiertas[-1].lower()
        if "youtube.com/watch" in u or "youtu.be/" in u:
            return "revisar", "abre un vídeo: mira que sea el último del canal"
        if "youtube.com" in u and _en(u, canal):
            return "a medias", "abre el canal, no el vídeo"
        return "mal", "no es un vídeo de YouTube"
    return juzgar


# La tanda. Nada de nombres de personas reales del entorno del usuario: solo equipos, deportistas, series y canales públicos.
CASOS = [
    ("Ponme el partido del Barça de hoy.", juez_evento("barcelona")),
    ("Ponme el partido de Alcaraz.", juez_evento("alcaraz")),
    ("Ponme la carrera de Fórmula 1.", juez_evento()),
    ("Ponme el partido del Unicaja de baloncesto.", juez_evento("unicaja")),
    ("Ponme el capítulo 3 de la segunda temporada de Stranger Things.", juez_capitulo("stranger things", "pollywog")),
    ("Ponme el último capítulo de The Last of Us.", juez_capitulo("last of us")),
    ("Ponme Stranger Things.", juez_titulo("stranger things")),
    ("Ponme la película Oppenheimer.", juez_titulo("oppenheimer")),
    ("Ponme el Telediario de La 1.", juez_titulo("telediario")),
    ("Ponme el último vídeo de Ibai en YouTube.", juez_video("ibai")),
]


def _asistente():
    """La Lina de verdad (ajustes, claves, IA y búsqueda), sin Whisper (la frase llega escrita) y sin abrir nada: cada xdg-open se apunta."""
    from lina.nucleo import asistente as A
    from lina.nucleo import herramientas as H
    A.MODELOS.cargar_whisper = lambda *a, **k: MagicMock()
    abiertas = []
    real = H.Ejecutor.herramienta

    def herramienta(self, args):
        comando = str((args or {}).get("comando", "")).strip()
        if comando.startswith("xdg-open"):
            abiertas.append(comando.split(None, 1)[1].strip().strip("'\"") if " " in comando else "")
            return "Lanzado."
        return real(self, args)
    H.Ejecutor.herramienta = herramienta
    a = A.Asistente()
    a.titulo, a.contexto = "", {"tipo": "general", "nombre": None, "clase": ""}
    a.hilo_captura, a.ruta_captura, a.ventana_al_pulsar = None, None, {}
    return A, a, abiertas


def pasar(frase, A, a, abiertas, tope=TOPE_SEG):
    """(abiertas, dicho, segundos) de una petición, cortándola si pasa de `tope`."""
    abiertas.clear()
    dicho = []
    a.decir = dicho.append
    a._hablar = lambda texto, *x, **k: None
    a.historial = []
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
    return list(abiertas), dicho, time.time() - t0


def principal(argv, salida=print):
    if argv[:1] in (["-h"], ["--help"], ["ayuda"]):
        salida(T(AYUDA))
        return 0
    casos = CASOS[:int(argv[0])] if argv[:1] and argv[0].isdigit() else CASOS
    from lina.nucleo import claves as CL
    from lina.nucleo import ia as IA
    CL.proteger_salida()
    salida(T("Paso {n} peticiones por tu Lina, sin abrir nada (unos segundos cada una)…", n=len(casos)))
    A, a, abiertas = _asistente()
    cuenta, filas = {}, []
    with IA.solo_medida():
        for frase, juez in casos:
            abiertas_caso, dicho, seg = pasar(frase, A, a, abiertas)
            nota, motivo = juez(abiertas_caso, dicho)
            cuenta[nota] = cuenta.get(nota, 0) + 1
            filas.append((frase, nota, motivo, seg, abiertas_caso, dicho))
    salida("")
    for frase, nota, motivo, seg, abiertas_caso, dicho in filas:
        salida(f"{nota:9} {seg:5.1f} s  {len(abiertas_caso)} pág.  {frase}")
        salida(f"            {motivo}")
        for u in abiertas_caso:
            salida(f"            → {u}")
        if dicho:
            salida(f"            dice: {' '.join(dicho)[:200]}")
    salida("")
    salida(T("Bien: {b} · a medias: {m} · mal: {x} · revisar: {r} · media {s:.1f} s · {p} páginas abiertas", b=cuenta.get("bien", 0),
             m=cuenta.get("a medias", 0), x=cuenta.get("mal", 0), r=cuenta.get("revisar", 0), s=sum(f[3] for f in filas) / max(1, len(filas)),
             p=sum(len(f[4]) for f in filas)))
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
