# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""«Ponme el partido»: es abrirlo para verlo (en la plataforma oficial), no informar; si solo se informó, el código lo reintenta; al insistir, un nombre
que no existe se trata primero como mal oído («rayador» = «navegador»). HOME aislado; la IA, simulada."""
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import constantes as K
from lina.nucleo import turnos as TU


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
