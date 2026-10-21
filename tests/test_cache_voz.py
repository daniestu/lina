# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Caché de frases cortas de voz: la segunda vez suenan sin volver a sintetizar. Sin audio real."""
import os

from lina.nucleo import cache_voz as CV

WAV = b"RIFF" + b"\0" * 80


def test_guardar_y_buscar_una_frase_corta(tmp_path):
    origen = tmp_path / "respuesta.wav"
    origen.write_bytes(WAV)
    carpeta = tmp_path / "voz"
    assert CV.buscar("m", None, 1.0, "Abierto.", carpeta) is None
    assert CV.guardar(origen, "m", None, 1.0, "Abierto.", carpeta)
    ruta = CV.buscar("m", None, 1.0, "Abierto.", carpeta)
    assert ruta and ruta.read_bytes() == WAV and ruta != origen


def test_la_clave_distingue_voz_locutor_velocidad_y_texto(tmp_path):
    origen = tmp_path / "r.wav"
    origen.write_bytes(WAV)
    carpeta = tmp_path / "voz"
    CV.guardar(origen, "m", 1, 1.0, "Hola.", carpeta)
    assert CV.buscar("m", 1, 1.0, "Hola.", carpeta)
    for otra in (("otra", 1, 1.0, "Hola."), ("m", 2, 1.0, "Hola."), ("m", 1, 1.2, "Hola."), ("m", 1, 1.0, "Adiós.")):
        assert CV.buscar(*otra, carpeta) is None


def test_las_frases_largas_no_se_guardan(tmp_path):
    origen = tmp_path / "r.wav"
    origen.write_bytes(WAV)
    largo = "x" * (CV.MAX_CARACTERES + 1)
    assert CV.guardar(origen, "m", None, 1.0, largo, tmp_path / "voz") is False
    assert CV.buscar("m", None, 1.0, largo, tmp_path / "voz") is None
    assert not (tmp_path / "voz").exists()


def test_un_archivo_vacio_o_roto_no_vale(tmp_path):
    carpeta = tmp_path / "voz"
    carpeta.mkdir()
    ruta = CV._ruta("m", None, 1.0, "Hola.", carpeta)
    ruta.write_bytes(b"")
    assert CV.buscar("m", None, 1.0, "Hola.", carpeta) is None


def test_se_poda_lo_menos_usado(tmp_path, monkeypatch):
    origen = tmp_path / "r.wav"
    origen.write_bytes(WAV)
    carpeta = tmp_path / "voz"
    monkeypatch.setattr(CV, "MAX_ARCHIVOS", 3)
    for i in range(5):
        CV.guardar(origen, "m", None, 1.0, f"frase {i}", carpeta)
        for f in carpeta.glob("*.wav"):
            pass
        os.utime(CV._ruta("m", None, 1.0, f"frase {i}", carpeta), (1000 + i, 1000 + i))
    CV.podar(carpeta)
    assert len(list(carpeta.glob("*.wav"))) == 3
    assert CV.buscar("m", None, 1.0, "frase 4", carpeta) and CV.buscar("m", None, 1.0, "frase 0", carpeta) is None


def test_guardar_nunca_falla(tmp_path):
    assert CV.guardar(tmp_path / "no_existe.wav", "m", None, 1.0, "Hola.", tmp_path / "voz") is False
