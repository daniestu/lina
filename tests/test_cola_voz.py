# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Cola de voz (fase 17, V1): Lina habla de una en una y en orden, cada frase con su audio (también en la caché), «cállate» calla todo, los avisos de
espera caducan cuando ya se dijo la respuesta, y un aviso o una confirmación que no llega a decirse sale como notificación. Piper y paplay simulados."""
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lina.nucleo import cache_voz as CV

A = None


class _Paplay:
    """paplay simulado: lee el audio al empezar (para saber qué suena) y cuenta cuántos suenan a la vez."""
    activos, maximo, sonado, dura, colgado = 0, 0, [], 0.05, None
    cerrojo = threading.Lock()

    def __init__(self, orden, **k):
        self.texto = Path(orden[1]).read_text(encoding="utf-8").strip()
        self.cortado = threading.Event()
        with _Paplay.cerrojo:
            _Paplay.activos += 1
            _Paplay.maximo = max(_Paplay.maximo, _Paplay.activos)
            _Paplay.sonado.append(self.texto)

    def wait(self):
        espera = _Paplay.colgado if _Paplay.colgado is not None else None
        if espera is not None:
            espera.wait(5)
        else:
            self.cortado.wait(_Paplay.dura)
        with _Paplay.cerrojo:
            _Paplay.activos -= 1

    def terminate(self):
        self.cortado.set()


class _Residente:
    """Piper residente simulado: escribe en el audio el texto de la frase (relleno para que la caché lo acepte)."""
    def sintetizar(self, modelo, carpeta, locutor, escala, texto, salida):
        time.sleep(0.01)
        Path(salida).write_text(texto + " " * 60, encoding="utf-8")
        return True


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    global A
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente
    A = asistente
    _Paplay.activos, _Paplay.maximo, _Paplay.sonado, _Paplay.dura, _Paplay.colgado = 0, 0, [], 0.05, None
    monkeypatch.setattr(A.subprocess, "Popen", _Paplay)
    monkeypatch.setattr(A, "_piper_residente", lambda: _Residente())
    monkeypatch.setattr(CV, "CARPETA", tmp_path / "cache")
    avisos = []
    monkeypatch.setattr(A.H, "notificar", lambda titulo, texto: avisos.append(texto))
    return avisos


def _asistente():
    a = A.Asistente.__new__(A.Asistente)
    a.reproductor, a.estado, a.cerrojo = None, "esperando", threading.Lock()
    a.ejecutor = MagicMock()
    a.ejecutor.pendientes = []
    return a


def _en_hilos(*funciones, separacion=0.02):
    hilos = []
    for f in funciones:
        h = threading.Thread(target=f)
        h.start()
        hilos.append(h)
        time.sleep(separacion)
    return hilos


def _esperar(hilos):
    for h in hilos:
        h.join(5)


def test_de_una_en_una_cada_frase_con_su_audio_y_en_orden():
    a = _asistente()
    textos = ["frase alfa", "frase beta", "frase gamma", "frase delta", "frase épsilon"]
    _esperar(_en_hilos(*[lambda t=t: a._hablar(t) for t in textos]))
    assert _Paplay.maximo == 1
    assert _Paplay.sonado == textos                                # cada una su propio audio, y en el orden en que se pidieron


def test_la_cache_guarda_cada_frase_con_su_audio(tmp_path):
    a = _asistente()
    textos = ["hecho", "abierto", "parada", "pausado"]
    _esperar(_en_hilos(*[lambda t=t: a._hablar(t) for t in textos], separacion=0))
    voz = A.VOC.voz_elegida() or A.VOZ
    velocidad = A.AJ.actuales(log=lambda m: None).get("voz", "velocidad")
    for t in textos:
        ruta = CV.buscar(A.VOC.modelo(voz), A.VOC.locutor(voz), velocidad, t)
        assert ruta and Path(ruta).read_text(encoding="utf-8").strip() == t, t


def test_callar_corta_lo_que_suena_y_descarta_lo_que_esperaba(entorno):
    a = _asistente()
    _Paplay.dura = 2
    hilos = _en_hilos(lambda: a._hablar("una respuesta larga"), lambda: a._hablar("ya ha terminado la instalación", tipo="aviso"),
                      lambda: a._hablar("otra cosa"))
    a.callar()
    _esperar(hilos)
    assert _Paplay.sonado == ["una respuesta larga"]
    assert entorno == ["ya ha terminado la instalación"]           # el aviso de segundo plano no se pierde: sale como notificación
    _Paplay.dura = 0.01
    a._hablar("después sí")
    assert _Paplay.sonado[-1] == "después sí"


def test_una_confirmacion_que_se_descarta_sale_como_notificacion(entorno):
    a = _asistente()
    a.ejecutor.pendientes = [{"comando": "shutdown -h +60"}]
    _Paplay.dura = 2
    hilos = _en_hilos(lambda: a._hablar("algo que estaba diciendo"), lambda: a.decir("Voy a apagar el equipo dentro de 60 minutos, ¿lo hago?"))
    a.callar()
    _esperar(hilos)
    assert entorno == ["Voy a apagar el equipo dentro de 60 minutos, ¿lo hago?"]      # en la notificación, con cifras


def test_una_confirmacion_que_espera_demasiado_sale_como_notificacion(entorno, monkeypatch):
    a = _asistente()
    a.ejecutor.pendientes = [{"comando": "x"}]
    monkeypatch.setattr(A, "ESPERA_TURNO_VOZ", 0.3)
    _Paplay.colgado = threading.Event()                            # un paplay que no termina
    hilos = _en_hilos(lambda: a._hablar("se ha quedado colgado"), lambda: a.decir("¿Borro la carpeta vieja?"))
    hilos[1].join(3)
    assert not hilos[1].is_alive() and entorno == ["¿Borro la carpeta vieja?"]   # Lina no se queda muda esperando para siempre
    _Paplay.colgado.set()
    _esperar(hilos)
    _Paplay.colgado = None
    a._hablar("y luego sigue hablando")
    assert _Paplay.sonado[-1] == "y luego sigue hablando"


def test_los_avisos_de_espera_caducan_si_ya_se_dijo_la_respuesta(entorno):
    a = _asistente()
    a._n_peticion = 1
    _Paplay.dura = 0.2
    hilos = _en_hilos(lambda: a._hablar("algo de antes"), lambda: a.decir("La respuesta."), lambda: a._avisar_voz("Google está tardando en responder.").join(5))
    _esperar(hilos)
    assert _Paplay.sonado == ["algo de antes", "La respuesta."] and entorno == []   # caduca sin notificación: no hacía falta


def test_un_aviso_de_espera_anterior_a_la_respuesta_si_se_dice():
    a = _asistente()
    a._n_peticion = 1
    _Paplay.dura = 0.1
    hilos = _en_hilos(lambda: a._avisar_voz("Vale, lo pienso a fondo.").join(5), lambda: a.decir("La respuesta."))
    _esperar(hilos)
    assert _Paplay.sonado == ["Vale, lo pienso a fondo.", "La respuesta."]


def test_la_espera_del_turno_no_cuenta_como_sintesis():
    a = _asistente()
    _Paplay.dura = 0.4
    hilos = _en_hilos(lambda: a._hablar("la primera"), lambda: a._hablar("la segunda"))
    _esperar(hilos)
    assert a.ultima_habla[0] < 0.2                                 # síntesis de la segunda: sin los 0,4 s que esperó su turno


def test_decir_cambia_el_estado_con_el_cerrojo():
    a = _asistente()
    a.cerrojo.acquire()
    hilo = threading.Thread(target=lambda: a.decir("hola"))
    hilo.start()
    time.sleep(0.1)
    assert a.estado == "esperando"                                 # no lo cambia mientras otro tiene el cerrojo
    a.cerrojo.release()
    hilo.join(5)
    assert a.estado == "hablando"
