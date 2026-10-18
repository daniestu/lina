# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Presupuesto de Gemini: qué clave toca, cuánto se lleva gastado, avisos y subida del tope."""
import pytest

from lina.nucleo import presupuesto as PRE

PRECIOS = {"modelo-a": [(None, 1.0, 10.0, 0.1)], "modelo-b": [(None, 2.0, 20.0, 0.2), ("2999-01-01", 4.0, 40.0, 0.4)]}


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(PRE, "ARCHIVO_GASTO", tmp_path / "gasto.json")
    monkeypatch.setattr(PRE, "configuracion", lambda: {"tope_eur": 10.0, "eur_por_usd": 1.0, "avisos": (50, 80, 100), "precios": PRECIOS})
    monkeypatch.setattr(PRE, "_avisos_pendientes", [])
    PRE.configurar_claves("", "")
    yield
    PRE.configurar_claves("", "")


def _uso(prompt=0, salida=0, pensado=0):
    return {"promptTokenCount": prompt, "candidatesTokenCount": salida, "thoughtsTokenCount": pensado}


def test_con_una_sola_clave_no_hay_pago():
    PRE.configurar_claves("gratis-1", "")
    assert PRE.una_sola_clave() and not PRE.hay_clave_de_pago() and not PRE.pago_disponible()
    assert PRE.claves_para("profundo") == ["gratis-1"]


def test_la_misma_clave_dos_veces_cuenta_como_una():
    PRE.configurar_claves("misma", "misma")
    assert PRE.una_sola_clave()


def test_el_orden_de_las_claves_depende_del_modo():
    PRE.configurar_claves("gratis-1", "pago-1")
    assert PRE.claves_para("profundo") == ["pago-1", "gratis-1"]
    assert PRE.claves_para("rapido") == ["gratis-1", "pago-1"]
    assert PRE.nombre_de("pago-1") == "pago" and PRE.nombre_de("gratis-1") == "gratis"


def test_el_precio_usa_el_modelo_real_y_la_tarifa_vigente():
    assert PRE.precio("modelo-a")[:3] == (1.0, 10.0, 0.1)
    assert PRE.precio("modelo-b")[:3] == (2.0, 20.0, 0.2)                 # la tarifa de 2999 todavía no vale
    assert PRE.precio("modelo-a-v2")[3] is False                            # un nombre que empieza por uno conocido
    assert PRE.precio("desconocido", "tampoco")[:3] == (2.0, 20.0, 0.2) and PRE.precio("desconocido")[3] is True   # el más caro de cada columna


def test_coste_en_dolares():
    # 1 000 000 de tokens de entrada a 1 $ + 100 000 de salida a 10 $ = 2 $
    assert abs(PRE.coste_usd("modelo-a", None, 1_000_000, 100_000, 0) - 2.0) < 1e-9
    assert abs(PRE.coste_usd("modelo-a", None, 1_000_000, 0, 0, cacheados=1_000_000) - 0.1) < 1e-9


def test_la_clave_gratis_solo_cuenta_llamadas():
    PRE.configurar_claves("gratis-1", "pago-1")
    PRE.registrar("gratis-1", "modelo-a", _uso(1000, 100))
    e = PRE.estado()
    assert e["llamadas_gratis"] == 1 and e["llamadas_pago"] == 0 and e["gasto_eur"] == 0


def test_la_clave_de_pago_acumula_dinero_y_avisa_al_cruzar_umbrales():
    PRE.configurar_claves("gratis-1", "pago-1")
    PRE.registrar("pago-1", "modelo-a", _uso(0, 500_000))                   # 5 $ → 50 %
    assert any("50 %" in a for a in PRE.avisos_pendientes())
    assert PRE.avisos_pendientes() == []                                     # los avisos se dicen una sola vez
    PRE.registrar("pago-1", "modelo-a", _uso(0, 400_000))                   # 9 $ → 90 %
    assert any("80 %" in a for a in PRE.avisos_pendientes())
    assert PRE.pago_disponible()


def test_al_llegar_al_tope_la_clave_de_pago_deja_de_usarse():
    PRE.configurar_claves("gratis-1", "pago-1")
    PRE.registrar("pago-1", "modelo-a", _uso(0, 1_000_000))                 # 10 $ = el tope
    assert any("tope de gasto" in a for a in PRE.avisos_pendientes())
    assert not PRE.pago_disponible()
    assert PRE.claves_para("profundo") == ["gratis-1"]
    assert "tope" in PRE.resumen()


def test_un_dato_raro_de_google_no_rompe_nada():
    PRE.configurar_claves("gratis-1", "pago-1")
    PRE.registrar("pago-1", "modelo-a", {"promptTokenCount": "mucho", "candidatesTokenCount": -5})
    PRE.registrar("pago-1", "modelo-a", None)
    assert PRE.estado()["gasto_eur"] == 0


def test_resumen_sin_clave_de_pago():
    PRE.configurar_claves("gratis-1", "")
    assert "No hay clave de pago" in PRE.resumen()


def test_subir_el_tope():
    assert "No hay clave de pago" in PRE.subir_tope(15)
    PRE.configurar_claves("gratis-1", "pago-1")
    assert "solo lo hago si pulsas el atajo" in PRE.subir_tope(15, voz_libre=True)     # con «Oye Lina» no se puede subir
    assert "entre 1 y" in PRE.subir_tope(5000)
    assert "hasta 15 €" in PRE.subir_tope(15)
    assert PRE.estado()["tope_eur"] == 15.0
    assert "Vale" in PRE.subir_tope(5, voz_libre=True)                                  # bajarlo sí se deja por voz


@pytest.mark.parametrize("frase,euros", [
    ("sigue con el de pago hasta 15 euros", 15.0),
    ("sube el tope de gasto a 20 €", 20.0),
    ("aumenta el gasto a quince euros", 15.0),
    ("pon un límite de 30 euros a mi compra", None),         # no habla del gasto de la clave de pago
    ("abre firefox", None),
    ("sube el tope", None),                                    # sin cantidad
])
def test_entender_el_tope_dicho_por_voz(frase, euros):
    assert PRE.entender_tope(frase) == euros
