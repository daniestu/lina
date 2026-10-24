# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Variantes que Whisper suelta de verdad con la voz de Dani (prueba grande) y que `directas` ya tolera, sin que ninguna pueda cambiar el sentido de una orden."""
import pytest

from lina.nucleo import directas as D


@pytest.mark.parametrize("oido,esperado", [
    ("Renuda la música.", ("reproduccion", {"accion": "reanudar"})),
    ("Reanuda la música", ("reproduccion", {"accion": "reanudar"})),
    ("Entiende el Bluetooth.", ("bluetooth", {"accion": "bluetooth_encender"})),
    ("Conecto mis auriculares.", ("bluetooth", {"accion": "bluetooth_conectar", "objetivo": "auriculares"})),
    ("Conectas mis auriculares", ("bluetooth", {"accion": "bluetooth_conectar", "objetivo": "auriculares"})),
    ("Ábreme y console.", ("abrir_app", {"nombre": "console"})),
])
def test_variantes_oidas_que_se_entienden(oido, esperado):
    assert D.entender(oido) == esperado


@pytest.mark.parametrize("oido", [
    "Abre y cierra la ventana", "Abre y cierra Steam", "Abre y lanza Steam", "Abre y busca recetas", "Abre y luego cierra",
])
def test_la_y_suelta_no_convierte_en_programa_una_orden_encadenada(oido):
    assert D.entender(oido) is None


def test_ninguna_variante_invierte_una_orden():
    assert D.entender("Desconecto mis auriculares")[1]["accion"] == "bluetooth_desconectar"
    assert D.entender("Desconecta los auriculares")[1]["accion"] == "bluetooth_desconectar"
    assert D.entender("Conecta los auriculares")[1]["accion"] == "bluetooth_conectar"
    assert D.entender("Pausa la música")[1]["accion"] == "pausar"
    assert D.entender("Para la música")[1]["accion"] == "detener"
