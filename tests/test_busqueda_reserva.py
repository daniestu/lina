# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""N1: búsqueda de reserva sin clave (DuckDuckGo, versión ligera) cuando Tavily no responde o agota su cupo, y sin volver a llamar a Tavily hasta mañana
tras un 432/433 (el registro real: 12 llamadas fallidas en un segundo). Sin red: requests.post simulado según la dirección."""
from unittest.mock import MagicMock

import pytest
import requests

from lina.nucleo import ajustes as AJ
from lina.nucleo import aviso_busqueda as AVB
from lina.nucleo import claves as CL
from lina.nucleo import ia as IA

PAGINA = """<table>
<tr><td>1.&nbsp;</td><td><a rel="nofollow" href="https://www.netflix.com/es/title/81439208" class='result-link'>Ve Aquí no hay quien viva | Netflix</a></td></tr>
<tr><td>&nbsp;</td><td class='result-snippet'>
  Vecinos de la calle &lt;b&gt;Desengaño&lt;/b&gt; 21.
</td></tr>
<tr><td>2.&nbsp;</td><td><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.rtve.es%2Fplay%2Fvideos%2Faqui%2F&amp;rut=x" class='result-link'>RTVE Play</a></td></tr>
<tr><td>&nbsp;</td><td class='result-snippet'>Otro resumen</td></tr>
<tr><td>3.&nbsp;</td><td><a rel="nofollow" href="https://duckduckgo.com/y.js?ad=1" class='result-link'>Anuncio</a></td></tr>
<tr><td>&nbsp;</td><td class='result-snippet'>anuncio</td></tr>
</table>"""


class AjFalso:
    def __init__(self, reserva=True):
        self.reserva = reserva

    def get(self, seccion, clave):
        if (seccion, clave) == ("ia", "busqueda"):
            return "tavily"
        if (seccion, clave) == ("ia", "busqueda_reserva"):
            return self.reserva
        return AJ.ESQUEMA[seccion][clave][0]


@pytest.fixture
def red(monkeypatch, tmp_path):
    """red(tavily=código o excepción, ddg=página o excepción). Devuelve la lista de direcciones pedidas."""
    pedidas = []
    monkeypatch.setattr(IA, "_pausa_tavily", [0.0])
    monkeypatch.setattr(IA, "_pausa_reserva", [0.0])
    monkeypatch.setattr(CL, "obtener", lambda nombre, *a: "tvly-de-prueba" if nombre == "tavily" else None)
    monkeypatch.setattr(AVB.RUT, "ESTADO", tmp_path)
    AVB.descartar()

    def poner(tavily=432, ddg=PAGINA, reserva=True):
        monkeypatch.setattr(AJ, "actuales", lambda log=print: AjFalso(reserva))

        def post(url, **k):
            pedidas.append((url, k))
            if "tavily" in url:
                if isinstance(tavily, Exception):
                    raise tavily
                return MagicMock(ok=tavily == 200, status_code=tavily, text="limit",
                                 json=lambda: {"results": [{"title": "T", "url": "https://t.es/x", "content": "c"}]})
            if isinstance(ddg, Exception):
                raise ddg
            if isinstance(ddg, tuple):                                       # (código, página)
                return MagicMock(ok=200 <= ddg[0] < 300, status_code=ddg[0], text=ddg[1])
            return MagicMock(ok=True, status_code=200, text=ddg)
        monkeypatch.setattr(requests, "post", post)
        return pedidas
    yield poner
    AVB.descartar()


# ---------------------------------------------------------------- leer la página de DuckDuckGo
def test_lee_titulos_enlaces_y_resumenes_y_deshace_las_redirecciones():
    r = IA.leer_resultados_reserva(PAGINA)
    assert [x["url"] for x in r] == ["https://www.netflix.com/es/title/81439208", "https://www.rtve.es/play/videos/aqui/"]
    assert r[0]["title"] == "Ve Aquí no hay quien viva | Netflix" and r[0]["content"] == "Vecinos de la calle <b>Desengaño</b> 21."
    assert len(IA.leer_resultados_reserva(PAGINA, maximo=1)) == 1 and IA.leer_resultados_reserva("<html>nada</html>") == []


def test_con_dominio_busca_solo_en_esa_web(red):
    pedidas = red()
    IA.resultados_reserva("aqui no hay quien viva", "netflix.com")
    assert pedidas[-1][0] == IA.RESERVA and pedidas[-1][1]["data"]["q"] == "site:netflix.com aqui no hay quien viva"


def test_si_la_reserva_falla_lo_dice(red):
    red(ddg=requests.ConnectionError("sin red"))
    assert IA.resultados_reserva("x") == "La búsqueda web no está disponible ahora mismo."


# ---------------------------------------------------------------- cuándo se usa
def test_cupo_agotado_usa_la_reserva_y_no_vuelve_a_llamar_a_tavily_hasta_manana(red):
    pedidas = red(tavily=432)
    r = IA.resultados_tavily("aqui no hay quien viva", "netflix.com")
    assert isinstance(r, list) and r[0]["url"].endswith("/title/81439208")
    assert AVB.LIMITE_PLAN in AVB._pendientes                                  # el aviso del cupo sigue saliendo (una vez al mes)
    assert IA._pausa_tavily[0] > IA.time.time()
    pedidas.clear()
    for _ in range(12):                                                        # el registro real: 12 búsquedas seguidas
        IA.resultados_tavily("aqui no hay quien viva")
    assert pedidas and all("tavily" not in url for url, _ in pedidas)


def test_tavily_sin_conexion_tambien_pasa_a_la_reserva_sin_pausa(red):
    red(tavily=requests.ConnectionError("caído"))
    assert isinstance(IA.resultados_tavily("x"), list) and IA._pausa_tavily[0] == 0.0


def test_tavily_bien_no_usa_la_reserva(red):
    pedidas = red(tavily=200)
    assert IA.resultados_tavily("x")[0]["url"] == "https://t.es/x" and all("duckduckgo" not in url for url, _ in pedidas)


def test_con_la_reserva_apagada_como_antes_pero_sin_insistir(red):
    pedidas = red(tavily=432, reserva=False)
    assert IA.resultados_tavily("x") == AVB.PARA_LA_IA_LIMITE
    pedidas.clear()
    assert IA.resultados_tavily("x") == AVB.PARA_LA_IA_LIMITE and pedidas == []   # en pausa: ni Tavily ni reserva


def test_si_la_reserva_no_encuentra_nada_queda_el_mensaje_de_siempre(red):
    red(tavily=500, ddg="<html>sin resultados</html>")
    assert IA.resultados_tavily("x") == "La búsqueda web no está disponible ahora mismo."


# ---------------------------------------------------------------- el aviso del cupo con la reserva
def test_con_reserva_el_cupo_no_se_dice_en_voz_alta_y_la_notificacion_lo_cuenta(tmp_path, monkeypatch):
    monkeypatch.setattr(AVB.RUT, "ESTADO", tmp_path)
    AVB.apuntar(AVB.LIMITE_PLAN)
    [(hablado, titulo, texto)] = AVB.pendientes("tavily", reserva=True)
    assert hablado == "" and "DuckDuckGo" in texto
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    [(hablado, _, _)] = AVB.pendientes("tavily", reserva=True)
    assert hablado                                                              # «falta la búsqueda» se sigue diciendo


def test_si_duckduckgo_nos_toma_por_un_robot_no_insiste_en_media_hora(red):
    pedidas = red(tavily=500, ddg=(202, "<html>Unfortunately, bots use DuckDuckGo too. anomaly detected</html>"))
    assert IA.resultados_tavily("x") == "La búsqueda web no está disponible ahora mismo."
    assert IA._pausa_reserva[0] > IA.time.time()
    pedidas.clear()
    IA.resultados_reserva("y")
    assert pedidas == []                                                        # en pausa: ni se le pregunta

