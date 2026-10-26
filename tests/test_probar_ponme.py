# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-ponme`: sus jueces y que pasa las peticiones sin abrir nada. Sin IA ni red (todo simulado)."""
import threading
from unittest.mock import MagicMock

from lina.nucleo import probar_ponme as P


def test_jueces_de_eventos():
    j = P.juez_evento("barcelona")
    assert j([], ["Hoy no veo FC Barcelona en ninguna plataforma"])[0] == "bien"
    assert j([], ["Abierto."])[0] == "mal"
    assert j(["https://www.movistarplus.es/"], [])[0] == "mal"
    assert j(["https://www.movistarplus.es/programacion-tv/daznli/2026-10-25"], [])[0] == "mal"
    assert j(["https://www.google.com/search?q=barcelona"], [])[0] == "mal"                    # no es una plataforma oficial
    assert j(["https://www.movistarplus.es/deportes/x/fc-barcelona-sevilla/ficha?id=1"], [])[0] == "revisar"


def test_jueces_de_series_peliculas_y_videos():
    c = P.juez_capitulo("stranger things")
    assert c(["https://www.netflix.com/watch/80144892"], [])[0] == "revisar"
    assert c(["https://www.netflix.com/es/title/80057281"], [])[0] == "a medias"
    assert c(["https://www.netflix.com/tudum/stranger-things"], [])[0] == "mal"
    t = P.juez_titulo("oppenheimer")
    assert t(["https://www.primevideo.com/-/es/detail/Oppenheimer/0TQ"], [])[0] == "bien"
    assert t(["https://www.justwatch.com/es/pelicula/oppenheimer"], [])[0] == "mal"
    v = P.juez_video("ibai")
    assert v(["https://www.youtube.com/watch?v=x"], [])[0] == "revisar" and v(["https://www.youtube.com/@ibai"], [])[0] == "a medias"


def test_pasar_no_abre_nada_y_corta_si_tarda():
    abiertas = []
    A = MagicMock()
    A._abortar = threading.Event()
    A.Cancelado = type("Cancelado", (Exception,), {})
    a = MagicMock()
    a._atender = lambda frase, inicio, origen=None: (abiertas.append("https://www.rtve.es/play/videos/telediario-1"), a.decir("Te abro el Telediario."))
    vistas, dicho, seg = P.pasar("Ponme el Telediario.", A, a, abiertas, tope=5)
    assert vistas == ["https://www.rtve.es/play/videos/telediario-1"] and dicho == ["Te abro el Telediario."] and seg < 5
    assert not A._abortar.is_set()


def test_ayuda(capsys):
    assert P.principal(["--help"]) == 0 and "probar-ponme" in capsys.readouterr().out
