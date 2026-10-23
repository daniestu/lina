# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Modelos en el disco: Whisper y la voz. Nada se descarga de verdad (se pasa un descargador falso)."""
from lina.nucleo import modelos as MOD


def test_whisper_listo_si_el_descargador_lo_encuentra_en_local():
    llamadas = []
    assert MOD.whisper_listo(lambda n, **k: llamadas.append((n, k))) is True
    assert llamadas == [(MOD.MODELO_WHISPER, {"local_files_only": True})]


def test_whisper_no_listo_si_falla():
    def sin_modelo(n, **k):
        raise OSError("no está")
    assert MOD.whisper_listo(sin_modelo) is False


def test_asegurar_whisper_descarga_solo_lo_que_falta():
    descargas = []

    def descargar(n, **k):
        if k.get("local_files_only") and not descargas:
            raise OSError("no está")
        descargas.append(k)
    mensajes = []
    assert MOD.asegurar_whisper(mensajes.append, descargar) is True
    assert any("descargando" in m for m in mensajes) and mensajes[-1] == "Whisper: listo."


def test_asegurar_whisper_cuenta_el_fallo_sin_romperse():
    def siempre_falla(n, **k):
        raise ConnectionError("sin red")
    mensajes = []
    assert MOD.asegurar_whisper(mensajes.append, siempre_falla) is False
    assert "no he podido" in mensajes[-1] and "ConnectionError" in mensajes[-1]


def test_asegurar_todo_en_simulacion_no_toca_nada():
    mensajes = []
    ok, problemas = MOD.asegurar_todo(mensajes.append, descargar=lambda *a, **k: 1 / 0, simular=True)
    assert ok and problemas == [] and "simulación" in mensajes[0]


def test_asegurar_todo_lista_lo_que_falla(monkeypatch):
    monkeypatch.setattr(MOD, "asegurar_whisper", lambda *a, **k: False)
    monkeypatch.setattr(MOD.VOC, "preparar", lambda log=print: False)
    ok, problemas = MOD.asegurar_todo(lambda m: None)
    assert not ok and problemas == ["Whisper", "la voz"]


def test_principal_estado_y_descarga(monkeypatch, capsys):
    monkeypatch.setattr(MOD, "estado", lambda: {"whisper": True, "voz": "una", "voz_integra": False})
    assert MOD.principal(["estado"]) == 0
    salida = capsys.readouterr().out
    assert "listo" in salida and "ALTERADO" in salida
    monkeypatch.setattr(MOD, "asegurar_todo", lambda: (False, ["la voz"]))
    assert MOD.principal([]) == 1 and "Faltan: la voz" in capsys.readouterr().out
    monkeypatch.setattr(MOD, "asegurar_todo", lambda: (True, []))
    assert MOD.principal([]) == 0


class _Aj:
    def __init__(self, modelo="auto", proc="auto"):
        self.v = {"reconocimiento_modelo": modelo, "reconocimiento_procesador": proc}

    def get(self, seccion, clave):
        return self.v[clave]


def test_elegir_whisper_usa_la_tarjeta_solo_si_todo_esta_listo():
    esta = lambda n, **k: None                                           # noqa: E731  (el modelo está en el disco)
    assert MOD.elegir_whisper(True, esta, _Aj())[:3] == (MOD.MODELO_GPU, "cuda", "int8_float16")
    assert MOD.elegir_whisper(False, esta, _Aj())[:3] == (MOD.MODELO_WHISPER, "cpu", "int8")

    def falta(n, **k):
        raise OSError("no está")
    modelo, proc, _, motivo, por_bajar = MOD.elegir_whisper(True, falta, _Aj())
    assert (modelo, proc, por_bajar) == (MOD.MODELO_WHISPER, "cpu", MOD.MODELO_GPU) and "lina modelos gpu" in motivo


def test_elegir_whisper_respeta_lo_que_pides():
    esta = lambda n, **k: None                                           # noqa: E731
    assert MOD.elegir_whisper(True, esta, _Aj(proc="cpu"))[:3] == (MOD.MODELO_WHISPER, "cpu", "int8")
    assert MOD.elegir_whisper(True, esta, _Aj(modelo="medium"))[:3] == ("medium", "cuda", "int8_float16")
    assert "lina modelos gpu" in MOD.elegir_whisper(False, esta, _Aj(proc="cuda"))[3]


def test_cargar_whisper_vuelve_a_la_cpu_si_la_tarjeta_falla():
    intentos, avisos = [], []

    def fabrica(modelo, device, compute_type):
        intentos.append((modelo, device))
        if device == "cuda":
            raise RuntimeError("libcublas no está")
        return "modelo"
    elegir = lambda: (MOD.MODELO_GPU, "cuda", "float16", "tarjeta NVIDIA lista", None)   # noqa: E731
    assert MOD.cargar_whisper(avisos.append, fabrica, elegir) == "modelo"
    assert intentos == [(MOD.MODELO_GPU, "cuda"), (MOD.MODELO_WHISPER, "cpu")]
    assert any("uso «small» en la CPU" in a for a in avisos)


def test_cargar_whisper_no_oculta_un_fallo_de_la_cpu():
    import pytest

    def fabrica(*a, **k):
        raise MemoryError("sin memoria")
    with pytest.raises(MemoryError):
        MOD.cargar_whisper(lambda m: None, fabrica, lambda: (MOD.MODELO_WHISPER, "cpu", "int8", "x", None))


def test_asegurar_gpu_sin_nvidia_no_hace_nada(monkeypatch):
    monkeypatch.setattr(MOD.CUDA, "hay_nvidia", lambda: False)
    dicho = []
    assert MOD.asegurar_gpu(dicho.append, entrada=lambda *a: 1 / 0) is False and dicho


def test_asegurar_gpu_pregunta_antes_de_bajar_y_respeta_el_no(monkeypatch):
    monkeypatch.setattr(MOD.CUDA, "hay_nvidia", lambda: True)
    monkeypatch.setattr(MOD.CUDA, "instaladas", lambda: False)

    def falta(n, **k):
        raise OSError
    descargas = []
    assert MOD.asegurar_gpu(lambda m: None, entrada=lambda *a: "n", descargar=falta, instalar=lambda log: descargas.append("pip")) is False
    assert descargas == []


def test_asegurar_gpu_instala_baja_y_comprueba(monkeypatch):
    estado = {"libs": False, "modelo": False}
    monkeypatch.setattr(MOD.CUDA, "hay_nvidia", lambda: True)
    monkeypatch.setattr(MOD.CUDA, "instaladas", lambda: estado["libs"])
    monkeypatch.setattr(MOD, "_cuda_usable", lambda: estado["libs"])

    def descargar(n, **k):
        if k.get("local_files_only") and not estado["modelo"]:
            raise OSError
        estado["modelo"] = True

    def instalar(log):
        estado["libs"] = True
        return True
    dicho = []
    assert MOD.asegurar_gpu(dicho.append, entrada=lambda *a: "s", descargar=descargar, instalar=instalar) is True
    assert estado == {"libs": True, "modelo": True} and "Listo" in dicho[-1]
