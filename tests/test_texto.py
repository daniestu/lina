# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Texto del asistente: números a palabras, limpieza para la voz y fecha para la IA."""
from datetime import datetime

import pytest

from lina.nucleo import texto as T


@pytest.mark.parametrize("n,esperado", [
    (0, "cero"), (7, "siete"), (21, "veintiuno"), (100, "cien"), (101, "ciento uno"), (115, "ciento quince"),
    (1000, "mil"), (2025, "dos mil veinticinco"), (15103, "quince mil ciento tres"), (1_000_000, "un millón"),
])
def test_numero_a_texto(n, esperado):
    assert T.numero_a_texto(n) == esperado


def test_los_numeros_de_una_frase_se_leen_con_letras():
    frase = T.numeros_a_palabras("Tengo 3 gatos, 21 perros y 15103 euros")
    assert "tres gatos" in frase and "veintiún perros" in frase and "quince mil ciento tres euros" in frase
    assert "por ciento" in T.numeros_a_palabras("un 50%")


def test_limpiar_para_voz_quita_el_formato():
    limpio = T.limpiar_para_voz("**Hola** _mundo_ `código`")
    assert "*" not in limpio and "`" not in limpio and "Hola" in limpio and "mundo" in limpio
    assert "https://" not in T.limpiar_para_voz("mira https://ejemplo.com/a/b/c ahora")


def test_la_fecha_para_la_ia_dice_dia_hora_y_mes():
    texto = T.texto_fecha_hora(datetime(2026, 10, 15, 9, 5))
    assert "09:05" in texto and "jueves 15 de octubre de 2026" in texto


def test_admite_duda_y_afirma_hecho():
    assert T.admite_duda("no estoy seguro de eso")
    assert not T.admite_duda("claro que sí")
    assert T.afirma_hecho("Listo, ya lo he hecho")
    assert not T.afirma_hecho("quizá mañana")


def test_estado_de_resultado():
    assert T.estado_de_resultado("código de salida: 0") == "terminó bien"
    assert T.estado_de_resultado("PREPARADO, NO EJECUTADO: todavía no") is None


def test_plano_simple_quita_acentos_y_mayusculas():
    assert T._plano_simple("  ÁÉÍÓÚ Ñandú ") == "aeiou nandu"
