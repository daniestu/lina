# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""V3b: fin de frase por silencio con el atajo (activacion.fin_por_silencio). Apagado, todo como siempre (doble pulsación). Activo: termina sola al quedarte
callado, con «No te he oído» si no dices nada o a los 60 s; siempre se cierra el micrófono antes del pitido de 520 Hz, la frase se procesa una sola vez
aunque el corte coincida con tu pulsación, y una pulsación justo después del corte no empieza otra escucha. Micrófono, pitido y Whisper simulados."""
import sys
import threading
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

from lina.nucleo import ajustes as AJ
from lina.voz import fin_de_frase as FDF

F = FDF.FRECUENCIA


def silencio(s, nivel=0.002):
    return (np.random.default_rng(0).standard_normal(int(s * F)) * nivel).astype(np.float32)


def voz(s, nivel=0.1):
    t = np.arange(int(s * F)) / F
    return (np.sin(2 * np.pi * 220 * t) * nivel * np.sqrt(2)).astype(np.float32)


class AjFalso:
    def __init__(self, **activacion):
        self.activacion = activacion

    def get(self, seccion, clave):
        if seccion == "activacion" and clave in self.activacion:
            return self.activacion[clave]
        return AJ.ESQUEMA[seccion][clave][0]


class HiloSincrono:
    """Para que lo que se lanza en un hilo (procesar, el corte) pase en el acto y en orden."""
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture
def A(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente
    return asistente


@pytest.fixture
def entorno(A, monkeypatch):
    """(asistente, eventos, micrófonos, procesados, poner_ajuste)."""
    eventos, micros, procesados = [], [], []

    class Micro:
        def __init__(self, **k):
            self.k, self.callback = k, k["callback"]
            micros.append(self)

        def start(self):
            eventos.append("abrir")

        def stop(self):
            eventos.append("parar")

        def close(self):
            eventos.append("cerrar")

        def dar(self, audio):
            for b in FDF.trocear(audio):
                self.callback(b.reshape(-1, 1), len(b), None, None)

    monkeypatch.setattr(A.sd, "InputStream", Micro)
    monkeypatch.setattr(A, "pitido", lambda f: eventos.append(f"pitido {f}"))
    monkeypatch.setattr(A, "threading", types.SimpleNamespace(Thread=HiloSincrono))
    monkeypatch.setattr(A, "log_nueva_peticion", lambda: None)
    ajuste = {"valor": AjFalso()}
    monkeypatch.setattr(A.AJ, "actuales", lambda log=None: ajuste["valor"])
    a = A.Asistente.__new__(A.Asistente)
    a.estado, a.cerrojo, a.fin_tarea, a.interrumpiendo = "esperando", threading.Lock(), threading.Event(), False
    a._preparar_contexto = lambda: None
    a._bajar_sonido = lambda *x: eventos.append("bajar")
    a._subir_sonido = lambda *x: eventos.append("subir")
    a.procesar = procesados.append
    a._empezar_interrupcion = lambda: eventos.append("interrupción")

    def poner(**valores):
        ajuste["valor"] = AjFalso(**valores)
    return a, eventos, micros, procesados, poner


def _cierre(eventos):
    i = eventos.index("parar")
    return eventos[i:i + 4]


# ---------------------------------------------------------------- apagado: como siempre
def test_apagado_solo_termina_pulsando(entorno):
    a, eventos, micros, procesados, _ = entorno
    a.pulsacion()
    assert "blocksize" not in micros[0].k                                    # el mismo micrófono de siempre, sin detector
    micros[0].dar(np.concatenate([silencio(0.5), voz(1), silencio(5)]))
    assert a.estado == "grabando" and procesados == []
    a.pulsacion()
    assert _cierre(eventos) == ["parar", "cerrar", "subir", "pitido 520"]
    assert len(procesados) == 1 and len(procesados[0]) == int(6.5 * F) // FDF.BLOQUE * FDF.BLOQUE


# ---------------------------------------------------------------- activo
def test_activo_termina_al_callar_cerrando_el_micro_antes_del_pitido(entorno):
    a, eventos, micros, procesados, poner = entorno
    poner(fin_por_silencio=True, silencio_atajo=1.0)
    a.pulsacion()
    assert micros[0].k["blocksize"] == FDF.BLOQUE
    micros[0].dar(np.concatenate([silencio(0.5), voz(1), silencio(3)]))
    assert _cierre(eventos) == ["parar", "cerrar", "subir", "pitido 520"]
    assert eventos.count("pitido 520") == 1 and len(procesados) == 1
    assert len(procesados[0]) / F == pytest.approx(0.5 + 1 + 1.0, abs=0.1)   # lo que llegó hasta el corte
    assert a.estado == "pensando"


def test_sin_voz_dice_no_te_he_oido_sin_pasar_por_whisper(entorno):
    a, eventos, micros, procesados, poner = entorno
    poner(fin_por_silencio=True, espera_atajo=2)
    a.pulsacion()
    micros[0].dar(silencio(5))
    assert _cierre(eventos) == ["parar", "cerrar", "subir", "pitido 520"]
    assert len(procesados) == 1 and len(procesados[0]) == 0                 # audio vacío: Whisper no se llama
    a._transcribir = MagicMock(side_effect=AssertionError("no debía transcribir"))
    dicho = []
    a.decir = dicho.append
    a._voz_a_respuesta(procesados[0])
    assert dicho == ["No te he oído."]


def test_si_nunca_oye_el_silencio_para_en_el_tope(entorno, A, monkeypatch):
    a, eventos, micros, procesados, poner = entorno
    monkeypatch.setattr(A, "TOPE_ATAJO_SEG", 2)
    poner(fin_por_silencio=True)
    a.pulsacion()
    micros[0].dar(np.concatenate([silencio(0.5), voz(3, nivel=0.05)]))       # voz (o música) sin pausa
    assert _cierre(eventos) == ["parar", "cerrar", "subir", "pitido 520"]
    assert len(procesados) == 1 and len(procesados[0]) / F == pytest.approx(2, abs=0.05)


def test_activo_tu_pulsacion_sigue_terminando_antes_y_sin_margen(entorno):
    a, eventos, micros, procesados, poner = entorno
    poner(fin_por_silencio=True)
    a.pulsacion()
    micros[0].dar(np.concatenate([silencio(0.5), voz(1)]))
    a.pulsacion()
    assert _cierre(eventos) == ["parar", "cerrar", "subir", "pitido 520"] and len(procesados) == 1
    micros[0].dar(silencio(3))                                               # un bloque que llega tarde no vuelve a terminar nada
    assert len(procesados) == 1 and eventos.count("pitido 520") == 1
    a.pulsacion()                                                            # tras terminar pulsando no hay margen: es una interrupción, como hoy
    assert eventos[-1] == "interrupción"


def test_una_pulsacion_justo_tras_el_corte_se_ignora_y_luego_vuelve_a_valer(entorno, A):
    a, eventos, micros, procesados, poner = entorno
    ahora = [100.0]
    a._reloj = lambda: ahora[0]
    poner(fin_por_silencio=True)
    a.pulsacion()
    micros[0].dar(np.concatenate([silencio(0.5), voz(1), silencio(2)]))
    assert len(procesados) == 1
    ahora[0] += A.MARGEN_TRAS_CORTE - 0.1
    a.pulsacion()
    assert "interrupción" not in eventos and len(micros) == 1                # ni otra escucha ni otra interrupción
    ahora[0] += 0.2
    a.pulsacion()
    assert eventos[-1] == "interrupción"


def test_un_corte_de_una_grabacion_anterior_no_cierra_la_nueva(entorno):
    a, eventos, micros, procesados, poner = entorno
    poner(fin_por_silencio=True)
    a.pulsacion()
    vieja = a._grabacion_n
    a.pulsacion()                                                            # termina pulsando
    a.estado = "esperando"
    a._corte_t = -1e9
    a.pulsacion()                                                            # una grabación nueva
    a._cortar(vieja, "fin")
    assert a.estado == "grabando" and len(procesados) == 1


def test_la_interrupcion_sigue_con_dos_pulsaciones(entorno, A):
    a, eventos, micros, procesados, poner = entorno
    poner(fin_por_silencio=True)
    del a._empezar_interrupcion                                              # la de verdad
    a.estado = "pensando"
    a.pulsacion()
    assert a.interrumpiendo and "blocksize" not in micros[-1].k              # sin detector
    micros[-1].dar(np.concatenate([silencio(0.5), voz(1), silencio(3)]))
    assert "pitido 520" not in eventos


def test_la_carrera_entre_el_corte_y_tu_pulsacion_procesa_una_sola_vez(entorno):
    """Determinista: los dos hilos esperan en una barrera y salen a la vez; gane quien gane el cerrojo, la frase se procesa una vez y no empieza
    ninguna escucha nueva (si gana el corte, tu pulsación cae en el margen)."""
    a, eventos, micros, procesados, poner = entorno
    poner(fin_por_silencio=True)
    for _ in range(50):
        eventos.clear()
        procesados.clear()
        a.estado, a._corte_t = "esperando", -1e9
        a.pulsacion()
        n = a._grabacion_n
        barrera = threading.Barrier(2)

        def corte(barrera, n):
            barrera.wait()
            a._cortar(n, "fin")

        def pulsar(barrera):
            barrera.wait()
            a.pulsacion()
        hilos = [threading.Thread(target=corte, args=(barrera, n)), threading.Thread(target=pulsar, args=(barrera,))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(5)
        assert len(procesados) == 1, eventos
        assert eventos.count("pitido 520") == 1 and eventos.count("cerrar") == 1 and "interrupción" not in eventos


# ---------------------------------------------------------------- los ajustes
def test_ajustes_de_fabrica_y_rangos():
    esq = AJ.ESQUEMA["activacion"]
    assert esq["fin_por_silencio"][0] is False                               # apagado de fábrica: doble pulsación
    assert esq["silencio_atajo"][0] == 1.0 and esq["silencio_atajo"][2] == (0.5, 3.0)
    assert esq["espera_atajo"][0] == 6 and esq["espera_atajo"][2] == (2, 20)
    with pytest.raises(ValueError):
        AJ.validar("activacion", "silencio_atajo", 0.2)
