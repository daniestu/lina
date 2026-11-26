# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A17b (decidido el 2026-11-26): el botón Home de los mandos ya no activa a Lina de fábrica, porque Steam abre su menú con él; quien lo quiera lo
enciende con activacion.boton_home. La IA no puede encenderlo."""
from lina.nucleo import ajustes as AJ


def test_home_viene_apagado_de_fabrica():
    assert AJ.ESQUEMA["activacion"]["boton_home"][0] is False


def test_se_puede_encender_y_la_ia_no(tmp_path):
    aj = AJ.Ajustes(tmp_path / "ajustes.toml", log=lambda m: None)
    assert aj.get("activacion", "boton_home") is False
    aj.establecer("activacion", "boton_home", "true")
    assert aj.get("activacion", "boton_home") is True
    from lina.nucleo import autoconocimiento as AUT
    hecho, _ = AUT.cambiar("activacion.boton_home", "true", aj=aj)
    assert hecho is False
