# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""E2: el cupo mensual de Tavily. Caso real (2026-11-20): un 432 dejó Tavily agotado hasta el 1 de diciembre y las medidas habían gastado 228 búsquedas
en una semana. Contador y topes (medidas 100, uso real ia.tavily_mes con aviso al 80 %), pausa hasta el día 1, ninguna llamada dentro de una medida
salvo `probar-busqueda tavily`, el aviso que no dice «se han acabado las búsquedas» si las wikis siguen y la línea de lina doctor. Sin red: Tavily simulado."""
import datetime
import json
from unittest.mock import MagicMock

import pytest
import requests

from lina.nucleo import aviso_busqueda as AVB
from lina.nucleo import busqueda as BUS
from lina.nucleo import claves as CL
from lina.nucleo import cupo_tavily as CUP
from lina.nucleo import ia as IA
from lina.nucleo import rutas as RUT

HOY = datetime.date(2026, 11, 20)


@pytest.fixture
def tavily(monkeypatch, tmp_path):
    """Tavily simulado: `tavily.respuesta = (ok, código)`; `tavily.post` cuenta las llamadas. Nada sale a la red."""
    monkeypatch.setattr(RUT, "ESTADO", tmp_path / "estado")
    monkeypatch.setattr(CL, "obtener", lambda n: "tvly-de-prueba" if n == "tavily" else "")
    monkeypatch.setattr(IA, "_pausa_tavily", [0.0])
    monkeypatch.setattr(CUP, "tope_real", lambda: 10)
    monkeypatch.setattr(requests, "get", MagicMock(side_effect=AssertionError("no debía ir a la red")))
    AVB.descartar()
    estado = MagicMock(respuesta=(True, 200))

    def post(url, **k):
        ok, codigo = estado.respuesta
        r = MagicMock(ok=ok, status_code=codigo, text="limit")
        r.json.return_value = {"results": [{"title": "Ficha", "url": "https://ejemplo.es/x", "content": "dato"}]}
        return r
    estado.post = MagicMock(side_effect=post)
    monkeypatch.setattr(requests, "post", estado.post)
    return estado


def _buscar():
    return IA.resultados_tavily("partido de hoy", reserva=False, comprobar_modo=False)


# ---------------------------------------------------------------- el contador y los topes
def test_cuenta_uso_real_y_medidas_por_separado_y_solo_numeros(tavily):
    _buscar()
    with IA.solo_medida(), IA.tavily_en_medida():
        _buscar()
    r = CUP.resumen()
    assert (r["real"], r["medida"]) == (1, 1)
    guardado = CUP.ARCHIVO.read_text(encoding="utf-8")
    assert "partido" not in guardado and "tvly" not in guardado and set(json.loads(guardado)) == {"mes", "real", "medida", "agotado_hasta"}


def test_dentro_de_una_medida_no_se_llama_a_tavily(tavily):
    with IA.solo_medida():
        assert _buscar() == "La búsqueda web no está configurada."
    tavily.post.assert_not_called()
    assert CUP.resumen()["medida"] == 0


def test_la_previa_de_ponme_no_busca_en_tavily_dentro_de_una_medida(tavily):
    from lina.nucleo import contenido as CONT
    consultar = MagicMock(return_value=None)
    with IA.solo_medida():
        CONT.entender("clave", "Ponme el partido de esta noche", consultar=consultar)
    tavily.post.assert_not_called()
    assert "(sin resultados)" in consultar.call_args[0][3]          # la IA sigue entendiendo la frase, sin resultados de Tavily
    CONT.entender("clave", "Ponme el partido de esta noche", consultar=consultar)
    tavily.post.assert_called_once()                               # en uso real, como siempre


def test_el_tope_de_medidas_es_100(tavily, monkeypatch):
    monkeypatch.setattr(CUP, "TOPE_MEDIDAS", 2)
    with IA.solo_medida(), IA.tavily_en_medida():
        for _ in range(3):
            _buscar()
    assert tavily.post.call_count == 2 and CUP.restante_medidas() == 0
    _buscar()                                                      # el uso real no se ve afectado por el tope de las medidas
    assert tavily.post.call_count == 3


def test_el_tope_de_uso_real_avisa_al_80_y_para_al_llegar(tavily):
    for _ in range(8):
        _buscar()
    assert AVB.AVISO_80 in AVB._pendientes
    [(hablado, titulo, texto)] = AVB.pendientes("auto")
    assert hablado == "" and "8 de 10" in texto
    _buscar()
    _buscar()
    assert tavily.post.call_count == 10
    assert _buscar() == AVB.PARA_LA_IA_LIMITE and tavily.post.call_count == 10
    assert AVB.TOPE_PROPIO in AVB._pendientes


def test_sin_tope_de_uso_real(tavily, monkeypatch):
    monkeypatch.setattr(CUP, "tope_real", lambda: 0)
    for _ in range(12):
        _buscar()
    assert tavily.post.call_count == 12 and AVB.AVISO_80 not in AVB._pendientes


# ---------------------------------------------------------------- el 432: hasta el día 1
def test_el_432_pausa_hasta_el_dia_1_aunque_cambie_el_proceso(tavily):
    tavily.respuesta = (False, 432)
    assert _buscar() == AVB.PARA_LA_IA_LIMITE
    assert CUP.agotado_hasta() == CUP.primer_dia_del_mes_siguiente()
    IA._pausa_tavily[0] = 0.0                                       # otro proceso (otra Lina, probar-…): lo que vale está en el archivo
    tavily.respuesta = (True, 200)
    assert _buscar() == AVB.PARA_LA_IA_LIMITE and tavily.post.call_count == 1


def test_guardar_la_clave_otra_vez_quita_la_pausa(tavily):
    tavily.respuesta = (False, 432)
    _buscar()
    CL._olvidar_avisos("tavily")
    IA._pausa_tavily[0] = 0.0
    tavily.respuesta = (True, 200)
    assert isinstance(_buscar(), list) and tavily.post.call_count == 2


@pytest.mark.parametrize("hoy, dia_1", [(datetime.date(2026, 11, 20), datetime.date(2026, 12, 1)), (datetime.date(2026, 12, 31), datetime.date(2027, 1, 1))])
def test_el_dia_1_es_el_del_mes_siguiente(tavily, hoy, dia_1):
    assert CUP.agotado(hoy) == dia_1


def test_el_mes_nuevo_empieza_de_cero_y_sin_pausa(tavily):
    CUP.apuntar(False, hoy=HOY)
    CUP.agotado(hoy=HOY)
    assert CUP.motivo_para_no_llamar(False, hoy=HOY) == "agotado"
    diciembre = datetime.date(2026, 12, 1)
    assert CUP.motivo_para_no_llamar(False, hoy=diciembre) == "" and CUP.resumen(hoy=diciembre)["real"] == 0


def test_la_escalera_sigue_con_las_wikis_sin_errores(tavily, monkeypatch):
    monkeypatch.setattr(IA, "modo_busqueda", lambda: "auto")
    monkeypatch.setattr(IA, "hay_reserva", lambda: False)
    monkeypatch.setattr(BUS, "resultados_google", lambda *a, **k: ([], "sin clave de pago"))
    monkeypatch.setattr(BUS, "resultados_wiki", lambda *a, **k: ([{"title": "Wiki", "url": "https://es.wikipedia.org/wiki/X", "content": "x"}], ""))
    BUS._cache.clear()
    tavily.respuesta = (False, 432)
    res = BUS.buscar("quién ganó el mundial de 2010")
    assert res.escalon == "wiki" and res.resultados and any("Tavily" in m for m in res.motivos)


def test_en_una_medida_la_escalera_lo_trata_como_sin_tavily(tavily, monkeypatch):
    monkeypatch.setattr(BUS, "resultados_google", lambda *a, **k: ([], ""))
    monkeypatch.setattr(BUS, "resultados_wiki", lambda *a, **k: ([], ""))
    BUS._cache.clear()
    with IA.solo_medida():
        res = BUS.buscar("algo de hoy", modo="auto")
    assert res.sin_tavily and not tavily.post.called


# ---------------------------------------------------------------- el aviso
def test_con_las_wikis_no_dice_que_se_han_acabado_las_busquedas(tavily):
    AVB.apuntar(AVB.LIMITE_PLAN)
    [(hablado, _, _)] = AVB.pendientes("auto")
    assert "Wikipedia" in hablado and "día 1" in hablado and "se han acabado" not in hablado.lower() and "tavily" not in hablado.lower()
    AVB.olvidar()
    AVB.apuntar(AVB.LIMITE_PLAN)
    [(hablado, _, _)] = AVB.pendientes("tavily")
    assert "respondo con lo que sé" in hablado and "Wikipedia" not in hablado


# ---------------------------------------------------------------- lina doctor
def _filas_tavily():
    """Las filas «Tavily» del informe, con las sondas de una prueba de doctor y el cupo de verdad (el archivo de esta prueba)."""
    from test_doctor import Todo
    from lina.nucleo import doctor as D

    class ConTavily(Todo):
        def busqueda(self):
            return "auto", "el llavero", None

        def tavily(self):
            return CUP.resumen()
    return [f for f in D.comprobar(ConTavily()) if f[1] == "Tavily"]


def test_doctor_cuenta_el_cupo_sin_llamar_a_tavily(tavily):
    from lina.nucleo import doctor as D
    CUP.apuntar(False)
    [fila] = _filas_tavily()
    assert fila[0] == D.OK and "1 búsquedas de 10" in fila[2] and "0 de medidas, de 100" in fila[2]
    tavily.post.assert_not_called()


def test_doctor_dice_agotado_hasta_el_dia_1(tavily):
    from lina.nucleo import doctor as D
    CUP.agotado()
    [fila] = _filas_tavily()
    assert fila[0] == D.AVISO and "agotado hasta el día 1" in fila[2] and "Wikipedia" in fila[2] and "lina clave tavily" in fila[3]


# ---------------------------------------------------------------- probar-busqueda tavily
def test_probar_busqueda_tavily_no_empieza_sin_cupo_de_medidas(tavily, monkeypatch):
    from lina.nucleo import probar_busqueda as PB
    monkeypatch.setattr(CUP, "TOPE_MEDIDAS", 0)
    salida = []
    assert PB.principal(["tavily"], salida.append, preparar=MagicMock(side_effect=AssertionError)) == 5
    assert "tope" in salida[0]


def test_probar_busqueda_tavily_dice_antes_cuanto_puede_gastar(tavily, monkeypatch):
    from lina.nucleo import probar_busqueda as PB
    salida = []
    PB.principal(["tavily", "3", "--estimar"], salida.append, preparar=MagicMock(side_effect=AssertionError))
    assert salida[0].startswith("Gastará como mucho 6 búsquedas de Tavily; a las medidas les quedan 100 de 100")
