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
