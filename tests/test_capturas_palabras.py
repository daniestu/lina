# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Punto 5: una palabra suelta ya no manda una captura. Con las tres frases reales que mandaron la ventana del usuario a la IA, y lo que sí tiene que seguir mirando."""
import pytest

from lina.nucleo import comandos as C

REALES = ["Revisa a ver cómo funcionas y respóndeme a ver si yo te puedo dar como una fuente, una página web. Esto puedes hacerlo.",     # «esto»
          "Pero yo me refiero a que en vez de buscar tú en las páginas oficiales, que yo te doy una página y tú buscas en la página que yo te doy.",
          "Claro, pero yo no te lo quiero pasar por aquí por este chat, sino que yo quiero que revises cómo funciona la aplicación."]    # «aquí», «este»


@pytest.mark.parametrize("frase", REALES + ["Apaga la pantalla", "Haz una captura de pantalla", "Maximiza esta ventana", "Esto no funciona", "Ponlo aquí", "Dice que no hay red",
                                            "¿Qué significa Proton?", "¿Qué hago para instalar Steam?", "Sale a las ocho", "Mira a ver si hay actualizaciones"])
def test_una_palabra_suelta_no_manda_captura(frase):
    assert not C.pide_mirar(frase), frase


@pytest.mark.parametrize("frase", ["¿Qué pone aquí?", "Mira esto", "Mira mi pantalla", "¿Qué es esto?", "¿Qué significa esto?", "¿Qué me sale?", "¿Dónde pulso?", "¿Qué hago ahora?",
                                   "¿Qué ves?", "¿Puedes ver el error?", "¿Qué hay en mi pantalla?", "Léeme este mensaje", "¿Qué pone en esta ventana?", "Aquí dice que falta algo"])
def test_una_expresion_clara_si(frase):
    assert C.pide_mirar(frase), frase


def test_se_compara_por_palabras_enteras():
    assert not C.pide_mirar("porque ponerlo en pantallas viejas")


def test_con_la_pantalla_en_uso_basta_una_palabra_suelta_si_sigue_hablando_de_ella():
    assert C.sigue_mirando("¿Y aquí?") and C.sigue_mirando("¿Y ahora?") and C.sigue_mirando("Mira esto")
    assert not C.sigue_mirando(REALES[1]) and not C.sigue_mirando("¿Qué tiempo va a hacer mañana?")
