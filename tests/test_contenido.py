# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""«Ponme…»: entiende la IA, elige el código (contenido.py). Solo se abre una página que se pueda comprobar con la PROPIA página: de esa plataforma, que
nombre lo pedido (sin palabras de más), de esta temporada, año y torneo, de tu país, y que no sea portada, guía ni noticia. Si es un partido y hoy no hay,
se dice. Búsqueda, páginas e IA simuladas; HOME aislado."""
import datetime
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import contenido as CONT
from lina.nucleo import turnos as TU

HOY = datetime.date(2026, 10, 25)
PARTIDO = "Ponme el partido del Barça contra el Sevilla."
BUENA = "https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-26-27/fc-barcelona-sevilla/ficha?tipo=E&id=4345779"
FEMENINA = "https://www.movistarplus.es/deportes/futbol-espanol/liga-f-26-27/barcelona-sevilla/ficha?tipo=E&id=4409913"
ANTIGUA = "https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-25-26/barcelona-sevilla/ficha?tipo=E&id=4067960"
OTRO_RIVAL = "https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-26-27/r-racing-club-sevilla/ficha?tipo=E&id=4345765"
GUIA = "https://www.movistarplus.es/programacion-tv/daznli/2026-10-25"


@pytest.fixture(autouse=True)
def octubre_2026(monkeypatch):
    original = TU.temporada_actual
    monkeypatch.setattr(TU, "temporada_actual", lambda hoy=None: original(hoy or HOY))
    monkeypatch.setattr(CONT.datetime, "date", type("D", (datetime.date,), {"today": staticmethod(lambda: HOY)}))
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)


def _que(tipo="evento", terminos=("FC Barcelona", "Sevilla FC"), torneo="LaLiga", fecha=HOY, temporada=0, episodio=0, titulo_episodio="", plataformas=()):
    return {"tipo": tipo, "terminos": list(terminos), "torneo": torneo, "fecha_evento": fecha, "temporada": temporada, "episodio": episodio,
            "titulo_episodio": titulo_episodio, "plataformas": list(plataformas)}


def _buscador(por_web):
    """Búsqueda simulada: {dominio: [(título, dirección, resumen)]}."""
    def resultados(consulta, dominio, maximo=5):
        return [{"title": t, "url": u, "content": c} for t, u, c in por_web.get(dominio, [])]
    return resultados


def _paginas(titulos):
    """Descarga simulada: {dirección: título que da la página} (None = no deja leerla)."""
    def descargar(url):
        if url not in titulos or titulos[url] is None:
            raise RuntimeError("no deja leerla")
        return f"<html><head><title>{titulos[url]}</title></head></html>".encode(), "text/html", url, None
    return descargar


def _elegir(que, por_web, titulos, peticion=PARTIDO, preferencias=()):
    return CONT.elegir(que, peticion, preferencias, hoy=HOY, resultados_de=_buscador(por_web), descargar=_paginas(titulos))


# ---------- partidos ----------
def test_elige_la_ficha_de_hoy_con_los_dos_equipos():
    web = {"movistarplus.es": [("Ver Jornada 6: Barcelona - Sevilla", FEMENINA, ""), ("Ver Jornada 35: Barcelona - Sevilla", ANTIGUA, ""),
                               ("Ver Jornada 11: Racing - Sevilla", OTRO_RIVAL, ""), ("Programación DAZN LaLiga", GUIA, ""),
                               ("Ver Jornada 10: Barcelona - Sevilla", BUENA, "")]}
    r = _elegir(_que(), web, {BUENA: "Ver Jornada 10: Barcelona - Sevilla (2026) | Movistar Plus"})
    assert r[0] == BUENA and r[1] == "movistarplus.es"


def test_un_partido_de_otro_torneo_o_de_otro_ano_no_vale():
    vieja = "https://www.movistarplus.es/deportes/tenis/open-de-australia-2026/alcaraz-sinner/ficha?tipo=E&id=1"
    que = _que(terminos=("Alcaraz", "Sinner"), torneo="Masters de París")
    assert _elegir(que, {"movistarplus.es": [("Ver Alcaraz - Sinner", vieja, "")]}, {vieja: "Ver Masculino: Alcaraz - Sinner (2026)"}) is None
    buena = "https://www.movistarplus.es/deportes/tenis/masters-1000-paris-2026/alcaraz-sinner/ficha?tipo=E&id=2"
    assert _elegir(que, {"movistarplus.es": [("Ver Alcaraz - Sinner", buena, "")]}, {buena: "Ver Masters 1000 de París: Alcaraz - Sinner (2026)"})[0] == buena


def test_un_programa_de_alrededor_no_gana_al_evento():
    post = "https://www.movistarplus.es/deportes/motor/mundial-f1-gp-de-estados-unidos-2026/el-post-de-la-formula-1/ficha?id=1"
    carrera = "https://www.movistarplus.es/deportes/motor/mundial-f1-gp-de-estados-unidos-2026/carrera-formula-1/ficha?id=2"
    que = _que(terminos=("Fórmula 1",), torneo="GP de Estados Unidos")
    web = {"movistarplus.es": [("El post de la Fórmula 1", post, ""), ("Carrera Fórmula 1", carrera, "")]}
    r = _elegir(que, web, {post: "Ver El Post de la Fórmula 1 (2026)", carrera: "Ver Carrera: GP de Estados Unidos Fórmula 1 (2026)"},
                peticion="Ponme la carrera de Fórmula 1.")
    assert r[0] == carrera


def test_otra_competicion_aunque_el_titulo_la_nombre_no_vale():
    moto3 = "https://www.movistarplus.es/deportes/motociclismo/motogp-gp-de-estados-unidos-2026/carrera-moto3/ficha?id=1"
    que = _que(terminos=("Fórmula 1",), torneo="GP de Estados Unidos")
    assert _elegir(que, {"movistarplus.es": [("Carrera Moto3 Fórmula", moto3, "")]}, {moto3: "Ver Carrera Moto3 Fórmula 1 (2026)"}) is None


def test_la_femenina_solo_si_la_pides():
    web = {"movistarplus.es": [("Ver Jornada 6: Barcelona - Sevilla", FEMENINA, "")]}
    titulos = {FEMENINA: "Ver Jornada 6: Barcelona - Sevilla (2026)"}
    assert _elegir(_que(), web, titulos) is None
    assert _elegir(_que(), web, titulos, peticion="Ponme el partido femenino del Barça contra el Sevilla")[0] == FEMENINA


def test_si_no_es_de_hoy_o_no_se_sabe_o_solo_hay_un_nombre_no_elige():
    web = {"movistarplus.es": [("Ver Jornada 10: Barcelona - Sevilla", BUENA, "")]}
    titulos = {BUENA: "Ver Jornada 10: Barcelona - Sevilla (2026)"}
    assert _elegir(_que(fecha=None), web, titulos) is None
    assert _elegir(_que(fecha=HOY + datetime.timedelta(days=3)), web, titulos) is None
    assert _elegir(_que(terminos=("FC Barcelona",), torneo="LaLiga"), web, titulos) is None     # un solo equipo: cualquier partido del Barça pasaría


def test_dos_competiciones_que_encajan_no_adivina():
    copa = "https://www.movistarplus.es/deportes/copa-del-rey-26-27/fc-barcelona-sevilla/ficha?id=9"
    web = {"movistarplus.es": [("Jornada 10: Barcelona - Sevilla", BUENA, ""), ("Copa: Barcelona - Sevilla", copa, "")]}
    assert _elegir(_que(torneo=""), web, {BUENA: "Barcelona - Sevilla", copa: "Barcelona - Sevilla"}) is None


# ---------- series, capítulos y películas ----------
NETFLIX_SERIE = "https://www.netflix.com/es/title/80057281"
NETFLIX_CHIMENEA = "https://www.netflix.com/es/title/82134925"


def test_la_propia_pagina_decide_aunque_el_buscador_la_titule_netflix():
    que = _que(tipo="serie", terminos=("Stranger Things",), torneo="", fecha=None)
    web = {"netflix.com": [("Stranger Things: Fireplace", NETFLIX_CHIMENEA, "Stranger Things"), ("Netflix", NETFLIX_SERIE, "Stranger Things temporadas")]}
    r = _elegir(que, web, {NETFLIX_CHIMENEA: "Stranger Things: Chimenea", NETFLIX_SERIE: "Stranger Things"}, peticion="Ponme Stranger Things.")
    assert r[0] == NETFLIX_SERIE


def test_la_version_de_otro_pais_no_vale():
    que = _que(tipo="serie", terminos=("Stranger Things",), torneo="", fecha=None)
    for url in ("https://www.netflix.com/tt-es/title/80057281", "https://www.netflix.com/ye/title/80057281", "https://www.max.com/ad/es/shows/x/1"):
        dominio = "max.com" if "max.com" in url else "netflix.com"
        assert _elegir(que, {dominio: [("Stranger Things", url, "")]}, {url: "Stranger Things"}, peticion="Ponme Stranger Things.") is None, url


def test_el_capitulo_pedido_y_no_otro():
    que = _que(tipo="capitulo", terminos=("The Last of Us",), torneo="", fecha=None, temporada=2, episodio=7)
    e1 = "https://www.max.com/es/es/shows/last-of-us/s2/93/e1-episodio-1/9f"
    e7 = "https://www.max.com/es/es/shows/last-of-us/s2/93/e7-episodio-7/6d"
    web = {"max.com": [("The Last of Us", e1, ""), ("The Last of Us", e7, "")]}
    r = _elegir(que, web, {e1: "The Last of Us", e7: "The Last of Us"}, peticion="Ponme el último capítulo de The Last of Us.")
    assert r[0] == e7 and r[3] is True


def test_si_no_esta_el_capitulo_vale_la_serie_y_se_dice():
    que = _que(tipo="capitulo", terminos=("Stranger Things",), torneo="", fecha=None, temporada=2, episodio=3)
    r = _elegir(que, {"netflix.com": [("Netflix", NETFLIX_SERIE, "Stranger Things")]}, {NETFLIX_SERIE: "Stranger Things"})
    assert r[0] == NETFLIX_SERIE and r[3] is False


def test_una_coleccion_un_making_of_o_una_web_de_noticias_no_valen():
    que = _que(tipo="serie", terminos=("The Last of Us",), torneo="", fecha=None)
    for url, titulo in (("https://www.max.com/collections/watch-free/the-last-of-us-s1-e1/93", "The Last of Us"),
                        ("https://www.max.com/es/es/shows/making-of-the-last-of-us/34", "Making of The Last of Us"),
                        ("https://www.netflix.com/tudum/the-last-of-us", "The Last of Us")):
        dominio = "max.com" if "max.com" in url else "netflix.com"
        assert _elegir(que, {dominio: [("The Last of Us", url, "")]}, {url: titulo}, peticion="Ponme The Last of Us.") is None, url


def test_el_titulo_con_el_nombre_de_la_plataforma_delante_vale():
    url = "https://www.primevideo.com/-/es/detail/Oppenheimer/0TQ"
    que = _que(tipo="pelicula", terminos=("Oppenheimer",), torneo="", fecha=None)
    assert _elegir(que, {"primevideo.com": [("Oppenheimer", url, "")]}, {url: "Prime Video: Oppenheimer"}, peticion="Ponme Oppenheimer.")[0] == url


def test_si_la_pagina_no_deja_leerla_solo_vale_una_direccion_que_lo_nombra_entero():
    que = _que(tipo="pelicula", terminos=("Oppenheimer",), torneo="", fecha=None, plataformas=("rtve.es",))
    nombra = "https://www.rtve.es/play/videos/cine-internacional/oppenheimer/1"
    no_nombra = "https://www.dazn.com/es-ES/fixture/ContentId:1lwb/1lwb"
    assert _elegir(que, {"rtve.es": [("Oppenheimer", nombra, "")]}, {nombra: None}, peticion="Ponme Oppenheimer.")[0] == nombra
    evento = _que(terminos=("FC Barcelona", "Sevilla FC"))
    assert _elegir(evento, {"dazn.com": [("FC Barcelona - Sevilla FC", no_nombra, "")]}, {no_nombra: None}) is None


def test_solo_plataformas_de_la_lista_y_primero_la_tuya():
    que = _que(plataformas=("laligatv.es", "dazn.com", "movistarplus.es"))
    assert CONT.plataformas(que) == ["dazn.com", "movistarplus.es", "max.com"]
    assert CONT.plataformas(que, ["el fútbol lo veo en Movistar Plus"])[0] == "movistarplus.es"
    otra = "https://otra-web.example/laliga-ea-sports-26-27/fc-barcelona-sevilla/ficha"
    assert _elegir(_que(), {"movistarplus.es": [("Barcelona - Sevilla", otra, "")]}, {otra: "Barcelona - Sevilla"}) is None


def test_fecha_hablada():
    assert CONT.fecha_hablada(datetime.date(2026, 10, 31)) == "el sábado 31 de octubre"


def test_entender_le_pasa_a_la_ia_la_peticion_la_fecha_y_los_resultados():
    vistos = {}

    def consultar(clave, prompt, esquema, contenido, etiqueta, validar, maximo=200):
        vistos["contenido"] = contenido
        obj = {"tipo": "evento", "terminos": ["FC Barcelona", "Sevilla FC"], "torneo": "LaLiga", "fecha_evento": "2026-10-25", "temporada": 0,
               "episodio": 0, "titulo_episodio": "", "plataformas": ["movistarplus.es"]}
        validar(obj)
        return obj, "modelo"
    que = CONT.entender("clave", PARTIDO, ["el fútbol lo veo en Movistar Plus"], hoy=HOY,
                        buscar=lambda q, d, maximo=6: [{"title": "Barça - Sevilla hoy", "url": "https://x.es/a", "content": "a las 21:00"}], consultar=consultar)
    assert que["fecha_evento"] == HOY and que["terminos"] == ["FC Barcelona", "Sevilla FC"]
    assert "2026-10-25" in vistos["contenido"] and "Movistar Plus" in vistos["contenido"] and "a las 21:00" in vistos["contenido"]


# ---------- en el asistente ----------
def _asistente(monkeypatch, que, hallada, resultado="Lanzado."):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.clave = "clave"
    a.ejecutor = MagicMock()
    a.ejecutor.pendientes = []
    a.ejecutor.herramienta.return_value = resultado
    a.nueva_tarea = lambda: None
    a._con_claves = lambda modo, funcion, *args: que
    monkeypatch.setattr(A.CONT, "elegir", lambda que, peticion, preferencias=(): hallada)
    monkeypatch.setattr(A, "datetime", type("DT", (), {"now": staticmethod(lambda: datetime.datetime(2026, 10, 25, 20, 0))}))
    return A, a


def test_el_asistente_abre_la_pagina_comprobada_sin_ia(monkeypatch):
    A, a = _asistente(monkeypatch, _que(), (BUENA, "movistarplus.es", "Ver Jornada 10", False))
    frase, ident = a._intentar_contenido(PARTIDO, A.TIE.Cronometro())
    assert ident == "contenido" and "FC Barcelona - Sevilla FC" in frase and "Movistar Plus" in frase
    assert BUENA in a.ejecutor.herramienta.call_args.args[0]["comando"]


def test_si_es_otro_dia_lo_dice_sin_abrir_nada(monkeypatch):
    A, a = _asistente(monkeypatch, _que(fecha=datetime.date(2026, 10, 31)), (BUENA, "movistarplus.es", "x", False))
    frase, _ = a._intentar_contenido(PARTIDO, A.TIE.Cronometro())
    assert "el sábado 31 de octubre" in frase and not a.ejecutor.herramienta.called


def test_un_capitulo_sin_enlace_directo_dice_cual_elegir(monkeypatch):
    que = _que(tipo="capitulo", terminos=("Stranger Things",), torneo="", fecha=None, temporada=2, episodio=3)
    A, a = _asistente(monkeypatch, que, (NETFLIX_SERIE, "netflix.com", "Stranger Things", False))
    frase, _ = a._intentar_contenido("Ponme el capítulo 3 de la segunda temporada de Stranger Things", A.TIE.Cronometro())
    assert "Netflix" in frase and "temporada 2, capítulo 3" in frase


def test_sin_entender_sin_pagina_o_si_no_se_abre_lo_intenta_la_ia(monkeypatch):
    A, a = _asistente(monkeypatch, None, None)
    assert a._intentar_contenido(PARTIDO, A.TIE.Cronometro()) is None
    A, a = _asistente(monkeypatch, _que(tipo="video", terminos=("Ibai",)), None)
    assert a._intentar_contenido("Ponme el último vídeo de Ibai", A.TIE.Cronometro()) is None
    A, a = _asistente(monkeypatch, _que(), None)
    assert a._intentar_contenido(PARTIDO, A.TIE.Cronometro()) is None
    A, a = _asistente(monkeypatch, _que(), (BUENA, "movistarplus.es", "x", False), resultado="BLOQUEADO: no")
    assert a._intentar_contenido(PARTIDO, A.TIE.Cronometro()) is None
    A, a = _asistente(monkeypatch, _que(), (BUENA, "movistarplus.es", "x", False))
    assert a._intentar_contenido("¿A qué hora es el partido del Barça?", A.TIE.Cronometro()) is None


def test_una_sola_pagina_por_peticion_cuando_decide_la_ia(monkeypatch):
    A, a = _asistente(monkeypatch, None, None)
    a.pregunta_pura = PARTIDO
    a.acciones_turno = [("ejecutar_comando", {"comando": f"xdg-open '{BUENA}'"}, "Lanzado.")]
    assert "ya está abierta" in a._otra_pagina_de_mas(f"xdg-open '{BUENA}'")
    assert "Ya hay abierta una página" in a._otra_pagina_de_mas("xdg-open https://www.dazn.com/es-ES/home")
    a.acciones_turno = [("ejecutar_comando", {"comando": "xdg-open https://www.dazn.com/es-ES/home"}, "Lanzado.")]
    assert a._otra_pagina_de_mas(f"xdg-open '{BUENA}'") is None                      # la anterior no valía: puede abrir la buena
