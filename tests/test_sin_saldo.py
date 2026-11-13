# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Un 402 de Gemini («Your prepayment credits are depleted»): la clave de pago se ha quedado sin saldo prepago. Tiene su propia clase, Lina lo dice tal cual
y la clave de pago no se vuelve a probar en unas horas o hasta que la cambies. Sin red: el estado va a una carpeta temporal."""
import sys
import time
from unittest.mock import MagicMock

import pytest

from lina.nucleo import ia as IA
from lina.nucleo import presupuesto as PRES
from lina.nucleo import proveedores as P
from lina.nucleo import rutas as RUT

SALDO = P.ErrorIA("saldo", 402, "error 402 RESOURCE_EXHAUSTED | Your prepayment credits are depleted. Please go to AI Studio…")


@pytest.fixture
def claves(monkeypatch, tmp_path):
    monkeypatch.setattr(RUT, "ESTADO", tmp_path)
    monkeypatch.setattr(PRES, "_claves", {"gratis": "GRATIS", "pago": "PAGO"})
    monkeypatch.setattr(PRES, "_cargar", lambda: PRES._nuevo(time.strftime("%Y-%m")))
    return tmp_path


def test_el_402_tiene_su_clase():
    assert P.tipo_de_estado(402) == "saldo" and IA.clase_de_fallo(SALDO) == "sin_saldo"


def test_sin_saldo_la_de_pago_no_se_prueba_en_unas_horas(claves):
    assert PRES.pago_disponible() and PRES.claves_para("rapido") == ["GRATIS", "PAGO"]
    PRES.marcar_sin_saldo("PAGO", ahora=time.time())
    assert not PRES.pago_disponible() and PRES.claves_para("rapido") == ["GRATIS"] and PRES.clave_de_pago_con_saldo() == ""
    assert PRES.sin_saldo(ahora=time.time() + (PRES.HORAS_SIN_SALDO - 1) * 3600)
    assert PRES.sin_saldo(ahora=time.time() + PRES.HORAS_SIN_SALDO * 3600 + 1) is None          # pasadas unas horas, se vuelve a probar


def test_cambiar_la_clave_de_pago_lo_levanta(claves, monkeypatch):
    PRES.marcar_sin_saldo("PAGO")
    monkeypatch.setattr(PRES, "_claves", {"gratis": "GRATIS", "pago": "OTRA"})
    assert PRES.sin_saldo() is None and PRES.pago_disponible()


def test_preguntar_ia_con_un_402_marca_la_de_pago(claves, monkeypatch):
    monkeypatch.setattr(IA, "_pausa_modelo", {})
    monkeypatch.setattr(IA, "_turno_medido", lambda *a, **k: SALDO)
    IA.empezar_peticion()
    assert IA.preguntar_ia(MagicMock(), "PAGO", "gemini-flash-lite-latest", "hola", None) is None
    assert PRES.sin_saldo() and IA.fallos_de_la_peticion() == [("sin_saldo", "pago")]


def test_la_busqueda_de_google_con_un_402_tambien(claves):
    from lina.nucleo import busqueda as BUS
    r = MagicMock(ok=False, status_code=402)
    r.json.return_value = {"error": {"code": 402, "message": "Your prepayment credits are depleted."}}
    assert BUS.resultados_google("x", post=MagicMock(return_value=r))[0] == []
    assert PRES.sin_saldo()


def test_lina_lo_dice_tal_cual(claves, monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    monkeypatch.setattr(A, "fallos_de_la_peticion", lambda: [("cuota", "gratis"), ("sin_saldo", "pago")])
    assert a._por_que_no_responde_gemini() == "La clave de pago se ha quedado sin saldo prepago; recárgalo en AI Studio."
    PRES.marcar_sin_saldo("PAGO")                                  # ya marcada: aunque esta vez no se probara la de pago, se dice igual
    monkeypatch.setattr(A, "fallos_de_la_peticion", lambda: [("saturado", "gratis")])
    assert a._por_que_no_responde_gemini() == "La clave de pago se ha quedado sin saldo prepago; recárgalo en AI Studio."
