# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""M4, primer paso: si una orden acabó bien se mira en un solo sitio (ejecucion.salio_bien), no comparando el texto en cada módulo."""
from pathlib import Path

from lina.nucleo import ejecucion as EJ

SRC = Path(__file__).resolve().parents[1] / "src" / "lina"


def test_salio_bien_y_salida_de_orden():
    assert EJ.salio_bien("código de salida: 0 (1 s)\nhecho")
    assert not EJ.salio_bien("código de salida: 1 (0 s)\nfallo")
    assert not EJ.salio_bien("PREPARADO, NO EJECUTADO: …")
    assert not EJ.salio_bien(None)
    assert EJ.es_salida_de_orden("código de salida: 127 (0 s)\nbash: x: command not found")
    assert not EJ.es_salida_de_orden("Lanzado.")


def test_ningun_modulo_compara_el_prefijo_a_mano():
    a_mano = [f"{p.relative_to(SRC)}:{n}" for p in SRC.rglob("*.py") if p.name != "ejecucion.py"
              for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if 'startswith("código de salida' in linea]
    assert a_mano == []
