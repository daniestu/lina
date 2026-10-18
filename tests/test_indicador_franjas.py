# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
from lina.voz import indicador as IND


def test_franjas_del_largo_completo():
    w, h, g = 1920, 1080, 40
    assert IND.medidas_de("arriba", w, h, g) == (1920, 40)
    assert IND.medidas_de("derecha", w, h, g) == (40, 1080)


def test_grosor_limitado_por_la_pantalla():
    assert IND.medidas_de("arriba", 100, 60, 300) == (100, 30)


def test_anclas_pegan_a_tres_bordes_menos_el_opuesto():
    for lado in IND.LADOS:
        assert sum(IND.anclas_de(lado)) == 3
    assert IND.anclas_de("arriba")[1] is False
    assert IND.anclas_de("derecha")[3] is True and IND.anclas_de("derecha")[2] is False


def test_degradado_parte_del_borde_de_pantalla():
    assert IND.degradado_de("arriba", 1920, 40) == (0, 0, 0, 40)
    assert IND.degradado_de("abajo", 1920, 40) == (0, 40, 0, 0)
    assert IND.degradado_de("izquierda", 40, 1000) == (0, 0, 40, 0)
    assert IND.degradado_de("derecha", 40, 1000) == (40, 0, 0, 0)
