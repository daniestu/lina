# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El gasto de las medidas con la clave de pago: el máximo estimado antes de empezar, el tope que las para solas, --estimar sin gastar, --solo-gratis, y que
probar-ia empiece cada frase sin modelos en pausa. Caso real: una tarde de medidas agotó el saldo prepago (431 llamadas, unos 0,91 €). Sin IA ni red."""
import json
from unittest.mock import MagicMock

import pytest

from lina.nucleo import banco_ia as B
from lina.nucleo import medida_gasto as MG
from lina.nucleo import presupuesto as PRES
from lina.nucleo import probar_busqueda as PB


def test_el_coste_por_llamada_sale_de_las_llamadas_de_pago(tmp_path):
    archivo = tmp_path / "llamadas_ia.jsonl"
    filas = [{"modelo": "gemini-flash-lite-latest", "pago": True, "res": "ok", "ent": 8000, "sal": 40}] * 25 + [{"modelo": "x", "pago": False, "res": "ok", "ent": 9e9}]
    archivo.write_text("\n".join(json.dumps(f) for f in filas))
    esperado = PRES.coste_usd("gemini-flash-lite-latest", "gemini-flash-lite-latest", 8000, 40, 0) * PRES.EUR_POR_USD
    assert MG.eur_por_llamada(archivo) == pytest.approx(esperado)
    assert MG.eur_por_llamada(tmp_path / "no_hay.jsonl") == MG.EUR_POR_LLAMADA_SIN_DATOS
    assert MG.maximo_estimado(17, 8, eur_llamada=0.002) == pytest.approx(0.272)


def test_el_tope_y_su_opcion():
    assert MG.tope_de(["--tope-eur=1,5"], 0.3) == 1.5 and MG.tope_de(["--tope-eur=2"], 0.3) == 2.0 and MG.tope_de([], 0.3) == 0.3
    gastado = iter([1.00, 1.10, 1.31])
    t = MG.Tope(0.25, gastado=lambda: next(gastado))
    assert not t.superado() and t.superado()


def _banco(monkeypatch, argv, gastos=(0.0,)):
    from lina.nucleo import probar_ponme as PON
    monkeypatch.setattr(PON, "_asistente", lambda: (MagicMock(), MagicMock(), []))
    monkeypatch.setattr(B, "pasar", lambda caso, *a: ([("buscar_web", {})], "Vale."))
    monkeypatch.setattr(MG, "eur_por_llamada", lambda *a, **k: 0.002)
    gastado = iter(list(gastos) + [gastos[-1]] * 100)
    monkeypatch.setattr(MG, "gastado_eur", lambda: next(gastado))
    reinicios, salida = [], []
    r = B.principal(argv, salida.append, reiniciar=lambda: reinicios.append(1))
    return r, "\n".join(salida), reinicios


def test_probar_ia_dice_el_maximo_antes_y_estimar_no_gasta(monkeypatch):
    r, texto, reinicios = _banco(monkeypatch, ["3", "--estimar"])
    assert r == 0 and "Gasto máximo estimado con la clave de pago: 0,05 €" in texto and not reinicios


def test_probar_ia_se_para_al_pasar_el_tope(monkeypatch):
    r, texto, reinicios = _banco(monkeypatch, ["3", "--tope-eur=0,10"], gastos=(1.00, 1.00, 1.05, 1.20))
    assert r == 4 and "Parada: llevo gastados 0,20 €" in texto and len(reinicios) == 2


def test_probar_ia_empieza_cada_frase_sin_pausas(monkeypatch):
    _, _, reinicios = _banco(monkeypatch, ["3"])
    assert len(reinicios) == 3


def test_solo_gratis_quita_la_clave_de_pago(monkeypatch):
    from lina.nucleo import claves as CL
    monkeypatch.setattr(CL, "obtener", lambda nombre, *a, **k: {"gemini": "G", "gemini_pago": "P"}.get(nombre, ""))
    monkeypatch.setattr(PRES, "_claves", {"gratis": "G", "pago": "P"})
    with MG.solo_gratis():
        assert CL.obtener("gemini_pago") == "" and CL.obtener("gemini") == "G" and not PRES.hay_clave_de_pago()
    assert CL.obtener("gemini_pago") == "P" and PRES._claves["pago"] == "P"


def test_probar_ia_solo_gratis_no_estima_gasto(monkeypatch):
    r, texto, _ = _banco(monkeypatch, ["2", "--solo-gratis"])
    assert "Gasto máximo" not in texto and r in (0, 1)


def test_probar_busqueda_pago_dice_el_maximo_y_se_para(monkeypatch):
    class Sin:
        def __init__(self, nivel): pass
        def __enter__(self): return {"gemini": "G", "gemini_pago": "P"}
        def __exit__(self, *a): return False
    monkeypatch.setattr(PB, "usuario_nuevo", Sin)
    monkeypatch.setattr(MG, "eur_por_llamada", lambda *a, **k: 0.002)
    salida = []
    assert PB.principal(["pago", "--estimar"], salida.append) == 0 and "Gasto máximo estimado con la clave de pago: 0,80 €" in salida[0]
    gastado = iter([1.0, 1.0, 2.0] + [2.0] * 50)
    monkeypatch.setattr(MG, "gastado_eur", lambda: next(gastado))
    bien = (["Según la UESP, ectoplasma."], [("buscar_web", {}, "RESULTADOS DE BÚSQUEDA (…):\n\n[1] P (uesp.net) https://x\ny")], ["ok"], 1.0)
    salida.clear()
    r = PB.principal(["pago", "3"], salida.append, preparar=lambda: (MagicMock(), MagicMock(busquedas_hechas=[]), []),
                     pasar_pregunta=lambda *a: bien, dormir=lambda s: None, reiniciar=lambda: None)
    assert r == 4 and any(t.startswith("Parada:") for t in salida)
