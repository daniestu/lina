# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-voz`: comparar lo dicho con lo oído, resumir, informar y no romperse si falta un motor. Sin micrófono, sin modelos ni red."""
import numpy as np
import pytest

from lina.nucleo import probar_voz as PV


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(PV, "CARPETA", tmp_path / "prueba-voz")
    return tmp_path / "prueba-voz"


def test_acierta_ignora_mayusculas_tildes_y_signos():
    assert PV.acierta("¿Qué hora es?", "que hora es")
    assert not PV.acierta("Pausa", "Pausas")
    assert PV.parecido("Pon música", "Por música") > 0.8
    assert PV.parecido("Pausa", "Abre Firefox") < 0.4


def test_resumir_cuenta_aciertos_y_tiempos():
    r = PV.resumir(["Pausa", "Pon música"], [("pausas", 0.5), ("Pon música", 1.5)])
    assert r["aciertos"] == 1 and r["total"] == 2
    assert r["media_s"] == pytest.approx(1.0) and r["max_s"] == 1.5


def test_wav_ida_y_vuelta(carpeta):
    audio = np.sin(np.linspace(0, 60, 16000)).astype("float32") * 0.5
    PV.guardar_wav(PV.ruta_audio(0), audio)
    leido = PV.leer_wav(PV.ruta_audio(0))
    assert len(leido) == len(audio) and np.allclose(leido, audio, atol=1e-3)


def test_una_combinacion_que_falla_se_cuenta_y_no_rompe():
    def cargador(*a):
        raise ImportError("no hay librería")
    r = PV.medir_una(("whisper", "turbo", "cuda", "float16", True), [np.zeros(10)], ["Pausa"], cargador=cargador, vram=lambda: None)
    assert "ImportError" in r["error"]


def test_medir_una_y_informe():
    def cargador(motor, modelo, proc, calculo):
        return lambda audio, idioma, pista: "Pausa" if len(audio) == 1 else "Pausas"
    audios = [np.zeros(1), np.zeros(2)]
    r = PV.medir_una(("faster-whisper", "small", "cpu", "int8", True), audios, ["Pausa", "Pausa"], cargador=cargador, vram=lambda: None)
    assert r["aciertos"] == 1 and r["vram_mb"] is None
    texto = PV.informe(["Pausa", "Pausa"], [(("faster-whisper", "small", "cpu", "int8", True), r),
                                            (("whisper", "turbo", "cuda", "float16", True), {"error": "x"})])
    assert "«Pausa» → «Pausas»" in texto and "no disponible" in texto


def test_principal_graba_mide_y_no_pregunta_si_no_hay_modelos_grandes(carpeta, monkeypatch):
    monkeypatch.setattr(PV, "COMBINACIONES", [("faster-whisper", "small", "cpu", "int8", True)])
    sali = []
    esperadas = PV.frases()
    llamadas = iter(range(len(esperadas)))
    orden = PV.principal([], salida=sali.append, entrada=lambda *a: "",
                         grabar=lambda **k: np.ones(PV.FRECUENCIA, dtype="float32") * 0.1,
                         cargador=lambda *a: (lambda audio, idioma, pista: next(iter([esperadas[0]]))))
    assert orden == 0
    assert all(PV.ruta_audio(i).exists() for i in range(len(esperadas)))
    assert (carpeta / "informe.txt").exists()
    PV.principal(["borrar"], salida=sali.append)
    assert not carpeta.exists()


def test_si_dices_que_no_a_las_descargas_no_mide(carpeta, monkeypatch):
    sali = []
    PV.guardar_wav  # las grabaciones ya existen
    for i in range(len(PV.frases())):
        PV.guardar_wav(PV.ruta_audio(i), np.ones(PV.FRECUENCIA, dtype="float32") * 0.1)
    def cargador(*a):
        raise AssertionError("no debía medir")
    assert PV.principal([], salida=sali.append, entrada=lambda *a: "n", cargador=cargador) == 0
    assert any("no mido nada" in x for x in sali)


def test_cuda_instalar_y_cargar(monkeypatch):
    from lina.nucleo import cuda as CU
    llamadas = []

    class R:
        returncode = 0
        stdout = stderr = ""
    monkeypatch.setattr(CU, "instaladas", lambda: True)
    assert CU.instalar(ejecutar=lambda cmd, **k: (llamadas.append(cmd), R())[1])
    assert llamadas[0][1:4] == ["-m", "pip", "install"] and "nvidia-cublas-cu12" in llamadas[0]
    monkeypatch.setattr(CU, "instaladas", lambda: False)
    assert CU.cargar_librerias() is False                 # sin las librerías no hace nada ni falla


def test_cuda_instalar_cuenta_el_fallo():
    from lina.nucleo import cuda as CU

    class R:
        returncode = 1
        stdout = ""
        stderr = "ERROR: sin red\n"
    dicho = []
    assert CU.instalar(salida=dicho.append, ejecutar=lambda *a, **k: R()) is False
    assert "sin red" in dicho[0]
