# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""La búsqueda en internet es un ajuste (ia.busqueda: tavily · google · ninguna) y no una constante: se relee en cada petición, con «ninguna» no se busca
aunque haya clave, y «ponme…» también lo respeta. Con el HOME aislado del conftest; ni red ni llavero de verdad."""
import sys
from unittest.mock import MagicMock

import pytest
import requests

from lina.nucleo import ajustes as AJ
from lina.nucleo import claves as CL
from lina.nucleo import ia as IA


class AjFalso:
    def __init__(self, busqueda):
        self.busqueda = busqueda

    def get(self, seccion, clave):
        return self.busqueda if (seccion, clave) == ("ia", "busqueda") else AJ.ESQUEMA[seccion][clave][0]


@pytest.fixture
def con(monkeypatch):
    """con(busqueda, clave): fija el ajuste y la clave de Tavily; cualquier petición de red hace fallar la prueba."""
    def poner(busqueda, clave="tvly-de-prueba"):
        monkeypatch.setattr(AJ, "actuales", lambda log=print: AjFalso(busqueda))
        monkeypatch.setattr(CL, "obtener", lambda nombre: clave if nombre == "tavily" else None)
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=AssertionError("no debía ir a la red")))
    monkeypatch.setattr(IA, "_pausa_tavily", [0.0])
    monkeypatch.setattr(IA, "hay_reserva", lambda: False)           # la búsqueda de reserva tiene sus propias pruebas
    return poner


def test_de_fabrica_auto_y_lo_mal_escrito_vuelve_a_fabrica(tmp_path):
    assert AJ.ESQUEMA["ia"]["busqueda"][0] == "auto"
    assert AJ.ESQUEMA["ia"]["busqueda_reserva"][0] is False                  # DuckDuckGo: 1 de 30 a 4 s y 0 de 30 a 30 s; solo si lo pides
    ruta = tmp_path / "c.toml"
    ruta.write_text('[ia]\nbusqueda = "bing"\n', encoding="utf-8")
    a = AJ.Ajustes(ruta, log=lambda m: None)
    assert a.get("ia", "busqueda") == "auto" and len(a.avisos) == 1


@pytest.mark.parametrize("escrito", ["tavily", "ninguna", "google"])
def test_quien_ya_lo_tiene_escrito_lo_conserva(tmp_path, escrito):
    ruta = tmp_path / "c.toml"
    ruta.write_text(f'[ia]\nbusqueda = "{escrito}"\nbusqueda_reserva = true\n', encoding="utf-8")
    a = AJ.Ajustes(ruta, log=lambda m: None)
    assert a.get("ia", "busqueda") == escrito and a.get("ia", "busqueda_reserva") is True


@pytest.mark.parametrize("busqueda,clave,hay", [("tavily", "tvly-x", True), ("tavily", None, False), ("ninguna", "tvly-x", False), ("google", "tvly-x", False),
                                               ("auto", "tvly-x", True), ("auto", None, False)])
def test_hay_busqueda_tavily(con, busqueda, clave, hay):
    con(busqueda, clave)
    assert IA.modo_busqueda() == busqueda
    assert IA.hay_busqueda_tavily() is hay


@pytest.mark.parametrize("busqueda, clave, permitida, hay", [("tavily", None, True, True), ("tavily", None, False, False), ("tavily", "tvly-x", True, False),
                                                             ("ninguna", None, True, False), ("google", None, True, False)])
def test_reserva_sin_clave_respeta_el_permiso(con, monkeypatch, busqueda, clave, permitida, hay):
    con(busqueda, clave)
    monkeypatch.setattr(IA, "hay_reserva", lambda: permitida)
    assert IA.reserva_sin_clave() is hay


@pytest.mark.parametrize("busqueda,clave", [("ninguna", "tvly-x"), ("tavily", None), ("google", "tvly-x")])
def test_sin_busqueda_tavily_no_se_busca(con, busqueda, clave):
    con(busqueda, clave)
    assert IA.resultados_tavily("partido de hoy") == "La búsqueda web no está configurada."
    assert "no está configurada" in IA.buscar_tavily("partido de hoy")


def test_con_tavily_y_clave_si_se_busca(con, monkeypatch):
    con("tavily")
    respuesta = MagicMock(ok=True)
    respuesta.json.return_value = {"results": [{"title": "Ficha", "url": "https://ejemplo.test/ficha", "content": "algo"}]}
    monkeypatch.setattr(requests, "post", MagicMock(return_value=respuesta))
    assert IA.resultados_tavily("partido de hoy")[0]["url"] == "https://ejemplo.test/ficha"


def test_ponme_sin_busqueda_se_lo_deja_a_la_ia_sin_gastar_la_consulta(con, monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    con("ninguna")
    entender = MagicMock(side_effect=AssertionError("no debía consultar a la IA"))
    monkeypatch.setattr(A.CONT, "entender", entender)
    a = A.Asistente.__new__(A.Asistente)
    a.clave, a.ejecutor = "CLAVE", MagicMock(pendientes=[])
    a._con_claves = lambda tipo, f, *x: f(*x)
    assert a._intentar_contenido("ponme el partido del Barça", MagicMock()) is None
    entender.assert_not_called()
