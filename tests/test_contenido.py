# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""«Ponme el partido…» lo resuelve el código: busca en las plataformas oficiales y elige la ficha de ese partido (esta temporada, tu país, los dos equipos,
no la femenina si no la pides, ni portada, guía ni noticia). Búsqueda simulada; HOME aislado."""
import datetime
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import contenido as CONT
from lina.nucleo import turnos as TU

PARTIDO = "Ponme el partido del Barça contra el Sevilla."
BUENA = "https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-26-27/fc-barcelona-sevilla/ficha?tipo=E&id=4345779"
FEMENINA = "https://www.movistarplus.es/deportes/futbol-espanol/liga-f-26-27/barcelona-sevilla/ficha?tipo=E&id=4409913"
ANTIGUA = "https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-25-26/barcelona-sevilla/ficha?tipo=E&id=4067960"
OTRO_RIVAL = "https://www.movistarplus.es/deportes/futbol-espanol/laliga-ea-sports-26-27/r-racing-club-sevilla/ficha?tipo=E&id=4345765"
GUIA = "https://www.movistarplus.es/programacion-tv/daznli/2026-10-25"
DAZN_BUENA = "https://www.dazn.com/es-ES/fixture/ContentId:1lwb/1lwb/6g5e"


@pytest.fixture(autouse=True)
def octubre_2026(monkeypatch):
    original = TU.temporada_actual
    monkeypatch.setattr(TU, "temporada_actual", lambda hoy=None: original(hoy or datetime.date(2026, 10, 25)))
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)


def _buscador(por_web):
    """Búsqueda simulada: {dominio: [(título, dirección)]}; apunta qué se buscó."""
    pedidas = []

    def resultados(consulta, dominio, maximo=5):
        pedidas.append((consulta, dominio, maximo))
        return [{"title": t, "url": u, "content": ""} for t, u in por_web.get(dominio, [])]
    resultados.pedidas = pedidas
    return resultados


def test_que_es_un_partido_y_que_se_busca():
    assert CONT.es_deporte(PARTIDO) and CONT.es_deporte("pon el Clásico") and not CONT.es_deporte("ponme Stranger Things")
    assert CONT.consulta(PARTIDO) == "barcelona sevilla"
    assert CONT.consulta("ponme el partido") == ""


def test_elige_la_ficha_de_esta_temporada_con_los_dos_equipos():
    buscar = _buscador({"movistarplus.es": [("Ver Jornada 6: Barcelona - Sevilla", FEMENINA), ("Ver Jornada 35: Barcelona - Sevilla", ANTIGUA),
                                            ("Ver Jornada 11: Racing - Sevilla", OTRO_RIVAL), ("Programación DAZN LaLiga", GUIA),
                                            ("Ver Jornada 10: Barcelona - Sevilla", BUENA)]})
    assert CONT.buscar(PARTIDO, resultados_de=buscar) == (BUENA, "movistarplus.es", "Ver Jornada 10: Barcelona - Sevilla")
    consultas = {c for c, d, _ in buscar.pedidas}
    assert {"barcelona sevilla partido ficha", "barcelona sevilla jornada ficha ver"} <= consultas and all(m == 15 for _, _, m in buscar.pedidas)


def test_la_femenina_solo_si_la_pides():
    buscar = _buscador({"movistarplus.es": [("Ver Jornada 6: Barcelona - Sevilla", FEMENINA)]})
    assert CONT.buscar(PARTIDO, resultados_de=buscar) is None
    assert CONT.buscar("Ponme el partido femenino del Barça contra el Sevilla", resultados_de=buscar)[0] == FEMENINA


def test_primero_la_plataforma_que_dijiste_que_usas():
    assert CONT.plataformas(["el fútbol lo veo en DAZN"]) == ["dazn.com", "movistarplus.es"]
    assert CONT.plataformas([]) == ["movistarplus.es", "dazn.com"]
    buscar = _buscador({"dazn.com": [("FC Barcelona - Sevilla FC", DAZN_BUENA)], "movistarplus.es": [("Ver Jornada 10: Barcelona - Sevilla", BUENA)]})
    assert CONT.buscar(PARTIDO, ["el fútbol lo veo en DAZN"], resultados_de=buscar)[1] == "dazn.com"


def test_si_en_tu_plataforma_no_esta_prueba_en_la_otra():
    buscar = _buscador({"dazn.com": [("Barcelona - Sevilla: horario", "https://www.dazn.com/es-ES/news/futbol/barcelona-sevilla/1x")],
                        "movistarplus.es": [("Ver Jornada 10: Barcelona - Sevilla", BUENA)]})
    assert CONT.buscar(PARTIDO, ["el fútbol lo veo en DAZN"], resultados_de=buscar)[0] == BUENA


def test_nada_claro_o_sin_busqueda_lo_deja_a_la_ia():
    assert CONT.buscar(PARTIDO, resultados_de=_buscador({})) is None
    assert CONT.buscar(PARTIDO, resultados_de=lambda *a, **k: "La búsqueda web no está configurada.") is None
    dos = _buscador({"movistarplus.es": [("Jornada 10: Barcelona - Sevilla", BUENA),
                                         ("Copa: Barcelona - Sevilla", "https://www.movistarplus.es/deportes/copa-del-rey-26-27/fc-barcelona-sevilla/ficha?id=9")]})
    assert CONT.buscar(PARTIDO, resultados_de=dos) is None                  # dos competiciones que encajan: no adivina


def test_solo_abre_direcciones_de_la_plataforma():
    buscar = _buscador({"movistarplus.es": [("Ver Jornada 10: Barcelona - Sevilla", "https://otra-web.example/laliga-ea-sports-26-27/fc-barcelona-sevilla/ficha")]})
    assert CONT.buscar(PARTIDO, resultados_de=buscar) is None


# ---------- en el asistente: sin IA, por el ejecutor de siempre ----------
def _asistente(monkeypatch, hallada, resultado="Lanzado."):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock()
    a.ejecutor.pendientes = []
    a.ejecutor.herramienta.return_value = resultado
    a.nueva_tarea = lambda: None
    monkeypatch.setattr(A.CONT, "buscar", lambda peticion, preferencias=(): hallada)
    return A, a


def test_el_asistente_lo_abre_sin_ia(monkeypatch):
    A, a = _asistente(monkeypatch, (BUENA, "movistarplus.es", "Ver Jornada 10"))
    frase, ident = a._intentar_contenido(PARTIDO, A.TIE.Cronometro())
    assert ident == "contenido" and "Movistar Plus" in frase and "Ver" in frase
    comando = a.ejecutor.herramienta.call_args.args[0]["comando"]
    assert comando.startswith("xdg-open ") and BUENA in comando
    a.ejecutor.contaminar.assert_called_once()                              # lo que siga en esta tarea, con el freno de siempre


def test_si_no_lo_encuentra_o_no_se_abre_lo_intenta_la_ia(monkeypatch):
    A, a = _asistente(monkeypatch, None)
    assert a._intentar_contenido(PARTIDO, A.TIE.Cronometro()) is None
    A, a = _asistente(monkeypatch, (BUENA, "movistarplus.es", "x"), resultado="BLOQUEADO: no")
    assert a._intentar_contenido(PARTIDO, A.TIE.Cronometro()) is None
    A, a = _asistente(monkeypatch, (BUENA, "movistarplus.es", "x"))
    assert a._intentar_contenido("¿A qué hora es el partido del Barça?", A.TIE.Cronometro()) is None
    assert a._intentar_contenido("ponme Stranger Things", A.TIE.Cronometro()) is None
