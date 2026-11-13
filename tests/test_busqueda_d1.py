# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Bloque D1: la fecha de hoy junto a cualquier búsqueda (también Tavily y wikis), lo «próximo» que ya pasó, el aviso de fallo escrito por el código solo
para datos actuales, y las wikis con tus palabras y un título que nombre lo buscado. Sin red ni llavero."""
import datetime as dt
import sys
import time
from unittest.mock import MagicMock

import pytest

from lina.nucleo import busqueda as BUS
from lina.nucleo import ia as IA

HOY = dt.date(2026, 11, 13)


def respuesta(codigo=200, cuerpo=None):
    r = MagicMock(ok=codigo < 400, status_code=codigo)
    r.json.return_value = cuerpo if cuerpo is not None else {}
    return r


# ---------------------------------------------------------------- 1. la fecha de hoy con cualquier escalón
def test_los_resultados_de_tavily_y_de_las_wikis_llevan_la_fecha_de_hoy():
    """El caso: en tavily, «el próximo eclipse visible en España» salió «12 de agosto de 2026» en noviembre de 2026."""
    texto = IA._resultados_como_texto([{"title": "Eclipse", "url": "https://www.ign.es/eclipse", "content": "El próximo eclipse, el 12 de agosto de 2026."}])
    assert f"HOY ES {time.strftime('%Y-%m-%d')}." in texto and "descarta lo que ya haya pasado" in texto
    wiki = BUS.como_texto(BUS.Resultado(resultados=[{"title": "T", "url": "https://es.wikipedia.org/wiki/T", "dominio": "es.wikipedia.org", "content": "x"}], escalon="wiki"))
    assert "HOY ES " in wiki


@pytest.mark.parametrize("peticion, respuesta_ia, pasada", [
    ("cuándo es el próximo eclipse visible en España", "Según ign.es, será el 12 de agosto de 2026.", dt.date(2026, 8, 12)),
    ("when is the next eclipse", "According to ign.es, on August 12, 2026.", dt.date(2026, 8, 12)),
    ("cuándo es el próximo eclipse visible en España", "Según ign.es, será el 2 de agosto de 2027.", None),             # futura: bien
    ("cuándo sale la próxima actualización de No Man's Sky", "No hay una fecha anunciada; el 2 de noviembre de 2026 salió la 7.13.", None),
    ("cuándo fue el último eclipse", "Fue el 12 de agosto de 2026.", None),                                               # no pedía lo próximo
    ("cuándo es el próximo eclipse", "Será en agosto.", None),                                                            # sin fecha completa
])
def test_lo_proximo_que_ya_ha_pasado(peticion, respuesta_ia, pasada):
    assert BUS.proximo_ya_pasado(peticion, respuesta_ia, HOY) == pasada


# ---------------------------------------------------------------- 2. el aviso de fallo, escrito por el código
NADA_SIN_TAVILY = BUS.Resultado(motivos=["no tienes clave de Tavily", "Wikipedia y las wikis no sirven para datos del momento como precios, noticias, el tiempo o resultados"],
                                sin_tavily=True)
NADA_TAVILY_LIMITE = BUS.Resultado(motivos=["Tavily ha llegado a su límite"])


def test_sin_tavily_termina_con_la_clave_gratuita():
    t = BUS.aviso_de_fallo([NADA_SIN_TAVILY], hay_tavily=False)
    assert t.startswith("No he podido buscarlo: no tienes clave de Tavily y Wikipedia y las wikis no sirven")
    assert t.endswith("Con una clave gratuita de Tavily buscaría noticias, precios y horarios: lina bienvenida.")


def test_con_tavily_que_ha_fallado_termina_con_lina_doctor():
    t = BUS.aviso_de_fallo([NADA_TAVILY_LIMITE], hay_tavily=True)
    assert t == "No he podido buscarlo: Tavily ha llegado a su límite. Mira qué le pasa con lina doctor." and "clave gratuita" not in t


@pytest.fixture
def lina(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[])
    a.busquedas_hechas, a.acciones_turno, a.fuente_turno = [NADA_SIN_TAVILY], [("buscar_web", {}, "NO SE HA PODIDO BUSCAR: …")], None
    monkeypatch.setattr(BUS.CL, "obtener", lambda n, *a, **k: "")
    return a


@pytest.mark.parametrize("dice", ["No tengo forma de saberlo ahora.", "Creo que hoy hará sol en Sevilla, unos 24 grados.", ""])
def test_un_dato_actual_sin_resultados_lo_contesta_el_codigo_diga_lo_que_diga_la_ia(lina, dice):
    lina.pregunta_pura = "qué tiempo hará mañana en Sevilla"
    assert lina._aviso_de_fallo_de_busqueda(dice) == BUS.aviso_de_fallo([NADA_SIN_TAVILY], hay_tavily=False)


def test_si_no_pedia_nada_actual_la_respuesta_de_la_ia_se_queda(lina):
    """La IA buscó algo que sabía de memoria y la búsqueda falló: no se le tapa la respuesta."""
    lina.pregunta_pura = "cuánto mide la torre Eiffel"
    assert lina._aviso_de_fallo_de_busqueda("Mide unos 330 metros (no lo he podido comprobar).") == "Mide unos 330 metros (no lo he podido comprobar)."


def test_si_algo_dio_resultados_no_se_toca(lina):
    lina.pregunta_pura = "qué tiempo hará mañana en Sevilla"
    lina.acciones_turno.append(("leer_web", {"url": "https://aemet.es"}, "CONTENIDO DE LA PÁGINA «x» (aemet.es)."))
    assert lina._aviso_de_fallo_de_busqueda("Según aemet.es, sol.") == "Según aemet.es, sol."


def test_la_fecha_pasada_se_avisa_al_final(lina, monkeypatch):
    lina.pregunta_pura = "cuándo es el próximo eclipse visible en España"
    monkeypatch.setattr(BUS, "proximo_ya_pasado", lambda p, r, hoy=None: dt.date(2026, 8, 12))
    assert lina._avisar_fecha_pasada("Será el 12 de agosto de 2026.").endswith("Ojo: esa fecha ya ha pasado, así que puede que no sea lo próximo.")


# ---------------------------------------------------------------- 3. wikis: tus palabras y un título que lo nombre
def test_la_wikipedia_de_tu_idioma_busca_con_tus_palabras_y_no_con_la_consulta_inglesa():
    pedidas = []

    def get(url, params, headers, timeout):
        pedidas.append((url, params["srsearch"]))
        return respuesta(200, {"query": {"search": [{"title": "Torre Eiffel", "snippet": ""}]}})
    r, _ = BUS.resultados_wiki("Eiffel Tower height", "es", get=get, peticion="cuánto mide la torre Eiffel")
    assert pedidas[0] == ("https://es.wikipedia.org/w/api.php", "mide torre Eiffel") and r[0]["title"] == "Torre Eiffel"


def test_un_titulo_que_no_nombra_lo_buscado_no_vale_aunque_lo_nombre_el_extracto():
    """El caso: «Eiffel Tower height» en la Wikipedia en español dio «Torre de Watkin» y «Torre de Tokio», que mencionan la Eiffel en el extracto."""
    def get(url, params, headers, timeout):
        if "es.wikipedia" in url:
            return respuesta(200, {"query": {"search": [{"title": "Torre de Watkin", "snippet": "más alta que la torre Eiffel"},
                                                        {"title": "Torre de Tokio", "snippet": "inspirada en la torre Eiffel"}]}})
        return respuesta(200, {"query": {"search": [{"title": "Eiffel Tower", "snippet": "330 m"}]}})
    r, _ = BUS.resultados_wiki("Eiffel Tower height", "es", get=get)
    assert [x["title"] for x in r] == ["Eiffel Tower"] and r[0]["dominio"] == "en.wikipedia.org"


def test_la_wiki_del_juego_se_elige_tambien_por_la_peticion():
    assert BUS.wikis_para("creeper", "es", peticion="qué es un creeper en Minecraft")[0]["api"] == "es.minecraft.wiki"
