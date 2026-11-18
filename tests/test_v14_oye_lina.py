# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""V14a: cada «Oye Lina» con algo sonando deja una línea en escuchas.jsonl, solo con números: de una frase (no se baja nunca), en dos tiempos (cuánto
tardó en bajar tras el pitido y si hablaste antes) o sin orden. Sin micrófono, sin audio real y con el reloj simulado."""
import datetime

import pytest

from lina.nucleo import tiempos as TIE
from lina.voz import manos_libres as M

SUENA = "Sink Input #7\n\tCorked: no\n\tMute: no\n\tapplication.name = \"Reproductor\"\n"


class Asistente:
    estado, interrumpiendo, modo_privado, origen_voz_libre = "esperando", False, False, True

    def __init__(self):
        self.ordenes, self.escuchas, self.bajadas = [], [], 0

    def atender_manos_libres(self, t):
        self.ordenes.append(t)
        return True

    def en_juego(self):
        return False

    def _bajar_sonido(self, motivo=""):
        self.bajadas += 1

    def _subir_sonido(self, motivo=""):
        pass

    def _anotar_escucha(self, fin, **datos):
        self.escuchas.append((fin, datos))


@pytest.fixture
def oyente(tmp_path):
    a, t, textos = Asistente(), [100.0], []
    sonido = {"suena": True}
    ml = M.ManosLibres(a, lambda audio: textos.pop(0), log=lambda m: None, reloj=lambda: t[0], cfg=M.Config(tmp_path / "activacion.txt"),
                       pactl=lambda *x: SUENA if sonido["suena"] else "")
    return ml, a, t, textos, sonido


def test_de_una_frase_se_apunta_antes_de_atenderla(oyente):
    ml, a, t, textos, _ = oyente
    textos.append("Oye Lina, pon música")
    ml.tratar_frase(b"x")
    assert a.escuchas == [("oye_lina", {"forma": "una_frase"})] and a.ordenes == ["pon música"]


def test_en_dos_tiempos_mide_la_bajada_y_si_hablaste_antes(oyente):
    ml, a, t, textos, _ = oyente
    textos.append("Oye Lina")
    ml.tratar_frase(b"x")
    t[0] += 0.42
    ml._bajar_tras_pitido()                         # lo que hace el temporizador de 0,4 s
    t[0] += 0.5
    ml.seg.en_voz, ml.seg.alimentar = True, lambda bloque: None
    ml.procesar_bloque(None)                         # tu voz empieza después de bajar
    textos.append("pon música")
    ml.tratar_frase(b"x")
    assert a.escuchas == [("oye_lina", {"forma": "dos_tiempos", "bajado_ms": pytest.approx(420), "voz_antes": False})]
    assert a.bajadas == 1 and a.ordenes == ["pon música"]


def test_si_hablas_antes_de_que_baje_se_apunta(oyente):
    ml, a, t, textos, _ = oyente
    textos.append("Oye Lina")
    ml.tratar_frase(b"x")
    t[0] += 0.1
    ml.oye["voz"] = t[0]                             # el detector ya te oía
    t[0] += 0.3
    ml._bajar_tras_pitido()
    textos.append("baja la persiana")
    ml.tratar_frase(b"x")
    assert a.escuchas[-1][1]["voz_antes"] is True


def test_sin_orden_tambien_se_apunta_y_sin_sonido_nada(oyente):
    ml, a, t, textos, sonido = oyente
    textos.append("Oye Lina")
    ml.tratar_frase(b"x")
    t[0] += 60
    ml.tic()
    assert a.escuchas == [("oye_lina", {"forma": "sin_orden"})]
    sonido["suena"] = False
    textos.append("Oye Lina, pon música")
    ml.tratar_frase(b"x")
    assert len(a.escuchas) == 1


def test_si_pactl_falla_no_estorba(tmp_path):
    a = Asistente()

    def roto(*x):
        raise OSError("sin pactl")
    ml = M.ManosLibres(a, lambda audio: "Oye Lina, pon música", log=lambda m: None, cfg=M.Config(tmp_path / "a.txt"), pactl=roto)
    ml.tratar_frase(b"x")
    assert a.ordenes == ["pon música"] and a.escuchas == []


# ---------------------------------------------------------------- el registro y el resumen
def test_el_registro_solo_lleva_numeros_y_rechaza_formas_raras():
    reg = TIE.registro_escucha("oye_lina", forma="dos_tiempos", bajado_ms=417.6, voz_antes=1, hoy=datetime.date(2026, 11, 18))
    assert reg == {"dia": "2026-11-18", "fin": "oye_lina", "forma": "dos_tiempos", "bajado_ms": 418, "voz_antes": True}
    for malo in ({"forma": "otra"}, {}):
        with pytest.raises(ValueError):
            TIE.registro_escucha("oye_lina", **malo)
    with pytest.raises(ValueError):
        TIE.registro_escucha("silencio", forma="una_frase")


def _oyes(*formas):
    return [{"dia": "2026-11-18", "fin": "oye_lina", "forma": f, **({"bajado_ms": 420, "voz_antes": antes} if f == "dos_tiempos" else {})}
            for f, antes in formas]


def test_el_resumen_cuenta_con_el_sonido_alto_y_el_criterio_de_uno_de_cada_cinco():
    o = TIE.resumir_oye(_oyes(("una_frase", None), ("dos_tiempos", True), ("dos_tiempos", False), ("dos_tiempos", False), ("dos_tiempos", False),
                              ("dos_tiempos", False), ("sin_orden", None)))
    assert (o["n"], o["con_orden"], o["alto"], o["bajado_ms"], o["supera"]) == (7, 6, 2, 420, True)
    o = TIE.resumir_oye(_oyes(("una_frase", None), *[("dos_tiempos", False)] * 4))
    assert (o["alto"], o["con_orden"], o["supera"]) == (1, 5, False)        # 1 de 5 justo: no pasa de 1 de cada 5


def test_lina_tiempos_escucha_lo_enseña_aparte_del_atajo(tmp_path):
    archivo = tmp_path / "escuchas.jsonl"
    for r in _oyes(("una_frase", None), ("dos_tiempos", True)) + [{"dia": "2026-11-18", "fin": "silencio", "ajuste": True, "silencio": 1.0}]:
        TIE.apuntar_escucha(r, archivo)
    salida = []
    TIE.principal_escucha([], salida.append, archivo, hoy=datetime.date(2026, 11, 18))
    texto = "\n".join(salida)
    assert "Escuchas con el atajo, últimos 14 días: 1" in texto and "«Oye Lina» con algo sonando: 2" in texto
    assert "Con el sonido alto: 2 de 2 con orden (100 %)" in texto
    assert max(len(s) for s in salida if "Oye Lina" in s or s.startswith("  ")) <= 100
    salida.clear()
    archivo.write_text("")
    TIE.apuntar_escucha(_oyes(("sin_orden", None))[0], archivo)
    TIE.principal_escucha([], salida.append, archivo, hoy=datetime.date(2026, 11, 18))
    assert "«Oye Lina» con algo sonando: 1" in "\n".join(salida)
