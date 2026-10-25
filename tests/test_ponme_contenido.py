# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""«Ponme el partido»: es abrirlo para verlo (en la plataforma oficial), no informar; si solo se informó, el código lo reintenta; al insistir, un nombre
que no existe se trata primero como mal oído («rayador» = «navegador»). HOME aislado; la IA, simulada."""
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import constantes as K
from lina.nucleo import turnos as TU


@pytest.fixture(autouse=True)
def idioma_del_equipo(monkeypatch):
    """Las direcciones con país («es-ES») se comparan con el idioma del equipo: se fija para que dé igual dónde se pasen las pruebas."""
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)


def test_las_instrucciones_dicen_que_ponme_es_abrirlo_en_la_plataforma_oficial():
    assert "PONGAS un partido" in K.INSTRUCCIONES and "plataforma OFICIAL" in K.INSTRUCCIONES and "emisiones no oficiales" in K.INSTRUCCIONES
    assert "nunca escribes contraseñas" in K.INSTRUCCIONES
    assert "PUT ON a match" in K.INSTRUCCIONES_EN and "OFFICIAL platform" in K.INSTRUCCIONES_EN and "unofficial streams" in K.INSTRUCCIONES_EN


@pytest.mark.parametrize("frase", ["Ponme el partido del Barça contra el Sevilla.", "Pon el partido en el navegador", "ponme el partido en el rayador",
                                   "Abre Steam", "Reproduce el último vídeo de mi canal", "Quiero ver el Clásico"])
def test_pide_accion(frase):
    assert TU.pide_accion(frase), frase


@pytest.mark.parametrize("frase", ["¿A qué hora es el partido?", "¿Dónde echan el Barça - Sevilla?", "Dime quién ganó ayer", "¿Qué tiempo hace?",
                                   "pongamos que sí"])
def test_no_pide_accion(frase):
    assert not TU.pide_accion(frase), frase


def test_solo_se_informo():
    leer = lambda c: c.startswith(("ls", "cat", "xdg-settings get"))
    assert TU.solo_se_informo([("buscar_web", {"consulta": "x"}, "r"), ("mas_herramientas", {}, "r")], leer)
    assert TU.solo_se_informo([("ejecutar_comando", {"comando": "xdg-settings get default-web-browser"}, "r")], leer)
    assert not TU.solo_se_informo([("buscar_web", {}, "r"), ("ejecutar_comando", {"comando": "xdg-open https://www.dazn.com"}, "r")], leer)
    assert not TU.solo_se_informo([("abrir_app", {"nombre": "Brave"}, "r")], leer)


def _asistente(pregunta, acciones, respuesta_a_fondo="Te abro DAZN en Brave."):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock()
    a.ejecutor.duda, a.ejecutor.pendientes, a.ejecutor.recetas_diferidas, a.ejecutor.efecto_sin_comprobar = "", [], [], False
    a.clave, a.pregunta_pura, a.historial, a.acciones_turno = "clave", pregunta, [], acciones
    a.pedir_profundo, a.obstaculo, a.insistiendo, a.pantalla_adjunta = "", "", False, False
    a._cerrar_receta_interfaz = lambda bueno: None
    a._avisar_voz = lambda t: None
    a._acciones_comprobadas = lambda: False
    enviadas = []
    a._gemini = lambda modo, modelo, texto, *x, **k: (enviadas.append(texto), respuesta_a_fondo)[1]
    return A, a, enviadas


def test_si_pidio_ponerlo_y_solo_se_informo_se_reintenta_sin_revisor(monkeypatch):
    A, a, enviadas = _asistente("Ponme el partido del Barça contra el Sevilla.", [("buscar_web", {"consulta": "barça sevilla"}, "…")])
    monkeypatch.setattr(A, "verificar_cumplimiento", MagicMock(side_effect=AssertionError("no hace falta el revisor")))
    r, _ = a._insistir_si_hace_falta("Según Marca, se emite por DAZN a las 21:00.", "m", "rapido", "p", None, [], "s")
    assert r == "Te abro DAZN en Brave." and enviadas
    assert "HICIERAS" in enviadas[0] and "rayador" in enviadas[0]       # y al insistir sabe que un nombre que no existe puede estar mal oído


def test_una_pregunta_con_solo_busqueda_no_se_reintenta(monkeypatch):
    A, a, enviadas = _asistente("¿A qué hora es el partido del Barça?", [("buscar_web", {"consulta": "x"}, "…")])
    monkeypatch.setattr(A, "verificar_cumplimiento", lambda *x, **k: False)
    r, _ = a._insistir_si_hace_falta("Según Marca, a las 21:00.", "m", "rapido", "p", None, [], "s")
    assert r == "Según Marca, a las 21:00." and not enviadas


def test_si_ya_lo_abrio_no_se_reintenta(monkeypatch):
    A, a, enviadas = _asistente("Ponme el partido del Barça", [("buscar_web", {}, "…"), ("ejecutar_comando", {"comando": "xdg-open https://www.dazn.com/es-ES/fixture/barcelona-sevilla"}, "código de salida: 0")])
    monkeypatch.setattr(A, "verificar_cumplimiento", lambda *x, **k: False)
    r, _ = a._insistir_si_hace_falta("Te abro DAZN en Brave.", "m", "rapido", "p", None, [], "s")
    assert r == "Te abro DAZN en Brave." and not enviadas


def test_la_pista_de_whisper_lleva_navegador():
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    assert "navegador" in A.prompt_whisper()


# ---------- buscar dentro de la web de la plataforma y no quedarse en su portada ----------
def test_la_regla_dice_buscar_dentro_de_la_plataforma_y_no_quedarse_en_la_portada():
    assert "busca DENTRO de su web" in K.INSTRUCCIONES and "temporada" in K.INSTRUCCIONES and "pulse «Ver»" in K.INSTRUCCIONES
    assert "search INSIDE its website" in K.INSTRUCCIONES_EN and "season" in K.INSTRUCCIONES_EN


@pytest.mark.parametrize("entrada, esperado", [("movistarplus.es", "movistarplus.es"), ("https://www.movistarplus.es/deportes", "movistarplus.es"),
                                               ("WWW.DAZN.COM", "dazn.com"), ("ver.movistarplus.es", "ver.movistarplus.es"),
                                               ("no es un dominio", None), ("javascript:alert(1)", None), ("", None), ("localhost", None)])
def test_dominio_valido(entrada, esperado):
    from lina.nucleo import ia as IA
    assert IA.dominio_valido(entrada) == esperado


def test_la_busqueda_dentro_de_una_web_se_lo_pide_a_tavily(monkeypatch):
    from lina.nucleo import ia as IA
    enviado = {}

    class _R:
        ok = True

        def json(self):
            return {"results": [{"title": "Ver Jornada 10: Barcelona - Sevilla", "url": "https://www.movistarplus.es/deportes/ficha?id=1", "content": "Hoy"}]}
    monkeypatch.setattr(IA.CL, "obtener", lambda nombre: "clave-de-prueba")
    monkeypatch.setattr(IA.requests, "post", lambda url, headers=None, json=None, timeout=None: (enviado.update(json), _R())[1])
    r = IA.buscar_tavily("barcelona sevilla jornada 10", "https://www.movistarplus.es/")
    assert enviado["include_domains"] == ["movistarplus.es"] and "ficha?id=1" in r
    enviado.clear()
    IA.buscar_tavily("barcelona sevilla")
    assert "include_domains" not in enviado


def test_un_dominio_mal_formado_no_busca(monkeypatch):
    from lina.nucleo import ia as IA
    monkeypatch.setattr(IA.CL, "obtener", lambda nombre: "clave-de-prueba")
    monkeypatch.setattr(IA.requests, "post", MagicMock(side_effect=AssertionError("no debía buscar")))
    assert "no es un nombre de web válido" in IA.buscar_tavily("x", "no es un dominio")


def test_buscar_web_pasa_el_dominio(monkeypatch):
    A, a, _ = _asistente("x", [])
    a.busquedas_turno, a.max_busquedas = 0, 2
    pedidas = []
    monkeypatch.setattr(A, "buscar_tavily", lambda consulta, dominio=None: pedidas.append((consulta, dominio)) or "ok")
    a._ejecutar_herramienta("buscar_web", {"consulta": "barcelona sevilla", "dominio": "movistarplus.es"})
    assert pedidas == [("barcelona sevilla", "movistarplus.es")]


def test_solo_portadas():
    leer = lambda c: False
    assert TU.solo_portadas([("buscar_web", {}, ""), ("ejecutar_comando", {"comando": "xdg-open https://www.movistarplus.es"}, "")], leer) == "www.movistarplus.es"
    assert TU.solo_portadas([("ejecutar_comando", {"comando": "xdg-open https://www.dazn.com/"}, "")], leer) == "www.dazn.com"
    assert TU.solo_portadas([("ejecutar_comando", {"comando": "xdg-open https://www.movistarplus.es/deportes/ficha?id=1"}, "")], leer) is None
    assert TU.solo_portadas([("ejecutar_comando", {"comando": "xdg-open https://www.movistarplus.es/?q=barça"}, "")], leer) is None
    assert TU.solo_portadas([("abrir_app", {"nombre": "Brave"}, "")], leer) is None
    assert TU.solo_portadas([("buscar_web", {}, "")], leer) is None


def test_abrir_solo_la_portada_tras_ponme_hace_insistir(monkeypatch):
    A, a, enviadas = _asistente("Ponme el partido del Barça en el navegador",
                                [("buscar_web", {}, "…"), ("ejecutar_comando", {"comando": "xdg-open https://www.movistarplus.es"}, "código de salida: 0")])
    monkeypatch.setattr(A, "verificar_cumplimiento", MagicMock(side_effect=AssertionError("no hace falta el revisor")))
    a._insistir_si_hace_falta("El partido lo emite Movistar Plus, te he abierto la plataforma.", "m", "rapido", "p", None, [], "s")
    assert enviadas and "PUSIERAS" in enviadas[0] and "«movistarplus.es»" in enviadas[0]


def test_abrir_la_ficha_no_hace_insistir(monkeypatch):
    A, a, enviadas = _asistente("Ponme el partido del Barça", [("buscar_web", {}, "…"), ("ejecutar_comando", {
        "comando": "xdg-open 'https://www.movistarplus.es/deportes/futbol-espanol/laliga/fc-barcelona-sevilla/ficha?tipo=E&id=1'"}, "código de salida: 0")])
    monkeypatch.setattr(A, "verificar_cumplimiento", lambda *x, **k: False)
    a._insistir_si_hace_falta("Te abro el partido; si no empieza solo, pulsa Ver.", "m", "rapido", "p", None, [], "s")
    assert not enviadas


def test_abrir_una_web_que_se_pidio_abrir_no_hace_insistir(monkeypatch):
    A, a, enviadas = _asistente("Abre YouTube", [("ejecutar_comando", {"comando": "xdg-open https://www.youtube.com"}, "código de salida: 0")])
    monkeypatch.setattr(A, "verificar_cumplimiento", lambda *x, **k: False)
    a._insistir_si_hace_falta("Abierto.", "m", "rapido", "p", None, [], "s")
    assert not enviadas


# ---------- lo que se abre tiene que ser la página de lo pedido ----------
_PARTIDO = "Ponme el partido del Barça contra el Sevilla."


def _abre(url, resultados=""):
    return [("buscar_web", {"consulta": "x"}, resultados), ("ejecutar_comando", {"comando": f"xdg-open '{url}'"}, "código de salida: 0")]


def test_palabras_distintivas():
    assert TU.palabras_distintivas(_PARTIDO) == {"barcelona", "sevilla"}
    assert TU.palabras_distintivas("Ponme Stranger Things en el navegador") == {"stranger", "things"}
    assert TU.palabras_distintivas("ponme el partido") == set()


@pytest.mark.parametrize("url, motivo", [
    ("https://www.movistarplus.es/programacion-tv/daznli/2026-10-25", "guía de programación"),
    ("https://www.movistarplus.es/deportes/futbol/la-liga-ea-sports/calendario", "guía de programación"),
    ("https://www.movistarplus.es", "portada"),
    ("https://www.movistarplus.es/deportes/futbol/ofertas", "no nombra"),
])
def test_lo_que_no_es_la_pagina_del_partido(url, motivo):
    r = TU.pagina_que_no_es(_abre(url), _PARTIDO, lambda c: False)
    assert r and motivo in r[1], (url, r)


@pytest.mark.parametrize("url, pregunta, resultados", [
    ("https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-26-27/fc-barcelona-sevilla/ficha?tipo=E&id=1", _PARTIDO, ""),
    ("https://www.netflix.com/es/series/stranger-things", "Ponme Stranger Things", ""),
    ("https://www.netflix.com/es/title/80057281", "Ponme Stranger Things",
     "RESULTADOS DE BÚSQUEDA:\n\n[1] Stranger Things | Sitio oficial de Netflix (netflix.com) https://www.netflix.com/es/title/80057281\nSerie"),
    ("https://www.movistarplus.es", "Ponme Movistar Plus", ""),
    ("https://www.dazn.com/es-ES/home", "ponme el partido", ""),             # sin palabras con las que comparar: no se juzga
])
def test_lo_que_si_es_la_pagina_de_lo_pedido(url, pregunta, resultados):
    assert TU.pagina_que_no_es(_abre(url, resultados), pregunta, lambda c: False) is None


def test_un_identificador_sin_titulo_que_lo_nombre_no_basta():
    r = TU.pagina_que_no_es(_abre("https://www.netflix.com/es/title/80057281"), "Ponme Stranger Things", lambda c: False)
    assert r and "no nombra" in r[1]


def test_abrir_la_programacion_del_canal_hace_insistir_con_buenas_indicaciones(monkeypatch):
    A, a, enviadas = _asistente(_PARTIDO, _abre("https://www.movistarplus.es/programacion-tv/daznli/2026-10-25"))
    monkeypatch.setattr(A, "verificar_cumplimiento", MagicMock(side_effect=AssertionError("no hace falta el revisor")))
    a._insistir_si_hace_falta("Lo emite DAZN LALIGA en Movistar Plus, ya lo he abierto.", "m", "rapido", "p", None, [], "s")
    assert enviadas and "guía de programación" in enviadas[0] and "«movistarplus.es»" in enviadas[0] and "ficha" in enviadas[0]


def test_la_regla_dice_como_buscar_y_que_no_abrir():
    assert "nunca abras una guía de programación" in K.INSTRUCCIONES and "«ficha» o «ver»" in K.INSTRUCCIONES
    assert "never open a TV guide" in K.INSTRUCCIONES_EN


# ---------- la temporada de ahora, no la pasada ----------
import datetime  # noqa: E402

_ANTIGUA = "https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-25-26/barcelona-sevilla/ficha?tipo=E&id=4067960"
_ACTUAL = "https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-26-27/fc-barcelona-sevilla/ficha?tipo=E&id=4345779"


@pytest.fixture
def octubre_2026(monkeypatch):
    original = TU.temporada_actual
    monkeypatch.setattr(TU, "temporada_actual", lambda hoy=None: original(hoy or datetime.date(2026, 10, 25)))


def test_temporada_actual():
    assert TU.temporada_actual(datetime.date(2026, 10, 25)) == (26, 27)
    assert TU.temporada_actual(datetime.date(2026, 5, 3)) == (25, 26)
    assert TU.temporada_actual(datetime.date(2026, 7, 1)) == (26, 27)


def test_de_otra_temporada(octubre_2026):
    assert TU.de_otra_temporada(_ANTIGUA) == "25-26"
    assert TU.de_otra_temporada(_ACTUAL) is None
    assert TU.de_otra_temporada("Liga 2024/2025") == "24-25" and TU.de_otra_temporada("liga 2025-2026") == "25-26"
    assert TU.de_otra_temporada("https://www.movistarplus.es/programacion-tv/daznli/2026-10-25") is None    # una fecha no es una temporada
    assert TU.de_otra_temporada("Stranger Things") is None


def test_la_ficha_de_la_temporada_pasada_no_vale(octubre_2026):
    r = TU.pagina_que_no_es(_abre(_ANTIGUA), _PARTIDO, lambda c: False)
    assert r and "temporada 25-26" in r[1] and "26-27" in r[1]
    assert TU.pagina_que_no_es(_abre(_ACTUAL), _PARTIDO, lambda c: False) is None


def test_los_resultados_de_otra_temporada_van_marcados(monkeypatch, octubre_2026):
    from lina.nucleo import ia as IA

    class _R:
        ok = True

        def json(self):
            return {"results": [{"title": "Jornada 35: Barcelona - Sevilla (2026)", "url": _ANTIGUA, "content": "Mayo"},
                                {"title": "Ver Jornada 10: Barcelona - Sevilla (2026)", "url": _ACTUAL, "content": "Hoy 21:00"}]}
    monkeypatch.setattr(IA.CL, "obtener", lambda nombre: "clave-de-prueba")
    monkeypatch.setattr(IA.requests, "post", lambda *a, **k: _R())
    r = IA.buscar_tavily("barcelona sevilla ficha", "movistarplus.es")
    antigua, actual = r.split("[2]")
    assert "OJO: es de la temporada 25-26, NO de la actual (26-27)" in antigua and "OJO" not in actual


def test_abrir_la_ficha_antigua_hace_insistir_con_el_modelo_rapido(monkeypatch, octubre_2026):
    A, a, enviadas = _asistente(_PARTIDO, _abre(_ANTIGUA))
    grupos = []
    a._gemini = lambda modo, modelo, texto, *x, **k: (grupos.append(modo), enviadas.append(texto),
                                                      a.acciones_turno.append(("ejecutar_comando", {"comando": f"xdg-open '{_ACTUAL}'"}, "Lanzado.")),
                                                      "Te abro el partido de esta temporada.")[3]
    a._avisar_voz = MagicMock()
    monkeypatch.setattr(A, "verificar_cumplimiento", MagicMock(side_effect=AssertionError("no hace falta el revisor")))
    r, origen = a._insistir_si_hace_falta("Abro el partido en Movistar Plus.", "m", "rapido", "p", None, [], "s")
    assert r == "Te abro el partido de esta temporada." and grupos == ["rapido"] and "insistió" in origen
    assert "temporada 25-26" in enviadas[0]
    a._avisar_voz.assert_not_called()                              # sin «lo pienso a fondo»: es rápido


# ---------- noticias, varias competiciones y la plataforma que prefieres ----------
def test_una_noticia_no_es_la_pagina_para_verlo():
    r = TU.pagina_que_no_es(_abre("https://www.dazn.com/es-ES/news/futbol/clasico-laliga-barcelona-sevilla/1mrs35"), _PARTIDO, lambda c: False)
    assert r and "noticia" in r[1]


def test_competicion_de_y_varias_de_ahora(octubre_2026):
    laliga = "https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-26-27/fc-barcelona-sevilla/ficha?id=1"
    ligaf = "https://www.movistarplus.es/deportes/futbol-espanol/liga-f-26-27/barcelona-sevilla/ficha?id=2"
    assert TU.competicion_de(laliga) == "laliga-ea-sports" and TU.competicion_de(ligaf) == "liga-f" and TU.competicion_de("https://x.es/serie") is None
    assert TU.competiciones_de_ahora([laliga, ligaf, _ANTIGUA]) == ["laliga-ea-sports", "liga-f"]
    assert TU.competiciones_de_ahora([laliga, _ANTIGUA]) == ["laliga-ea-sports"]


def test_los_resultados_avisan_si_hay_varias_competiciones_de_ahora(monkeypatch, octubre_2026):
    from lina.nucleo import ia as IA

    class _R:
        ok = True

        def json(self):
            return {"results": [{"title": "Ver Jornada 10: Barcelona - Sevilla", "url": _ACTUAL, "content": ""},
                                {"title": "Ver Jornada 6: Barcelona - Sevilla", "url": "https://www.movistarplus.es/deportes/futbol-espanol/liga-f-26-27/"
                                                                                     "barcelona-sevilla/ficha?id=2", "content": ""}]}
    monkeypatch.setattr(IA.CL, "obtener", lambda nombre: "clave-de-prueba")
    monkeypatch.setattr(IA.requests, "post", lambda *a, **k: _R())
    r = IA.buscar_tavily("barcelona sevilla ficha", "movistarplus.es")
    assert "competiciones distintas (laliga-ea-sports, liga-f)" in r and "pregúntaselo" in r


def test_la_plataforma_que_prefieres_viene_al_caso_de_un_partido(tmp_path, monkeypatch):
    from lina.nucleo import memoria as M
    monkeypatch.setattr(M, "ARCHIVO", tmp_path / "memoria.json")
    assert M.recordar("el fútbol lo veo en Movistar Plus")[0]
    assert M.relevantes(_PARTIDO) == ["el fútbol lo veo en Movistar Plus"]
    assert M.relevantes("¿cuándo es el Clásico?") == ["el fútbol lo veo en Movistar Plus"]
    assert M.relevantes("sube el volumen") == []                     # y no se cuela en lo que no tiene que ver
    assert M.recordar("las series las veo en Netflix")[0]
    assert M.relevantes("Ponme el último capítulo de Stranger Things") == ["las series las veo en Netflix"]


# ---------- «con el partido…» (mal oído) y comprobar también lo que se abre al insistir ----------
def test_con_al_principio_es_pon_mal_oido_y_una_pregunta_no_es_una_orden():
    assert TU.pide_contenido("con el partido del Barça contra el Sevilla.") and TU.pide_accion("con el partido del Barça contra el Sevilla.")
    assert not TU.pide_contenido("con mucho gusto") and not TU.pide_contenido("con quién juega el Barça")
    assert not TU.pide_contenido("¿con el volumen así está bien?") and not TU.pide_accion("¿Pon el volumen al 40?")


def test_lo_que_se_abre_al_insistir_tambien_se_comprueba(octubre_2026):
    A, a, _ = _asistente(_PARTIDO, _abre("https://www.dazn.com/es-ES/home"))
    vueltas = []

    def gemini(modo, modelo, texto, *x, **k):
        vueltas.append(modo)
        url = _ANTIGUA if len(vueltas) == 1 else _ACTUAL                  # primero otra página que no vale, luego la buena
        a.acciones_turno.append(("ejecutar_comando", {"comando": f"xdg-open '{url}'"}, "Lanzado."))
        return "Abierto."
    a._gemini = gemini
    assert a._asegurar_pagina_de_contenido("Te he abierto DAZN.", "p", None, [], "s") == "Abierto."
    assert vueltas == ["rapido", "rapido"]


def test_si_tras_insistir_sigue_sin_estar_lo_dice(octubre_2026):
    A, a, _ = _asistente(_PARTIDO, _abre("https://www.dazn.com/es-ES/home"))
    a._gemini = lambda *x, **k: (a.acciones_turno.append(("ejecutar_comando", {"comando": "xdg-open https://www.dazn.com/es-ES/home"}, "")), "Abierto.")[1]
    r = a._asegurar_pagina_de_contenido("Te he abierto DAZN.", "p", None, [], "s")
    assert "No he dado con la página" in r


def test_si_ya_esta_bien_no_se_toca(octubre_2026):
    A, a, _ = _asistente(_PARTIDO, _abre(_ACTUAL))
    a._gemini = MagicMock(side_effect=AssertionError("no hace falta otra vuelta"))
    assert a._asegurar_pagina_de_contenido("Abierto.", "p", None, [], "s") == "Abierto."


def test_la_pista_de_whisper_lleva_ponme():
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    assert "Ponme" in A.prompt_whisper()



# ---------- la versión de tu país, y probar en la otra plataforma ----------
def test_mi_pais_web_y_de_otro_pais():
    assert TU.mi_pais_web({"LANG": "es_ES.UTF-8"}) == "es-ES" and TU.mi_pais_web({"LANG": "C.UTF-8"}) is None
    assert TU.de_otro_pais("https://www.dazn.com/en-US/fixture/ContentId:c3/c3") == "en-US"
    assert TU.de_otro_pais("https://www.dazn.com/es-ES/fixture/ContentId:1l/1l/6g") is None
    assert TU.de_otro_pais("https://www.movistarplus.es/deportes/x") is None
    assert TU.de_otro_pais("https://www.dazn.com/en-US/fixture/x", entorno={"LANG": "C"}) is None    # sin saber el tuyo, no se juzga


def test_la_ficha_de_otro_pais_no_vale_aunque_su_titulo_lo_nombre():
    res = "RESULTADOS:\n\n[1] Barcelona vs. Sevilla - Soccer (dazn.com) https://www.dazn.com/en-US/fixture/ContentId:c3g/c3g\nx"
    r = TU.pagina_que_no_es(_abre("https://www.dazn.com/en-US/fixture/ContentId:c3g/c3g", res), _PARTIDO, lambda c: False)
    assert r and "otro país (en-US)" in r[1]


def test_la_ficha_de_dazn_de_tu_pais_vale_si_su_titulo_lo_nombra():
    url = "https://www.dazn.com/es-ES/fixture/ContentId:1lwb/1lwb/6g5e"
    res = f"RESULTADOS:\n\n[1] FC Barcelona - Sevilla FC (dazn.com) {url}\nHoy"
    assert TU.pagina_que_no_es(_abre(url, res), _PARTIDO, lambda c: False) is None


def test_la_nota_al_insistir_dice_que_pruebe_en_la_otra_plataforma():
    A, a, _ = _asistente(_PARTIDO, [])
    nota = a._nota_pagina_de_contenido("https://www.dazn.com/es-ES/home", "solo se ha abierto la portada", "p")
    assert "OTRA plataforma oficial" in nota and "otro país" in nota and "«dazn.com»" in nota
    assert "versión de otro país" in K.INSTRUCCIONES and "otra plataforma oficial" in K.INSTRUCCIONES


def test_una_seccion_de_la_portada_no_es_la_pagina_del_partido_aunque_el_titulo_lo_nombre():
    url = "https://www.dazn.com/es-ES/home/7ghp10wewr0h2z2lm8g4pams"
    res = f"RESULTADOS:\n\n[1] Barcelona - Sevilla (dazn.com) {url}\nx"
    r = TU.pagina_que_no_es(_abre(url, res), _PARTIDO, lambda c: False)
    assert r and "no nombra" in r[1]


def test_si_el_codigo_ya_comprobo_la_pagina_el_revisor_sobra(octubre_2026):
    A, a, _ = _asistente(_PARTIDO, _abre(_ACTUAL))
    assert a._acciones_comprobadas.__class__ is not None
    a._acciones_comprobadas = A.Asistente._acciones_comprobadas.__get__(a)
    assert a._acciones_comprobadas()
    b = _asistente(_PARTIDO, _abre("https://www.dazn.com/es-ES/home"))[1]
    b._acciones_comprobadas = A.Asistente._acciones_comprobadas.__get__(b)
    assert not b._acciones_comprobadas()
