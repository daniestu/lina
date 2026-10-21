# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Las pausas de un modelo tras fallos de conexión crecen con cada fallo seguido y se olvidan al responder bien."""
import time

import pytest

from lina.nucleo import ia as IA
from lina.nucleo.constantes import PAUSA_MODELO_SEG, PAUSA_RED_SEG


@pytest.fixture(autouse=True)
def limpio():
    IA._pausa_modelo.clear()
    IA._fallos_red.clear()
    yield
    IA._pausa_modelo.clear()
    IA._fallos_red.clear()


def _espera(modelo="m", clave="k"):
    return IA._pausa_modelo[IA._id_pausa(modelo, clave)] - time.time()


def test_la_pausa_se_duplica_con_cada_fallo_hasta_el_tope():
    esperas = []
    for _ in range(6):
        IA._pausar_por_red("m", "k")
        esperas.append(round(_espera()))
    assert esperas[0] == PAUSA_RED_SEG
    assert esperas[1] == 2 * PAUSA_RED_SEG and esperas[2] == 4 * PAUSA_RED_SEG
    assert max(esperas) == PAUSA_MODELO_SEG == esperas[-1]


def test_cada_modelo_lleva_su_cuenta():
    IA._pausar_por_red("a", "k")
    IA._pausar_por_red("a", "k")
    IA._pausar_por_red("b", "k")
    assert round(_espera("b")) == PAUSA_RED_SEG and round(_espera("a")) == 2 * PAUSA_RED_SEG


def test_al_responder_bien_se_olvida(monkeypatch):
    class Resp:
        texto = "ok"
        uso = {}
        modelo_real = None
    class Prov:
        def turno(self, *a, **k):
            return Resp()
    IA._pausar_por_red("m", "k")
    IA._pausar_por_red("m", "k")
    IA._pausa_modelo.clear()                                     # (ha pasado la pausa)
    monkeypatch.setattr(IA, "_registrar_uso", lambda *a: None)
    assert IA._pedir_corto(Prov(), "k", "m", "s", [], "x", intentos=1, timeout=1) is not None
    assert IA._fallos_red == {}
    IA._pausar_por_red("m", "k")
    assert round(_espera()) == PAUSA_RED_SEG                      # vuelve a empezar desde la pausa corta
