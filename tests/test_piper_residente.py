# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 12: Piper residente. Sin Piper de verdad: módulos falsos con las dos formas de su API, y un proceso hijo real que habla por tuberías."""
import json
import sys
import time
import wave

import pytest

from lina.voz import piper_residente as PR


def escribir_wav(wav, segundos=0.5):
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(22050)
    wav.writeframes(b"\x00\x00" * int(22050 * segundos))


class Voz12:
    """piper-tts 1.2: synthesize(texto, wav, speaker_id=, length_scale=)."""
    llamadas = []

    @classmethod
    def load(cls, ruta):
        cls.cargada = ruta
        return cls()

    def synthesize(self, texto, wav, speaker_id=None, length_scale=None):
        Voz12.llamadas.append((texto, speaker_id, length_scale))
        escribir_wav(wav)


class Voz13:
    """piper-tts 1.3 o posterior: synthesize_wav(texto, wav, syn_config=)."""
    llamadas = []

    @classmethod
    def load(cls, ruta):
        cls.cargada = ruta
        return cls()

    def synthesize_wav(self, texto, wav, syn_config=None):
        Voz13.llamadas.append((texto, syn_config.speaker_id, syn_config.length_scale))
        escribir_wav(wav)


class Config:
    def __init__(self, speaker_id=None, length_scale=None):
        self.speaker_id, self.length_scale = speaker_id, length_scale


class Piper12:
    PiperVoice = Voz12


class Piper13:
    PiperVoice = Voz13
    SynthesisConfig = Config


def test_sintetiza_con_las_dos_versiones_de_la_api(tmp_path):
    for piper, voz in ((Piper12, Voz12), (Piper13, Voz13)):
        voz.llamadas.clear()
        salida, voces = tmp_path / "a.wav", {}
        PR.sintetizar_con(piper, voces, {"modelo": "es_ES-x-medium", "carpeta": str(tmp_path), "locutor": 3, "escala": 1.25, "texto": "Hola", "salida": str(salida)})
        assert voz.llamadas == [("Hola", 3, 1.25)] and PR.audio_valido(salida)
        assert voz.cargada == str(tmp_path / "es_ES-x-medium.onnx")
        PR.sintetizar_con(piper, voces, {"modelo": "es_ES-x-medium", "carpeta": str(tmp_path), "texto": "Otra", "salida": str(salida)})
        assert len(voces) == 1 and voz.llamadas[-1] == ("Otra", None, None)         # la voz ya cargada se reutiliza


def test_solo_guarda_dos_voces_cargadas(tmp_path):
    voces = {}
    for nombre in ("a", "b", "c"):
        PR.sintetizar_con(Piper12, voces, {"modelo": nombre, "carpeta": str(tmp_path), "texto": "", "salida": ""})
    assert len(voces) == 2 and str(tmp_path / "a.onnx") not in voces


def test_audio_valido_rechaza_vacios_y_basura(tmp_path):
    assert not PR.audio_valido(tmp_path / "no_existe.wav")
    (tmp_path / "basura.wav").write_bytes(b"no soy un wav")
    assert not PR.audio_valido(tmp_path / "basura.wav")
    with wave.open(str(tmp_path / "vacio.wav"), "wb") as w:
        escribir_wav(w, 0.0)
    assert not PR.audio_valido(tmp_path / "vacio.wav")


def guion(extra=""):
    """El programa del proceso hijo: el trabajador de verdad, con un Piper falso dentro (`extra` cambia su comportamiento)."""
    return f"""
import sys, json, wave, time
sys.path[:0] = {json.dumps(sys.path)}
from lina.voz import piper_residente as PR
{extra}
class V:
    @classmethod
    def load(cls, ruta): return cls()
    def synthesize(self, texto, wav, speaker_id=None, length_scale=None):
        if texto == 'LENTO': time.sleep(5)
        if texto == 'ROTO': raise RuntimeError('boom')
        if texto == 'MUERE': sys.exit(3)
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
        wav.writeframes(b'\\x00\\x00' * (0 if texto == 'VACIO' else 11025))
class P: PiperVoice = V
PR.trabajador(piper=P)
"""


def residente(**kw):
    avisos = []
    r = PR.PiperResidente(orden=[sys.executable, "-c", guion()], log=avisos.append, **kw)
    r.avisos = avisos
    return r


def test_un_proceso_real_sintetiza_varias_frases_y_se_cierra(tmp_path):
    r = residente()
    try:
        salida = tmp_path / "s.wav"
        assert r.precalentar("voz", tmp_path)
        pid = r.proceso.pid
        for texto in ("Hola", "Otra frase", "Y otra más"):
            salida.unlink(missing_ok=True)
            assert r.sintetizar("voz", tmp_path, None, None, texto, salida) and PR.audio_valido(salida)
        assert r.proceso.pid == pid and r.avisos == []                    # sigue siendo el mismo proceso: la voz no se recarga
    finally:
        r.cerrar()
    assert r.proceso is None


def test_si_la_sintesis_falla_se_pide_el_metodo_de_siempre_y_a_la_segunda_se_rinde(tmp_path):
    r = residente()
    try:
        salida = tmp_path / "s.wav"
        assert r.sintetizar("voz", tmp_path, None, None, "ROTO", salida) is False and not r.rendido
        assert r.sintetizar("voz", tmp_path, None, None, "Hola", salida) is True        # se recupera: el fallo era de esa frase
        assert r.sintetizar("voz", tmp_path, None, None, "ROTO", salida) is False
        assert r.sintetizar("voz", tmp_path, None, None, "ROTO", salida) is False and r.rendido
        assert r.sintetizar("voz", tmp_path, None, None, "Hola", salida) is False        # rendido: ya ni lo intenta
        assert any("lina config poner voz.residente no" in a for a in r.avisos)
    finally:
        r.cerrar()


def test_audio_vacio_proceso_muerto_y_demora_no_dejan_a_lina_muda(tmp_path):
    salida = tmp_path / "s.wav"
    for texto, espera in (("VACIO", 30), ("MUERE", 30), ("LENTO", 0.5)):
        r = residente(espera_frase=espera, espera_carga=espera)
        try:
            t0 = time.monotonic()
            assert r.sintetizar("voz", tmp_path, None, None, texto, salida) is False, texto
            assert time.monotonic() - t0 < 10
            assert r.proceso is None                                          # el proceso dudoso se descarta
        finally:
            r.cerrar()


def test_sin_poder_arrancar_no_rompe(tmp_path):
    r = PR.PiperResidente(orden=["/no/existe/piper-falso"], log=lambda m: None)
    assert r.sintetizar("voz", tmp_path, None, None, "Hola", tmp_path / "s.wav") is False
    assert r.precalentar("voz", tmp_path) is False or r.rendido


def test_se_cierra_solo_tras_un_rato_sin_hablar(tmp_path):
    r = residente(inactividad=0.3)
    try:
        assert r.sintetizar("voz", tmp_path, None, None, "Hola", tmp_path / "s.wav")
        proceso = r.proceso
        for _ in range(40):
            if r.proceso is None:
                break
            time.sleep(0.1)
        assert r.proceso is None and proceso.wait(timeout=5) is not None          # y el proceso de verdad ha salido
        assert r.sintetizar("voz", tmp_path, None, None, "Hola otra vez", tmp_path / "s.wav")        # y vuelve a arrancar cuando hace falta
    finally:
        r.cerrar()


def test_no_sintetiza_texto_vacio(tmp_path):
    r = residente()
    assert r.sintetizar("voz", tmp_path, None, None, "", tmp_path / "s.wav") is False and r.proceso is None
