# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A3: los modelos de Gemini van fijados, no con los alias «-latest» que Google cambia cuando quiere. Si Google retira uno (404), esa llamada se repite
una vez con su alias y queda en el log; con un 429 no (el alias no es cupo extra). `lina doctor` mira en la lista de la API que siguen ahí. Sin red ni IA.
"""
from unittest.mock import MagicMock

import pytest

from lina.nucleo import busqueda as BUS
from lina.nucleo import constantes as C
from lina.nucleo import doctor as D
from lina.nucleo import proveedor_gemini as PG

FIJADOS = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]


@pytest.fixture(autouse=True)
def sin_retirados(monkeypatch):
    monkeypatch.setattr(PG, "_retirados", set())
    monkeypatch.setattr(PG, "log", MagicMock())


def _resp(estado, cuerpo=None):
    r = MagicMock(status_code=estado, ok=estado == 200)
    r.json.return_value = cuerpo if cuerpo is not None else (
        {"candidates": [{"content": {"parts": [{"text": "vale"}]}}], "modelVersion": "x"} if estado == 200 else {"error": {"code": estado, "status": "X"}})
    return r


def test_las_listas_de_fabrica_no_usan_alias():
    for lista in (C.MODELOS_GEMINI, C.MODELOS_PROFUNDO, C.MODELOS_CONFIRMACION, [BUS.MODELO_GOOGLE]):
        assert lista and not any(m.endswith("-latest") for m in lista) and set(lista) <= set(PG.ALIAS_DE)
    assert C.MODELOS_GEMINI == FIJADOS and C.MODELOS_PROFUNDO == FIJADOS[::-1]        # el mismo orden que con los alias


def test_un_modelo_que_responde_va_con_su_nombre_fijado():
    post = MagicMock(return_value=_resp(200))
    r = PG.GEMINI.turno("k", FIJADOS[0], "s", [{"rol": "user", "texto": "hola"}], post=post)
    assert r.texto == "vale" and post.call_count == 1 and FIJADOS[0] + ":generateContent" in post.call_args.args[0]


def test_si_google_lo_retira_repite_una_vez_con_el_alias_y_lo_apunta():
    post = MagicMock(side_effect=[_resp(404), _resp(200), _resp(200)])
    r = PG.GEMINI.turno("k", FIJADOS[1], "s", [{"rol": "user", "texto": "hola"}], post=post)
    assert r.texto == "vale" and [c.args[0].split("/")[-1] for c in post.call_args_list] == ["gemini-3.8-flash:generateContent", "gemini-flash-latest:generateContent"]
    assert "404" in PG.log.call_args.args[0] and "gemini-flash-latest" in PG.log.call_args.args[0]
    PG.GEMINI.turno("k", FIJADOS[1], "s", [{"rol": "user", "texto": "otra"}], post=post)       # las siguientes van directas al alias
    assert post.call_args.args[0].endswith("gemini-flash-latest:generateContent") and PG.log.call_count == 1


def test_un_429_no_cambia_al_alias():
    post = MagicMock(return_value=_resp(429))
    r = PG.GEMINI.turno("k", FIJADOS[0], "s", [{"rol": "user", "texto": "hola"}], post=post)
    assert r.tipo == "cuota" and post.call_count == 1 and PG.en_uso(FIJADOS[0]) == FIJADOS[0]


def test_un_404_de_un_modelo_sin_alias_no_se_repite():
    post = MagicMock(return_value=_resp(404))
    r = PG.GEMINI.turno("k", "modelo-de-config-toml", "s", [{"rol": "user", "texto": "hola"}], post=post)
    assert r.tipo == "peticion" and post.call_count == 1


def test_si_el_alias_tambien_da_404_no_hay_bucle():
    post = MagicMock(return_value=_resp(404))
    r = PG.GEMINI.turno("k", FIJADOS[0], "s", [{"rol": "user", "texto": "hola"}], post=post)
    assert r.tipo == "peticion" and post.call_count == 2


def test_la_busqueda_de_google_tambien_cambia_al_alias_con_un_404(monkeypatch):
    post = MagicMock(side_effect=[_resp(404), _resp(200, {"candidates": [{"content": {"parts": [{"text": "x"}]}}]})])
    monkeypatch.setattr(BUS, "_claves_google", lambda: [("k", "gratis")])
    monkeypatch.setattr(BUS, "bloqueo", lambda *a, **k: False)
    monkeypatch.setattr(BUS, "_pausa_google", {})
    monkeypatch.setattr(BUS.PRES, "registrar", lambda *a, **k: None)
    BUS.resultados_google("consulta", post=post)
    assert [c.args[0].split("/")[-1] for c in post.call_args_list] == ["gemini-3.5-flash-lite:generateContent", "gemini-flash-lite-latest:generateContent"]


# ---------------------------------------------------------------- lina doctor
class Sondas(D.Sondas):
    def __init__(self, lista, nombre="gemini", rapido=FIJADOS):
        self._lista, self._ia = lista, MagicMock(nombre=nombre, rapido=list(rapido), profundo=list(rapido), mini=list(rapido))
        self._ia.proveedor.modelos.return_value = (lista, "") if lista is not None else (None, "error 403")

    def ia(self):
        return self._ia


def test_doctor_ve_los_fijados_en_la_lista(monkeypatch):
    monkeypatch.setattr("lina.nucleo.claves.obtener", lambda n, *a, **k: "k")
    assert Sondas(FIJADOS + ["otro"]).modelos_fijados() == (FIJADOS, [])
    assert Sondas(["gemini-3.5-flash-lite"]).modelos_fijados() == (FIJADOS, ["gemini-3.8-flash"])
    assert Sondas(FIJADOS, rapido=["modelo-propio"]).modelos_fijados() is None              # quien fijó el suyo en config.toml
    assert Sondas(FIJADOS, nombre="anthropic").modelos_fijados() is None
    with pytest.raises(RuntimeError):
        Sondas(None).modelos_fijados()
