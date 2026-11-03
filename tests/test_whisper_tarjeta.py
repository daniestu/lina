# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Whisper en la tarjeta sin sus librerías de NVIDIA: el modelo carga sin cuBLAS y solo falla al transcribir. Lina tiene que verlo antes y, si se le
escapa, pasar a la CPU en vez de responder «Error inesperado» a cada petición. Nada carga librerías ni modelos de verdad."""
import threading

import pytest

from lina.nucleo import asistente as A
from lina.nucleo import cuda as CUDA
from lina.nucleo import modelos as MOD

ERROR_REAL = RuntimeError("Library libcublas.so.12 is not found or cannot be loaded")


def test_las_del_entorno_de_lina_bastan(monkeypatch):
    monkeypatch.setattr(CUDA, "cargar_librerias", lambda: True)
    assert CUDA.disponibles(cargar=lambda *a, **k: pytest.fail("no hace falta mirar el sistema"))


def test_las_del_sistema_valen_si_son_de_la_version_que_pide_ctranslate2(monkeypatch):
    monkeypatch.setattr(CUDA, "cargar_librerias", lambda: False)
    pedidas = []
    assert CUDA.disponibles(cargar=lambda nombre, **k: pedidas.append(nombre))
    assert pedidas == ["libcublas.so.12", "libcudnn.so.9"]


def test_una_cuda_13_del_sistema_no_cuenta(monkeypatch):
    """Lo que pasó: /opt/cuda trae libcublas.so.13 y el entorno recién creado no tenía las de pip."""
    monkeypatch.setattr(CUDA, "cargar_librerias", lambda: False)

    def cargar(nombre, **k):
        raise OSError(f"{nombre}: cannot open shared object file")
    assert not CUDA.disponibles(cargar=cargar)


def test_sin_librerias_la_tarjeta_no_esta_lista_aunque_el_driver_la_vea(monkeypatch):
    monkeypatch.setattr(MOD.CUDA, "disponibles", lambda: False)
    assert MOD._cuda_usable() is False


class _Aj:
    def get(self, seccion, clave):
        return "auto"


def test_el_registro_dice_que_faltan_las_librerias_y_como_ponerlas(monkeypatch):
    monkeypatch.setattr(MOD, "_cuda_usable", lambda: False)
    monkeypatch.setattr(MOD.CUDA, "hay_nvidia", lambda: True)
    modelo, proc, calculo, motivo, _ = MOD.elegir_whisper(None, lambda n, **k: None, _Aj())
    assert (modelo, proc, calculo) == (MOD.MODELO_WHISPER, "cpu", "int8")
    assert "librerías CUDA" in motivo and "lina modelos gpu" in motivo


def test_sin_tarjeta_nvidia_el_motivo_no_cambia(monkeypatch):
    monkeypatch.setattr(MOD, "_cuda_usable", lambda: False)
    monkeypatch.setattr(MOD.CUDA, "hay_nvidia", lambda: False)
    assert MOD.elegir_whisper(None, lambda n, **k: None, _Aj())[3] == "sin tarjeta NVIDIA lista"


@pytest.mark.parametrize("error, es", [
    (ERROR_REAL, True), (RuntimeError("Library libcudnn_ops.so.9.1.0 is not found"), True), (OSError("libcudart.so.12: cannot open"), True),
    (RuntimeError("CUDA failed with error out of memory"), False), (ValueError("libcublas.so.12"), False), (RuntimeError("libportaudio.so.2"), False),
])
def test_que_cuenta_como_fallo_de_libreria(error, es):
    assert MOD.fallo_de_libreria(error) is es


def test_pasar_a_cpu_carga_small_y_deja_de_contar_vram(monkeypatch):
    monkeypatch.setitem(MOD._en_tarjeta, "mb", 1100)
    avisos, pedidos = [], []
    assert MOD.pasar_a_cpu(avisos.append, lambda *a, **k: pedidos.append((a, k)) or "cpu") == "cpu"
    assert pedidos == [((MOD.MODELO_WHISPER,), {"device": "cpu", "compute_type": "int8"})]
    assert MOD.vram_whisper_mb() == 0 and "lina modelos gpu" in avisos[0]


class _Segmento:
    def __init__(self, texto):
        self.text = texto


class _WhisperTarjeta:
    """Como el de verdad: transcribe() devuelve un generador y el fallo de cuBLAS sale al recorrerlo."""
    def __init__(self, error=ERROR_REAL):
        self.error = error

    def transcribe(self, audio, **k):
        def segmentos():
            raise self.error
            yield
        return segmentos(), None


class _WhisperCPU:
    def __init__(self):
        self.llamadas = []

    def transcribe(self, audio, **k):
        self.llamadas.append(k)
        return iter([_Segmento(" abre"), _Segmento("firefox ")]), None


def _asistente(monkeypatch, whisper, mb=1100):
    monkeypatch.setitem(MOD._en_tarjeta, "mb", mb)
    monkeypatch.setattr(A, "log", lambda m: None)
    cpu = _WhisperCPU()
    cargas = []
    monkeypatch.setattr(A.MODELOS, "pasar_a_cpu", lambda log, fabrica: cargas.append(fabrica) or cpu)
    a = A.Asistente.__new__(A.Asistente)
    a.whisper, a.cerrojo_whisper = whisper, threading.Lock()
    return a, cpu, cargas


def test_si_la_tarjeta_no_puede_transcribir_pasa_a_la_cpu_y_te_entiende(monkeypatch):
    a, cpu, cargas = _asistente(monkeypatch, _WhisperTarjeta())
    assert a._whisper_texto(b"audio", language="es", beam_size=1) == "abre firefox"
    assert a.whisper is cpu and cpu.llamadas == [{"language": "es", "beam_size": 1}] and len(cargas) == 1
    assert a._whisper_texto(b"audio", language="es") == "abre firefox" and len(cargas) == 1     # una sola vez


def test_otro_error_de_la_tarjeta_no_se_esconde(monkeypatch):
    a, _, cargas = _asistente(monkeypatch, _WhisperTarjeta(RuntimeError("CUDA failed with error out of memory")))
    with pytest.raises(RuntimeError, match="out of memory"):
        a._whisper_texto(b"audio", language="es")
    assert not cargas


def test_en_la_cpu_no_hay_a_donde_pasar(monkeypatch):
    a, _, cargas = _asistente(monkeypatch, _WhisperTarjeta(), mb=0)
    with pytest.raises(RuntimeError, match="libcublas"):
        a._whisper_texto(b"audio", language="es")
    assert not cargas
