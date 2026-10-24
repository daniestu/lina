# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El modelo local de reserva (Ollama) solo se carga si cabe en el tope de VRAM de Lina (ia.tope_vram_mb, contando Whisper). Todo simulado: ni Ollama,
ni nvidia-smi, ni la tarjeta, ni el llavero de verdad."""
import sys
from unittest.mock import MagicMock

import pytest

from lina.modulos import gpu as GPU
from lina.nucleo import ajustes as AJ
from lina.nucleo import ia as IA
from lina.nucleo import modelos as MOD

GB = 1e9


class _Respuesta:
    def __init__(self, datos):
        self.datos = datos

    def json(self):
        return self.datos


def _ollama(monkeypatch, tamano=None, cargado=None, apagado=False):
    """Ollama simulado: `tamano` en disco (/api/tags) y, si está cargado, lo que ocupa (/api/ps)."""
    pedidos = []

    def get(url, timeout=None):
        pedidos.append(url)
        if apagado:
            raise IA.requests.ConnectionError("Ollama no está")
        if url.endswith("/api/ps"):
            return _Respuesta({"models": [{"name": IA.MODELO_LOCAL, "size_vram": cargado}] if cargado else []})
        return _Respuesta({"models": [{"name": IA.MODELO_LOCAL, "size": tamano}] if tamano else []})
    monkeypatch.setattr(IA.requests, "get", get)
    return pedidos


# ---------- la lectura de la tarjeta (reutiliza el módulo de la gráfica) ----------
def _sysfs(tmp_path, vendor, usada=None, total=None):
    d = tmp_path / "class/drm/card0/device"
    d.mkdir(parents=True)
    (d / "vendor").write_text(vendor)
    if usada is not None:
        (d / "mem_info_vram_used").write_text(str(int(usada * 1e6)))
        (d / "mem_info_vram_total").write_text(str(int(total * 1e6)))
    return tmp_path


@pytest.fixture
def sin_nvidia(monkeypatch):
    monkeypatch.setattr(GPU.shutil, "which", lambda programa: None)


def test_sin_tarjeta(tmp_path, sin_nvidia):
    assert GPU.memoria_libre(tmp_path) == ("sin_tarjeta", None)


def test_amd_se_mide_por_sysfs(tmp_path, sin_nvidia):
    assert GPU.memoria_libre(_sysfs(tmp_path, "0x1002", usada=2000, total=16000)) == ("medible", 14000)


def test_intel_integrada_no_se_puede_medir(tmp_path, sin_nvidia):
    assert GPU.memoria_libre(_sysfs(tmp_path, "0x8086")) == ("ilegible", None)


def test_nvidia_se_mide_con_nvidia_smi(tmp_path, monkeypatch):
    monkeypatch.setattr(GPU.shutil, "which", lambda programa: "/usr/bin/nvidia-smi")

    def ej(argv, timeout=8):
        if "--query-gpu=index,name" in argv:
            return 0, "0, Tarjeta de prueba"
        return 0, "50, 10, 3000, 16000, 80, 300, 1500, 9000, 0x0"
    monkeypatch.setattr(GPU, "_ej", ej)
    assert GPU.memoria_libre(tmp_path) == ("medible", 13000)


# ---------- ¿cabe? ----------
def test_un_modelo_de_6_gb_no_cabe_en_el_tope(monkeypatch):
    _ollama(monkeypatch, tamano=6.1 * GB)
    cabe, motivo, por_vram = IA.cabe_modelo_local(tope_mb=4096, memoria=("medible", 12000), whisper_mb=1100)
    assert not cabe and por_vram and "tope de 4096" in motivo


def test_uno_de_2_gb_cabe_con_whisper_en_la_tarjeta(monkeypatch):
    _ollama(monkeypatch, tamano=2 * GB)
    assert IA.cabe_modelo_local(tope_mb=4096, memoria=("medible", 8000), whisper_mb=1100)[0]


def test_tampoco_si_no_hay_memoria_libre(monkeypatch):
    _ollama(monkeypatch, tamano=2 * GB)
    cabe, motivo, por_vram = IA.cabe_modelo_local(tope_mb=4096, memoria=("medible", 2000), whisper_mb=1100)
    assert not cabe and por_vram and "libres" in motivo


def test_ya_cargado_vale_aunque_no_se_pueda_medir(monkeypatch):
    _ollama(monkeypatch, tamano=6.1 * GB, cargado=6.5 * GB)
    assert IA.cabe_modelo_local(tope_mb=4096, memoria=("ilegible", None), whisper_mb=1100)[0]


def test_sin_tarjeta_se_permite_en_la_cpu(monkeypatch):
    _ollama(monkeypatch, tamano=6.1 * GB)
    cabe, motivo, _ = IA.cabe_modelo_local(tope_mb=4096, memoria=("sin_tarjeta", None), whisper_mb=0)
    assert cabe and "CPU" in motivo


def test_con_tarjeta_que_no_se_puede_leer_no_se_carga(monkeypatch):
    _ollama(monkeypatch, tamano=1 * GB)
    cabe, _, por_vram = IA.cabe_modelo_local(tope_mb=4096, memoria=("ilegible", None), whisper_mb=0)
    assert not cabe and por_vram


def test_ollama_apagado_no_es_cosa_de_la_vram(monkeypatch):
    _ollama(monkeypatch, apagado=True)
    cabe, _, por_vram = IA.cabe_modelo_local(tope_mb=4096, memoria=("medible", 12000), whisper_mb=0)
    assert not cabe and not por_vram


def test_el_tope_sale_del_ajuste(monkeypatch):
    assert AJ.ESQUEMA["ia"]["tope_vram_mb"][0] == 4096
    _ollama(monkeypatch, tamano=6.1 * GB)                       # ~7320 MB + 1100 de Whisper
    for tope, esperado in ((8192, False), (10000, True)):
        falso = MagicMock()
        falso.get = lambda seccion, clave, t=tope: t if (seccion, clave) == ("ia", "tope_vram_mb") else None
        monkeypatch.setattr(IA.AJ, "actuales", lambda log=None, f=falso: f)
        assert IA.cabe_modelo_local(memoria=("medible", 20000), whisper_mb=1100)[0] is esperado, tope


# ---------- lo que ocupa Whisper ----------
def test_whisper_cuenta_solo_si_esta_en_la_tarjeta(monkeypatch):
    fabrica = MagicMock()
    MOD.cargar_whisper(log=lambda m: None, fabrica=fabrica, elegir=lambda: ("large-v3-turbo", "cuda", "int8_float16", "prueba", None))
    assert MOD.vram_whisper_mb() == 1100
    MOD.cargar_whisper(log=lambda m: None, fabrica=fabrica, elegir=lambda: ("small", "cpu", "int8", "prueba", None))
    assert MOD.vram_whisper_mb() == 0

    def falla_en_la_tarjeta(modelo, device, compute_type):
        if device == "cuda":
            raise RuntimeError("sin memoria")
        return object()
    MOD.cargar_whisper(log=lambda m: None, fabrica=falla_en_la_tarjeta, elegir=lambda: ("large-v3-turbo", "cuda", "int8_float16", "prueba", None))
    assert MOD.vram_whisper_mb() == 0


# ---------- el plan B ----------
@pytest.fixture
def asistente(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    monkeypatch.setattr(A.CL, "obtener", lambda *a, **k: None)       # ni el llavero ni el archivo de claves de verdad
    monkeypatch.setattr(A.H, "hechos_sistema", lambda: "")
    a = A.Asistente.__new__(A.Asistente)
    a.clave = ""                                                      # sin Gemini: se va directo al plan B
    a.acciones_confirmadas, a.historial, a.pregunta_pura = [], [], "hola"
    a.contexto = {"tipo": "general", "nombre": None, "clase": ""}
    a.ejecutor = MagicMock()
    a.ejecutor.pendientes = []
    return A, a


def test_el_plan_b_no_llama_a_ollama_si_no_cabe(asistente, monkeypatch):
    A, a = asistente
    monkeypatch.setattr(A, "cabe_modelo_local", lambda: (False, "no cabe", True))
    monkeypatch.setattr(A, "preguntar_local", MagicMock(side_effect=AssertionError("no debía cargar el modelo local")))
    texto, origen = a._responder("hola", None)
    assert "no cabe en la tarjeta" in texto and "plan B" in origen


def test_el_plan_b_sin_ollama_contesta_como_siempre(asistente, monkeypatch):
    A, a = asistente
    monkeypatch.setattr(A, "cabe_modelo_local", lambda: (False, "Ollama no contesta", False))
    monkeypatch.setattr(A, "preguntar_local", MagicMock(side_effect=AssertionError("no debía llamar a Ollama")))
    assert a._responder("hola", None)[0] == A.SIN_RESPUESTA


def test_el_plan_b_pide_soltar_la_vram_pronto(asistente, monkeypatch):
    A, a = asistente
    monkeypatch.setattr(A, "cabe_modelo_local", lambda: (True, "cabe", False))
    local = MagicMock(return_value="respuesta local")
    monkeypatch.setattr(A, "preguntar_local", local)
    assert a._responder("hola", None) == ("respuesta local", "local (plan B)")
    assert local.call_args.kwargs["soltar_en"] == A.SOLTAR_LOCAL_PLAN_B == "1m"


def test_preguntar_local_manda_el_keep_alive(monkeypatch):
    enviado = {}

    class _Post(_Respuesta):
        def raise_for_status(self):
            pass

    def post(url, timeout=None, json=None):
        enviado.update(json)
        return _Post({"message": {"content": "vale"}})
    monkeypatch.setattr(IA.requests, "post", post)
    assert IA.preguntar_local("hola", None, permitir_escalar=False, soltar_en="1m") == "vale"
    assert enviado["keep_alive"] == "1m"


def test_con_prioridad_local_si_no_cabe_queda_escrito_el_motivo_y_que_va_a_la_nube(asistente, monkeypatch):
    A, a = asistente
    motivo = f"{IA.MODELO_LOCAL} necesita ~7320 MB y con Whisper (1100 MB) pasaría del tope de 4096 MB (ia.tope_vram_mb)"
    monkeypatch.setattr(A, "PRIORIDAD", "local")
    monkeypatch.setattr(A, "cabe_modelo_local", lambda: (False, motivo, True))
    monkeypatch.setattr(A, "preguntar_local", MagicMock(side_effect=AssertionError("no debía cargar el modelo local")))
    registro = []
    monkeypatch.setattr(A, "log", registro.append)
    a._responder("hola", None)
    linea = next(l for l in registro if l.startswith("Prioridad local"))
    assert motivo in linea and "paso a la nube" in linea
